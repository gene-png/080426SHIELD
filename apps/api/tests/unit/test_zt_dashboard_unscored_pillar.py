"""#1183, the Zero Trust half: stage 1 is now 0%, so an UNSCORED pillar (null
percentage) must not be told apart from a scored one by a zero.

`approve_assessment` has no completeness check, so a released assessment can
leave a whole pillar unscored. Its percentage is null; it must not be named the
"Largest" gap, which would present it as a pillar scored at the lowest stage.
Expected values are worked out here from the stages typed into the world.
"""

from __future__ import annotations

import pytest

from tests.unit.test_zt_dashboard import app_client  # noqa: F401  (fixture)
from tests.unit.test_zt_dashboard_maturity_pct import _world

pytestmark = pytest.mark.unit


def test_an_unscored_pillar_is_never_the_largest_gap(app_client) -> None:  # noqa: F811
    # Identity unscored; every other capability at stage 3 (66.6%), target 4:
    # the scored pillars' gap is 33.4. Identity's null current compared as 0
    # would give it a gap of 100.0 and make it "Largest".
    body = _world(
        app_client,
        kind="zero_trust_cisa",
        stage=0,
        target_stage=4,
        stage_by_code=lambda code: None if code.startswith("CISA.ID.") else 3,
    )
    identity = body["pillars"][0]
    assert (identity["code"], identity["answered_count"]) == ("ID", 0), identity  # positive first
    assert identity["current_pct"] is None, identity
    assert body["largest_gap_pillar"] != identity["name"], body["largest_gap_pillar"]
    assert body["largest_gap_pct"] == 33.4, body["largest_gap_pct"]
