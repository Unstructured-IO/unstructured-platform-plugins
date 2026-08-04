"""The transport for the reserved /invoke fields: middleware, /metadata, request-scoped binding.

The *contract* these exercise — which shapes carry settings, what absence means — is owned and
tested in `utic_invocation_settings`. What is tested here is delivery: that a raw body is read,
resolved, bound, and replayed intact, and that a payload which cannot be used fails the request
instead of reaching a handler as absence.
"""

from __future__ import annotations

import asyncio
import json
from base64 import b64decode, b64encode

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from utic_invocation_settings import (
    DAG_NODE_SETTINGS_KEY,
    REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR,
    default_resolver,
    reset_workload_identity_cache,
)
from utic_invocation_settings.crypto import seal_settings

from unstructured_platform_plugins.invocation_settings import (
    InvocationEnvelopeMiddleware,
    add_metadata_route,
    current_invocation_context,
    current_invocation_settings,
)

SENTINEL_SECRET = "sealed-settings-sentinel-secret"


@pytest.fixture(scope="session")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


@pytest.fixture(autouse=True)
def isolated_identity(monkeypatch):
    """The identity memo and the resolver caches both outlive a test; an inherited env var or a
    stale entry would make these order-dependent."""
    for var in ("WORKLOAD_IDENTITY_DIR", "INVOCATION_SETTINGS_KEY_DIR",
                REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR):
        monkeypatch.delenv(var, raising=False)
    reset_workload_identity_cache()
    default_resolver().clear_caches()
    yield
    reset_workload_identity_cache()
    default_resolver().clear_caches()


@pytest.fixture
def key_dir(tmp_path, private_key, monkeypatch, isolated_identity):
    (tmp_path / "tls.key").write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("WORKLOAD_IDENTITY_DIR", str(tmp_path))
    reset_workload_identity_cache()
    return tmp_path


def sealed_payload(private_key: rsa.RSAPrivateKey, settings: dict) -> dict:
    return seal_settings(settings, private_key.public_key()).model_dump(
        mode="json", exclude_none=True
    )


def tampered(sealed: dict) -> dict:
    ciphertext = bytearray(b64decode(sealed["content_encryption"]["ciphertext"]))
    ciphertext[0] ^= 0x01
    sealed["content_encryption"]["ciphertext"] = b64encode(bytes(ciphertext)).decode()
    return sealed


class TestMetadataRoute:
    def test_advertises_settings_and_context_capabilities(self):
        app = FastAPI()
        add_metadata_route(app, identifier="plugin.test")

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload == {
            "api_version": "3",
            "identifier": "plugin.test",
            "capabilities": ["invocation_settings", "invocation_context"],
        }

    def test_sealed_dag_node_settings_flag_advertises_capability(self):
        app = FastAPI()
        add_metadata_route(app, invoke_with_sealed_dag_node_settings=True)

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload["capabilities"] == [
            "invocation_settings",
            "invocation_context",
            "invoke_with_sealed_dag_node_settings",
        ]

    def test_last_call_wins(self):
        # A host wrapper registers /metadata with defaults at construction; the plugin's later call
        # with the sealed capability must replace it, not be shadowed by route order.
        app = FastAPI()
        add_metadata_route(app, identifier="plugin.test")
        add_metadata_route(app, identifier="plugin.test", invoke_with_sealed_dag_node_settings=True)

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert "invoke_with_sealed_dag_node_settings" in payload["capabilities"]

    def test_replaces_a_directly_registered_metadata_route(self):
        # A route the app registered itself would otherwise win by route order and pin its stale
        # payload.
        app = FastAPI()

        @app.get("/metadata")
        async def stale_metadata() -> dict:
            return {"api_version": "3", "identifier": "stale", "capabilities": []}

        add_metadata_route(app, identifier="plugin.test", invoke_with_sealed_dag_node_settings=True)

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload["identifier"] == "plugin.test"
        assert "invoke_with_sealed_dag_node_settings" in payload["capabilities"]


def _invoke_scope(path: str = "/invoke", method: str = "POST") -> dict:
    return {"type": "http", "method": method, "path": path}


