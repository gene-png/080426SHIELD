"""Run-AI in the background, through ATT&CK's endpoints (#645, with #504).

Every guard here is driven through the HTTP surface a consultant reaches. Most
tests install a DEFERRING runner (`tests/_ai_runs.py`) so a run can be observed
while RUNNING; Starlette's TestClient would otherwise finish the job before
`post()` returns and no guard would ever see a run in progress. One test runs
the production `BackgroundTasks` path end to end.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.ai_run import AiRun, AiRunStatus
from app.models.attack_assessment import AttackCoverage
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.llm_call import LLMCall, LLMCallMode
from app.models.service import Service, ServiceKind, ServiceStatus
from tests._ai_runs import DeferringRunner, defer_runs, get_run, start_run
from tests._attack_rows import standalone_rows


class LiveLookingProvider(FixtureProvider):
    """Serves canned output but REPORTS itself live, the way a provider built
    from a stored key does. Everything mode-dependent keys on `provider.name`."""

    name = "anthropic"


@dataclass
class World:
    c: TestClient
    app: Any
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    cid: str
    user_id: str
    svc_id: str
    assessment_id: str
    codes: list[str]
    coverage_ids: dict[str, str]

    @property
    def run_url(self) -> str:
        return f"/attack/services/{self.svc_id}/run-ai"

    def use_provider(self, provider: FixtureProvider) -> None:
        from app.routes.attack import _llm_dep

        self.provider = provider
        self.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
        _register(provider, self.codes)

    def runs(self) -> list[AiRun]:
        with self.sessions() as s:
            return list(s.execute(select(AiRun).order_by(AiRun.started_at)).scalars())

    def row(self, code: str) -> AttackCoverage:
        with self.sessions() as s:
            return s.execute(
                select(AttackCoverage).where(
                    AttackCoverage.assessment_id == uuid.UUID(self.assessment_id),
                    AttackCoverage.technique_code == code,
                )
            ).scalar_one()


def _register(provider: FixtureProvider, codes: list[str]) -> None:
    """Suggest `covered` for each of `codes` IN THE BATCH it was sent, as the
    prompt asks: mitre_map runs in batches, and a static response would
    answer every batch with the same rows."""

    def respond(payload: dict) -> LLMResponse:
        sent = set(payload.get("technique_codes") or [])
        techniques = ",".join(
            '{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike Falcon"], "prevention_tools": [],'
            ' "response_tools": [], "rationale": "EDR detects."}'
            for code in codes
            if code in sent
        )
        return LLMResponse('{"techniques": [' + techniques + "]}")

    provider.register("mitre_map", respond)


@pytest.fixture()
def app_parts(tmp_path) -> Iterator[tuple[TestClient, Any, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-airuns.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, app, sessions


def _world(app_parts, *, provider: FixtureProvider | None = None, n_codes: int = 3) -> World:
    c, app, sessions = app_parts
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    with sessions() as db:
        td = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=uuid.UUID(cid),
            opened_by=uuid.UUID(me["id"]),
        )
        db.add(td)
        db.flush()
        cl = CapabilityList(service_id=td.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        db.add(CapabilityItem(capability_list_id=cl.id, name="CrowdStrike Falcon"))
        db.commit()
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()
    rows = standalone_rows(a["coverage"], n_codes)
    w = World(
        c=c,
        app=app,
        sessions=sessions,
        provider=FixtureProvider(),
        h=h,
        cid=cid,
        user_id=me["id"],
        svc_id=svc_id,
        assessment_id=a["id"],
        codes=[r["technique_code"] for r in rows],
        coverage_ids={r["technique_code"]: r["id"] for r in rows},
    )
    w.use_provider(provider or FixtureProvider())
    return w


def _deferred(app_parts, **kw) -> tuple[World, DeferringRunner]:
    w = _world(app_parts, **kw)
    return w, defer_runs(w.app)


# ---------------------------------------------------------------------------
# The POST: `serves` is required, and #504's refusal
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("body", [None, {}, {"serves": "broken"}, {"serves": None}])
def test_a_run_without_an_acknowledged_mode_is_a_typed_422(app_parts, body) -> None:
    w, runner = _deferred(app_parts)
    r = (
        w.c.post(w.run_url, headers=w.h, json=body)
        if body is not None
        else w.c.post(w.run_url, headers=w.h)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "serves_required"
    assert w.runs() == [] and runner.pending == []


@pytest.mark.unit
def test_offline_acknowledged_but_the_provider_now_live_is_refused_and_nothing_is_sent(
    app_parts,
) -> None:
    w, runner = _deferred(app_parts, provider=LiveLookingProvider())
    r = w.c.post(w.run_url, headers=w.h, json={"serves": "offline"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "ai_status_changed"
    assert w.runs() == [] and runner.pending == []
    with w.sessions() as s:
        assert s.execute(select(LLMCall)).first() is None


@pytest.mark.unit
def test_live_acknowledged_and_the_provider_now_offline_is_allowed(app_parts) -> None:
    # #504: the reverse direction serves canned output, which is harmless.
    w, _runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h, serves="live")
    assert started["serves"] == "offline" and started["joined"] is False


# ---------------------------------------------------------------------------
# One run at a time: join, refuse the other mode, the index, the savepoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_second_post_while_running_joins_the_same_run(app_parts) -> None:
    w, runner = _deferred(app_parts)
    first = start_run(w.c, w.run_url, w.h)
    assert get_run(w.c, first["run_id"], w.h)["status"] == "running"
    second = start_run(w.c, w.run_url, w.h)
    assert second["run_id"] == first["run_id"]
    assert second["joined"] is True
    assert len(w.runs()) == 1 and len(runner.pending) == 1
    assert runner.run_all() == 1
    assert get_run(w.c, first["run_id"], w.h)["status"] == "completed"


@pytest.mark.unit
def test_a_second_post_in_the_other_mode_is_refused_not_joined(app_parts) -> None:
    w, runner = _deferred(app_parts)
    start_run(w.c, w.run_url, w.h, serves="offline")
    # The key was loaded: the provider is live now, and this consultant
    # acknowledged live. They must not be told the offline run is theirs.
    w.use_provider(LiveLookingProvider())
    r = w.c.post(w.run_url, headers=w.h, json={"serves": "live"})
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "ai_run_in_progress_other_mode"
    assert len(w.runs()) == 1 and len(runner.pending) == 1


@pytest.mark.unit
def test_the_index_refuses_a_second_running_run_for_the_same_service_and_purpose(
    app_parts,
) -> None:
    """The single-run guarantee is the database's, not a read's. On SQLite;
    Postgres gets the same predicate through `postgresql_where` (0057)."""
    w, _runner = _deferred(app_parts)
    first = start_run(w.c, w.run_url, w.h)
    with w.sessions() as s:
        s.add(_competing_run(w, mode=LLMCallMode.FIXTURE))
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
        # A finished run does not hold the slot: the index is PARTIAL.
        s.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(first["run_id"]))
            .values(status=AiRunStatus.FAILED)
        )
        s.add(_competing_run(w, mode=LLMCallMode.FIXTURE))
        s.commit()


def _competing_run(w: World, *, mode: LLMCallMode) -> AiRun:
    from app.ai.runs import BOOT_ID, RUN_DEADLINE
    from app.models._common import utcnow

    now = utcnow()
    return AiRun(
        client_id=uuid.UUID(w.cid),
        service_id=uuid.UUID(w.svc_id),
        purpose="mitre_map",
        subject_id=uuid.UUID(w.assessment_id),
        status=AiRunStatus.RUNNING,
        mode=mode,
        boot_id=BOOT_ID,
        requested_by=uuid.UUID(w.user_id),
        started_at=now,
        deadline_at=now + RUN_DEADLINE,
    )


def _race(w: World, monkeypatch, mode: LLMCallMode) -> list[uuid.UUID]:
    """Commit a competing RUNNING run between the POST's read and its insert."""
    import app.ai.runs as runs

    fired: list[uuid.UUID] = []

    def compete() -> None:
        if not fired:
            run = _competing_run(w, mode=mode)
            with w.sessions() as other:
                other.add(run)
                other.commit()
                fired.append(run.id)
            runs._mark_live(fired[0])

    monkeypatch.setattr(runs, "_between_read_and_insert", compete)
    return fired


