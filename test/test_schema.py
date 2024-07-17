import inspect
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Union

import pytest
from pydantic import BaseModel
from typing_extensions import TypedDict
from unstructured.ingest.v2.interfaces import FileData

import unstructured_platform_plugins.schema.json_schema as js
from unstructured_platform_plugins.etl_uvicorn.utils import get_input_schema
from unstructured_platform_plugins.schema.model import is_valid_input_dict, is_valid_response_dict
from unstructured_platform_plugins.schema.utils import get_typed_parameters
from unstructured_platform_plugins.type_hints import get_type_hints


def test_string_enum_fn():
    class StringEnum(Enum):
        FIRST = "first"
        SECOND = "second"
        THIRD = "third"

    def fn(input: StringEnum) -> None:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_schema = {
        "type": "object",
        "required": ["input"],
        "properties": {"input": {"type": "string", "enum": ["first", "second", "third"]}},
    }

    assert input_schema == expected_schema
    assert is_valid_response_dict(input_schema)


def test_int_enum_fn():
    class IntEnum(Enum):
        FIRST = 1
        SECOND = 2
        THIRD = 3

    def fn(input: IntEnum) -> None:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_schema = {
        "type": "object",
        "required": ["input"],
        "properties": {"input": {"type": "integer", "enum": [1, 2, 3]}},
    }
    assert input_schema == expected_schema
    assert is_valid_response_dict(input_schema)


def test_mixed_enum_fn():
    class MixedEnum(Enum):
        FIRST = 1
        SECOND = "second"
        THIRD = 3

    def fn(input: MixedEnum) -> None:
        pass

    sig = inspect.signature(fn)
    with pytest.raises(ValueError):
        js.parameters_to_json_schema(parameters=list(sig.parameters.values()))


def test_blank_fn():
    def fn() -> None:
        pass

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_schema = {"type": "null"}
    assert input_schema == expected_schema
    assert is_valid_input_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {"type": "null"}
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


def test_simple_fn():
    class Response(TypedDict):
        x: int
        y: str

    def fn(
        a: int,
        b: Union[float, int],
        c: Optional[str] = "my_string",
        d: bool = False,
        e: dict[str, dict[str, bool]] = None,
        f: list[float] = None,
    ) -> Response:
        return Response(x=1, y="y")

    sig = inspect.signature(fn)
    input_schema = js.parameters_to_json_schema(parameters=list(sig.parameters.values()))
    expected_input_schema = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {
            "a": {"type": "integer"},
            "b": {"anyOf": [{"type": "number"}, {"type": "integer"}]},
            "c": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": "my_string"},
            "d": {"type": "boolean", "default": False},
            "e": {
                "type": "object",
                "items": {
                    "key": {"type": "string"},
                    "value": {
                        "type": "object",
                        "items": {"key": {"type": "string"}, "value": {"type": "boolean"}},
                    },
                },
                "default": None,
            },
            "f": {"type": "array", "items": {"type": "number"}, "default": None},
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "string"}},
        "required": ["x", "y"],
    }
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


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
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                },
                "required": ["x"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "a": {"type": "object", "items": {"key": {"type": "string"}, "value": {}}},
                    "b": {"type": "array", "items": {"type": "boolean"}},
                    "c": {"anyOf": [{"type": "number"}, {"type": "null"}], "default": 5.46},
                },
                "required": ["a", "b"],
            },
            {"type": "null"},
        ]
    }
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


def test_pydantic_base_model():
    class Input(BaseModel):
        x: "int"
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
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                },
                "required": ["x"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "a": {"type": "object", "items": {"key": {"type": "string"}, "value": {}}},
                    "b": {"type": "array", "items": {"type": "boolean"}},
                    "c": {"anyOf": [{"type": "number"}, {"type": "null"}], "default": 5.46},
                },
                "required": ["a", "b"],
            },
            {"type": "null"},
        ]
    }
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


def test_typed_dict():
    class Input(TypedDict):
        x: "int"
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
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                },
                "required": ["x", "y"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    output_schema = js.response_to_json_schema(return_annotation=sig.return_annotation)
    expected_output_schema = {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "a": {"type": "object", "items": {"key": {"type": "string"}, "value": {}}},
                    "b": {"type": "array", "items": {"type": "boolean"}},
                    "c": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                },
                "required": ["a", "b", "c"],
            },
            {"type": "null"},
        ]
    }
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


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
                                    "anyOf": [
                                        {
                                            "type": "object",
                                            "properties": {
                                                "x": {"type": "integer"},
                                                "y": {
                                                    "anyOf": [{"type": "string"}, {"type": "null"}]
                                                },
                                            },
                                            "required": ["x", "y"],
                                        },
                                        {"type": "null"},
                                    ],
                                    "default": None,
                                },
                            },
                            "required": ["a"],
                        },
                    },
                    "h": {"type": "boolean", "default": False},
                },
                "required": ["g"],
            }
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)


