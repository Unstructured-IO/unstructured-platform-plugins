import inspect
from types import UnionType
from typing import Any, Literal, Optional, Union, get_args

from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated

AnnotatedType = type(Annotated[str, str])


class StringEntrySchema(BaseModel):
    type: Literal["string"]
    default: Optional[str] = None


class BooleanEntrySchema(BaseModel):
    type: Literal["boolean"]
    default: Optional[bool] = None


class IntegerEntrySchema(BaseModel):
    type: Literal["integer"]
    default: Optional[int] = None


class NumberEntrySchema(BaseModel):
    type: Literal["number"]
    default: Optional[float] = None


class ArrayEntrySchema(BaseModel):
    type: Literal["array"]
    items: Optional["AnyEntry"] = None


class ObjectEntrySchema(BaseModel):
    type: Literal["object"]
    properties: Optional[dict[str, "AnyEntry"]] = None
    required: Optional[list[str]] = None


class NullEntrySchema(BaseModel):
    type: Literal["null"]


class AnyOfEntrySchema(BaseModel):
    anyOf: list["AnyEntry"]


TypedAnyEntry = Union[
    StringEntrySchema,
    BooleanEntrySchema,
    IntegerEntrySchema,
    ArrayEntrySchema,
    ObjectEntrySchema,
    NumberEntrySchema,
    NullEntrySchema,
]
TypedAnyEntryTyping = Annotated[TypedAnyEntry, Field(discriminator="type")]
AnyEntry = Union[TypedAnyEntryTyping, AnyOfEntrySchema]


def is_valid_input_dict(schema: dict) -> bool:
    # Support both null and object cases
    try:
        NullEntrySchema.model_validate(schema, strict=True)
        return True
    except ValidationError:
        pass
    try:
        ObjectEntrySchema.model_validate(schema, strict=True)
        return True
    except ValidationError:
        pass
    return False


def decompose_union(tp: Any) -> list[BaseModel]:
    args = get_args(tp)
    decomposed_types = []
    for arg in args:
        if inspect.isclass(arg) and issubclass(arg, BaseModel):
            decomposed_types.append(arg)
        elif isinstance(arg, UnionType):
            decomposed_types.extend(decompose_union(tp=arg))
        elif isinstance(arg, AnnotatedType):
            annotated_args = get_args(arg)
            type_arg = annotated_args[0]
            decomposed_types.extend(decompose_union(tp=type_arg))
    return decomposed_types


def is_valid_response_dict(schema: dict) -> bool:
    decomposed_models = decompose_union(tp=AnyEntry)
    for tp in decomposed_models:
        try:
            tp.model_validate(schema, strict=True)
            return True
        except ValidationError:
            pass
    return False
