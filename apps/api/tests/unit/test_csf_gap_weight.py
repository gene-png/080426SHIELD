"""W6 (Gene, #736 6205956728): the gap list shows the priority with its
working, `Priority {p}: {g} tiers below target × {w} ({Function} weighting)`,
so the gap-analysis route carries each gap's function weight, as stored.

Through the route the list reads. The weights expected here are typed from the
function weighting the gap list's description states (operational functions
PR/DE/RS/RC above governance GV/ID) and the stored table's values, never read
from `FUNCTION_WEIGHTS`: GV 1.0, ID 1.0, PR 1.15, DE 1.2, RS 1.2, RC 1.15.
And the working must be the priority: weight × gap size is the stored
`priority_score`.
"""

from __future__ import annotations

import pytest

from tests.unit.test_csf_gap import _register, _seed_assessment, app_client  # noqa: F401

pytestmark = pytest.mark.unit

WEIGHTS = {"GV": 1.0, "ID": 1.0, "PR": 1.15, "DE": 1.2, "RS": 1.2, "RC": 1.15}


def test_every_gap_carries_its_function_weight_and_the_working_is_the_priority(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id, answers = _seed_assessment(c, bearer)
    # One tier-1 answer in each function: a gap of 2 to the default target 3.
    first_by_function: dict[str, dict] = {}
    for ans in answers:
        first_by_function.setdefault(ans["subcategory_code"][:2], ans)
    assert set(first_by_function) == set(WEIGHTS), sorted(first_by_function)
    for ans in first_by_function.values():
        r = c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 1})
        assert r.status_code == 200, r.text

    body = c.get(f"/csf/services/{svc_id}/gap-analysis", headers=h).json()
    gaps = {g["code"][:2]: g for g in body["gaps"]}
    assert set(gaps) == set(WEIGHTS), sorted(gaps)  # positive first: six gaps
    for fn, g in gaps.items():
        assert g["weight"] == WEIGHTS[fn], (fn, g)
        assert g["gap_size"] == 2, g
        assert g["priority_score"] == pytest.approx(g["gap_size"] * g["weight"]), g