@pytest.mark.unit
def test_concurrent_first_posts_join_the_run_that_won_the_insert(app_parts, monkeypatch) -> None:
    w, runner = _deferred(app_parts)
    fired = _race(w, monkeypatch, LLMCallMode.FIXTURE)
    started = start_run(w.c, w.run_url, w.h)
    assert fired, "the race was not exercised"
    assert started["run_id"] == str(fired[0])
    assert started["joined"] is True
    assert len(w.runs()) == 1 and runner.pending == []


@pytest.mark.unit
def test_concurrent_first_posts_in_the_other_mode_are_refused(app_parts, monkeypatch) -> None:
    w, runner = _deferred(app_parts)
    fired = _race(w, monkeypatch, LLMCallMode.LIVE)
    r = w.c.post(w.run_url, headers=w.h, json={"serves": "offline"})
    assert fired, "the race was not exercised"
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "ai_run_in_progress_other_mode"
    assert len(w.runs()) == 1 and runner.pending == []


# ---------------------------------------------------------------------------
# The job: completion, failures, the deadline, rows edited mid-run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_run_applies_its_results_and_records_every_disclosure(app_parts) -> None:
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert run["status"] == "completed", run
    assert run["applied_count"] == len(w.codes)
    assert run["batches_total"] >= 1 and run["batches_failed"] == 0
    assert run["result"]["batches_total"] == run["batches_total"]
    assert run["charged_likely"] is False
    for key in (
        "tools_available",
        "changed",
        "batches_total",
        "batches_failed",
        "citations_confirmed",
        "citations_needs_review",
        "citations_rejected",
        "citations_rejected_examples",
        "citations_needs_review_tools",
        "citations_needs_review_by_reason",
        "citations_unusable",
        "rows_left_unresolved",
        "unresolved_fields",
        "pending_review_rows",
        "rows_skipped_edited",
    ):
        assert key in run["result"], key
    assert run["result"]["citations_confirmed"] == len(w.codes)
    assert all(w.row(code).status == "covered" for code in w.codes)
    from app.schemas.attack import AttackRunAiResponse

    # Derived from the schema, never hand-listed: `AttackRunAiResponse` was the
    # synchronous route's `response_model` and is now the run result's model,
    # so every key it declares must be on the stored result. A field dropped
    # from the result fails here instead of silently shrinking what the
    # migrated assertions can see.
    result = run["result"]
    assert set(result) == set(AttackRunAiResponse.model_fields), set(result) ^ set(
        AttackRunAiResponse.model_fields
    )
    covered = {c["technique_code"] for c in result["coverage"] if c["status"] == "covered"}
    assert covered >= set(w.codes)


