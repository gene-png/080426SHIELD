"""#1025: no pooled database connection is held across a provider call.

Measured on #1025 against Postgres: every background AI run held two
connections for its whole life (the request's session, and the job session's
open transaction), and `invoke` held a third, a write transaction around the
RUNNING `llm_calls` row, for the length of every provider call, in every
batch worker. Eight concurrent ordinary runs exhausted the production pool for
every tenant, and some runs failed.

These tests count connections checked out of the test engine's pool, from its
own `checkout`/`checkin` events, at the moment the provider is called. CI runs
SQLite, so this measures the SQLAlchemy pool, not database backends; the pool
is what ran out. Every test drives a route.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field

import pytest
from sqlalchemy import event

from app.ai.llm import LLMResponse
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
    seen_during_calls: list[int] = field(default_factory=list)

    def attach(self, engine) -> None:
        def _out(*_args) -> None:
            with self.lock:
                self.held += 1

        def _in(*_args) -> None:
            with self.lock:
                self.held -= 1

        event.listen(engine, "checkout", _out)
        event.listen(engine, "checkin", _in)

    def sample(self) -> None:
        with self.lock:
            self.seen_during_calls.append(self.held)


def _attack_world(app_client):  # noqa: F811
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    coverage = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"]
    watch = PoolWatch()
    watch.attach(TestSession.kw["bind"])
    return c, provider, h, svc_id, standalone_rows(coverage, 1), watch


def test_an_attack_run_holds_no_connection_while_the_provider_answers(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    """The request's session, the job's session and every batch worker's
    session: none of them holds a connection during a provider call.

    One worker, so batches run one at a time and a sample cannot catch a
    sibling batch committing its own ledger row."""
    from app.routes import attack as attack_routes

    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)
    c, provider, h, svc_id, rows, watch = _attack_world(app_client)
    code = rows[0]["technique_code"]

    def _answer(payload: dict) -> LLMResponse:
        watch.sample()
        asked = payload.get("technique_codes") or []
        entries = [
            {
                "technique_code": t,
                "status": "gap",
                "detection_tools": [],
                "prevention_tools": [],
                "response_tools": [],
                "rationale": "x",
            }
            for t in asked
        ]
        return LLMResponse(json.dumps({"techniques": entries}))

    provider.register("mitre_map", _answer)
    result = attack_run_ai(c, svc_id, h)
    assert result["batches_total"] > 1, "setup: a batched run"
    assert len(watch.seen_during_calls) == result["batches_total"], watch.seen_during_calls
    assert code in {t["technique_code"] for t in result["coverage"] if t["status"]}
    # Nothing holds a connection while any batch's provider call is in flight.
    assert max(watch.seen_during_calls) == 0, watch.seen_during_calls


def _invoke_world(app_client):  # noqa: F811
    from app.ai.llm import LLMClient

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    watch = PoolWatch()
    watch.attach(TestSession.kw["bind"])
    return TestSession, provider, LLMClient(provider), me["id"], cid, watch


def test_a_caller_that_only_read_does_not_hold_its_connection_across_the_call(
    app_client,  # noqa: F811
) -> None:
    """#1026 / #1027's shape: a synchronous route read, then called the AI."""
    import uuid

    from sqlalchemy import select

    from app.models.client import Client

    TestSession, provider, llm, user_id, cid, watch = _invoke_world(app_client)

    def _answer(payload: dict) -> LLMResponse:
        watch.sample()
        return LLMResponse('{"ok": true}')

    provider.register("conn_probe", _answer)
    with TestSession() as db:
        db.execute(select(Client).where(Client.id == uuid.UUID(cid))).scalar_one()
        assert db.in_transaction(), "setup: the caller holds an open read"
        llm.invoke(
            db,
            purpose="conn_probe",
            prompt="p",
            payload={},
            requested_by=uuid.UUID(user_id),
        )
        db.commit()
    assert watch.seen_during_calls == [0], watch.seen_during_calls


def test_a_caller_that_wrote_keeps_its_transaction_uncommitted(app_client) -> None:  # noqa: F811
    """`invoke` must never commit a caller's write: that would break the
    caller's atomicity. The write stays invisible to others until the caller
    commits, and is gone if the caller rolls back."""
    import uuid

    from sqlalchemy import select

    from app.models.client import Client

    TestSession, provider, llm, user_id, cid, watch = _invoke_world(app_client)
    provider.register("conn_probe", lambda payload: LLMResponse('{"ok": true}'))
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == uuid.UUID(cid))).scalar_one()
        client.legal_name = "Renamed mid-call"
        db.flush()
        llm.invoke(
            db,
            purpose="conn_probe",
            prompt="p",
            payload={},
            requested_by=uuid.UUID(user_id),
        )
        db.rollback()
    with TestSession() as other:
        name = other.execute(select(Client.legal_name).where(Client.id == uuid.UUID(cid)))
        assert name.scalar_one() == "Acme"
