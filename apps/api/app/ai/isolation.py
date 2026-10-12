"""Egress redaction in a short-lived child process, with a budget (#552).

WHY A CHILD. The redactor's regexes run as long C-level calls that hold the GIL:
measured on 3933a85c (#552), one tenant's crafted display names held it for
~0.3 s per inventory cell, and every other tenant's requests stalled behind it
(`GET /auth/me` up to 3.7 s). A C regex call cannot be interrupted in-process,
so no in-process budget can bound it either. In a child process it holds only
the child's GIL, and the child can be killed by PID.

WHAT THE CHILD GETS: the payload, the mode, the client's name and the hint set.
Nothing else. The forkserver it is forked from is a fresh interpreter started
through `env -i` with only PATH and LANG (`prepare_redaction_executable`), so neither
holds the api's environment: not in `os.environ`, and not in the environment
block the kernel keeps for the process (`/proc/<pid>/environ`), which is what a
deletion from `os.environ` leaves behind. No provider key, no database URL, no
SHIELD_* setting, and none of the api process's memory, in the child's OWN
state. That is not out of its reach: THE CHILD IS NOT A PRIVILEGE BOUNDARY. It
runs as the same user as the api, and measured on the #1042 review (`/proc`
mounted without `hidepid`), a child read the api process's
`/proc/<pid>/environ`, the environment the api was started with, which is where
a provider key given at container start lives. The child keeps the redactor's
work off the api's GIL and bounded; it does not contain a compromised
redactor. Each child also has a
CPU-time limit from the budget and dies with its parent, so it cannot outlive
an api that died hard (`_redaction_child.limit_cpu`, `die_with_parent`).

WHAT HAPPENS WHEN IT GOES WRONG, every outcome typed (D-016) and before egress:

* over the budget (per PAYLOAD, `shield_redaction_budget_seconds`): the child
  is killed by PID and `redaction_budget_exceeded` is raised;
* the child dies without answering: `redaction_failed`;
* the redactor's own typed refusal (`BlankRedactionLiteralError`): its reason
  and message cross the boundary unchanged;
* no place, or no slot in time: `redaction_capacity_busy`.

CONCURRENCY, design (ii) approved in R8 (#736 6096174390):

* `shield_redaction_max_children` child SLOTS (2). Each call waits for one,
  FIFO by ticket, for at most `shield_redaction_slot_wait_seconds` (30).
* `shield_redaction_max_runs` run PLACES (4). A run takes ONE place at its first
  redaction and keeps it until the run ends: a Run-AI is keyed by
  `ai_run_id_var` (which `run_batches` copies into every batch), Risk generate
  by `redaction_scope()`, and a call outside both (the preview, the what-if
  parse, the CLI scripts) is a one-call run. A run arriving with every place
  taken is refused at once.
* A run refused over its budget, for a child that died, or for want of a place
  or a slot is refused whole: every later call of it is refused too, and none
  of its payloads clears after the refusal, so the refusal can say exactly
  whether anything was sent. The redactor's own typed refusal is NOT recorded
  on the place: it is raised as it came, and a later call of the same run is
  not refused by it. That is unreachable today (`BlankRedactionLiteralError`'s
  docstring in `app/ai/redact.py`: no current caller hands the redactor a blank
  needle); if it becomes reachable, record it on the place like the others.
* The place is released when the run ends, on every path (`release_run`, called
  from the run framework's `finally` and from the reaper), and an ended run is
  never admitted again. A call of it still redacting when it ends is refused
  when its child answers (`_end_place`): nothing clears for a run already over.

ONE PROCESS. The places and slots are this process's. That is the reaper's
precondition already (`app/ai/runs.py`); a multi-worker deploy would multiply
them by the number of workers.
"""

from __future__ import annotations

import collections
import contextlib
import multiprocessing
import os
import shlex
import shutil
import signal

# One fixed probe of this module's own wrapper (`_probe_wrapper`).
import subprocess  # nosec B404
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable, Hashable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, status

from app.ai import redact as redact_module
from app.ai._redaction_child import child_main
from app.ai.redact import RedactionMode, redact_payload
from app.ai.run_context import ai_run_id_var
from app.config import get_settings
from app.logging import get_logger

_log = get_logger(__name__)

REDACTION_BUDGET_EXCEEDED = "redaction_budget_exceeded"
REDACTION_FAILED = "redaction_failed"
REDACTION_CAPACITY_BUSY = "redaction_capacity_busy"

