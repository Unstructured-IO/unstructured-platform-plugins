import asyncio
import contextvars
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Optional, Union, get_origin

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, Field, create_model
from starlette.responses import RedirectResponse
from typing_extensions import deprecated
from unstructured_ingest.data_types.file_data import BatchFileData, FileData, file_data_from_dict
from unstructured_ingest.error import UnstructuredIngestError, UserError
from uvicorn.config import LOG_LEVELS
from uvicorn.importer import import_from_string

from unstructured_platform_plugins.etl_uvicorn.otel import get_metric_provider, get_trace_provider
from unstructured_platform_plugins.etl_uvicorn.utils import (
    get_func,
    get_input_schema,
    get_output_sig,
    get_plugin_id,
    get_schema_dict,
    map_inputs,
)
from unstructured_platform_plugins.invocation_settings import (
    add_metadata_route,
    current_invocation_context,
    current_invocation_settings,
    install_invocation_envelope,
    invocation_envelope,
)
from unstructured_platform_plugins.schema import FileDataMeta, NewRecord, UsageData
from unstructured_platform_plugins.schema.json_schema import (
    schema_to_base_model,
)

FileDataType = Union[FileData, BatchFileData]


class EtlApiException(Exception):
    pass


logger = logging.getLogger("uvicorn.error")


class MessageChannels(BaseModel):
    infos: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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


def _error_attr(error: BaseException, name: str) -> Any:
    """Read an attribute off a raised error, treating a raising property as absent.

    Runs while an exception handler is building the sanitized response; an
    attribute access that itself raises must not replace that response with a
    raw 500.
    """
    try:
        return getattr(error, name, None)
    except Exception:
        return None


def _safe_str(value: object) -> str:
    """str() on a plugin-supplied error can itself raise; never let that escape the handler.

    An escape replaces the sanitized envelope with a raw HTTP 500, which the
    controller's preflight reads as fail-open — a plugin-reported failure would
    silently become a proceed.
    """
    try:
        return str(value)
    except Exception:
        return "<unrenderable error>"


def failure_category_of(error: BaseException) -> Optional[str]:
    """Return the error's failure_category only when it is a plain string."""
    category = _error_attr(error, "failure_category")
    return category if isinstance(category, str) else None


def status_code_of(error: BaseException) -> int:
    """Return the error's status_code only when it is an int in the HTTP range, else 500."""
    status_code = _error_attr(error, "status_code")
    if (
        isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 100 <= status_code <= 599
    ):
        return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


