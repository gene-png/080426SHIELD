"""NIST CSF 2.0 scoring engine.

Pure functions. No I/O, no DB. Callers pass in a mapping of
`subcategory_code -> maturity_tier` (or None for unscored).

Rollup model (mirrors the published NIST CSF guidance):
  - Per-function score: arithmetic mean of answered subcategories
    in that function. Unscored rows are excluded from the mean so a
    half-finished assessment doesn't dilute the score.
  - Overall maturity: weighted by subcategory count across functions
    (i.e., the simple average of all answered subcategories, which is
    equivalent because every subcategory is weighted equally).
  - Coverage: answered count / total count, per-function and overall.
  - Weakest subcategory codes per function: the lowest-tier answered
    subcategories (used by the gap analysis in stage 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.csf.catalog import (
    FUNCTIONS,
    SUBCATEGORIES,
    FunctionCode,
    function_by_code,
)
from app.csf.maturity import MaturityTier, tier_label

# How many of the weakest subcategories to surface per function. Keeps
# the JSON payload bounded even for engagements with many low scores.
WEAKEST_PER_FUNCTION = 5


@dataclass(frozen=True)
class FunctionScoreResult:
    function: FunctionCode
    function_name: str
    subcategory_count: int
    answered_count: int
    average_tier: float | None
    coverage_pct: float
    weakest_subcategory_codes: tuple[str, ...]


@dataclass(frozen=True)
class ScoreResult:
    total_subcategories: int
    answered_subcategories: int
    coverage_pct: float
    average_tier: float | None
    overall_maturity_label: str
    by_function: tuple[FunctionScoreResult, ...]


def _coverage_pct(answered: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(answered / total * 100, 1)


def _round_average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _label_from_average(avg: float | None) -> str:
    """Bucketize the float average back into a tier short label.

    Bands: <1.5 = Partial, <2.5 = Risk Informed, <3.5 = Repeatable, else Adaptive.
    Returns "Unscored" when avg is None.
    """
    if avg is None:
        return "Unscored"
    if avg < 1.5:
        return tier_label(MaturityTier.PARTIAL)
    if avg < 2.5:
        return tier_label(MaturityTier.RISK_INFORMED)
    if avg < 3.5:
        return tier_label(MaturityTier.REPEATABLE)
    return tier_label(MaturityTier.ADAPTIVE)


def _validated(tier: int | None) -> int | None:
    """Return tier if 1-4, else None. Defensive against bogus DB rows."""
    if tier is None:
        return None
    if 1 <= int(tier) <= 4:
        return int(tier)
    return None


def compute(answers: Mapping[str, int | None]) -> ScoreResult:
    """Roll up `answers` into a full ScoreResult.

    Subcategories absent from `answers` (or with a None / out-of-range
    tier) are treated as unscored.
    """
    per_function: list[FunctionScoreResult] = []
    overall_values: list[int] = []
    overall_total = 0
    overall_answered = 0

    for fn in FUNCTIONS:
        codes = [s.code for s in SUBCATEGORIES if s.function == fn.code]
        total = len(codes)
        overall_total += total

        scored_pairs: list[tuple[str, int]] = []
        for code in codes:
            t = _validated(answers.get(code))
            if t is not None:
                scored_pairs.append((code, t))

        answered = len(scored_pairs)
        overall_answered += answered
        overall_values.extend(t for _, t in scored_pairs)

        # Weakest = lowest tier first; ties broken by code (stable, deterministic).
        scored_pairs.sort(key=lambda p: (p[1], p[0]))
        weakest = tuple(code for code, _ in scored_pairs[:WEAKEST_PER_FUNCTION])

        per_function.append(
            FunctionScoreResult(
                function=fn.code,
                function_name=fn.name,
                subcategory_count=total,
                answered_count=answered,
                average_tier=_round_average([t for _, t in scored_pairs]),
                coverage_pct=_coverage_pct(answered, total),
                weakest_subcategory_codes=weakest,
            )
        )

    avg_overall = _round_average(overall_values)
    return ScoreResult(
        total_subcategories=overall_total,
        answered_subcategories=overall_answered,
        coverage_pct=_coverage_pct(overall_answered, overall_total),
        average_tier=avg_overall,
        overall_maturity_label=_label_from_average(avg_overall),
        by_function=tuple(per_function),
    )


__all__ = [
    "FunctionScoreResult",
    "ScoreResult",
    "WEAKEST_PER_FUNCTION",
    "compute",
    "function_by_code",  # re-exported for callers that want both
]
