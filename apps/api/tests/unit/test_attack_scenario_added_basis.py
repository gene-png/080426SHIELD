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

Audit rows are moved the same way, by a Core `update(AuditEntry)`. That
BYPASSES `_block_audit_mutations` (`app/models/audit_entry.py`), which
inspects only ORM-dirty instances in a flush; production code can never do
this, and these tests do it only to place a route-written row in time.
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
    _approve_before_the_base(w, v1)
    return v1


def _approve_before_the_base(w: World, list_id: uuid.UUID) -> None:
    """Approve `list_id` through the route, then place its upload, rows and
    approval an hour before the base's approval. The approval's audit row is
    moved by a Core update, which bypasses `_block_audit_mutations` (see the
    module docstring)."""
    v1 = list_id
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


def test_an_uncited_tool_in_the_approved_snapshot_is_not_added(app_parts) -> None:  # noqa: F811
    """MAIL is in v1's approved snapshot, which was in force at the base, and
    no base row cites it. Re-extracted into v2, it is not new: only the
    snapshot can say the base had it."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        db.add(CapabilityItem(capability_list_id=_v1_id(w), name=MAIL))
        db.commit()
    _v1_approved_before_the_base(w)
    with w.sessions() as db:
        snapshot = db.get(CapabilityList, _v1_id(w)).approved_membership
    assert MAIL in {e["name"] for e in snapshot}, snapshot
    _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_a_pre_0043_list_in_force_at_the_base_reads_null(app_parts) -> None:  # noqa: F811
    """The shape migration 0043 left on lists approved before it: approved,
    with `approved_at` and its approval on record, membership NULL. In force
    at the base, its membership then cannot be read: null, and the run
    still completes."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    v1 = _v1_approved_before_the_base(w)
    with w.sessions() as db:
        db.execute(
            update(CapabilityList).where(CapabilityList.id == v1).values(approved_membership=None)
        )
        db.commit()
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["run_status"] == "completed", body["run_status"]
    assert body["after"] is not None
    assert body["tools_added_since_base"] is None, body["tools_added_since_base"]


