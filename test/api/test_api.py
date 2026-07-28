from pathlib import Path
from typing import Any, Optional, Union

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from unstructured_ingest.data_types.file_data import (
    BatchFileData,
    BatchItem,
    FileData,
    SourceIdentifiers,
)

from unstructured_platform_plugins.etl_uvicorn.api_generator import (
    EtlApiException,
    UsageData,
    wrap_in_fastapi,
)
from unstructured_platform_plugins.schema.filedata_meta import FileDataMeta


class InvokeResponse(BaseModel):
    usage: list[UsageData]
    status_code: int
    filedata_meta: FileDataMeta
    status_code_text: Optional[str] = None
    output: Optional[Any] = None
    file_data: Optional[Union[FileData, BatchFileData]] = None

    def generic_validation(self):
        assert self.status_code == 200
        assert not self.status_code_text


mock_file_data = [
    FileData(
        identifier="mock file data",
        connector_type="CON",
        source_identifiers=SourceIdentifiers(filename="n", fullpath="n"),
    ),
    BatchFileData(
        identifier="mock file data", connector_type="CON", batch_items=[BatchItem(identifier="bid")]
    ),
]


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_async_sample_function(file_data):
    from test.assets.async_typed_dict_response import async_sample_function as test_fn

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump(), "content": {"a": 1, "b": 2}}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)
    invoke_response.generic_validation()
    output = invoke_response.output
    assert isinstance(output, dict)
    assert output == {"response": {"a_out": 1, "b_out": 2}}


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_dataclass_response(file_data):
    from test.assets.dataclass_response import sample_function_with_path as test_fn

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))
    current_path = Path(__file__)

    post_body = {"file_data": file_data.model_dump(), "c": 1, "b": "2", "a": str(current_path)}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)
    invoke_response.generic_validation()
    output = invoke_response.output
    assert isinstance(output, dict)
    assert output == {
        "t": "PosixPath",
        "exists": True,
        "resolved": str(current_path.resolve()),
        "b": "2",
        "c": 1,
        "p": not isinstance(file_data, BatchFileData),
    }


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_empty_input_and_output(file_data):
    from test.assets.empty_input_and_response import SampleClass as TestClass

    test_class = TestClass()
    client = TestClient(wrap_in_fastapi(func=test_class.do_nothing, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"file_data": file_data.model_dump()})
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)
    invoke_response.generic_validation()
    output = invoke_response.output
    assert not output


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_filedata_meta(file_data):
    from test.assets.filedata_meta import Input
    from test.assets.filedata_meta import process_input as test_fn

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump(), "i": Input(m=15).model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)
    invoke_response.generic_validation()
    filedata_meta = invoke_response.filedata_meta
    assert len(filedata_meta.new_records) == 15
    assert filedata_meta.terminate_current
    file_data = invoke_response.file_data
    assert file_data
    assert file_data.metadata.record_locator.get("key") == "value"
    assert not invoke_response.output


