"""zt_score Run-AI: current+target suggestions, validation, lock-skip (Work Order D3)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-ztai.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.zt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        yield c, provider


def _admin_service(c: TestClient, kind: str) -> tuple[dict, str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/zt/services", headers=h, json={"kind": kind, "title": "Acme ZT"})
    return h, svc.json()["id"], cid


@pytest.mark.unit
def test_zt_run_ai_applies_current_and_target(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": [{"code": "' + code + '", "current": 2, "target": 4}],'
            ' "pillar_narratives": {"ID": "Identity is partial."},'
            ' "executive_summary": "draft", "roadmap_summary": "12-month plan"}'
        ),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 2
    assert row["target_stage"] == 4
    fields = {ch["field"] for ch in body["changed"] if ch["capability_code"] == code}
    assert {"maturity_stage", "target_stage"} <= fields

    # This test used to assert `pillar_narratives` and `executive_summary` were
    # echoed back. Those assertions were not WRONG about the old behaviour —
    # they are removed because the behaviour is deliberately gone (issue #64):
    # all three narrative fields were returned and none was ever persisted,
    # exported or rendered, so they were pulled from the prompt rather than
    # given accounting machinery. The payload above still SENDS them, on
    # purpose: a model that has not caught up with a prompt change must not 500.
    #
    # They are TOP-LEVEL keys, so they do not reach the per-entry unknown-field
    # path and are not counted — the run ignores them exactly as CSF ignores its
    # `executive_summary`. That top-level silence is issue #46 / #60 and is
    # outside W1's invariant, which covers the entries in `capabilities`.
    assert "pillar_narratives" not in body
    assert "executive_summary" not in body
    # All THREE, not two. NOTE the narrow scope: `body` is served through a
    # `response_model`, which strips unknown keys, so this fires only if someone
    # re-adds a SCHEMA field. It cannot catch a re-add to the PROMPT, which is
    # the change that would start costing tokens again — that is pinned by
    # `test_zt_score_prompt_does_not_ask_for_narratives` below.
    assert "roadmap_summary" not in body
    # And the top-level extras must not move the counters. Stated in the comment
    # above; asserted here so a future `received` that enumerates top-level keys
    # cannot pass silently.
    assert body["suggestions_received"] == 2, body
    assert body["suggestions_applied"] == 2, body
    assert body["dropped"] == [], body["dropped"]


@pytest.mark.unit
def test_zt_run_ai_clamps_out_of_range_for_dod(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_dod")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]
    # DoD max stage is 3; a suggested 4 is out of range and must be ignored.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    row = next(x for x in r.json()["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3
    assert row["target_stage"] is None  # 4 rejected for DoD


@pytest.mark.unit
def test_build_roadmap_front_loads_priority() -> None:
    from app.zt.scoring import Gap, build_roadmap

    def _gap(code: str, prio: float) -> Gap:
        return Gap(
            code=code,
            pillar_code="ID",
            pillar_name="Identity",
            name=code,
            outcome="o",
            current_stage=1,
            target_stage=3,
            gap_size=2,
            priority_score=prio,
            notes=None,
        )

    gaps = [_gap(f"C{i:02d}", 100 - i) for i in range(24)]  # priority-descending
    rm = build_roadmap(gaps, horizon_months=12)
    assert len(rm) == 24
    assert all(1 <= it.month <= 12 for it in rm)
    assert rm[0].month == 1  # highest priority first
    assert rm[-1].month == 12  # lowest priority last
    assert build_roadmap([]) == ()


@pytest.mark.unit
def test_gap_endpoint_respects_per_capability_target_and_returns_roadmap(app_client) -> None:
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    # current 1, per-capability target 4 -> a gap to target 4.
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"maturity_stage": 1, "target_stage": 4})
    g = c.get(f"/zt/services/{svc_id}/gap-analysis", headers=h)
    assert g.status_code == 200, g.text
    body = g.json()
    gap = next(x for x in body["gaps"] if x["code"] == code)
    assert gap["target_stage"] == 4  # per-capability target, not the default 3
    assert any(it["code"] == code for it in body["roadmap"])


@pytest.mark.unit
def test_zt_run_ai_skips_locked(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"locked": True})
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    row = next(x for x in r.json()["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] is None
    assert all(ch["capability_code"] != code for ch in r.json()["changed"])


# --------------------------------------------------------------------------- #
# Fixture output must never overwrite what a client submitted.
#
# The 2026-08-04 review pressed Run AI on a Zero Trust workspace with no API key
# loaded. Fixture mode returned canned demo values and wrote them straight over
# a real client self-assessment: average maturity fell 2.14 -> 1.49 and the
# Identity pillar 3.00 -> 1. `locked` did not help — it records a consultant's
# choice, not provenance — so migration 0035 added `answer_source`.
# --------------------------------------------------------------------------- #


def _submitted_self_assessment(c, h, svc_id: str) -> tuple[str, str]:
    """Answer one capability as the client and submit. Returns (code, answer id)."""
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"maturity_stage": 3})
    submitted = c.post(
        f"/zt/services/{svc_id}/self-assessment/submit",
        headers=h,
        json={"target_stage": 3},
    )
    assert submitted.status_code == 200, submitted.text
    return code, ans_id


@pytest.mark.unit
def test_fixture_run_ai_leaves_client_submitted_answers_untouched(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    # Fixture provider = offline demo output.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 2}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3, "canned output overwrote a client-submitted answer"
    assert all(ch["capability_code"] != code for ch in body["changed"])
    # The skip is reported, not silent.
    assert body["preserved_client_answers"] == 1


@pytest.mark.unit
def test_submit_stamps_client_provenance(app_client) -> None:
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, ans_id = _submitted_self_assessment(c, h, svc_id)

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        row = check.execute(select(ZtAnswer).where(ZtAnswer.capability_code == code)).scalar_one()
        assert row.answer_source == "client"


@pytest.mark.unit
def test_live_run_ai_may_update_client_answers(app_client, monkeypatch) -> None:
    """A LIVE run drafting over a client's self-assessment is the consultant
    workflow — the diff is shown for review. Only fixture output is refused."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    # Present the same canned response as if it came from a real provider.
    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 2}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 1
    assert body["preserved_client_answers"] == 0


