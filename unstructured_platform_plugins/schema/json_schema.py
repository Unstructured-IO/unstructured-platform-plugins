import inspect
from dataclasses import MISSING, fields, is_dataclass
from inspect import Parameter
from pathlib import Path
from types import GenericAlias, NoneType, UnionType
from typing import Any, Optional, Type, Union

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo, PydanticUndefined

# https://json-schema.org/understanding-json-schema/reference/type
types_map: dict[Type, str] = {
    str: "string",
    bool: "boolean",
    int: "integer",
    float: "number",
    dict: "object",
    list: "array",
}

typed_map_reverse: dict[str, Type] = {v: k for k, v in types_map.items()}


def is_generic_alias(val: Any) -> bool:
    return hasattr(val, "__origin__") and hasattr(val, "__args__")


def is_typed_dict(val: Any) -> bool:
    return inspect.isclass(val) and dict in inspect.getmro(val) and dict != inspect.getmro(val)[0]


def type_to_json_schema(t: Type, args: Optional[tuple[Any, ...]] = None) -> dict:
    resp = {"type": types_map[t]}
    if t is list and args:
        list_type = args[0]
        resp["items"] = to_json_schema(list_type)
    if t is dict and args:
        key = args[0]
        value = args[1]
        resp["items"] = {
            "key": to_json_schema(key),
            "value": to_json_schema(value),
        }
    return resp


def path_to_json_schema(path: Path) -> dict:
    return {"type": "string", "is_path": True}


def generic_alias_to_json_schema(t: GenericAlias) -> dict:
    origin = t.__origin__
    if origin is Union:
        types = t.__args__
        if len(types) == 1:
            return to_json_schema(types[0])
        else:
            return {"anyOf": [to_json_schema(t) for t in types]}
    return type_to_json_schema(t=origin, args=t.__args__)


def union_type_to_json_schema(t: UnionType) -> dict:
    types = t.__args__
    if len(types) == 1:
        return to_json_schema(types[0])
    else:
        return {"anyOf": [to_json_schema(t) for t in types]}


def dataclass_to_json_schema(class_or_instance) -> dict:
    resp = {"type": "object"}
    fs = fields(class_or_instance)
    if not fs:
        return resp
    properties = {}
    required = []
    for f in fs:
        t = f.type
        f_resp = to_json_schema(t)
        if f.default is not MISSING:
            f_resp["default"] = f.default
        else:
            required.append(f.name)
        properties[f.name] = f_resp
    resp["properties"] = properties
    resp["required"] = required
    return resp


def pydantic_base_model_to_json_schema(model: Type[BaseModel]) -> dict:
    resp = {"type": "object"}
    fs: dict[str, FieldInfo] = model.model_fields
    if not fs:
        return resp
    properties = {}
    required = []
    for name, f in fs.items():
        t = f.annotation
        f_resp = to_json_schema(t)
        if f.default != PydanticUndefined:
            f_resp["default"] = f.default
        else:
            required.append(name)
        properties[name] = f_resp
    resp["properties"] = properties
    resp["required"] = required
    return resp


def typed_dict_to_json_schem(typed_dict_class) -> dict:
    resp = {"type": "object"}
    fs = typed_dict_class.__annotations__
    if not fs:
        return resp
    properties = {}
    required = []
    for name, t in fs.items():
        f_resp = to_json_schema(t)
        properties[name] = f_resp
        required.append(name)
    resp["properties"] = properties
    resp["required"] = required
    return resp


def parameter_to_json_schema(parameter: Parameter) -> dict:
    annotation = parameter.annotation
    resp = to_json_schema(annotation)
    if parameter.default != Parameter.empty:
        resp["default"] = parameter.default
    return resp


def to_json_schema(val: Any) -> dict:
    if val in [None, NoneType]:
        return {"type": "null"}
    if val is Any:
        return {}
    if isinstance(val, Parameter):
        return parameter_to_json_schema(parameter=val)
    if isinstance(val, UnionType):
        return union_type_to_json_schema(t=val)
    if is_generic_alias(val=val):
        return generic_alias_to_json_schema(t=val)
    if val is Type:
        return type_to_json_schema(t=val)
    if is_dataclass(val):
        return dataclass_to_json_schema(val)
    if val is Path:
        return path_to_json_schema(val)
    if val in types_map:
        return type_to_json_schema(t=val)
    if inspect.isclass(val) and issubclass(val, BaseModel):
        return pydantic_base_model_to_json_schema(model=val)
    if is_typed_dict(val):
        return typed_dict_to_json_schem(val)
    raise ValueError(f"Unsupported type: ({type(val).__name__}) {val}")