@pytest.mark.unit
def test_the_production_background_runner_finishes_the_run_end_to_end(app_parts) -> None:
    w = _world(app_parts)  # no deferring runner: FastAPI's BackgroundTasks
    started = start_run(w.c, w.run_url, w.h)
    run = get_run(w.c, started["run_id"], w.h)
    assert run["status"] == "completed", run
    assert run["applied_count"] == len(w.codes)
    from app.ai.runs import is_live

    assert not is_live(uuid.UUID(started["run_id"])), "the job must leave the live set"


@pytest.mark.unit
def test_a_reaped_run_never_applies_late(app_parts) -> None:
    """Completion is a compare-and-swap on RUNNING. A run ended while its job
    worked must not land its results under a run the workspace calls failed."""
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    with w.sessions() as s:
        s.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(started["run_id"]))
            .values(status=AiRunStatus.FAILED, error_reason="run_deadline_exceeded")
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded")
    assert run["result"] is None
    assert all(w.row(code).status is None for code in w.codes)


@pytest.mark.unit
def test_a_provider_failure_ends_the_run_failed_with_its_typed_reason(app_parts) -> None:
    w, runner = _deferred(app_parts, provider=LiveLookingProvider())

    def boom(_payload: dict) -> LLMResponse:
        raise RuntimeError("upstream exploded")

    w.provider.register("mitre_map", boom)
    started = start_run(w.c, w.run_url, w.h, serves="live")
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "ai_call_failed"), run
    assert "upstream exploded" in run["error_message"]
    assert run["charged_likely"] is True
    with w.sessions() as s:
        calls = s.execute(select(LLMCall)).scalars().all()
    assert calls and all(c.ai_run_id == uuid.UUID(started["run_id"]) for c in calls)


