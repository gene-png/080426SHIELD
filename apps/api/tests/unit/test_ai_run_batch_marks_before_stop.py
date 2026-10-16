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
the record is the conservative "not known". What this pins is that ORDER; it
does not drive a call into the gap, which needs the release itself delayed.
"""

from __future__ import annotations

import threading
import time
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
    monkeypatch.setattr(runs, "RUN_DEADLINE", timedelta(seconds=2))
    gate = threading.Event()
    held = threading.Event()
    real_run_job = batching.run_job

    def _held_run_job(*args: object, **kwargs: object) -> object:
        held.set()
        assert gate.wait(timeout=60), "the test never released the batch"
        return real_run_job(*args, **kwargs)

    monkeypatch.setattr(batching, "run_job", _held_run_job)
    world.suggest(2)

    try:
        started = start_run(world.c, world.run_url, world.h, serves="live")
        assert held.is_set(), "no batch reached the point between its stop check and the call"
        run = get_run(world.c, started["run_id"], world.h)
        assert run["serves"] == "live", run
        assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded"), run
        # Recorded while every batch was still held, before any call.
        assert run["charged_likely"] is None, run
    finally:
        gate.set()

    # Let the released batches finish before the fixture tears the database
    # down. The run has ended, so the redaction gate turns them away.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if not any(t.name.startswith("ThreadPoolExecutor") for t in threading.enumerate()):
            break
        time.sleep(0.1)
