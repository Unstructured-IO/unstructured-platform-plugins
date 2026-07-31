"""The wrapper-installed invocation-settings surface: /metadata and reserved-field binding."""

from typing import Optional

from fastapi.testclient import TestClient
from pydantic import BaseModel
from utic_invocation_settings import current_invocation_settings

from unstructured_platform_plugins.etl_uvicorn.api_generator import wrap_in_fastapi


class _Echo(BaseModel):
    content: str
    settings: Optional[dict]


def _echo_settings(content: str) -> _Echo:
    return _Echo(content=content, settings=current_invocation_settings())


def test_metadata_route_is_registered_with_default_capabilities():
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
            invoke_with_sealed_dag_node_settings=True,
        )
    )

    payload = client.get("/metadata").json()

    assert "invoke_with_sealed_dag_node_settings" in payload["capabilities"]


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


def test_sync_function_sees_bound_settings_across_the_executor():
    # Sync functions run in an executor thread; the context must be copied there or the
    # request-scoped binding would read as absent.
    def sync_echo(content: str) -> _Echo:
        return _Echo(content=content, settings=current_invocation_settings())

    client = TestClient(wrap_in_fastapi(func=sync_echo, plugin_id="mock_plugin"))

    resp = client.post(
        "/invoke", json={"content": "hello", "invocation_settings": {"model": "m"}}
    )

    assert resp.json()["output"]["settings"] == {"model": "m"}


async def _async_echo(content: str) -> _Echo:
    return _Echo(content=content, settings=current_invocation_settings())


def test_async_function_sees_bound_settings():
    client = TestClient(wrap_in_fastapi(func=_async_echo, plugin_id="mock_plugin"))

    resp = client.post(
        "/invoke", json={"content": "hello", "invocation_settings": {"model": "m"}}
    )

    assert resp.json()["output"]["settings"] == {"model": "m"}


def test_absent_reserved_fields_bind_none():
    client = TestClient(wrap_in_fastapi(func=_echo_settings, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"content": "hello"})

    assert resp.status_code == 200
    assert resp.json()["output"] == {"content": "hello", "settings": None}
