"""The transport for the reserved /invoke fields: dependency binding, /metadata, the body cap.

The *contract* these exercise — which shapes carry settings, what absence means — is owned and
tested in `utic_invocation_settings`. What is tested here is delivery: that the framework-parsed
body is resolved and bound for the handler, and that a payload which cannot be used fails the
request instead of reaching a handler as absence.
"""

from __future__ import annotations

import asyncio
import json
from base64 import b64decode, b64encode
from typing import Optional

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from utic_invocation_settings import (
    DAG_NODE_SETTINGS_KEY,
    REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR,
    default_resolver,
    reset_workload_identity_cache,
)
from utic_invocation_settings.crypto import seal_settings

from unstructured_platform_plugins.invocation_settings import (
    InvokeBodyLimitMiddleware,
    add_metadata_route,
    current_invocation_context,
    current_invocation_settings,
    install_invocation_envelope,
)

SENTINEL_SECRET = "sealed-settings-sentinel-secret"


@pytest.fixture(scope="session")
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=3072)


@pytest.fixture(autouse=True)
def isolated_identity(monkeypatch):
    """The identity memo and the resolver caches both outlive a test; an inherited env var or a
    stale entry would make these order-dependent."""
    for var in (
        "WORKLOAD_IDENTITY_DIR",
        "INVOCATION_SETTINGS_KEY_DIR",
        REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR,
    ):
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


BASE_CAPABILITIES = [
    "invocation_settings",
    "invocation_context",
]
ALL_CAPABILITIES = [
    *BASE_CAPABILITIES,
    "invoke_with_sealed_dag_node_settings",
]


class TestMetadataRoute:
    def test_advertises_transport_capabilities_by_default(self):
        app = FastAPI()
        add_metadata_route(app, identifier="plugin.test")

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload == {
            "api_version": "3",
            "identifier": "plugin.test",
            "capabilities": BASE_CAPABILITIES,
        }

    def test_sealed_consumption_capability_is_opt_in(self):
        app = FastAPI()
        add_metadata_route(app, invoke_with_sealed_dag_node_settings=True)

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload["capabilities"] == ALL_CAPABILITIES

    def test_last_call_wins(self):
        # A host wrapper registers /metadata at construction; the plugin's later call with its own
        # identifier must replace it, not be shadowed by route order.
        app = FastAPI()
        add_metadata_route(app, identifier="wrapper.default")
        add_metadata_route(app, identifier="plugin.test", invoke_with_sealed_dag_node_settings=True)

        with TestClient(app) as client:
            payload = client.get("/metadata").json()

        assert payload["identifier"] == "plugin.test"
        assert payload["capabilities"] == ALL_CAPABILITIES

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
        assert payload["capabilities"] == ALL_CAPABILITIES


class _Recorder:
    """What the /invoke handler observed: the bound envelope, and whether it ran at all."""

    def __init__(self):
        self.called = False
        self.seen_settings = "unset"
        self.seen_context = "unset"


def _envelope_app(recorder: _Recorder, max_body_bytes: Optional[int] = None) -> FastAPI:
    """A hand-rolled host app: the /invoke route reads the raw request, like a plugin that owns
    its own route, so any body shape reaches the handler unless the dependency rejects it."""
    app = FastAPI()
    if max_body_bytes is None:
        install_invocation_envelope(app)
    else:
        install_invocation_envelope(app, max_body_bytes=max_body_bytes)

    @app.post("/invoke")
    async def invoke(request: Request) -> dict:
        recorder.called = True
        recorder.seen_settings = current_invocation_settings()
        recorder.seen_context = current_invocation_context()
        return {}

    @app.get("/schema")
    async def schema() -> dict:
        recorder.called = True
        return {}

    return app


class _SpecCompliantRootShim:
    """A rooted deployment as the ASGI spec describes it: ``path`` carries the mount prefix and
    ``root_path`` names it. ``TestClient(root_path=...)`` sets only ``root_path`` without
    prefixing ``path``, so it cannot produce this shape."""

    def __init__(self, app, root: str):
        self.app = app
        self.root = root

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "path": self.root + scope["path"], "root_path": self.root}
        await self.app(scope, receive, send)


def _post_invoke(payload, recorder: Optional[_Recorder] = None, **app_kwargs):
    recorder = recorder if recorder is not None else _Recorder()
    app = _envelope_app(recorder, **app_kwargs)
    with TestClient(app, raise_server_exceptions=False) as client:
        if isinstance(payload, bytes):
            response = client.post("/invoke", content=payload)
        else:
            response = client.post("/invoke", json=payload)
    return recorder, response