@pytest.mark.unit
def test_one_failed_batch_leaves_a_partial_run_that_says_so(app_parts) -> None:
    """#479: the batch loop moved to `app.ai.batching.run_batches`, shared with
    csf_score. Through ATT&CK's own endpoint: one batch raising costs that
    batch's techniques, the run completes, and the run and its result say how
    many batches failed."""
    w, runner = _deferred(app_parts)
    lost = w.codes[0]

    def respond(payload: dict) -> LLMResponse:
        sent = set(payload.get("technique_codes") or [])
        if lost in sent:
            raise RuntimeError("provider closed the connection")
        techniques = ",".join(
            '{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike Falcon"], "prevention_tools": [],'
            ' "response_tools": [], "rationale": "EDR detects."}'
            for code in w.codes
            if code in sent
        )
        return LLMResponse('{"techniques": [' + techniques + "]}")

    w.provider.register("mitre_map", respond)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert run["status"] == "completed", run
    assert run["batches_failed"] == 1
    assert run["batches_total"] > 1
    assert run["result"]["batches_failed"] == 1
    assert run["result"]["batches_total"] == run["batches_total"]
    assert w.row(lost).status is None
    with w.sessions() as s:
        calls = s.execute(select(LLMCall)).scalars().all()
    assert len(calls) == run["batches_total"]


@pytest.mark.unit
def test_a_discard_during_the_run_wins_and_the_run_ends_not_editable(app_parts) -> None:
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    r = w.c.post(f"/attack/assessments/{w.assessment_id}/discard", headers=w.h)
    assert r.status_code == 200, r.text
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "assessment_not_editable"), run
    assert all(w.row(code).status is None for code in w.codes)


@pytest.mark.unit
def test_a_run_past_its_deadline_stops_between_batches(app_parts, monkeypatch) -> None:
    import app.ai.runs as runs

    w, runner = _deferred(app_parts)
    monkeypatch.setattr(runs, "RUN_DEADLINE", timedelta(seconds=-1))
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded"), run
    assert all(w.row(code).status is None for code in w.codes)


@pytest.mark.unit
def test_a_row_edited_after_the_run_started_is_kept_and_counted(app_parts) -> None:
    """The edit lock refuses an edit while the run is RUNNING, but an edit that
    checked the lock BEFORE the run row existed can commit after it. Simulated
    here by writing the row directly, as that edit's transaction would."""
    from app.models._common import utcnow

    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    edited = w.codes[0]
    with w.sessions() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(w.coverage_ids[edited]))
            .values(status="gap", updated_at=utcnow())
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert run["status"] == "completed", run
    assert run["result"]["rows_skipped_edited"] == 1
    assert run["applied_count"] == len(w.codes) - 1
    assert run["applied_count"] > 0
    assert w.row(edited).status == "gap"
    assert all(w.row(code).status == "covered" for code in w.codes[1:])


