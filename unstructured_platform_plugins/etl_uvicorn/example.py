from pathlib import Path
from typing import Any, Optional


def sample_function(content: dict[str, Any]) -> dict[str, Any]:
    resp = {f"{k}_out": v for k, v in content.items()}
    return resp


def sample_function_with_path(b: str, c: int, a: Optional[Path] = None) -> str:
    s: list[Any] = [type(a).__name__, f"[exists: {a.exists()}]", a.resolve()] if a else []
    s.extend([b, c])
    return "-".join([str(a) for a in s])


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
