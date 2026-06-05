from unittest.mock import patch

from click.testing import CliRunner

from unstructured_platform_plugins.etl_uvicorn.main import get_command
from unstructured_platform_plugins.etl_uvicorn.serve import DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN


def test_cli_uses_graceful_server_with_finite_timeout():
    captured = {}

    class _FakeServer:
        def __init__(self, config):
            captured["config"] = config

        def run(self):
            captured["ran"] = True

    with (
        patch(
            "unstructured_platform_plugins.etl_uvicorn.main.generate_fast_api",
            return_value=lambda *a, **k: None,
        ),
        patch("unstructured_platform_plugins.etl_uvicorn.main.GracefulServer", _FakeServer),
    ):
        runner = CliRunner()
        result = runner.invoke(
            get_command(),
            ["test.assets.hash_function:get_hash", "--host", "0.0.0.0", "--port", "8000"],
        )

    assert result.exit_code == 0, result.output
    assert captured.get("ran") is True
    assert captured["config"].timeout_graceful_shutdown == DEFAULT_TIMEOUT_GRACEFUL_SHUTDOWN
