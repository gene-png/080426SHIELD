"""#889 PR 1: after an ATT&CK assessment is approved, a tool can leave the
client's security tool list. The client dashboard, the exports and the client
home card disclose a row still crediting it. Disclosure only: no number moves.

Plan: track4, #736 comment 6089903057. Ruling: the advisor, #736 comment
6090360421 (the design, copy C1 to C7 verbatim, Q1 to Q7 as recommended).

Sources, as approved: the dashboard and the home card read the CURRENT subset
(the existing `subset_state`); the exports record it as of finalize, in the
bytes.

Every expected string below is the approved copy written out, never imported
from the module that renders it.

The world is #851's (`test_attack_subset_drift._world`): a Tech Debt list whose
"Legacy AV" carries the model's provisional "not security" call. Confirming that
call (`confirm_not_security`) takes the tool out of the subset AFTER approve,
which is the drift this issue is about.
"""

from __future__ import annotations

import io
import uuid

import pytest

from app.models.attack_assessment import AttackCoverage
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_subset_drift import (
    EDR,
    LEGACY,
    World,
    _codes,
    _format_text,
    _no_list_world,
    _with_storage,
    _world,
)

pytestmark = pytest.mark.unit

# C1, the approved singular and plural (#736 6089903057, approved 6090360421).
C1_ONE = (
    "1 technique row credits a tool that is not in the client's security tool list, "
    "so its status may count a tool the client does not use."
)
C1_TWO = (
    "2 technique rows credit a tool that is not in the client's security tool list, "
    "so their status may count a tool the client does not use."
)
# C3, the per-tool mark.
C3 = " (not in the security tool list)"
# C4, the XLSX legend.
C4_LABEL = "Tools marked (not in the security tool list)"
C4_TEXT = (
    "Not in the client's security tool list when this report was finalized, so "
    "coverage may count a tool the client does not use."
)
# C5: #851's approved "not checked" sentence (#736 6040458893), verbatim.
C5 = (
    "The tools cited here were not checked against a security tool list, because "
    "the client has none."
)

FORMATS = ["pdf", "docx", "xlsx", "summary"]


def _cover(w: World, code: str, tools: list[str]) -> None:
    """A Covered row naming `tools` in Detect, Prevent and Respond, so its
    status survives #554 R3's computation and the dashboard shows the row."""
    r = w.patch(
        code,
        {
            "status": "covered",
            "detection_tools": tools,
            "prevention_tools": tools,
            "response_tools": tools,
        },
    )
    assert r.status_code == 200, r.text


def _approve_finalize(w: World) -> dict:
    assert w.approve().status_code == 200
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    return fin.json()


def _release(w: World, fin: dict) -> None:
    r = w.c.post(f"/attack/deliverables/{fin['id']}/release", headers=w.h)
    assert r.status_code == 200, r.text


def _dashboard(w: World) -> dict:
    r = w.c.get(f"/clients/{w.cid}/attack/{w.svc_id}/dashboard", headers=w.h)
    assert r.status_code == 200, r.text
    return r.json()


def _download(w: World, artifact_id: str) -> bytes:
    r = w.c.get(f"/artifacts/{artifact_id}/download", headers=w.h)
    assert r.status_code == 200, r.text
    return r.content


def _xlsx_tool_cells(raw: bytes) -> set[str]:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(raw))["Coverage"]
    col = [c.value for c in ws[1]].index("Detection tools") + 1
    return {
        str(ws.cell(row=r, column=col).value)
        for r in range(2, ws.max_row + 1)
        if ws.cell(row=r, column=col).value
    }


def _xlsx_legend(raw: bytes) -> dict:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(raw))["Heatmap Summary"]
    return {r[0].value: r[1].value for r in ws.iter_rows(max_row=40) if r and r[0].value}


# --- T1: the client dashboard discloses a tool that left the list after release ---------


