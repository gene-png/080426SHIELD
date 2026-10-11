"""#474 E, review 6105054562 finding 1; ruling #736 6105137014, option (a).

An ATT&CK assessment approved before R3 (`status_rules` 1) renders its STORED
statuses: its screens show no Detect / Prevent / Respond capabilities, and the
stored status can contradict what `attack_capabilities` would compute from the
row's tools. So Risk's `attack` evidence for such a finding sends
`{status, status_basis: "stored", rationale, notes}` and nothing computed; a
computed-status finding keeps its shape plus `status_basis: "computed"`. The
approved v3 text: "`status_basis` is `computed` when SHIELD derived the status
from the function states given, and `stored` when the status was recorded
directly, with no function states; treat a stored status as given and do not
infer missing functions from it."

The world: a stored-status gap whose three tool lists are confirmed, so the
computed states would read "in place" everywhere and `missing_functions` would
be empty beside status "gap" (the contradiction the review found). A
computed-status twin keeps the function states. Driven through the real routes
(approve, generate); the payload is the one the provider receives.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests._attack_rows import standalone_rows
from tests.unit.test_risk_pending_links import _h, _seed_zt
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

_FUNCTIONS = ("detection", "prevention", "response")
_NONE_SENTENCE = "None identified in the supplied information."


def _world(
    app_client, *, status_rules: int, tools: list[str], fixture_mode: bool = False  # noqa: F811
) -> tuple[str, dict, dict]:
    """`(gap code, the gap finding's evidence as sent, generate's response)`.
    `tools`: each function's confirmed tool list on the gap row.
    `fixture_mode`: answer with the runtime fixture (`SHIELD_LLM_MODE=fixture`)."""
    from app.ai.fixtures import build_runtime_provider
    from app.ai.llm import LLMResponse
    from app.models.attack_assessment import AttackAssessment, AttackCoverage

    c, provider = app_client
    bearer, cid = _admin(c)
    h = _h(bearer, cid)
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    (gap,) = standalone_rows(a["coverage"], 1)
    ap = c.post(f"/attack/assessments/{a['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    _seed_zt(c, bearer, cid)
    with _session() as s:
        s.get(AttackAssessment, uuid.UUID(a["id"])).status_rules = status_rules
        row = s.get(AttackCoverage, uuid.UUID(gap["id"]))
        row.status = "gap"
        row.detection_tools = list(tools)
        row.prevention_tools = list(tools)
        row.response_tools = list(tools)
        row.unconfirmed_citations = []
        s.commit()

    seen: list[dict] = []
    runtime = build_runtime_provider()

    def capture(payload: dict) -> LLMResponse:
        seen.append(payload)
        if fixture_mode:
            return runtime.complete("", payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", capture)
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    assert seen, "no risk_synthesize payload was captured"
    code = gap["technique_code"]
    assert code in seen[0]["findings"], sorted(seen[0]["findings"])
    return code, seen[0]["findings"][code]["evidence"], r.json()


def test_a_stored_status_finding_sends_no_computed_function_states(
    app_client,  # noqa: F811
) -> None:
    # Stored "gap", every function's tool confirmed: computed capabilities
    # would all read in place, beside a status of gap.
    _code, ev, _ = _world(app_client, status_rules=1, tools=["Tool A"])
    # Positive first: the stored status, the flag, and the record's own text.
    assert ev["status"] == "gap", ev
    assert ev["status_basis"] == "stored", ev
    assert set(ev) == {"status", "status_basis", "rationale", "notes"}, ev
    # Then the absences, named: nothing computed from the tools.
    assert "missing_functions" not in ev, ev
    for name in _FUNCTIONS:
        assert name not in ev, (name, ev)


def test_a_computed_status_finding_keeps_its_function_states(
    app_client,  # noqa: F811
) -> None:
    # Under R3 the status is computed from the tools; with none it is a gap.
    _code, ev, _ = _world(app_client, status_rules=2, tools=[])
    assert ev["status"] == "gap", ev
    assert ev["status_basis"] == "computed", ev
    assert ev["missing_functions"] == ["detection", "prevention", "response"], ev
    for name in _FUNCTIONS:
        assert ev[name] == {"state": "not_in_place", "tools": []}, (name, ev)


def test_the_fixture_answer_for_a_stored_finding_names_no_axis_or_control(
    app_client,  # noqa: F811
) -> None:
    """What fixture mode answers for a stored-status finding whose row lists
    confirmed tools: no other axis and the exact "none" sentence. That holds
    because the evidence above carries no function states. It does NOT test
    the fixture's own `_risk_status_is_stored` guard (`app/ai/fixtures.py`):
    deleting that guard leaves this green, since no current writer sends
    function states with a stored status (see the guard's docstring)."""
    code, ev, body = _world(app_client, status_rules=1, tools=["Tool A"], fixture_mode=True)
    assert ev["status_basis"] == "stored", ev
    (entry,) = [e for e in body["entries"] if e["source_id"] == code]
    assert entry["other_axes"] == [], entry
    assert entry["compensating_controls"] == _NONE_SENTENCE, entry
