"""#865: a tenant user's name typed into an ATT&CK AI payload reaches the
provider as [NAME].

The tenant's user names are the redactor's name dictionary
(`name_hints_for_tenant`), as Tech Debt's extraction and the what-if chat box
(#863) already use them. Two ATT&CK payloads carried admin-typed text with no
dictionary at all:

- the what-if re-assessment: an added tool's name, vendor and category are
  typed by the admin on the what-if panel, and the client's remaining tools
  are Tech Debt capability rows an admin can edit;
- `mitre_map`: the same capability rows, offered as `capability_list`.

Every expected value here is the scenario's literal ("Dana Whitfield", the
placeholder "[NAME]"), never a call to the redactor.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import FixtureProvider, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList
from app.models.service import Service, ServiceKind
from app.models.user import User, UserRole
from tests._ai_runs import defer_runs, get_run, start_run
from tests.unit.test_ai_runs_attack import _world as _mitre_world
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import (
    EDR,
    PURPOSE,
    SIEM,
    _error,
    _flags,
    _run_to_completion,
    _world,
)

pytestmark = pytest.mark.unit

#: A tenant user, and a tool an admin named after them.
DANA = "Dana Whitfield"
DANA_TOOL = "Dana Whitfield Scanner"
#: What the model is shown for it: the person's name as the placeholder.
DANA_TOOL_SHOWN = "[NAME] Scanner"
SAM = "Sam Ortiz"
SAM_TOOL = "Sam Ortiz Scanner"


def _tenant_user(w, display_name: str, email: str) -> None:
    with w.sessions() as db:
        db.add(
            User(
                email=email,
                password_hash="x" * 64,
                role=UserRole.CLIENT,
                display_name=display_name,
                client_id=uuid.UUID(w.cid),
            )
        )
        db.commit()


def _create(w, added):
    return w.c.post(f"/attack/services/{w.svc_id}/scenarios", headers=w.h, json={"added": added})


def _tool(name: str) -> dict:
    return {"name": name, "security_functions": ["detect", "prevent"]}


def _no_person_in(payload: dict) -> None:
    blob = json.dumps(payload)
    assert "Dana" not in blob and "Whitfield" not in blob, blob


# --- the what-if re-assessment --------------------------------------------------------


def test_a_tenant_users_name_in_an_added_tool_reaches_the_ai_redacted(
    app_parts,  # noqa: F811
) -> None:
    """The added tool is sent as "[NAME] Scanner", and the model's citation of
    that shown form is credited to the tool the admin added: the reading is
    given the SAME dictionary as the egress, so the credit is not lost."""
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    seen: list[dict] = []
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        sent = payload.get("technique_codes") or []
        rows = [_flags(w.cc, DANA_TOOL_SHOWN, d=True)] if w.cc in sent else []
        return LLMResponse(json.dumps({"rows": rows}))

    provider.register(PURPOSE, respond)
    w.use(provider)
    r = _create(w, [_tool(DANA_TOOL)])
    assert r.status_code == 201, r.text
    body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "completed", body["run_error"]
    (payload,) = seen
    _no_person_in(payload)
    assert [t["name"] for t in payload["added_tools"]] == [DANA_TOOL_SHOWN]
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_tools_you_added"] == [DANA_TOOL]
    assert body["dropped"] == {}


def test_two_added_tools_shown_as_one_placeholder_are_refused_at_creation(
    app_parts,  # noqa: F811
) -> None:
    """Both names are tenant users, so the model would see "[NAME] Scanner"
    twice: B5, before anything is stored."""
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    _tenant_user(w, SAM, "sam.ortiz@acme.example")
    r = _create(w, [_tool(DANA_TOOL), _tool(SAM_TOOL)])
    assert r.status_code == 422, r.text
    assert _error(r)["reason"] == "scenario_added_tool_indistinct"
    assert SAM_TOOL in _error(r)["message"]


def test_a_user_added_after_creation_whose_name_merges_two_added_tools_stops_the_run(
    app_parts,  # noqa: F811
) -> None:
    """F4's re-check, given today's dictionary: Sam joins the tenant after the
    what-if was created, so both added tools would now be shown as one."""
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    r = _create(w, [_tool(DANA_TOOL), _tool(SAM_TOOL)])
    assert r.status_code == 201, r.text
    _tenant_user(w, SAM, "sam.ortiz@acme.example")
    run = w.run(r.json()["id"])
    assert run.status_code == 409, run.text
    assert _error(run)["reason"] == "scenario_added_tool_collides"


def test_a_kept_tool_shown_as_the_removed_one_is_not_credited_for_it(
    app_parts,  # noqa: F811
) -> None:
    """The dictionary is whatever display names the tenant has. With users
    displayed as "EDR" and "SIEM", the removed EDR Tool and the kept SIEM Tool
    are both shown as "[NAME] Tool", so a credit to that string cannot be told
    apart: it is set aside, never given to SIEM Tool (F2's rule, judged with
    the run's own dictionary)."""
    w = _world(app_parts)
    _tenant_user(w, "EDR", "edr.lead@acme.example")
    _tenant_user(w, "SIEM", "siem.lead@acme.example")
    w.answer({w.a: [_flags(w.a, "[NAME] Tool", d=True)]})
    r = w.create([EDR])
    assert r.status_code == 201, r.text
    body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "completed", body["run_error"]
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert SIEM not in lists[w.a]["detection_tools"], lists[w.a]
    assert body["dropped"] == {"tool_unconfirmed": 1}


def test_a_removal_takes_its_placeholder_spelling_with_it_at_creation(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """The client's list holds Dana Whitfield Scanner AND "[NAME] Scanner", the
    spelling an extraction stores once the redactor has shown it that way (the
    `soc_twins` world, with a person's name in place of the client's). Removing
    the one removes the other, so A, which cites only the placeholder, is
    affected too."""
    import tests.unit.test_attack_scenario_routes as routes_world

    monkeypatch.setattr(routes_world, "SOC_NAMED", DANA_TOOL)
    monkeypatch.setattr(routes_world, "SOC_PLACEHOLDER", DANA_TOOL_SHOWN)
    w = _world(app_parts, soc_twins=True)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    r = w.create([DANA_TOOL])
    assert r.status_code == 201, r.text
    assert r.json()["affected_codes"] == sorted([w.a, w.b])


# --- mitre_map ------------------------------------------------------------------------


def test_a_tenant_users_name_in_a_capability_reaches_mitre_map_redacted(
    app_parts,  # noqa: F811
) -> None:
    w = _mitre_world(app_parts)
    runner = defer_runs(w.app)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    with w.sessions() as db:
        td = db.execute(
            select(Service).where(
                Service.client_id == uuid.UUID(w.cid), Service.kind == ServiceKind.TECH_DEBT
            )
        ).scalar_one()
        cl = db.execute(
            select(CapabilityList).where(CapabilityList.service_id == td.id)
        ).scalar_one()
        db.add(CapabilityItem(capability_list_id=cl.id, name=DANA_TOOL))
        db.commit()
    seen: list[dict] = []

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"techniques": []}))

    w.provider.register("mitre_map", respond)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert run["status"] == "completed", run
    assert seen, "mitre_map was never called"
    for payload in seen:
        _no_person_in(payload)
        names = [c["name"] for c in payload["capability_list"]]
        assert DANA_TOOL_SHOWN in names, names
