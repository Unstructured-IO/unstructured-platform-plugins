import asyncio
import hashlib
import inspect
import json
import logging
from pathlib import Path
from typing import Any, Optional, Callable

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import RedirectResponse
from uvicorn.importer import import_from_string

from unstructured_platform_plugins.etl_uvicorn.utils import (
    get_func,
    get_input_schema,
    get_output_sig,
    get_plugin_id,
    get_schema_dict,
    map_inputs,
)
from unstructured_platform_plugins.schema.json_schema import (
    schema_to_base_model,
)

logger = logging.getLogger("uvicorn.error")


async def invoke_func(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> Any:
    kwargs = kwargs or {}
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    else:
        return func(**kwargs)


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
    logger.debug(f"set static id response to: {plugin_id}")

    fastapi_app = FastAPI()

    response_type = get_output_sig(func)

    input_schema_model = schema_to_base_model(get_input_schema(func))

    logging.getLogger("etl_uvicorn.fastapi")

    if input_schema_model.model_fields:
        logger.debug(f"input model set to: {input_schema_model.model_fields}")

        @fastapi_app.post("/invoke", response_model=response_type)
        async def run_job(request: input_schema_model) -> response_type:
            logger.debug(f"invoking function: {func}")
            input_schema = get_input_schema(func)
            request_dict = request.model_dump()
            for k, v in request_dict.items():
                if schema := input_schema.get(k):  # noqa: SIM102
                    if (
                        schema.get("type") == "string"
                        and schema.get("is_path", False)
                        and isinstance(v, str)
                    ):
                        request_dict[k] = Path(v)
            map_inputs(func=func, raw_inputs=request_dict)
            logger.debug(f"passing inputs to function: {request_dict}")
            return await invoke_func(func=func, kwargs=request_dict)

    else:

        @fastapi_app.post("/invoke", response_model=response_type)
        async def run_job() -> response_type:
            logger.debug(f"invoking function without inputs: {func}")
            return await invoke_func(func=func, kwargs=request_dict)

    class SchemaOutputResponse(BaseModel):
        inputs: dict[str, Any]
        outputs: dict[str, Any]

    @fastapi_app.get("/", include_in_schema=False)
    async def docs_redirect():
        return RedirectResponse("/docs")

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
