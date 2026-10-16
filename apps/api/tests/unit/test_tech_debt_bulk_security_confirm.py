"""#1174: confirm many negative security classifications at once.

Gene decided: "Select all on the security-classification confirm, then untick
the exceptions." The plan (#736 6205635962; strings approved 6206818759 item
7) adds `POST /tech-debt/capability-lists/{id}/items/security-classification/
confirm` with `{item_ids}`:

* all or nothing: one selected row not awaiting sign-off refuses the whole
  request, typed `not_a_negative_classification`, and nothing is written;
* the SAME per-row effect as the single confirm, audit rows included, because
  ATT&CK's what-if dates each row's exit from scope by its own per-item
  confirmation row (`routes/attack_scenarios.py`);
* it is a step-2 edit, so the list's revision moves once.
"""

from __future__ import annotations

import io
import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityList
from tests._ai_runs import tech_debt_extract
from tests.unit.test_capability_list_revision import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

_ITEMS = [
    {
        "name": "Tool Sec",
        "category": "EDR/XDR",
        "annual_cost_usd": 1000,
        "confidence_pct": 90,
        "source_row_index": 0,
        "security_related": True,
        "security_functions": ["detect"],
    },
    {
        "name": "Tool HR",
        "category": "HCM/HR",
        "annual_cost_usd": 2000,
        "confidence_pct": 90,
        "source_row_index": 1,
        "security_related": False,
        "security_functions": [],
    },
    {
        "name": "Tool Mail",
        "category": "Collaboration/Communication",
        "annual_cost_usd": 3000,
        "confidence_pct": 90,
        "source_row_index": 2,
        "security_related": False,
        "security_functions": [],
    },
    {
        "name": "Tool Old",
        "category": "SIEM/SOAR",
        "annual_cost_usd": 4000,
        "confidence_pct": 60,
        "source_row_index": 3,
        "notes": "Security tool not in use: retired last year.",
        "security_related": False,
        "security_functions": [],
    },
]
_CSV = b"Tool\nTool Sec\nTool HR\nTool Mail\nTool Old\n"


def _extract_list(c, h, title: str) -> tuple[str, dict[str, str], str]:
    """One extracted list of `_ITEMS` in a new service: (list id, ids by name,
    service id)."""
    svc_id = c.post("/tech-debt/services", headers=h, json={"title": title}).json()["id"]
    art = c.post("/artifacts", headers=h, files={"file": ("inv.csv", io.BytesIO(_CSV), "text/csv")})
    assert art.status_code == 201, art.text
    body = tech_debt_extract(c, svc_id, h, art.json()["id"])
    return body["id"], {i["name"]: i["id"] for i in body["items"]}, svc_id


def _world(app_client):  # noqa: F811
    c, sessions, provider = app_client
    bearer = _register(c, "admin@example.com")
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": _ITEMS})))
    list_id, ids, svc_id = _extract_list(c, h, "Portfolio")
    return c, sessions, h, list_id, ids, svc_id


def _confirm(c, h, list_id: str, item_ids: list[str]):
    return c.post(
        f"/tech-debt/capability-lists/{list_id}/items/security-classification/confirm",
        headers=h,
        json={"item_ids": item_ids},
    )


def _row(c, h, svc_id: str, item_id: str) -> dict:
    r = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h)
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["id"] == item_id)


def _audit_rows(sessions, item_id: str) -> list[AuditEntry]:
    with sessions() as s:
        return list(
            s.execute(
                select(AuditEntry).where(
                    AuditEntry.target_type == "capability_item",
                    AuditEntry.target_id == uuid.UUID(item_id),
                )
            ).scalars()
        )


def _audits(sessions, item_id: str) -> list[str]:
    with sessions() as s:
        return [
            a.action
            for a in s.execute(
                select(AuditEntry).where(
                    AuditEntry.target_type == "capability_item",
                    AuditEntry.target_id == uuid.UUID(item_id),
                )
            ).scalars()
        ]


def _revision(sessions, list_id: str) -> int:
    with sessions() as s:
        return s.get(CapabilityList, uuid.UUID(list_id)).revision


def test_confirms_exactly_the_sent_rows(app_client) -> None:  # noqa: F811
    c, _s, h, list_id, ids, svc_id = _world(app_client)
    r = _confirm(c, h, list_id, [ids["Tool HR"], ids["Tool Old"]])
    assert r.status_code == 200, r.text
    by_id = {i["id"]: i for i in r.json()["items"]}
    assert by_id[ids["Tool HR"]]["security_class_confirmed"] is True
    assert by_id[ids["Tool Old"]]["security_class_confirmed"] is True
    # The unticked exception stays in the queue.
    assert by_id[ids["Tool Mail"]]["security_class_confirmed"] is False


