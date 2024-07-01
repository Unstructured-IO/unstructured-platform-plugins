import inspect
from dataclasses import is_dataclass

from pydantic import BaseModel
from uvicorn.importer import import_from_string

from unstructured_platform_plugins.cli import utils


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