def test_t1_the_dashboard_discloses_a_tool_that_left_the_list_after_release(
    app_parts, tmp_path  # noqa: F811
) -> None:
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    one, two = _codes(w)[:2]
    _cover(w, one, [EDR, LEGACY])
    _cover(w, two, [EDR])
    _release(w, _approve_finalize(w))

    before = _dashboard(w)
    # Positive first: the check ran and found nothing, so the keys are present
    # and empty (the second state), not absent.
    assert before["tool_outside_subset"] == [], before.get("tool_outside_subset")
    assert before["subset_notes"] == [], before.get("subset_notes")

    w.confirm_not_security(LEGACY)
    after = _dashboard(w)
    assert after["tool_outside_subset"] == [LEGACY], after.get("tool_outside_subset")
    assert after["subset_notes"] == [C1_ONE], after.get("subset_notes")
    # Disclosure only: the number the client reads does not move.
    assert after["rollup"] == before["rollup"]


# --- T2: "not checked" is the third state, said on the dashboard ----------------------


def test_t2_the_dashboard_says_not_checked_when_the_client_has_no_list(
    app_parts, tmp_path  # noqa: F811
) -> None:
    _with_storage(app_parts, tmp_path)
    w = _no_list_world(app_parts)
    _cover(w, _codes(w)[0], ["Tool A"])
    _release(w, _approve_finalize(w))
    body = _dashboard(w)
    assert "techniques" in body, sorted(body)  # positive first: it rendered
    assert body["subset_notes"] == [C5], body.get("subset_notes")
    # Nothing could be looked at, so there is no list of tools at all: absent,
    # never an empty list that would read as "checked, none found".
    assert "tool_outside_subset" not in body, sorted(body)


# --- T3: each export states the outside rows, as of finalize --------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_t3_each_format_states_rows_outside_the_list_at_finalize(
    app_parts, tmp_path, fmt: str  # noqa: F811
) -> None:
    """Approve accepts the row (the tool is still in the subset); the tool
    leaves before finalize, which is what a re-finalize after drift is."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    text = _format_text(w, fin.json(), fmt)
    assert C1_ONE in text, text[:3000]
    assert C5 not in text, text[:3000]


@pytest.mark.parametrize("fmt", FORMATS)
def test_t3_the_document_keeps_the_list_as_it_stood_at_finalize(
    app_parts, tmp_path, fmt: str  # noqa: F811
) -> None:
    """Finalized while the tool was still listed: the stored document says
    nothing, and the dashboard (read live) is where the later change shows."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    fin = _approve_finalize(w)
    w.confirm_not_security(LEGACY)
    text = _format_text(w, fin, fmt)
    assert ("Coverage:" if fmt == "summary" else "ATT&CK") in text, text[:3000]
    assert "not in the client's security tool list" not in text, text[:3000]


# --- T4: the per-tool mark, stacked last, and its legend ------------------------------


