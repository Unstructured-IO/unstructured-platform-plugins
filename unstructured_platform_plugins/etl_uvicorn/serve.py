import os
from typing import Any, Optional

import uvicorn

from unstructured_platform_plugins.etl_uvicorn.shutdown import request_shutdown

DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN: int = int(os.getenv("UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN", "30"))


class GracefulServer(uvicorn.Server):
    """uvicorn Server that signals the process cancellation event on shutdown.

    ``handle_exit`` is uvicorn's single SIGINT/SIGTERM chokepoint (installed via
    ``capture_signals`` -> ``signal.signal``). We set the cancellation event
    before delegating so threadpool-bound plugin work can cooperatively stop.
    """

    def handle_exit(self, sig: int, frame: Any) -> None:
        request_shutdown()
        super().handle_exit(sig, frame)


def serve(
    app: Any,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    log_level: Optional[Any] = None,
    log_config: Optional[Any] = None,
    timeout_graceful_shutdown: Optional[int] = DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN,
    **kwargs: Any,
) -> None:
    """Launch ``app`` under a GracefulServer with a finite graceful-shutdown timeout."""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level=log_level,
        log_config=log_config,
        timeout_graceful_shutdown=timeout_graceful_shutdown,
        **kwargs,
    )
    GracefulServer(config).run()
