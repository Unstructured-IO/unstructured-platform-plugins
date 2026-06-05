from pydantic import BaseModel

from unstructured_platform_plugins.etl_uvicorn.shutdown import CancellationToken


class Result(BaseModel):
    value: int


class CancelAwareAsyncGen:
    def id(self) -> str:
        return "cancel_aware_asyncgen"

    async def run(self, value: int, cancellation_token: CancellationToken) -> Result:
        cancellation_token.raise_if_cancelled()
        yield Result(value=value + 1)
