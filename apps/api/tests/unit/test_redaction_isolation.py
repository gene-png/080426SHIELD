"""Egress redaction runs in a child process with a budget (for #552).

Measured on 3933a85c (#552, 2026-10-10): one tenant's crafted display names held
the GIL for ~0.3 s per inventory cell, and another tenant's GET /auth/me took up
to 3.7 s. Moving the matcher into a child process removed it. These tests pin
the properties that fix depends on, each through the surface a consultant
reaches (the Tech Debt extract route) wherever a route can reach it:

* the redaction that feeds the provider is NOT computed in the api process;
* a redaction over its budget is stopped, typed, before anything is sent, and
  the child that was doing it no longer exists;
* a child that dies fails closed, typed;
* the redactor's own typed refusals cross the process boundary still typed;
* the child carries no provider key;
* the concurrency cap refuses, typed, rather than queueing without bound.

Budget, parity and the copy split are in `test_redaction_budget.py`; the
per-run places, whole-run refusal and every release path in
`test_redaction_places.py`.

NO WALL-CLOCK ASSERTION ANYWHERE. Every outcome here is decided by state: which
reason the run ended with, whether the provider was called, whether a PID
exists. The one timeout (`post_within`) is a hang guard with a 60 s limit over
work stopped at 0.5 s, so it fails only when the budget is gone.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

import pytest
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.llm_call import LLMCall
from tests import _isolation_targets as targets
from tests import _redaction_world as rw
from tests._redaction_world import _world  # noqa: F401 - the `world` fixture

# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_redacts_in_a_child_process_not_the_api(world, monkeypatch) -> None:
    """The in-process redactor is made to explode. The extraction still
    completes and still sends `[NAME]`, so the redaction that fed the provider
    was computed somewhere else -- the child, which imports the module fresh
    and never sees this patch. Red if the call site goes back in-process.

    Patched under BOTH names: `catalog_fields` no longer imports it, so the
    second patch creates the name (`raising=False`), and a revert that imports
    it again at the call site gets the exploding one rather than the original
    it bound at import."""
    import app.ai.catalog_fields as catalog_fields
    import app.ai.redact as redact

    def _in_process(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("redaction ran in the api process (#552)")

    monkeypatch.setattr(redact, "redact_payload", _in_process)
    monkeypatch.setattr(catalog_fields, "redact_payload", _in_process, raising=False)

    rw.add_tenant_user(world, "dana.whitfield@example.com", "Dana Whitfield")
    svc_id, artifact_id = rw.service_and_artifact(
        world, "Application,Owner\nPayroll VPN,Dana Whitfield\n"
    )
    run = rw.extract(world, svc_id, artifact_id)

    assert run["status"] == "completed", run
    assert len(world["sent"]) == 1, f"provider called {len(world['sent'])} times"
    sent = json.dumps(world["sent"][0])
    assert "[NAME]" in sent, sent
    assert "Dana Whitfield" not in sent, sent
    with world["Session"]() as db:
        row = db.execute(select(LLMCall)).scalar_one()
    assert (row.redacted_counts or {}).get("name", 0) >= 1, row.redacted_counts


# ---------------------------------------------------------------------------
# The child is stopped, and is gone
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_over_budget_is_killed_and_its_pid_is_gone(world, monkeypatch) -> None:
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    pid_file = world["tmp"] / "child.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_budget_exceeded", run
    assert pid_file.is_file(), "the stand-in child never ran, so this proves nothing"
    rw.assert_gone(int(pid_file.read_text()))
    assert world["sent"] == [], "the provider was called after the budget ran out"
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0


# ---------------------------------------------------------------------------
# Crash and exception transport
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_crash_fails_closed_typed(world, monkeypatch) -> None:
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.crash)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_failed", run
    assert "nothing was sent" in (run["error_message"] or ""), run
    assert run["charged_likely"] is False, run
    assert world["sent"] == []
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0


@pytest.mark.unit
def test_redactor_typed_refusal_crosses_the_process_boundary_typed(world, monkeypatch) -> None:
    """`BlankRedactionLiteralError` raised IN THE CHILD reaches the run with its
    own reason. A transport that flattened it to `redaction_failed` or
    `run_crashed` would lose the sentence that says what was wrong."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.raise_blank_literal)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_blank_literal", run
    assert "nothing was sent" in (run["error_message"] or ""), run
    assert world["sent"] == []