class TestInvocationEnvelopeBinding:
    def test_binds_reserved_fields(self):
        recorder, response = _post_invoke(
            {
                "element_dicts": "/in.json",
                "invocation_settings": {"model": "m"},
                "invocation_context": {"schema_version": "1", "job_id": "job-1"},
            }
        )

        assert response.status_code == 200
        assert recorder.seen_settings == {"model": "m"}
        assert recorder.seen_context.job_id == "job-1"

    def test_absent_fields_bind_none(self):
        recorder, response = _post_invoke({"element_dicts": "/in.json"})

        assert response.status_code == 200
        assert recorder.seen_settings is None
        assert recorder.seen_context is None

    def test_non_dict_reserved_field_is_rejected(self):
        recorder, response = _post_invoke({"invocation_settings": "not-a-dict"})

        assert not recorder.called
        assert response.status_code == 422
        body = response.json()
        assert "invocation_settings" in body["detail"]
        assert body["reason"] == "malformed_envelope"

    def test_context_with_an_unreadable_schema_version_fails_as_platform_error(self):
        # Absence means "older caller, use the boot settings"; a context this plugin cannot read
        # must not be downgraded to that. And it is deployment skew, not a caller fault — a 422
        # would let an upstream blame classifier pin version skew on the customer.
        recorder, response = _post_invoke({"invocation_context": {"schema_version": "99"}})

        assert not recorder.called
        assert response.status_code == 500
        body = response.json()
        assert "invocation_context" in body["detail"]
        assert "UnsupportedContextVersionError" in body["detail"]
        assert body["reason"] == "unsupported_context_version"

    def test_malformed_context_is_rejected(self):
        recorder, response = _post_invoke({"invocation_context": "not-an-object"})

        assert not recorder.called
        assert response.status_code == 422

    def test_non_invoke_routes_are_untouched(self):
        recorder = _Recorder()
        app = _envelope_app(recorder)

        with TestClient(app) as client:
            response = client.get("/schema")

        assert response.status_code == 200
        assert recorder.called

    def test_envelope_does_not_leak_between_requests(self):
        recorder = _Recorder()
        app = _envelope_app(recorder)

        with TestClient(app) as client:
            client.post("/invoke", json={"invocation_settings": {"model": "m"}})
            client.post("/invoke", json={"element_dicts": "/in.json"})

        assert recorder.seen_settings is None
        assert recorder.seen_context is None

    def test_install_after_an_invoke_route_fails_loudly(self):
        app = FastAPI()

        @app.post("/invoke")
        async def invoke() -> dict:
            return {}

        with pytest.raises(RuntimeError, match="POST /invoke"):
            install_invocation_envelope(app)

    def test_install_after_metadata_but_before_invoke_is_supported(self):
        recorder = _Recorder()
        app = FastAPI()
        add_metadata_route(app, invoke_with_sealed_dag_node_settings=True)
        install_invocation_envelope(app)

        @app.post("/invoke")
        async def invoke() -> dict:
            recorder.seen_settings = current_invocation_settings()
            return {}

        with TestClient(app) as client:
            response = client.post("/invoke", json={"invocation_settings": {"model": "m"}})

        assert response.status_code == 200
        assert recorder.seen_settings == {"model": "m"}

    def test_mixed_method_route_does_not_bind_or_parse_get(self):
        recorder = _Recorder()
        app = FastAPI()
        install_invocation_envelope(app)

        @app.api_route("/invoke", methods=["GET", "POST"])
        async def invoke() -> dict:
            recorder.seen_settings = current_invocation_settings()
            return {}

        with TestClient(app) as client:
            response = client.get("/invoke")

        assert response.status_code == 200
        assert recorder.seen_settings is None

    def test_root_path_does_not_prevent_invoke_binding(self):
        recorder = _Recorder()
        app = _envelope_app(recorder)

        with TestClient(app, root_path="/plugins/chunker") as client:
            response = client.post("/invoke", json={"invocation_settings": {"model": "rooted"}})

        assert response.status_code == 200
        assert recorder.seen_settings == {"model": "rooted"}

    def test_spec_compliant_root_path_scope_still_binds(self):
        recorder = _Recorder()
        app = _envelope_app(recorder)

        with TestClient(_SpecCompliantRootShim(app, "/plugins/chunker")) as client:
            response = client.post("/invoke", json={"invocation_settings": {"model": "rooted"}})

        assert response.status_code == 200
        assert recorder.seen_settings == {"model": "rooted"}

    def test_oversized_body_is_rejected(self):
        recorder, response = _post_invoke(
            {"invocation_settings": {"pad": "x" * 64}}, max_body_bytes=16
        )

        assert not recorder.called
        assert response.status_code == 413

    def test_spec_compliant_root_path_scope_still_caps_body(self):
        recorder = _Recorder()
        app = _envelope_app(recorder, max_body_bytes=16)

        with TestClient(
            _SpecCompliantRootShim(app, "/plugins/chunker"), raise_server_exceptions=False
        ) as client:
            response = client.post("/invoke", json={"invocation_settings": {"pad": "x" * 64}})

        assert not recorder.called
        assert response.status_code == 413

    def test_repeat_install_with_the_same_cap_is_a_noop(self):
        recorder = _Recorder()
        app = _envelope_app(recorder, max_body_bytes=1024)
        install_invocation_envelope(app, max_body_bytes=1024)

        with TestClient(app) as client:
            response = client.post("/invoke", json={"element_dicts": "/in.json"})

        assert response.status_code == 200
        assert recorder.called

    def test_repeat_install_with_a_different_cap_fails_loudly(self):
        app = FastAPI()
        install_invocation_envelope(app, max_body_bytes=16)

        with pytest.raises(ValueError, match="max_body_bytes"):
            install_invocation_envelope(app, max_body_bytes=32)


