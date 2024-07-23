import inspect
from dataclasses import dataclass, is_dataclass
from enum import Enum

import pytest
from pydantic import BaseModel
from unstructured.ingest.v2.interfaces import FileData
from uvicorn.importer import import_from_string

from unstructured_platform_plugins.etl_uvicorn import utils


def test_get_func_simple():
    instance = import_from_string("test.assets.typed_dict_response:sample_function")
    func = utils.get_func(instance)
    assert callable(func)
    assert func.__name__ == "sample_function"
    sig = inspect.signature(func)
    response = sig.return_annotation
    # Check for typed dict response
    assert dict in inspect.getmro(response)
    assert dict is not inspect.getmro(response)[0]


def test_get_async_func():
    instance = import_from_string("test.assets.async_typed_dict_response:async_sample_function")
    func = utils.get_func(instance)
    assert callable(func)
    assert func.__name__ == "async_sample_function"
    sig = inspect.signature(func)
    response = sig.return_annotation
    # Check for typed dict response
    assert dict in inspect.getmro(response)
    assert dict is not inspect.getmro(response)[0]


def test_get_class_func():
    instance = import_from_string("test.assets.pydantic_response_class_method:SampleClass")
    func = utils.get_func(instance, method_name="sample_method")
    assert callable(func)
    assert func.__name__ == "sample_method"
    sig = inspect.signature(func)
    response = sig.return_annotation
    # Check for pydantic model response
    assert inspect.isclass(response)
    assert issubclass(response, BaseModel)


def test_get_func_dataclass_response():
    instance = import_from_string("test.assets.dataclass_response:sample_function_with_path")
    func = utils.get_func(instance)
    assert callable(func)
    assert func.__name__ == "sample_function_with_path"
    sig = inspect.signature(func)
    response = sig.return_annotation
    # Check for dataclass response
    assert is_dataclass(response)


def test_get_plugin_id_value():
    instance = import_from_string("test.assets.simple_hash_value:hash_value")
    hash_value = utils.get_plugin_id(instance)
    assert hash_value == "plugin_id_123"


def test_get_plugin_id_lambda():
    instance = import_from_string("test.assets.simple_hash_lambda:hash_lambda_fn")
    hash_value = utils.get_plugin_id(instance)
    assert hash_value == "plugin_id_hash_123"


def test_get_plugin_id_function():
    instance = import_from_string("test.assets.hash_function:get_hash")
    hash_value = utils.get_plugin_id(instance)
    assert hash_value == "plugin_id_fn_123"


def test_get_plugin_id_class():
    instance = import_from_string("test.assets.simple_hash_class:GetHash")
    hash_value = utils.get_plugin_id(instance, method_name="my_hash")
    assert hash_value == "plugin_id_class_123"


def test_get_plugin_id_class_instance():
    instance = import_from_string("test.assets.simple_hash_class:get_hash_class_instance")
    hash_value = utils.get_plugin_id(instance, method_name="my_hash")
    assert hash_value == "plugin_id_class_123"


@dataclass
class A:
    b: int
    c: float


class B(BaseModel):
    d: bool
    e: dict


class MyEnum(Enum):
    VALUE = "value"


def test_map_inputs():
    def fn(a: A, b: B, c: MyEnum, d: list, e: FileData) -> None:
        pass

    file_data = FileData(
        identifier="custom_file_data",
        connector_type="mock_connector",
        additional_metadata={"additional": "metadata"},
    )
    inputs = {
        "a": {"b": 4, "c": 5.6},
        "b": {"d": True, "e": {"key": "value"}},
        "c": MyEnum.VALUE.value,
        "d": [1, 2, 3],
        "e": file_data.to_dict(),
    }

    mapped_inputs = utils.map_inputs(func=fn, raw_inputs=inputs)
    expected = {
        "a": A(b=4, c=5.6),
        "b": B(d=True, e={"key": "value"}),
        "c": MyEnum.VALUE.value,
        "d": [1, 2, 3],
        "e": file_data,
    }
    assert mapped_inputs == expected


def test_map_inputs_error():
    def fn(a: FileData) -> None:
        pass

    inputs = {"a": {"not": "the", "right": "values"}}

    with pytest.raises(KeyError):
        utils.map_inputs(func=fn, raw_inputs=inputs)