def test_t4_the_xlsx_marks_the_tool_after_the_unconfirmed_and_retirement_marks(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """ "Homegrown Script" is on no list: outside the subset, and (with no
    approved plan) carrying no retirement mark. "Legacy AV" leaves after
    approve and carries an inferred, uncleared citation, so its mark stacks
    after " (unconfirmed)"."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    code = _codes(w)[0]
    _cover(w, code, [EDR, LEGACY])
    with w.sessions() as db:
        row = db.get(AttackCoverage, uuid.UUID(w.rows[code]))
        row.unconfirmed_citations = [
            {
                "tool": LEGACY,
                "cited": "Legacy",
                "reason": "substring",
                "field": "detection_tools",
                "cleared_at": None,
            }
        ]
        db.commit()
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    raw = _download(w, fin.json()["xlsx_artifact_id"])
    cells = _xlsx_tool_cells(raw)
    assert f"{EDR}; {LEGACY} (unconfirmed){C3}" in cells, cells
    assert _xlsx_legend(raw).get(C4_LABEL) == C4_TEXT


def test_t4_the_mark_stacks_after_the_retirement_mark() -> None:
    """The order on one tool carrying all three marks. A pure render over a
    plan that cuts "Splunk": the route world above has no approved plan."""
    from app.attack.exporters import _tools
    from app.attack.retirement import Retirement, RetirementIndex

    plan = RetirementIndex(
        has_plan=True,
        by_key={"splunk": Retirement.PLANNED, "okta": Retirement.NOT_RETIRING},
    )
    text = _tools(["Splunk", "Okta"], frozenset({"Splunk"}), plan, frozenset({"Splunk"}))
    assert text == f"Splunk (unconfirmed) (planned retirement){C3}; Okta", text


def test_t4_no_legend_row_without_a_marked_tool(app_parts, tmp_path) -> None:  # noqa: F811
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR])
    fin = _approve_finalize(w)
    raw = _download(w, fin["xlsx_artifact_id"])
    legend = _xlsx_legend(raw)
    assert "Tools marked (unconfirmed)" in legend, legend  # positive first
    assert C4_LABEL not in legend, legend


# --- T5: Q7, one subset parameter: the flag and the list cannot disagree --------------


def test_t5_an_unchecked_subset_cannot_carry_outside_tools() -> None:
    from app.attack.subset_drift import OutsideCitation, SubsetCheck

    hit = OutsideCitation(technique_code="T1", field="detection_tools", tool="X", locked=False)
    assert SubsetCheck(checked=True, outside=(hit,)).outside == (hit,)  # positive first
    with pytest.raises(ValueError, match="not checked"):
        SubsetCheck(checked=False, outside=(hit,))


# --- T6: the client home card (C7, Q3) ------------------------------------------------


def _value_summary(w: World) -> dict:
    r = w.c.get(f"/clients/{w.cid}/value-summary", headers=w.h)
    assert r.status_code == 200, r.text
    return r.json()


def test_t6_the_home_card_flags_a_covered_technique_relying_on_a_tool_outside_the_list(
    app_parts, tmp_path  # noqa: F811
) -> None:
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    before = _value_summary(w)
    assert before["attack_uncovered_count"] is not None, before  # positive first
    assert before["attack_covered_relies_on_outside_tool"] is False, before
    w.confirm_not_security(LEGACY)
    after = _value_summary(w)
    assert after["attack_covered_relies_on_outside_tool"] is True, after
    # Disclosure only: the total does not move.
    assert after["attack_uncovered_count"] == before["attack_uncovered_count"]


def test_t6_the_home_card_flag_is_null_with_no_list(app_parts, tmp_path) -> None:  # noqa: F811
    """Not checked: the card has nothing to say, and says nothing, rather than
    reading False ("checked, none found")."""
    _with_storage(app_parts, tmp_path)
    w = _no_list_world(app_parts)
    _cover(w, _codes(w)[0], ["Tool A"])
    _release(w, _approve_finalize(w))
    body = _value_summary(w)
    assert body["attack_uncovered_count"] is not None, body  # positive first
    assert body["attack_covered_relies_on_outside_tool"] is None, body


# --- T7: one tool on two rows is one name and two rows ---------------------------------


def test_t7_the_dashboard_lists_each_outside_tool_once(app_parts, tmp_path) -> None:  # noqa: F811
    """The same tool on two rows is one name in `tool_outside_subset` (the
    per-tool mark) and two rows in the sentence (which counts rows), and a
    tool still on the list is never named."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    one, two = _codes(w)[:2]
    _cover(w, one, [EDR, LEGACY])
    _cover(w, two, [LEGACY])
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)
    body = _dashboard(w)
    assert body["tool_outside_subset"] == [LEGACY], body.get("tool_outside_subset")
    assert body["subset_notes"] == [C1_TWO], body.get("subset_notes")


# --- plan T2: the APPROVED list answers from its snapshot (D-053/D-064) -----------------


