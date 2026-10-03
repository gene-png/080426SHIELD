"""#802 slice B, through the routes: a what-if that ADDS tools.

The world is slice A's (`test_attack_scenario_routes._world`): technique A is
covered by EDR/EDR/SOAR, B is partial on SIEM's Detect alone, and C is a gap
whose Detect rests on an uncleared inference of EDR. Every other technique is
unassessed and is never asked about.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import FixtureProvider, LLMResponse
from app.models.capability import CapabilityListStatus
from tests._ai_runs import defer_runs
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import (  # noqa: F401  (fixture)
    EDR,
    PURPOSE,
    SIEM,
    SOAR,
    _add_tool_after_approval,
    _ai_runs,
    _error,
    _flags,
    _run_to_completion,
    _world,
    analysis_job,
)

pytestmark = pytest.mark.unit

XDR = "XDR Suite"


def _tool(name=XDR, functions=("detect", "prevent"), **kw):
    return {"name": name, "security_functions": list(functions), **kw}


def _create(w, removed=None, added=None):
    body = {}
    if removed is not None:
        body["removed"] = removed
    if added is not None:
        body["added"] = added
    return w.c.post(f"/attack/services/{w.svc_id}/scenarios", headers=w.h, json=body)


# --- creating ----------------------------------------------------------------------


def test_a_what_if_may_only_add_and_names_the_gaps_an_added_tool_could_fill(
    app_parts,  # noqa: F811
) -> None:
    """XDR declares Detect and Prevent. A is covered: nothing open. B lacks
    Prevent. C's Detect awaits review (not in place) and it lacks Prevent."""
    w = _world(app_parts)
    r = _create(w, added=[_tool(vendor="  Vendor X ", category="XDR")])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["removed"] == []
    assert body["added"] == [
        {
            "name": XDR,
            "vendor": "Vendor X",
            "category": "XDR",
            "security_functions": ["detect", "prevent"],
        }
    ]
    assert body["affected_codes"] == sorted([w.b, w.cc])
    assert (body["affected_by_removal"], body["affected_by_addition_only"]) == (0, 2)
    listed = w.c.get(f"/attack/services/{w.svc_id}/scenarios", headers=w.h).json()
    assert listed["scenarios"][0]["added"] == [XDR]


def test_removals_and_additions_split_the_affected_count(app_parts) -> None:  # noqa: F811
    """Removing EDR affects A and C; with EDR gone A's Detect and Prevent are
    open too, and B is opened by the addition alone."""
    w = _world(app_parts)
    body = _create(w, removed=[EDR], added=[_tool()]).json()
    assert body["affected_codes"] == sorted([w.a, w.b, w.cc])
    assert (body["affected_by_removal"], body["affected_by_addition_only"]) == (2, 1)


@pytest.mark.parametrize("removed, added", [(None, None), ([], []), ([], None), (None, [])])
def test_a_change_of_nothing_is_refused_with_b8(app_parts, removed, added) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _create(w, removed=removed, added=added)
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_empty_change",
        "message": "Choose at least one tool to remove or add.",
    }


def test_an_addition_that_could_change_nothing_is_refused_before_anything_is_stored(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    """Every technique already has the declared functions in place: nothing is
    asked, nothing paid for, and no what-if is stored."""
    w = _world(app_parts)
    monkeypatch.setattr("app.attack.scenario.open_functions", lambda *a, **k: {})
    r = _create(w, added=[_tool()])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_nothing_affected",
        "message": (
            "Every technique the last confirmed assessment scored already has what these "
            "tools do in place, so there is nothing to re-assess."
        ),
    }
    listed = w.c.get(f"/attack/services/{w.svc_id}/scenarios", headers=w.h).json()
    assert listed["scenarios"] == []


def test_adding_a_tool_the_base_cites_is_refused_with_b4(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _create(w, added=[_tool("edr tool")])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_added_tool_is_clients",
        "message": (
            "edr tool is already one of the client's tools. Choose it under Tools to "
            "remove, or give the new tool a different name."
        ),
    }