def test_each_row_gets_the_single_confirms_own_audit_row(app_client) -> None:  # noqa: F811
    """ATT&CK's what-if dates each row's exit from scope by its own per-item
    row, so a bulk confirm writes exactly what N single confirms write."""
    c, sessions, h, list_id, ids, svc_id = _world(app_client)
    r = _confirm(c, h, list_id, [ids["Tool HR"], ids["Tool Old"]])
    assert r.status_code == 200, r.text
    assert _audits(sessions, ids["Tool HR"]) == [
        "capability_item.security_classification_confirmed"
    ]
    # #845: a not-in-use security tool is recorded as taken out of ATT&CK scope.
    assert _audits(sessions, ids["Tool Old"]) == ["capability_item.removed_from_attack_scope"]
    assert _audits(sessions, ids["Tool Mail"]) == []
    # The single confirm's own details, per row: the name, and for a
    # not-in-use tool its note too.
    assert _audit_rows(sessions, ids["Tool HR"])[0].details == {"name": "Tool HR"}
    assert _audit_rows(sessions, ids["Tool Old"])[0].details == {
        "name": "Tool Old",
        "notes": "Security tool not in use: retired last year.",
    }


def _audit_written(sessions, before: set, names_by_id: dict[str, str]) -> list[tuple]:
    """Every audit row written since `before` (a set of ids), as (action,
    target type, the target's NAME, details, actor): the target id differs
    between two lists, the row it names does not."""
    with sessions() as s:
        rows = s.execute(select(AuditEntry)).scalars().all()
        return sorted(
            (
                a.action,
                a.target_type,
                names_by_id.get(str(a.target_id), str(a.target_id)),
                json.dumps(a.details, sort_keys=True),
                str(a.actor_user_id),
            )
            for a in rows
            if a.id not in before
        )


def _audit_ids(sessions) -> set:
    with sessions() as s:
        return set(s.execute(select(AuditEntry.id)).scalars())


def test_one_bulk_confirm_writes_what_n_single_confirms_write(app_client) -> None:  # noqa: F811
    """Parity, not a hand-typed expectation: the same two rows in two lists of
    the same extraction, one list signed off row by row through the single
    route, the other in one bulk call. Their audit trails must match row for
    row; one list-level row in place of the per-row ones would differ."""
    c, sessions, h, list_id, ids, _svc = _world(app_client)
    other_list, other_ids, _other_svc = _extract_list(c, h, "Second portfolio")
    picked = ["Tool HR", "Tool Old"]

    before = _audit_ids(sessions)
    for name in picked:
        r = c.post(
            f"/tech-debt/capability-items/{ids[name]}/security-classification/confirm",
            headers=h,
        )
        assert r.status_code == 200, r.text
    singles = _audit_written(sessions, before, {v: k for k, v in ids.items()})

    before = _audit_ids(sessions)
    assert _confirm(c, h, other_list, [other_ids[n] for n in picked]).status_code == 200
    bulk = _audit_written(sessions, before, {v: k for k, v in other_ids.items()})

    assert len(singles) == len(picked), singles  # POSITIVE CONTROL: one per row
    assert bulk == singles


def test_the_revision_moves_once(app_client) -> None:  # noqa: F811
    c, sessions, h, list_id, ids, svc_id = _world(app_client)
    before = _revision(sessions, list_id)
    assert _confirm(c, h, list_id, [ids["Tool HR"], ids["Tool Mail"]]).status_code == 200
    assert _revision(sessions, list_id) == before + 1


@pytest.mark.parametrize("bad", ["Tool Sec", "already-confirmed"])
def test_one_row_not_awaiting_sign_off_refuses_the_whole_request(
    app_client, bad: str  # noqa: F811
) -> None:
    c, sessions, h, list_id, ids, svc_id = _world(app_client)
    if bad == "already-confirmed":
        assert _confirm(c, h, list_id, [ids["Tool Mail"]]).status_code == 200
        target = ids["Tool Mail"]
    else:
        target = ids[bad]
    before = _revision(sessions, list_id)
    r = _confirm(c, h, list_id, [ids["Tool HR"], target])
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "not_a_negative_classification"
    # Nothing was written: the valid row is still awaiting sign-off, with no
    # audit row of its own, and the revision did not move.
    assert _row(c, h, svc_id, ids["Tool HR"])["security_class_confirmed"] is False
    assert _audits(sessions, ids["Tool HR"]) == []
    assert _revision(sessions, list_id) == before


def test_a_row_from_another_list_is_refused(app_client) -> None:  # noqa: F811
    """A REAL row awaiting sign-off in another list, so only the route's list
    filter can refuse it (a made-up id would be refused with no filter at all)."""
    c, sessions, h, list_id, ids, svc_id = _world(app_client)
    _other_list, other_ids, _other_svc = _extract_list(c, h, "Second portfolio")
    r = _confirm(c, h, list_id, [ids["Tool HR"], other_ids["Tool HR"]])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "capability_items_not_in_list"
    assert _row(c, h, svc_id, ids["Tool HR"])["security_class_confirmed"] is False
    assert _audits(sessions, other_ids["Tool HR"]) == []


def test_an_empty_selection_is_refused(app_client) -> None:  # noqa: F811
    c, _s, h, list_id, _ids, _svc = _world(app_client)
    r = _confirm(c, h, list_id, [])
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "no_items_selected"