@pytest.mark.unit
def test_the_correlation_id_reaches_every_llm_call_of_the_run(app_parts) -> None:
    """The deferred job runs OUTSIDE the request, as a real background task
    does once the response is sent: only the copied context can carry it."""
    w, runner = _deferred(app_parts, n_codes=30)  # two batches of mitre_map
    r = w.c.post(w.run_url, headers={**w.h, "X-Request-ID": "req-645"}, json={"serves": "offline"})
    assert r.status_code == 202, r.text
    run_id = uuid.UUID(r.json()["run_id"])
    assert runner.run_all() == 1
    with w.sessions() as s:
        calls = s.execute(select(LLMCall).where(LLMCall.ai_run_id == run_id)).scalars().all()
        stored = s.get(AiRun, run_id)
    assert len(calls) >= 2, "expected one llm_calls row per batch"
    assert {c.correlation_id for c in calls} == {"req-645"}
    assert stored.correlation_id == "req-645"


# ---------------------------------------------------------------------------
# The reaper, on read
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_run_left_by_another_boot_is_ended_on_the_next_read(app_parts) -> None:
    w, _runner = _deferred(app_parts)
    with w.sessions() as s:
        run = _competing_run(w, mode=LLMCallMode.FIXTURE)
        run.boot_id = "a-previous-process"
        s.add(run)
        s.commit()
        run_id = run.id
    summary = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h).json()
    assert summary["running"] is None, summary
    assert summary["latest"]["id"] == str(run_id)
    assert summary["latest"]["error_reason"] == "run_orphaned"
    assert "restarted" in summary["latest"]["error_message"]


@pytest.mark.unit
def test_a_run_this_process_is_executing_is_not_reaped(app_parts) -> None:
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    assert get_run(w.c, started["run_id"], w.h)["status"] == "running"
    summary = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h).json()
    assert summary["running"]["id"] == started["run_id"]


@pytest.mark.unit
def test_a_live_run_far_past_its_deadline_is_ended_by_a_read(app_parts) -> None:
    from app.ai.runs import REAP_MARGIN
    from app.models._common import utcnow

    w, _runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    with w.sessions() as s:
        s.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(started["run_id"]))
            .values(deadline_at=utcnow() - REAP_MARGIN - timedelta(seconds=1))
        )
        s.commit()
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded"), run


# ---------------------------------------------------------------------------
# The edit lock, over a route set derived from the router
# ---------------------------------------------------------------------------

LOCK_DRIVERS: dict[tuple[str, str], Callable[[World], Any]] = {
    ("POST", "/attack/services/{service_id}/assessments"): (
        lambda w: w.c.post(f"/attack/services/{w.svc_id}/assessments", headers=w.h)
    ),
    ("PATCH", "/attack/coverage/{coverage_id}"): (
        lambda w: w.c.patch(
            f"/attack/coverage/{w.coverage_ids[w.codes[0]]}",
            headers=w.h,
            json={"notes": "edited mid-run"},
        )
    ),
    ("POST", "/attack/coverage/{coverage_id}/confirm-citations"): (
        lambda w: w.c.post(
            f"/attack/coverage/{w.coverage_ids[w.codes[0]]}/confirm-citations", headers=w.h
        )
    ),
    ("POST", "/attack/assessments/{assessment_id}/approve"): (
        lambda w: w.c.post(f"/attack/assessments/{w.assessment_id}/approve", headers=w.h)
    ),
    ("POST", "/attack/services/{service_id}/deliverables/finalize"): (
        lambda w: w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    ),
    # #554 R3: a run rewrites the stored suggestions the review compares against.
    ("POST", "/attack/assessments/{assessment_id}/computed-status-review"): (
        lambda w: w.c.post(
            f"/attack/assessments/{w.assessment_id}/computed-status-review",
            headers=w.h,
            json={"reviews": [{"code": w.codes[0], "computed_status": "gap"}]},
        )
    ),
}