# ---------------------------------------------------------------------------
# The child's environment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_environment_carries_no_provider_key(world, monkeypatch) -> None:
    """The child gets the payload and the hints, and nothing it does not need.
    Keys are set in the PARENT here, so a child that inherited the parent's
    environment would carry them."""
    import app.ai.isolation as isolation

    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "sk-test-not-a-real-key")
    monkeypatch.setattr(isolation, "_TARGET", targets.report_environment)

    cleaned, _counts = isolation.redact_payload_isolated(
        {"env": "x"}, mode="strict", client_org_name=None, name_hints=()
    )
    names = cleaned["env"]
    assert isinstance(names, list) and names, f"child reported no environment: {cleaned!r}"
    leaked = [n for n in names if n.upper().endswith("_API_KEY")]
    assert leaked == [], f"the redaction child inherited provider keys: {leaked}"
    assert not [n for n in names if n.upper().startswith("SHIELD_")], names
    assert "DATABASE_URL" not in names, names


# ---------------------------------------------------------------------------
# The concurrency cap: typed refusal, never an unbounded queue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_place_taken_refuses_typed(world, monkeypatch) -> None:
    """One place. While a one-call run holds it (its child is running), a
    second one-call run is refused with `redaction_capacity_busy` -- it neither
    queues nor runs. "Holds" is established by the child's own PID file, not by
    a sleep."""
    import app.ai.isolation as isolation
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_MAX_RUNS", "1")
    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", "5")
    get_settings.cache_clear()
    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)

    pid_file = world["tmp"] / "holder.pid"
    holder_error: dict[str, BaseException] = {}

    def _hold() -> None:
        try:
            isolation.redact_payload_isolated(
                {"__pid_file__": str(pid_file)},
                mode="strict",
                client_org_name=None,
                name_hints=(),
            )
        except BaseException as exc:  # noqa: BLE001 - inspected below
            holder_error["e"] = exc

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    rw.wait_for_file(pid_file)

    with pytest.raises(StarletteHTTPException) as refused:
        isolation.redact_payload_isolated(
            {"x": "y"}, mode="strict", client_org_name=None, name_hints=()
        )
    assert refused.value.detail["reason"] == "redaction_capacity_busy", refused.value.detail
    assert "nothing was sent" in refused.value.detail["message"]

    holder.join(rw.HANG_GUARD_S)
    assert not holder.is_alive()
    assert isinstance(holder_error.get("e"), StarletteHTTPException), holder_error
    assert holder_error["e"].detail["reason"] == "redaction_budget_exceeded"
    rw.assert_gone(int(pid_file.read_text()))