def _receive_for(body: bytes):
    chunks = [
        {"type": "http.request", "body": body[: len(body) // 2], "more_body": True},
        {"type": "http.request", "body": body[len(body) // 2 :], "more_body": False},
    ]

    async def receive():
        return chunks.pop(0)

    return receive


async def _ok(send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


class _DownstreamApp:
    """Records the replayed body and the envelope bound while handling."""

    def __init__(self):
        self.body = None
        self.called = False
        self.seen_settings = "unset"
        self.seen_context = "unset"

    async def __call__(self, scope, receive, send):
        body = b""
        while True:
            message = await receive()
            body += message.get("body", b"")
            if not message.get("more_body"):
                break
        self.body = body
        self.called = True
        self.seen_settings = current_invocation_settings()
        self.seen_context = current_invocation_context()
        await _ok(send)


def _run_middleware(body: bytes, scope: dict | None = None) -> tuple[_DownstreamApp, list]:
    downstream = _DownstreamApp()
    middleware = InvocationEnvelopeMiddleware(downstream)
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope or _invoke_scope(), _receive_for(body), send))
    return downstream, sent


class TestInvocationEnvelopeMiddleware:
    def test_binds_reserved_fields_and_replays_body(self):
        body = json.dumps(
            {
                "element_dicts": "/in.json",
                "invocation_settings": {"model": "m"},
                "invocation_context": {"schema_version": "1", "job_id": "job-1"},
            }
        ).encode()

        downstream, sent = _run_middleware(body)

        assert downstream.body == body
        assert downstream.seen_settings == {"model": "m"}
        assert downstream.seen_context.job_id == "job-1"
        assert sent[0]["status"] == 200

    def test_absent_fields_bind_none(self):
        downstream, _ = _run_middleware(json.dumps({"element_dicts": "/in.json"}).encode())

        assert downstream.seen_settings is None
        assert downstream.seen_context is None

    def test_non_dict_reserved_field_is_rejected(self):
        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": "not-a-dict"}).encode()
        )

        assert downstream.body is None
        assert sent[0]["status"] == 422
        assert b"invocation_settings" in sent[1]["body"]

    def test_context_with_an_unreadable_schema_version_fails_as_platform_error(self):
        # Absence means "older caller, use the boot settings"; a context this plugin cannot read
        # must not be downgraded to that. And it is deployment skew, not a caller fault — a 422
        # would let an upstream blame classifier pin version skew on the customer.
        downstream, sent = _run_middleware(
            json.dumps({"invocation_context": {"schema_version": "99"}}).encode()
        )

        assert downstream.body is None
        assert sent[0]["status"] == 500
        assert b"invocation_context" in sent[1]["body"]
        assert b"UnsupportedContextVersionError" in sent[1]["body"]

    def test_malformed_context_is_rejected(self):
        downstream, sent = _run_middleware(
            json.dumps({"invocation_context": "not-an-object"}).encode()
        )

        assert downstream.body is None
        assert sent[0]["status"] == 422

    def test_non_invoke_requests_pass_through_untouched(self):
        body = json.dumps({"invocation_settings": "not-a-dict"}).encode()

        downstream, sent = _run_middleware(body, scope=_invoke_scope(path="/schema", method="GET"))

        assert downstream.body == body
        assert sent[0]["status"] == 200

    def test_envelope_is_reset_after_request(self):
        body = json.dumps({"invocation_settings": {"model": "m"}}).encode()

        async def scenario():
            middleware = InvocationEnvelopeMiddleware(_DownstreamApp())

            async def send(_message):
                pass

            await middleware(_invoke_scope(), _receive_for(body), send)
            return current_invocation_settings(), current_invocation_context()

        assert asyncio.run(scenario()) == (None, None)

    def test_oversized_body_is_rejected(self):
        body = json.dumps({"invocation_settings": {"pad": "x" * 64}}).encode()

        downstream = _DownstreamApp()
        middleware = InvocationEnvelopeMiddleware(downstream, max_body_bytes=16)
        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(_invoke_scope(), _receive_for(body), send))

        assert downstream.body is None
        assert sent[0]["status"] == 413

    def test_drained_replay_proxies_disconnect(self):
        body = json.dumps({"invocation_settings": {"model": "m"}}).encode()

        class _DisconnectWatcher:
            def __init__(self):
                self.saw_disconnect = False

            async def __call__(self, scope, receive, send):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        self.saw_disconnect = True
                        return
                    if not message.get("more_body"):
                        break
                message = await receive()
                self.saw_disconnect = message["type"] == "http.disconnect"
                await _ok(send)

        chunks = [
            {"type": "http.request", "body": body, "more_body": False},
            {"type": "http.disconnect"},
        ]

        async def receive():
            return chunks.pop(0)

        watcher = _DisconnectWatcher()
        middleware = InvocationEnvelopeMiddleware(watcher)
        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(middleware(_invoke_scope(), receive, send))

        assert watcher.saw_disconnect


class TestMiddlewareResolution:
    """Sealed payloads through the middleware. The HTTP class comes from the library's blame
    taxonomy, so only a caller-fixable fault is a 422."""

    def test_sealed_envelope_binds_plaintext_settings(self, key_dir, private_key):
        settings = {"api_key": SENTINEL_SECRET, "max_characters": 700}
        sealed = sealed_payload(private_key, settings)

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": sealed}).encode()
        )

        assert sent[0]["status"] == 200
        assert downstream.seen_settings == settings

    def test_composite_dag_node_settings_member_is_opened(self, key_dir, private_key):
        settings = {"api_key": SENTINEL_SECRET, "max_characters": 700}
        composite = {DAG_NODE_SETTINGS_KEY: sealed_payload(private_key, settings)}

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": composite}).encode()
        )

        assert sent[0]["status"] == 200
        assert downstream.seen_settings == settings

    def test_plain_dict_settings_pass_through(self):
        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": {"model": "m"}}).encode()
        )

        assert sent[0]["status"] == 200
        assert downstream.seen_settings == {"model": "m"}

    def test_non_envelope_member_fails_as_platform_error(self, key_dir):
        composite = {DAG_NODE_SETTINGS_KEY: {"model": "m"}}

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": composite}).encode()
        )

        assert sent[0]["status"] == 500
        assert "MalformedDagNodeSettingsError" in json.loads(sent[1]["body"])["detail"]
        assert not downstream.called

    def test_undecryptable_envelope_fails_without_leaking_the_secret(
        self, key_dir, private_key, caplog
    ):
        sealed = tampered(sealed_payload(private_key, {"api_key": SENTINEL_SECRET}))

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": sealed}).encode()
        )

        assert sent[0]["status"] == 500
        detail = json.loads(sent[1]["body"])["detail"]
        assert "DecryptionError" in detail
        assert SENTINEL_SECRET not in caplog.text
        assert SENTINEL_SECRET not in detail
        assert not downstream.called

    def test_unmounted_identity_fails_as_platform_error(self, tmp_path, monkeypatch, private_key):
        monkeypatch.setenv("WORKLOAD_IDENTITY_DIR", str(tmp_path / "missing"))
        sealed = sealed_payload(private_key, {"api_key": SENTINEL_SECRET})

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": sealed}).encode()
        )

        assert sent[0]["status"] == 500
        assert "IdentityNotMountedError" in json.loads(sent[1]["body"])["detail"]
        assert not downstream.called


