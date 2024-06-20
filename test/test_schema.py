import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypedDict, Union

import pytest
from pydantic import BaseModel, create_model

from unstructured_platform_plugins.etl_uvicorn.utils import get_input_schema
import unstructured_platform_plugins.schema.json_schema as js
from unstructured_platform_plugins.schema.model import is_validate_dict


def test_blank_fn():
    def fn() -> None:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_schema = {"type": "object"}
    assert input_schema == expected_schema
    assert is_validate_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {"type": "null"}
    assert output_schema == expected_output_schema
    assert is_validate_dict(output_schema)


def test_simple_fn():
    class Response(TypedDict):
        x: int
        y: str

    def fn(
        a: int,
        b: Union[float, int],
        c: Optional[str] = "my_string",
        d: bool = False,
        e: dict[str, Any] = None,
        f: list[float] = None,
    ) -> Response:
        return Response(x=1, y="y")

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["a", "b", "d", "e", "f"],
        "properties": {
            "a": {"type": "integer"},
            "b": {"anyOf": [{"type": "number"}, {"type": "integer"}]},
            "c": {"type": "string", "default": "my_string"},
            "d": {"type": "boolean", "default": False},
            "e": {"type": "object", "default": None},
            "f": {"type": "array", "items": {"type": "number"}, "default": None},
        },
    }
    assert input_schema == expected_input_schema
    assert is_validate_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "string"}},
        "required": ["x", "y"],
    }
    assert output_schema == expected_output_schema
    assert is_validate_dict(output_schema)


def test_incorrect_dict_response():
    def fn() -> dict[str, Any]:
        pass

    sig = inspect.signature(fn)
    with pytest.raises(ValueError):
        js.response_to_json_schema(return_annotation=sig.return_annotation)


def test_incorrect_int_response():
    def fn() -> int:
        pass

    sig = inspect.signature(fn)
    with pytest.raises(ValueError):
        js.response_to_json_schema(return_annotation=sig.return_annotation)


def test_incorrect_inputs():
    def fn(*args, **kwargs) -> None:
        pass

    sig = inspect.signature(fn)
    with pytest.raises(TypeError):
        js.parameters_to_json_schema(parameters=list(sig.parameters.values()))


def test_incorrect_union_response():
    class CorrectResponse(TypedDict):
        x: int

    def fn() -> Union[CorrectResponse, float]:
        pass

    sig = inspect.signature(fn)
    with pytest.raises(ValueError):
        js.response_to_json_schema(return_annotation=sig.return_annotation)


def test_dataclass_schema():
    @dataclass
    class Input:
        x: int
        y: Optional[str] = None

    @dataclass
    class Output:
        a: dict[str, Any]
        b: list[bool]
        c: Optional[float] = 5.46

    def fn(g: Input) -> Optional[Output]:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["g"],
        "properties": {
            "g": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "string", "default": None}},
                "required": ["x"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_validate_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {
            "a": {"type": "object"},
            "b": {"type": "array", "items": {"type": "boolean"}},
            "c": {"type": "number", "default": 5.46},
        },
        "required": ["a", "b"],
    }
    assert output_schema == expected_output_schema
    assert is_validate_dict(output_schema)


def test_pydantic_base_model():
    class Input(BaseModel):
        x: int
        y: Optional[str] = None

    class Output(BaseModel):
        a: dict[str, Any]
        b: list[bool]
        c: Optional[float] = 5.46

    def fn(g: Input) -> Optional[Output]:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["g"],
        "properties": {
            "g": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "string", "default": None}},
                "required": ["x"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_validate_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {
            "a": {"type": "object"},
            "b": {"type": "array", "items": {"type": "boolean"}},
            "c": {"type": "number", "default": 5.46},
        },
        "required": ["a", "b"],
    }
    assert output_schema == expected_output_schema
    assert is_validate_dict(output_schema)


def test_typed_dict():
    class Input(TypedDict):
        x: int
        y: Optional[str]

    class Output(TypedDict):
        a: dict[str, Any]
        b: list[bool]
        c: Optional[float]

    def fn(g: Input) -> Optional[Output]:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["g"],
        "properties": {
            "g": {
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "string"}},
                "required": ["x"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_validate_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {
            "a": {"type": "object"},
            "b": {"type": "array", "items": {"type": "boolean"}},
            "c": {"type": "number"},
        },
        "required": ["a", "b"],
    }
    assert output_schema == expected_output_schema
    assert is_validate_dict(output_schema)


def test_nested_complex_types():
    class InputA(TypedDict):
        x: int
        y: Optional[str]

    class InputB(BaseModel):
        a: float
        b: Optional[InputA] = None

    @dataclass
    class InputC:
        g: list[InputB]
        h: bool = False

    def fn(q: InputC) -> None:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["q"],
        "properties": {
            "q": {
                "type": "object",
                "properties": {
                    "g": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number"},
                                "b": {
                                    "type": "object",
                                    "properties": {
                                        "x": {"type": "integer"},
                                        "y": {"type": "string"},
                                    },
                                    "required": ["x"],
                                    "default": None,
                                },
                            },
                            "required": ["a"],
                        },
                    },
                    "h": {"type": "boolean", "default": False},
                },
                "required": ["g", "h"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_validate_dict(input_schema)


def test_schema_to_base_model():
    class ExpectedModel(BaseModel):
        first: list[dict]

    def examined_fn(input: ExpectedModel) -> dict:
        pass

    example_data = [{"x": 1, "y": 2}, {"a": 1, "b": 2}]

    tested_model = js.schema_to_base_model(get_input_schema(examined_fn))

    instance_correct = ExpectedModel(first=example_data)
    assert instance_correct.first

    instance_tested = tested_model(first=example_data)
    print(instance_tested.model_dump())
    assert instance_tested.first


def test_schema_introspection():
    def func_with_python_args(first: dict[int, str], second: list[dict], third: int = 3):
        pass

    class MyInputModel(BaseModel):
        first: dict[int, str]
        second: list[dict]
        third: int = 3

    def func_with_input_model(input: MyInputModel):
        pass

    expected_acceptable_input = {
        "first": {1: "a", 2: "b"},
        "second": [{"x": 1}, {"y": 2}],
        "third": 123,
    }

    def infer_model_from_function(func: Callable[..., Any]):
        params = {}
        signature = inspect.signature(func)
        print(f"Signature is {signature}")
        for parameter in signature.parameters.values():
            name = parameter.name
            annotation = parameter.annotation
            if parameter.default is inspect._empty:
                default = Ellipsis
            else:
                default = parameter.default
            params[name] = (annotation, default)

        print(f"Create model with params: '{params}'")
        infered_model = create_model("infered_model", **params)
        return infered_model

    print("Test model creation")
    for tested_func in (func_with_python_args, func_with_input_model):
        print(f"Examining {tested_func}")
        infered_model = infer_model_from_function(tested_func)
        for name, field in infered_model.model_fields.items():
            print(f"Field '{name}' -> '{field}'")
        print()

    print("Test model instance creation")
    func_with_python_args_model = infer_model_from_function(func_with_python_args)
    func_with_input_model_model = infer_model_from_function(func_with_input_model)

    print("Instance of model for func_with_python_args")
    model = func_with_python_args_model(**expected_acceptable_input)
    print(model)
    func_with_python_args(**model.model_dump())
    print()

    print("Instance of model for func_with_input_model")
    model = func_with_input_model_model(**{"input": expected_acceptable_input})
    print(model)
    func_with_input_model(**model.model_dump())
