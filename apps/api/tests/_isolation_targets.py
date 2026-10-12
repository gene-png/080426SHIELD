"""Stand-in child targets for the redaction-isolation tests (#552).

`app.ai.isolation._TARGET` is the function the parent hands to the child
process, pickled BY REFERENCE. A test swaps it for one of these, in the parent,
and the child imports this module to run it. Each has `redact_payload`'s
signature, so the wiring that calls it is the production wiring.

They live in a module, not in a test file, because the child must import them
by name; a function defined inside a test cannot be pickled.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def _pid_file(payload: Any) -> Path | None:
    """The pid file a test planted in the payload, wherever it sits."""
    if isinstance(payload, dict):
        if isinstance(payload.get("__pid_file__"), str):
            return Path(payload["__pid_file__"])
        for value in payload.values():
            found = _pid_file(value)
            if found is not None:
                return found
    if isinstance(payload, list):
        for value in payload:
            found = _pid_file(value)
            if found is not None:
                return found
    return None


def write_pid_then_spin(payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Record this process's PID, then never return.

    A pure-Python spin, not a sleep: a child that slept would be stopped just
    as surely, but the claim under test is that a child doing CPU work is
    stopped, which is what a slow redaction is."""
    pid_file = _pid_file(payload)
    if pid_file is None:
        raise AssertionError("write_pid_then_spin needs a '__pid_file__' in the payload")
    pid_file.write_text(str(os.getpid()))
    x = 0
    while True:
        x += 1


def spin_seconds(payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Hold a slot for `payload['__hold_s__']` seconds of wall time, then
    return the payload unchanged. Used to fill the concurrency cap."""
    end = time.monotonic() + float(payload["__hold_s__"])
    while time.monotonic() < end:
        time.sleep(0.01)
    return payload, {}


def crash(_payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Die the way an OOM kill or a segfault does: no exception, no answer."""
    os._exit(3)


def raise_blank_literal(_payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Raise the redactor's own typed refusal from inside the child."""
    from app.ai.redact import BlankRedactionLiteralError

    raise BlankRedactionLiteralError("   ")


def report_environment(payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Answer with the NAMES of the child's environment variables, never their
    values, in place of every top-level value."""
    names = sorted(os.environ)
    return dict.fromkeys(payload, names), {}


def _control_dir(kwargs: dict[str, Any]) -> Path:
    """The directory a test named as `__ctl__:<dir>`, in the hint set (a tenant
    user's display name, `_redaction_world.control_dir`) or as the client's
    legal name (Risk passes no hints). Those are the channels besides the
    payload that reach the child, and a batched run's payload is built by the
    route, so a test cannot plant a path in it."""
    candidates = [*kwargs.get("name_hints", ()), kwargs.get("client_org_name")]
    for hint in candidates:
        if isinstance(hint, str) and hint.startswith("__ctl__:"):
            return Path(hint.split(":", 1)[1])
    raise AssertionError("this target needs a '__ctl__:<dir>' hint or client name")


def _call_index(ctl: Path) -> int:
    """This call's position among every call that reached a child, decided by
    an exclusive create, so two children can never take the same index."""
    i = 0
    while True:
        try:
            os.close(os.open(ctl / f"call-{i}", os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return i
        except FileExistsError:
            i += 1


def first_real_then_hold(payload: Any, **kwargs: Any) -> tuple[Any, dict[str, int]]:
    """The FIRST call to reach a child redacts for real and is sent; the SECOND
    writes its PID to `<ctl>/holder.pid` and never returns, holding its slot
    until the budget stops it; every later call redacts for real. With one
    child slot, that makes a run which has already sent something meet a
    redaction it cannot get past: the part-way case."""
    from app.ai.redact import redact_payload

    ctl = _control_dir(kwargs)
    index = _call_index(ctl)
    if index == 1:
        (ctl / "holder.pid").write_text(str(os.getpid()))
        x = 0
        while True:
            x += 1
    return redact_payload(payload, **kwargs)


def spin_forever(_payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """CPU work that never ends, for a path whose payload a test cannot plant
    a pid file in (the preview builds its own)."""
    x = 0
    while True:
        x += 1


def write_pid_close_pipe_then_spin(payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Record this process's PID, close every inherited descriptor above
    stderr (the answer pipe among them, so the parent reads end-of-file), then
    never return: a child that hangs up without exiting."""
    pid_file = _pid_file(payload)
    if pid_file is None:
        raise AssertionError("write_pid_close_pipe_then_spin needs a '__pid_file__' in the payload")
    pid_file.write_text(str(os.getpid()))
    os.closerange(3, 65536)
    x = 0
    while True:
        x += 1


def write_pid_wait_for_go_then_redact(payload: Any, **kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Record this process's PID, wait until the test creates `<pid file>.go`,
    then redact for real and answer: a slow child whose answer arrives when
    the test chooses (after its run has ended, say)."""
    from app.ai.redact import redact_payload

    pid_file = _pid_file(payload)
    if pid_file is None:
        raise AssertionError("write_pid_wait_for_go_then_redact needs a '__pid_file__'")
    pid_file.write_text(str(os.getpid()))
    go = pid_file.with_suffix(".go")
    while not go.exists():
        time.sleep(0.01)
    return redact_payload(payload, **kwargs)


def report_cpu_limit(_payload: Any, **_kwargs: Any) -> tuple[Any, dict[str, int]]:
    """Answer with this child's RLIMIT_CPU (soft, hard), in place of a payload."""
    import resource

    return {"rlimit_cpu": list(resource.getrlimit(resource.RLIMIT_CPU))}, {}
