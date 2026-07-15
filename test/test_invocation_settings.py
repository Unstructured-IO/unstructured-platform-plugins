from typing import Any, Optional

from fastapi.testclient import TestClient

from unstructured_platform_plugins.etl_uvicorn.api_generator import wrap_in_fastapi
from unstructured_platform_plugins.etl_uvicorn.invocation_context import (
    get_invocation_settings,
)
from pydantic import BaseModel


class Out(BaseModel):
    content: str
    settings_seen: Optional[dict[str, Any]] = None


def fn_declares(content: str, invocation_settings: Optional[dict[str, Any]] = None) -> Out:
    return Out(content=content, settings_seen=invocation_settings)


def fn_uses_context(content: str) -> Out:
    return Out(content=content, settings_seen=get_invocation_settings())


def test_declared_param_receives_settings():
    client = TestClient(wrap_in_fastapi(func=fn_declares, plugin_id="t1"))
    resp = client.post(
        "/invoke",
        json={"content": "x", "invocation_settings": {"strategy": "fast"}},
    )
    assert resp.status_code == 200
    assert resp.json()["output"]["settings_seen"] == {"strategy": "fast"}


def test_context_accessor_receives_settings():
    client = TestClient(wrap_in_fastapi(func=fn_uses_context, plugin_id="t2"))
    resp = client.post(
        "/invoke",
        json={"content": "x", "invocation_settings": {"k": 1}},
    )
    assert resp.status_code == 200
    assert resp.json()["output"]["settings_seen"] == {"k": 1}


def test_omitted_settings_is_none_and_context_resets():
    client = TestClient(wrap_in_fastapi(func=fn_uses_context, plugin_id="t3"))
    with_settings = client.post("/invoke", json={"content": "x", "invocation_settings": {"k": 1}})
    without = client.post("/invoke", json={"content": "x"})
    assert with_settings.json()["output"]["settings_seen"] == {"k": 1}
    assert without.json()["output"]["settings_seen"] is None


def test_capabilities_endpoint():
    client = TestClient(wrap_in_fastapi(func=fn_uses_context, plugin_id="t4"))
    resp = client.get("/capabilities")
    assert resp.status_code == 200
    assert resp.json()["invocation_settings"] is True


def test_schema_unpolluted_by_envelope_field():
    client = TestClient(wrap_in_fastapi(func=fn_uses_context, plugin_id="t5"))
    schema = client.get("/schema").json()
    assert "invocation_settings" not in schema["inputs"].get("properties", {})
