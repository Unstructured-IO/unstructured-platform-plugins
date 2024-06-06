import asyncio
import inspect
from typing import Any, Callable, Optional

import click
from fastapi import FastAPI
from platform_plugins.etl_uvicorn.json_schema import parameters_to_json_schema, type_to_json_schema
from uvicorn.importer import import_from_string
from uvicorn.main import LOGGING_CONFIG, logger, main, run


def get_func(instance: Any, method_name: Optional[str] = None) -> Callable:
    if inspect.isfunction(instance):
        return instance
    elif inspect.isclass(instance):
        i = instance()
        method_name = method_name or "__call__"
        return getattr(i, method_name)
    elif isinstance(instance, object):
        try:
            method_name = method_name or "__call__"
            func = getattr(instance, method_name)
            if inspect.ismethod(func):
                return func
        except Exception as e:
            logger.debug(f"attempt to call instantiated class failed: {e}")
    raise ValueError(f"type of instance not recognized: {type(instance)}")


def generate_fast_api(app: str, method_name: Optional[str] = None) -> FastAPI:
    instance = import_from_string(app)
    func = get_func(instance, method_name)
    fastapi_app = FastAPI()

    @fastapi_app.post("/invoke")
    async def run_job(request: dict[str, Any]):
        if inspect.iscoroutinefunction(func):
            return await func(**request)
        else:
            return func(**request)

    @fastapi_app.get("/schema")
    async def get_schema() -> dict[str, Any]:
        sig = inspect.signature(func)
        parameters = list(sig.parameters.values())
        outputs = (
            sig.return_annotation if sig.return_annotation is not inspect.Signature.empty else None
        )
        resp = {
            "inputs": parameters_to_json_schema(parameters),
            "outputs": type_to_json_schema(outputs),
        }
        return resp

    # Run initial schema validation
    try:
        asyncio.run(get_schema())
    except TypeError as e:
        raise TypeError(f"failed to validate function schema: {e}") from e

    return fastapi_app


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
        **kwargs,
    ):
        fastapi_app = generate_fast_api(app, method_name)
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
    cmd.params.append(
        click.Option(
            ["--method-name"],
            required=False,
            type=str,
            default=None,
            help="If passed in instance is a class, what method to wrap. "
            "Will fall back to __call__ if none is provided.",
        )
    )
    return cmd


cmd = get_command()

if __name__ == "__main__":
    cmd = get_command()
    cmd()
