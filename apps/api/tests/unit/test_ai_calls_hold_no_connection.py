"""#1025: the AI framework holds no pooled connection of its own across a
provider call.

Measured on #1025 against Postgres: every background AI run held connections
for its whole life, and eight concurrent ordinary runs exhausted the production
pool for every tenant. Three holders were named:

1. the REQUEST's session (`runs.start_run` re-read the run, and `get_db`
   closes only after the background task);
2. the job session's read transaction, across the call;
3. `invoke`'s write transaction around the RUNNING `llm_calls` row, for the
   length of every provider call, in the job and in every batch worker.

This file pins 1 and 3, which release only what the framework itself opened.
Holder 2 means ending a CALLER's transaction and is held for the advisor
(#736 6210805139); the run test below therefore expects exactly one connection
left during a call, the job session's, and says so.

Every test drives a route or `invoke` itself. CI runs SQLite, so the counts are
of the SQLAlchemy pool, which is what ran out.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.ai.llm import LLMResponse
from app.models.llm_call import LLMCall, LLMCallStatus
from tests._ai_runs import attack_run_ai
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _admin,
    _seed_tech_debt_tools,
    app_client,
)

pytestmark = pytest.mark.unit


@dataclass
class PoolWatch:
    """Connections checked out of one engine's pool, live."""

    held: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def attach(self, engine) -> None:
        def _out(*_args) -> None:
            with self.lock:
                self.held += 1

        def _in(*_args) -> None:
            with self.lock:
                self.held -= 1

        event.listen(engine, "checkout", _out)
        event.listen(engine, "checkin", _in)

    def now(self) -> int:
        with self.lock:
            return self.held


def _recording(cls_list: list[Session]) -> type[Session]:
    class _Recorded(Session):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            cls_list.append(self)

    return _Recorded


@dataclass
class Sample:
    held: int
    request_in_txn: bool
    workers_in_txn: bool
    running_rows_visible: int


def _attack_world(app_client, monkeypatch):  # noqa: F811
    """A batched ATT&CK run, one worker so batches run one at a time and a
    sample never catches a sibling mid-commit. Records the request sessions the
    app opens and the batch workers' sessions."""
    from app.ai import batching
    from app.db.session import get_db
    from app.routes import attack as attack_routes

    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    coverage = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"]

    request_sessions: list[Session] = []

    def _recorded_get_db():
        db = TestSession()
        request_sessions.append(db)
        try:
            yield db
        finally:
            db.close()

    c.app.dependency_overrides[get_db] = _recorded_get_db
    worker_sessions: list[Session] = []
    monkeypatch.setattr(batching, "Session", _recording(worker_sessions))
    watch = PoolWatch()
    watch.attach(TestSession.kw["bind"])
    samples: list[Sample] = []

    def _answer(payload: dict) -> LLMResponse:
        with TestSession() as probe:
            running = probe.execute(
                select(func.count())
                .select_from(LLMCall)
                .where(LLMCall.status == LLMCallStatus.RUNNING)
            ).scalar_one()
        samples.append(
            Sample(
                # Read after the probe closed, so it counts only the others.
                held=watch.now(),
                request_in_txn=any(s.in_transaction() for s in request_sessions),
                workers_in_txn=any(s.in_transaction() for s in worker_sessions),
                running_rows_visible=running,
            )
        )
        entries = [
            {
                "technique_code": t,
                "status": "gap",
                "detection_tools": [],
                "prevention_tools": [],
                "response_tools": [],
                "rationale": "x",
            }
            for t in payload.get("technique_codes") or []
        ]
        return LLMResponse(json.dumps({"techniques": entries}))

    provider.register("mitre_map", _answer)
    return c, h, svc_id, standalone_rows(coverage, 1), samples, request_sessions


