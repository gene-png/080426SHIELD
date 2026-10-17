"""#1219: a LIVE run refused before it reached the provider was not charged.

A discard racing a run wins (D-031): the job re-reads the assessment, finds it
discarded, and fails `assessment_not_editable` before any provider call. With
no `llm_calls` row a live run used to store `charged_likely` None, which the
workspace prints beside that failure as "It may have made a live AI call" --
next to a message saying the run never started. Only ZT's blank-notes path
declared "no call" (#1231); every service's refusal path is this case.

Driven through the real endpoints with the job held (`defer_runs`), so the
discard lands between the 202 and the job, as it does in production. The
control is a run that DID enter `LLMClient.invoke` and failed there before any
ledger row: it must stay "not known", never be cleared to False.

The controls come in both shapes of job. A batched job (CSF) also marks the run
in `batching._one`, so only a single-call job (ZT) depends on the mark in
`invoke` itself; that is the control which goes red if `invoke` stops marking.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from tests._ai_runs import defer_runs, get_run, start_run
from tests._zt_notes import noted_assessment
from tests.unit.test_ai_runs_csf import world  # noqa: F401  (fixture)
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _present_as_live(provider, monkeypatch) -> None:
    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)


def test_a_live_csf_run_discarded_before_its_job_was_not_charged(
    world, monkeypatch  # noqa: F811
) -> None:
    """Red before the fix: `charged_likely` None."""
    _present_as_live(world.provider, monkeypatch)
    runner = defer_runs(world.app)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h, serves="live")
    r = world.c.post(f"/csf/assessments/{world.assessment_id}/discard", headers=world.h)
    assert r.status_code == 200, r.text
    assert runner.run_all() == 1

    run = get_run(world.c, started["run_id"], world.h)
    # Live, or False would be the offline answer and prove nothing.
    assert run["serves"] == "live", run
    assert (run["status"], run["error_reason"]) == ("failed", "assessment_not_editable"), run
    assert run["charged_likely"] is False, run


def test_a_live_zt_run_discarded_before_its_job_was_not_charged(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The twin, in a service whose refusal is a separate code path."""
    c, provider = app_client
    _present_as_live(provider, monkeypatch)
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = noted_assessment(c, h, svc_id)
    runner = defer_runs(c.app)
    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h, serves="live")
    r = c.post(f"/zt/assessments/{a.json()['id']}/discard", headers=h)
    assert r.status_code == 200, r.text
    assert runner.run_all() == 1

    run = get_run(c, started["run_id"], h)
    assert run["serves"] == "live", run
    assert (run["status"], run["error_reason"]) == ("failed", "assessment_not_editable"), run
    assert run["charged_likely"] is False, run


def test_a_live_run_that_entered_invoke_stays_not_known(world, monkeypatch) -> None:  # noqa: F811
    """The control. The job reached `LLMClient.invoke`, which failed before it
    wrote any ledger row: nothing proves a call was or was not made, so the
    answer stays None. A fix that cleared every row-less live run to False
    turns this red."""
    import app.ai.llm as llm_module

    def _boom(*_: object, **__: object) -> object:
        raise RuntimeError("failed inside invoke, before the ledger row")

    monkeypatch.setattr(llm_module, "redact_ai_payload", _boom)
    _present_as_live(world.provider, monkeypatch)
    world.suggest(2)
    started = start_run(world.c, world.run_url, world.h, serves="live")

    run = get_run(world.c, started["run_id"], world.h)
    assert run["serves"] == "live", run
    # Whether CSF records the batch failure as a failed run or as a completed
    # run with failed batches, no batch can have reached the provider.
    assert run["status"] == "failed" or run["batches_failed"] > 0, run
    assert run["charged_likely"] is None, run


def test_a_live_single_call_run_that_entered_invoke_stays_not_known(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The single-call control. ZT's job calls `run_job` directly, with no
    batch worker to mark the run, so only `invoke`'s own mark keeps this None.
    Red if `note_invoke_entered()` is removed from `invoke` or moved below the
    point where this fails."""
    import app.ai.llm as llm_module

    def _boom(*_: object, **__: object) -> object:
        raise RuntimeError("failed inside invoke, before the ledger row")

    monkeypatch.setattr(llm_module, "redact_ai_payload", _boom)
    c, provider = app_client
    _present_as_live(provider, monkeypatch)
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    noted_assessment(c, h, svc_id)
    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h, serves="live")

    run = get_run(c, started["run_id"], h)
    assert run["serves"] == "live", run
    assert run["status"] == "failed", run
    assert run["charged_likely"] is None, run


def test_invoke_marks_the_run_before_anything_else() -> None:
    """The advisor's ratchet (#736 6225076633 item 3): the mark is the FIRST
    statement of `LLMClient.invoke`, after its docstring, so nothing that can
    fail or send runs before it. The control above proves the mark is there;
    this pins where."""
    from app.ai.llm import LLMClient

    fn = ast.parse(textwrap.dedent(inspect.getsource(LLMClient.invoke))).body[0]
    assert isinstance(fn, ast.FunctionDef) and fn.name == "invoke", ast.dump(fn)[:200]
    body = fn.body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    first = body[0]
    assert (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "note_invoke_entered"
        and not first.value.args
        and not first.value.keywords
    ), f"invoke's first statement is not note_invoke_entered(): line {first.lineno}"