@pytest.mark.unit
def test_live_run_ai_does_not_stamp_ai_provenance_on_a_rejected_suggestion(
    app_client, monkeypatch
) -> None:
    """F9 (issue #38): a suggestion `_coerce` rejects applies NOTHING, so the row
    must not go on to claim the model authored it.

    Asserted on a LIVE run deliberately. `protected_keys` returns an empty set
    off-fixture (`app/ai/provenance.py:54-56`), so live is the only mode where
    the row is reachable at all — a fixture-mode test cannot express this and is
    exactly why it shipped.

    The stake is the client's own answer: re-stamping it `ai` loses the
    `SOURCE_CLIENT` provenance irrecoverably AND re-opens the fixture door that
    migration 0035 closed, since `protected_keys` protects only non-AI rows.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    # CISA tops out at stage 4. Both values are out of range, so neither is applied.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 9, "target": 9}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3, "a rejected suggestion changed the value"
    assert all(ch["capability_code"] != code for ch in body["changed"])

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        stored = check.execute(
            select(ZtAnswer).where(ZtAnswer.capability_code == code)
        ).scalar_one()
        assert stored.answer_source == "client", (
            "the client's own answer was re-stamped as AI-authored after the "
            "model's suggestion was rejected (F9)"
        )


@pytest.mark.unit
def test_live_run_ai_agreeing_with_the_client_does_not_claim_authorship(
    app_client, monkeypatch
) -> None:
    """F9, the wider half (issue #38): an ACCEPTED value equal to what was
    already there is the same non-authorship as a rejected one.

    This is the LIKELIER case, not an edge case. `build_zt_ai_request` sends the
    model `{"current": r.maturity_stage}` for every capability, so echoing the
    client's own number back for rows it agrees with is the expected response
    shape. Stamping that `ai` destroys the SOURCE_CLIENT provenance — which
    `submit_self_assessment` can never restore, since it refuses once the
    assessment leaves DRAFT — and unprotects the row for every later fixture
    run, because `protected_keys` protects only non-AI rows.

    The model here also proposes a TARGET, which IS new: the target must land
    and appear in the diff, while the client's stamp on the maturity stage
    survives. Provenance tracks who set the stage, which is what
    `protected_keys` keys on.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    # current 3 == what the client submitted; target 4 is genuinely new.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3
    assert row["target_stage"] == 4, "a genuinely new target must still apply"

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        stored = check.execute(
            select(ZtAnswer).where(ZtAnswer.capability_code == code)
        ).scalar_one()
        assert stored.answer_source == "client", (
            "the model agreed with the client's stage and was credited with "
            "authoring it, unprotecting the row for every later fixture run (F9)"
        )


@pytest.mark.unit
def test_live_run_ai_duplicate_codes_that_round_trip_do_not_claim_authorship(
    app_client, monkeypatch
) -> None:
    """F9, third route in (issue #38): the same code twice, netting to zero.

    Deciding provenance per suggestion compares against a row the loop is still
    mutating, so 3 -> 4 -> 3 reads as two changes, stamps twice, and lands back
    on the client's own number. `before`/`after` are taken outside the loop, so
    the diff shows nothing and no counter fires — the original defect reached
    through the one input shape a per-suggestion rule cannot see.

    Provenance is therefore settled after the loop from the net effect.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": ['
            '{"code": "' + code + '", "current": 4},'
            '{"code": "' + code + '", "current": 3}]}'
        ),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3, "the round trip should net to the client's value"
    assert all(ch["capability_code"] != code for ch in body["changed"])

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        stored = check.execute(
            select(ZtAnswer).where(ZtAnswer.capability_code == code)
        ).scalar_one()
        assert stored.answer_source == "client", (
            "a duplicated capability code round-tripped through the loop and "
            "stamped the client's own value as AI-authored (F9)"
        )


@pytest.mark.unit
def test_live_run_ai_drops_an_out_of_range_value_but_applies_its_sibling(
    app_client, monkeypatch
) -> None:
    """The two stage values are validated independently.

    `{"current": 9, "target": 3}` must apply the target and drop the current,
    rather than the bad value poisoning the whole suggestion or the good one
    dragging the bad one in. The drop is now visible in the RESPONSE, itemized
    per reason (W1, D-047). This docstring used to point at a
    `zt_run_ai_suggestions_dropped` log line explaining why the count was
    deliberately withheld; that line and that rationale are both gone.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    # CISA tops out at 4: the current is rejected, the target is fine.
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 9, "target": 3}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] is None, "an out-of-range current must not apply"
    assert row["target_stage"] == 3


