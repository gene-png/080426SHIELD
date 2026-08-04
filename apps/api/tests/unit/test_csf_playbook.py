"""CSF full-Playbook deterministic engine (Work Order D4)."""

from __future__ import annotations

import pytest

from app.csf.playbook import (
    DimensionScores,
    Tier,
    gap_priority,
    is_gap,
    maturity_level,
    score_tier,
    total,
    weighted_floor_rollup,
)


@pytest.mark.unit
def test_total_sums_five_dimensions() -> None:
    assert total(DimensionScores(2, 2, 2, 2, 2)) == 10
    assert total(DimensionScores(0, 0, 0, 0, 0)) == 0
    assert total(DimensionScores(2, 1, 0, 1, 1)) == 5
    # Out-of-range inputs are clamped to 0..2 per dimension.
    assert total(DimensionScores(5, -1, 2, 2, 2)) == 2 + 0 + 2 + 2 + 2


@pytest.mark.unit
@pytest.mark.parametrize(
    "score,level",
    [(0, 1), (2, 1), (3, 2), (5, 2), (6, 3), (7, 3), (8, 4), (9, 4), (10, 5)],
)
def test_maturity_level_mapping(score: int, level: int) -> None:
    assert maturity_level(score) == level


@pytest.mark.unit
def test_evidence_cap_clamps_implementation_and_level() -> None:
    # Full marks but NO evidence: Implementation -> 1, level -> 2.
    ds = DimensionScores(2, 2, 2, 2, 2)  # total 10, level 5
    capped = score_tier(ds, has_evidence=False)
    assert capped.dimensions.implementation == 1
    assert capped.total == 9  # 2+2+1+2+2
    assert capped.level == 2  # clamped from 4
    assert capped.evidence_capped is True


@pytest.mark.unit
def test_evidence_present_no_cap() -> None:
    ds = DimensionScores(2, 2, 2, 2, 2)
    r = score_tier(ds, has_evidence=True)
    assert r.total == 10
    assert r.level == 5
    assert r.evidence_capped is False


@pytest.mark.unit
def test_rollup_rule1_all_same() -> None:
    r = weighted_floor_rollup(
        {Tier.HIGH: 6, Tier.MODERATE: 6, Tier.LOW: 6},
        is_core_primary=False,
        is_supporting_or_supplemental=False,
    )
    assert (r.score, r.rule) == (6, 1)


@pytest.mark.unit
def test_rollup_rule2_core_primary_strict_floor() -> None:
    r = weighted_floor_rollup(
        {Tier.HIGH: 8, Tier.MODERATE: 6, Tier.LOW: 4},
        is_core_primary=True,
        is_supporting_or_supplemental=True,  # rule 2 overrides rule 5
    )
    assert (r.score, r.rule) == (4, 2)


@pytest.mark.unit
def test_rollup_rule3_high_lowest() -> None:
    r = weighted_floor_rollup(
        {Tier.HIGH: 4, Tier.MODERATE: 6, Tier.LOW: 8},
        is_core_primary=False,
        is_supporting_or_supplemental=False,
    )
    assert (r.score, r.rule) == (4, 3)


@pytest.mark.unit
def test_rollup_rule4_moderate_lowest() -> None:
    r = weighted_floor_rollup(
        {Tier.HIGH: 8, Tier.MODERATE: 4, Tier.LOW: 6},
        is_core_primary=False,
        is_supporting_or_supplemental=False,
    )
    assert (r.score, r.rule) == (4, 4)


@pytest.mark.unit
def test_rollup_rule5_only_low_lowest_supporting() -> None:
    r = weighted_floor_rollup(
        {Tier.HIGH: 8, Tier.MODERATE: 8, Tier.LOW: 4},
        is_core_primary=False,
        is_supporting_or_supplemental=True,
    )
    # Documented exception: take the HIGH/MOD score, not the LOW floor.
    assert (r.score, r.rule) == (8, 5)


@pytest.mark.unit
def test_rollup_rule6_mixed_otherwise() -> None:
    # Only LOW is lowest but NOT supporting/supplemental -> falls through to rule 6.
    r = weighted_floor_rollup(
        {Tier.HIGH: 8, Tier.MODERATE: 7, Tier.LOW: 4},
        is_core_primary=False,
        is_supporting_or_supplemental=False,
    )
    assert (r.score, r.rule) == (4, 6)


@pytest.mark.unit
def test_rollup_subset_of_tiers() -> None:
    # Client uses only HIGH + LOW; HIGH is lowest -> rule 3.
    r = weighted_floor_rollup(
        {Tier.HIGH: 3, Tier.LOW: 7},
        is_core_primary=False,
        is_supporting_or_supplemental=False,
    )
    assert (r.score, r.rule) == (3, 3)


@pytest.mark.unit
def test_is_gap_and_priority() -> None:
    assert is_gap(2, 4) is True
    assert is_gap(4, 4) is False
    assert gap_priority(is_core=True, high_tier=True, multi_system=True) == "P1"
    assert gap_priority(is_core=True, high_tier=False, multi_system=False) == "P2"
    assert gap_priority(is_core=False, high_tier=True, multi_system=False) == "P2"
    assert gap_priority(is_core=False, high_tier=False, multi_system=True) == "P3"
