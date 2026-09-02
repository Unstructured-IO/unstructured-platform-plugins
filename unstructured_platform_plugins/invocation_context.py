"""The ``invocation_context`` companion to the settings envelope.

Where ``invocation_settings`` carries *what* a plugin should be configured with, the context
carries *who* the invocation is for: the identity facets a shared-tenancy pod can no longer read
from its process environment. It travels in a second reserved, out-of-schema field of the
``/invoke`` body, extracted by the same route dependency that resolves the settings field.

The context is `/invoke` protocol identity, not settings security: it touches no crypto and no
secrets, and it evolves with the plugin protocol this package defines. The errors it raises come
from the shared ``InvocationSettingsError`` taxonomy so hosts classify context failures with the
same ``reason``/``blame`` machinery as settings failures.

The model below is the **consumer** view of that contract, deliberately lenient: unknown keys are
preserved for additive forward compatibility, and every identity field is optional so a
partially-populated context degrades to "less telemetry" rather than a failed invoke. The one thing
it is strict about is ``schema_version`` — that field makes incompatible producer and consumer
contracts detectable. The payload carries the version, so evolving the contract does not require
adding endpoints.
"""

from __future__ import annotations

from typing import Any, Mapping

import pydantic
from utic_invocation_settings import Blame, InvocationSettingsError, MalformedEnvelopeError

from unstructured_platform_plugins.generated.invocation_context_v1 import (
    DIMENSION_FIELDS,
    RESERVED_CONTEXT_KEY,
    SUPPORTED_CONTEXT_VERSIONS,
)
from unstructured_platform_plugins.generated.invocation_context_v1 import (
    InvocationContext as _GeneratedInvocationContext,
)

# Sentinel distinguishing a truly-absent reserved key from one present with a ``None`` value.
_ABSENT = object()


class UnsupportedContextVersionError(InvocationSettingsError):
    """The ``invocation_context`` declares a ``schema_version`` this package does not understand.

    This indicates deployment skew between platform components, not a fault in the request.
    ``CONTENT`` (a 5xx) rather than ``CALLER``: contexts are produced by the platform's own claim
    pipeline, and a 422 would make an upstream blame classifier pin a version-skew failure on the
    customer. Failing the request prevents an unreadable context from silently removing telemetry
    dimensions.
    """

    reason = "unsupported_context_version"
    blame = Blame.CONTENT


class InvocationContext(_GeneratedInvocationContext):
    """Request-scoped identity delivered alongside one claimed unit of work.

    The field shape, version literal, extra-field policy, reserved key, and dimensions are generated
    from the ratified schema. This adapter retains the cross-field invariant JSON Schema cannot
    express.
    """

    @pydantic.model_validator(mode="after")
    def _batch_lists_stay_index_aligned(self) -> "InvocationContext":
        if (
            self.record_ids is not None
            and self.invocation_ids is not None
            and len(self.record_ids) != len(self.invocation_ids)
        ):
            raise ValueError(
                "record_ids and invocation_ids must be the same length: "
                "entry i of invocation_ids describes record i"
            )
        return self

def extract_context(payload: Mapping[str, Any]) -> InvocationContext | None:
    """Return the :class:`InvocationContext` from ``payload[RESERVED_CONTEXT_KEY]``.

    Returns ``None`` only when the producer omitted the reserved key. A present-but-invalid value
    fails closed rather than degrading to "no context", because a context that silently vanishes
    takes a pod's tenant attribution with it.

    A recognizable context carrying an unknown ``schema_version`` raises
    :class:`UnsupportedContextVersionError` so an incompatible contract cannot be mistaken for
    absent context.
    """
    raw = payload.get(RESERVED_CONTEXT_KEY, _ABSENT)
    if raw is _ABSENT:
        return None
    if isinstance(raw, InvocationContext):
        return raw
    try:
        return InvocationContext.model_validate(raw)
    except pydantic.ValidationError as exc:
        errors = exc.errors()
        # Only a well-typed version string this package does not know reads as deployment skew; a
        # schema_version of the wrong type is the caller's malformed context like any other field.
        reported = _reported_version(raw)
        if isinstance(reported, str) and any(
            error["loc"] == ("schema_version",) for error in errors
        ):
            raise UnsupportedContextVersionError(
                f"unsupported invocation_context schema_version: "
                f"{_reported_version(raw)!r}; expected one of {sorted(SUPPORTED_CONTEXT_VERSIONS)}"
            ) from None
        # `from None` so the pydantic error tree does not cross the domain-error boundary; a count
        # plus the first message is enough signal. Mirrors the envelope extraction.
        raise MalformedEnvelopeError(
            f"invalid invocation_context: {exc.error_count()} validation error(s), "
            f"first: {errors[0]['msg']}"
        ) from None


def _reported_version(raw: Any) -> Any:
    """The offending ``schema_version``, for the error message only. Never trusted."""
    return raw.get("schema_version") if isinstance(raw, Mapping) else None


def dimensions(context: InvocationContext | None) -> dict[str, Any]:
    """The context's populated identity facets, ready to bind as telemetry dimensions."""
    if context is None:
        return {}
    return {
        field: value for field in DIMENSION_FIELDS if (value := getattr(context, field)) is not None
    }
