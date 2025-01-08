import asyncio
import hashlib
import inspect
import json
import logging
from functools import partial
from typing import Any, Callable, Optional, Union

from fastapi import FastAPI, status
from fastapi.responses import StreamingResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field, create_model
from starlette.responses import RedirectResponse
from unstructured_ingest.v2.interfaces.file_data import file_data_from_dict
from uvicorn.config import LOG_LEVELS
from uvicorn.importer import import_from_string

from unstructured_platform_plugins.etl_uvicorn.errors import wrap_error
from unstructured_platform_plugins.etl_uvicorn.otel import get_metric_provider, get_trace_provider
from unstructured_platform_plugins.etl_uvicorn.utils import (
    get_func,
    get_input_schema,
    get_output_sig,
    get_plugin_id,
    get_schema_dict,
    map_inputs,
)
from unstructured_platform_plugins.exceptions import UnrecoverableException
from unstructured_platform_plugins.schema import FileDataMeta, NewRecord, UsageData
from unstructured_platform_plugins.schema.json_schema import (
    schema_to_base_model,
)


class EtlApiException(Exception):
    pass


logger = logging.getLogger("uvicorn.error")


def log_func_and_body(func: Callable, body: Optional[str] = None) -> None:
    msg = None
    if logger.level == LOG_LEVELS.get("debug", logging.NOTSET):
        if not body:
            msg = f"invoking function without inputs: {func.__name__}"
        else:
            msg = f"invoking function {func.__name__} with body"
    elif logger.level == LOG_LEVELS.get("trace", logging.NOTSET):
        if not body:
            msg = f"invoking function without inputs: {func}"
        else:
            msg = f"invoking function {func} with body: {body}"
    if msg:
        logger.log(level=logger.level, msg=msg)


async def invoke_func(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> Any:
    kwargs = kwargs or {}
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    else:
        return await asyncio.get_event_loop().run_in_executor(None, partial(func, **kwargs))


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


def is_optional(t: Any) -> bool:
    return (
        hasattr(t, "__origin__")
        and t.__origin__ is Union
        and hasattr(t, "__args__")
        and type(None) in t.__args__
    )


def update_filedata_model(new_type) -> BaseModel:
    field_info = NewRecord.model_fields["contents"]
    if is_optional(new_type):
        field_info.default = None
    if new_type is None:
        new_type = type(None)
        field_info.default = None
    new_record_model = create_model(
        NewRecord.__name__, contents=(new_type, field_info), __base__=NewRecord
    )
    new_filedata_model = create_model(
        FileDataMeta.__name__,
        new_records=(list[new_record_model], Field(default_factory=list)),
        __base__=FileDataMeta,
    )
    return new_filedata_model


def wrap_in_fastapi(
    func: Callable,
    plugin_id: str,
    precheck_func: Optional[Callable] = None,
) -> FastAPI:
    try:
        return _wrap_in_fastapi(func=func, plugin_id=plugin_id, precheck_func=precheck_func)
    except Exception as e:
        logger.error(f"failed to wrap function in FastAPI: {e}", exc_info=True)
        raise EtlApiException(e) from e


def _wrap_in_fastapi(
    func: Callable,
    plugin_id: str,
    precheck_func: Optional[Callable] = None,
) -> FastAPI:
    if precheck_func is not None:
        check_precheck_func(precheck_func=precheck_func)

    logger.debug(f"set static id response to: {plugin_id}")

    fastapi_app = FastAPI()

    response_type = get_output_sig(func)
    filedata_meta_model = update_filedata_model(response_type)

    class InvokeResponse(BaseModel):
        usage: list[UsageData]
        status_code: int
        filedata_meta: filedata_meta_model
        status_code_text: Optional[str] = None
        output: Optional[response_type] = None

    input_schema = get_input_schema(func, omit=["usage", "filedata_meta"])
    input_schema_model = schema_to_base_model(input_schema)

    logging.getLogger("etl_uvicorn.fastapi")

    ResponseType = StreamingResponse if inspect.isasyncgenfunction(func) else InvokeResponse

    async def wrap_fn(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> ResponseType:
        usage: list[UsageData] = []
        filedata_meta = FileDataMeta()
        request_dict = kwargs if kwargs else {}
        if "usage" in inspect.signature(func).parameters:
            request_dict["usage"] = usage
        else:
            logger.warning("usage data not an expected parameter, omitting")
        if "filedata_meta" in inspect.signature(func).parameters:
            request_dict["filedata_meta"] = filedata_meta
        try:
            if inspect.isasyncgenfunction(func):
                # Stream response if function is an async generator

                async def _stream_response():
                    async for output in func(**(request_dict or {})):
                        yield InvokeResponse(
                            usage=usage,
                            filedata_meta=filedata_meta_model.model_validate(
                                filedata_meta.model_dump()
                            ),
                            status_code=status.HTTP_200_OK,
                            output=output,
                        ).model_dump_json() + "\n"

                return StreamingResponse(_stream_response(), media_type="application/x-ndjson")
            else:
                output = await invoke_func(func=func, kwargs=request_dict)
                return InvokeResponse(
                    usage=usage,
                    filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                    status_code=status.HTTP_200_OK,
                    output=output,
                )
        except UnrecoverableException as ex:
            logger.info("Unrecoverable error occurred during plugin invocation")
            return InvokeResponse(
                usage=usage,
                status_code=512,
                status_code_text=ex.message,
                filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
            )
        except Exception as invoke_error:
            logger.error(f"failed to invoke plugin: {invoke_error}", exc_info=True)
            http_error = wrap_error(invoke_error)
            return InvokeResponse(
                usage=usage,
                filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                status_code=http_error.status_code,
                status_code_text=f"[{invoke_error.__class__.__name__}] {invoke_error}",
            )

    if input_schema_model.model_fields:

        @fastapi_app.post("/invoke", response_model=InvokeResponse)
        async def run_job(request: input_schema_model) -> ResponseType:
            log_func_and_body(func=func, body=request.json())
            # Create dictionary from pydantic model while preserving underlying types
            request_dict = {f: getattr(request, f) for f in request.model_fields}
            # Make sure nested classes get instantiated correctly
            if "file_data" in request_dict:
                request_dict["file_data"] = file_data_from_dict(
                    request_dict["file_data"].model_dump()
                )
            map_inputs(func=func, raw_inputs=request_dict)
            if logger.level == LOG_LEVELS.get("trace", logging.NOTSET):
                logger.log(level=logger.level, msg=f"passing inputs to function: {request_dict}")
            return await wrap_fn(func=func, kwargs=request_dict)

    else:

        @fastapi_app.post("/invoke", response_model=InvokeResponse)
        async def run_job() -> ResponseType:
            log_func_and_body(func=func)
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

    FastAPIInstrumentor.instrument_app(
        fastapi_app, tracer_provider=get_trace_provider(), meter_provider=get_metric_provider()
    )

    return fastapi_app


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

    return wrap_in_fastapi(func=func, plugin_id=plugin_id, precheck_func=precheck_func)
