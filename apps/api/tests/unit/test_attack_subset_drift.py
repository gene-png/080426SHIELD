"""#851: ATT&CK rows that credit a tool outside the client's CURRENT security
subset are disclosed, refuse approve, and can be removed by hand.

Plan: #851 comments 5983988541 (track5) and 6022779778 (re-verified at main
82d6114). Ruling: the advisor, #736 comment 5984022081 (option A; release
discloses; the remove-tool control; S1-S5), and the coordinator's D2 (a
narrow `remove_tool` that stamps nothing else).

The world is built through the routes wherever a route exists: a Tech Debt
list whose "Legacy AV" carries the model's provisional "not security" call,
which keeps it in the ATT&CK subset until a consultant confirms the call
(`/security-classification/confirm`); that sign-off is what takes it out.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy import select

from app.models.audit_entry import AuditEntry
from app.models.capability import (
    CapabilityDisposition,
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
)
from app.models.service import Service, ServiceKind, ServiceStatus
from tests._attack_rows import standalone_rows
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

EDR = "EDR Tool"
LEGACY = "Legacy AV"
PORTAL = "Acme Portal"  # the client's own name: shown to the AI as "[CLIENT] Portal"


@dataclass
class World:
    c: Any
    sessions: Any
    h: dict
    cid: str
    svc_id: str
    assessment_id: str
    list_id: str
    items: dict[str, str]
    rows: dict[str, str]

    def get(self) -> dict:
        r = self.c.get(f"/attack/services/{self.svc_id}/assessments/latest", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()

    def patch(self, code: str, body: dict):
        return self.c.patch(f"/attack/coverage/{self.rows[code]}", headers=self.h, json=body)

    def approve(self):
        return self.c.post(f"/attack/assessments/{self.assessment_id}/approve", headers=self.h)

    def confirm_not_security(self, name: str) -> None:
        r = self.c.post(
            f"/tech-debt/capability-items/{self.items[name]}/security-classification/confirm",
            headers=self.h,
        )
        assert r.status_code == 200, r.text

    def approve_list(self) -> None:
        r = self.c.post(f"/tech-debt/capability-lists/{self.list_id}/approve", headers=self.h)
        assert r.status_code == 200, r.text


def _world(app_parts) -> World:  # noqa: F811
    c, _app, sessions = app_parts
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    with sessions() as db:
        td = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=uuid.UUID(cid),
            opened_by=uuid.UUID(me["id"]),
        )
        db.add(td)
        db.flush()
        cl = CapabilityList(service_id=td.id, version=1, status=CapabilityListStatus.DRAFT)
        db.add(cl)
        db.flush()
        items = {}
        for name, security in ((EDR, True), (LEGACY, False), (PORTAL, True)):
            it = CapabilityItem(
                capability_list_id=cl.id,
                name=name,
                # The model's call. A False is provisional until confirmed, so
                # the row stays in the ATT&CK subset (security_scope).
                security_related=security,
                disposition=CapabilityDisposition.KEEP,
            )
            db.add(it)
            db.flush()
            items[name] = str(it.id)
        db.commit()
        list_id = str(cl.id)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()
    rows = {r["technique_code"]: r["id"] for r in standalone_rows(a["coverage"], 3)}
    return World(c, sessions, h, cid, svc_id, a["id"], list_id, items, rows)


def _codes(w: World) -> list[str]:
    return sorted(w.rows)


def _outside(w: World) -> list[tuple]:
    return [
        (o["technique_code"], o["field"], o["tool"], o["locked"])
        for o in w.get()["citations_outside_subset"]
    ]


# --- disclosed on the workspace, refused at approve -----------------------------------


def test_a_tool_confirmed_not_security_is_disclosed_and_blocks_approve(
    app_parts,  # noqa: F811
) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    assert w.patch(code, {"detection_tools": [EDR, LEGACY]}).status_code == 200
    w.confirm_not_security(LEGACY)
    assert _outside(w) == [(code, "detection_tools", LEGACY, False)]
    r = w.approve()
    assert r.status_code == 409, r.text
    detail = r.json()["error"]
    assert detail["reason"] == "attack_not_release_ready"
    assert detail["cites_outside_subset"] == [
        {"technique_code": code, "field": "detection_tools", "tool": LEGACY, "locked": False}
    ]
    # S4 (the "not in" variant, PENDING the advisor) and S3b (approved).
    assert (
        "1 technique row credits a tool that is not in the client's security tool list"
        in detail["message"]
    )
    assert detail["message"].endswith(
        "Remove the tool in the technique's panel, or unlock the row and use Run AI."
    )


def test_removing_the_tool_by_hand_clears_it_and_approve_proceeds(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [EDR, LEGACY]})
    w.confirm_not_security(LEGACY)
    assert _outside(w) != []  # the positive state first
    r = w.patch(code, {"remove_tool": {"field": "detection_tools", "name": LEGACY}})
    assert r.status_code == 200, r.text
    assert r.json()["detection_tools"] == [EDR]
    assert _outside(w) == []
    assert w.approve().status_code == 200


def test_a_locked_row_is_listed_as_locked(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [LEGACY]})
    w.patch(code, {"locked": True})
    w.confirm_not_security(LEGACY)
    assert _outside(w) == [(code, "detection_tools", LEGACY, True)]


def test_every_field_and_row_is_read(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    a, b = _codes(w)[:2]
    w.patch(a, {"prevention_tools": [LEGACY]})
    w.patch(b, {"response_tools": [LEGACY], "detection_tools": [EDR]})
    w.confirm_not_security(LEGACY)
    assert sorted(_outside(w)) == sorted(
        [(a, "prevention_tools", LEGACY, False), (b, "response_tools", LEGACY, False)]
    )


# --- which names are "outside": D1(a), behind one predicate ---------------------------


def test_a_free_text_tool_never_on_the_list_is_listed(app_parts) -> None:  # noqa: F811
    """D1(a), recommended and pending the advisor: a name the subset does not
    know is outside it, however it got onto the row."""
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": ["Shadow Scanner"]})
    assert _outside(w) == [(code, "detection_tools", "Shadow Scanner", False)]


@pytest.mark.parametrize("spelling", ["EDR TOOL", "edr  tool", "[CLIENT] Portal"])
def test_the_runs_resolver_decides_what_is_the_same_tool(app_parts, spelling) -> None:  # noqa: F811
    """Case and whitespace, and the shown form of a client-named tool, are the
    same tool: the run's own name tiers decide, never a second comparison."""
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [spelling]})
    assert _outside(w) == []
    w.patch(code, {"detection_tools": [spelling, "Shadow Scanner"]})
    assert _outside(w) == [(code, "detection_tools", "Shadow Scanner", False)]