# Mutating ATT&CK routes the lock deliberately leaves open, each for a reason.
NOT_LOCKED = {
    # Creates a new service; no run can be in progress on it.
    ("POST", "/attack/services"),
    # Joins or refuses the run in progress itself.
    ("POST", "/attack/services/{service_id}/run-ai"),
    # D-031: a discard racing a run wins; the job then ends FAILED.
    ("POST", "/attack/assessments/{assessment_id}/discard"),
    # Ships a deliverable already rendered from an APPROVED assessment. A run
    # is refused on an approved or released assessment, so it can never be
    # writing the rows a release ships.
    ("POST", "/attack/deliverables/{deliverable_id}/release"),
}


def _mutating_attack_routes() -> set[tuple[str, str]]:
    from app.routes.attack import router

    found: set[tuple[str, str]] = set()
    for route in router.routes:
        for method in getattr(route, "methods", set()) - {"GET", "HEAD", "OPTIONS"}:
            found.add((method, getattr(route, "path", "")))
    return found


@pytest.mark.unit
def test_every_mutating_attack_route_is_either_locked_or_named_as_open() -> None:
    found = _mutating_attack_routes()
    assert found, "no routes found: the filter is broken, not the routes clean"
    assert found == set(LOCK_DRIVERS) | NOT_LOCKED, {
        "undriven": sorted(found - set(LOCK_DRIVERS) - NOT_LOCKED),
        "stale": sorted((set(LOCK_DRIVERS) | NOT_LOCKED) - found),
    }


@pytest.mark.unit
@pytest.mark.parametrize("route", sorted(LOCK_DRIVERS), ids=lambda r: f"{r[0]} {r[1]}")
def test_each_locked_route_is_refused_while_a_run_is_in_progress(app_parts, route) -> None:
    w, runner = _deferred(app_parts)
    start_run(w.c, w.run_url, w.h)
    r = LOCK_DRIVERS[route](w)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "ai_run_in_progress"
    assert "UTC" in err["message"]  # the screen says when the lock ends
    # And once the run has finished, the same request is not refused for it.
    assert runner.run_all() == 1
    after = LOCK_DRIVERS[route](w)
    assert after.status_code != 409 or after.json()["error"].get("reason") != "ai_run_in_progress"


# ---------------------------------------------------------------------------
# Reading runs: authorization, tenancy, the last applied run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_another_tenants_run_is_a_404_and_a_client_user_is_refused(app_parts) -> None:
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    other = w.c.post(
        "/admin/clients",
        headers={"Authorization": w.h["Authorization"]},
        json={"legal_name": "Other Co"},
    ).json()["id"]
    elsewhere = {**w.h, "X-Client-Id": other}
    assert w.c.get(f"/ai-runs/{started['run_id']}", headers=elsewhere).status_code == 404
    assert w.c.get(f"/ai-runs/services/{w.svc_id}", headers=elsewhere).status_code == 404

    w.c.post(
        f"/admin/clients/{w.cid}/domains",
        headers={"Authorization": w.h["Authorization"]},
        json={"domain": "acme.example"},
    )
    user = w.c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    ).json()
    ch = {"Authorization": f"Bearer {user['tokens']['access_token']}"}
    assert w.c.get(f"/ai-runs/{started['run_id']}", headers=ch).status_code == 403
    assert w.c.get(f"/ai-runs/services/{w.svc_id}", headers=ch).status_code == 403


@pytest.mark.unit
def test_a_later_failure_does_not_hide_the_last_run_whose_results_stand(app_parts) -> None:
    w, runner = _deferred(app_parts)
    first = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1

    def boom(_payload: dict) -> LLMResponse:
        raise RuntimeError("down")

    w.provider.register("mitre_map", boom)
    second = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    summary = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h).json()
    assert summary["latest"]["id"] == second["run_id"]
    assert summary["latest"]["status"] == "failed"
    assert summary["last_completed"]["id"] == first["run_id"]
    assert summary["last_completed"]["result"]["citations_confirmed"] == len(w.codes)