#: The function the child runs, with `redact_payload`'s signature. Handed to the
#: child as a (module, name) pair and imported THERE, so the child always runs
#: the module's own function, never a parent-side patch of it. Tests swap this
#: for a stand-in (`tests/_isolation_targets.py`).
_TARGET: Callable[..., tuple[Any, dict[str, int]]] = redact_payload

#: The module the forkserver imports before it forks anything: it preloads the
#: redactor and scrubs `os.environ` again (the forkserver already starts with an
#: allowlisted environment, below). NEVER imported here -- in this process it
#: would scrub the api's own environment (it refuses to).
_FORKSERVER_PRELOAD = "app.ai._redaction_forkserver"

_ctx = multiprocessing.get_context("forkserver")
_ctx.set_forkserver_preload([_FORKSERVER_PRELOAD])

#: The forkserver's ENTIRE environment. It is started through `env -i` with
#: these and nothing else, so neither it nor any child it forks ever holds the
#: api's environment, in `os.environ` or in the environment block the kernel
#: keeps (`/proc/<pid>/environ`). Deleting from `os.environ` alone leaves the
#: original strings in that block, and a forked child inherits it: measured on
#: the #1042 review, a child's block held the provider key, the database URL
#: and every SHIELD_* setting after the scrub.
_CHILD_ENVIRONMENT = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8"}
_executable_lock = threading.Lock()
#: The wrapper the forkserver context currently execs, or None before the first.
_wrapper_path: str | None = None
#: The wrapper's mode. Owner-only: it is this process's way into a clean child.
_WRAPPER_MODE = 0o700
#: The probe the wrapper must pass before it is used: the interpreter starts,
#: and its environment is exactly the allowlist.
_ALLOWED_NAMES = ", ".join(repr(k) for k in sorted(_CHILD_ENVIRONMENT))
_PROBE = f"import os, sys; sys.exit(0 if set(os.environ) <= {{{_ALLOWED_NAMES}}} else 3)"
_PROBE_SECONDS = 30.0


class RedactionSetupError(RuntimeError):
    """The clean-environment wrapper cannot be made or cannot run. The message
    names the cause; every redaction fails closed until it is fixed."""


def prepare_redaction_executable() -> str:
    """The wrapper that execs this interpreter under `env -i`, written, PROBED
    and set as the forkserver context's executable. Called at api startup (so a
    host that cannot run it refuses to start, naming why) and before every
    child (so a wrapper a temp cleaner deleted is made again before the next
    forkserver start needs it). `multiprocessing` starts the forkserver with
    `spawn.get_executable()`, and it reports no exec failure of its own (Python
    3.12's `spawnv_passfds`), so the probe is what finds one. Nothing else in
    the api uses `multiprocessing`. Never falls back to the api's environment."""
    global _wrapper_path
    with _executable_lock:
        if _wrapper_path is not None and os.path.isfile(_wrapper_path):
            return _wrapper_path
        replacing = _wrapper_path
        wrapper = _write_wrapper()
        _probe_wrapper(wrapper)
        _ctx.set_executable(wrapper)
        _wrapper_path = wrapper
    _log.info("redaction_isolation.forkserver_executable", wrapper=wrapper, replaced=replacing)
    return wrapper


def _write_wrapper() -> str:
    env = shutil.which("env")
    if env is None:
        raise RedactionSetupError(
            "redaction isolation: no `env` executable on PATH, so the redaction "
            "forkserver cannot be started with a clean environment"
        )
    assignments = " ".join(f"{k}={shlex.quote(v)}" for k, v in sorted(_CHILD_ENVIRONMENT.items()))
    try:
        wrapper = os.path.join(tempfile.mkdtemp(prefix="shield-redaction-"), "python")
        with open(wrapper, "w", encoding="ascii") as f:
            f.write(
                "#!/bin/sh\n"
                f'exec {shlex.quote(env)} -i {assignments} {shlex.quote(sys.executable)} "$@"\n'
            )
        os.chmod(wrapper, _WRAPPER_MODE)
    except OSError as exc:
        raise RedactionSetupError(
            f"redaction isolation: cannot write the forkserver wrapper under "
            f"{tempfile.gettempdir()} (is the temp directory writable?): {exc}"
        ) from exc
    return wrapper


