"""#1219: a batch worker marks its run as calling BEFORE its stop check.

The run records "not charged" (`charged_likely` False) only for a job that
never entered `LLMClient.invoke`. A batch worker that passed its stop check
and had not yet reached `invoke` when the collector ended the run (here, the
run deadline) used to leave the mark unset: the run recorded False, and the
worker then went on to call the provider. The workspace would print "made no
live AI call" about a call that happened.

The interleaving is forced, not hoped for: every batch is held between its
stop check and `run_job` (so before `invoke`) until the run has been recorded
failed at its deadline; then the batches are let go, and their live
`llm_calls` rows prove the call happened after the record.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from tests._ai_runs import get_run, start_run
from tests.unit.test_ai_runs_csf import world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_a_batch_held_past_its_stop_check_leaves_the_run_not_known(
    world, monkeypatch  # noqa: F811
) -> None:
    import app.ai.batching as batching
    import app.ai.runs as runs
    from app.models.llm_call import LLMCall, LLMCallMode

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

    # The held batches now call: the run's "not known" was the honest answer.
    run_id = uuid.UUID(started["run_id"])
    deadline = time.monotonic() + 30
    live = 0
    while time.monotonic() < deadline:
        with world.sessions() as s:
            live = s.execute(
                select(func.count())
                .select_from(LLMCall)
                .where(LLMCall.ai_run_id == run_id, LLMCall.mode == LLMCallMode.LIVE)
            ).scalar_one()
        if live and not any(t.name.startswith("ThreadPoolExecutor") for t in threading.enumerate()):
            break
        time.sleep(0.1)
    assert live > 0, "the released batches made no live call"