@pytest.mark.unit
def test_live_run_ai_does_stamp_ai_provenance_when_it_changes_a_stage(
    app_client, monkeypatch
) -> None:
    """The POSITIVE half of the provenance contract (issue #38).

    Every other provenance test here asserts the stamp does NOT move. Without
    this one, deleting the `answer_source = SOURCE_AI` write leaves the whole
    suite green — and the consequence is not benign: `protected_keys` protects
    any answered row whose source is not AI, so AI-written rows would all become
    protected, `preserved_client_answers` would jump to the full capability
    count, and the "fixture may refresh output it wrote itself" path that D-017
    demos and the e2e suite rely on would stop working.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 3, "target": 4}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    row = next(x for x in body["answers"] if x["capability_code"] == code)
    assert row["maturity_stage"] == 3
    assert any(ch["capability_code"] == code for ch in body["changed"])

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        stored = check.execute(
            select(ZtAnswer).where(ZtAnswer.capability_code == code)
        ).scalar_one()
        assert stored.answer_source == "ai", (
            "a stage the AI genuinely wrote must be stamped as AI-authored, or "
            "every AI row becomes 'protected' and fixture refresh breaks"
        )
        assert stored.answered_by is not None
        assert stored.answered_at is not None


@pytest.mark.unit
def test_a_malformed_response_does_not_500_and_changes_nothing(app_client, monkeypatch) -> None:
    """The shapes `parse_json` will happily hand back that used to crash.

    `parse_json` is bare `json.loads` with no schema validation, so anything the
    model emits reaches this loop. An unhashable `code` raised
    `TypeError: unhashable type` out of `rows.get`, and a non-list
    `capabilities` raised out of the `for` — both surfacing as an untyped 500 on
    a well-formed request. They are bad model output, not server faults.

    This is the only coverage for those two guards; without it, deleting either
    leaves the suite green.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    for payload in (
        '{"capabilities": [{"code": ["x"], "current": 2}]}',  # unhashable code
        '{"capabilities": ["' + code + '", 7]}',  # entries that are not objects
        '{"capabilities": [{"code": "NOPE-1", "current": 2}]}',  # unknown code
    ):
        provider.register_static("zt_score", LLMResponse(payload))
        r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
        assert r.status_code == 200, f"{payload} -> {r.status_code} {r.text}"
        assert r.json()["changed"] == [], f"{payload} should change nothing"

    # A NON-LIST `capabilities` moved out of the loop above, because it is no
    # longer a 200. This is a deliberate behaviour change, not a test bent to
    # fit the code: the old path did `raw_caps = []` after a warning — a
    # default-value fallback on a bad shape, which FAIL LOUDLY forbids and which
    # made a structurally broken response indistinguishable from a model that
    # had nothing to say. It is now refused by
    # `parse_json_object_with_list("capabilities")`, matching what csf_score
    # already does with `scores`. Counting it as drops was the other option and
    # is wrong: there are no entries to enumerate, so any per-entry number would
    # be invented.
    provider.register_static("zt_score", LLMResponse('{"capabilities": 0}'))
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"
    assert "drifted apart" in r.json()["error"]["message"]

    from app.models.zt_assessment import ZtAnswer

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as check:
        stored = check.execute(
            select(ZtAnswer).where(ZtAnswer.capability_code == code)
        ).scalar_one()
        assert stored.maturity_stage is None
        assert stored.answer_source is None, "no row was written, so nothing was authored"


