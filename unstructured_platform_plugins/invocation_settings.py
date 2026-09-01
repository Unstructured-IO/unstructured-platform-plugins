"""Transport for the reserved `/invoke` fields: request dependency, `/metadata`, optional body cap.

The *settings contract* — including the only accepted sealed `/invoke` shape (the v2 settings
document), field-level resolution, and what an absent field is allowed to mean — lives in
`utic_invocation_settings`, next to the crypto it governs; every decision about a settings payload
is delegated there. The *identity contract* —
the `invocation_context` model — is
`/invoke` protocol rather than settings security and lives in this package's
`invocation_context` module. This module is the delivery mechanism for both: getting the payloads
off the wire and the results to the handler, and spelling the shared `blame` taxonomy as HTTP
statuses.

The reserved fields are a first-class HTTP contract independent of the generated input schema.
They never appear in a plugin's declared signature, so `wrap_in_fastapi` keeps producing a handler
model built purely from the wrapped function, and a plugin reads the fields through
`current_invocation_settings()` / `current_invocation_context()` instead.

Well-formed extraction runs in a route dependency (`bind_invocation_envelope`), so the `/invoke`
body is buffered and parsed exactly once: Starlette caches both the bytes and the parsed JSON on
the `Request`, and the dependency reads that cached parse. Generated routes can reject malformed
JSON while validating their typed body before dependencies run, so the installer normalizes that
specific validation failure to the same transport error. Hosts that have established a safe
request ceiling may opt into `InvokeBodyLimitMiddleware`, which counts bytes as they stream through
without buffering. Wrapped plugins do not acquire a fleet-wide limit merely by upgrading this
package.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional, TypeVar

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse
from starlette.routing import get_route_path
from starlette.types import ASGIApp, Receive, Scope, Send
from utic_invocation_settings import (
    INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_V2_CAPABILITY,
    RESERVED_ENVELOPE_KEY,
    Blame,
    InvocationSettingsError,
    MalformedEnvelopeError,
    resolve_invocation_settings,
)

from unstructured_platform_plugins.invocation_context import (
    RESERVED_CONTEXT_KEY,
    InvocationContext,
    extract_context,
)

logger = logging.getLogger(__name__)


def http_status_for(error: BaseException) -> int:
    """The HTTP status this transport answers for a failed resolution, from ``blame``.

    One rule, the one the library README states normatively: ``Blame.CALLER`` -> 422, everything
    else -> 500. The line it draws is whether a different request would work. Sealing drift, an
    envelope for another recipient and a broken local mount are all 5xx, which keeps a controller's
    blame classification off the customer, whose request was fine. Anything that is not a
    classified error is a 500: an unclassified failure is not the caller's.
    """
    return 422 if getattr(error, "blame", None) is Blame.CALLER else 500


T = TypeVar("T")

_METADATA_PATH = "/metadata"
_INVOKE_PATH = "/invoke"

# A convenient opt-in ceiling for hosts that have verified it against their request distribution.
# It is deliberately not the install default: batch invokes carry arrays of file_data payloads,
# and a wrapper upgrade must not reject previously valid fleet traffic without an explicit choice.
MAX_INVOKE_BODY_BYTES = 64 * 1024 * 1024

_INVOCATION: ContextVar[tuple[Optional[dict], Optional[InvocationContext]]] = ContextVar(
    "invocation", default=(None, None)
)


def current_invocation_settings() -> Optional[dict]:
    """Reserved `invocation_settings` field bound for the current request, if any.

    `None` means the field was genuinely absent — the only case in which a plugin may fall back to
    its boot-time settings. A field that arrived and could not be opened never reaches a handler:
    the binding dependency fails the request first.
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
    invoke_with_sealed_dag_node_settings_v2: bool = False,
) -> None:
    """Register GET /metadata advertising the reserved /invoke fields this plugin accepts.

    `/metadata` is the plugin API spec's own discovery surface (`PluginMetadataOutput`): capability
    flags are strings in its `capabilities` list, which is where the controller looks before
    forwarding the reserved fields — no controller-private probe route.

    `invocation_settings` and `invocation_context` are transport capabilities: installing the
    dependency makes the host receive, resolve, and bind those fields. The sealed-settings
    capability is stronger: it tells the controller that the plugin handler consumes the resolved
    field-level v2 settings in place of boot-time state. The controller may therefore send the
    versioned v2 document, so this remains an explicit opt-in.

    Last call wins: the payload lives on `app.state` and every call overwrites it, while the route
    is registered once. A host wrapper may register at app construction and a plugin can still
    re-register with its own identifier afterwards, with no route-order dependence.
    """
    capabilities = [RESERVED_ENVELOPE_KEY, RESERVED_CONTEXT_KEY]
    if invoke_with_sealed_dag_node_settings_v2:
        capabilities.append(INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_V2_CAPABILITY)
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


