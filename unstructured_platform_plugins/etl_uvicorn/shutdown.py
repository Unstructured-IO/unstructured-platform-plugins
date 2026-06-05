import logging
import threading

logger = logging.getLogger("uvicorn.error")

_cancellation_event = threading.Event()


class PluginShutdown(Exception):
    """Raised inside a plugin run-loop to abort in-flight work on SIGTERM.

    Caught by the etl_uvicorn invoke wrapper and mapped to a shutdown-abort
    response; must NOT be treated as a plugin failure.
    """


class CancellationToken:
    """Read-only view of the process shutdown signal handed to plugin run-funcs.

    Backed by a process-global event set by GracefulServer.handle_exit on
    SIGTERM/SIGINT. ``.set()`` is intentionally not exposed so plugins cannot
    self-trigger shutdown.
    """

    def __init__(self, event: threading.Event) -> None:
        self._event = event

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise PluginShutdown("shutdown requested; aborting in-flight work")


def request_shutdown() -> None:
    if not _cancellation_event.is_set():
        logger.info("shutdown requested; signalling in-flight plugin work to stop")
        _cancellation_event.set()


def is_shutting_down() -> bool:
    return _cancellation_event.is_set()


def get_cancellation_token() -> CancellationToken:
    return CancellationToken(_cancellation_event)


def cancellation_dependency() -> CancellationToken:
    """FastAPI dependency for direct-FastAPI plugins to consult shutdown state."""
    return get_cancellation_token()


def reset_for_tests() -> None:
    """Clear the global event. Tests only."""
    _cancellation_event.clear()
