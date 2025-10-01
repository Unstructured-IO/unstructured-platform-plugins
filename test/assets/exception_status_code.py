"""Test assets for testing exception handling with various status_code scenarios."""

from fastapi import HTTPException
from unstructured_ingest.error import UnstructuredIngestError
from unstructured_ingest.errors_v2 import UnstructuredIngestError as UnstructuredIngestErrorV2


class ExceptionWithNoneStatusCode(Exception):
    """Exception that has status_code attribute set to None."""

    def __init__(self, message: str):
        super().__init__(message)
        self.status_code = None


class ExceptionWithValidStatusCode(Exception):
    """Exception that has status_code attribute set to a valid integer."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


class ExceptionWithoutStatusCode(Exception):
    """Exception that has no status_code attribute."""

    def __init__(self, message: str):
        super().__init__(message)


def function_raises_exception_with_none_status_code():
    """Function that raises an exception with status_code=None."""
    raise ExceptionWithNoneStatusCode("Test exception with None status_code")


def function_raises_exception_with_valid_status_code():
    """Function that raises an exception with valid status_code."""
    raise ExceptionWithValidStatusCode("Test exception with valid status_code", 422)


def function_raises_exception_without_status_code():
    """Function that raises an exception without status_code attribute."""
    raise ExceptionWithoutStatusCode("Test exception without status_code")


def function_raises_http_exception():
    """Function that raises FastAPI HTTPException."""
    raise HTTPException(status_code=404, detail="Not found")


def function_raises_generic_exception():
    """Function that raises a generic exception."""
    raise ValueError("Generic error")


def function_raises_unstructured_ingest_error_with_status_code():
    """Function that raises UnstructuredIngestError with status_code."""
    error = UnstructuredIngestError("Test UnstructuredIngestError with status_code")
    error.status_code = 400
    raise error


def function_raises_unstructured_ingest_error_without_status_code():
    """Function that raises UnstructuredIngestError without status_code."""
    raise UnstructuredIngestError("Test UnstructuredIngestError without status_code")


def function_raises_unstructured_ingest_error_with_none_status_code():
    """Function that raises UnstructuredIngestError with None status_code."""
    error = UnstructuredIngestError("Test UnstructuredIngestError with None status_code")
    error.status_code = None
    raise error


# Async versions for streaming response tests
async def async_function_raises_exception_with_none_status_code():
    """Async function that raises an exception with status_code=None."""
    raise ExceptionWithNoneStatusCode("Async test exception with None status_code")


async def async_function_raises_exception_with_valid_status_code():
    """Async function that raises an exception with valid status_code."""
    raise ExceptionWithValidStatusCode("Async test exception with valid status_code", 422)


async def async_function_raises_exception_without_status_code():
    """Async function that raises an exception without status_code attribute."""
    raise ExceptionWithoutStatusCode("Async test exception without status_code")


async def async_function_raises_unstructured_ingest_error():
    """Async function that raises UnstructuredIngestError."""
    error = UnstructuredIngestError("Async test UnstructuredIngestError")
    error.status_code = 503
    raise error


# Async generator versions for streaming response error tests
async def async_gen_function_raises_exception_with_none_status_code():
    """Async generator that raises an exception with status_code=None."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    raise ExceptionWithNoneStatusCode("Async gen test exception with None status_code")


async def async_gen_function_raises_exception_with_valid_status_code():
    """Async generator that raises an exception with valid status_code."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    raise ExceptionWithValidStatusCode("Async gen test exception with valid status_code", 422)


async def async_gen_function_raises_exception_without_status_code():
    """Async generator that raises an exception without status_code attribute."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    raise ExceptionWithoutStatusCode("Async gen test exception without status_code")


async def async_gen_function_raises_unstructured_ingest_error():
    """Async generator that raises UnstructuredIngestError."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    error = UnstructuredIngestError("Async gen test UnstructuredIngestError")
    error.status_code = 502
    raise error


async def async_gen_function_raises_unstructured_ingest_error_with_none_status_code():
    """Async generator that raises UnstructuredIngestError with None status_code."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    error = UnstructuredIngestError("Async gen test UnstructuredIngestError with None status_code")
    error.status_code = None
    raise error


# V2 Error Functions - using UnstructuredIngestErrorV2
def function_raises_unstructured_ingest_error_v2_with_status_code():
    """Function that raises UnstructuredIngestErrorV2 with status_code."""
    error = UnstructuredIngestErrorV2("Test UnstructuredIngestErrorV2 with status_code")
    error.status_code = 400
    raise error


def function_raises_unstructured_ingest_error_v2_without_status_code():
    """Function that raises UnstructuredIngestErrorV2 without status_code."""
    raise UnstructuredIngestErrorV2("Test UnstructuredIngestErrorV2 without status_code")


def function_raises_unstructured_ingest_error_v2_with_none_status_code():
    """Function that raises UnstructuredIngestErrorV2 with None status_code."""
    error = UnstructuredIngestErrorV2("Test UnstructuredIngestErrorV2 with None status_code")
    error.status_code = None
    raise error


async def async_function_raises_unstructured_ingest_error_v2():
    """Async function that raises UnstructuredIngestErrorV2."""
    error = UnstructuredIngestErrorV2("Async test UnstructuredIngestErrorV2")
    error.status_code = 503
    raise error


async def async_gen_function_raises_unstructured_ingest_error_v2():
    """Async generator that raises UnstructuredIngestErrorV2."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    error = UnstructuredIngestErrorV2("Async gen test UnstructuredIngestErrorV2")
    error.status_code = 502
    raise error


async def async_gen_function_raises_unstructured_ingest_error_v2_with_none_status_code():
    """Async generator that raises UnstructuredIngestErrorV2 with None status_code."""
    # Don't yield anything, just raise the exception
    if False:  # This ensures the function is detected as a generator but never yields
        yield None
    error = UnstructuredIngestErrorV2(
        "Async gen test UnstructuredIngestErrorV2 with None status_code"
    )
    error.status_code = None
    raise error
