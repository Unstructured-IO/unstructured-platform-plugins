"""The wrapper-installed invocation-settings surface: /metadata and reserved-field binding."""

import json
from typing import Optional

from fastapi.testclient import TestClient
from pydantic import BaseModel

from unstructured_platform_plugins.etl_uvicorn.api_generator import wrap_in_fastapi
from unstructured_platform_plugins.invocation_settings import current_invocation_settings


class _Echo(BaseModel):
    content: str
    settings: Optional[dict]


def _echo_settings(content: str) -> _Echo:
    return _Echo(content=content, settings=current_invocation_settings())


def test_metadata_route_is_registered_with_transport_capabilities():
    client = TestClient(wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin"))

    resp = client.get("/metadata")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["identifier"] == "mock_plugin"
    assert payload["capabilities"] == ["invocation_settings", "invocation_context"]


def test_sealed_capability_is_opt_in():
    client = TestClient(
        wrap_in_fastapi(
            func=_echo_settings,
            plugin_id="mock_plugin",
            invoke_with_sealed_dag_node_settings_v2=True,
        )
    )

    payload = client.get("/metadata").json()

    assert "invoke_with_sealed_dag_node_settings_v2" in payload["capabilities"]


def test_reserved_settings_field_binds_without_appearing_in_schema():
    app = wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin")
    client = TestClient(app)

    resp = client.post(
        "/invoke",
        json={"content": "hello", "invocation_settings": {"model": "m"}},
    )

    assert resp.status_code == 200
    output = resp.json()["output"]
    assert output == {"content": "hello", "settings": {"model": "m"}}
    # The wrapper does not add the reserved field to the generated handler input model.
    openapi = app.openapi()
    request_schema = openapi["paths"]["/invoke"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    schema_name = request_schema["$ref"].rsplit("/", 1)[-1]
    properties = openapi["components"]["schemas"][schema_name]["properties"]
    assert "invocation_settings" not in properties


def test_generated_invoke_route_classifies_malformed_json_as_caller_error():
    client = TestClient(wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin"))

    resp = client.post(
        "/invoke",
        content=b"{",
        headers={"content-type": "application/json"},
    )

    assert resp.status_code == 422
    assert resp.json() == {
        "detail": "Invalid JSON body",
        "reason": "malformed_envelope",
    }


def test_generated_invoke_route_preserves_other_request_validation_errors():
    client = TestClient(wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={})

    assert resp.status_code == 422
    payload = resp.json()
    assert "reason" not in payload
    assert isinstance(payload["detail"], list)
    assert any(error["loc"] == ["body", "content"] for error in payload["detail"])


def test_sync_function_sees_bound_settings_across_the_executor():
    # Sync functions run in an executor thread; the context must be copied there or the
    # request-scoped binding would read as absent.
    def sync_echo(content: str) -> _Echo:
        return _Echo(content=content, settings=current_invocation_settings())

    client = TestClient(wrap_in_fastapi(func=sync_echo, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"content": "hello", "invocation_settings": {"model": "m"}})

    assert resp.json()["output"]["settings"] == {"model": "m"}


async def _async_echo(content: str) -> _Echo:
    return _Echo(content=content, settings=current_invocation_settings())


def test_async_function_sees_bound_settings():
    client = TestClient(wrap_in_fastapi(func=_async_echo, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"content": "hello", "invocation_settings": {"model": "m"}})

    assert resp.json()["output"]["settings"] == {"model": "m"}


async def _stream_echo(content: str) -> _Echo:
    yield _Echo(content=content, settings=current_invocation_settings())


def test_async_generator_sees_bound_settings_during_stream_iteration():
    client = TestClient(wrap_in_fastapi(func=_stream_echo, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"content": "hello", "invocation_settings": {"model": "m"}})

    line = json.loads(resp.text.strip())
    assert line["output"]["settings"] == {"model": "m"}


def test_absent_reserved_fields_bind_none():
    client = TestClient(wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"content": "hello"})

    assert resp.status_code == 200
    assert resp.json()["output"] == {"content": "hello", "settings": None}
