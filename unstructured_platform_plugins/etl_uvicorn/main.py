from typing import Optional

import click
from uvicorn.main import LOGGING_CONFIG, main, run

from unstructured_platform_plugins.etl_uvicorn.fastapi import generate_fast_api


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
        **kwargs,
    ):
        fastapi_app = generate_fast_api(
            app=app, method_name=method_name, id_str=plugin_id, id_method=plugin_id_method
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
        ]
    )
    return cmd


cmd = get_command()

if __name__ == "__main__":
    cmd = get_command()
    cmd()
