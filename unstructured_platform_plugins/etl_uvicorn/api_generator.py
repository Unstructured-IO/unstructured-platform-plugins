import asyncio
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Optional

from fastapi import FastAPI, status
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
from unstructured_platform_plugins.schema.usage import UsageData

logger = logging.getLogger("uvicorn.error")


async def invoke_func(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> Any:
    kwargs = kwargs or {}
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    else:
        return func(**kwargs)


def check_precheck_func(precheck_func: Callable):
    sig = inspect.signature(precheck_func)
    inputs = sig.parameters.values()
    outputs = sig.return_annotation
    if len(inputs) == 1:
        i = inputs[0]
        if i.name != "usage" or i.annotation is list:
            raise ValueError("the only input available for precheck is usage which must be a list")
    if outputs not in [None, sig.empty]:
        raise ValueError(f"no output should exist for precheck function, found: {outputs}")


def generate_fast_api(
    app: str,
    method_name: Optional[str] = None,
    id_str: Optional[str] = None,
    id_method: Optional[str] = None,
    precheck_str: Optional[str] = None,
    precheck_method: Optional[str] = None,
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

    precheck_func = None
    if precheck_str:
        precheck_instance = import_from_string(precheck_str)
        precheck_func = get_func(precheck_instance, precheck_method)
    elif precheck_method:
        precheck_func = get_func(instance, precheck_method)
    if precheck_func is not None:
        check_precheck_func(precheck_func=precheck_func)

    logger.debug(f"set static id response to: {plugin_id}")

    fastapi_app = FastAPI()

    response_type = get_output_sig(func)

    class InvokeResponse(BaseModel):
        usage: list[UsageData]
        status_code: int
        status_code_text: Optional[str] = None
        output: Optional[response_type] = None

    input_schema = get_input_schema(func, omit=["usage"])
    input_schema_model = schema_to_base_model(input_schema)

    logging.getLogger("etl_uvicorn.fastapi")

    async def wrap_fn(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> InvokeResponse:
        usage: list[UsageData] = []
        request_dict = kwargs if kwargs else {}
        if "usage" in inspect.signature(func).parameters:
            request_dict["usage"] = usage
        else:
            logger.warning("usage data not an expected parameter, omitting")
        try:
            output = await invoke_func(func=func, kwargs=request_dict)
            return InvokeResponse(usage=usage, status_code=status.HTTP_200_OK, output=output)
        except Exception as invoke_error:
            logger.error(f"failed to invoke plugin: {invoke_error}", exc_info=True)
            return InvokeResponse(
                usage=usage,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                status_code_text=f"failed to invoke plugin: "
                f"[{invoke_error.__class__.__name__}] {invoke_error}",
            )

    if input_schema_model.model_fields:

        @fastapi_app.post("/invoke", response_model=InvokeResponse)
        async def run_job(request: input_schema_model) -> InvokeResponse:
            logger.debug(f"invoking function {func} with input: {request.model_dump()}")
            # Create dictionary from pydantic model while preserving underlying types
            request_dict = {f: getattr(request, f) for f in request.model_fields}
            map_inputs(func=func, raw_inputs=request_dict)
            logger.debug(f"passing inputs to function: {request_dict}")
            return await wrap_fn(func=func, kwargs=request_dict)

    else:

        @fastapi_app.post("/invoke", response_model=response_type)
        async def run_job() -> response_type:
            logger.debug(f"invoking function without inputs: {func}")
            return await wrap_fn(
                func=func,
            )

    class SchemaOutputResponse(BaseModel):
        inputs: dict[str, Any]
        outputs: dict[str, Any]

    @fastapi_app.get("/", include_in_schema=False)
    async def docs_redirect():
        return RedirectResponse("/docs")

    class InvokePrecheckResponse(BaseModel):
        usage: list[UsageData]
        status_code: int
        status_code_text: Optional[str] = None

    @fastapi_app.get("/schema")
    async def get_schema() -> SchemaOutputResponse:
        schema = get_schema_dict(func)
        resp = SchemaOutputResponse(inputs=schema["inputs"], outputs=schema["outputs"])
        return resp

    @fastapi_app.get("/precheck")
    async def run_precheck() -> InvokePrecheckResponse:
        if precheck_func:
            fn_response = await wrap_fn(func=precheck_func)
            return InvokePrecheckResponse(
                status_code=fn_response.status_code,
                status_code_text=fn_response.status_code_text,
                usage=fn_response.usage,
            )
        else:
            return InvokePrecheckResponse(status_code=status.HTTP_200_OK, usage=[])

    @fastapi_app.get("/id")
    async def get_id() -> str:
        return plugin_id

    # Run initial schema validation
    try:
        asyncio.run(get_schema())
    except TypeError as e:
        raise TypeError(f"failed to validate function schema: {e}") from e

    return fastapi_app
