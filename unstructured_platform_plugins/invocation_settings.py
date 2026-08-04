"""Transport for the reserved `/invoke` fields: ASGI middleware, `/metadata`, request binding.

The *contract* — which keys carry settings, how a sealed envelope is told from plaintext, and what
an absent field is allowed to mean — lives in `utic_invocation_settings.invoke`, next to the crypto
it governs. This module is the other half: getting the payload off the wire and the result to the
handler. It owns no policy; every decision about a payload it delegates.

The reserved fields are a first-class HTTP contract independent of the generated input schema. They
never appear in a plugin's declared signature, so `wrap_in_fastapi` keeps producing a handler model
built purely from the wrapped function, and a plugin reads the fields through
`current_invocation_settings()` / `current_invocation_context()` instead.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional, TypeVar

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send
from utic_invocation_settings import (
    INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_CAPABILITY,
    RESERVED_CONTEXT_KEY,
    RESERVED_ENVELOPE_KEY,
    InvocationContext,
    InvocationSettingsError,
    MalformedEnvelopeError,
    extract_context,
    http_status_for,
    resolve_invocation_settings,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

_METADATA_PATH = "/metadata"
_INVOKE_PATH = "/invoke"

# Bounds middleware body buffering; generous because batch invokes carry an array of file_data
# payloads. The framework buffers the same body afterward, so this cap is the only guard against
# unbounded-memory requests.
MAX_INVOKE_BODY_BYTES = 64 * 1024 * 1024

_INVOCATION: ContextVar[tuple[Optional[dict], Optional[InvocationContext]]] = ContextVar(
    "invocation", default=(None, None)
)


def current_invocation_settings() -> Optional[dict]:
    """Reserved `invocation_settings` field bound for the current request, if any.

    `None` means the field was genuinely absent — the only case in which a plugin may fall back to
    its boot-time settings. A field that arrived and could not be opened never reaches a handler:
    the middleware fails the request first.
    """
    return _INVOCATION.get()[0]


def current_invocation_context() -> Optional[InvocationContext]:
    """Reserved `invocation_context` field bound for the current request, if any."""
    return _INVOCATION.get()[1]


@contextmanager
def invocation_envelope(
    invocation_settings: Optional[dict], invocation_context: Optional[InvocationContext]
) -> Iterator[None]:
    """Bind the reserved /invoke fields for the current context."""
    token = _INVOCATION.set((invocation_settings, invocation_context))
    try:
        yield
    finally:
        _INVOCATION.reset(token)


def add_metadata_route(
    app: FastAPI,
    identifier: Optional[str] = None,
    invoke_with_sealed_dag_node_settings: bool = False,
) -> None:
    """Register GET /metadata advertising the reserved /invoke fields this plugin accepts.

    `/metadata` is the plugin API spec's own discovery surface (`PluginMetadataOutput`): capability
    flags are strings in its `capabilities` list, which is where the controller looks before
    forwarding the reserved fields — no controller-private probe route.

    The two tiers make different claims. `invocation_settings` / `invocation_context` are
    *transport-level* facts, advertised unconditionally because the installed middleware makes
    them true for every wrapped app: the reserved fields will be received, resolved, and bound —
    or the request failed. They say nothing about whether the handler reads the binding.
    `invoke_with_sealed_dag_node_settings` is the *consumption* claim — this plugin opens sealed
    `dag_node_settings` itself and its handler acts on the result — and stays a per-plugin opt-in
    set in the same change that makes it true, because it is the flag that invites the controller
    to seal settings to this pod in place of any other settings source.

    Last call wins: the payload lives on `app.state` and every call overwrites it, while the route
    is registered once. A host wrapper may register with default capabilities at app construction
    and a plugin can still declare the sealed capability afterwards, with no route-order dependence.
    """
    capabilities = [RESERVED_ENVELOPE_KEY, RESERVED_CONTEXT_KEY]
    if invoke_with_sealed_dag_node_settings:
        capabilities.append(INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_CAPABILITY)
    app.state.plugin_metadata_payload = {
        "api_version": "3",
        "identifier": identifier,
        "capabilities": capabilities,
    }
    if getattr(app.state, "plugin_metadata_route_installed", False):
        return
    app.state.plugin_metadata_route_installed = True

    # A /metadata route registered by the application itself would win by route order and pin its
    # own stale payload; drop it so the last add_metadata_route call is the one that answers.
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != _METADATA_PATH]

    @app.get(_METADATA_PATH)
    async def plugin_metadata() -> dict:
        return app.state.plugin_metadata_payload


async def _send_json(send: Send, status_code: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class InvocationEnvelopeMiddleware:
    """Extract the reserved envelope fields from the raw POST /invoke body.

    Pure ASGI rather than `BaseHTTPMiddleware`: the body has to be read before the framework parses
    it and then replayed intact, which is exactly what the raw protocol allows and what a
    request/response middleware would fight.

    A reserved field that is present but unusable fails the request rather than being treated as
    absent, because absence is the signal to fall back to the boot-time settings file: degrading a
    malformed field to absence would quietly answer a request configured for one tenant with
    whatever the pod happened to boot with. Under `FF_REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS`
    there is no settings file to fall back to, so absent or plaintext settings fail too — as does
    any /invoke whose body is not a JSON object, since such a body cannot carry the envelope a
    native pod requires. A body over `max_body_bytes` is rejected with 413 before it can exhaust
    memory.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_INVOKE_BODY_BYTES):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != _INVOKE_PATH
        ):
            await self.app(scope, receive, send)
            return

        messages = []
        buffered_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            buffered_bytes += len(message.get("body", b""))
            if buffered_bytes > self.max_body_bytes:
                await _send_json(send, 413, {"detail": "Request body too large"})
                return
            if message["type"] != "http.request" or not message.get("more_body"):
                break
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.request")

        try:
            parsed = json.loads(body) if body else None
        except ValueError:
            # Malformed JSON: forward unchanged so the framework returns its own error.
            parsed = None

        invocation_context: Optional[InvocationContext] = None
        raw_settings: Optional[dict[str, Any]] = None
        if isinstance(parsed, dict):
            raw_settings = parsed.get(RESERVED_ENVELOPE_KEY)
            if RESERVED_ENVELOPE_KEY in parsed and not isinstance(raw_settings, dict):
                await _send_json(
                    send,
                    422,
                    {
                        "detail": f"Invalid field: {RESERVED_ENVELOPE_KEY}",
                        "reason": MalformedEnvelopeError.reason,
                    },
                )
                return
        # Resolved even when the field — or the whole JSON object — is absent:
        # resolve_invocation_settings owns the FF_REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS
        # policy, under which a bodyless or non-object invoke cannot carry the envelope a native
        # pod requires and is a failure, not a fallback signal.
        try:
            # Off the event loop: a cold resolve is an RSA unwrap of a couple of milliseconds, and
            # this middleware sits in front of every invoke on the pod.
            invocation_settings = await asyncio.to_thread(resolve_invocation_settings, raw_settings)
        except Exception as exc:
            # Class name only — never envelope contents, and never the exception's own message,
            # which can embed request-controlled values.
            logger.warning("unusable %s payload: %s", RESERVED_ENVELOPE_KEY, type(exc).__name__)
            body = {"detail": f"Unusable invocation settings: {type(exc).__name__}"}
            reason = getattr(exc, "reason", None)
            if isinstance(reason, str):
                body["reason"] = reason
            await _send_json(send, http_status_for(exc), body)
            return
        if isinstance(parsed, dict):
            try:
                invocation_context = extract_context(parsed)
            except InvocationSettingsError as exc:
                # A context this plugin cannot read fails loudly here rather than running with
                # silently absent identity. Status comes from the blame taxonomy: a malformed
                # field is the caller's 422, but an unreadable schema_version is deployment skew
                # between platform components and must not read as a caller fault. The log line is
                # truncated because the message can embed request-controlled values.
                logger.warning("rejecting invalid %s: %.200s", RESERVED_CONTEXT_KEY, exc)
                status = http_status_for(exc)
                detail = (
                    f"Invalid field: {RESERVED_CONTEXT_KEY}"
                    if status == 422
                    else f"Unusable {RESERVED_CONTEXT_KEY}: {type(exc).__name__}"
                )
                await _send_json(send, status, {"detail": detail, "reason": exc.reason})
                return

        # The joined body and its parsed tree can be tens of MB and are not needed past this point;
        # the framework re-buffers and re-parses the replayed messages downstream, so holding these
        # through the handler would double peak memory.
        del body, parsed, raw_settings

        async def replay() -> dict:
            if messages:
                return messages.pop(0)
            # Buffer drained: proxy the original channel so downstream still observes
            # http.disconnect.
            return await receive()

        with invocation_envelope(invocation_settings, invocation_context):
            await self.app(scope, replay, send)


