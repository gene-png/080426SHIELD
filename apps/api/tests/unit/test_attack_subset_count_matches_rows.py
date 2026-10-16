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
