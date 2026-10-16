"""Z4: the gap list shows the priority with its working, so the API sends the
pillar weight the engine multiplied by (`GapItem.pillar_weight`).

`pillar_weight()` is a refactor of the engine's own lookup: `_row_for` calls
it, and no client number may move. The weights below are the table as it
stands in `app/zt/scoring.py`'s comment and review record (#838), written out
here as literals so a change to the table or to the arithmetic is caught, not
agreed with.
"""

from __future__ import annotations

import pytest

from app.zt.maturity import ZtFrameworkCode
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

#: The pillar weights, written out (not read from the module under test).
WEIGHTS = {
    "ID": 1.20,
    "DT": 1.15,
    "DV": 1.10,
    "NW": 1.05,
    "AW": 1.10,
    "USR": 1.20,
    "DAT": 1.15,
    "DEV": 1.10,
    "NET": 1.05,
    "APP": 1.10,
    "VIS": 1.00,
    "AUT": 1.00,
}


@pytest.mark.parametrize("framework", list(ZtFrameworkCode))
def test_every_pillars_priority_is_unchanged_and_names_its_weight(framework) -> None:
    """Every capability at stage 1, targeted at the top stage: every pillar
    yields gaps, and each priority is `round(gap * weight, 2)` with the
    written-out weight, exactly as before the refactor."""
    from app.zt.catalog import capabilities
    from app.zt.maturity import level_count
    from app.zt.scoring import analyze_gaps, pillar_weight

    codes = [c.code for c in capabilities(framework)]
    top = level_count(framework)
    analysis = analyze_gaps(framework, dict.fromkeys(codes, 1), target_stage=top, top_n=10_000)

    seen = {g.pillar_code for g in analysis.gaps}
    expected_pillars = {c.pillar_code for c in capabilities(framework)}
    assert seen == expected_pillars, sorted(expected_pillars - seen)
    for g in analysis.gaps:
        assert g.priority_score == round(g.gap_size * WEIGHTS[g.pillar_code], 2), g
        assert pillar_weight(g.pillar_code) == WEIGHTS[g.pillar_code], g.pillar_code


def test_an_unknown_pillar_has_no_weight() -> None:
    """A direct index, as before (#838): never a silent 1.0."""
    from app.zt.scoring import pillar_weight

    with pytest.raises(KeyError):
        pillar_weight("NOPE")


def test_the_gap_endpoint_sends_the_weight_it_multiplied_by(app_client) -> None:  # noqa: F811
    """Through the surface the panel reads: each gap carries the weight, and
    the priority is that weight times the gap."""
    c, _ = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    answers = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()["answers"]
    for ans in answers[:3]:
        r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
        assert r.status_code == 200, r.text

    body = c.get(f"/zt/services/{svc_id}/gap-analysis", headers=h).json()

    assert body["gaps"], body
    for g in body["gaps"]:
        assert g["pillar_weight"] == WEIGHTS[g["pillar_code"]], g
        assert g["priority_score"] == round(g["gap_size"] * g["pillar_weight"], 2), g
