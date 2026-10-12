"""What runs INSIDE an egress-redaction child (#552). See `app/ai/isolation.py`.

Importing this module has no side effect: the parent imports it to hand
`child_main` to the child by reference. The scrub runs only when called, first
thing in the child, and once in the forkserver (`_redaction_forkserver`).
"""

from __future__ import annotations

import importlib
import math
import os
import signal
import sys
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


def limit_cpu(budget: float) -> None:
    """A CPU-time limit of the budget, rounded up, plus one second: a child the
    parent can no longer kill (the api died hard) still stops. The parent's
    wall-clock kill is the bound in normal running; this one needs no parent."""
    import resource

    seconds = math.ceil(budget) + 1
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))


def die_with_parent() -> None:
    """SIGKILL this child when its parent dies (`PR_SET_PDEATHSIG`). The parent
    is the forkserver, which exits as soon as the api process is gone, so a
    child never outlives the api by more than that. Linux only, where the api
    runs; on Linux, a prctl that cannot be called or fails is an error, never a
    child running unbounded."""
    if not sys.platform.startswith("linux"):
        return
    import ctypes

    parent = os.getppid()
    libc = ctypes.CDLL(None, use_errno=True)
    pr_set_pdeathsig = 1
    if libc.prctl(pr_set_pdeathsig, signal.SIGKILL, 0, 0, 0) != 0:
        err = ctypes.get_errno()
        raise OSError(err, f"prctl(PR_SET_PDEATHSIG) failed: {os.strerror(err)}")
    if os.getppid() != parent:
        # The parent died before the signal was armed: nobody will send it.
        os._exit(1)


def let_the_forkserver_go() -> None:
    """Close this child's copy of the api's "alive" pipe. Every forkserver
    client holds its write end, children included (`multiprocessing.forkserver`
    `_serve_one`), and the forkserver exits only when the last copy closes. A
    child holding one keeps the forkserver alive after the api dies, so
    `die_with_parent` would never fire. This child starts no processes, so it
    has no use for it. Missing is an error: a later Python that moved it would
    otherwise leave that path open in silence."""
    from multiprocessing import forkserver

    fd = forkserver._forkserver._forkserver_alive_fd
    if fd is None:
        raise RuntimeError("redaction child: no forkserver alive fd to close")
    os.close(fd)
    forkserver._forkserver._forkserver_alive_fd = None


def child_main(
    conn: Any,
    target: tuple[str, str],
    payload: Any,
    mode: str,
    client_org_name: str | None,
    name_hints: tuple[str, ...],
    redactor_file: str,
    budget: float,
) -> None:
    """Scrub, bound this child's CPU and tie it to its parent's life (both
    before any work), check it loaded the api's own redactor file, run `target`
    (a (module, name) pair) and send back exactly one answer: ("ok", result),
    ("http", (status, detail)) for a typed refusal, or
    ("error", text). An answer never lost to an exception: whatever fails is
    sent as an error, and a child that cannot send dies, which the parent
    reads as a crash."""
    from starlette.exceptions import HTTPException

    scrub_environment()
    try:
        limit_cpu(budget)
        die_with_parent()
        let_the_forkserver_go()
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
