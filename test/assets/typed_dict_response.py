from dataclasses import dataclass
from typing import Any, TypedDict


class SampleFunctionResponse(TypedDict):
    response: dict[str, Any]


@dataclass
class SampleFunctionInput:
    name: str
    value: float


def sample_function(content: SampleFunctionInput) -> SampleFunctionResponse:
    resp = {f"{k}_out": v for k, v in content.__dict__.items()}
    return SampleFunctionResponse(response=resp)