@pytest.mark.unit
def test_a_child_running_a_different_redactor_file_is_refused(world, monkeypatch) -> None:
    """The child must run the SAME redactor file as the api. Python 3.12's
    forkserver ignores the parent's sys.path, so a forkserver started from
    another directory, or beside an installed copy of `app`, can load another
    tree's `app.ai.redact`: older rules, silently. Measured on the #552 build
    harness (a `python -I` uvicorn beside an editable install of another
    worktree). The parent names its own file; a child that loaded a different
    one refuses, typed, and nothing is sent."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_redactor_file", lambda: "/not/the/api/app/ai/redact.py")
    with pytest.raises(StarletteHTTPException) as refused:
        isolation.redact_payload_isolated(
            {"x": "Dana Whitfield"}, mode="strict", client_org_name=None, name_hints=()
        )
    assert refused.value.detail["reason"] == "redaction_failed", refused.value.detail
    assert isolation.places_in_use() == 0


# ---------------------------------------------------------------------------
# Every other way the child call can go wrong is "died": typed, whole-run
# (#1042 review, findings 2 and 5)
# ---------------------------------------------------------------------------


def _assert_failed_closed(world: dict, svc_id: str, run: dict) -> None:
    import app.ai.isolation as isolation

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_failed", run
    assert "nothing was sent" in (run["error_message"] or ""), run
    assert run["charged_likely"] is False, run
    assert world["sent"] == [], "the provider was called after the child call failed"
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0
    assert isolation.places_in_use() == 0


class _ProcessThatCannotStart:
    """`Process` whose `start()` fails the way fork does when the host is out of
    processes or memory."""

    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.pid = None
        self.exitcode = None

    def start(self) -> None:
        raise OSError(11, "Resource temporarily unavailable")


@pytest.mark.unit
def test_a_child_that_cannot_start_fails_closed_typed(world, monkeypatch) -> None:
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation._ctx, "Process", _ProcessThatCannotStart)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    _assert_failed_closed(world, svc_id, run)


@pytest.mark.unit
def test_a_child_that_survives_sigkill_fails_closed_typed(world, monkeypatch) -> None:
    """`_kill` raises when a child is still there after SIGKILL. That raise is
    a failure of the child call like any other, not an untyped crash."""
    import app.ai.isolation as isolation

    real_kill = isolation._kill

    def _kill_then_report_a_survivor(child: Any) -> None:
        real_kill(child)
        raise RuntimeError(f"redaction child {child.pid} survived SIGKILL")

    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    monkeypatch.setattr(isolation, "_kill", _kill_then_report_a_survivor)
    pid_file = world["tmp"] / "survivor.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert pid_file.is_file(), "the stand-in child never ran, so this proves nothing"
    _assert_failed_closed(world, svc_id, run)


@pytest.mark.unit
def test_a_child_that_hangs_up_and_keeps_running_is_killed(world, monkeypatch) -> None:
    """The parent reads end-of-file, but the child has not exited: it is killed
    by PID, as on the answered path, rather than left running."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_close_pipe_then_spin)
    monkeypatch.setattr(isolation, "_KILL_JOIN_SECONDS", 1.0)
    pid_file = world["tmp"] / "hangup.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert pid_file.is_file(), "the stand-in child never ran, so this proves nothing"
    _assert_failed_closed(world, svc_id, run)
    rw.assert_gone(int(pid_file.read_text()))


class _RecvFailsOnceTheChildRuns:
    """The read end of the answer pipe: `poll` says an answer is waiting as
    soon as the child has written its PID, and `recv` then fails the way a
    broken pipe does, with the child still running."""

    def __init__(self, real: Any, pid_file: Any) -> None:
        self._real = real
        self._pid_file = pid_file

    def poll(self, _timeout: float) -> bool:
        rw.wait_for_file(self._pid_file)
        return True

    def recv(self) -> Any:
        raise OSError(104, "Connection reset by peer")

    def close(self) -> None:
        self._real.close()


@pytest.mark.unit
def test_a_child_left_running_by_a_failed_read_is_killed(world, monkeypatch) -> None:
    """`recv` raises while the child is alive. The run fails closed, typed, and
    the child does not outlive the call (#1042 narrow review, item 2)."""
    import app.ai.isolation as isolation

    pid_file = world["tmp"] / "readfail.pid"
    real_pipe = isolation._ctx.Pipe

    def _pipe(duplex: bool = True) -> tuple[Any, Any]:
        recv, send = real_pipe(duplex)
        return _RecvFailsOnceTheChildRuns(recv, pid_file), send

    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    monkeypatch.setattr(isolation._ctx, "Pipe", _pipe)
    monkeypatch.setattr(isolation, "_KILL_JOIN_SECONDS", 1.0)
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert pid_file.is_file(), "the stand-in child never ran, so this proves nothing"
    _assert_failed_closed(world, svc_id, run)
    rw.assert_gone(int(pid_file.read_text()))


