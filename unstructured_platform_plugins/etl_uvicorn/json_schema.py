import types
import typing
from inspect import Parameter
from typing import Optional, Type, Union

# https://json-schema.org/understanding-json-schema/reference/type
types_map: dict[Type, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
    dict: "object",
    list: "array",
}


def is_optional(t: types.GenericAlias) -> bool:
    origin = t.__origin__
    if origin is typing.Union:
        types = t.__args__
        if type(None) in types:
            return True
    return False


def type_to_json_schema(t: Optional[Union[Type, types.GenericAlias]]) -> dict:
    if t is None:
        return {"type": "null"}
    resp = {}
    origin = t if isinstance(t, Type) else t.__origin__
    if origin in types_map:
        resp = {"type": types_map[origin]}
        if origin is list and t.__args__:
            list_type = t.__args__[0]
            resp["items"] = type_to_json_schema(list_type)

    elif origin is typing.Union:
        types = t.__args__
        if type(None) in types:
            types = [t for t in types if t is not type(None)]
        if len(types) == 1:
            return type_to_json_schema(types[0])
        else:
            resp["anyOf"] = [type_to_json_schema(t) for t in types]
    else:
        raise ValueError(f"Unsupported origin: {origin}")
    return resp


def parameter_to_json_schema(parameter: Parameter) -> tuple[dict, bool]:
    annotation = parameter.annotation
    resp = type_to_json_schema(annotation)
    required = True
    if getattr(annotation, "__origin__", None) is typing.Union:
        required = not is_optional(annotation)
    if parameter.default != Parameter.empty:
        resp["default"] = parameter.default
    return resp, required


def parameters_to_json_schema(parameters: list[Parameter]) -> dict:
    resp = {}
    required_fields = []
    # Any variable positional or keyword args are not allowed (i.e. *args, **kwargs)
    var_positional = [str(p) for p in parameters if p.kind == Parameter.VAR_POSITIONAL]
    if var_positional:
        raise TypeError(
            "function has variable positional arguments, which are not allowed: {}".format(
                ", ".join(var_positional)
            )
        )
    var_keywords = [str(p) for p in parameters if p.kind == Parameter.VAR_KEYWORD]
    if var_keywords:
        raise TypeError(
            "function has variable keyword arguments, which are not allowed: {}".format(
                ", ".join(var_keywords)
            )
        )

    for p in parameters:
        schema, required = parameter_to_json_schema(p)
        if required:
            required_fields.append(p.name)
        resp[p.name] = schema
    if required_fields:
        resp["required"] = required_fields
    return resp
