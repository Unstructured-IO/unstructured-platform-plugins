from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError
from typing_extensions import Annotated


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


def is_validate_dict(schema: dict) -> bool:
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