def test_the_dashboard_reads_an_approved_lists_snapshot_until_it_is_approved_again(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """Approve the Tech Debt list BEFORE the ATT&CK approve. Confirming the
    sign-off afterwards changes the live row but not the approved snapshot,
    which IS the membership: nothing is listed. Approving the list again
    refreshes the snapshot, and the tool is listed."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    w.approve_list()
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)
    pinned = _dashboard(w)
    assert pinned["tool_outside_subset"] == [], pinned.get("tool_outside_subset")
    assert pinned["subset_notes"] == [], pinned.get("subset_notes")
    w.approve_list()
    refreshed = _dashboard(w)
    assert refreshed["tool_outside_subset"] == [LEGACY], refreshed.get("tool_outside_subset")
    assert refreshed["subset_notes"] == [C1_ONE], refreshed.get("subset_notes")


# --- plan T4: a computed parent's own tools are not its evidence (D-094) ----------------


def test_a_computed_parents_own_tools_are_neither_marked_nor_counted(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """Under the new rules a computed parent's own stored tools are not
    delivered, so the dashboard neither names them in `tool_outside_subset`
    nor counts the parent row in C1. Its child is checked like any row.

    The parent's own "Shadow Scanner" was never on the list, so it would be
    flagged if the parent were read; the child's "Legacy AV" leaves the list
    after release."""
    from tests.unit.test_attack_subset_drift import _legacy_parent_tools, _parent_with_child

    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _parent, parent_id, child, child_id = _parent_with_child(w)
    _legacy_parent_tools(w, parent_id, ["Shadow Scanner"])
    w.rows[child] = child_id
    _cover(w, child, [LEGACY])
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)
    body = _dashboard(w)
    assert body.get("parents_computed") is True, sorted(body)  # the new rules apply
    # The parent row is in the context C1 counts over even where the matrix
    # hides it (no status of its own until its children are scored).
    assert child in {t["code"] for t in body["techniques"]}, child  # positive first
    assert body["tool_outside_subset"] == [LEGACY], body.get("tool_outside_subset")
    assert body["subset_notes"] == [C1_ONE], body.get("subset_notes")


# --- plan T7: the delivered bytes keep the list as it stood at finalize ----------------


def test_the_finalized_artifacts_are_byte_identical_after_the_drift(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """The ratchet: the v1 PDF, DOCX and XLSX downloaded after the tool leaves
    the list (and after the live dashboard has disclosed it) are the bytes
    downloaded before."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    fin = _approve_finalize(w)
    _release(w, fin)
    ids = [fin[f"{fmt}_artifact_id"] for fmt in ("pdf", "docx", "xlsx")]
    before = [_download(w, i) for i in ids]
    w.confirm_not_security(LEGACY)
    assert _dashboard(w)["subset_notes"] == [C1_ONE]  # positive first: the drift is live
    assert [_download(w, i) for i in ids] == before


# --- review F2: a newer list version supersedes an older approved one -------------------


def _upload_v2_without(w: World, dropped: str) -> str:
    """A second version of the client's Tech Debt list, without `dropped`: the
    world, written directly, as `test_attack_subset_drift._world` writes v1."""
    names = [n for n in (EDR, "Acme Portal") if n != dropped]
    return _upload_v2(w, names)


def _upload_v2(w: World, names: list[str]) -> str:
    """A DRAFT second version of the client's Tech Debt list holding `names`."""
    from app.models.capability import (
        CapabilityDisposition,
        CapabilityItem,
        CapabilityList,
        CapabilityListStatus,
    )

    with w.sessions() as db:
        v1 = db.get(CapabilityList, uuid.UUID(w.list_id))
        v2 = CapabilityList(service_id=v1.service_id, version=2, status=CapabilityListStatus.DRAFT)
        db.add(v2)
        db.flush()
        for name in names:
            db.add(
                CapabilityItem(
                    capability_list_id=v2.id,
                    name=name,
                    security_related=True,
                    disposition=CapabilityDisposition.KEEP,
                )
            )
        db.commit()
        return str(v2.id)


def test_a_tool_dropped_from_an_approved_v2_is_flagged_though_v1_held_it(
    app_parts, tmp_path  # noqa: F811
) -> None:
    """v1 is approved holding "Legacy AV"; ATT&CK is released; v2 is uploaded
    without it and approved. Per Tech Debt service only the latest version
    counts toward the security tool list (older versions do not vote), so the
    dashboard and the home card flag it. v1's snapshot must not keep it in."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    w.approve_list()
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    before = _dashboard(w)
    assert before["tool_outside_subset"] == [], before.get("tool_outside_subset")  # positive first
    v2 = _upload_v2_without(w, LEGACY)
    r = w.c.post(f"/tech-debt/capability-lists/{v2}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    after = _dashboard(w)
    assert after["tool_outside_subset"] == [LEGACY], after.get("tool_outside_subset")
    assert after["subset_notes"] == [C1_ONE], after.get("subset_notes")
    assert _value_summary(w)["attack_covered_relies_on_outside_tool"] is True


def test_a_draft_v2_is_the_current_list(app_parts, tmp_path) -> None:  # noqa: F811
    """R2 (advisor, #736 6091824874): a DRAFT latest version counts as the
    current list. v2 is uploaded without "Legacy AV" and NOT approved; the
    tool is flagged on the dashboard and the home card."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    w.approve_list()
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    assert _dashboard(w)["tool_outside_subset"] == []  # positive first: v1 holds it
    _upload_v2_without(w, LEGACY)  # a DRAFT, never approved
    body = _dashboard(w)
    assert body["tool_outside_subset"] == [LEGACY], body.get("tool_outside_subset")
    assert body["subset_notes"] == [C1_ONE], body.get("subset_notes")
    assert _value_summary(w)["attack_covered_relies_on_outside_tool"] is True


@pytest.mark.parametrize("v2_holds_it", [True, False])
def test_approve_refuses_a_tool_the_latest_approved_version_dropped(
    app_parts, v2_holds_it: bool  # noqa: F811
) -> None:
    """#851's approve refusal reads the same check (`subset_state`), so after
    F2 it judges against each service's LATEST version: v1 APPROVED with the
    tool, v2 APPROVED without it, and an ATT&CK row citing it is refused. The
    same flow with v2 still holding it approves (the positive control)."""
    w = _world(app_parts)
    w.approve_list()
    names = [EDR, LEGACY] if v2_holds_it else [EDR]
    v2 = _upload_v2(w, names)
    r = w.c.post(f"/tech-debt/capability-lists/{v2}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    code = _codes(w)[0]
    _cover(w, code, [EDR, LEGACY])
    r = w.approve()
    if v2_holds_it:
        assert r.status_code == 200, r.text
        return
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["reason"] == "attack_not_release_ready", err
    assert {(o["technique_code"], o["tool"]) for o in err["cites_outside_subset"]} == {
        (code, LEGACY)
    }, err


# --- round 2, F1: the home card flags only rows that credit coverage --------------------


def _uncleared(w: World, code: str, tool: str) -> None:
    """Every citation of `tool` on the row is inferred and uncleared (#102), so
    under R3 Detect / Prevent / Respond are all awaiting review and the row
    computes to Gap."""
    from app.attack.pending import TOOL_FIELDS

    with w.sessions() as db:
        row = db.get(AttackCoverage, uuid.UUID(w.rows[code]))
        row.unconfirmed_citations = [
            {"tool": tool, "cited": tool, "reason": "substring", "field": f, "cleared_at": None}
            for f in TOOL_FIELDS
        ]
        db.commit()


@pytest.mark.parametrize(
    ("case", "stored", "effective", "flag"),
    [
        # The positive control: a cleared citation, Covered stored and computed.
        ("covered", "covered", "covered", True),
        # Gap stored and computed: already in the uncovered total.
        ("stored_gap", "gap", "gap", False),
        # The usual production path (round-3 review): Run AI suggested
        # "covered" with an uncleared citation, R3 computes Gap, and the
        # consultant accepts it through the computed-status review, which
        # writes only `reviewed_status`. STORED covered, EFFECTIVE gap.
        ("reviewed_gap", "covered", "gap", False),
    ],
)
def test_the_home_card_flag_needs_a_row_that_credits_coverage(
    app_parts, tmp_path, case: str, stored: str, effective: str, flag: bool  # noqa: F811
) -> None:
    """R1's note says techniques COUNTED AS COVERED rely on the tool, so the
    flag reads the EFFECTIVE status. A row whose only tool is an uncleared
    citation computes to Gap and is already in the uncovered total: the tool
    leaving the list must not raise the note, whatever status is stored."""
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    code = _codes(w)[0]
    _cover(w, code, [LEGACY])
    if case == "stored_gap":
        # The stored status agrees with the computed one, so release needs no
        # computed-status review (`attack_computed_status_unreviewed`).
        assert w.patch(code, {"status": "gap"}).status_code == 200
    if case != "covered":
        _uncleared(w, code, LEGACY)
    assert w.approve().status_code == 200
    if case == "reviewed_gap":
        r = w.c.post(
            f"/attack/assessments/{w.assessment_id}/computed-status-review",
            headers=w.h,
            json={"reviews": [{"code": code, "computed_status": "gap"}]},
        )
        assert r.status_code == 200, r.text
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    _release(w, fin.json())
    w.confirm_not_security(LEGACY)
    dash = _dashboard(w)
    # The world is what it says, positive first: the effective status the
    # client reads, and the stored status underneath it.
    assert {t["code"]: t["status"] for t in dash["techniques"]}[code] == effective
    with w.sessions() as db:
        assert db.get(AttackCoverage, uuid.UUID(w.rows[code])).status == stored
    assert dash["tool_outside_subset"] == [LEGACY]  # the check ran and found it
    body = _value_summary(w)
    assert body["attack_covered_relies_on_outside_tool"] is flag, body


# --- round 2, F2: `_current_list_versions`, one per service, and discards skipped -----


def _second_tech_debt_service(w: World, names: list[str]) -> None:
    """Another Tech Debt service for the same client, its v1 a DRAFT holding
    `names`: the world, written directly."""
    from app.models.capability import (
        CapabilityDisposition,
        CapabilityItem,
        CapabilityList,
        CapabilityListStatus,
    )
    from app.models.service import Service, ServiceKind, ServiceStatus

    with w.sessions() as db:
        opened_by = db.get(Service, uuid.UUID(w.svc_id)).opened_by  # the ATT&CK service
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt B",
            client_id=uuid.UUID(w.cid),
            opened_by=opened_by,
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.DRAFT)
        db.add(cl)
        db.flush()
        for name in names:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    security_related=True,
                    disposition=CapabilityDisposition.KEEP,
                )
            )
        db.commit()


