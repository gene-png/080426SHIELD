"""A stage stored above its capability's maximum counts at the maximum (#839, F1).

The advisor's default (#736 comment 6048561596): a stage written before the
write-path guard is LEFT as stored, counted at the capped level in every
figure, and disclosed. This pins the engine half and the detection the
disclosure will read. The disclosure's wording is pending approval and is not
pinned here.

1.1 has no Advanced activity, so its maximum is 2; 1.2 has one, so 3 stands.
Both groups are pinned from the extraction in `test_zt_dod_target_caps.py`.
"""

from __future__ import annotations

import pytest

from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import analyze_gaps, compute
from app.zt.target_caps import stages_above_capability_max

pytestmark = pytest.mark.unit

DOD = ZtFrameworkCode.DOD_ZTRA
NO_ADVANCED = "DOD.USR.01"
HAS_ADVANCED = "DOD.USR.02"


def test_a_stored_three_on_a_capped_capability_counts_as_two() -> None:
    score = compute(DOD, {NO_ADVANCED: 3})
    assert score.answered_capabilities == 1
    assert score.average_stage == 2.0


def test_a_reachable_three_still_counts_as_three() -> None:
    assert compute(DOD, {HAS_ADVANCED: 3}).average_stage == 3.0
    assert compute(DOD, {NO_ADVANCED: 2, HAS_ADVANCED: 3}).average_stage == 2.5


def test_the_gap_engine_reads_the_capped_value() -> None:
    # Against an engagement target of 3, 1.1's target is capped at 2: a stored
    # 3 counted as 2 meets it, and is no gap.
    gap = analyze_gaps(DOD, {NO_ADVANCED: 3}, target_stage=3)
    assert NO_ADVANCED not in {g.code for g in gap.gaps}
    assert NO_ADVANCED not in gap.unscored_codes


def test_the_over_cap_rows_are_detected_in_catalog_order_and_cisa_has_none() -> None:
    answers = {HAS_ADVANCED: 3, NO_ADVANCED: 3, "DOD.USR.07": 3, "DOD.USR.03": 2}
    # 1.7 Least Privileged Access has no Advanced activity either.
    assert stages_above_capability_max(DOD, answers) == (NO_ADVANCED, "DOD.USR.07")
    assert stages_above_capability_max(DOD, {NO_ADVANCED: 2}) == ()
    assert stages_above_capability_max(ZtFrameworkCode.CISA_ZTMM_2_0, {"CISA.ID.01": 4}) == ()


def test_a_retired_row_is_not_reported_as_over_its_capability() -> None:
    # DOD.NET.05 is retired by 0064: not scored, disclosed by `zt/retired.py`.
    assert stages_above_capability_max(DOD, {"DOD.NET.05": 3}) == ()