def test_schema_to_base_model():
    class g_enum(Enum):
        FIRST = "first"
        SECOND = "second"
        THIRD = "third"

    def fn(
        a: int,
        b: float | int = 4,
        c: str | None = "my_string",
        d: bool = False,
        e: Optional[dict[str, Any]] = None,
        f: list[float] = None,
        g: Optional[g_enum] = None,
        h: FileData | None = None,
        i: Path | None = None,
    ) -> None:
        pass

    class ExpectedInputModel(BaseModel):
        a: int
        b: Union[float, int] = 4
        c: str | None = "my_string"
        d: bool = False
        e: Optional[dict[str, Any]] = None
        f: list[float] = None
        g: Optional[g_enum] = None
        h: FileData | None = None
        i: Path | None = None

    input_schema = get_input_schema(fn)
    input_model = js.schema_to_base_model(schema=input_schema)
    input_model_schema = input_model.model_json_schema()
    expected_model_schema = ExpectedInputModel.model_json_schema()
    expected_model_schema["title"] = "reconstructed_model"
    assert input_model_schema == expected_model_schema


# These need to be defined outside the code of test_forward_reference_typing
# for references to resolve:
@dataclass
class MockInputClass:
    a: str


@dataclass
class MockOutputClass:
    b: bool


def test_forward_reference_typing():

    def fn(a: "MockInputClass") -> "MockOutputClass":
        pass

    parameters = get_typed_parameters(fn)
    input_schema = js.parameters_to_json_schema(parameters=parameters)
    expected_input_schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
        },
    }
    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    return_annotation = get_type_hints(fn)["return"]
    output_schema = js.response_to_json_schema(return_annotation=return_annotation)
    expected_output_schema = {
        "type": "object",
        "properties": {"b": {"type": "boolean"}},
        "required": ["b"],
    }
    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)


def test_file_data():
    def fn(a: FileData) -> list[FileData]:
        pass

    parameters = get_typed_parameters(fn)
    input_schema = js.parameters_to_json_schema(parameters=parameters)
    expected_input_schema = {
        "type": "object",
        "required": ["a"],
        "properties": {
            "a": {
                "type": "object",
                "is_file_data": True,
                "properties": {
                    "identifier": {"type": "string"},
                    "connector_type": {"type": "string"},
                    "source_identifiers": {
                        "anyOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "filename": {"type": "string"},
                                    "fullpath": {"type": "string"},
                                    "rel_path": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}],
                                        "default": None,
                                    },
                                },
                                "required": ["filename", "fullpath"],
                            },
                            {"type": "null"},
                        ],
                        "default": None,
                    },
                    "doc_type": {"type": "string", "enum": ["batch", "file"], "default": "file"},
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                            },
                            "version": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                            },
                            "record_locator": {
                                "anyOf": [
                                    {
                                        "type": "object",
                                        "items": {"key": {"type": "string"}, "value": {}},
                                    },
                                    {"type": "null"},
                                ],
                                "default": None,
                            },
                            "date_created": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                            },
                            "date_modified": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                            },
                            "date_processed": {
                                "anyOf": [{"type": "string"}, {"type": "null"}],
                                "default": None,
                            },
                            "permissions_data": {
                                "anyOf": [
                                    {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "items": {"key": {"type": "string"}, "value": {}},
                                        },
                                    },
                                    {"type": "null"},
                                ],
                                "default": None,
                            },
                        },
                        "required": [],
                    },
                    "additional_metadata": {
                        "type": "object",
                        "items": {"key": {"type": "string"}, "value": {}},
                    },
                    "reprocess": {"type": "boolean", "default": False},
                },
                "required": ["identifier", "connector_type", "metadata", "additional_metadata"],
            }
        },
    }

    assert input_schema == expected_input_schema
    assert is_valid_input_dict(input_schema)

    return_annotation = get_type_hints(fn)["return"]
    output_schema = js.response_to_json_schema(return_annotation=return_annotation)
    expected_output_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "is_file_data": True,
            "properties": {
                "identifier": {"type": "string"},
                "connector_type": {"type": "string"},
                "source_identifiers": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "fullpath": {"type": "string"},
                                "rel_path": {
                                    "anyOf": [{"type": "string"}, {"type": "null"}],
                                    "default": None,
                                },
                            },
                            "required": ["filename", "fullpath"],
                        },
                        {"type": "null"},
                    ],
                    "default": None,
                },
                "doc_type": {"type": "string", "enum": ["batch", "file"], "default": "file"},
                "metadata": {
                    "type": "object",
                    "properties": {
                        "url": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
                        "version": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "default": None,
                        },
                        "record_locator": {
                            "anyOf": [
                                {
                                    "type": "object",
                                    "items": {"key": {"type": "string"}, "value": {}},
                                },
                                {"type": "null"},
                            ],
                            "default": None,
                        },
                        "date_created": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "default": None,
                        },
                        "date_modified": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "default": None,
                        },
                        "date_processed": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "default": None,
                        },
                        "permissions_data": {
                            "anyOf": [
                                {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "items": {"key": {"type": "string"}, "value": {}},
                                    },
                                },
                                {"type": "null"},
                            ],
                            "default": None,
                        },
                    },
                    "required": [],
                },
                "additional_metadata": {
                    "type": "object",
                    "items": {"key": {"type": "string"}, "value": {}},
                },
                "reprocess": {"type": "boolean", "default": False},
            },
            "required": ["identifier", "connector_type", "metadata", "additional_metadata"],
        },
    }

    assert output_schema == expected_output_schema
    assert is_valid_response_dict(output_schema)