def test_a_self_contradicting_approval_trail_reads_null(app_parts) -> None:  # noqa: F811
    """A RATCHET on `_SAME_APPROVAL`, not a live case. `approved_at` (the
    LAST approval) is set a day before the only audited approval, so the
    trail contradicts itself. No current writer produces this: the approve
    route stamps `approved_at` and writes the audit row in one transaction,
    so the state is built here by hand. It would become reachable if a
    writer audited an approval without stamping `approved_at`, or stamped
    `approved_at` from elsewhere; the answer must then be null, never a
    reading of a trail that disagrees with itself."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    v1 = _v1_approved_before_the_base(w)
    with w.sessions() as db:
        cl = db.get(CapabilityList, v1)
        cl.approved_at = cl.approved_at - timedelta(days=1)
        db.commit()
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["run_status"] == "completed", body["run_status"]
    assert body["tools_added_since_base"] is None, body["tools_added_since_base"]


def _override(w: World, item_id: uuid.UUID) -> None:
    """The real override endpoint, after the base."""
    r = w.c.post(
        f"/tech-debt/capability-items/{item_id}/security-classification/override",
        headers=w.h,
        json={"security_functions": ["detect"]},
    )
    assert r.status_code == 200, r.text


def _item(w: World, list_id: uuid.UUID, name: str) -> uuid.UUID:
    with w.sessions() as db:
        return db.execute(
            select(CapabilityItem.id).where(
                CapabilityItem.capability_list_id == list_id, CapabilityItem.name == name
            )
        ).scalar_one()


def test_an_override_after_the_base_does_not_add_a_tool_in_the_approved_snapshot(
    app_parts,  # noqa: F811
) -> None:
    """#736 6116519635: (ii) does not apply where the base's basis is an
    APPROVED version's recorded membership. MAIL (cited by no base row) was in
    v1's snapshot in force at the base; re-extracted into v2 and overridden
    after the base, it is still not new."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        db.add(CapabilityItem(capability_list_id=_v1_id(w), name=MAIL))
        db.commit()
    _v1_approved_before_the_base(w)
    v2 = _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    _override(w, _item(w, v2, MAIL))
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_an_override_after_the_base_adds_a_tool_in_the_drafts_branch(
    app_parts,  # noqa: F811
) -> None:
    """(ii) in the DRAFTS branch: MAIL was on the draft in force at the base
    but confirmed NOT security, so offered to nobody. The override endpoint
    brings it into scope after the base: it is new to the AI."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _mail_confirmed_out_before_the_base(w)
    _override(w, _item(w, _v1_id(w), MAIL))
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True, marks


def test_an_override_on_the_basis_row_counts_though_the_offered_row_has_none(
    app_parts,  # noqa: F811
) -> None:
    """(ii) is judged on the row the drafts-branch basis reads, not on the
    offered row. v1 was a DRAFT at the base with MAIL confirmed NOT security
    (offered to nobody). After the base, v1's MAIL is overridden into scope,
    then v2 is re-extracted with MAIL in scope by classification (no
    override on v2's row) and approved. MAIL is new to the AI."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _mail_confirmed_out_before_the_base(w)
    _override(w, _item(w, _v1_id(w), MAIL))
    v2 = _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    with w.sessions() as db:
        offered_row = db.get(CapabilityItem, _item(w, v2, MAIL))
        assert offered_row.security_related is None  # in scope by classification
        overrides_on_v2 = db.execute(
            select(AuditEntry).where(AuditEntry.target_id == offered_row.id)
        ).all()
    assert overrides_on_v2 == []  # the precondition: no override on the offered row
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True, marks


def _mail_on_v1_before_the_base(w: World) -> uuid.UUID:
    """MAIL on v1 from a day before the base, the model's provisional "not
    security" call (in scope until a consultant confirms it)."""
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        db.add(
            CapabilityItem(
                capability_list_id=_v1_id(w),
                name=MAIL,
                security_related=False,
                created_at=base_at - timedelta(days=1),
            )
        )
        db.commit()
    return _item(w, _v1_id(w), MAIL)


def _confirm(w: World, item_id: uuid.UUID) -> None:
    """The real confirm route: takes a negative row out of scope."""
    r = w.c.post(
        f"/tech-debt/capability-items/{item_id}/security-classification/confirm",
        headers=w.h,
    )
    assert r.status_code == 200, r.text


def _mail_confirmed_out_before_the_base(w: World) -> None:
    """MAIL confirmed NOT security through the confirm route, its sign-off
    then placed an hour before the base: out of scope at the base. The
    sign-off's audit row is moved by a Core update, which bypasses
    `_block_audit_mutations` (see the module docstring)."""
    item_id = _mail_on_v1_before_the_base(w)
    _confirm(w, item_id)
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        moved = db.execute(
            update(AuditEntry)
            .where(
                AuditEntry.target_id == item_id,
                AuditEntry.action == "capability_item.security_classification_confirmed",
            )
            .values(at=base_at - timedelta(hours=1))
        ).rowcount
        assert moved == 1, moved
        db.commit()


def test_a_row_in_scope_at_the_base_and_confirmed_out_since_is_not_added(
    app_parts,  # noqa: F811
) -> None:
    """The drafts-branch basis reads a row as it was AT THE BASE. MAIL was a
    provisional negative on v1 (in scope, offered to the base); after the
    base a consultant confirms it out of scope, then v2 is re-extracted with
    MAIL in scope and approved. The base was offered MAIL: not added."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _confirm(w, _mail_on_v1_before_the_base(w))  # after the base
    _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_the_first_override_decides_not_the_latest(app_parts) -> None:  # noqa: F811
    """MAIL was confirmed out, then overridden back in, both before the base:
    in scope at the base. Overriding it AGAIN after the base (re-picking its
    functions) changes nothing about the base. Re-extracted into v2, MAIL is
    not added. Judged on the LATEST override it would read as out of scope
    at the base, and so as added."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _mail_confirmed_out_before_the_base(w)
    item_id = _item(w, _v1_id(w), MAIL)
    _override(w, item_id)
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        moved = db.execute(
            update(AuditEntry)
            .where(
                AuditEntry.target_id == item_id,
                AuditEntry.action == "capability_item.security_classification_overridden",
            )
            .values(at=base_at - timedelta(minutes=30))
        ).rowcount
        assert moved == 1, moved
        db.commit()
    _override(w, item_id)  # again, after the base
    _re_extracted_v2(w, [EDR, SIEM, SOAR, MAIL])
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 0, body["tools_added_since_base"]


def test_a_row_confirmed_out_with_no_confirmation_on_record_reads_null(
    app_parts,  # noqa: F811
) -> None:
    """A RATCHET, not a live case: the confirm route sets the flag and writes
    its audit row together, and no other writer sets the flag, so the state
    is built here by hand. MAIL, on the draft in force at the base, is
    confirmed out of scope NOW with no confirmation on record, so its scope
    at the base cannot be placed: null, never a guess."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    item_id = _mail_on_v1_before_the_base(w)
    with w.sessions() as db:
        db.get(CapabilityItem, item_id).security_class_confirmed = True
        db.commit()
        trail = db.execute(select(AuditEntry).where(AuditEntry.target_id == item_id)).all()
    assert trail == []  # the precondition: no confirmation on record
    body = _what_if(w, {w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert body["run_status"] == "completed", body["run_status"]
    assert body["after"] is not None
    assert body["tools_added_since_base"] is None, body["tools_added_since_base"]


def test_a_not_in_use_row_removed_before_the_base_and_overridden_since_is_added(
    app_parts,  # noqa: F811
) -> None:
    """#845's variant of the confirm route: MAIL, a security tool the
    extraction marked NOT IN USE, is confirmed out of ATT&CK scope a day
    before the base (the route records it as removed from ATT&CK scope), so
    it was offered to nobody. Overridden into scope after the base, it is new
    to the AI."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        base_at = db.get(AttackAssessment, uuid.UUID(w.assessment_id)).approved_at
        db.add(
            CapabilityItem(
                capability_list_id=_v1_id(w),
                name=MAIL,
                security_related=False,
                notes="Security tool not in use: licensed, never deployed.",
                created_at=base_at - timedelta(days=2),
            )
        )
        db.commit()
    item_id = _item(w, _v1_id(w), MAIL)
    _confirm(w, item_id)
    with w.sessions() as db:
        # Core update: bypasses `_block_audit_mutations` (module docstring).
        moved = db.execute(
            update(AuditEntry)
            .where(
                AuditEntry.target_id == item_id,
                AuditEntry.action == "capability_item.removed_from_attack_scope",
            )
            .values(at=base_at - timedelta(days=1))
        ).rowcount
        assert moved == 1, moved  # the route recorded the not-in-use removal
        db.commit()
    _override(w, item_id)  # after the base
    body = _what_if(w, {w.cc: [_flags(w.cc, MAIL, d=True)]})
    assert body["tools_added_since_base"] == 1, body["tools_added_since_base"]
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True, marks
