from typing import Any, TypedDict

from pydantic import BaseModel


class SampleFunctionResponse(TypedDict):
    response: dict[str, Any]


class SampleClassMethodResponse(BaseModel):
    response: dict[str, Any]


class SampleClass:

    def sample_method(self, content: dict[str, Any]) -> SampleClassMethodResponse:
        resp = {f"{k}_{self.__class__.__name__}": v for k, v in content.items()}
        return SampleClassMethodResponse(response=resp)


sample_class = SampleClass()