def _probe_wrapper(wrapper: str) -> None:
    try:
        # Our own wrapper, a fixed `-c` probe, no shell.
        done = subprocess.run(  # noqa: S603  # nosec B603
            [wrapper, "-c", _PROBE], capture_output=True, timeout=_PROBE_SECONDS, check=False
        )
    except PermissionError as exc:
        raise RedactionSetupError(
            f"redaction isolation: cannot execute the forkserver wrapper {wrapper} "
            f"(is {os.path.dirname(os.path.dirname(wrapper))} mounted noexec?): {exc}"
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RedactionSetupError(
            f"redaction isolation: the forkserver wrapper {wrapper} did not run: {exc}"
        ) from exc
    if done.returncode != 0:
        raise RedactionSetupError(
            f"redaction isolation: the forkserver wrapper {wrapper} exited "
            f"{done.returncode}, so it cannot start a clean interpreter: "
            f"{done.stderr.decode(errors='replace').strip()[:300]}"
        )


#: How long to wait for a killed child to be reaped before failing loudly.
_KILL_JOIN_SECONDS = 10.0

#: How many ended runs are remembered, so a straggling call of a run that has
#: already ended is refused rather than admitted to a place nobody will release.
#: Stragglers arrive within seconds of the end; this is thousands of runs.
_ENDED_MEMORY = 4096


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------


def limit_text(seconds: float) -> str:
    """`30` for 30.0, `0.5` for 0.5: the {N} in the approved sentences."""
    return f"{seconds:g}"


def budget_message(budget: float, *, sent_before: bool) -> str:
    """The neutral budget sentence (#736 6094274195), or the part-way one when
    this run had already sent a payload (drafted for #552, held for a ruling)."""
    if sent_before:
        return (
            "Checking a payload in this run for people's names took longer than the "
            f"{limit_text(budget)}-second limit, so the run was stopped part-way. Nothing "
            "from it was applied."
        )
    return (
        "Checking this payload for people's names took longer than the "
        f"{limit_text(budget)}-second limit, so the check was stopped and nothing was "
        "sent to the AI provider."
    )


def busy_message(*, sent_before: bool) -> str:
    """The busy sentence (#736 6094362713), or its part-way form."""
    if sent_before:
        return (
            "The check for people's names is busy with other AI work, so this run was "
            "stopped part-way. Nothing from it was applied."
        )
    return (
        "The check for people's names is busy with other AI work, so this was "
        "stopped and nothing was sent to the AI provider. Try again in a minute."
    )


def failed_message(*, sent_before: bool) -> str:
    """A child that died without answering (drafted for #552, held for a ruling)."""
    if sent_before:
        return (
            "The check for people's names stopped unexpectedly, so this run was "
            "stopped part-way. Nothing from it was applied."
        )
    return (
        "The check for people's names stopped unexpectedly, so nothing was sent "
        "to the AI provider."
    )


class RedactionRefused(HTTPException):
    """A redaction this module refused, typed (D-016). Raised before egress.

    `sent_before` says whether the SAME run had already cleared a payload for
    sending when it was refused: False is what lets a run record "not charged"
    and say "nothing was sent". The run framework and the batch runner key on
    this class to fail a run whole rather than count a failed batch."""

    def __init__(self, reason: str, message: str, *, status_code: int, sent_before: bool) -> None:
        super().__init__(status_code=status_code, detail={"reason": reason, "message": message})
        self.reason = reason
        self.message = message
        self.sent_before = sent_before

    def with_message(self, message: str) -> RedactionRefused:
        """The same refusal in a service's own words (Tech Debt's sentence)."""
        return RedactionRefused(
            self.reason, message, status_code=self.status_code, sent_before=self.sent_before
        )

    def again(self) -> RedactionRefused:
        """A fresh copy to raise: a run's stored refusal is raised in every one
        of its batch threads, and one exception object raised in several
        threads would carry their tracebacks tangled together."""
        return self.with_message(self.message)


# ---------------------------------------------------------------------------
# Slots: FIFO by ticket
# ---------------------------------------------------------------------------


class FifoSlots:
    """`n` slots handed out strictly in arrival order.

    `threading.BoundedSemaphore` is not FIFO: measured on #736 (6095152284),
    later arrivals were served while earlier waiters timed out."""

    def __init__(self, n: int) -> None:
        self.capacity = n
        self._free = n
        self._queue: collections.deque[dict[str, Any]] = collections.deque()
        self._lock = threading.Lock()

    def wait(self, timeout: float) -> bool:
        """A slot within `timeout` seconds, in turn, or False."""
        ticket: dict[str, Any] = {"event": threading.Event(), "granted": False}
        with self._lock:
            if self._free > 0 and not self._queue:
                self._free -= 1
                return True
            self._queue.append(ticket)
        ticket["event"].wait(timeout)
        with self._lock:
            if ticket["granted"]:
                return True
            self._queue.remove(ticket)
            return False

    def release(self) -> None:
        with self._lock:
            if self._queue:
                ticket = self._queue.popleft()
                ticket["granted"] = True
                ticket["event"].set()
            elif self._free < self.capacity:
                self._free += 1
            else:
                raise RuntimeError("redaction slots: released more slots than were taken")

    def in_use(self) -> int:
        with self._lock:
            return self.capacity - self._free

    def waiting(self) -> int:
        with self._lock:
            return len(self._queue)


# ---------------------------------------------------------------------------
# Places: one per run
# ---------------------------------------------------------------------------


class _Place:
    """A run's place: how many of its payloads have cleared for sending, and
    the refusal that ended it, if one did."""

    __slots__ = ("cleared", "refused")

    def __init__(self) -> None:
        self.cleared = 0
        self.refused: RedactionRefused | None = None


_lock = threading.Lock()
_places: dict[Hashable, _Place] = {}
#: Runs refused at ARRIVAL hold no place, but are remembered until they end so
#: their sibling batches are refused too.
_refused_unplaced: dict[Hashable, RedactionRefused] = {}
_ended: collections.OrderedDict[Hashable, None] = collections.OrderedDict()
_slots: list[FifoSlots] = []

#: Risk generate's key, set by `redaction_scope()`. A Run-AI's key is its run id.
_scope_var: ContextVar[uuid.UUID | None] = ContextVar("redaction_scope", default=None)


def _run_key() -> Hashable | None:
    run_id = ai_run_id_var.get()
    if run_id is not None:
        return ("run", run_id)
    scope = _scope_var.get()
    if scope is not None:
        return ("scope", scope)
    return None


def _slots_for(max_children: int) -> FifoSlots:
    """The slots, rebuilt only while idle when the setting changed (tests do;
    production reads it once). Busy and changed is a loud error, not a guess."""
    with _lock:
        if _slots and _slots[0].capacity == max_children:
            return _slots[0]
        if _slots and (_slots[0].in_use() or _slots[0].waiting() or _places):
            raise RuntimeError(
                f"redaction slots: the setting changed to {max_children} while "
                f"{_slots[0].in_use()} slots were in use"
            )
        _slots[:] = [FifoSlots(max_children)]
        return _slots[0]


def places_in_use() -> int:
    with _lock:
        return len(_places)


def slots_in_use() -> int:
    with _lock:
        return _slots[0].in_use() if _slots else 0


def release_run(run_id: uuid.UUID) -> None:
    """Give back a Run-AI's place. Called from the run framework's `finally`
    and from the reaper; idempotent, and a no-op for a run that never took one."""
    _release(("run", run_id))


def _release(key: Hashable) -> None:
    with _lock:
        place = _places.pop(key, None)
        if place is not None:
            _end_place(place)
        _refused_unplaced.pop(key, None)
        if key[0] != "call":
            # A one-call run has no stragglers to refuse, and recording it
            # would push a real run's key out of this bounded memory, after
            # which that run's straggler is admitted to a place nobody frees.
            _ended[key] = None
            while len(_ended) > _ENDED_MEMORY:
                _ended.popitem(last=False)
    if place is not None:
        _log.info("redaction_isolation.place_released", run=str(key[1]), cleared=place.cleared)


def _end_place(place: _Place) -> None:
    """Refuse whatever of this run is still redacting, under `_lock`. A batch
    whose child answers after its run ended (reaped, or failed on another
    batch) must not clear and egress for a run already recorded as over: the
    answer is refused like any call of an ended run (`_admit`)."""
    if place.refused is None:
        place.refused = RedactionRefused(
            REDACTION_CAPACITY_BUSY,
            busy_message(sent_before=True),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            sent_before=True,
        )


@contextmanager
def redaction_scope() -> Iterator[None]:
    """One place for everything redacted inside the block, for a fan-out that
    is not a Run-AI and so carries no run id: Risk generate, and `run_batches`
    called directly (the CLI measure script). Without it each concurrent batch
    would be a one-call run, and five of them would take more than the
    platform's places and refuse each other. A NO-OP when the caller already
    has a run key (a Run-AI, or an enclosing scope): the run keeps its place.
    The place is released when the block exits, however it exits; a straggling
    call after that is refused, never placed."""
    if _run_key() is not None:
        yield
        return
    scope = uuid.uuid4()
    token = _scope_var.set(scope)
    try:
        yield
    finally:
        _scope_var.reset(token)
        _release(("scope", scope))


def _refuse(
    key: Hashable, place: _Place | None, reason: str, message_of: Callable[[bool], str], code: int
) -> RedactionRefused:
    """Record a refusal for this run, under the lock the caller holds. The FIRST
    refusal ends the run; a later one is that same refusal again, so every call
    of the run says the same thing."""
    if place is not None and place.refused is not None:
        return place.refused.again()
    if place is None and key in _refused_unplaced:
        return _refused_unplaced[key].again()
    sent_before = place is not None and place.cleared > 0
    refused = RedactionRefused(
        reason, message_of(sent_before), status_code=code, sent_before=sent_before
    )
    if place is not None:
        place.refused = refused
    elif key[0] != "call":
        _refused_unplaced[key] = refused
    _log.warning(
        "redaction_isolation.refused",
        reason=reason,
        run=str(key[1]),
        sent_before=sent_before,
        places_in_use=len(_places),
    )
    return refused


def _admit(key: Hashable, max_runs: int) -> _Place:
    """This run's place, taken now if it has none. Refuses a run that has
    ended or been refused, and a new run when every place is taken."""
    busy = status.HTTP_503_SERVICE_UNAVAILABLE
    with _lock:
        place = _places.get(key)
        if place is not None:
            if place.refused is not None:
                raise place.refused.again()
            return place
        if key in _refused_unplaced:
            raise _refused_unplaced[key].again()
        if key in _ended:
            # A straggling call of a run that has ended. Refused, never placed:
            # nobody would release a place taken now. Not recorded either, and
            # "sent before" is assumed, since the run's count is gone.
            _log.warning("redaction_isolation.refused_ended_run", run=str(key[1]))
            raise RedactionRefused(
                REDACTION_CAPACITY_BUSY,
                busy_message(sent_before=True),
                status_code=busy,
                sent_before=True,
            )
        if len(_places) >= max_runs:
            raise _refuse(
                key, None, REDACTION_CAPACITY_BUSY, lambda s: busy_message(sent_before=s), busy
            )
        place = _Place()
        _places[key] = place
        _log.info("redaction_isolation.place_taken", run=str(key[1]), places_in_use=len(_places))
        return place


# ---------------------------------------------------------------------------
# The child
# ---------------------------------------------------------------------------


def _target_ref() -> tuple[str, str]:
    return _TARGET.__module__, _TARGET.__qualname__


def _redactor_file() -> str:
    """The redactor file THIS process runs. Handed to the child, which refuses
    to run if it loaded another: Python 3.12's forkserver ignores the parent's
    sys.path (`multiprocessing.forkserver.main` takes it and never applies it),
    so a forkserver started from another directory, or beside an installed
    copy of `app`, can load another tree's rules. Measured on the #552 build
    harness; see `_redaction_child.child_main`."""
    return os.path.realpath(redact_module.__file__)


def _run_child(
    target: tuple[str, str],
    payload: Any,
    mode: RedactionMode,
    client_org_name: str | None,
    name_hints: tuple[str, ...],
    budget: float,
) -> tuple[str, Any]:
    """Run the target in a fresh forkserver child. Returns ("ok", result) or
    ("http", (status, detail)), or ("timeout"|"died", detail) for the caller to
    type. The child is gone, reaped, before this returns, whatever happened."""
    prepare_redaction_executable()
    recv, send = _ctx.Pipe(duplex=False)
    child = _ctx.Process(
        target=child_main,
        args=(send, target, payload, mode, client_org_name, name_hints, _redactor_file(), budget),
        daemon=True,
    )
    child.start()
    send.close()
    try:
        if not recv.poll(budget):
            _kill(child)
            return "timeout", child.pid
        try:
            answer = recv.recv()
        except EOFError:
            child.join(_KILL_JOIN_SECONDS)
            if child.exitcode is None:
                # Hung up without exiting: killed by PID, as on the answered path.
                _kill(child)
            return "died", f"child {child.pid} exited {child.exitcode} without answering"
        child.join(_KILL_JOIN_SECONDS)
        if child.exitcode is None:
            _kill(child)
        return answer
    finally:
        recv.close()
        if child.exitcode is None:
            # Reached with the child alive only when something above raised
            # (a `recv` error other than end-of-file, say): the docstring's
            # "gone before this returns" holds on that path too.
            _kill(child)


def _kill(child: Any) -> None:
    """SIGKILL by PID, then wait for the forkserver to reap it. A child that is
    still there afterwards is a loud error: it would hold a CPU nobody counts."""
    # Already gone is not an error here: the join below and its exit-code
    # check are what decide whether the child is really over.
    with contextlib.suppress(ProcessLookupError):
        os.kill(child.pid, signal.SIGKILL)
    child.join(_KILL_JOIN_SECONDS)
    if child.exitcode is None:
        raise RuntimeError(f"redaction child {child.pid} survived SIGKILL")
    _log.warning("redaction_isolation.child_killed", pid=child.pid, exitcode=child.exitcode)


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def redact_payload_isolated(
    payload: Any,
    *,
    mode: RedactionMode,
    client_org_name: str | None,
    name_hints: Iterable[str],
) -> tuple[Any, dict[str, int]]:
    """`redact_payload`, computed in a child process under the budget, inside
    this run's place and one child slot. Same inputs, same output (pinned by
    `test_child_output_equals_in_process_output`)."""
    s = get_settings()
    budget = float(s.shield_redaction_budget_seconds)
    slots = _slots_for(int(s.shield_redaction_max_children))
    key = _run_key()
    one_call = key is None
    if key is None:
        key = ("call", uuid.uuid4())
    place = _admit(key, int(s.shield_redaction_max_runs))
    try:
        return _redact_in_place(
            key,
            place,
            slots,
            budget,
            float(s.shield_redaction_slot_wait_seconds),
            payload,
            mode,
            client_org_name,
            tuple(name_hints),
        )
    finally:
        if one_call:
            _release(key)


def _redact_in_place(
    key: Hashable,
    place: _Place,
    slots: FifoSlots,
    budget: float,
    slot_wait: float,
    payload: Any,
    mode: RedactionMode,
    client_org_name: str | None,
    name_hints: tuple[str, ...],
) -> tuple[Any, dict[str, int]]:
    busy = status.HTTP_503_SERVICE_UNAVAILABLE
    if not slots.wait(slot_wait):
        with _lock:
            raise _refuse(
                key, place, REDACTION_CAPACITY_BUSY, lambda s: busy_message(sent_before=s), busy
            )
    try:
        with _lock:
            if place.refused is not None:
                raise place.refused.again()
        try:
            kind, value = _run_child(
                _target_ref(), payload, mode, client_org_name, name_hints, budget
            )
        except Exception as exc:  # noqa: BLE001 - typed below as "died", never swallowed
            # A child that cannot start (fork's OSError, a payload that will not
            # pickle), a pipe error other than end-of-file, a child that
            # survived SIGKILL: nothing trustworthy came back, so it fails
            # closed exactly as a child that died does, refused on the place.
            _log.exception("redaction_isolation.child_call_raised", run=str(key[1]))
            kind, value = "died", f"{type(exc).__name__}: {exc}"
    finally:
        slots.release()
    with _lock:
        if kind == "timeout":
            raise _refuse(
                key,
                place,
                REDACTION_BUDGET_EXCEEDED,
                lambda s: budget_message(budget, sent_before=s),
                busy,
            )
        if kind in ("died", "error"):
            # Died without answering, or raised something other than a typed
            # refusal: either way nothing trustworthy came back. Fail closed.
            _log.error("redaction_isolation.child_failed", run=str(key[1]), kind=kind, detail=value)
            raise _refuse(
                key,
                place,
                REDACTION_FAILED,
                lambda s: failed_message(sent_before=s),
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        if kind == "http":
            status_code, detail = value
            raise HTTPException(status_code=status_code, detail=detail)
        if kind != "ok":
            raise RuntimeError(f"redaction child answered an unknown kind {kind!r}")
        if place.refused is not None:
            # A sibling call was refused while this one ran: this payload is
            # not cleared, so the refusal's "sent before" stays true.
            raise place.refused.again()
        place.cleared += 1
    return value
