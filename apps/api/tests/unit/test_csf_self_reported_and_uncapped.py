"""CSF Options 1 and 3 (Gene, #736 6200638511; Q1 to Q4 approved in
6201691989), through the routes the panel and the exports read.

- Option 1 / #1073: a subcategory with no scored in-scope tier gets no
  Enterprise level, no target and no gap. Before, its seed rows rolled up to
  level 1 and could be a gap.
- Option 3: evidence no longer caps a level, for every assessment not frozen
  under the old rules. Q2: an assessment approved under rules 1 or 2 keeps the
  cap, so released numbers do not move; approve now stamps rules 3.
- Three-state evidence (6201691989 item 2): `evidence_status` is `on_file`,
  `confirmed_in_discussion` or `neither`. No value changes a score or a level.
- The coverage counts behind C3 (6201620727 item 2): scored, self-reported
  only, not answered, adding up to the in-scope total.

Every expected level is worked out here from the scores, never imported:
G2 P2 I2 M2 C2 totals 10, which is level 5. Under the old cap, with no
evidence, Implementation is held to 1 (total 9) and the level to 2.
G2 P2 I2 M1 C0 totals 7, which is level 3.
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from app.csf.catalog import SUBCATEGORIES
from tests.unit.test_csf_playbook_override_every_artifact import app_client  # noqa: F401

pytestmark = pytest.mark.unit

CODE = SUBCATEGORIES[0].code
OTHER = SUBCATEGORIES[1].code
THIRD = SUBCATEGORIES[2].code
ALL_TWOS = {"governance": 2, "policy": 2, "implementation": 2, "monitoring": 2, "improvement": 2}
LEVEL_3 = {"governance": 2, "policy": 2, "implementation": 2, "monitoring": 1, "improvement": 0}


def _world(c, h: dict, tiers: list[str]) -> tuple[str, str]:
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    a = c.post(f"/csf/services/{svc}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    r = c.post(f"/csf/services/{svc}/profiles/seed", headers=h, json={"tiers": tiers})
    assert r.status_code == 200, r.text
    return svc, a.json()["id"]


def _row(c, h: dict, svc: str, tier: str, code: str) -> dict:
    rows = c.get(f"/csf/services/{svc}/profile/{tier}", headers=h).json()["rows"]
    return next(r for r in rows if r["subcategory_code"] == code)


def _patch(c, h: dict, svc: str, tier: str, code: str, body: dict):
    sid = _row(c, h, svc, tier, code)["id"]
    return c.patch(f"/csf/dimension-scores/{sid}", headers=h, json=body)


def _ok_patch(c, h: dict, svc: str, tier: str, code: str, body: dict) -> dict:
    r = _patch(c, h, svc, tier, code, body)
    assert r.status_code == 200, r.text
    return r.json()


def _profile(c, h: dict, svc: str) -> dict:
    r = c.get(f"/csf/services/{svc}/enterprise-profile", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def _sub(c, h: dict, svc: str, code: str = CODE) -> dict:
    return next(s for s in _profile(c, h, svc)["subcategories"] if s["subcategory_code"] == code)


def _answer(c, h: dict, svc: str, code: str, body: dict) -> None:
    latest = c.get(f"/csf/services/{svc}/assessments/latest", headers=h).json()
    answer_id = next(a["id"] for a in latest["answers"] if a["subcategory_code"] == code)
    r = c.patch(f"/csf/answers/{answer_id}", headers=h, json=body)
    assert r.status_code == 200, r.text


def _approve(c, h: dict, aid: str) -> None:
    r = c.post(f"/csf/assessments/{aid}/approve", headers=h)
    assert r.status_code == 200, r.text


def _db():
    return create_engine(os.environ["DATABASE_URL"], future=True)


def _ids(aid: str) -> dict:
    return {"a": aid, "b": str(uuid.UUID(aid)).replace("-", "")}


def _rollup_rules(aid: str) -> int | None:
    with _db().connect() as db:
        values = db.execute(
            text("SELECT rollup_rules FROM csf_assessments WHERE id IN (:a, :b)"), _ids(aid)
        ).scalars()
        (value,) = list(values)
    return value


def _set_rollup_rules(aid: str, value: int) -> None:
    """Setup only: the value an assessment approved before this change carries
    (2, written by approve since #1031; 1, migration 0070's backfill)."""
    with _db().begin() as db:
        n = db.execute(
            text("UPDATE csf_assessments SET rollup_rules = :v WHERE id IN (:a, :b)"),
            {"v": value, **_ids(aid)},
        ).rowcount
    assert n == 1, n


# --- Option 1 / #1073: no scored tier, no level ------------------------------------------


def test_a_subcategory_with_no_scored_tier_has_no_level_target_or_gap(
    app_client,  # noqa: F811
) -> None:
    c, h = app_client
    svc, _aid = _world(c, h, ["high", "moderate", "low"])
    _ok_patch(c, h, svc, "high", OTHER, {**LEVEL_3, "target_level": 4})
    # A target alone is not a score (#1031 ruling (a)), so CODE has no scored tier.
    _ok_patch(c, h, svc, "high", CODE, {"target_level": 4})
    scored = _sub(c, h, svc, OTHER)
    assert (scored["enterprise_level"], scored["gap"]) == (3, True), scored  # positive first
    sub = _sub(c, h, svc)
    assert sub["enterprise_level"] is None, sub
    assert (sub["gap"], sub["priority"], sub["target_level"]) == (False, None, None), sub
    assert sub["tier_levels"] == {}, sub


def test_the_gap_actions_list_carries_no_level_for_it(app_client) -> None:  # noqa: F811
    """The gap-actions response used `enterprise_level=0` as a stand-in for a
    code with no row; a not-scored code must read None there too."""
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    r = c.put(f"/csf/services/{svc}/gap-actions/{CODE}", headers=h, json={"owner": "Ops lead"})
    assert r.status_code == 200, r.text
    r = c.get(f"/csf/services/{svc}/gap-actions", headers=h)
    assert r.status_code == 200, r.text
    action = next(a for a in r.json()["actions"] if a["subcategory_code"] == CODE)
    assert action["owner"] == "Ops lead", action
    assert action["enterprise_level"] is None, action


def test_a_frozen_assessment_keeps_level_1_for_a_subcategory_nobody_scored(
    app_client,  # noqa: F811
) -> None:
    c, h = app_client
    svc, aid = _world(c, h, ["high"])
    _approve(c, h, aid)
    assert _sub(c, h, svc)["enterprise_level"] is None  # positive first: rules 3
    _set_rollup_rules(aid, 2)
    assert _sub(c, h, svc)["enterprise_level"] == 1


# --- Option 3 and Q2: no cap, except on a frozen assessment --------------------------------


def test_approve_records_rules_3(app_client) -> None:  # noqa: F811
    c, h = app_client
    _svc, aid = _world(c, h, ["high"])
    assert _rollup_rules(aid) is None
    _approve(c, h, aid)
    assert _rollup_rules(aid) == 3


def test_a_draft_level_is_not_capped_without_evidence(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    row = _ok_patch(c, h, svc, "high", CODE, ALL_TWOS)
    assert row["evidence_status"] == "neither", row
    assert (row["total"], row["level"], row["evidence_capped"]) == (10, 5, False), row
    sub = _sub(c, h, svc)
    assert (sub["tier_levels"], sub["enterprise_level"]) == ({"high": 5}, 5), sub


@pytest.mark.parametrize("rules", [1, 2])
def test_a_frozen_assessment_keeps_the_cap(app_client, rules: int) -> None:  # noqa: F811
    c, h = app_client
    svc, aid = _world(c, h, ["high"])
    _ok_patch(c, h, svc, "high", CODE, ALL_TWOS)
    _approve(c, h, aid)
    assert _sub(c, h, svc)["enterprise_level"] == 5  # positive first: rules 3
    _set_rollup_rules(aid, rules)
    row = _row(c, h, svc, "high", CODE)
    assert (row["total"], row["level"], row["evidence_capped"]) == (9, 2, True), row
    assert _sub(c, h, svc)["enterprise_level"] == 2


def test_a_frozen_assessment_with_evidence_on_file_is_not_capped(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, aid = _world(c, h, ["high"])
    _ok_patch(c, h, svc, "high", CODE, {**ALL_TWOS, "evidence_status": "on_file"})
    _approve(c, h, aid)
    _set_rollup_rules(aid, 2)
    row = _row(c, h, svc, "high", CODE)
    assert (row["level"], row["evidence_capped"]) == (5, False), row


def test_confirmed_in_discussion_is_capped_on_a_frozen_assessment(app_client) -> None:  # noqa: F811
    """The old cap read "evidence on file"; a level confirmed only in
    discussion had no evidence on file, and a frozen assessment keeps that."""
    c, h = app_client
    svc, aid = _world(c, h, ["high"])
    _ok_patch(c, h, svc, "high", CODE, {**ALL_TWOS, "evidence_status": "confirmed_in_discussion"})
    _approve(c, h, aid)
    assert _row(c, h, svc, "high", CODE)["level"] == 5
    _set_rollup_rules(aid, 2)
    assert _row(c, h, svc, "high", CODE)["level"] == 2


# --- Three-state evidence ------------------------------------------------------------------


@pytest.mark.parametrize("status", ["on_file", "confirmed_in_discussion", "neither"])
def test_evidence_status_round_trips_and_never_changes_the_level(
    app_client,  # noqa: F811
    status: str,
) -> None:
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    row = _ok_patch(c, h, svc, "high", CODE, {**LEVEL_3, "evidence_status": status})
    assert (row["evidence_status"], row["level"]) == (status, 3), row
    assert row["has_evidence"] is (status == "on_file"), row
    assert _sub(c, h, svc)["tier_evidence"] == {"high": status}


def test_the_has_evidence_patch_still_writes_the_two_old_values(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    assert (
        _ok_patch(c, h, svc, "high", CODE, {"has_evidence": True})["evidence_status"] == "on_file"
    )
    assert (
        _ok_patch(c, h, svc, "high", CODE, {"has_evidence": False})["evidence_status"] == "neither"
    )


def test_has_evidence_and_evidence_status_together_are_refused(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    r = _patch(c, h, svc, "high", CODE, {"has_evidence": True, "evidence_status": "neither"})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "evidence_fields_conflict", r.text
    assert _row(c, h, svc, "high", CODE)["evidence_status"] == "neither"


def test_an_unknown_evidence_status_is_refused(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    r = _patch(c, h, svc, "high", CODE, {"evidence_status": "yes"})
    assert r.status_code == 422, r.text
    assert _row(c, h, svc, "high", CODE)["evidence_status"] == "neither"


def test_a_tier_with_only_an_evidence_status_counts_as_scored(app_client) -> None:  # noqa: F811
    """`has_recorded_value_besides_target` counted a ticked box; a consultant
    recording "confirmed in discussion" has recorded something too."""
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    assert _sub(c, h, svc)["enterprise_level"] is None  # positive first
    _ok_patch(c, h, svc, "high", CODE, {"evidence_status": "confirmed_in_discussion"})
    assert _sub(c, h, svc)["enterprise_level"] == 1


# --- C3 (four counts, Q-A as the advisor recommends) and E3 ---------------------------------

FOURTH = SUBCATEGORIES[3].code
FIFTH = SUBCATEGORIES[4].code
SIXTH = SUBCATEGORIES[5].code
SEVENTH = SUBCATEGORIES[6].code
EIGHTH = SUBCATEGORIES[7].code


def test_the_coverage_counts_add_up_to_the_in_scope_total(app_client) -> None:  # noqa: F811
    """Every count is worked out here from the world, never from the code.

    C3, over the in-scope subcategories:
    - scored: CODE, FOURTH, FIFTH, SIXTH, SEVENTH, EIGHTH (6);
    - with notes, not yet scored: THIRD (1);
    - self-reported only: OTHER, a rating and no notes (1);
    - not answered: the rest.

    E3, over the six scored, as Gene approved the classes (#736 6205956728):
    - on file on every scored tier: FIFTH;
    - confirmed in discussion (every tier on file or confirmed, at least one
      confirmed): SEVENTH, and EIGHTH (on file on high, confirmed on moderate);
    - neither: CODE (level 3) and FOURTH (level 5);
    - mixed: SIXTH, on file on high and neither on moderate;
    - notional (Managed or Optimized, and `neither` on a rolled-up tier):
      FOURTH, and SIXTH, whose level 5 rests partly on a tier nobody
      validated. CODE is level 3, so not notional."""
    c, h = app_client
    svc, _aid = _world(c, h, ["high", "moderate"])
    _ok_patch(c, h, svc, "high", CODE, LEVEL_3)
    _ok_patch(c, h, svc, "high", FOURTH, ALL_TWOS)
    _ok_patch(c, h, svc, "high", FIFTH, {**LEVEL_3, "evidence_status": "on_file"})
    _ok_patch(c, h, svc, "high", SIXTH, {**ALL_TWOS, "evidence_status": "on_file"})
    _ok_patch(c, h, svc, "moderate", SIXTH, ALL_TWOS)
    _ok_patch(c, h, svc, "high", SEVENTH, {**LEVEL_3, "evidence_status": "confirmed_in_discussion"})
    _ok_patch(c, h, svc, "high", EIGHTH, {**LEVEL_3, "evidence_status": "on_file"})
    _ok_patch(
        c, h, svc, "moderate", EIGHTH, {**LEVEL_3, "evidence_status": "confirmed_in_discussion"}
    )
    _answer(c, h, svc, OTHER, {"maturity_tier": 2})  # self-reported only
    _answer(c, h, svc, THIRD, {"maturity_tier": 3, "notes": "Asked, nothing scored yet."})
    profile = _profile(c, h, svc)
    assert _sub(c, h, svc, SIXTH)["enterprise_level"] == 5  # positive first
    total = len(profile["subcategories"])
    cov = profile["coverage"]
    assert cov == {
        "total": total,
        "scored": 6,
        "notes_not_scored": 1,
        "self_reported": 1,
        "not_answered": total - 8,
        "evidence_on_file": 1,
        "evidence_confirmed": 2,
        "evidence_neither": 2,
        "evidence_mixed": 1,
        "notional": 2,
    }, cov
    assert (
        cov["scored"] + cov["notes_not_scored"] + cov["self_reported"] + cov["not_answered"]
        == cov["total"]
    )
    assert (
        cov["evidence_on_file"]
        + cov["evidence_confirmed"]
        + cov["evidence_mixed"]
        + cov["evidence_neither"]
        == cov["scored"]
    )
    assert profile["evidence_cap"] is False
    other = _sub(c, h, svc, OTHER)
    assert (other["enterprise_level"], other["self_rating"]) == (None, 2), other
    third = _sub(c, h, svc, THIRD)
    assert (third["enterprise_level"], third["no_notes"]) == (None, False), third
    assert _sub(c, h, svc)["self_rating"] is None


def test_a_frozen_assessment_says_its_evidence_caps(app_client) -> None:  # noqa: F811
    c, h = app_client
    svc, aid = _world(c, h, ["high"])
    _approve(c, h, aid)
    assert _profile(c, h, svc)["evidence_cap"] is False  # positive first: rules 3
    _set_rollup_rules(aid, 2)
    assert _profile(c, h, svc)["evidence_cap"] is True