class TestRequireSealedDagNodeSettings:
    """A native pod's operator sets FF_REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS in the same
    decision that drops the init-secrets sidecar: without it, an invoke that arrived with no
    envelope would fall back to a settings file that was never written."""

    @pytest.fixture(autouse=True)
    def _require_sealed(self, monkeypatch):
        monkeypatch.setenv(REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR, "true")

    def test_missing_settings_fail_as_platform_error(self):
        downstream, sent = _run_middleware(json.dumps({"element_dicts": "/tmp/x.json"}).encode())

        assert sent[0]["status"] == 500
        assert "SealedDagNodeSettingsRequiredError" in json.loads(sent[1]["body"])["detail"]
        assert not downstream.called

    def test_plaintext_settings_fail_as_platform_error(self):
        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": {"model": "m"}}).encode()
        )

        assert sent[0]["status"] == 500
        assert not downstream.called

    def test_sealed_settings_still_bind(self, key_dir, private_key):
        settings = {"api_key": SENTINEL_SECRET}
        composite = {DAG_NODE_SETTINGS_KEY: sealed_payload(private_key, settings)}

        downstream, sent = _run_middleware(
            json.dumps({"invocation_settings": composite}).encode()
        )

        assert sent[0]["status"] == 200
        assert downstream.seen_settings == settings

    def test_bodyless_invoke_fails_as_platform_error(self):
        # A bodyless invoke cannot carry the envelope; on a pod with no boot settings file it must
        # not dispatch a handler with no settings source at all.
        downstream, sent = _run_middleware(b"")

        assert sent[0]["status"] == 500
        assert not downstream.called

    def test_non_object_json_body_fails_as_platform_error(self):
        downstream, sent = _run_middleware(json.dumps([{"element": 1}]).encode())

        assert sent[0]["status"] == 500
        assert not downstream.called


def test_non_object_bodies_pass_through_when_sealed_settings_not_required():
    downstream, sent = _run_middleware(b"")

    assert sent[0]["status"] == 200
    assert downstream.seen_settings is None