@pytest.mark.unit
def test_a_completion_landing_between_the_reapers_read_and_its_update_stands(
    app_parts, monkeypatch
) -> None:
    """The reap is a compare-and-swap on RUNNING. A run that COMPLETED after
    the reaper read it as an orphan, and before its UPDATE, must not be
    overwritten FAILED."""
    import app.ai.runs as runs

    w, _runner = _deferred(app_parts)
    with w.sessions() as s:
        run = _competing_run(w, mode=LLMCallMode.FIXTURE)
        run.boot_id = "a-previous-process"
        s.add(run)
        s.commit()
        run_id = run.id
    fired: list[str] = []

    def complete_meanwhile() -> None:
        fired.append("completed")
        with w.sessions() as other:
            other.execute(
                update(AiRun)
                .where(AiRun.id == run_id)
                .values(status=AiRunStatus.COMPLETED, result={"landed": True})
            )
            other.commit()

    monkeypatch.setattr(runs, "_between_reap_read_and_update", complete_meanwhile)
    summary = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h).json()
    assert fired == ["completed"], "the race was not exercised"
    assert summary["running"] is None
    assert (summary["latest"]["status"], summary["latest"]["error_reason"]) == (
        "completed",
        None,
    ), summary["latest"]
    assert summary["latest"]["result"] == {"landed": True}


@pytest.mark.unit
def test_the_job_leaves_the_live_set_only_after_its_terminal_commit(app_parts, monkeypatch) -> None:
    """Out of the live set before the commit, a status read in the gap would
    reap a run about to complete. Pinned by reading the run's stored status,
    on another connection, at the moment the job leaves the live set."""
    import app.ai.runs as runs

    w, runner = _deferred(app_parts)
    real_done = runs._mark_done
    seen: list[str] = []

    def record_then_leave(run_id: uuid.UUID) -> None:
        with w.sessions() as other:
            seen.append(other.get(AiRun, run_id).status.value)
        real_done(run_id)

    monkeypatch.setattr(runs, "_mark_done", record_then_leave)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    assert seen == ["completed"], seen
    assert get_run(w.c, started["run_id"], w.h)["status"] == "completed"


# ---------------------------------------------------------------------------
# Review round 1 (199e9853): A1, A2, A3, A4, W1
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("mode", "expected"), [(LLMCallMode.LIVE, None), (LLMCallMode.FIXTURE, False)]
)
def test_a_reaped_run_with_no_committed_live_call_is_charged_unknown_not_no(
    app_parts, mode, expected
) -> None:
    """A1. `invoke` only flushes its row before the provider call, so a live
    call in flight when the api restarted leaves no committed row and may be
    billing. A LIVE run reaped with no committed live row is NOT KNOWN (None);
    only an offline run is definitely not charged."""
    w, _runner = _deferred(app_parts)
    with w.sessions() as s:
        run = _competing_run(w, mode=mode)
        run.boot_id = "a-previous-process"
        s.add(run)
        s.commit()
    latest = w.c.get(f"/ai-runs/services/{w.svc_id}", headers=w.h).json()["latest"]
    assert latest["error_reason"] == "run_orphaned", latest
    assert latest["charged_likely"] is expected, latest


@pytest.mark.unit
def test_a_reaped_runs_accounting_is_logged_voided_not_applied(app_parts, capsys) -> None:
    """A2. The accounting line is emitted after the completion commit; a run
    whose compare-and-swap misses logs it as `.voided`, never as applied."""
    w, runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    with w.sessions() as s:
        s.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(started["run_id"]))
            .values(status=AiRunStatus.FAILED, error_reason="run_deadline_exceeded")
        )
        s.commit()
    capsys.readouterr()
    assert runner.run_all() == 1
    out = capsys.readouterr().out
    assert '"attack.run_ai.citations_resolved.voided"' in out, out[-2000:]
    assert '"attack.run_ai.citations_resolved"' not in out


