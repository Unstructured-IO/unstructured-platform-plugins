import signal

import pytest
from uvicorn.config import Config

from unstructured_platform_plugins.etl_uvicorn import shutdown
from unstructured_platform_plugins.etl_uvicorn.serve import (
    DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN,
    GracefulServer,
)


@pytest.fixture(autouse=True)
def _reset():
    shutdown.reset_for_tests()
    yield
    shutdown.reset_for_tests()


def _dummy_app(scope, receive, send):  # minimal ASGI app
    raise NotImplementedError


def test_handle_exit_sets_cancellation_event_and_delegates():
    server = GracefulServer(Config(_dummy_app))
    assert shutdown.is_shutting_down() is False
    server.handle_exit(signal.SIGTERM, None)
    assert shutdown.is_shutting_down() is True
    # super().handle_exit must still run uvicorn's own shutdown bookkeeping
    assert server.should_exit is True


def test_default_timeout_is_finite():
    assert isinstance(DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN, int)
    assert DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN > 0


def test_serve_constructs_graceful_server_with_passed_timeout():
    """serve() must build a GracefulServer whose Config carries the caller's timeout."""
    from unittest.mock import patch

    from unstructured_platform_plugins.etl_uvicorn.serve import serve

    captured = {}

    class _FakeServer:
        def __init__(self, config):
            captured["config"] = config

        def run(self):
            captured["ran"] = True

    with patch("unstructured_platform_plugins.etl_uvicorn.serve.GracefulServer", _FakeServer):
        serve(_dummy_app, port=9999, timeout_graceful_shutdown=7)

    assert captured.get("ran") is True
    assert captured["config"].timeout_graceful_shutdown == 7
