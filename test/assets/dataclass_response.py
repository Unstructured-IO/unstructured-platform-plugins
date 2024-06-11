from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypedDict


class SampleFunctionResponse(TypedDict):
    response: dict[str, Any]


@dataclass
class SampleFunctionInput:
    name: str
    value: float


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
