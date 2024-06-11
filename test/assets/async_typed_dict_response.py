from typing import Any, TypedDict


class SampleFunctionResponse(TypedDict):
    response: dict[str, Any]


async def async_sample_function(content: dict[str, Any]) -> SampleFunctionResponse:
    resp = {f"{k}_out": v for k, v in content.items()}
    return SampleFunctionResponse(response=resp)