class UnusableInvocationEnvelope(Exception):
    """A reserved /invoke field arrived but cannot be used.

    Raised by `bind_invocation_envelope` and answered by the handler
    `install_invocation_envelope` registers, so the response shape — `detail` plus the library's
    stable `reason` code as top-level siblings — stays what orchestrators parse, independent of
    FastAPI's own error envelope.
    """

    def __init__(self, status_code: int, payload: dict):
        super().__init__(payload.get("detail"))
        self.status_code = status_code
        self.payload = payload


async def _unusable_envelope_response(
    _request: Request, exc: UnusableInvocationEnvelope
) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.payload)


def _is_malformed_json_validation(exc: RequestValidationError) -> bool:
    """Whether FastAPI rejected the request body before route dependencies could run."""
    # A top-level JSONDecodeError stores the raw document and reports its integer parser offset as
    # exactly ("body", offset). Pydantic's Json fields also emit `json_invalid`, but by then the
    # outer request has been decoded into a mapping/list and the location continues through the
    # model field. Those are ordinary schema-validation errors and must retain FastAPI's detail.
    if not isinstance(exc.body, (str, bytes, bytearray)):
        return False
    return any(
        error.get("type") == "json_invalid"
        and len(location := tuple(error.get("loc", ()))) == 2
        and location[0] == "body"
        and isinstance(location[1], int)
        for error in exc.errors()
    )


async def bind_invocation_envelope(request: Request) -> AsyncIterator[None]:
    """Resolve the reserved /invoke fields and bind them for the duration of the request.

    Runs as a route dependency, after the framework has read the body: `request.json()` is
    Starlette-cached, so the parse is shared with the framework's own body handling.
    A reserved field that is present but unusable fails the request rather than being
    treated as absent, because absence is the signal to fall back to the boot-time settings file:
    degrading a malformed field to absence would quietly answer a request configured for one
    tenant with whatever the pod happened to boot with. Under
    `FF_INVOCATION_SETTINGS` there is no settings file to fall back to,
    so absent or plaintext settings fail too — as does any /invoke whose body is not a JSON
    object, since such a body cannot carry the envelope a native pod requires.
    """
    # ASGI `path` includes any deployment root_path; get_route_path strips it, which is how the
    # router itself matches, so binding fires exactly when the /invoke route does.
    if request.method != "POST" or get_route_path(request.scope) != _INVOKE_PATH:
        yield
        return

    try:
        parsed = await request.json()
    except ValueError:
        # request.json() reads through Starlette's cached body, so this does not consume or buffer
        # the stream a second time. A truly empty body is absence and remains subject to the
        # native-pod policy below. Any bytes that fail JSON parsing are a malformed request, not
        # absence: collapsing them would turn a caller-fixable syntax error into a native pod's
        # SealedDagNodeSettingsRequiredError (RECIPIENT -> 500).
        if await request.body():
            raise UnusableInvocationEnvelope(
                422,
                {
                    "detail": "Invalid JSON body",
                    "reason": MalformedEnvelopeError.reason,
                },
            ) from None
        parsed = None

    raw_settings: Optional[Any] = None
    if isinstance(parsed, dict):
        raw_settings = parsed.get(RESERVED_ENVELOPE_KEY)
        if RESERVED_ENVELOPE_KEY in parsed and not isinstance(raw_settings, dict):
            raise UnusableInvocationEnvelope(
                422,
                {
                    "detail": f"Invalid field: {RESERVED_ENVELOPE_KEY}",
                    "reason": MalformedEnvelopeError.reason,
                },
            )
    try:
        # Off the event loop: resolution may perform blocking cryptography for independently
        # sealed fields, and this dependency fronts every invoke on the pod.
        invocation_settings = await asyncio.to_thread(resolve_invocation_settings, raw_settings)
    except Exception as exc:
        # Class name only — never envelope contents, and never the exception's own message,
        # which can embed request-controlled values.
        logger.warning("unusable %s payload: %s", RESERVED_ENVELOPE_KEY, type(exc).__name__)
        payload = {"detail": f"Unusable invocation settings: {type(exc).__name__}"}
        reason = getattr(exc, "reason", None)
        if isinstance(reason, str):
            payload["reason"] = reason
        raise UnusableInvocationEnvelope(http_status_for(exc), payload) from exc

    invocation_context: Optional[InvocationContext] = None
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
            raise UnusableInvocationEnvelope(
                status, {"detail": detail, "reason": exc.reason}
            ) from exc

    with invocation_envelope(invocation_settings, invocation_context):
        yield


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


