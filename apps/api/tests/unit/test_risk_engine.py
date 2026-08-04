"""Risk Register 5x5 tier engine + rollups (Work Order E)."""

from __future__ import annotations

import pytest

from app.risk.engine import (
    Impact,
    Likelihood,
    RecommendedAction,
    RiskAxis,
    RiskTier,
    action_counts,
    axis_counts,
    cadence_for,
    matrix_counts,
    risk_score,
    tier_counts,
    tier_for,
)


@pytest.mark.unit
def test_risk_score_range() -> None:
    assert risk_score(Likelihood.VERY_LOW, Impact.NEGLIGIBLE) == 1
    assert risk_score(Likelihood.VERY_HIGH, Impact.CATASTROPHIC) == 25
    assert risk_score(Likelihood.MEDIUM, Impact.MODERATE) == 9


@pytest.mark.unit
@pytest.mark.parametrize(
    "likelihood,impact,tier",
    [
        # Special Critical cases.
        (Likelihood.HIGH, Impact.CATASTROPHIC, RiskTier.CRITICAL),
        (Likelihood.VERY_HIGH, Impact.CATASTROPHIC, RiskTier.CRITICAL),
        (Likelihood.VERY_HIGH, Impact.MAJOR, RiskTier.CRITICAL),
        # Very High + Moderate = score 15 -> High (Moderate < Major, no Critical).
        (Likelihood.VERY_HIGH, Impact.MODERATE, RiskTier.HIGH),
        # score >= 15 band.
        (Likelihood.HIGH, Impact.MAJOR, RiskTier.HIGH),  # 16
        # score >= 9 band.
        (Likelihood.MEDIUM, Impact.MODERATE, RiskTier.MEDIUM),  # 9
        (Likelihood.MEDIUM, Impact.MAJOR, RiskTier.MEDIUM),  # 12
        # score >= 4 band.
        (Likelihood.LOW, Impact.MODERATE, RiskTier.LOW),  # 6
        (Likelihood.VERY_LOW, Impact.MAJOR, RiskTier.LOW),  # 4
        # negligible.
        (Likelihood.VERY_LOW, Impact.NEGLIGIBLE, RiskTier.NEGLIGIBLE),  # 1
        (Likelihood.LOW, Impact.MINOR, RiskTier.NEGLIGIBLE),  # 4? -> check
    ],
)
def test_tier_for(likelihood: Likelihood, impact: Impact, tier: RiskTier) -> None:
    # Low + Minor: score (2*2)=4 -> Low, not Negligible; fix the expectation inline.
    if (likelihood, impact) == (Likelihood.LOW, Impact.MINOR):
        assert tier_for(likelihood, impact) == RiskTier.LOW
        return
    assert tier_for(likelihood, impact) == tier


@pytest.mark.unit
def test_tier_never_critical_below_major_or_below_high_likelihood() -> None:
    # High likelihood + Major (not Catastrophic) -> High, not Critical.
    assert tier_for(Likelihood.HIGH, Impact.MAJOR) == RiskTier.HIGH
    # Medium likelihood + Catastrophic -> not Critical (likelihood too low).
    assert tier_for(Likelihood.MEDIUM, Impact.CATASTROPHIC) == RiskTier.HIGH  # 15


@pytest.mark.unit
def test_cadence_distinct_per_tier() -> None:
    cadences = {cadence_for(t) for t in RiskTier}
    assert len(cadences) >= 4
    assert "board" in cadence_for(RiskTier.CRITICAL).lower()


@pytest.mark.unit
def test_rollups() -> None:
    tiers = [RiskTier.CRITICAL, RiskTier.CRITICAL, RiskTier.LOW]
    assert tier_counts(tiers)["critical"] == 2
    assert tier_counts(tiers)["low"] == 1
    assert tier_counts(tiers)["high"] == 0

    axes = [RiskAxis.DETECTION, RiskAxis.DETECTION, RiskAxis.RESPONSE]
    assert axis_counts(axes) == {"detection": 2, "prevention": 0, "response": 1}

    actions = [RecommendedAction.REMEDIATE, RecommendedAction.ACCEPT]
    assert action_counts(actions)["remediate"] == 1
    assert action_counts(actions)["avoid"] == 0


@pytest.mark.unit
def test_matrix_counts_is_full_grid() -> None:
    entries = [
        (Likelihood.HIGH, Impact.CATASTROPHIC),
        (Likelihood.HIGH, Impact.CATASTROPHIC),
        (Likelihood.LOW, Impact.MINOR),
    ]
    cells = matrix_counts(entries)
    assert len(cells) == 25  # 5x5
    hot = next(c for c in cells if c.likelihood == "high" and c.impact == "catastrophic")
    assert hot.count == 2
    assert hot.tier == "critical"
    empty = next(c for c in cells if c.likelihood == "very_low" and c.impact == "negligible")
    assert empty.count == 0
    assert empty.tier == "negligible"