# ---------------------------------------------------------------------------
# W1's ZT step - every AI suggestion is applied or itemized (issue #44, D-045).
#
# Payloads below carry ONLY `capabilities`, never a narrative key, so every
# count here is unambiguous regardless of how the narrative fields are scoped.
# ---------------------------------------------------------------------------

# One capability entry's worth of suggestions: `current` and `target`. Used when
# an entry is too broken to enumerate what it meant to set.
_ROW_VALUE_SLOTS = 2


def _run_ai_caps(c, provider, h, svc_id: str, caps: list) -> dict:
    import json as _json

    provider.register_static("zt_score", LLMResponse(_json.dumps({"capabilities": caps})))
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_invariant(body: dict) -> None:
    """Every suggestion the run received is either applied or itemized."""
    accounted = body["suggestions_applied"] + sum(d["values"] for d in body["dropped"])
    assert body["suggestions_received"] == accounted, body


def _only_dropped(body: dict) -> dict:
    assert len(body["dropped"]) == 1, body["dropped"]
    return body["dropped"][0]


def _answer(body: dict, code: str) -> dict:
    return next(x for x in body["answers"] if x["capability_code"] == code)


@pytest.mark.unit
def test_zt_run_ai_boolean_is_not_a_stage_of_one(app_client) -> None:
    """`int(True)` is 1. A bool is not a maturity stage.

    Reads the row back, not just the drop record: a regression that writes the
    value AND itemizes the drop would look green on the record alone.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": True}])
    d = _only_dropped(body)
    assert d["reason"] == "unparseable", d
    assert d["field"] == "current", d
    assert _answer(body, code)["maturity_stage"] is None
    assert body["suggestions_applied"] == 0
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_in_range_float_is_refused_not_silently_truncated(app_client) -> None:
    """`int(1.9)` is 1 - a value the model never sent, reported as applied."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 1.9}])
    d = _only_dropped(body)
    assert d["reason"] == "unparseable", d
    assert "1.9" in str(d["value"]), d
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_out_of_range_float_reports_range_not_a_fraction(app_client) -> None:
    """Range is judged BEFORE wholeness, so 4.9 on a 1..4 ladder is out of range.

    Today `int(4.9)` is 4, which is in range, so the run silently applies a 4 the
    model never asked for.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 4.9}])
    d = _only_dropped(body)
    assert d["reason"] == "out_of_range", d
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_whole_number_written_as_text_or_float_is_applied(app_client) -> None:
    """The counterweight: refusing a value the model plainly meant is the same
    defect facing the other way."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": "2", "target": 3.0}])
    assert body["dropped"] == [], body["dropped"]
    assert body["suggestions_applied"] == 2
    row = _answer(body, code)
    assert row["maturity_stage"] == 2
    assert row["target_stage"] == 3
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_unknown_field_is_counted_not_silently_ignored(app_client) -> None:
    """The loop reads only code/current/target, so a drifted key vanishes."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 2, "maturity_level": 3}])
    assert body["suggestions_applied"] == 1
    assert body["suggestions_received"] == 2
    drift = [d for d in body["dropped"] if d["reason"] == "unknown_field"]
    assert len(drift) == 1 and drift[0]["field"] == "maturity_level", body["dropped"]
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_unknown_code_is_itemized_verbatim(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": "NOPE-1", "current": 2}])
    d = _only_dropped(body)
    assert d["reason"] == "unknown_key", d
    assert d["key"] == "NOPE-1", d
    assert d["values"] == 1, d
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_unreadable_entry_counts_the_full_row_width(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)

    body = _run_ai_caps(c, provider, h, svc_id, ["not-a-dict"])
    d = _only_dropped(body)
    assert d["reason"] == "entry_shape", d
    assert d["values"] == _ROW_VALUE_SLOTS, d
    assert d["key"] is None, d
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_locked_row_is_a_visible_reason_not_a_silent_skip(app_client) -> None:
    """`if row.locked or code in protected: continue` records nothing today."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"locked": True})

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 2}])
    d = _only_dropped(body)
    assert d["reason"] == "locked", d
    assert d["key"] == code, d
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_superseded_value_is_not_counted_as_applied(app_client) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(
        c, provider, h, svc_id, [{"code": code, "current": 2}, {"code": code, "current": 3}]
    )
    assert body["suggestions_received"] == 2
    assert body["suggestions_applied"] == 1
    d = _only_dropped(body)
    assert d["reason"] == "superseded", d
    assert d["field"] == "current", d
    # Names the value that was LOST, not the one that won. Without this the
    # natural mistake (recording `raw`) leaves the suite green while the record
    # tells a consultant the opposite of what happened.
    assert d["value"] == "2", d
    assert _answer(body, code)["maturity_stage"] == 3
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_audit_row_carries_counts_but_no_model_content(app_client) -> None:
    """Audit rows get reason codes and value counts only (#44 constraint 1)."""
    import json as _json
    import os as _os

    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import sessionmaker as _sm

    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    # THREE values behind ONE unrecognized key, so `dropped_by_reason` cannot
    # pass by counting records — 3 discriminates values-per-reason from
    # records-per-reason, which is the whole rule the audit row encodes. The
    # previous payload used a scalar, where the two are identical.
    _run_ai_caps(
        c,
        provider,
        h,
        svc_id,
        [{"code": code, "current": 2, "okta_stages": {"a": 1, "b": 2, "c": 3}}],
    )

    from app.models.audit_entry import AuditEntry

    eng = _ce(_os.environ["DATABASE_URL"], future=True)
    with _sm(bind=eng, future=True)() as s:
        row = s.execute(select(AuditEntry).where(AuditEntry.action == "zt.run_ai")).scalars().one()
    details = row.details
    assert details["suggestions_received"] == 4, details
    assert details["suggestions_applied"] == 1, details
    assert details["dropped_by_reason"] == {"unknown_field": 3}, details
    # The durable record's own arithmetic must close, not just the response's.
    assert details["suggestions_received"] == details["suggestions_applied"] + sum(
        details["dropped_by_reason"].values()
    ), details
    blob = _json.dumps(details)
    assert code not in blob, blob
    assert "okta_stages" not in blob, blob


