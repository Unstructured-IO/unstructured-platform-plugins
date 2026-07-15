"""Per-invocation context for first-class /invoke envelope fields.

``invocation_settings`` is a reserved, always-accepted field of every generated
``/invoke`` request. Functions that declare an ``invocation_settings`` parameter
receive it as a kwarg; all other code (including plugins with hand-rolled apps
that adopt the same contract) can read it for the duration of the call via
:func:`get_invocation_settings`.
"""

from contextvars import ContextVar
from typing import Any, Optional

_invocation_settings_var: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "invocation_settings", default=None
)


def get_invocation_settings() -> Optional[dict[str, Any]]:
    """The invocation_settings of the in-flight /invoke call, if any."""
    return _invocation_settings_var.get()