def test_adding_a_client_tool_the_base_does_not_cite_is_refused_without_the_picker_clause(
    app_parts,  # noqa: F811
) -> None:
    """B4 names "Tools to remove", which lists only cited tools. A tool on the
    client's list that the base never cited is not there."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _add_tool_after_approval(w, "Backup Tool")
    r = _create(w, added=[_tool("Backup Tool")])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_added_tool_is_clients",
        "message": "Backup Tool is already one of the client's tools. Give the new tool a different name.",
    }


def test_a_name_shown_as_another_added_tool_is_refused_with_b5(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _create(w, added=[_tool("Suite 100 Scanner"), _tool("Suite 200 Scanner")])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_added_tool_indistinct",
        "message": (
            "The AI would be shown Suite 200 Scanner under the same name as another tool, "
            "so its credit could not be told apart. Give it a different name."
        ),
    }


def test_a_tool_with_no_function_is_refused_with_b6(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _create(w, added=[_tool(functions=())])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_added_tool_no_functions",
        "message": f"Choose at least one of Detect, Prevent or Respond for {XDR}.",
    }


def test_more_than_ten_tools_is_refused_with_b7(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _create(w, added=[_tool(f"Tool {chr(65 + i)}") for i in range(11)])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_too_many_added",
        "message": "A what-if can add up to 10 tools.",
    }


# --- running ------------------------------------------------------------------------


def _answering(w, rows_by_code, *, seen=None):
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        if seen is not None:
            seen.append(payload)
        sent = payload.get("technique_codes") or []
        return LLMResponse(json.dumps({"rows": [r for c in sent for r in rows_by_code.get(c, [])]}))

    provider.register(PURPOSE, respond)
    w.use(provider)


def test_a_rise_from_an_added_tool_is_counted_marked_and_kept_out_of_copy_18(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """C's Detect was an uncleared inference; XDR, confirmed, fills it: Gap to
    Partial, credited to the added tool. B11 counts it; copy 18 does not. The
    AI also credits SIEM for C's Prevent, which only an added tool may fill:
    set aside as `tool_not_added`."""
    w = _world(app_parts)
    seen: list[dict] = []
    _answering(
        w,
        {w.cc: [_flags(w.cc, XDR, d=True), _flags(w.cc, SIEM, p=True)]},
        seen=seen,
    )
    sid = _create(w, added=[_tool()]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["run_status"] == "completed", body["run_error"]
    assert body["higher_with_added"] == 1
    assert body["scored_higher"] == 0
    assert body["dropped"] == {"tool_not_added": 1}
    diffs = {d["technique_code"]: d for d in body["differences"]}
    assert diffs[w.cc]["today"] == "gap" and diffs[w.cc]["after"] == "partial"
    assert diffs[w.cc]["credited_tool_you_added"] is True
    assert diffs[w.cc]["scored_higher"] is False
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_tools_you_added"] == [XDR]
    # What the model was given: the added tool beside the client's, and the
    # functions it may be asked about.
    (payload,) = seen
    assert [t["name"] for t in payload["added_tools"]] == [XDR]
    assert XDR in [t["name"] for t in payload["available_tools"]]
    assert payload["open_functions"][w.cc] == ["detection", "prevention"]


def test_a_rise_from_a_remaining_tool_is_still_copy_18_beside_an_addition(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """EDR removed, XDR (Respond) added. C lost Detect; the AI credits SIEM, a
    REMAINING tool, there: Gap to Partial, copy 18's anomaly, not B11's."""
    w = _world(app_parts)
    _answering(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = _create(w, removed=[EDR], added=[_tool(functions=("respond",))]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["scored_higher"] == 1
    assert body["higher_with_added"] == 0
    diffs = {d["technique_code"]: d for d in body["differences"]}
    assert diffs[w.cc]["scored_higher"] is True
    assert diffs[w.cc]["credited_tool_you_added"] is False


def test_a_rise_owed_to_a_remaining_tool_is_copy_18_even_beside_an_added_credit(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """#818 review, F3, through the GET. EDR removed, XDR (Prevent) added. C
    lost Detect; the AI re-credits it to SIEM (remaining) and credits XDR for
    Prevent. Without XDR, C still rises from Gap: copy 18 counts it, not B11."""
    w = _world(app_parts)
    _answering(w, {w.cc: [_flags(w.cc, SIEM, d=True), _flags(w.cc, XDR, p=True)]})
    sid = _create(w, removed=[EDR], added=[_tool(functions=("prevent",))]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["dropped"] == {}
    diffs = {d["technique_code"]: d for d in body["differences"]}
    assert diffs[w.cc]["today"] == "gap" and diffs[w.cc]["after"] == "partial"
    assert diffs[w.cc]["credited_tool_you_added"] is True
    assert diffs[w.cc]["scored_higher"] is True
    assert body["scored_higher"] == 1
    assert body["higher_with_added"] == 0


def test_a_tool_the_client_now_has_stops_the_run_before_anything_is_spent(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """#818 review, F4. The client's list gains XDR Suite after the what-if
    added it. Every credit to either would be dropped, so the run is refused,
    typed, and no run is started."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _answering(w, {})
    sid = _create(w, added=[_tool()]).json()["id"]
    _add_tool_after_approval(w, XDR)
    r = w.run(sid)
    assert r.status_code == 409, r.text
    assert _error(r) == {
        "reason": "scenario_added_tool_collides",
        "message": (
            f"{XDR}, a tool you added, can no longer be told apart from one of the client's "
            "tools, so this what-if cannot be analysed. Start a new what-if."
        ),
    }
    assert _ai_runs(w) == []


def test_a_tool_the_client_gains_while_the_run_waits_fails_it_typed(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """F4, in the job: the list changes between the POST and the job."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _answering(w, {w.cc: [_flags(w.cc, XDR, d=True)]})
    runner = defer_runs(w.app)
    sid = _create(w, added=[_tool()]).json()["id"]
    assert w.run(sid).status_code == 202
    _add_tool_after_approval(w, XDR)
    assert runner.run_all() == 1
    body = w.get(sid)
    assert body["run_status"] == "failed"
    assert body["run_error"]["reason"] == "scenario_added_tool_collides"
    assert body["techniques"] == []


def test_a_function_that_is_not_a_string_is_a_typed_422(app_parts) -> None:  # noqa: F811
    """#818 review, F2: it used to be an untyped 500."""
    w = _world(app_parts)
    r = _create(w, added=[_tool(functions=(["detect"],))])
    assert r.status_code == 422, r.text
    assert _error(r)["reason"] == "scenario_added_tool_bad_function"


def test_an_added_tool_is_never_drift(app_parts, analysis_job) -> None:  # noqa: F811
    """The drift check judges the client's list. The admin's tool has no
    capability item; left in, it would make the check unknowable (None)."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _answering(w, {w.cc: [_flags(w.cc, XDR, d=True)]})
    sid = _create(w, added=[_tool()]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 0
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_before_a_run_the_added_tools_result_is_none(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    body = _create(w, added=[_tool()]).json()
    assert body["higher_with_added"] is None
    assert body["after"] is None