@pytest.mark.unit
def test_zt_run_ai_logs_carry_no_key_and_no_model_text(app_client, capsys) -> None:
    """`zt.py` logs `value=repr(raw)[:120]` today - AI output in a log line.

    Reads stdout, not `caplog`: structlog renders JSON straight to stdout here.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    capsys.readouterr()
    _run_ai_caps(
        c, provider, h, svc_id, [{"code": code, "current": "Okta is partial", "okta_stage": 2}]
    )
    text = capsys.readouterr().out
    assert "zt_run_ai_suggestions_accounted" in text, text
    assert "Okta is partial" not in text, text
    assert "okta_stage" not in text, text
    assert code not in text, text


# --- W1 ZT round 1: found by the adversarial pass.
#
# Three of these five FAILED as first written (the two container cases and the
# unbounded field name) and pin the round-1 fix. The other two — `protected` and
# the second `entry_shape` branch — characterise behaviour that was already
# correct but had NO test, so a revert to a bare `continue` would have stayed
# green. Both kinds are worth keeping; only the first kind proves a fix.


@pytest.mark.unit
def test_zt_run_ai_container_under_a_recognized_key_is_counted_whole(app_client) -> None:
    """A wrapper under `current` must be charged the values it hides.

    `received` charged the leaves, the drop record charged a flat 1, and the
    difference fell out of both sides of the invariant with no record — the
    silent loss this whole feature exists to end, reached through the one line
    that was not ported from the CSF sibling.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(
        c, provider, h, svc_id, [{"code": code, "current": {"stage": 2, "confidence": 0.8}}]
    )
    d = _only_dropped(body)
    assert d["reason"] == "unparseable", d
    assert d["field"] == "current", d
    assert d["values"] == 2, "a wrapper hiding two values must not be charged one"
    assert body["suggestions_received"] == 2, body
    assert body["suggestions_applied"] == 0
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_containers_on_both_fields_lose_nothing(app_client) -> None:
    """The same leak, widened: four values behind two recognized names."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(
        c, provider, h, svc_id, [{"code": code, "current": [1, 2, 3], "target": [1, 2, 3]}]
    )
    assert body["suggestions_received"] == 6, body
    assert body["suggestions_applied"] == 0
    assert sum(d["values"] for d in body["dropped"]) == 6, body["dropped"]
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_protected_answer_is_itemized_not_a_silent_skip(app_client) -> None:
    """`protected` is a by-design skip, but it must still be COUNTED.

    Reverting this branch to a bare `continue` left the suite green over a
    two-value silent loss: the one test covering it asserted only
    `preserved_client_answers` and never looked at `dropped`.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    code, _ = _submitted_self_assessment(c, h, svc_id)

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 1, "target": 2}])
    d = _only_dropped(body)
    assert d["reason"] == "protected", d
    assert d["key"] == code, d
    assert d["values"] == 2, d
    # Distinct from `locked` — nobody locked this row.
    assert d["reason"] != "locked"
    assert _answer(body, code)["maturity_stage"] == 3, "client answer was overwritten"
    assert body["preserved_client_answers"] == 1
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_entry_naming_a_capability_with_no_values_is_not_silent(app_client) -> None:
    """Names a real capability and suggests nothing. Charged the full row width,
    not zero — a zero satisfies the invariant vacuously."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code}])
    d = _only_dropped(body)
    assert d["reason"] == "entry_shape", d
    assert d["values"] == _ROW_VALUE_SLOTS, d
    assert d["key"] == code, d
    assert body["suggestions_received"] == _ROW_VALUE_SLOTS
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_unknown_field_name_is_bounded(app_client) -> None:
    """A JSON KEY is model output too. `code` was bounded and `field` was not,
    so a hostile key name reached the response, and the admin DOM, unbounded."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "x" * 5000: 2, "current": 1}])
    drift = next(d for d in body["dropped"] if d["reason"] == "unknown_field")
    assert len(drift["field"]) <= 80, len(drift["field"])
    _assert_invariant(body)


