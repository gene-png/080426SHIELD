"""Risk Register deterministic engine (Work Order E).

Pure functions, identical to the Atlas dashboard logic (RiskRegister_Flow_Spec
section 5). The AI never sets the tier; it always derives from likelihood and
impact through the NIST 800-30 5x5 matrix here.

  score = (li+1) * (ii+1), li/ii are 0-based indexes into the ordered scales.
  - High or Very High likelihood AND Catastrophic impact -> Critical
  - Very High likelihood AND Major or higher impact      -> Critical
  - score >= 15 -> High
  - score >= 9  -> Medium
  - score >= 4  -> Low
  - otherwise   -> Negligible
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass


class Likelihood(enum.StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class Impact(enum.StrEnum):
    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    CATASTROPHIC = "catastrophic"


class RiskTier(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NEGLIGIBLE = "negligible"


class RiskAxis(enum.StrEnum):
    DETECTION = "detection"
    PREVENTION = "prevention"
    RESPONSE = "response"


class RecommendedAction(enum.StrEnum):
    REMEDIATE = "remediate"
    MITIGATE = "mitigate"
    ACCEPT = "accept"
    TRANSFER = "transfer"
    AVOID = "avoid"


LIKELIHOOD_ORDER: tuple[Likelihood, ...] = (
    Likelihood.VERY_LOW,
    Likelihood.LOW,
    Likelihood.MEDIUM,
    Likelihood.HIGH,
    Likelihood.VERY_HIGH,
)
IMPACT_ORDER: tuple[Impact, ...] = (
    Impact.NEGLIGIBLE,
    Impact.MINOR,
    Impact.MODERATE,
    Impact.MAJOR,
    Impact.CATASTROPHIC,
)


def risk_score(likelihood: Likelihood, impact: Impact) -> int:
    """(li+1) * (ii+1), range 1..25."""
    li = LIKELIHOOD_ORDER.index(likelihood)
    ii = IMPACT_ORDER.index(impact)
    return (li + 1) * (ii + 1)


def tier_for(likelihood: Likelihood, impact: Impact) -> RiskTier:
    """The NIST 800-30 5x5 tier. The AI never sets this — code always derives it."""
    ii = IMPACT_ORDER.index(impact)
    # High/Very High likelihood with Catastrophic impact -> Critical.
    if likelihood in (Likelihood.HIGH, Likelihood.VERY_HIGH) and impact == Impact.CATASTROPHIC:
        return RiskTier.CRITICAL
    # Very High likelihood with Major or higher impact -> Critical.
    if likelihood == Likelihood.VERY_HIGH and ii >= IMPACT_ORDER.index(Impact.MAJOR):
        return RiskTier.CRITICAL
    score = risk_score(likelihood, impact)
    if score >= 15:
        return RiskTier.HIGH
    if score >= 9:
        return RiskTier.MEDIUM
    if score >= 4:
        return RiskTier.LOW
    return RiskTier.NEGLIGIBLE


_CADENCE: dict[RiskTier, str] = {
    RiskTier.CRITICAL: "Quarterly review plus board notification.",
    RiskTier.HIGH: "Semi-annual review.",
    RiskTier.MEDIUM: "Annual review.",
    RiskTier.LOW: "Annual review or on the next scope cycle.",
    RiskTier.NEGLIGIBLE: "On the next scope cycle.",
}


def cadence_for(tier: RiskTier) -> str:
    """Suggested review cadence printed for the client (guidance only)."""
    return _CADENCE[tier]


# ---------------------------------------------------------------------------
# Rollups (dashboard cards)
# ---------------------------------------------------------------------------


def tier_counts(tiers: Iterable[RiskTier]) -> dict[str, int]:
    out = {t.value: 0 for t in RiskTier}
    for t in tiers:
        out[t.value] += 1
    return out


def axis_counts(axes: Iterable[RiskAxis]) -> dict[str, int]:
    out = {a.value: 0 for a in RiskAxis}
    for a in axes:
        out[a.value] += 1
    return out


def action_counts(actions: Iterable[RecommendedAction]) -> dict[str, int]:
    out = {a.value: 0 for a in RecommendedAction}
    for a in actions:
        out[a.value] += 1
    return out


@dataclass(frozen=True)
class MatrixCell:
    likelihood: str
    impact: str
    tier: str
    count: int


def matrix_counts(entries: Iterable[tuple[Likelihood, Impact]]) -> list[MatrixCell]:
    """The full 5x5 Likelihood x Impact grid with per-cell counts + tier color."""
    counts: dict[tuple[Likelihood, Impact], int] = {}
    for lk, im in entries:
        counts[(lk, im)] = counts.get((lk, im), 0) + 1
    cells: list[MatrixCell] = []
    for lk in LIKELIHOOD_ORDER:
        for im in IMPACT_ORDER:
            cells.append(
                MatrixCell(
                    likelihood=lk.value,
                    impact=im.value,
                    tier=tier_for(lk, im).value,
                    count=counts.get((lk, im), 0),
                )
            )
    return cells