class TestInvokeBodyLimitMiddleware:
    """ASGI-level behavior of the streaming byte counter: no buffering, disconnect pass-through."""

    @staticmethod
    def _run(middleware, scope, chunks) -> tuple[list, list]:
        received = []
        sent = []

        async def receive():
            return chunks.pop(0)

        async def send(message):
            sent.append(message)

        async def downstream(scope, receive, send):
            while True:
                message = await receive()
                received.append(message)
                if message["type"] != "http.request" or not message.get("more_body"):
                    break
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"{}"})

        middleware = middleware(downstream)
        asyncio.run(middleware(scope, receive, send))
        return received, sent

    def test_chunked_body_over_the_cap_answers_413_and_cuts_downstream(self):
        chunks = [
            {"type": "http.request", "body": b"x" * 10, "more_body": True},
            {"type": "http.request", "body": b"x" * 10, "more_body": False},
        ]
        received, sent = self._run(
            lambda app: InvokeBodyLimitMiddleware(app, max_body_bytes=16),
            {"type": "http", "method": "POST", "path": "/invoke"},
            chunks,
        )

        assert received[-1] == {"type": "http.disconnect"}
        assert sent[0]["status"] == 413

    def test_rooted_scope_over_the_cap_answers_413(self):
        # Per the ASGI spec, `path` includes the deployment root_path; the cap must key on the
        # mount-relative path, the same one the router matches.
        chunks = [{"type": "http.request", "body": b"x" * 20, "more_body": False}]
        received, sent = self._run(
            lambda app: InvokeBodyLimitMiddleware(app, max_body_bytes=16),
            {
                "type": "http",
                "method": "POST",
                "path": "/plugins/chunker/invoke",
                "root_path": "/plugins/chunker",
            },
            chunks,
        )

        assert received[-1] == {"type": "http.disconnect"}
        assert sent[0]["status"] == 413

    def test_client_disconnect_passes_through_uncounted(self):
        chunks = [{"type": "http.disconnect"}]
        received, sent = self._run(
            lambda app: InvokeBodyLimitMiddleware(app, max_body_bytes=16),
            {"type": "http", "method": "POST", "path": "/invoke"},
            chunks,
        )

        assert received == [{"type": "http.disconnect"}]

    def test_non_invoke_requests_are_not_capped(self):
        chunks = [{"type": "http.request", "body": b"x" * 100, "more_body": False}]
        received, sent = self._run(
            lambda app: InvokeBodyLimitMiddleware(app, max_body_bytes=16),
            {"type": "http", "method": "GET", "path": "/schema"},
            chunks,
        )

        assert sent[0]["status"] == 200