# --- W1 ZT round 2: gaps the round-1 fixes did not close ---------------------


@pytest.mark.unit
def test_zt_run_ai_unresolvable_row_is_named_even_when_it_charges_nothing(app_client) -> None:
    """The row fault is NAMED at values=0, not suppressed.

    The code emits this record unconditionally and says so in a comment; nothing
    pinned it. `test_zt_run_ai_unknown_code_is_itemized_verbatim` uses a
    recognized field, so `recognized_values` is 1 there and a regression to
    `if recognized_values:` would still emit. This is the payload that
    discriminates: a run naming a capability that does not exist would otherwise
    report a field-name curiosity and no alert at all.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": "NOPE-1", "maturity_level": 2}])
    assert {d["reason"] for d in body["dropped"]} == {"unknown_field", "unknown_key"}, body
    unresolved = next(d for d in body["dropped"] if d["reason"] == "unknown_key")
    assert unresolved["key"] == "NOPE-1", unresolved
    assert unresolved["values"] == 0, "named, not double-charged"
    assert body["suggestions_received"] == 1
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_locked_row_still_reports_field_drift(app_client) -> None:
    """Drift is itemized BEFORE the lock check, so a locked row cannot hide it."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    ans = a.json()["answers"][0]
    code, ans_id = ans["capability_code"], ans["id"]
    c.patch(f"/zt/answers/{ans_id}", headers=h, json={"locked": True})

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": 2, "maturity_level": 1}])
    assert {d["reason"] for d in body["dropped"]} == {"unknown_field", "locked"}, body
    drift = next(d for d in body["dropped"] if d["reason"] == "unknown_field")
    assert drift["field"] == "maturity_level", drift
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_absurdly_large_integer_is_itemized_not_a_500(app_client) -> None:
    """`float()` raises OverflowError, not ValueError, on a huge JSON int.

    Uncaught it is a bare 500 that rolls back the flushed `llm_calls` row —
    money spent, ledger empty (the N-019 shape). The guard exists; nothing
    pinned it, so deleting it was free.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": code, "current": int("9" * 400)}])
    d = _only_dropped(body)
    assert d["reason"] == "unparseable", d
    assert d["field"] == "current", d
    assert _answer(body, code)["maturity_stage"] is None
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_two_level_wrapper_counts_leaves_not_the_wrapper(app_client) -> None:
    """Counting the container's own `len` stops one level down and hides the rest."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    body = _run_ai_caps(
        c,
        provider,
        h,
        svc_id,
        [{"code": code, "values": {"stages": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 1}}}],
    )
    d = _only_dropped(body)
    assert d["reason"] == "unknown_field", d
    assert d["field"] == "values", d
    assert d["values"] == 5, "a two-level wrapper hiding five values must not be charged one"
    assert body["suggestions_received"] == 5
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_same_field_on_two_capabilities_is_not_a_supersede(app_client) -> None:
    """`written` is keyed (capability, field). Keying it on field alone would
    make the second capability look like an overwrite of the first."""
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    answers = a.json()["answers"]
    first, second = answers[0]["capability_code"], answers[1]["capability_code"]

    body = _run_ai_caps(
        c, provider, h, svc_id, [{"code": first, "current": 2}, {"code": second, "current": 2}]
    )
    assert body["dropped"] == [], body["dropped"]
    assert body["suggestions_applied"] == 2
    assert _answer(body, first)["maturity_stage"] == 2
    assert _answer(body, second)["maturity_stage"] == 2
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_score_prompt_does_not_ask_for_narratives() -> None:
    """The prompt is the thing that costs money, and nothing else asserts it.

    `assert "roadmap_summary" not in body` cannot catch a re-add to the PROMPT —
    the response model strips unknown keys, so that assertion only fires if
    someone adds a schema field. This is the one that fires if someone starts
    paying for narrative tokens again (issue #64).
    """
    # test-integrity: the PROMPT is the spec being checked. See #92 — ZT's
    # contract test should be audited for the same one-directionality as CSF's.
    from app.ai.jobs import _ZT_SCORE_PROMPT

    for key in ("pillar_narratives", "executive_summary", "roadmap_summary"):
        assert key not in _ZT_SCORE_PROMPT, f"{key} is back in the zt_score prompt (#64)"