def test_the_request_session_holds_nothing_while_the_run_calls_the_provider(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    """Holder 1: the session of the request that started the run."""
    c, h, svc_id, rows, samples, request_sessions = _attack_world(app_client, monkeypatch)
    result = attack_run_ai(c, svc_id, h)
    assert result["batches_total"] > 1, "setup: a batched run"
    assert len(samples) == result["batches_total"], samples
    assert request_sessions, "setup: the request sessions were recorded"
    assert not any(s.request_in_txn for s in samples), samples


def test_no_batch_worker_holds_a_transaction_during_its_call_and_the_ledger_row_is_committed(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    """Holder 3: the RUNNING `llm_calls` row is committed before egress, from
    its own short session, so no worker holds a write open during the call,
    and the row is evidence another session can already read."""
    c, h, svc_id, rows, samples, _ = _attack_world(app_client, monkeypatch)
    result = attack_run_ai(c, svc_id, h)
    assert len(samples) == result["batches_total"] > 1, samples
    assert not any(s.workers_in_txn for s in samples), samples
    assert all(s.running_rows_visible == 1 for s in samples), samples
    # And every row was finalized afterwards.
    with app_client[1]() as db:
        statuses = db.execute(select(LLMCall.status)).scalars().all()
    assert statuses and set(statuses) == {LLMCallStatus.COMPLETED}, statuses


def test_a_run_holds_only_the_job_sessions_connection_during_a_call(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    """Measured on main: 3 per call (request, job, worker). With holders 1 and
    3 released, the job session's read is the one left, until the advisor
    rules on holder 2 (#736 6210805139)."""
    c, h, svc_id, rows, samples, _ = _attack_world(app_client, monkeypatch)
    result = attack_run_ai(c, svc_id, h)
    assert len(samples) == result["batches_total"] > 1, samples
    assert [s.held for s in samples] == [1] * len(samples), samples


def _invoke_world(app_client):  # noqa: F811
    from app.ai.llm import LLMClient
    from app.models.client import Client

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    return TestSession, provider, LLMClient(provider), uuid.UUID(me["id"]), uuid.UUID(cid), Client


def _visible_running(TestSession) -> int:
    with TestSession() as other:
        return other.execute(
            select(func.count()).select_from(LLMCall).where(LLMCall.status == LLMCallStatus.RUNNING)
        ).scalar_one()


def test_a_caller_that_wrote_keeps_its_transaction_and_the_ledger_row_in_it(
    app_client,  # noqa: F811
) -> None:
    """`invoke` never commits a caller's write: that would break the caller's
    atomicity. With a write pending it keeps today's path, the RUNNING row in
    the caller's own transaction (not yet visible to others), and a rollback
    takes both away."""
    TestSession, provider, llm, user_id, cid, Client = _invoke_world(app_client)
    seen: list[int] = []
    provider.register(
        "conn_probe",
        lambda payload: (seen.append(_visible_running(TestSession)), LLMResponse("{}"))[1],
    )
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        client.legal_name = "Renamed mid-call"
        db.flush()
        llm.invoke(db, purpose="conn_probe", prompt="p", payload={}, requested_by=user_id)
        db.rollback()
    assert seen == [0], seen
    with TestSession() as other:
        name = other.execute(select(Client.legal_name).where(Client.id == cid)).scalar_one()
        calls = other.execute(select(func.count()).select_from(LLMCall)).scalar_one()
    assert (name, calls) == ("Acme", 0)


def test_a_caller_that_has_not_written_gets_a_committed_ledger_row(
    app_client,  # noqa: F811
) -> None:
    """Holder 3 through `invoke` itself: the RUNNING row is visible to another
    session during the call, survives the caller's rollback (it is evidence a
    call was made), and is finalized as COMPLETED."""
    TestSession, provider, llm, user_id, cid, Client = _invoke_world(app_client)
    seen: list[int] = []
    provider.register(
        "conn_probe",
        lambda payload: (seen.append(_visible_running(TestSession)), LLMResponse("{}"))[1],
    )
    with TestSession() as db:
        _response, row = llm.invoke(
            db, purpose="conn_probe", prompt="p", payload={}, requested_by=user_id
        )
        db.rollback()
    assert seen == [1], seen
    assert (row.status, row.purpose) == (LLMCallStatus.COMPLETED, "conn_probe")
    with TestSession() as other:
        stored = other.execute(select(LLMCall.status)).scalars().all()
    assert stored == [LLMCallStatus.COMPLETED], stored


def test_a_failed_call_from_a_caller_that_has_not_written_is_recorded_failed(
    app_client,  # noqa: F811
) -> None:
    TestSession, provider, llm, user_id, cid, Client = _invoke_world(app_client)

    def _boom(payload: dict) -> LLMResponse:
        raise RuntimeError("provider closed the connection")

    provider.register("conn_probe", _boom)
    with TestSession() as db:
        with pytest.raises(RuntimeError):
            llm.invoke(db, purpose="conn_probe", prompt="p", payload={}, requested_by=user_id)
        db.rollback()
    with TestSession() as other:
        rows = other.execute(select(LLMCall.status, LLMCall.error_message)).all()
    assert [r.status for r in rows] == [LLMCallStatus.FAILED], rows
    assert "provider closed the connection" in rows[0].error_message
