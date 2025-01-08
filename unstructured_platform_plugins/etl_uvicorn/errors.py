from abc import ABC
from typing import Any, Optional

import unstructured_ingest.v2.errors as ingest_errors
from fastapi import HTTPException


class BaseError(HTTPException, ABC):
    status_code: int

    def __init__(self, detail: Any, headers: Optional[dict[str, str]] = None):
        super().__init__(status_code=self.status_code, detail=detail, headers=headers)


class UserError(BaseError):
    status_code: int = 400


class UserAuthError(UserError):
    status_code: int = 403


class RateLimitError(UserError):
    status_code: int = 429


class QuotaError(UserError):
    status_code: int = 402


class ProviderError(BaseError):
    status_code: int = 500


class CatchAllError(BaseError):
    status_code: int = 512


def wrap_error(e: Exception) -> HTTPException:
    if isinstance(e, ingest_errors.UserAuthError):
        return UserAuthError(e)
    elif isinstance(e, ingest_errors.RateLimitError):
        return RateLimitError(e)
    elif isinstance(e, ingest_errors.QuotaError):
        return QuotaError(e)
    elif isinstance(e, ingest_errors.UserError):
        return UserError(e)
    elif isinstance(e, ingest_errors.ProviderError):
        return ProviderError(e)
    else:
        return CatchAllError(e)
