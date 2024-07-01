import inspect
from dataclasses import is_dataclass
from types import NoneType
from typing import Any, Callable, Optional, get_type_hints

from pydantic import BaseModel

from unstructured_platform_plugins.schema.json_schema import (
    parameters_to_json_schema,
    response_to_json_schema,
)
from unstructured_platform_plugins.schema.utils import get_types_parameters


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
    parameters = get_types_parameters(func)
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
    input_params = {p.name: p for p in inspect.signature(func).parameters.values()}
    for k, v in input_params.items():
        annotation = v.annotation
        if is_dataclass(annotation) and k in raw_inputs and isinstance(raw_inputs[k], dict):
            raw_inputs[k] = annotation(**raw_inputs[k])
        elif inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            raw_inputs[k] = annotation.parse_obj(raw_inputs[k])
    return raw_inputs
