import asyncio
import threading

import pytest

from unstructured_platform_plugins.etl_uvicorn import shutdown
from unstructured_platform_plugins.etl_uvicorn.api_generator import invoke_func
from unstructured_platform_plugins.etl_uvicorn.shutdown import (
    CancellationToken,
    PluginShutdown,
)


@pytest.fixture(autouse=True)
def _reset():
    shutdown.reset_for_tests()
    yield
    shutdown.reset_for_tests()


async def test_sync_runfunc_bails_promptly_when_cancelled():
    started = threading.Event()

    def blocking_run(cancellation_token: CancellationToken) -> str:
        started.set()
        # simulate a unit-of-work loop that polls between units
        for _ in range(1000):
            cancellation_token.raise_if_cancelled()
            threading.Event().wait(0.01)
        return "completed"

    token = shutdown.get_cancellation_token()
    task = asyncio.ensure_future(
        invoke_func(func=blocking_run, kwargs={"cancellation_token": token})
    )
    await asyncio.get_event_loop().run_in_executor(None, started.wait, 2.0)
    shutdown.request_shutdown()
    with pytest.raises(PluginShutdown):
        await asyncio.wait_for(task, timeout=2.0)
