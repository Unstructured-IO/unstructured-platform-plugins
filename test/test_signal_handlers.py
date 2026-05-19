"""Verify the etl_uvicorn module installs a SIGTERM-ignoring handler on uvicorn.Server."""

import asyncio
import signal

import uvicorn

# Importing the module applies the monkey-patch as a side effect.
from unstructured_platform_plugins.etl_uvicorn import main  # noqa: F401


def test_uvicorn_server_install_signal_handlers_is_patched():
    assert (
        uvicorn.Server.install_signal_handlers.__name__
        == "_install_signal_handlers_ignoring_sigterm"
    )


def test_install_signal_handlers_registers_sigint_only():
    async def _run() -> None:
        config = uvicorn.Config(app="fake:app", lifespan="off")
        server = uvicorn.Server(config=config)
        server.install_signal_handlers()
        loop = asyncio.get_running_loop()
        try:
            assert loop.remove_signal_handler(signal.SIGINT) is True
            assert loop.remove_signal_handler(signal.SIGTERM) is False
        finally:
            try:
                loop.remove_signal_handler(signal.SIGINT)
                loop.remove_signal_handler(signal.SIGTERM)
            except Exception:
                pass

    asyncio.run(_run())
