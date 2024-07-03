import sys
from typing import ForwardRef, _allowed_types, _eval_type, _strip_annotations, types

"""
python3.10 behavior breaks python3.12 behavior, injecting Optional[] into the type
if the field has a default value set. Below is the 3.12 behavior, pulling the same logic in when
3.10 is used.
"""


def get_type_hints(obj, globalns=None, localns=None, include_extras=False):
    """Return type hints for an object.

    This is often the same as obj.__annotations__, but it handles
    forward references encoded as string literals and recursively replaces all
    'Annotated[T, ...]' with 'T' (unless 'include_extras=True').

    The argument may be a module, class, method, or function. The annotations
    are returned as a dictionary. For classes, annotations include also
    inherited members.

    TypeError is raised if the argument is not of a type that can contain
    annotations, and an empty dictionary is returned if no annotations are
    present.

    BEWARE -- the behavior of globalns and localns is counterintuitive
    (unless you are familiar with how eval() and exec() work).  The
    search order is locals first, then globals.

    - If no dict arguments are passed, an attempt is made to use the
      globals from obj (or the respective module's globals for classes),
      and these are also used as the locals.  If the object does not appear
      to have globals, an empty dictionary is used.  For classes, the search
      order is globals first then locals.

    - If one dict argument is passed, it is used for both globals and
      locals.

    - If two dict arguments are passed, they specify globals and
      locals, respectively.
    """
    if getattr(obj, "__no_type_check__", None):
        return {}
    # Classes require a special treatment.
    if isinstance(obj, type):
        hints = {}
        for base in reversed(obj.__mro__):
            if globalns is None:
                base_globals = getattr(sys.modules.get(base.__module__, None), "__dict__", {})
            else:
                base_globals = globalns
            ann = base.__dict__.get("__annotations__", {})
            if isinstance(ann, types.GetSetDescriptorType):
                ann = {}
            base_locals = dict(vars(base)) if localns is None else localns
            if localns is None and globalns is None:
                # This is surprising, but required.  Before Python 3.10,
                # get_type_hints only evaluated the globalns of
                # a class.  To maintain backwards compatibility, we reverse
                # the globalns and localns order so that eval() looks into
                # *base_globals* first rather than *base_locals*.
                # This only affects ForwardRefs.
                base_globals, base_locals = base_locals, base_globals
            for name, value in ann.items():
                if value is None:
                    value = type(None)
                if isinstance(value, str):
                    value = ForwardRef(value, is_argument=False, is_class=True)
                value = _eval_type(value, base_globals, base_locals)
                hints[name] = value
        return hints if include_extras else {k: _strip_annotations(t) for k, t in hints.items()}

    if globalns is None:
        if isinstance(obj, types.ModuleType):
            globalns = obj.__dict__
        else:
            nsobj = obj
            # Find globalns for the unwrapped object.
            while hasattr(nsobj, "__wrapped__"):
                nsobj = nsobj.__wrapped__
            globalns = getattr(nsobj, "__globals__", {})
        if localns is None:
            localns = globalns
    elif localns is None:
        localns = globalns
    hints = getattr(obj, "__annotations__", None)
    if hints is None:
        # Return empty annotations for something that _could_ have them.
        if isinstance(obj, _allowed_types):
            return {}
        else:
            raise TypeError(f"{obj!r} is not a module, class, method, " "or function.")
    hints = dict(hints)
    for name, value in hints.items():
        if value is None:
            value = type(None)
        if isinstance(value, str):
            # class-level forward refs were handled above, this must be either
            # a module-level annotation or a function argument annotation
            value = ForwardRef(
                value,
                is_argument=not isinstance(obj, types.ModuleType),
                is_class=False,
            )
        hints[name] = _eval_type(value, globalns, localns)
    return hints if include_extras else {k: _strip_annotations(t) for k, t in hints.items()}