# --- W1 ZT round 3: the security lens ---------------------------------------


@pytest.mark.unit
def test_zt_run_ai_unencodable_code_does_not_500_after_committing(app_client) -> None:
    """A `code` the response cannot encode must not commit and then explode.

    `json.loads` accepts an unpaired surrogate escape. `_bounded_key` used to
    return the model's string RAW, so it reached `dropped[].key`, the run
    COMMITTED, and only then did the response encoder raise - a 500 over an
    already-rewritten database, with the workspace still showing pre-run values
    because its catch does not re-fetch. Worse than a refusal.

    The escape is assembled at runtime so this source file never contains a lone
    surrogate itself (writing one breaks any tool that reads the file as UTF-8 -
    which is the same class of defect, one layer out).
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    code = a.json()["answers"][0]["capability_code"]

    lone_surrogate = "\\u" + "d800"  # two chars in THIS file, one escape in JSON
    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": [{"code": "'
            + lone_surrogate
            + '", "current": 1}, {"code": "'
            + code
            + '", "current": 2}]}'
        ),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    # The sibling entry still applied, and the run is reportable.
    assert _answer(body, code)["maturity_stage"] == 2
    d = _only_dropped(body)
    assert d["reason"] == "unknown_key", d
    # Escaped, not raw: the key round-trips as text and encodes cleanly.
    assert d["key"] is not None
    d["key"].encode("utf-8")
    _assert_invariant(body)


@pytest.mark.unit
def test_zt_run_ai_control_characters_in_a_code_are_escaped(app_client) -> None:
    """A right-to-left override in `code` renders live in the admin alert.

    React escapes angle brackets, ampersands and quotes - not control
    characters - so the neutralising has to happen server-side, where every
    other piece of model output already goes through `repr()`.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)

    bidi = "\\u" + "202e"
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + bidi + 'DEILPPA", "current": 1}]}'),
    )
    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    d = _only_dropped(r.json())
    # The override is shown as its escape, not applied to the consultant's line.
    assert "\\u202e" in d["key"], d
    assert d["key"].isprintable(), d


@pytest.mark.unit
def test_zt_run_ai_ordinary_code_is_not_mangled_by_the_escaping(app_client) -> None:
    """The counterweight: escaping must be invisible for real codes.

    A capability code is plain ASCII. If the guard above started quoting or
    escaping those, every `key == code` assertion elsewhere would be wrong and
    the panel would show noise instead of the code the model wrote.
    """
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    c.post(f"/zt/services/{svc_id}/assessments", headers=h)

    body = _run_ai_caps(c, provider, h, svc_id, [{"code": "CISA.NOPE-1", "current": 2}])
    d = _only_dropped(body)
    assert d["key"] == "CISA.NOPE-1", d
