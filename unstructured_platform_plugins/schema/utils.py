import inspect
from inspect import Parameter, _empty
from typing import Callable, get_type_hints


class TypedParameter(Parameter):
    def __init__(self, *args, param_type=_empty, **kwargs):
        super().__init__(*args, **kwargs)
        self.param_type = param_type

    @classmethod
    def from_paramaeter(cls, param: Parameter) -> "TypedParameter":
        return cls(
            name=param.name, default=param.default, annotation=param.annotation, kind=param.kind
        )


def get_types_parameters(fn: Callable) -> list[TypedParameter]:
    type_hints = get_type_hints(fn)
    parameters = list(inspect.signature(fn).parameters.values())
    typed_params = []
    for p in parameters:
        typed_param = TypedParameter.from_paramaeter(param=p)
        typed_param.param_type = type_hints[typed_param.name]
        typed_params.append(typed_param)
    return typed_params
