from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypedDict

from pydantic import BaseModel


class SampleFunctionResponse(TypedDict):
    response: dict[str, Any]


@dataclass
class SampleFunctionInput:
    name: str
    value: float


def sample_function(content: SampleFunctionInput) -> SampleFunctionResponse:
    resp = {f"{k}_out": v for k, v in content.__dict__.items()}
    return SampleFunctionResponse(response=resp)


@dataclass
class SampleFunctionWithPathResponse:
    t: str
    exists: bool
    resolved: str
    b: str
    c: int


def sample_function_with_path(
    b: str, c: int, a: Optional[Path] = None
) -> SampleFunctionWithPathResponse:
    s: list[Any] = [type(a).__name__, f"[exists: {a.exists()}]", a.resolve()] if a else []
    s.extend([b, c])
    resp = {
        "t": type(a).__name__,
        "exists": a.exists(),
        "resolved": a.resolve(),
        "b": b,
        "c": c,
    }
    return SampleFunctionWithPathResponse(**resp)


async def async_sample_function(content: dict[str, Any]) -> dict[str, Any]:
    resp = {f"{k}_out": v for k, v in content.items()}
    return SampleFunctionResponse(response=resp)


def sample_improper_function(*args, **kwargs):
    pass


class SampleClassMethodResponse(BaseModel):
    response: dict[str, Any]


class SampleClass:

    def sample_method(self, content: dict[str, Any]) -> SampleClassMethodResponse:
        resp = {f"{k}_{self.__class__.__name__}": v for k, v in content.items()}
        return SampleClassMethodResponse(response=resp)


sample_class = SampleClass()