def _outside_tools(w: World) -> list[str]:
    body = w.get()
    assert body["subset_checked"] is True, body["subset_checked"]
    return sorted({o["tool"] for o in body["citations_outside_subset"]})


def test_each_tech_debt_service_has_its_own_latest_version(app_parts) -> None:  # noqa: F811
    """Service A's latest (v2) holds EDR and not Legacy AV; service B's latest
    holds Legacy AV. One latest list PER SERVICE: a row citing both is
    inside the list."""
    w = _world(app_parts)
    _upload_v2_without(w, LEGACY)
    _second_tech_debt_service(w, [LEGACY])
    code = _codes(w)[0]
    r = w.patch(code, {"detection_tools": [EDR, LEGACY]})
    assert r.status_code == 200, r.text
    row = next(c for c in w.get()["coverage"] if c["technique_code"] == code)
    assert row["detection_tools"] == [EDR, LEGACY], row  # positive first
    assert _outside_tools(w) == []


def _discard(w: World, list_id: str) -> None:
    r = w.c.post(f"/tech-debt/capability-lists/{list_id}/discard", headers=w.h)
    assert r.status_code == 200, r.text


def test_a_discarded_v2_falls_back_to_the_approved_v1(app_parts) -> None:  # noqa: F811
    """v1 APPROVED holds Legacy AV; v2 is DISCARDED without it. A discarded
    list does not vote, so v1 is the current list: checked, and not flagged."""
    w = _world(app_parts)
    w.approve_list()
    _discard(w, _upload_v2_without(w, LEGACY))
    code = _codes(w)[0]
    r = w.patch(code, {"detection_tools": [EDR, LEGACY]})
    assert r.status_code == 200, r.text
    row = next(c for c in w.get()["coverage"] if c["technique_code"] == code)
    assert row["detection_tools"] == [EDR, LEGACY], row  # positive first
    assert _outside_tools(w) == []


