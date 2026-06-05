import threading

import pytest

from unstructured_platform_plugins.etl_uvicorn import shutdown
from unstructured_platform_plugins.etl_uvicorn.shutdown import (
    CancellationToken,
    PluginShutdown,
)


@pytest.fixture(autouse=True)
def _reset():
    shutdown.reset_for_tests()
    yield
    shutdown.reset_for_tests()


def test_token_not_cancelled_by_default():
    token = shutdown.get_cancellation_token()
    assert token.cancelled is False
    token.raise_if_cancelled()  # no raise


def test_request_shutdown_flips_token_and_global():
    token = shutdown.get_cancellation_token()
    assert shutdown.is_shutting_down() is False
    shutdown.request_shutdown()
    assert shutdown.is_shutting_down() is True
    assert token.cancelled is True
    with pytest.raises(PluginShutdown):
        token.raise_if_cancelled()


def test_token_has_no_set_method():
    token = shutdown.get_cancellation_token()
    assert not hasattr(token, "set")


def test_token_reads_live_event():
    event = threading.Event()
    token = CancellationToken(event)
    assert token.cancelled is False
    event.set()
    assert token.cancelled is True
