from typing import Optional

from pydantic import BaseModel

from unstructured_platform_plugins.etl_uvicorn.shutdown import CancellationToken


class Result(BaseModel):
    value: int


class CancelAwareSync:
    def id(self) -> str:
        return "cancel_aware_sync"

    def run(self, value: int, cancellation_token: CancellationToken) -> Optional[Result]:
        cancellation_token.raise_if_cancelled()
        return Result(value=value + 1)