@pytest.mark.unit
def test_a_completed_runs_accounting_is_logged_after_its_commit(app_parts, capsys) -> None:
    w, runner = _deferred(app_parts)
    start_run(w.c, w.run_url, w.h)
    capsys.readouterr()
    assert runner.run_all() == 1
    out = capsys.readouterr().out
    assert '"attack.run_ai.citations_resolved"' in out
    assert '"attack.run_ai.citations_resolved.voided"' not in out


@pytest.mark.unit
def test_rows_skipped_edited_counts_rows_not_suggestions(app_parts) -> None:
    """A3. A model suggesting one edited technique twice is ONE row kept."""
    from app.models._common import utcnow

    w, runner = _deferred(app_parts)
    edited = w.codes[0]
    twice = (
        '{"technique_code": "' + edited + '", "status": "covered",'
        ' "detection_tools": ["CrowdStrike Falcon"]}'
    )

    def respond(payload: dict) -> LLMResponse:
        sent = set(payload.get("technique_codes") or [])
        body = f"{twice},{twice}" if edited in sent else ""
        return LLMResponse('{"techniques": [' + body + "]}")

    w.provider.register("mitre_map", respond)
    started = start_run(w.c, w.run_url, w.h)
    with w.sessions() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(w.coverage_ids[edited]))
            .values(status="gap", updated_at=utcnow())
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert run["result"]["rows_skipped_edited"] == 1, run["result"]["rows_skipped_edited"]


@pytest.mark.unit
def test_the_lock_states_the_deadline_plus_the_reapers_margin(app_parts) -> None:
    """A4. A run can hold the lock until `deadline_at + REAP_MARGIN`; every
    stated "until" is that, and the run reports it as `lock_until`."""
    from datetime import datetime

    from app.ai.runs import REAP_MARGIN

    w, _runner = _deferred(app_parts)
    started = start_run(w.c, w.run_url, w.h)
    run = get_run(w.c, started["run_id"], w.h)
    deadline = datetime.fromisoformat(run["deadline_at"].replace("Z", "+00:00"))
    until = datetime.fromisoformat(run["lock_until"].replace("Z", "+00:00"))
    assert until - deadline == REAP_MARGIN
    assert datetime.fromisoformat(started["lock_until"].replace("Z", "+00:00")) == until
    r = w.c.patch(
        f"/attack/coverage/{w.coverage_ids[w.codes[0]]}", headers=w.h, json={"notes": "x"}
    )
    assert r.status_code == 409, r.text
    assert until.strftime("%Y-%m-%d %H:%M UTC") in r.json()["error"]["message"]


@pytest.mark.unit
def test_a_discarded_drafts_run_does_not_describe_the_draft_that_replaced_it(
    app_parts,
) -> None:
    """W1. Disclosures are scoped to the assessment: after a run on a draft
    that is then discarded, the new draft's summary carries no run."""
    w, runner = _deferred(app_parts)
    start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    assert (
        w.c.post(f"/attack/assessments/{w.assessment_id}/discard", headers=w.h).status_code == 200
    )
    fresh = w.c.post(f"/attack/services/{w.svc_id}/assessments", headers=w.h).json()["id"]
    scoped = w.c.get(
        f"/ai-runs/services/{w.svc_id}", headers=w.h, params={"subject_id": fresh}
    ).json()
    assert (scoped["latest"], scoped["last_completed"]) == (None, None), scoped
    old = w.c.get(
        f"/ai-runs/services/{w.svc_id}", headers=w.h, params={"subject_id": w.assessment_id}
    ).json()
    assert old["last_completed"]["subject_id"] == w.assessment_id