def test_a_tool_only_on_a_discarded_v2_is_flagged(app_parts) -> None:  # noqa: F811
    """v1 APPROVED does not hold "Shadow Scanner"; v2 is DISCARDED holding it.
    v1 is the current list, so the tool is checked and flagged."""
    w = _world(app_parts)
    w.approve_list()
    _discard(w, _upload_v2(w, [EDR, "Shadow Scanner"]))
    code = _codes(w)[0]
    w.patch(code, {"detection_tools": [EDR, "Shadow Scanner"]})
    assert _outside_tools(w) == ["Shadow Scanner"]


# --- R4 (b): a latest version with no security-scope rows does not vote ----------------
# Ruled option (b) (#736). The API half only: the admin copy is with the advisor.


def _upload_v2_items(w: World, items: list[tuple[str, bool, bool]]) -> str:
    """A DRAFT v2 of the client's Tech Debt list, each item
    (name, security_related, security_class_confirmed)."""
    from app.models.capability import (
        CapabilityDisposition,
        CapabilityItem,
        CapabilityList,
        CapabilityListStatus,
    )

    with w.sessions() as db:
        v1 = db.get(CapabilityList, uuid.UUID(w.list_id))
        v2 = CapabilityList(service_id=v1.service_id, version=2, status=CapabilityListStatus.DRAFT)
        db.add(v2)
        db.flush()
        for name, security, confirmed in items:
            db.add(
                CapabilityItem(
                    capability_list_id=v2.id,
                    name=name,
                    security_related=security,
                    security_class_confirmed=confirmed,
                    disposition=CapabilityDisposition.KEEP,
                )
            )
        db.commit()
        return str(v2.id)