def install_invocation_envelope(app: FastAPI) -> None:
    """Install out-of-schema envelope extraction on a FastAPI app.

    Idempotent per app: a host wrapper may install at app construction while a plugin that predates
    the wrapper's support still calls this itself, and a double install would buffer and replay the
    request body twice.
    """
    if getattr(app.state, "invocation_envelope_installed", False):
        return
    app.state.invocation_envelope_installed = True
    app.add_middleware(InvocationEnvelopeMiddleware)


def settings_cache_key(invocation_settings: Mapping[str, Any]) -> str:
    """Digest of the canonical settings JSON, safe as a cache key for secret-bearing payloads."""
    return hashlib.sha256(json.dumps(invocation_settings, sort_keys=True).encode()).hexdigest()


class SettingsScopedCache:
    """Bind expensive derived state (clients, models, handlers) to the settings that built it.

    A plugin consuming ``current_invocation_settings()`` builds its handler per distinct settings
    payload instead of once at boot, and construction typically does network work (model
    resolution, prechecks), so results are memoized keyed by ``settings_cache_key``. Both bounds
    matter under shared tenancy: size caps how many distinct payloads stay live, and age evicts
    state built from credentials that may since have been rotated — eviction driven only by the
    count of distinct payloads can take arbitrarily long on a quiet pod.

    Thread-safe for lookups and inserts. Concurrent misses for the same settings may build twice;
    the extra build is wasted work, never wrong state.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = 15 * 60,
        maxsize: int = 32,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if maxsize < 1:
            raise ValueError("maxsize must be at least 1")
        self._ttl_seconds = float(ttl_seconds)
        self._maxsize = maxsize
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get_or_build(self, invocation_settings: Mapping[str, Any], build: Callable[[], T]) -> T:
        """Return the cached value for these settings, building it on a miss."""
        key = settings_cache_key(invocation_settings)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                expires_at, value = entry
                if now < expires_at:
                    self._entries.move_to_end(key)
                    return value
                del self._entries[key]
        value = build()
        with self._lock:
            self._entries[key] = (now + self._ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
