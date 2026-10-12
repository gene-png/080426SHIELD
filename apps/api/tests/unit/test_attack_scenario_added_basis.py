"""For #1012, the advisor's option A (#736 6115773247): the what-if's "tools
added since the base" is judged against the Tech Debt list version IN FORCE
when the base was approved, rebuilt from the record, by tool name.

Before this, a tool counted as added when the capability ROW it was offered
from was created after the base's approval. Re-extraction mints a new list
version with new rows, so once #1012 offered only the version in force, every
tool of a re-extracted and re-approved list read as "added since the base".

The record the rebuild reads: each version's approval times (the
`capability_list.approved` audit rows and `approved_at`), its recorded
membership (`approved_membership`, frozen at approval), and the base's
approval time. A snapshot overwritten by a re-approval AFTER the base no
longer says what the base was offered, so that reads "cannot be checked"
(null), never a guess.

Driven through the routes: the Tech Debt approve route and the what-if run
(`POST /attack/scenarios/{id}/run`), on `test_attack_scenario_routes`'s
world. Times are moved by direct SQL only to place v1's upload and approval
BEFORE the base's approval, a state the routes reach whenever a consultant
approves the Tech Debt list before the ATT&CK assessment.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.models.attack_assessment import AttackAssessment
from app.models.audit_entry import AuditEntry
from app.models.capability import (
    CapabilityDisposition,
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
)
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import (
    EDR,
    SIEM,
    SOAR,
    World,
    _flags,
    _run_to_completion,
    _world,
)

pytestmark = pytest.mark.unit

XDR = "XDR Platform"
MAIL = "Mail Gateway"  # on the list, cited by no base row


def _v1_id(w: World) -> uuid.UUID:
    with w.sessions() as db:
        return db.execute(select(CapabilityList.id).where(CapabilityList.version == 1)).scalar_one()


def _approve(w: World, list_id: uuid.UUID) -> None:
    """Approve through the Tech Debt route, every row decided first."""
    with w.sessions() as db:
        db.execute(
            update(CapabilityItem)
            .where(CapabilityItem.capability_list_id == list_id)
            .values(disposition=CapabilityDisposition.KEEP)
        )
        db.commit()
    r = w.c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=w.h)
    assert r.status_code == 200, r.text


def _v1_approved_before_the_base(w: World) -> uuid.UUID:
    """v1 approved through the route, then its upload, rows and approval
    placed an hour before the base's approval."""
    v1 = _v1_id(w)
    _approve(w, v1)
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        earlier = base_at - timedelta(hours=1)
        db.execute(
            update(CapabilityList)
            .where(CapabilityList.id == v1)
            .values(created_at=earlier - timedelta(hours=1), approved_at=earlier)
        )
        db.execute(
            update(CapabilityItem)
            .where(CapabilityItem.capability_list_id == v1)
            .values(created_at=earlier - timedelta(hours=1))
        )
        moved = db.execute(
            update(AuditEntry)
            .where(
                AuditEntry.action == "capability_list.approved",
                AuditEntry.target_id == v1,
            )
            .values(at=earlier)
        ).rowcount
        assert moved == 1, moved  # the route wrote exactly one approval
        db.commit()
    return v1


def _re_extracted_v2(w: World, names: list[str]) -> uuid.UUID:
    """A re-extraction: v2 of the same service with NEW rows, uploaded and
    approved after the base."""
    with w.sessions() as db:
        v1 = db.get(CapabilityList, _v1_id(w))
        v2 = CapabilityList(service_id=v1.service_id, version=2, status=CapabilityListStatus.DRAFT)
        db.add(v2)
        db.flush()
        for name in names:
            db.add(CapabilityItem(capability_list_id=v2.id, name=name))
        db.commit()
        v2_id = v2.id
    _approve(w, v2_id)
    return v2_id


def _what_if(w: World, answers: dict) -> dict:
    w.answer(answers)
    sid = w.create([EDR]).json()["id"]
    return _run_to_completion(w, sid)


def test_a_re_extracted_list_with_the_same_tools_reads_none_added(app_parts) -> None:  # noqa: F811
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _v1_approved_before_the_base(w)
    _re_extracted_v2(w, [EDR, SIEM, SOAR])
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_a_tool_new_in_the_re_extracted_list_reads_added(app_parts) -> None:  # noqa: F811
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _v1_approved_before_the_base(w)
    _re_extracted_v2(w, [EDR, SIEM, SOAR, XDR])
    body = _what_if(w, {w.cc: [_flags(w.cc, XDR, d=True)], w.a: [_flags(w.a, SIEM, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True and marks[w.a] is False, marks


def test_a_snapshot_re_approved_after_the_base_reads_null(app_parts) -> None:  # noqa: F811
    """v1 was in force at the base, and was approved again after it: the
    recorded membership is the later one, so what the base was offered
    cannot be read. Null, never 0."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    v1 = _v1_approved_before_the_base(w)
    _approve(w, v1)  # re-approval after the base overwrites the snapshot
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["after"] is not None
    assert body["tools_added_since_base"] is None, body["tools_added_since_base"]


def test_a_draft_only_base_still_counts_a_row_added_after_it(app_parts) -> None:  # noqa: F811
    """No version was approved when the base was: its newest draft was in
    force, and a row added to it afterwards is added; its older rows are not."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        db.add(CapabilityItem(capability_list_id=_v1_id(w), name=XDR))
        db.commit()
    body = _what_if(w, {w.cc: [_flags(w.cc, XDR, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]


def test_a_tool_the_base_credited_is_not_added_though_its_row_was_re_created(
    app_parts,  # noqa: F811
) -> None:
    """The base cites SOAR. After the base, SOAR's row on the (draft) list is
    deleted and typed in again: a new row, created after the base. The base
    credited the tool, so it is not new to the base."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        v1 = _v1_id(w)
        old = db.execute(
            select(CapabilityItem).where(
                CapabilityItem.capability_list_id == v1, CapabilityItem.name == SOAR
            )
        ).scalar_one()
        db.delete(old)
        db.flush()
        db.add(CapabilityItem(capability_list_id=v1, name=SOAR))
        db.commit()
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]


def test_a_draft_at_the_base_approved_since_is_judged_as_the_draft_it_was(
    app_parts,  # noqa: F811
) -> None:
    """v1 was a DRAFT when the base was approved (so it was in force then,
    read by its rows), gained a tool, and was approved afterwards. Only the
    tool added after the base counts. MAIL is on v1 from before the base and
    the base cites it nowhere, so only v1's rows can say the base had it."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        db.add(
            CapabilityItem(
                capability_list_id=_v1_id(w),
                name=MAIL,
                created_at=base_at - timedelta(minutes=5),
            )
        )
        db.add(CapabilityItem(capability_list_id=_v1_id(w), name=XDR))
        db.commit()
    _approve(w, _v1_id(w))
    body = _what_if(w, {w.cc: [_flags(w.cc, XDR, d=True)], w.a: [_flags(w.a, SIEM, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True and marks[w.a] is False, marks