class TestEnvelopeResolution:
    """Sealed payloads through the binding dependency. The HTTP class comes from the library's
    blame taxonomy, so only a caller-fixable fault is a 422."""

    def test_bare_sealed_envelope_is_rejected(self, key_dir, private_key):
        sealed = sealed_payload(private_key, {"api_key": SENTINEL_SECRET})

        recorder, response = _post_invoke({"invocation_settings": sealed})

        assert response.status_code == 500
        assert "MalformedDagNodeSettingsError" in response.json()["detail"]
        assert not recorder.called

    def test_composite_dag_node_settings_member_is_opened(self, key_dir, private_key):
        settings = {"api_key": SENTINEL_SECRET, "max_characters": 700}
        composite = {DAG_NODE_SETTINGS_KEY: sealed_payload(private_key, settings)}

        recorder, response = _post_invoke({"invocation_settings": composite})

        assert response.status_code == 200
        assert recorder.seen_settings == settings

    def test_plain_dict_settings_pass_through(self):
        recorder, response = _post_invoke({"invocation_settings": {"model": "m"}})

        assert response.status_code == 200
        assert recorder.seen_settings == {"model": "m"}

    def test_non_envelope_member_fails_as_platform_error(self, key_dir):
        composite = {DAG_NODE_SETTINGS_KEY: {"model": "m"}}

        recorder, response = _post_invoke({"invocation_settings": composite})

        assert response.status_code == 500
        assert "MalformedDagNodeSettingsError" in response.json()["detail"]
        assert not recorder.called

    def test_undecryptable_envelope_fails_without_leaking_the_secret(
        self, key_dir, private_key, caplog
    ):
        sealed = tampered(sealed_payload(private_key, {"api_key": SENTINEL_SECRET}))
        composite = {DAG_NODE_SETTINGS_KEY: sealed}

        recorder, response = _post_invoke({"invocation_settings": composite})

        assert response.status_code == 500
        detail = response.json()["detail"]
        assert "DecryptionError" in detail
        assert SENTINEL_SECRET not in caplog.text
        assert SENTINEL_SECRET not in detail
        assert not recorder.called

    def test_unmounted_identity_fails_as_platform_error(self, tmp_path, monkeypatch, private_key):
        monkeypatch.setenv("WORKLOAD_IDENTITY_DIR", str(tmp_path / "missing"))
        sealed = sealed_payload(private_key, {"api_key": SENTINEL_SECRET})
        composite = {DAG_NODE_SETTINGS_KEY: sealed}

        recorder, response = _post_invoke({"invocation_settings": composite})

        assert response.status_code == 500
        assert "IdentityNotMountedError" in response.json()["detail"]
        assert not recorder.called


class TestRequireSealedDagNodeSettings:
    """A native pod's operator sets FF_REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS in the same
    decision that drops the init-secrets sidecar: without it, an invoke that arrived with no
    envelope would fall back to a settings file that was never written."""

    @pytest.fixture(autouse=True)
    def _require_sealed(self, monkeypatch):
        monkeypatch.setenv(REQUIRE_INVOKE_WITH_SEALED_DAG_NODE_SETTINGS_ENV_VAR, "true")

    def test_missing_settings_fail_as_platform_error(self):
        recorder, response = _post_invoke({"element_dicts": "/tmp/x.json"})

        assert response.status_code == 500
        assert "SealedDagNodeSettingsRequiredError" in response.json()["detail"]
        assert not recorder.called

    def test_plaintext_settings_fail_as_platform_error(self):
        recorder, response = _post_invoke({"invocation_settings": {"model": "m"}})

        assert response.status_code == 500
        assert not recorder.called

    def test_sealed_settings_still_bind(self, key_dir, private_key):
        settings = {"api_key": SENTINEL_SECRET}
        composite = {DAG_NODE_SETTINGS_KEY: sealed_payload(private_key, settings)}

        recorder, response = _post_invoke({"invocation_settings": composite})

        assert response.status_code == 200
        assert recorder.seen_settings == settings

    def test_bodyless_invoke_fails_as_platform_error(self):
        # A bodyless invoke cannot carry the envelope; on a pod with no boot settings file it must
        # not dispatch a handler with no settings source at all.
        recorder, response = _post_invoke(b"")

        assert response.status_code == 500
        assert not recorder.called

    def test_non_object_json_body_fails_as_platform_error(self):
        recorder, response = _post_invoke(json.dumps([{"element": 1}]).encode())

        assert response.status_code == 500
        assert not recorder.called


def test_non_object_bodies_pass_through_when_sealed_settings_not_required():
    recorder, response = _post_invoke(b"")

    assert response.status_code == 200
    assert recorder.seen_settings is None
