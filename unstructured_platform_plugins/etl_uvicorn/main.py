import asyncio
import hashlib
import inspect
import json
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import click
from fastapi import FastAPI
from pydantic import BaseModel
from uvicorn.importer import import_from_string
from uvicorn.main import LOGGING_CONFIG, main, run

from unstructured_platform_plugins.etl_uvicorn.json_schema import (
    parameters_to_json_schema,
    response_to_json_schema,
    schema_to_base_model,
)


def get_func(instance: Any, method_name: Optional[str] = None) -> Callable:
    method_name = method_name or "__call__"
    if inspect.isfunction(instance):
        return instance
    elif inspect.isclass(instance):
        i = instance()
        return getattr(i, method_name)
    elif isinstance(instance, object) and hasattr(instance, method_name):
        func = getattr(instance, method_name)
        if inspect.ismethod(func):
            return func
    raise ValueError(f"type of instance not recognized: {type(instance)}")


def get_plugin_id(instance: Any, method_name: Optional[str] = None) -> str:
    method_name = method_name or "__call__"
    ref_id = None
    if inspect.isfunction(instance):
        ref_id = instance()
    elif inspect.isclass(instance):
        i = instance()
        method_name = method_name or "__call__"
        fn = getattr(i, method_name)
        ref_id = fn()
    elif isinstance(instance, object) and hasattr(instance, method_name):
        func = getattr(instance, method_name)
        if inspect.ismethod(func):
            ref_id = func()
    else:
        ref_id = instance
    if not ref_id:
        raise ValueError(f"id could not be parsed from instance {instance}")
    ref_id = str(ref_id)
    if not ref_id.isidentifier():
        raise ValueError(f"'{ref_id}' is not a valid identifier")
    return ref_id


def get_input_schema(func: Callable) -> dict:
    sig = inspect.signature(func)
    parameters = list(sig.parameters.values())
    return parameters_to_json_schema(parameters)


def get_output_sig(func: Callable) -> Optional[Any]:
    sig = inspect.signature(func)
    outputs = (
        sig.return_annotation if sig.return_annotation is not inspect.Signature.empty else None
    )
    return outputs


def get_output_schema(func: Callable) -> dict:
    return response_to_json_schema(get_output_sig(func))


def get_schema_dict(func) -> dict:
    return {
        "inputs": get_input_schema(func),
        "outputs": get_output_schema(func),
    }


def map_inputs(func: Callable, raw_inputs: dict[str, Any]) -> dict[str, Any]:
    input_params = {p.name: p for p in inspect.signature(func).parameters.values()}
    for k, v in input_params.items():
        annotation = v.annotation
        if is_dataclass(annotation) and k in raw_inputs and isinstance(raw_inputs[k], dict):
            raw_inputs[k] = annotation(**raw_inputs[k])
        elif issubclass(annotation, BaseModel):
            raw_inputs[k] = annotation.parse_obj(raw_inputs[k])
    return raw_inputs


def generate_fast_api(
    app: str,
    method_name: Optional[str] = None,
    id_str: Optional[str] = None,
    id_method: Optional[str] = None,
) -> FastAPI:
    instance = import_from_string(app)
    func = get_func(instance, method_name)
    if id_str:
        id_ref = import_from_string(id_str)
        plugin_id = get_plugin_id(instance=id_ref, method_name=id_method)
    else:
        plugin_id = hashlib.sha256(
            json.dumps(get_schema_dict(func), sort_keys=True).encode()
        ).hexdigest()[:32]

    fastapi_app = FastAPI()

    response_type = get_output_sig(func)

    InputSchema = schema_to_base_model(get_input_schema(func))

    @fastapi_app.post("/invoke")
    async def run_job(request: InputSchema) -> response_type:
        input_schema = get_input_schema(func)
        request_dict = request.dict()
        for k, v in request_dict.items():
            if schema := input_schema.get(k):  # noqa: SIM102
                if (
                    schema.get("type") == "string"
                    and schema.get("is_path", False)
                    and isinstance(v, str)
                ):
                    request_dict[k] = Path(v)
        map_inputs(func=func, raw_inputs=request_dict)
        print(f"passing inputs: {request_dict}")
        if inspect.iscoroutinefunction(func):
            return await func(**request_dict)
        else:
            return func(**request_dict)

    class SchemaOutputResponse(BaseModel):
        inputs: dict[str, Any]
        outputs: dict[str, Any]

    @fastapi_app.get("/schema")
    async def get_schema() -> SchemaOutputResponse:
        schema = get_schema_dict(func)
        resp = SchemaOutputResponse(inputs=schema["inputs"], outputs=schema["outputs"])
        return resp

    @fastapi_app.get("/id")
    async def get_id() -> str:
        return plugin_id

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
        plugin_id: Optional[str] = None,
        plugin_id_method: Optional[str] = None,
        **kwargs,
    ):
        fastapi_app = generate_fast_api(
            app, method_name, id_str=plugin_id, id_method=plugin_id_method
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
