"""#802 slice C, through the route: the chat box proposes, and writes nothing.

`POST /attack/services/{id}/scenarios/parse`. Approved plan: #802, comment
5971765890; the advisor at 18:32Z, copy C1-C9. The world is slice A's: the
base cites EDR Tool, SIEM Tool and SOAR Tool.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.ai_run import AiRun
from app.models.attack_scenario import AttackScenario, AttackScenarioRow
from app.models.audit_entry import AuditEntry
from app.models.llm_call import LLMCall
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import (
    EDR,
    SIEM,
    _error,
    _world,
)

pytestmark = pytest.mark.unit


def _parse(w, text, *, headers=None):
    return w.c.post(
        f"/attack/services/{w.svc_id}/scenarios/parse",
        headers=headers or w.h,
        json={"text": text} if text is not None else {},
    )


def _counts(w) -> tuple[int, ...]:
    with w.sessions() as db:
        return tuple(
            db.execute(select(func.count()).select_from(model)).scalar_one()
            for model in (AttackScenario, AttackScenarioRow, AiRun, LLMCall, AuditEntry)
        )


def test_a_description_becomes_a_proposed_change_list(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _parse(w, "What if we retire edr tool and SIEM Tool, add XDR Suite?")
    assert r.status_code == 200, r.text
    assert r.json() == {"removed": [EDR, SIEM], "added": ["XDR Suite"], "not_understood": []}


def test_a_parse_writes_nothing_and_calls_no_ai(app_parts) -> None:  # noqa: F811
    """Pure: no what-if, no scenario row, no run, no `llm_calls` row and no
    audit entry -- on a proposal, on a clause not understood, and on a
    refusal."""
    w = _world(app_parts)
    before = _counts(w)
    assert _parse(w, "swap EDR Tool for XDR Suite").status_code == 200
    assert _parse(w, "polish the dashboard").status_code == 200
    assert _parse(w, "").status_code == 422
    assert _counts(w) == before


def test_each_clause_not_understood_is_quoted_back_with_c5(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    body = _parse(w, "remove EDR, polish the dashboard").json()
    assert body["removed"] == []
    assert body["not_understood"] == [
        {
            "text": "remove EDR",
            "reason": "unknown_tool",
            "message": 'Not understood: "remove EDR". Pick the tool from the list instead.',
        },
        {
            # A failed removal shares nothing (#824 review, B7).
            "text": "polish the dashboard",
            "reason": "unrecognised",
            "message": 'Not understood: "polish the dashboard". Pick the tool from the list instead.',
        },
    ]


def test_adding_a_cited_client_tool_carries_b4(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    body = _parse(w, "add siem tool").json()
    assert body["added"] == []
    assert body["not_understood"] == [
        {
            "text": "add siem tool",
            "reason": "already_clients",
            "message": (
                "siem tool is already one of the client's tools. Choose it under Tools to "
                "remove, or give the new tool a different name."
            ),
        }
    ]


@pytest.mark.parametrize("text", [None, "", "   ", 7])
def test_an_empty_description_is_refused_with_c7(app_parts, text) -> None:  # noqa: F811
    w = _world(app_parts)
    r = _parse(w, text)
    assert r.status_code == 422, r.text
    assert _error(r) == {"reason": "scenario_chat_empty", "message": "Describe the change first."}


def test_a_description_over_500_characters_is_refused_with_c8(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    assert _parse(w, "remove EDR Tool" + " " * 485).status_code == 200  # exactly 500
    r = _parse(w, "remove EDR Tool" + " " * 486)
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_chat_too_long",
        "message": "Keep the description to 500 characters or fewer.",
    }


def test_with_no_confirmed_assessment_a_parse_is_refused_with_copy_4(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts, release=False)
    svc = w.c.post(
        "/attack/services", headers=w.h, json={"kind": "attack_coverage", "title": "Draft only"}
    ).json()["id"]
    assert w.c.post(f"/attack/services/{svc}/assessments", headers=w.h).status_code == 201
    r = w.c.post(f"/attack/services/{svc}/scenarios/parse", headers=w.h, json={"text": "x"})
    assert r.status_code == 409, r.text
    assert _error(r)["reason"] == "scenario_needs_confirmed_assessment"


def test_a_non_admin_cannot_parse(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    bearer = w.c.post(
        "/auth/register",
        json={
            "email": "someone@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "C",
        },
    ).json()["tokens"]["access_token"]
    r = _parse(
        w, "remove EDR Tool", headers={"Authorization": f"Bearer {bearer}", "X-Client-Id": w.cid}
    )
    assert r.status_code in (401, 403), r.text


def test_another_tenants_service_is_not_found(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    other = w.c.post(
        "/admin/clients",
        headers={"Authorization": w.h["Authorization"]},
        json={"legal_name": "Other"},
    ).json()["id"]
    r = _parse(w, "remove EDR Tool", headers={**w.h, "X-Client-Id": other})
    assert r.status_code == 404, r.text


def test_the_proposal_creates_exactly_that_what_if_on_continue(app_parts) -> None:  # noqa: F811
    """The chat proposes only what Continue accepts: posting its proposal
    (with the added tool's functions chosen) creates exactly that change."""
    w = _world(app_parts)
    proposal = _parse(w, "swap EDR Tool for XDR Suite").json()
    r = w.c.post(
        f"/attack/services/{w.svc_id}/scenarios",
        headers=w.h,
        json={
            "removed": proposal["removed"],
            "added": [{"name": n, "security_functions": ["detect"]} for n in proposal["added"]],
        },
    )
    assert r.status_code == 201, r.text
    assert (r.json()["removed"], [t["name"] for t in r.json()["added"]]) == ([EDR], ["XDR Suite"])
