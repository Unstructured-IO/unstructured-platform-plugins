from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from unstructured_ingest.v2.interfaces import BatchFileData, BatchItem, FileData, SourceIdentifiers

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
    assert not invoke_response.output


def test_improper_function():
    from test.assets.improper_function import sample_improper_function as test_fn

    with pytest.raises(EtlApiException):
        TestClient(wrap_in_fastapi(func=test_fn, plugin_id="mock_plugin"))
