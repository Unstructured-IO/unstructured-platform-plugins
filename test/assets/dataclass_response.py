from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypedDict, Union

from unstructured_ingest.v2.interfaces import BatchFileData, FileData


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
    p: bool


def sample_function_with_path(
    file_data: Union[FileData, BatchFileData], b: str, c: int, a: Optional[Path] = None
) -> SampleFunctionWithPathResponse:
    s: list[Any] = [type(a).__name__, f"[exists: {a.exists()}]", a.resolve()] if a else []
    s.extend([b, c])
    resp = {
        "t": type(a).__name__,
        "exists": a.exists(),
        "resolved": a.resolve(),
        "b": b,
        "c": c,
        "p": (
            False
            if isinstance(file_data, BatchFileData)
            else file_data.source_identifiers.relative_path is not None
        ),
    }
    return SampleFunctionWithPathResponse(**resp)
