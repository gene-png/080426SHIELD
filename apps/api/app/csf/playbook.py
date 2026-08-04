"""CSF 2.0 full-Playbook deterministic engine (Work Order D4).

Pure functions only — the AI never computes any of this. Implements, exactly per
CSF_Flow_Spec section 8:

  - total per subcategory per tier = sum of the five dimension scores (0..10)
  - maturity level from total (1..5)
  - the evidence cap (no evidence -> Implementation <= 1 AND level <= 2)
  - the weighted-floor roll-up to the Enterprise score (six ordered rules,
    first match wins; the rule number is recorded)
  - gap detection (current < target) and P1/P2/P3 priority

Everything here is unit-tested in tests/unit/test_csf_playbook.py.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass


class Tier(enum.StrEnum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


@dataclass(frozen=True)
class DimensionScores:
    """The five CSF scoring dimensions, each 0, 1, or 2."""

    governance: int = 0
    policy: int = 0  # Policy and Process
    implementation: int = 0
    monitoring: int = 0  # Monitoring and Measurement
    improvement: int = 0  # Continuous Improvement

    def clamped(self) -> DimensionScores:
        def _c(v: int) -> int:
            return max(0, min(2, int(v)))

        return DimensionScores(
            governance=_c(self.governance),
            policy=_c(self.policy),
            implementation=_c(self.implementation),
            monitoring=_c(self.monitoring),
            improvement=_c(self.improvement),
        )


def total(ds: DimensionScores) -> int:
    """Sum of the five dimensions, range 0..10."""
    d = ds.clamped()
    return d.governance + d.policy + d.implementation + d.monitoring + d.improvement


def maturity_level(total_score: int) -> int:
    """0-2 -> L1, 3-5 -> L2, 6-7 -> L3, 8-9 -> L4, 10 -> L5."""
    t = max(0, min(10, int(total_score)))
    if t <= 2:
        return 1
    if t <= 5:
        return 2
    if t <= 7:
        return 3
    if t <= 9:
        return 4
    return 5


@dataclass(frozen=True)
class TierResult:
    dimensions: DimensionScores
    total: int
    level: int
    evidence_capped: bool


def score_tier(ds: DimensionScores, *, has_evidence: bool) -> TierResult:
    """Total + maturity level for one tier, applying the evidence cap.

    Evidence cap (CSF_Flow_Spec section 8): if evidence cannot be produced,
    Implementation cannot exceed 1 AND the maturity level cannot exceed 2.
    """
    d = ds.clamped()
    capped = False
    if not has_evidence and d.implementation > 1:
        d = DimensionScores(
            governance=d.governance,
            policy=d.policy,
            implementation=1,
            monitoring=d.monitoring,
            improvement=d.improvement,
        )
        capped = True
    t = total(d)
    level = maturity_level(t)
    if not has_evidence and level > 2:
        level = 2
        capped = True
    return TierResult(dimensions=d, total=t, level=level, evidence_capped=capped)


@dataclass(frozen=True)
class RollupResult:
    score: int
    rule: int  # 1..6, the weighted-floor rule that decided it


def weighted_floor_rollup(
    tier_scores: Mapping[Tier, int],
    *,
    is_core_primary: bool,
    is_supporting_or_supplemental: bool,
) -> RollupResult:
    """Roll the per-tier scores up to one Enterprise score (CSF_Flow_Spec section 8).

    Apply in order, first match wins; the rule number is returned.
      1. All tiers the same score -> that score.
      2. Primary alignment to a Core metric AND a gap between tiers exists
         -> strict floor (lowest). (Rule 2 always overrides Rule 5.)
      3. HIGH tier is the lowest scorer -> HIGH's score.
      4. MODERATE is lowest (HIGH higher) -> MODERATE's score.
      5. Only LOW is lowest AND Supporting-aligned/Supplemental -> the HIGH/MOD
         score (documented exception).
      6. Mixed otherwise -> lower score plus reasoning.

    `tier_scores` holds only the tiers the client actually uses. The 'score'
    unit is whatever the caller rolls up (totals 0-10 or levels 1-5); the rules
    are unit-agnostic.
    """
    scores = {t: int(s) for t, s in tier_scores.items()}
    if not scores:
        raise ValueError("weighted_floor_rollup needs at least one tier score.")

    vals = list(scores.values())
    lo = min(vals)

    # Rule 1: all equal.
    if len(set(vals)) == 1:
        return RollupResult(score=vals[0], rule=1)

    # Rule 2: Core+Primary metric with a gap between tiers -> strict floor.
    if is_core_primary:
        return RollupResult(score=lo, rule=2)

    high = scores.get(Tier.HIGH)
    mod = scores.get(Tier.MODERATE)
    low = scores.get(Tier.LOW)

    # Rule 3: HIGH is (a) lowest.
    if high is not None and high == lo:
        return RollupResult(score=high, rule=3)

    # Rule 4: MODERATE is lowest, HIGH strictly higher.
    if mod is not None and mod == lo and (high is None or high > lo):
        return RollupResult(score=mod, rule=4)

    # Rule 5: only LOW is the lowest, and the subcategory is Supporting/Supplemental.
    only_low_lowest = (
        low is not None and low == lo and all(s > lo for t, s in scores.items() if t != Tier.LOW)
    )
    if only_low_lowest and is_supporting_or_supplemental:
        higher = max(s for t, s in scores.items() if t != Tier.LOW)
        return RollupResult(score=higher, rule=5)

    # Rule 6: mixed otherwise -> lower score.
    return RollupResult(score=lo, rule=6)


def is_gap(current_level: int, target_level: int) -> bool:
    """A gap exists when current maturity is below target."""
    return int(current_level) < int(target_level)


def gap_priority(*, is_core: bool, high_tier: bool, multi_system: bool) -> str:
    """P1/P2/P3 per CSF_Flow_Spec section 8.

    P1 = Core metric AND HIGH tier AND multi-system gap.
    P2 = Core metric OR HIGH tier.
    P3 = all other gaps.
    """
    if is_core and high_tier and multi_system:
        return "P1"
    if is_core or high_tier:
        return "P2"
    return "P3"
