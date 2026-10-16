"""#1219: a batch worker marks its run as calling BEFORE its stop check.

The run records "not charged" (`charged_likely` False) only for a job that
never entered `LLMClient.invoke`. A batch worker that passed its stop check
and had not yet reached `invoke` when the collector ended the run (here, the
run deadline) used to leave the mark unset, so the run recorded False while
that worker was still on its way to the provider. Whether it then gets there
depends on timing: once `_execute` releases the run's redaction place
(`release_run`), a batch arriving later is refused before any call; one that
enters `invoke` between the record and that release is not. A record that
depends on that race is not one a consultant can be shown as "made no call".

The interleaving is forced, not hoped for: every batch is held between its
stop check and `run_job` (so before `invoke`) until the run has been recorded
failed at its deadline. A worker past its stop check has marked the run, so
the record is the conservative "not known". It does not drive a call into the
gap, which needs the release itself delayed.

The hold sits inside `run_job`, after both the mark and the stop check, so
that test alone cannot tell "mark before the check" from "mark after the check
but before `run_job`". The second test pins the order itself: it reads the
run's mark at the moment each worker asks the stop flag.
"""

from __future__ import annotations

import threading
import types
from datetime import timedelta

import pytest

from tests._ai_runs import get_run, start_run
from tests.unit.test_ai_runs_csf import world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_a_batch_held_past_its_stop_check_leaves_the_run_not_known(
    world, monkeypatch  # noqa: F811
) -> None:
    import app.ai.batching as batching
    import app.ai.runs as runs

    monkeypatch.setattr(type(world.provider), "name", "anthropic", raising=False)
    # Long enough that a loaded runner still gets a batch to the hold before
    # the deadline (the job's own reads spend it first); the test asserts the
    # ORDER, so only its length, not its exact value, matters.
    monkeypatch.setattr(runs, "RUN_DEADLINE", timedelta(seconds=8))
    gate = threading.Event()
    held = threading.Event()
    held_threads: list[threading.Thread] = []
    real_run_job = batching.run_job

    def _held_run_job(*args: object, **kwargs: object) -> object:
        held_threads.append(threading.current_thread())
        held.set()
        assert gate.wait(timeout=60), "the test never released the batch"
        return real_run_job(*args, **kwargs)

    monkeypatch.setattr(batching, "run_job", _held_run_job)
    world.suggest(2)

    body_passed = False
    try:
        started = start_run(world.c, world.run_url, world.h, serves="live")
        assert held.is_set(), "no batch reached the point between its stop check and the call"
        run = get_run(world.c, started["run_id"], world.h)
        assert run["serves"] == "live", run
        assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded"), run
        # Recorded while every batch was still held, before any call.
        assert run["charged_likely"] is None, run
        body_passed = True
    finally:
        gate.set()
        # Let the released batches finish before the fixture tears the
        # database down, on the failing path too. The run has ended, so the
        # redaction gate turns them away. Only the threads this test held are
        # waited for; one still running is a fault, reported only when the
        # body passed so it never hides the assertion that failed.
        for t in held_threads:
            t.join(timeout=30)
        if body_passed:
            alive = [t.name for t in held_threads if t.is_alive()]
            assert not alive, f"a released batch never finished: {alive}"


def test_a_batch_worker_has_marked_its_run_when_it_checks_the_stop_flag(
    world, monkeypatch  # noqa: F811
) -> None:
    """Every `stop.is_set()` a batch worker makes must find the run already
    marked. Red if `note_invoke_entered()` moves below the stop check in
    `batching._one`: the first worker to check finds the mark unset."""
    import app.ai.batching as batching
    from app.ai.run_context import invoke_mark_var

    # Recorded in the worker and judged here: an assertion raised inside a
    # worker would only fail its batch. None means no mark in its context.
    seen: list[bool | None] = []

    class _RecordingEvent(threading.Event):
        def is_set(self) -> bool:
            mark = invoke_mark_var.get()
            seen.append(None if mark is None else mark.entered)
            return super().is_set()

    # Only `run_batches`' stop flag is built from `batching.threading`.
    monkeypatch.setattr(batching, "threading", types.SimpleNamespace(Event=_RecordingEvent))
    monkeypatch.setattr(type(world.provider), "name", "anthropic", raising=False)
    world.suggest(2)

    started = start_run(world.c, world.run_url, world.h, serves="live")
    get_run(world.c, started["run_id"], world.h)

    # A selector that selected nothing passes: the workers must have checked.
    assert seen, "no batch worker checked the stop flag"
    assert all(
        x is True for x in seen
    ), f"a worker checked the stop flag before marking the run: {seen}"