def _subset(w: World):
    """`subset_state` itself, over the assessment's stored rows, for the
    fields no response carries yet (the copy is pending)."""
    from sqlalchemy import select

    from app.routes.attack import subset_state

    with w.sessions() as db:
        rows = (
            db.execute(
                select(AttackCoverage).where(
                    AttackCoverage.assessment_id == uuid.UUID(w.assessment_id)
                )
            )
            .scalars()
            .all()
        )
        return subset_state(db, uuid.UUID(w.cid), rows, parents_computed=True)


@pytest.mark.parametrize(
    "v2_items",
    [
        pytest.param([], id="empty"),
        # Payroll, confirmed not security: out of scope, so v2 holds no
        # security-scope row and counts as empty.
        pytest.param([("Payroll", False, True)], id="only_out_of_scope"),
    ],
)
def test_an_empty_latest_version_falls_back_to_the_previous_one(
    app_parts, v2_items  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.approve_list()
    _upload_v2_items(w, v2_items)
    _fallback_asserts(w, "draft")


def test_an_approved_empty_latest_version_falls_back_too(app_parts) -> None:  # noqa: F811
    """An APPROVED v2 is judged by its snapshot, which holds no row: it does
    not vote either."""
    w = _world(app_parts)
    w.approve_list()
    v2 = _upload_v2_items(w, [])
    r = w.c.post(f"/tech-debt/capability-lists/{v2}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    with w.sessions() as db:
        from app.models.capability import CapabilityList

        assert db.get(CapabilityList, uuid.UUID(v2)).approved_membership == []
    _fallback_asserts(w, "approved")


def _fallback_asserts(w: World, skipped_status: str) -> None:
    code = _codes(w)[0]
    r = w.patch(code, {"detection_tools": [EDR, LEGACY]})
    assert r.status_code == 200, r.text
    assert _outside_tools(w) == []  # v1 is the current list, and holds both
    check = _subset(w)
    assert check.checked is True
    assert check.not_checked_reason is None
    assert [
        (f.service_title, f.skipped_version, f.skipped_status, f.used_version)
        for f in check.fallbacks
    ] == [("Acme Tech Debt", 2, skipped_status, 1)]


def test_with_only_an_empty_list_nothing_is_checked_and_the_reason_is_empty(
    app_parts,  # noqa: F811
) -> None:
    w = _no_list_world(app_parts)
    _second_tech_debt_service(w, [])  # one Tech Debt service, its only list empty
    code = _codes(w)[0]
    r = w.patch(code, {"detection_tools": ["Tool A"]})
    assert r.status_code == 200, r.text
    assert w.get()["subset_checked"] is False  # never "every tool is outside"
    check = _subset(w)
    assert (check.checked, check.not_checked_reason) == (False, "empty")
    assert [(f.skipped_version, f.used_version) for f in check.fallbacks] == [(1, None)]


def test_with_no_list_the_reason_is_no_list(app_parts) -> None:  # noqa: F811
    check = _subset(_no_list_world(app_parts))
    assert (check.checked, check.not_checked_reason) == (False, "no_list")


def test_with_only_discarded_lists_the_reason_is_discarded(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    assert _subset(w).checked is True  # positive first: a live list is checked
    _discard(w, w.list_id)
    check = _subset(w)
    assert (check.checked, check.not_checked_reason) == (False, "discarded")