def test_an_approved_list_answers_from_its_snapshot_until_approved_again(
    app_parts,  # noqa: F811
) -> None:  # noqa: F811
    """The snapshot is the membership: confirming after approval does not move
    it (pinned), and approving the list again does."""
    w = _world(app_parts)
    code = _codes(w)[0]
    w.approve_list()
    w.patch(code, {"detection_tools": [LEGACY]})
    w.confirm_not_security(LEGACY)
    assert _outside(w) == []
    w.approve_list()
    assert _outside(w) == [(code, "detection_tools", LEGACY, False)]


# --- after approval: disclosed, never refused -----------------------------------------


def test_an_approved_assessment_still_discloses_a_later_removal(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [LEGACY]})
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    body = w.get()
    assert body["status"] == "approved"
    assert [(o["technique_code"], o["tool"]) for o in body["citations_outside_subset"]] == [
        (code, LEGACY)
    ]


def test_the_what_if_base_carries_the_same_count(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [LEGACY, EDR]})
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    r = w.c.get(f"/attack/services/{w.svc_id}/scenarios", headers=w.h)
    assert r.status_code == 200, r.text
    assert r.json()["base"]["citations_outside_subset"] == 1


# --- the narrow remove (D2): it removes one name and stamps nothing else ---------------


def test_removing_one_tool_leaves_the_others_review_state_as_it_was(
    app_parts,  # noqa: F811
) -> None:  # noqa: F811
    """D2. A PATCH of a whole list stamps every citation in it confirmed (#102);
    the remove control must not. The inferred entry below is what the AI run
    writes for an uncleared citation (`routes/attack.py`, the run's row flags)."""
    from app.models.attack_assessment import AttackCoverage

    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [EDR, LEGACY]})
    with w.sessions() as db:
        row = db.get(AttackCoverage, uuid.UUID(w.rows[code]))
        row.unconfirmed_citations = [
            {
                "tool": EDR,
                "cited": "EDR",
                "reason": "substring",
                "field": "detection_tools",
                "cleared_at": None,
            },
            {
                "tool": LEGACY,
                "cited": "Legacy",
                "reason": "substring",
                "field": "detection_tools",
                "cleared_at": None,
            },
        ]
        db.commit()
    r = w.patch(code, {"remove_tool": {"field": "detection_tools", "name": LEGACY}})
    assert r.status_code == 200, r.text
    with w.sessions() as db:
        row = db.get(AttackCoverage, uuid.UUID(w.rows[code]))
        assert row.detection_tools == [EDR]
        assert [(e["tool"], e["cleared_at"]) for e in row.unconfirmed_citations] == [(EDR, None)]
        audited = (
            db.execute(
                select(AuditEntry).where(AuditEntry.action == "attack.coverage.tool_removed")
            )
            .scalars()
            .all()
        )
        # The technique and the list, never the tool's name (the client's data).
        assert [a.details for a in audited] == [
            {"technique_code": code, "field": "detection_tools"}
        ]


@pytest.mark.parametrize(
    ("remove", "reason"),
    [
        ({"field": "notes", "name": LEGACY}, "remove_tool_unknown_field"),
        ({"field": "detection_tools", "name": "Not There"}, "remove_tool_not_listed"),
    ],
)
def test_a_remove_that_cannot_apply_is_a_typed_422(app_parts, remove, reason) -> None:  # noqa: F811
    w = _world(app_parts)
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [EDR]})
    r = w.patch(code, {"remove_tool": remove})
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == reason
    assert w.get()["coverage"]  # the row is untouched
    with w.sessions() as db:
        from app.models.attack_assessment import AttackCoverage

        assert db.get(AttackCoverage, uuid.UUID(w.rows[code])).detection_tools == [EDR]
