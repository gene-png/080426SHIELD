"""What runs INSIDE an egress-redaction child (#552). See `app/ai/isolation.py`.

Importing this module has no side effect: the parent imports it to hand
`child_main` to the child by reference. The scrub runs only when called, first
thing in the child, and once in the forkserver (`_redaction_forkserver`).
"""

from __future__ import annotations

import importlib
import os
from typing import Any

#: The only variables a redaction child keeps. Nothing here names a key, a
#: database or a SHIELD setting; the redactor reads no environment at all.
_KEEP = frozenset({"PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ"})


def scrub_environment() -> None:
    """Drop every environment variable the redactor does not need, in THIS
    process. `os.environ` deletion unsets the C-level variable too."""
    for name in list(os.environ):
        if name not in _KEEP:
            del os.environ[name]


def child_main(
    conn: Any,
    target: tuple[str, str],
    payload: Any,
    mode: str,
    client_org_name: str | None,
    name_hints: tuple[str, ...],
    redactor_file: str,
) -> None:
    """Scrub, check this child loaded the api's own redactor file, run `target`
    (a (module, name) pair) and send back exactly one answer: ("ok", result),
    ("http", (status, detail)) for a typed refusal, or
    ("error", text). An answer never lost to an exception: whatever fails is
    sent as an error, and a child that cannot send dies, which the parent
    reads as a crash."""
    from starlette.exceptions import HTTPException

    scrub_environment()
    try:
        import app.ai.redact

        loaded = os.path.realpath(app.ai.redact.__file__)
        if loaded != redactor_file:
            # Another tree's rules: refuse rather than redact with them.
            raise RuntimeError(f"redactor is {loaded}, the api runs {redactor_file}")
        module_name, qualname = target
        fn = importlib.import_module(module_name)
        for part in qualname.split("."):
            fn = getattr(fn, part)
        result = fn(payload, mode=mode, client_org_name=client_org_name, name_hints=name_hints)
        conn.send(("ok", result))
    except HTTPException as exc:
        conn.send(("http", (exc.status_code, exc.detail)))
    except BaseException as exc:  # noqa: BLE001 - sent to the parent, which fails closed
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()
