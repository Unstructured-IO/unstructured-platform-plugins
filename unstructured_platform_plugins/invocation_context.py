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
preserved so a newer producer does not break an older plugin, and every identity field is optional
so a partially-populated context degrades to "less telemetry" rather than a failed invoke. The one
thing it is strict about is ``schema_version`` — that field exists to make an incompatible producer
detectable, which it can only do if somebody actually reads it. The payload is what carries the
version, not the route, so evolving the contract does not mean adding endpoints.
"""

from __future__ import annotations

from typing import Any, Mapping

import pydantic
from utic_invocation_settings import Blame, InvocationSettingsError, MalformedEnvelopeError

# Reserved key carrying the invocation context in the invoke request body.
RESERVED_CONTEXT_KEY = "invocation_context"

# Context payload versions this package understands. Additive keys do not bump this; a change that
# would make an old consumer misread an existing key does.
SUPPORTED_CONTEXT_VERSIONS = frozenset({"1"})

# The identity facets that become telemetry dimensions. Shared rather than per-service policy:
# every hop on one invocation's path has to pick the same fields, or the same request is attributed
# differently depending on which component emitted the event. Excludes the batch fields, which
# describe the work rather than who it belongs to.
DIMENSION_FIELDS = (
    "invocation_id",
    "tenant_id",
    "org_id",
    "job_id",
    "workflow_id",
    "attribution_id",
    "dag_node_id",
    "dag_node_type",
    "dag_node_subtype",
    "record_id",
    "attempt",
)

# Sentinel distinguishing a truly-absent reserved key from one present with a ``None`` value.
_ABSENT = object()


class UnsupportedContextVersionError(InvocationSettingsError):
    """The ``invocation_context`` declares a ``schema_version`` this package does not understand.

    A producer upgrade this consumer cannot follow — deployment skew between platform components,
    not a fault in the request. ``CONTENT`` (a 5xx) rather than ``CALLER``: contexts are produced
    by the platform's own claim pipeline, and a 422 would make an upstream blame classifier pin a
    version-skew failure on the customer. Loud at the first request rather than silently absent
    telemetry dimensions later.
    """

    reason = "unsupported_context_version"
    blame = Blame.CONTENT


class InvocationContext(pydantic.BaseModel):
    """Request-scoped identity delivered alongside one claimed unit of work.

    ``extra="allow"`` keeps forward compatibility: fields added by a newer producer survive round
    trips and stay reachable via ``model_extra`` instead of being silently dropped.
    """

    model_config = pydantic.ConfigDict(extra="allow")

    schema_version: str = "1"

    invocation_id: str | None = None
    job_id: str | None = None
    workflow_id: str | None = None
    attribution_id: str | None = None
    tenant_id: str | None = None
    org_id: str | None = None
    dag_node_id: str | None = None
    dag_node_type: str | None = None
    dag_node_subtype: str | None = None
    record_id: str | None = None
    attempt: int | None = None
    job_created_timestamp: str | None = None

    # Added by the controller on the way to the plugin, not by the work API. The batch pair is
    # index-aligned: entry i of `invocation_ids` is the invocation id of record i, or None where
    # that record carried no context. There is deliberately no `work_dir` field: scratch space is
    # the plugin's implementation detail (tempfile / uuid-named paths), not invoke-contract surface.
    record_ids: list[str] | None = None
    invocation_ids: list[str | None] | None = None

    @pydantic.field_validator("schema_version")
    @classmethod
    def _known_version(cls, value: str) -> str:
        if value not in SUPPORTED_CONTEXT_VERSIONS:
            raise ValueError(
                f"unsupported invocation_context schema_version {value!r}; "
                f"this package understands {sorted(SUPPORTED_CONTEXT_VERSIONS)}"
            )
        return value


def extract_context(payload: Mapping[str, Any]) -> InvocationContext | None:
    """Return the :class:`InvocationContext` from ``payload[RESERVED_CONTEXT_KEY]``.

    Returns ``None`` only when the reserved key is **absent** — the transitional signal that the
    caller is an older controller. A present-but-invalid value fails closed rather than degrading
    to "no context", because a context that silently vanishes takes a pod's tenant attribution with
    it.

    A recognizable context carrying an unknown ``schema_version`` raises
    :class:`UnsupportedContextVersionError` so a producer upgrade is loud at the first request
    instead of showing up later as absent telemetry dimensions.
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
        if any(error["loc"] == ("schema_version",) for error in errors):
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