def test_improper_function():
    from test.assets.improper_function import sample_improper_function as test_fn

    with pytest.raises(EtlApiException):
        TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_exception_with_none_status_code(file_data):
    """Test that exceptions with status_code=None are handled correctly."""
    from test.assets.exception_status_code import (
        function_raises_exception_with_none_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 when status_code is None
    assert invoke_response.status_code == 500
    assert "ExceptionWithNoneStatusCode" in invoke_response.status_code_text
    assert "Test exception with None status_code" in invoke_response.status_code_text


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_exception_with_valid_status_code(file_data):
    """Test that exceptions with valid status_code are handled correctly."""
    from test.assets.exception_status_code import (
        function_raises_exception_with_valid_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should use the exception's status_code
    assert invoke_response.status_code == 422
    assert "ExceptionWithValidStatusCode" in invoke_response.status_code_text
    assert "Test exception with valid status_code" in invoke_response.status_code_text


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_exception_without_status_code(file_data):
    """Test that exceptions without status_code attribute are handled correctly."""
    from test.assets.exception_status_code import (
        function_raises_exception_without_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 when no status_code attribute
    assert invoke_response.status_code == 500
    assert "ExceptionWithoutStatusCode" in invoke_response.status_code_text
    assert "Test exception without status_code" in invoke_response.status_code_text


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_http_exception_handling(file_data):
    """Test that HTTPException is handled correctly (should use HTTPException path)."""
    from test.assets.exception_status_code import function_raises_http_exception as test_fn

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # HTTPException should be handled by the HTTPException handler
    assert invoke_response.status_code == 404
    assert invoke_response.status_code_text == "Not found"


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_generic_exception_handling(file_data):
    """Test that generic exceptions are handled correctly."""
    from test.assets.exception_status_code import function_raises_generic_exception as test_fn

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 for generic exceptions
    assert invoke_response.status_code == 500
    assert "ValueError" in invoke_response.status_code_text
    assert "Generic error" in invoke_response.status_code_text


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_async_exception_with_none_status_code(file_data):
    """Test that async functions with status_code=None exceptions are handled correctly."""
    from test.assets.exception_status_code import (
        async_function_raises_exception_with_none_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 when status_code is None
    assert invoke_response.status_code == 500
    assert "ExceptionWithNoneStatusCode" in invoke_response.status_code_text
    assert "Async test exception with None status_code" in invoke_response.status_code_text


def test_streaming_exception_with_none_status_code():
    """Test that async generator functions with
    status_code=None exceptions are handled correctly."""
    from test.assets.exception_status_code import (
        async_gen_function_raises_exception_with_none_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": mock_file_data[0].model_dump()}
    resp = client.post("/invoke", json=post_body)

    # For streaming responses, we get NDJSON
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"

    # Parse the streaming response - should be a single error response
    lines = resp.content.decode().strip().split("\n")
    assert len(lines) == 1  # Only error response since no items were yielded

    # Parse the error response
    import json

    error_response = json.loads(lines[0])
    invoke_response = InvokeResponse.model_validate(error_response)

    # Should default to 500 when status_code is None
    assert invoke_response.status_code == 500
    assert "ExceptionWithNoneStatusCode" in invoke_response.status_code_text


def test_streaming_exception_with_valid_status_code():
    """Test that async generator functions with
    valid status_code exceptions are handled correctly."""
    from test.assets.exception_status_code import (
        async_gen_function_raises_exception_with_valid_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": mock_file_data[0].model_dump()}
    resp = client.post("/invoke", json=post_body)

    # For streaming responses, we get NDJSON
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"

    # Parse the streaming response - should be a single error response
    lines = resp.content.decode().strip().split("\n")
    assert len(lines) == 1  # Only error response since no items were yielded

    # Parse the error response
    import json

    error_response = json.loads(lines[0])
    invoke_response = InvokeResponse.model_validate(error_response)

    # Should use the exception's status_code
    assert invoke_response.status_code == 422
    assert "ExceptionWithValidStatusCode" in invoke_response.status_code_text


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_unstructured_ingest_error_with_status_code(file_data):
    """Test that UnstructuredIngestError with status_code is handled correctly."""
    from test.assets.exception_status_code import (
        function_raises_unstructured_ingest_error_with_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should use the UnstructuredIngestError's status_code
    assert invoke_response.status_code == 400
    assert invoke_response.status_code_text == "Test UnstructuredIngestError with status_code"


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_unstructured_ingest_error_without_status_code(file_data):
    """Test that UnstructuredIngestError without status_code defaults to 500."""
    from test.assets.exception_status_code import (
        function_raises_unstructured_ingest_error_without_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 when UnstructuredIngestError has no status_code
    assert invoke_response.status_code == 500
    assert invoke_response.status_code_text == "Test UnstructuredIngestError without status_code"


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_unstructured_ingest_error_with_none_status_code(file_data):
    """Test that UnstructuredIngestError with None status_code defaults to 500."""
    from test.assets.exception_status_code import (
        function_raises_unstructured_ingest_error_with_none_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should default to 500 when UnstructuredIngestError status_code is None
    assert invoke_response.status_code == 500
    assert invoke_response.status_code_text == "Test UnstructuredIngestError with None status_code"


@pytest.mark.parametrize(
    "file_data", mock_file_data, ids=[type(fd).__name__ for fd in mock_file_data]
)
def test_async_unstructured_ingest_error(file_data):
    """Test that async functions with UnstructuredIngestError are handled correctly."""
    from test.assets.exception_status_code import (
        async_function_raises_unstructured_ingest_error as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": file_data.model_dump()}
    resp = client.post("/invoke", json=post_body)
    resp_content = resp.json()
    invoke_response = InvokeResponse.model_validate(resp_content)

    # Should use the UnstructuredIngestError's status_code
    assert invoke_response.status_code == 503
    assert invoke_response.status_code_text == "Async test UnstructuredIngestError"


def test_streaming_unstructured_ingest_error():
    """Test that async generator functions with UnstructuredIngestError are handled correctly."""
    from test.assets.exception_status_code import (
        async_gen_function_raises_unstructured_ingest_error as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": mock_file_data[0].model_dump()}
    resp = client.post("/invoke", json=post_body)

    # For streaming responses, we get NDJSON
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"

    # Parse the streaming response - should be a single error response
    lines = resp.content.decode().strip().split("\n")
    assert len(lines) == 1  # Only error response since no items were yielded

    # Parse the error response
    import json

    error_response = json.loads(lines[0])
    invoke_response = InvokeResponse.model_validate(error_response)

    # Should use the UnstructuredIngestError's status_code
    assert invoke_response.status_code == 502
    assert "Async gen test UnstructuredIngestError" in invoke_response.status_code_text


def test_streaming_unstructured_ingest_error_with_none_status_code():
    """Test that async generator functions with UnstructuredIngestError
    with None status_code are handled correctly."""
    from test.assets.exception_status_code import (
        async_gen_function_raises_unstructured_ingest_error_with_none_status_code as test_fn,
    )

    client = TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))

    post_body = {"file_data": mock_file_data[0].model_dump()}
    resp = client.post("/invoke", json=post_body)

    # For streaming responses, we get NDJSON
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/x-ndjson"

    # Parse the streaming response - should be a single error response
    lines = resp.content.decode().strip().split("\n")
    assert len(lines) == 1  # Only error response since no items were yielded

    # Parse the error response
    import json

    error_response = json.loads(lines[0])
    invoke_response = InvokeResponse.model_validate(error_response)

    # Should default to 500 when UnstructuredIngestError status_code is None
    assert invoke_response.status_code == 500
    assert (
        "Async gen test UnstructuredIngestError with None status_code"
        in invoke_response.status_code_text
    )


# --- optional-body contract -------------------------------------------------------------------
#
# A pydantic body parameter with no default is mandatory even when every field inside the model is
# optional. A plugin whose parameters are ALL optional therefore used to demand a body that no
# caller has a reason to populate: before it grew those parameters the same plugin accepted no body
# at all, so adding one silently flipped its HTTP contract and every bodyless caller got a 422.


class _Echo(BaseModel):
    settings: Optional[dict] = None
    context: Optional[dict] = None
    received: Optional[str] = None


def _all_optional(
    invocation_settings: Optional[dict] = None, invocation_context: Optional[dict] = None
) -> _Echo:
    return _Echo(settings=invocation_settings, context=invocation_context)


def _no_params() -> _Echo:
    return _Echo(received="ok")


def _has_required(element_dicts: str, invocation_context: Optional[dict] = None) -> _Echo:
    return _Echo(received=element_dicts)


@pytest.mark.parametrize("body", [None, {}])
def test_all_optional_params_accept_absent_or_empty_body(body):
    client = TestClient(wrap_in_fastapi(func=_all_optional, plugin_id="mock_plugin"))

    kwargs = {} if body is None else {"json": body}
    resp = client.post("/invoke", **kwargs)

    assert resp.status_code == 200
    invoke_response = InvokeResponse.model_validate(resp.json())
    invoke_response.generic_validation()
    # Each field resolves to its own default, which is what the signature already promised.
    assert invoke_response.output == {"settings": None, "context": None, "received": None}


def test_all_optional_params_still_receive_a_populated_body():
    # The tolerance must not swallow a body that IS supplied, or the wire-settings plane silently
    # stops working while every request keeps returning 200.
    client = TestClient(wrap_in_fastapi(func=_all_optional, plugin_id="mock_plugin"))

    resp = client.post("/invoke", json={"invocation_settings": {"k": "v"}})

    assert resp.status_code == 200
    assert InvokeResponse.model_validate(resp.json()).output == {
        "settings": {"k": "v"},
        "context": None,
        "received": None,
    }


def test_required_param_still_rejects_an_absent_body():
    # The tolerance must not leak into plugins that genuinely need input: a downloader invoked
    # without `file_data` has to fail loudly rather than receive None.
    client = TestClient(wrap_in_fastapi(func=_has_required, plugin_id="mock_plugin"))

    assert client.post("/invoke").status_code == 422
    assert client.post("/invoke", json={}).status_code == 422
    assert client.post("/invoke", json={"element_dicts": "x"}).status_code == 200


def test_no_param_plugin_still_accepts_a_bodyless_post():
    client = TestClient(wrap_in_fastapi(func=_no_params, plugin_id="mock_plugin"))

    resp = client.post("/invoke")

    assert resp.status_code == 200
    assert InvokeResponse.model_validate(resp.json()).output["received"] == "ok"
