from dataclasses import dataclass, field
from typing import IO, Any, Optional

import click
from uvicorn.config import LOGGING_CONFIG, Config, RawConfigParser
from uvicorn.main import main, run

from unstructured_platform_plugins.etl_uvicorn.api_generator import generate_fast_api


@dataclass
class CustomConfig:
    log_config: dict[str, Any] | str | RawConfigParser | IO[Any] | None = field(
        default_factory=lambda: LOGGING_CONFIG
    )
    log_level: str | int | None = None
    use_colors: bool | None = None
    access_log: bool = True


CustomConfig.configure_logging = Config.configure_logging


def get_command() -> click.Command:
    @click.command(context_settings={"auto_envvar_prefix": "UVICORN"})
    def api_wrapper(
        app: str,
        log_config: str,
        reload_dirs: list[str],
        reload_includes: list[str],
        reload_excludes: list[str],
        headers: list[str],
        method_name: Optional[str] = None,
        plugin_id: Optional[str] = None,
        plugin_id_method: Optional[str] = None,
        precheck_app: Optional[str] = None,
        precheck_app_method: Optional[str] = None,
        **kwargs,
    ):
        # Make sure logging is configured before the call to run() so any setup has the same format
        config = CustomConfig(
            log_config=LOGGING_CONFIG if log_config is None else log_config,
            log_level=kwargs["log_level"],
            use_colors=kwargs["use_colors"],
            access_log=kwargs["access_log"],
        )
        config.configure_logging()
        fastapi_app = generate_fast_api(
            app=app,
            method_name=method_name,
            id_str=plugin_id,
            id_method=plugin_id_method,
            precheck_str=precheck_app,
            precheck_method=precheck_app_method,
        )
        # Explicitly map values that are manipulated in the original
        # call to run(), preventing **kwargs reference
        run(
            fastapi_app,
            log_config=LOGGING_CONFIG if log_config is None else log_config,
            reload_dirs=reload_dirs or None,
            reload_includes=reload_includes or None,
            reload_excludes=reload_excludes or None,
            headers=[header.split(":", 1) for header in headers],  # type: ignore[misc]
            **kwargs,
        )

    cmd = api_wrapper
    cmd.params = main.params
    cmd.params.extend(
        [
            click.Option(
                ["--method-name"],
                required=False,
                type=str,
                default=None,
                help="If passed in instance is a class, what method to wrap. "
                "Will fall back to __call__ if none is provided.",
            ),
            click.Option(
                ["--plugin-id"],
                required=False,
                type=str,
                default=None,
                help="Reference to either a value or function to get "
                "the plugin id once instantiated",
            ),
            click.Option(
                ["--plugin-id-method"],
                required=False,
                type=str,
                default=None,
                help="If plugin id reference is a class, what method to wrap. "
                "Will fall back to __call__ if none is provided.",
            ),
            click.Option(
                ["--precheck-app"],
                required=False,
                type=str,
                default=None,
                help="If provided, must point to code to run for precheck",
            ),
            click.Option(
                ["--precheck-app-method"],
                required=False,
                type=str,
                default=None,
                help="If provided, points to a method to call on a class. "
                "If precheck-app not provided, assumes method "
                "lives on main class passes in.",
            ),
        ]
    )
    return cmd


cmd = get_command()

if __name__ == "__main__":
    cmd = get_command()
    cmd()