class InvokeBodyLimitMiddleware:
    """Reject a POST /invoke body over ``max_body_bytes`` with 413.

    Counts bytes as the framework consumes them; nothing is buffered here. When the count crosses
    the cap the downstream read is answered with ``http.disconnect``, which aborts the framework's
    body read before another byte is held, and the 413 is sent once the application has unwound.
    This has to sit below the framework because neither Starlette nor uvicorn bounds request-body
    size.
    """

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_INVOKE_BODY_BYTES):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or get_route_path(scope) != _INVOKE_PATH
        ):
            await self.app(scope, receive, send)
            return

        seen = 0
        exceeded = False
        response_started = False

        async def counting_receive() -> dict:
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_body_bytes:
                    exceeded = True
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: dict) -> None:
            nonlocal response_started
            if exceeded and not response_started:
                # A response computed after the body was cut is answering a truncated request;
                # drop it so the 413 below is what the caller sees. A response that started
                # before the cap tripped keeps streaming — its start is already on the wire.
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except ClientDisconnect:
            if not exceeded:
                raise
        except Exception as exc:
            # The cut body stream can surface downstream as something other than
            # ClientDisconnect; once the cap is the cause, the 413 below is the answer. Retain a
            # type-only diagnostic for a coincident downstream bug without rendering its message,
            # which may contain request data or credentials.
            if not exceeded:
                raise
            logger.debug(
                "downstream raised after /invoke body limit was exceeded: %s",
                type(exc).__name__,
            )
        if exceeded and not response_started:
            await _send_json(send, 413, {"detail": "Request body too large"})