# ---------------------------------------------------------------------------
# The child's environment BLOCK, its CPU limit, and its parent's death
# (#1042 final review, items 1 and 2)
# ---------------------------------------------------------------------------

#: What a redaction child's environment may hold, as the kernel reports it.
_CHILD_ENVIRONMENT = {"PATH", "LANG"}


@pytest.mark.unit
def test_a_childs_environment_block_holds_only_its_allowlist(world, monkeypatch) -> None:
    """Read from `/proc/<pid>/environ`, the environment block the child was
    started with, not `os.environ`: deleting from `os.environ` leaves the
    original strings in that block, which a forked child inherits. The api
    process's environment holds a provider key, a database URL and SHIELD
    settings; none of their names may be there."""
    import app.ai.isolation as isolation
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", "10")
    get_settings.cache_clear()
    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    pid_file = world["tmp"] / "environ.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    box: dict[str, Any] = {}
    job = threading.Thread(
        target=lambda: box.update(run=rw.extract(world, svc_id, artifact_id)), daemon=True
    )
    job.start()
    rw.wait_for_file(pid_file)
    pid = int(pid_file.read_text())
    with open(f"/proc/{pid}/environ", "rb") as f:
        block = f.read()
    job.join(rw.HANG_GUARD_S)

    names = {entry.split(b"=", 1)[0].decode() for entry in block.split(b"\0") if entry}
    assert names, "read nothing from the child's environment block, so this proves nothing"
    assert names <= _CHILD_ENVIRONMENT, sorted(names - _CHILD_ENVIRONMENT)
    assert box["run"]["error_reason"] == "redaction_budget_exceeded", box


@pytest.mark.unit
def test_a_child_runs_under_a_cpu_limit_from_its_budget(monkeypatch) -> None:
    """A child the parent can no longer kill (the api died) still stops: its
    CPU limit is the budget, rounded up, plus one second."""
    import app.ai.isolation as isolation
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", "2.5")
    get_settings.cache_clear()
    monkeypatch.setattr(isolation, "_TARGET", targets.report_cpu_limit)
    try:
        out, _counts = isolation.redact_payload_isolated(
            {"x": 1}, mode="strict", client_org_name=None, name_hints=()
        )
    finally:
        get_settings.cache_clear()

    assert out == {"rlimit_cpu": [4, 4]}, out


@pytest.mark.unit
def test_a_child_dies_when_the_api_process_is_killed(tmp_path) -> None:
    """The api is killed outright (SIGKILL, as an OOM kill does) while its child
    is redacting. The child is gone within seconds, long before its budget or
    CPU limit (60 s) could stop it."""
    import os
    import signal
    import subprocess
    import sys
    import time

    pid_file = tmp_path / "orphan.pid"
    api = subprocess.Popen(  # noqa: S603 - this interpreter and a module of this repo
        [sys.executable, "-m", "tests._isolation_api_stand_in", str(pid_file), "60"],
        cwd=str(rw.API_DIR),
    )
    child = None
    try:
        rw.wait_for_file(pid_file)
        child = int(pid_file.read_text())
        rw.assert_running(child)
        api.send_signal(signal.SIGKILL)
        api.wait(rw.HANG_GUARD_S)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and rw.is_running(child):
            time.sleep(0.1)
        # Dead is the claim. Its parent (the forkserver) died first, so the
        # child may still sit as a zombie until whoever adopted it reaps it;
        # a zombie runs nothing, so `is_running` treats it as stopped.
        assert not rw.is_running(child), f"child PID {child} outlived the api process"
    finally:
        if api.poll() is None:
            api.kill()
        if child is not None and rw.is_running(child):
            os.kill(child, signal.SIGKILL)


# ---------------------------------------------------------------------------
# The clean-environment wrapper: refused at startup with a named cause, and
# made again when a temp cleaner deletes it (#1042 final review, items 1 and 2)
# ---------------------------------------------------------------------------