def run_input_checks(parameters: list[Parameter]):
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


def parameters_to_json_schema(parameters: list[Parameter]) -> dict:
    run_input_checks(parameters=parameters)
    resp = {"type": "object"}
    properties = {}
    required_fields = []
    for p in parameters:
        schema = to_json_schema(val=p)
        properties[p.name] = schema
        if p.default == Parameter.empty:
            required_fields.append(p.name)
    if required_fields:
        resp["required"] = required_fields
    if properties:
        resp["properties"] = properties
    return resp


def run_output_checks(return_annotation: Any):
    if is_generic_alias(val=return_annotation):  # noqa: SIM102
        if return_annotation.__origin__ in [Union, list]:
            for arg in return_annotation.__args__:
                run_output_checks(arg)
            return
    if is_typed_dict(return_annotation):
        return
    if is_dataclass(return_annotation):
        return
    if inspect.isclass(return_annotation) and issubclass(return_annotation, BaseModel):
        return
    if return_annotation is None:
        return
    if return_annotation is NoneType:
        return
    raise ValueError(f"Unsupported response type: {return_annotation}")


def response_to_json_schema(return_annotation: Any) -> dict:
    run_output_checks(return_annotation=return_annotation)
    return to_json_schema(val=return_annotation)


def schema_to_base_model_type(json_type_name, name: str, type_info: dict) -> Type[BaseModel]:
    t = typed_map_reverse[json_type_name]
    if t is dict and "properties" in type_info:
        t = schema_to_base_model(
            schema=type_info["properties"],
            name=name,
        )
    if t is dict and "items" in type_info and isinstance(type_info["items"], dict):
        items = type_info["items"]
        if "key" in items and "value" in items:
            key_info = items["key"]
            key_type_name = key_info["type"]
            key_subtype = schema_to_base_model_type(
                json_type_name=key_type_name, name=f"{name}_key", type_info=key_info
            )
            value_info = items["value"]
            if not value_info:
                value_subtype = Any
            else:
                value_type_name = items["value"]["type"]
                value_subtype = schema_to_base_model_type(
                    json_type_name=value_type_name, name=f"{name}_value", type_info=value_info
                )
            t = dict[key_subtype, value_subtype]
    if t is list and "items" in type_info and isinstance(type_info["items"], dict):
        items = type_info["items"]
        item_type_name = items["type"]
        subtype = schema_to_base_model_type(
            json_type_name=item_type_name, name=f"{name}_type", type_info=items
        )
        t = list[subtype]
    return t


def schema_to_base_model(schema: dict, name: str = "reconstructed_model") -> Type[BaseModel]:
    inputs = {}
    properties = schema.get("properties", {})

    for k, v in properties.items():
        optional = False
        if "anyOf" in v:
            any_of_entries = v["anyOf"]
            if "null" in [entry["type"] for entry in any_of_entries]:
                optional = True
                any_of_entries = [entry for entry in any_of_entries if entry["type"] != "null"]
            if len(any_of_entries) > 1:
                type_info = [
                    schema_to_base_model_type(
                        type_info["type"], name=f"{k}_{index}", type_info=type_info
                    )
                    for index, type_info in enumerate(any_of_entries)
                ]
                t = Union[*type_info]
            else:
                entry_info = any_of_entries[0]
                json_type_name = entry_info["type"]
                t = schema_to_base_model_type(
                    json_type_name=json_type_name, name=k, type_info=entry_info
                )
        else:
            json_type_name = v["type"]
            t = schema_to_base_model_type(json_type_name=json_type_name, name=k, type_info=v)
        if optional:
            t = Optional[t]
        resp = [t]
        if "default" in v:
            resp.append(v["default"])
        else:
            resp.append(Ellipsis)
        inputs[k] = tuple(resp)
    return create_model(name, **inputs)
