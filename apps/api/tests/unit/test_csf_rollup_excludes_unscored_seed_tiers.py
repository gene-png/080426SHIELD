"""#1031 (approved by Gene, #736 6115464421): an unscored seed tier row no
longer takes part in the CSF Playbook Enterprise roll-up.

A Playbook seeds high, moderate and low by default. A seeded row is all zeros,
which scores level 1, so a subcategory scored only on HIGH rolled up to level
1 through the untouched MODERATE and LOW rows: a level lower than anything
assessed, shown on the Enterprise table and stated by a CSF Risk finding
("level 1 of target 4").

"Unscored" is `csf/retired.py::has_recorded_value_besides_target` False, the
predicate D' and R10 already use for "measured": a target alone is not a
score (ruling (a)). Known limit, by that predicate: an AI row scored 0 on every
dimension with nothing else written is indistinguishable from a seeded row and
is treated as unscored.

Out of scope here, filed as #1073: a subcategory with NO scored tier still
rolls up its seed rows and reads level 1 (pre-existing).

Every expected level is written out, worked from the scores below:
Ruling 2 (a) (#736 6116519635): the target comes from the scored tiers too.

- HIGH scored governance 2, policy 2, implementation 2, monitoring 1,
  improvement 0, with evidence: total 7, level 3. A seeded row: total 0,
  level 1. Before #1031, {high: 3, moderate: 1, low: 1} rolled up to 1
  (rule 4, MODERATE lowest, HIGH higher); after, {high: 3} rolls up to 3
  (rule 1).
- The Risk world's HIGH row is Run-AI scored governance 2, policy 1, no
  evidence: total 3, level 2. Before, {high: 2, moderate: 1, low: 1} rolled
  up to 1; after, {high: 2} rolls up to 2.
"""

from __future__ import annotations

import pytest

from app.csf.catalog import SUBCATEGORIES
from tests.unit.test_csf_profile import _bootstrap, _row, app_client  # noqa: F401
from tests.unit.test_risk_csf_scored_and_targeted_row import A, _world
from tests.unit.test_risk_register import app_client as risk_app_client  # noqa: F401

pytestmark = pytest.mark.unit

CODE = SUBCATEGORIES[0].code
THREE_TIERS = ["high", "moderate", "low"]
LEVEL_3 = {
    "governance": 2,
    "policy": 2,
    "implementation": 2,
    "monitoring": 1,
    "improvement": 0,
    "has_evidence": True,
}


def _seeded(c, tiers: list[str]) -> tuple[dict, str]:
    h, svc_id = _bootstrap(c)
    r = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": tiers})
    assert r.status_code == 200, r.text
    return h, svc_id


def _patch(c, h: dict, svc_id: str, tier: str, body: dict) -> None:
    r = c.patch(
        f"/csf/dimension-scores/{_row(c, h, svc_id, tier, CODE)['id']}", headers=h, json=body
    )
    assert r.status_code == 200, r.text


def _enterprise(c, h: dict, svc_id: str) -> dict:
    r = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h)
    assert r.status_code == 200, r.text
    return next(s for s in r.json()["subcategories"] if s["subcategory_code"] == CODE)


def test_a_scored_tier_is_not_pulled_down_by_two_seed_tiers(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id = _seeded(c, THREE_TIERS)
    _patch(c, h, svc_id, "high", {**LEVEL_3, "target_level": 3})
    sub = _enterprise(c, h, svc_id)
    assert sub["tier_levels"] == {"high": 3}, sub
    assert (sub["enterprise_level"], sub["rollup_rule"]) == (3, 1), sub
    assert (sub["target_level"], sub["gap"], sub["priority"]) == (3, False, None), sub


def test_a_target_only_tier_is_unscored_and_its_target_is_not_counted(
    app_client,  # noqa: F811
) -> None:
    """Ruling (a): a target is not a score, so MODERATE's level leaves the
    roll-up; ruling 2 (a), #736 6116519635: its target leaves it too, so the
    gap is measured against the scored tier's own target (3), and there is
    none. Before 2 (a) this read target 4, gap True."""
    c = app_client
    h, svc_id = _seeded(c, THREE_TIERS)
    _patch(c, h, svc_id, "high", {**LEVEL_3, "target_level": 3})
    _patch(c, h, svc_id, "moderate", {"target_level": 4})
    sub = _enterprise(c, h, svc_id)
    assert sub["tier_levels"] == {"high": 3}, sub
    assert sub["enterprise_level"] == 3, sub
    assert (sub["target_level"], sub["gap"]) == (3, False), sub


def test_a_tier_with_only_a_finding_written_is_scored(app_client) -> None:  # noqa: F811
    """Anything the predicate counts keeps the tier in: a `what_we_found`
    alone stamps the row, so LOW (level 1) stays in the roll-up."""
    c = app_client
    h, svc_id = _seeded(c, THREE_TIERS)
    _patch(c, h, svc_id, "high", {**LEVEL_3, "target_level": 3})
    _patch(c, h, svc_id, "low", {"what_we_found": "Nothing documented."})
    sub = _enterprise(c, h, svc_id)
    assert sub["tier_levels"] == {"high": 3, "low": 1}, sub


def test_the_risk_finding_states_the_scored_level(risk_app_client) -> None:  # noqa: F811
    """The Risk Register's CSF finding and its evidence read the same
    roll-up: HIGH scored to level 2 and targeted at 4, MODERATE and LOW
    seeded and untouched."""
    _c, _bearer, _cid, payload = _world(
        risk_app_client, tiers=THREE_TIERS, scored=[("high", A)], targeted=[("high", A)]
    )
    csf = {sid: f for sid, f in payload["findings"].items() if f["kind"] == "csf"}
    assert list(csf) == [A], csf  # positive first
    finding = csf[A]
    assert finding["label"] == f"CSF {A}: level 2 of target 4", finding
    evidence = finding["evidence"]
    assert evidence["enterprise_level"] == 2, evidence
    assert evidence["tier_levels"] == {"high": 2}, evidence
    assert set(evidence["tier_notes"]) == {"high"}, evidence
