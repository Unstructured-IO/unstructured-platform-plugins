import inspect
from dataclasses import dataclass
from typing import Any, Optional, TypedDict, Union

import pytest
from pydantic import BaseModel

import unstructured_platform_plugins.schema.json_schema as js
from unstructured_platform_plugins.cli.utils import get_input_schema
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
    def fn(
        a: int,
        b: float | int = 4,
        c: str | None = "my_string",
        d: bool = False,
        e: dict[str, Any] = None,
        f: list[float] = None,
    ) -> None:
        pass

    class ExpectedInputModel(BaseModel):
        a: int
        b: Union[float, int] = 4
        c: Optional[str] = "my_string"
        d: bool = False
        e: dict = None
        f: list = None

    input_model = js.schema_to_base_model(get_input_schema(fn))
    input_model_schema = input_model.model_json_schema()
    expected_model_schema = ExpectedInputModel.model_json_schema()
    expected_model_schema["title"] = "reconstructed_model"
    assert input_model_schema == expected_model_schema