def _start_the_api() -> None:
    """Run the api's startup hook, and only that: no server, no requests."""
    import asyncio

    from app.main import _lifespan, create_app

    async def _enter() -> None:
        async with _lifespan(create_app()):
            pass

    asyncio.run(_enter())


@pytest.mark.unit
def test_startup_refuses_a_wrapper_it_cannot_execute_and_says_why(monkeypatch) -> None:
    """A wrapper the host will not execute (a noexec temp mount does the same:
    exec is refused) stops the api at startup, naming the cause, instead of
    failing every AI call later as a bare `redaction_failed`."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(isolation, "_WRAPPER_MODE", 0o600)
    with pytest.raises(isolation.RedactionSetupError, match=r"cannot execute .* noexec"):
        _start_the_api()


@pytest.mark.unit
def test_startup_refuses_a_host_with_no_env_and_says_why(monkeypatch) -> None:
    import shutil

    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(isolation.RedactionSetupError, match=r"no `env` executable"):
        _start_the_api()


@pytest.mark.unit
def test_a_wrapper_a_temp_cleaner_deleted_is_made_again(world) -> None:
    """The wrapper is gone (a host temp cleaner removed its directory) and the
    forkserver is down, so the next child needs a new forkserver, which execs
    the wrapper. The redaction makes the wrapper again before that, and
    succeeds. Read from the module, not by calling `prepare` here: calling it
    would perform the step under test."""
    import shutil
    from multiprocessing import forkserver

    import app.ai.isolation as isolation

    first = isolation.prepare_redaction_executable()
    forkserver._forkserver._stop()
    shutil.rmtree(os.path.dirname(first))
    assert not os.path.exists(first)

    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "completed", run
    second = isolation._wrapper_path
    assert second is not None and second != first
    assert os.path.isfile(second)


@pytest.mark.unit
def test_startup_refuses_a_wrapper_whose_probe_fails_and_says_why(monkeypatch) -> None:
    """The wrapper runs but its interpreter does not pass the probe."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(isolation, "_PROBE", "import sys; sys.exit(5)")
    with pytest.raises(isolation.RedactionSetupError, match=r"exited 5"):
        _start_the_api()


@pytest.mark.unit
def test_startup_refuses_a_wrapper_whose_environment_is_not_the_allowlist(monkeypatch) -> None:
    """A wrapper that passes one variable too many: the probe's environment
    check, not just its exit, is what refuses it."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(
        isolation, "_CHILD_ENVIRONMENT", {**isolation._CHILD_ENVIRONMENT, "EXTRA_PROBE": "1"}
    )
    with pytest.raises(
        isolation.RedactionSetupError, match=r"exited 3.*extra=EXTRA_PROBE missing=-"
    ):
        _start_the_api()


@pytest.mark.unit
def test_startup_refuses_a_wrapper_whose_environment_lacks_an_allowlisted_name(
    monkeypatch,
) -> None:
    """A wrapper that passes one variable too FEW: the probe wants the
    allowlist exactly, not merely nothing outside it, and names what is
    missing. PATH, not LANG: without LANG, PEP 538 sets LC_CTYPE, and the
    check would fail for an extra name as well, so it could not tell the two
    apart."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(isolation, "_CHILD_ENVIRONMENT", {"LANG": "C.UTF-8"})
    with pytest.raises(isolation.RedactionSetupError, match=r"exited 3.*extra=- missing=PATH"):
        _start_the_api()


@pytest.mark.unit
def test_startup_refuses_an_unwritable_temp_directory_and_says_why(monkeypatch) -> None:
    import tempfile

    import app.ai.isolation as isolation

    def _refuse(*_a: Any, **_k: Any) -> str:
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(isolation, "_wrapper_path", None)
    monkeypatch.setattr(tempfile, "mkdtemp", _refuse)
    with pytest.raises(isolation.RedactionSetupError, match=r"temp directory writable"):
        _start_the_api()
