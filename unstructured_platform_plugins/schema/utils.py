import inspect
from inspect import Parameter, _empty
from typing import Callable

from unstructured_platform_plugins.type_hints import get_type_hints


class TypedParameter(Parameter):
    def __init__(self, *args, param_type=_empty, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_type = param_type

    @classmethod
    def from_parameter(cls, param: Parameter) -> "TypedParameter":
        return cls(
            name=param.name, default=param.default, annotation=param.annotation, kind=param.kind
        )


def get_typed_parameters(fn: Callable) -> list[TypedParameter]:
    type_hints = get_type_hints(fn)
    parameters = list(inspect.signature(fn).parameters.values())
    typed_params = []
    for p in parameters:
        typed_param = TypedParameter.from_parameter(param=p)
        if isinstance(typed_param.annotation, str):
            typed_param.param_type = type_hints[typed_param.name]
        else:
            typed_param.param_type = typed_param.annotation
        typed_params.append(typed_param)
    return typed_params
