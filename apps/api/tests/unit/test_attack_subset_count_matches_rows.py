"""#1010: the C1 count ("{n} technique rows credit a tool that is not in the
client's security tool list, so their status may count a tool the client does
not use") counts rows the surface does not show as having a status.

The drifting row is reachable: `PATCH /attack/coverage/{id}` sets a row's tool
lists without a status (the existing #851 tests do exactly that), and a row
with tools and no status is UNSCORED. It has no status that could count a tool,
yet the count includes it, while the client dashboard's matrix does not draw it
at all (`attack_dashboard_content` skips `status is None`).

World: #851's (`test_attack_subset_drift._world`). Row ONE is Covered and
credits EDR and LEGACY; row TWO has no status and credits LEGACY. LEGACY then
leaves the security tool list (`confirm_not_security`), so both rows credit a
tool outside it, and exactly one of them has a status.

Expected values are the approved C1 copy written out (#736 6090360421), and the
rows each surface itself shows, never a count from the module under test.
"""

from __future__ import annotations

import pytest

from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_subset_after_release import (
    _approve_finalize,
    _cover,
    _dashboard,
    _release,
    _uncleared,
)
from tests.unit.test_attack_subset_drift import (
    EDR,
    LEGACY,
    _codes,
    _format_text,
    _with_storage,
    _world,
)

pytestmark = pytest.mark.unit

C1_ONE = (
    "1 technique row credits a tool that is not in the client's security tool list, "
    "so its status may count a tool the client does not use."
)
C1_TWO = (
    "2 technique rows credit a tool that is not in the client's security tool list, "
    "so their status may count a tool the client does not use."
)
FORMATS = ["pdf", "docx", "xlsx", "summary"]


def _drifting_world(app_parts, tmp_path):  # noqa: F811
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    one, two = _codes(w)[:2]
    _cover(w, one, [EDR, LEGACY])
    r = w.patch(two, {"detection_tools": [LEGACY]})
    assert r.status_code == 200, r.text
    (row_two,) = [t for t in w.get()["coverage"] if t["technique_code"] == two]
    assert (row_two["status"], row_two["detection_tools"]) == (
        None,
        [LEGACY],
    ), "setup: row two credits LEGACY and has no status"
    return w, one, two


def test_the_dashboard_counts_only_the_rows_it_shows(app_parts, tmp_path) -> None:  # noqa: F811
    w, one, two = _drifting_world(app_parts, tmp_path)
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)
    body = _dashboard(w)
    shown = {t["code"] for t in body["techniques"]}
    # Positive first: the matrix shows row one and the check found LEGACY.
    assert one in shown and two not in shown, sorted(shown)
    assert body["tool_outside_subset"] == [LEGACY], body.get("tool_outside_subset")
    crediting = [
        t
        for t in body["techniques"]
        if LEGACY in (*t["detection_tools"], *t["prevention_tools"], *t["response_tools"])
    ]
    assert len(crediting) == 1, crediting
    assert body["subset_notes"] == [C1_ONE], body.get("subset_notes")


@pytest.mark.parametrize("fmt", FORMATS)
def test_each_format_counts_only_rows_with_a_status(
    app_parts, tmp_path, fmt: str  # noqa: F811
) -> None:
    """The sentence is about rows whose STATUS may count a tool. Row two has
    none: it is printed as Unscored, and is not one of them."""
    w, one, two = _drifting_world(app_parts, tmp_path)
    assert w.approve().status_code == 200
    w.confirm_not_security(LEGACY)
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    text = _format_text(w, fin.json(), fmt)
    assert C1_ONE in text, text[:3000]
    assert C1_TWO not in text, text[:3000]


def _status_world(
    app_parts,  # noqa: F811
    tmp_path,
    status_body: dict,
    *,
    stored_rules: bool,
    tools: tuple[str, ...] = (EDR, LEGACY),
    uncleared: bool = False,
):
    """Row one carries `status_body` and credits `tools`; row two is unscored
    and credits LEGACY. `stored_rules` gives an assessment approved before R3
    (`status_rules` 1, migration 0059's backfill), whose stored status is what
    every surface reads. `uncleared` leaves every citation of LEGACY on row one
    uncleared (#102), so under R3 a row whose only tool is LEGACY computes to
    Gap and keeps its tools: a Gap stored and computed, as Run AI's citation
    merge leaves one that nobody has confirmed."""
    import uuid as _uuid

    from app.models.attack_assessment import AttackAssessment

    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    one, two = _codes(w)[:2]
    r = w.patch(one, {**status_body, "detection_tools": list(tools)})
    assert r.status_code == 200, r.text
    r = w.patch(two, {"detection_tools": [LEGACY]})
    assert r.status_code == 200, r.text
    if uncleared:
        _uncleared(w, one, LEGACY)
    assert w.approve().status_code == 200
    if stored_rules:
        # After approve, which stamps the rule set: migration 0059's backfill
        # shape for an assessment approved before R3.
        with w.sessions() as db:
            db.get(AttackAssessment, _uuid.UUID(w.assessment_id)).status_rules = 1
            db.commit()
    w.confirm_not_security(LEGACY)
    fin = w.c.post(f"/attack/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code in (200, 201), fin.text
    (row_one,) = [t for t in w.get()["coverage"] if t["technique_code"] == one]
    return w, fin.json(), row_one


@pytest.mark.parametrize(
    ("status_body", "stored_rules", "tools", "uncleared"),
    [
        (
            {"status": "not_applicable", "reason_code": "platform_absent"},
            False,
            (EDR, LEGACY),
            False,
        ),
        ({"status": "gap"}, True, (EDR, LEGACY), False),
        ({"status": "gap"}, False, (LEGACY,), True),
    ],
    ids=["not_applicable", "gap_before_r3", "gap_computed_r3"],
)
def test_a_judged_row_that_is_not_coverage_still_counts(
    app_parts, tmp_path, status_body: dict, stored_rules: bool, tools, uncleared: bool  # noqa: F811
) -> None:
    """Gap and N/A are judgements (#889): their rows still count. Only the
    unscored row is out."""
    w, fin, row_one = _status_world(
        app_parts,
        tmp_path,
        status_body,
        stored_rules=stored_rules,
        tools=tools,
        uncleared=uncleared,
    )
    assert row_one["status"] == status_body["status"], "setup: row one keeps its status"
    # And it is the status every surface reads, computed or stored.
    assert (row_one["computed_status"] or row_one["status"]) == status_body["status"], row_one
    if uncleared:
        # Observed, not assumed: R3 computed this Gap, from the uncleared
        # citation, so the case cannot quietly become `gap_before_r3`.
        assert row_one["computed_status"] == "gap", row_one
        assert row_one["capabilities"]["detect"] == "awaiting_review", row_one
    text = _format_text(w, fin, "summary")
    assert C1_ONE in text, text
    assert C1_TWO not in text, text