async def invoke_func(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> Any:
    kwargs = kwargs or {}
    if inspect.iscoroutinefunction(func):
        return await func(**kwargs)
    # to_thread copies contextvars into the worker thread, so OpenTelemetry
    # context (and any wide-event adoption inside func) survives the hop;
    # run_in_executor does not.
    return await asyncio.to_thread(func, **kwargs)


def check_precheck_func(precheck_func: Callable):
    try:
        # eval_str resolves postponed/string annotations ('list', 'None')
        sig = inspect.signature(precheck_func, eval_str=True)
    except (NameError, TypeError):
        sig = inspect.signature(precheck_func)
    inputs = list(sig.parameters.values())
    outputs = sig.return_annotation
    if len(inputs) == 1:
        i = inputs[0]
        annotation_is_list = (
            i.annotation is sig.empty or i.annotation is list or get_origin(i.annotation) is list
        )
        if i.name != "usage" or not annotation_is_list:
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


@deprecated(
    "wrap_in_fastapi is deprecated; build a FastAPI app directly with "
    "explicit handlers for the plugin contract routes."
)
def wrap_in_fastapi(
    func: Callable,
    plugin_id: str,
    precheck_func: Optional[Callable] = None,
    invoke_with_sealed_dag_node_settings: bool = False,
) -> FastAPI:
    try:
        return _wrap_in_fastapi(
            func=func,
            plugin_id=plugin_id,
            precheck_func=precheck_func,
            invoke_with_sealed_dag_node_settings=invoke_with_sealed_dag_node_settings,
        )
    except Exception as e:
        logger.error(f"failed to wrap function in FastAPI: {e}", exc_info=True)
        raise EtlApiException(e) from e


def _wrap_in_fastapi(
    func: Callable,
    plugin_id: str,
    precheck_func: Optional[Callable] = None,
    invoke_with_sealed_dag_node_settings: bool = False,
) -> FastAPI:
    if precheck_func is not None:
        check_precheck_func(precheck_func=precheck_func)

    logger.debug(f"set static id response to: {plugin_id}")

    if "usage" not in inspect.signature(func).parameters:
        logger.warning("usage data not an expected parameter, omitting")

    fastapi_app = FastAPI()
    # Installation contributes a public router dependency, so it must happen before /invoke is
    # registered. The dependency itself is a no-op for every other route.
    install_invocation_envelope(fastapi_app)

    response_type = get_output_sig(func)
    filedata_meta_model = update_filedata_model(response_type)

    class InvokeResponse(BaseModel):
        usage: list[UsageData]
        status_code: int
        file_data: Optional[FileDataType] = None
        filedata_meta: Optional[filedata_meta_model] = None
        status_code_text: Optional[str] = None
        failure_category: Optional[str] = None
        # Who must act on a failure: "user" only when the plugin raised the UserError family —
        # a fault in something the customer owns (their file, their credentials, their provider).
        # Absent means not-the-customer's: an orchestrator must never infer customer fault from
        # the status code alone, which also carries transport semantics.
        blame: Optional[str] = None
        output: Optional[response_type] = None
        message_channels: MessageChannels = Field(default_factory=MessageChannels)

    input_schema = get_input_schema(func, omit=["usage", "filedata_meta", "message_channels"])
    input_schema_model = schema_to_base_model(input_schema)

    logging.getLogger("etl_uvicorn.fastapi")

    ResponseType = StreamingResponse if inspect.isasyncgenfunction(func) else InvokeResponse

    async def wrap_fn(func: Callable, kwargs: Optional[dict[str, Any]] = None) -> ResponseType:
        usage: list[UsageData] = []
        filedata_meta = FileDataMeta()
        message_channels = MessageChannels()
        request_dict = kwargs if kwargs else {}
        params = inspect.signature(func).parameters
        if "usage" in params:
            request_dict["usage"] = usage
        if "message_channels" in params:
            request_dict["message_channels"] = message_channels
        if "filedata_meta" in params:
            request_dict["filedata_meta"] = filedata_meta
        bound_settings = current_invocation_settings()
        bound_context = current_invocation_context()
        try:
            if inspect.isasyncgenfunction(func):
                # Stream response if function is an async generator
                async def _stream_response():
                    # FastAPI 0.117 closes yield dependencies before iterating a
                    # StreamingResponse. Re-enter the captured binding inside the generator so the
                    # plugin sees the right request regardless of dependency-cleanup timing.
                    with invocation_envelope(bound_settings, bound_context):
                        try:
                            async for output in func(**(request_dict or {})):
                                yield (
                                    InvokeResponse(
                                        usage=usage,
                                        message_channels=message_channels,
                                        filedata_meta=filedata_meta_model.model_validate(
                                            filedata_meta.model_dump()
                                        ),
                                        status_code=status.HTTP_200_OK,
                                        output=output,
                                        file_data=request_dict.get("file_data", None),
                                    ).model_dump_json()
                                    + "\n"
                                )
                        except Exception as e:
                            logger.error(
                                f"Failure streaming response: {_safe_str(e)}", exc_info=True
                            )
                            yield (
                                InvokeResponse(
                                    usage=usage,
                                    message_channels=message_channels,
                                    filedata_meta=filedata_meta_model.model_validate(
                                        filedata_meta.model_dump()
                                    ),
                                    status_code=status_code_of(e),
                                    status_code_text=f"[{type(e).__name__}] {_safe_str(e)}",
                                    failure_category=failure_category_of(e),
                                    blame="user" if isinstance(e, UserError) else None,
                                ).model_dump_json()
                                + "\n"
                            )

                return StreamingResponse(_stream_response(), media_type="application/x-ndjson")
            else:
                # Keep execution-scoped binding explicit for the same reason as the streaming
                # branch; nested binding is harmless while the route dependency is still active.
                with invocation_envelope(bound_settings, bound_context):
                    output = await invoke_func(func=func, kwargs=request_dict)
                return InvokeResponse(
                    usage=usage,
                    message_channels=message_channels,
                    filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                    status_code=status.HTTP_200_OK,
                    output=output,
                    file_data=request_dict.get("file_data", None),
                )
        except HTTPException as exc:
            logger.error(
                f"HTTPException: {_safe_str(exc.detail)} (status_code={exc.status_code})",
                exc_info=True,
            )
            return InvokeResponse(
                usage=usage,
                message_channels=message_channels,
                filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                status_code=exc.status_code,
                status_code_text=exc.detail
                if isinstance(exc.detail, str)
                else json.dumps(exc.detail, default=_safe_str),
                failure_category=failure_category_of(exc),
                file_data=request_dict.get("file_data", None),
            )
        except UnstructuredIngestError as exc:
            logger.error(
                f"UnstructuredIngestError: {_safe_str(exc)} "
                f"(status_code={_error_attr(exc, 'status_code')})",
                exc_info=True,
            )
            return InvokeResponse(
                usage=usage,
                message_channels=message_channels,
                filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                status_code=status_code_of(exc),
                status_code_text=_safe_str(exc),
                failure_category=failure_category_of(exc),
                blame="user" if isinstance(exc, UserError) else None,
                file_data=request_dict.get("file_data", None),
            )
        except Exception as invoke_error:
            logger.error(f"failed to invoke plugin: {_safe_str(invoke_error)}", exc_info=True)
            return InvokeResponse(
                usage=usage,
                message_channels=message_channels,
                filedata_meta=filedata_meta_model.model_validate(filedata_meta.model_dump()),
                status_code=status_code_of(invoke_error),
                status_code_text=f"[{type(invoke_error).__name__}] {_safe_str(invoke_error)}",
                failure_category=failure_category_of(invoke_error),
                file_data=request_dict.get("file_data", None),
            )

    async def run_job_with_body(request: BaseModel) -> ResponseType:
        log_func_and_body(func=func, body=request.json())
        # Create dictionary from pydantic model while preserving underlying types
        request_dict = {f: getattr(request, f) for f in request.model_fields}
        # Make sure nested classes get instantiated correctly. `file_data` can legitimately be None
        # -- a plugin may declare it optional, and then an absent or partial body leaves it unset --
        # so convert only a real value. Calling `.model_dump()` on None would raise before `wrap_fn`
        # runs, turning the optional-body contract into a 500.
        file_data = request_dict.get("file_data")
        if file_data is not None:
            request_dict["file_data"] = file_data_from_dict(file_data.model_dump())
        map_inputs(func=func, raw_inputs=request_dict)
        if logger.level == LOG_LEVELS.get("trace", logging.NOTSET):
            logger.log(level=logger.level, msg=f"passing inputs to function: {request_dict}")
        return await wrap_fn(func=func, kwargs=request_dict)

    # A pydantic body parameter with no default is mandatory even when every field inside the model
    # is optional. So a plugin whose parameters are ALL optional would demand a body that no caller
    # has a reason to populate -- and before it grew those parameters that same plugin accepted no
    # body at all, so adding one flips the HTTP contract while looking backward-compatible. Default
    # the body in that case: an absent body resolves each field to its own default, which is exactly
    # what the function signature already promises.
    #
    # A plugin with at least one required field keeps a mandatory body, so an indexer that needs
    # `file_data` still fails validation rather than silently receiving None.
    body_is_optional = input_schema_model.model_fields and not any(
        field.is_required() for field in input_schema_model.model_fields.values()
    )

    if body_is_optional:

        @fastapi_app.post("/invoke", response_model=InvokeResponse)
        async def run_job(request: Optional[input_schema_model] = None) -> ResponseType:
            return await run_job_with_body(request if request is not None else input_schema_model())

    elif input_schema_model.model_fields:

        @fastapi_app.post("/invoke", response_model=InvokeResponse)
        async def run_job(request: input_schema_model) -> ResponseType:
            return await run_job_with_body(request)

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
        failure_category: Optional[str] = None

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
                failure_category=fn_response.failure_category,
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

    # The route dependency handles the reserved /invoke fields (invocation_settings and
    # invocation_context) outside the generated handler schema. It resolves sealed settings with
    # the configured private key and exposes both values through request-scoped accessors.
    # The sealed-settings capability remains opt-in because it asserts that the wrapped function
    # consumes current_invocation_settings(), not merely that the host can resolve it. The binding
    # dependency was installed before route registration; the last /metadata registration wins.
    add_metadata_route(
        fastapi_app,
        identifier=plugin_id,
        invoke_with_sealed_dag_node_settings=invoke_with_sealed_dag_node_settings,
    )

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
    invoke_with_sealed_dag_node_settings: bool = False,
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

    return wrap_in_fastapi(
        func=func,
        plugin_id=plugin_id,
        precheck_func=precheck_func,
        invoke_with_sealed_dag_node_settings=invoke_with_sealed_dag_node_settings,
    )
