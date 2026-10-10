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


def test_t6_the_home_card_says_its_total_counts_a_tool_outside_the_list(
    app_parts, tmp_path  # noqa: F811
) -> None:
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    before = _value_summary(w)
    assert before["attack_uncovered_count"] is not None, before  # positive first
    assert before["attack_counts_outside_subset"] is False, before
    w.confirm_not_security(LEGACY)
    after = _value_summary(w)
    assert after["attack_counts_outside_subset"] is True, after
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
    assert body["attack_counts_outside_subset"] is None, body


# --- T7: the dashboard marks only rows the client can see -----------------------------


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