def install_invocation_envelope(app: FastAPI, max_body_bytes: int | None = None) -> None:
    """Install reserved-field binding before registering a FastAPI app's routes.

    Adds `bind_invocation_envelope` through the router's public dependency list and registers the
    failure response shape. FastAPI parses a generated route's typed body before dependencies run,
    so malformed JSON validation is normalized to that same response shape at the app boundary;
    every other validation error retains the handler the app already had. When ``max_body_bytes``
    is supplied, also installs the body-size cap beneath the framework. The cap is opt-in because
    a wrapper upgrade must not impose an unvalidated fleet-wide request limit. The dependency is a
    path/method-aware no-op outside POST /invoke, so routes registered after this call can all
    inherit it without private dependency-graph mutation. Calling after routes have already been
    registered raises rather than silently leaving those routes uncovered.

    Idempotent per app because both host-wrapper and plugin setup may call this function, while a
    double installation would resolve settings twice per request. A repeated call asking for a
    different ``max_body_bytes`` raises because the installed configuration cannot be changed and
    silently keeping the first value would misrepresent the limit actually enforced.
    """
    if getattr(app.state, "invocation_envelope_installed", False):
        installed_max = app.state.invocation_envelope_max_body_bytes
        if max_body_bytes != installed_max:
            raise ValueError(
                "install_invocation_envelope already installed with "
                f"max_body_bytes={installed_max}; cannot reinstall with {max_body_bytes}"
            )
        return
    if any(
        getattr(route, "path", None) == _INVOKE_PATH
        and "POST" in (getattr(route, "methods", None) or set())
        for route in app.router.routes
    ):
        raise RuntimeError(
            "install_invocation_envelope must be called before the POST /invoke route is registered"
        )
    app.state.invocation_envelope_installed = True
    app.state.invocation_envelope_max_body_bytes = max_body_bytes
    app.router.dependencies.append(Depends(bind_invocation_envelope))
    if max_body_bytes is not None:
        app.add_middleware(InvokeBodyLimitMiddleware, max_body_bytes=max_body_bytes)
    app.add_exception_handler(UnusableInvocationEnvelope, _unusable_envelope_response)

    previous_validation_handler = app.exception_handlers.get(
        RequestValidationError, request_validation_exception_handler
    )

    async def invocation_request_validation_response(request: Request, exc: RequestValidationError):
        if (
            request.method == "POST"
            and get_route_path(request.scope) == _INVOKE_PATH
            and _is_malformed_json_validation(exc)
        ):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "Invalid JSON body",
                    "reason": MalformedEnvelopeError.reason,
                },
            )
        response = previous_validation_handler(request, exc)
        return await response if inspect.isawaitable(response) else response

    app.add_exception_handler(RequestValidationError, invocation_request_validation_response)


def settings_cache_key(invocation_settings: Mapping[str, Any]) -> str:
    """Digest of an ordinary resolved settings mapping, safe for secret-bearing values."""
    return hashlib.sha256(json.dumps(invocation_settings, sort_keys=True).encode()).hexdigest()


class SettingsScopedCache:
    """Bind expensive derived state (clients, models, handlers) to the settings that built it.

    A plugin consuming ``current_invocation_settings()`` derives a handler from each distinct
    resolved mapping. Construction typically performs network work (model resolution, prechecks),
    so results are memoized by ``settings_cache_key``. Raw field envelopes never reach this cache:
    the public settings library resolves and caches them at the field boundary before this
    transport binds the result. Both bounds matter under shared tenancy: size caps how many
    distinct mappings stay live, and age evicts state after credential rotation. Eviction driven
    only by the count of distinct mappings can take arbitrarily long on a quiet pod.

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
            # Every insert also sweeps entries whose TTL has lapsed, so a tenant that stops
            # sending requests does not keep its credential-bearing handler live while the pod
            # stays busy for others; per-key expiry alone only fires on that tenant's next hit.
            # Re-read the clock: build() may take long enough for more entries to lapse.
            now = self._clock()
            for stale_key, (expires_at, _) in list(self._entries.items()):
                if now >= expires_at:
                    del self._entries[stale_key]
            self._entries[key] = (now + self._ttl_seconds, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._maxsize:
                self._entries.popitem(last=False)
        return value

    def handler_for(
        self,
        resolved_settings: Optional[Mapping[str, Any]],
        *,
        boot: Callable[[], Optional[T]],
        build: Callable[[], T],
    ) -> T:
        """The handler for a request: cached per distinct resolved mapping, or the boot fallback.

        Absent settings select the single handler configured by the boot-time settings file.
        ``boot`` returning ``None`` means the pod has no boot configuration and sealed per-invoke
        settings are required, so the request fails rather than running an unconfigured handler.
        """
        if resolved_settings is None:
            handler = boot()
            if handler is None:
                raise ValueError(
                    "no boot-time handler on this pod: sealed per-invoke settings are required"
                )
            return handler
        return self.get_or_build(resolved_settings, build)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
