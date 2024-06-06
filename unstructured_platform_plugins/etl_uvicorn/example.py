from typing import Any


def sample_function(content: dict[str, Any]) -> dict[str, Any]:
    resp = {f"{k}_out": v for k, v in content.items()}
    return resp


async def async_sample_function(content: dict[str, Any]) -> dict[str, Any]:
    resp = {f"{k}_out": v for k, v in content.items()}
    return resp


def sample_improper_function(*args, **kwargs):
    pass


class SampleClass:

    def sample_method(self, content: dict[str, Any]) -> dict[str, Any]:
        resp = {f"{k}_{self.__class__.__name__}": v for k, v in content.items()}
        return resp


sample_class = SampleClass()
