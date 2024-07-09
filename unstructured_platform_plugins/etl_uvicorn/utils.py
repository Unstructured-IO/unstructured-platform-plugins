import inspect
from dataclasses import is_dataclass
from enum import EnumMeta
from types import GenericAlias, NoneType
from typing import Any, Callable, Optional

from pydantic import BaseModel

from unstructured_platform_plugins.schema.json_schema import (
    parameters_to_json_schema,
    response_to_json_schema,
)
from unstructured_platform_plugins.schema.utils import get_typed_parameters
from unstructured_platform_plugins.type_hints import get_type_hints


def get_func(instance: Any, method_name: Optional[str] = None) -> Callable:
    method_name = method_name or "__call__"
    if inspect.isfunction(instance):
        return instance
    elif inspect.isclass(instance):
        i = instance()
        return getattr(i, method_name)
    elif isinstance(instance, object) and hasattr(instance, method_name):
        func = getattr(instance, method_name)
        if inspect.ismethod(func):
            return func
    raise ValueError(f"type of instance not recognized: {type(instance)}")


def get_plugin_id(instance: Any, method_name: Optional[str] = None) -> str:
    method_name = method_name or "__call__"
    ref_id = None
    if inspect.isfunction(instance):
        ref_id = instance()
    elif inspect.isclass(instance):
        i = instance()
        method_name = method_name or "__call__"
        fn = getattr(i, method_name)
        ref_id = fn()
    elif isinstance(instance, object) and hasattr(instance, method_name):
        func = getattr(instance, method_name)
        if inspect.ismethod(func):
            ref_id = func()
    else:
        ref_id = instance
    if not ref_id:
        raise ValueError(f"id could not be parsed from instance {instance}")
    ref_id = str(ref_id)
    if not ref_id.isidentifier():
        raise ValueError(f"'{ref_id}' is not a valid identifier")
    return ref_id


def get_input_schema(func: Callable) -> dict:
    parameters = get_typed_parameters(func)
    return parameters_to_json_schema(parameters)


def get_output_sig(func: Callable) -> Optional[Any]:
    inspect.signature(func)
    type_hints = get_type_hints(func)
    return_typing = type_hints["return"]
    outputs = return_typing if return_typing is not NoneType else None
    return outputs


def get_output_schema(func: Callable) -> dict:
    return response_to_json_schema(get_output_sig(func))


def get_schema_dict(func) -> dict:
    return {
        "inputs": get_input_schema(func),
        "outputs": get_output_schema(func),
    }


def map_inputs(func: Callable, raw_inputs: dict[str, Any]) -> dict[str, Any]:
    # deserializes the raw dictionary coming in from the api into the underlying data
    # types expected by the function when being invoked
    raw_inputs = raw_inputs.copy()
    type_info = get_type_hints(func)
    type_info.pop("return")
    for field_name, type_data in type_info.items():
        if (
            is_dataclass(type_data)
            and field_name in raw_inputs
            and isinstance(raw_inputs[field_name], dict)
        ):
            raw_inputs[field_name] = type_data(**raw_inputs[field_name])
        elif isinstance(type_data, EnumMeta):
            raw_inputs[field_name] = raw_inputs[field_name]
        elif (
            inspect.isclass(type_data)
            and not isinstance(type_data, GenericAlias)
            and issubclass(type_data, BaseModel)
        ):
            raw_inputs[field_name] = type_data.model_validate(raw_inputs[field_name])
    return raw_inputs
