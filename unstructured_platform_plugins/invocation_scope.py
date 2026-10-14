"""Identity and filesystem scope for the current invocation."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, fields
from pathlib import Path
from uuid import uuid4

from unstructured_platform_plugins.invocation_settings import current_invocation_context


@dataclass(frozen=True)
class InvocationIdentity:
    job_id: str | None
    tenant_id: str | None
    org_id: str | None
    workflow_id: str | None
    attribution_id: str | None
    dag_node_id: str | None
    dag_node_type: str | None
    dag_node_subtype: str | None


def current_invocation_identity() -> InvocationIdentity:
    """Read bound identity, falling back to the environment for each absent field."""
    context = current_invocation_context()
    values = {}
    for field in fields(InvocationIdentity):
        value = getattr(context, field.name, None)
        values[field.name] = os.getenv(field.name.upper()) if value is None else value
    return InvocationIdentity(**values)


def _segment(value: str | None) -> str:
    if not value:
        return "unknown"
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", value)
    if safe in {".", ".."} or safe != value or len(safe) > 96:
        digest = hashlib.sha256(value.encode()).hexdigest()[:16]
        safe = f"{safe[:79].strip('.') or 'unknown'}-{digest}"
    return safe


def invocation_scratch_dir(root: str | os.PathLike[str], *, create: bool = True) -> Path:
    """Return an invocation directory, or the unchanged root when no context is bound."""
    path = Path(root)
    context = current_invocation_context()
    if context is not None:
        identity = current_invocation_identity()
        invocation_id = context.invocation_id
        if invocation_id is None and context.record_ids is None and context.invocation_ids is None:
            invocation_id = context.record_id
        path = path / _segment(identity.job_id) / _segment(identity.dag_node_id)
        path = path / _segment(invocation_id or uuid4().hex)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
