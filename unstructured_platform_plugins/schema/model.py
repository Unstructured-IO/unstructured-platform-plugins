from typing import Optional, Union

from pydantic import BaseModel, ValidationError


class StringEntrySchema(BaseModel):
    type: str = "string"
    default: Optional[str] = None


class BooleanEntrySchema(BaseModel):
    type: str = "boolean"
    default: Optional[bool] = None


class IntegerEntrySchema(BaseModel):
    type: str = "integer"
    default: Optional[int] = None


class NumberEntrySchema(BaseModel):
    type: str = "number"
    default: Optional[float] = None


class ArrayEntrySchema(BaseModel):
    type: str = "array"
    items: Optional[list["AnyEntry"]] = None


class ObjectEntrySchema(BaseModel):
    type: str = "object"
    properties: Optional[dict[str, "AnyEntry"]] = None
    required: Optional[list[str]] = None


class NullEntrySchema(BaseModel):
    type: str = "null"


AnyEntry = Union[
    StringEntrySchema, BooleanEntrySchema, IntegerEntrySchema, ArrayEntrySchema, ObjectEntrySchema
]


def is_validate_dict(schema: dict) -> bool:
    try:
        ObjectEntrySchema.model_validate(schema, strict=True)
        return True
    except ValidationError:
        return False
