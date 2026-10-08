"""csf_score in batches (#479), through CSF's Run-AI endpoint.

A full Working Profile is 106 subcategories x 3 tiers = 318 (tier,
subcategory) rows. One call over all of them could not fit any provider's
output cap, so the run splits them.

The cap these tests hold the batches to is derived from the PROVIDERS, not from
the code under test. Every figure is restated here, from its source:

* 8192 output tokens: the non-streamed adapters' cap for csf_score
  (`non_streamed_output_cap`, `app/ai/llm.py`);
* 2048 of those spent on thinking by gemini-2.5+ on Gemini and Vertex
  (`_THINKING_BUDGET_TOKENS`, the same file);
* ~575 output tokens per row: a mitre_map row as measured live on 2026-08-07
  (the comment above `_MITRE_BATCH_SIZE`, `routes/attack.py`), the high
  estimate the `llm.py` comment gives for a csf_score row.

So at most (8192 - 2048) / 575 = 10.7, i.e. 10, rows a batch.

The fixture answers are written from the PROMPT ("for every subcategory code
emit one row per tier listed in tiers"), never from the parser's constants.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.llm_call import LLMCall
from tests._ai_runs import csf_run_ai, defer_runs, get_run, start_run

# The provider figures above, restated rather than imported (see the docstring).
_NON_STREAMED_CAP = 8192
_GEMINI_THINKING_BUDGET = 2048
_HIGH_TOKENS_PER_ROW = 575
_TIERS = ["high", "low", "moderate"]


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-csfbatch.db'}"
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
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.csf import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with sessions() as seed:
        tenant = Client(legal_name="Test Tenant")
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc_id = c.post(
            "/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}
        ).json()["id"]
        a = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": _TIERS})
        assert seeded.status_code in (200, 201), seeded.text
        yield World(c, sessions, provider, h, svc_id)


def _rows_asked(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """The (tier, subcategory) rows a payload asks for, as the prompt defines
    them: one row per tier listed, for every subcategory code."""
    return [(t, code) for t in payload["tiers"] for code in payload["subcategories"]]


def _answer_as_the_prompt_asks(payload: dict[str, Any]) -> LLMResponse:
    scores = [
        {
            "tier": t,
            "subcategory_code": code,
            "governance": 1,
            "policy": 1,
            "implementation": 1,
            "monitoring": 1,
            "improvement": 1,
            "what_we_found": "Drafted.",
        }
        for t, code in _rows_asked(payload)
    ]
    return LLMResponse(json.dumps({"scores": scores, "executive_summary": "Draft."}))


class _Recorder:
    """Records every payload the provider receives, from every batch thread."""

    def __init__(self, fail_when=None) -> None:
        self.payloads: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._fail_when = fail_when

    def __call__(self, payload: dict[str, Any]) -> LLMResponse:
        with self._lock:
            self.payloads.append(payload)
        if self._fail_when is not None and self._fail_when(payload):
            raise RuntimeError("provider closed the connection")
        return _answer_as_the_prompt_asks(payload)


def _profile_rows(world: World) -> list[tuple[str, str]]:
    out = []
    for tier in _TIERS:
        rows = world.c.get(f"/csf/services/{world.svc_id}/profile/{tier}", headers=world.h)
        assert rows.status_code == 200, rows.text
        out += [(tier, r["subcategory_code"]) for r in rows.json()["rows"]]
    return out


@pytest.mark.unit
def test_a_full_working_profile_is_asked_for_in_batches_no_larger_than_the_cap(world) -> None:
    profile = _profile_rows(world)
    assert len(profile) == 318, "the Working Profile this test is about"
    rec = _Recorder()
    world.provider.register("csf_score", rec)

    result = csf_run_ai(world.c, world.svc_id, world.h)

    # Each tier's 106 subcategories in tens: 11 batches a tier, 33 in all.
    assert len(rec.payloads) == 33
    assert result["batches_total"] == 33
    assert result["batches_failed"] == 0
    cap_rows = (_NON_STREAMED_CAP - _GEMINI_THINKING_BUDGET) // _HIGH_TOKENS_PER_ROW
    assert cap_rows == 10
    for p in rec.payloads:
        asked = _rows_asked(p)
        assert 0 < len(asked) <= cap_rows, (len(asked), p["tiers"])
        assert len(asked) * _HIGH_TOKENS_PER_ROW <= _NON_STREAMED_CAP - _GEMINI_THINKING_BUDGET
    # Every row asked for exactly once: none lost between batches, none twice.
    asked_all = [r for p in rec.payloads for r in _rows_asked(p)]
    assert sorted(asked_all) == sorted(profile)
    # Every value of every row is accounted for, as in the single-call run.
    assert result["suggestions_received"] == 318 * 6
    assert result["suggestions_applied"] == 318 * 6
    assert result["dropped"] == []


@pytest.mark.unit
def test_every_batch_carries_the_interview_answers(world) -> None:
    rows = world.c.get(f"/csf/services/{world.svc_id}/assessments/latest", headers=world.h).json()
    answer = rows["answers"][0]
    r = world.c.patch(
        f"/csf/answers/{answer['id']}",
        headers=world.h,
        json={"maturity_tier": 3, "notes": "Documented policy exists."},
    )
    assert r.status_code == 200, r.text
    rec = _Recorder()
    world.provider.register("csf_score", rec)

    csf_run_ai(world.c, world.svc_id, world.h)

    assert len(rec.payloads) == 33
    for p in rec.payloads:
        assert p["answers"][answer["subcategory_code"]]["maturity_tier"] == 3


@pytest.mark.unit
def test_a_failed_batch_leaves_a_partial_run_that_says_so(world) -> None:
    profile = _profile_rows(world)
    first_low = sorted(code for t, code in profile if t == "low")[0]

    def _fails(payload: dict[str, Any]) -> bool:
        return payload["tiers"] == ["low"] and first_low in payload["subcategories"]

    rec = _Recorder(fail_when=_fails)
    world.provider.register("csf_score", rec)

    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    assert run["status"] == "completed", run
    assert run["batches_total"] == 33
    assert run["batches_failed"] == 1
    result = run["result"]
    assert result["batches_total"] == 33
    assert result["batches_failed"] == 1
    lost = [p for p in rec.payloads if _fails(p)]
    assert len(lost) == 1
    lost_rows = set(_rows_asked(lost[0]))
    assert len(lost_rows) == 10
    # The 308 rows that came back are applied; the 10 that did not are left as
    # they were, and are not counted as received or dropped -- the model never
    # answered for them. The batch count is what says they are missing.
    assert result["suggestions_received"] == 308 * 6
    assert result["suggestions_applied"] == 308 * 6
    untouched = [
        r
        for r in result["rows"]
        if (r["tier"], r["subcategory_code"]) in lost_rows and r["what_we_found"] is None
    ]
    assert len(untouched) == 10
    # The failed call is on record, as every billable call is.
    with world.sessions() as s:
        calls = s.execute(select(LLMCall).where(LLMCall.purpose == "csf_score")).scalars().all()
    assert len(calls) == 33
    assert sum(1 for c in calls if c.status.value.lower() == "failed") == 1


@pytest.mark.unit
def test_every_batch_failing_fails_the_run_with_the_providers_reason(world) -> None:
    rec = _Recorder(fail_when=lambda _p: True)
    world.provider.register("csf_score", rec)

    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    run = get_run(world.c, started["run_id"], world.h)

    assert run["status"] == "failed", run
    assert run["error_reason"] == "ai_call_failed"
    assert len(rec.payloads) == 33


def _row_entry(tier: str, code: str, value: int) -> dict[str, Any]:
    return {
        "tier": tier,
        "subcategory_code": code,
        "governance": value,
        "policy": value,
        "implementation": value,
        "monitoring": value,
        "improvement": value,
        "what_we_found": f"Answered with {value}.",
    }


@pytest.mark.unit
def test_a_row_answered_by_a_batch_that_did_not_ask_for_it_is_dropped_and_said(world) -> None:
    """A model asked about ten rows may answer an eleventh. That row belongs to
    another batch, which answers it too. It must be applied ONCE, from the
    batch that asked, and the stray answer dropped with a reason a reader
    sees -- never applied twice, never applied silently from the wrong batch."""
    profile = _profile_rows(world)
    high = sorted(code for t, code in profile if t == "high")
    stray = ("high", high[-1])  # asked by the LAST high batch

    def _answer(payload: dict[str, Any]) -> LLMResponse:
        scores = [_row_entry(t, c, 1) for t, c in _rows_asked(payload)]
        if payload["tiers"] == ["high"] and high[0] in payload["subcategories"]:
            scores.append(_row_entry(*stray, 2))  # not this batch's row
        return LLMResponse(json.dumps({"scores": scores}))

    world.provider.register("csf_score", _answer)
    result = csf_run_ai(world.c, world.svc_id, world.h)

    row = next(r for r in result["rows"] if (r["tier"], r["subcategory_code"]) == stray)
    assert row["governance"] == 1, "applied from the batch that asked, not the stray"
    assert row["what_we_found"] == "Answered with 1."
    stray_drops = [d for d in result["dropped"] if d["key"] == "|".join(stray)]
    assert [d["reason"] for d in stray_drops] == ["not_in_batch"]
    assert stray_drops[0]["values"] == 6
    assert result["suggestions_received"] == 319 * 6
    assert result["suggestions_applied"] == 318 * 6
    accounted = result["suggestions_applied"] + sum(d["values"] for d in result["dropped"])
    assert result["suggestions_received"] == accounted


@pytest.mark.unit
def test_every_batch_answering_the_same_rows_applies_each_once_and_counts_the_rest(
    world,
) -> None:
    """The old single-call fixture shape, as a misbehaving model: every batch
    answers the same two rows. Each is applied once, from the batch that asked
    for it; the 32 other copies are dropped as not asked, and counted."""
    profile = _profile_rows(world)
    high = sorted(code for t, code in profile if t == "high")
    canned = [_row_entry("high", high[0], 2), _row_entry("high", high[-1], 2)]
    world.provider.register_static("csf_score", LLMResponse(json.dumps({"scores": canned})))

    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert result["batches_total"] == 33
    assert result["suggestions_received"] == 33 * 2 * 6
    assert result["suggestions_applied"] == 2 * 6
    reasons = {d["reason"] for d in result["dropped"]}
    assert reasons == {"not_in_batch"}
    assert sum(d["values"] for d in result["dropped"]) == 32 * 2 * 6
    for code in (high[0], high[-1]):
        row = next(
            r for r in result["rows"] if (r["tier"], r["subcategory_code"]) == ("high", code)
        )
        assert row["governance"] == 2


# --- #836: a row the model leaves out of its own batch is counted ------------
# The prompt asks for every (tier, subcategory) row in the batch ("Score EACH
# in-scope (tier, subcategory) pair: for every subcategory code emit one row per
# tier listed"). A row a batch was asked for and did not answer keeps its
# previous values; the run must say so, per row. The truth table is #736
# comment 6067124922: R sent, F batch failed, A an entry names it, V a valid
# value applied, P a prior value stored. Each test names its row.


def _omit(rows: set[tuple[str, str]], *, extra=None):
    """Answer as the prompt asks, except for `rows`, which no entry names.
    `extra(payload)` may add entries (a stray, an out-of-range value)."""

    def _answer(payload: dict[str, Any]) -> LLMResponse:
        scores = [_row_entry(t, c, 1) for t, c in _rows_asked(payload) if (t, c) not in rows]
        if extra is not None:
            scores += extra(payload)
        return LLMResponse(json.dumps({"scores": scores}))

    return _answer


def _batch_codes(world: World, tier: str) -> list[str]:
    return sorted(code for t, code in _profile_rows(world) if t == tier)


def _row(result: dict[str, Any], key: tuple[str, str]) -> dict[str, Any]:
    return next(r for r in result["rows"] if (r["tier"], r["subcategory_code"]) == key)


def _omitted(result: dict[str, Any]) -> list[tuple[str, str]]:
    return [(r["tier"], r["subcategory_code"]) for r in result["omitted_rows"]]


def _identity_holds(result: dict[str, Any]) -> bool:
    accounted = result["suggestions_applied"] + sum(d["values"] for d in result["dropped"])
    return result["suggestions_received"] == accounted


@pytest.mark.unit
def test_rows_a_batch_leaves_out_are_counted_and_named(world) -> None:
    """Truth-table rows 5 (left out, nothing stored) and 8 (answered, applied)."""
    profile = _profile_rows(world)
    high = _batch_codes(world, "high")
    left_out = {("high", high[0]), ("high", high[1]), ("high", high[2])}
    world.provider.register("csf_score", _omit(left_out))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert result["omitted_count"] == 3
    assert set(_omitted(result)) == left_out
    for key in left_out:
        row = _row(result, key)
        assert row["governance"] == 0 and row["what_we_found"] is None, "left out, kept"
    assert _row(result, ("high", high[3]))["governance"] == 1, "answered, applied"
    # The W1 identity is about values SENT, and an omitted row sent none.
    assert _identity_holds(result)
    assert result["suggestions_received"] == (len(profile) - 3) * 6
    assert result["dropped"] == []


@pytest.mark.unit
def test_a_row_left_out_keeps_the_value_an_earlier_run_set_and_is_counted(world) -> None:
    """Truth-table row 6: a prior value this run did not confirm is still
    omitted, and the row keeps that value."""
    high = _batch_codes(world, "high")
    target = ("high", high[0])
    world.provider.register("csf_score", _omit(set()))
    first = csf_run_ai(world.c, world.svc_id, world.h)
    assert first["omitted_count"] == 0
    assert _row(first, target)["governance"] == 1

    world.provider.register("csf_score", _omit({target}))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert result["omitted_count"] == 1
    assert _omitted(result) == [target]
    assert _row(result, target)["governance"] == 1
    assert _row(result, target)["what_we_found"] == "Answered with 1."
    assert _identity_holds(result)


@pytest.mark.unit
def test_a_row_answered_with_a_bad_value_is_refused_not_omitted(world) -> None:
    """Truth-table row 7: an entry that names the row is an answer, even when
    its value is then refused. The loss is itemized once, under its reason."""
    high = _batch_codes(world, "high")
    target = ("high", high[0])

    def _bad(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if high[0] in payload["subcategories"] and payload["tiers"] == ["high"]:
            return [{**_row_entry(*target, 1), "governance": 9}]
        return []

    world.provider.register("csf_score", _omit({target}, extra=_bad))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert result["omitted_count"] == 0
    assert result["omitted_rows"] == []
    reasons = [d["reason"] for d in result["dropped"] if d.get("key") == "|".join(target)]
    assert reasons == ["out_of_range"]
    assert _identity_holds(result)


@pytest.mark.unit
def test_an_entry_naming_no_row_is_unknown_and_omits_nothing(world) -> None:
    """Truth-table row 2: a key nobody asked for is `unknown_key`; it is not
    a row, so it cannot be omitted, and every asked row was answered."""
    high = _batch_codes(world, "high")

    def _unknown(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload["tiers"] == ["high"] and high[0] in payload["subcategories"]:
            return [_row_entry("high", "ZZ.ZZ-99", 1)]
        return []

    world.provider.register("csf_score", _omit(set(), extra=_unknown))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert [d["reason"] for d in result["dropped"]] == ["unknown_key"]
    assert result["omitted_count"] == 0
    assert result["omitted_rows"] == []
    assert _identity_holds(result)


@pytest.mark.unit
def test_a_row_answered_only_by_another_batch_is_still_omitted(world) -> None:
    """A stray answer from the wrong batch is `not_in_batch` and is never an
    answer for the row: the batch that was asked still left it out."""
    high = _batch_codes(world, "high")
    target = ("high", high[-1])  # asked by the LAST high batch

    def _stray(payload: dict[str, Any]) -> list[dict[str, Any]]:
        if payload["tiers"] == ["high"] and high[0] in payload["subcategories"]:
            return [_row_entry(*target, 2)]
        return []

    world.provider.register("csf_score", _omit({target}, extra=_stray))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert [d["reason"] for d in result["dropped"] if d.get("key") == "|".join(target)] == [
        "not_in_batch"
    ]
    assert result["omitted_count"] == 1
    assert _omitted(result) == [target]
    assert _row(result, target)["governance"] == 0, "never written from the wrong batch"
    assert _identity_holds(result)


@pytest.mark.unit
@pytest.mark.parametrize("prior", [False, True], ids=["nothing-stored", "prior-stored"])
def test_a_failed_batchs_rows_are_counted_as_failed_not_omitted(world, prior) -> None:
    """Truth-table rows 3 and 4: a failed batch's rows are `batches_failed`'s
    only, whatever they held, and the run reports no omission for them."""
    low = _batch_codes(world, "low")
    if prior:
        world.provider.register("csf_score", _omit(set()))
        assert csf_run_ai(world.c, world.svc_id, world.h)["omitted_count"] == 0

    def _fails(payload: dict[str, Any]) -> bool:
        return payload["tiers"] == ["low"] and low[0] in payload["subcategories"]

    world.provider.register("csf_score", _Recorder(fail_when=_fails))
    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    result = get_run(world.c, started["run_id"], world.h)["result"]

    assert result["batches_failed"] == 1
    assert result["omitted_count"] == 0
    assert result["omitted_rows"] == []
    assert _row(result, ("low", low[0]))["governance"] == (1 if prior else 0)


@pytest.mark.unit
def test_a_locked_row_left_out_is_not_counted(world) -> None:
    high = _batch_codes(world, "high")
    rows = world.c.get(f"/csf/services/{world.svc_id}/profile/high", headers=world.h).json()
    sid = next(r["id"] for r in rows["rows"] if r["subcategory_code"] == high[0])
    locked = world.c.patch(f"/csf/dimension-scores/{sid}", headers=world.h, json={"locked": True})
    assert locked.status_code == 200, locked.text
    world.provider.register("csf_score", _omit({("high", high[0]), ("high", high[1])}))
    result = csf_run_ai(world.c, world.svc_id, world.h)

    assert result["omitted_count"] == 1
    assert _omitted(result) == [("high", high[1])]


@pytest.mark.unit
def test_a_row_edited_during_the_run_and_left_out_is_counted(world) -> None:
    """The model sent nothing for it, so "got no answer from the AI" stays
    true (approved on #736, comment 6067815887). The row keeps the
    consultant's edit. The run is held, as `test_ai_runs_csf.py` holds it, so
    the edit lands after the run started and before its batches answer."""
    from app.models._common import utcnow
    from app.models.csf_profile import CsfDimensionScore

    high = _batch_codes(world, "high")
    target = ("high", high[0])
    rows = world.c.get(f"/csf/services/{world.svc_id}/profile/high", headers=world.h).json()
    sid = next(r["id"] for r in rows["rows"] if r["subcategory_code"] == high[0])
    runner = defer_runs(world.c.app)
    world.provider.register("csf_score", _omit({target}))
    started = start_run(world.c, f"/csf/services/{world.svc_id}/run-ai", world.h)
    with world.sessions() as s:
        s.execute(
            update(CsfDimensionScore)
            .where(CsfDimensionScore.id == uuid.UUID(sid))
            .values(governance=2, updated_at=utcnow())
        )
        s.commit()
    assert runner.run_all() == 1
    run = get_run(world.c, started["run_id"], world.h)
    assert run["status"] == "completed", run
    result = run["result"]

    assert result["omitted_count"] == 1
    assert _omitted(result) == [target]
    assert _row(result, target)["governance"] == 2, "the consultant's edit stands"


@pytest.mark.unit
def test_the_audit_row_carries_the_omitted_count_and_no_codes(world) -> None:
    from app.models.audit_entry import AuditEntry

    high = _batch_codes(world, "high")
    world.provider.register("csf_score", _omit({("high", high[0]), ("high", high[1])}))
    csf_run_ai(world.c, world.svc_id, world.h)

    with world.sessions() as s:
        entry = s.execute(select(AuditEntry).where(AuditEntry.action == "csf.run_ai")).scalar_one()
    assert entry.details.get("omitted_count") == 2, "the audit row does not carry the count"
    assert "omitted_rows" not in entry.details
    assert high[0] not in json.dumps(entry.details), "the audit row carries counts only"
    assert high[1] not in json.dumps(entry.details), "the audit row carries counts only"


@pytest.mark.unit
def test_a_key_the_cross_product_asks_for_that_is_not_a_row_is_never_omitted(world) -> None:
    """A batch asks for its tier x the PROFILE-WIDE subcategory list, so on a
    non-rectangular profile it asks for keys that are not rows. Reachable: an
    assessment provisioned before #852 has no RC.CO-04 rows
    (`count_csf_retired_rows.py` counts them), and re-seeding one tier through
    the seed route adds RC.CO-04 to that tier only. A key that is not a row
    cannot keep a score, so it is not an omitted row."""
    from sqlalchemy import delete

    from app.models.csf_profile import CsfDimensionScore

    with world.sessions() as s:
        s.execute(delete(CsfDimensionScore).where(CsfDimensionScore.subcategory_code == "RC.CO-04"))
        s.commit()
    seeded = world.c.post(
        f"/csf/services/{world.svc_id}/profiles/seed", headers=world.h, json={"tiers": ["low"]}
    )
    assert seeded.status_code in (200, 201), seeded.text
    profile = set(_profile_rows(world))
    assert ("low", "RC.CO-04") in profile
    assert ("high", "RC.CO-04") not in profile and ("moderate", "RC.CO-04") not in profile

    high = _batch_codes(world, "high")
    real = ("high", high[0])
    phantoms = {("high", "RC.CO-04"), ("moderate", "RC.CO-04")}
    payloads: list[dict[str, Any]] = []  # list.append is atomic across batch threads
    omit = _omit({real} | phantoms)

    def _answer(payload: dict[str, Any]) -> LLMResponse:
        payloads.append(payload)
        return omit(payload)

    world.provider.register("csf_score", _answer)
    result = csf_run_ai(world.c, world.svc_id, world.h)

    asked = {r for p in payloads for r in _rows_asked(p)}
    assert phantoms <= asked, "the cross product asked for keys that are not rows"
    assert result["omitted_count"] == 1
    assert _omitted(result) == [real]
