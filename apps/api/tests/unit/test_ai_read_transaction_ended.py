"""#1025 holder 2 (advisor, #736 6216024281, 3e): every AI caller ends its READ
transaction before its provider call, so it holds no pooled connection while
the provider answers; and a provider call inside a transaction holding a
FOR UPDATE lock is refused.

The callers: the ATT&CK run (first pass and re-ask), the ATT&CK what-if run
and its parse route (#1027), the ZT run, the CSF run, Risk generate (#1026)
and the Tech Debt extraction. Each is driven through its route or run, and
the connections checked out of the pool are counted WHILE the provider is
being called (`FixtureProvider.complete`, wrapped). Every caller holds none.
Each count goes to 1 with that caller's `end_read_transaction` line removed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from sqlalchemy import select, update

from app.ai.llm import LLMResponse
from app.ai.session_marks import end_read_transaction
from tests._pool_count import pool_count, sampling_provider_calls
from tests.unit.test_ai_calls_hold_no_connection import _invoke_world
from tests.unit.test_attack_run_ai import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


@pytest.fixture
def held_during_calls(monkeypatch) -> Iterator[list[int]]:
    with sampling_provider_calls(monkeypatch) as samples:
        yield samples


# --- the helper and the guard ------------------------------------------------------


def test_ending_a_read_keeps_what_was_loaded_and_holds_nothing(app_client) -> None:  # noqa: F811
    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with pool_count() as held, TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        assert (db.in_transaction(), held[0]) == (True, 1), "setup: an open read"
        end_read_transaction(db, where="test")
        # Loaded attributes stay loaded: reading one opens nothing behind it.
        assert client.legal_name == "Acme"
        assert (db.in_transaction(), held[0]) == (False, 0)


@pytest.mark.parametrize("how", ["pending", "flushed", "statement"])
def test_a_transaction_that_wrote_is_refused_and_left_as_it_was(
    app_client, how: str  # noqa: F811
) -> None:
    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        if how == "statement":
            db.execute(update(Client).where(Client.id == cid).values(legal_name="Changed"))
        else:
            client.legal_name = "Changed"
            if how == "flushed":
                db.flush()
        with pytest.raises(RuntimeError, match=r"^the-caller: the session has written"):
            end_read_transaction(db, where="the-caller")
        assert db.in_transaction(), "the write is neither committed nor rolled back"
        db.rollback()
    with TestSession() as other:
        name = other.execute(select(Client.legal_name).where(Client.id == cid)).scalar_one()
    assert name == "Acme"


def test_a_mark_ends_with_its_transaction_and_a_later_read_on_the_same_session_is_clean(
    app_client,  # noqa: F811
) -> None:
    """A long-lived session (a measure script runs several extractions on one)
    that once wrote, or once took FOR UPDATE, must not carry that mark into
    its next transaction: the marks clear when the outermost one ends."""
    from app.ai.session_marks import holds_for_update

    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        client.legal_name = "Committed"
        db.commit()
        db.execute(select(Client).where(Client.id == cid).with_for_update()).scalar_one()
        assert holds_for_update(db), "setup: the lock is marked"
        db.rollback()
        db.execute(select(Client).where(Client.id == cid)).scalar_one()
        assert db.in_transaction(), "setup: a new read is open"
        assert not holds_for_update(db)
        end_read_transaction(db, where="test")
        assert not db.in_transaction()


def test_a_provider_call_inside_a_for_update_lock_is_refused_before_anything(
    app_client,  # noqa: F811
) -> None:
    from app.models.llm_call import LLMCall

    TestSession, provider, llm, user_id, cid, Client = _invoke_world(app_client)
    called: list[dict] = []
    provider.register("lock_probe", lambda p: (called.append(p), LLMResponse("{}"))[1])
    with TestSession() as db:
        db.execute(select(Client).where(Client.id == cid).with_for_update()).scalar_one()
        with pytest.raises(RuntimeError, match="holds a FOR UPDATE lock"):
            llm.invoke(db, purpose="lock_probe", prompt="p", payload={}, requested_by=user_id)
        db.rollback()
        # The positive control: the same call, the lock released, goes through.
        llm.invoke(db, purpose="lock_probe", prompt="p", payload={}, requested_by=user_id)
        db.commit()
    assert len(called) == 1, called
    with TestSession() as other:
        assert len(other.execute(select(LLMCall)).scalars().all()) == 1


# --- every caller, through its route or run ----------------------------------------


def test_the_attack_run_holds_no_connection_during_any_call(
    app_client, monkeypatch, held_during_calls  # noqa: F811
) -> None:
    """First pass AND re-ask: the first pass answers nothing for half the
    techniques, so the run asks again, after re-reading the rows' locks."""
    from app.routes import attack as attack_routes
    from tests._ai_runs import attack_run_ai
    from tests.unit.test_attack_run_ai import _admin, _seed_tech_debt_tools

    # One batch at a time, so a sample never counts a sibling batch's own
    # short ledger session mid-commit (as `test_ai_calls_hold_no_connection`).
    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    assert c.post(f"/attack/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
    asked_twice: list[str] = []
    seen: set[str] = set()

    def _answer(payload: dict) -> LLMResponse:
        asked = payload.get("technique_codes") or []
        again = [code for code in asked if code in seen]
        asked_twice.extend(again)
        seen.update(asked)
        keep = again or asked[: len(asked) // 2]
        entries = [
            {
                "technique_code": code,
                "status": "gap",
                "detection_tools": [],
                "prevention_tools": [],
                "response_tools": [],
                "rationale": "x",
            }
            for code in keep
        ]
        return LLMResponse(json.dumps({"techniques": entries}))

    provider.register("mitre_map", _answer)
    attack_run_ai(c, svc_id, h)
    assert asked_twice, "setup: the run asked again"
    assert held_during_calls and set(held_during_calls) == {0}, held_during_calls
