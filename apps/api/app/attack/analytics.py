"""ATT&CK coverage heatmap analytics.

Pure functions over a `technique_code -> status` map. Returns per-tactic
coverage breakdowns (counts + percentages by status) that the admin
heatmap UI can render directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.attack.catalog import TACTICS, TECHNIQUES, parent_techniques
from app.attack.coverage import CoverageStatus


@dataclass(frozen=True)
class TacticCoverage:
    tactic_id: str
    tactic_name: str
    technique_count: int  # parent techniques only - sub-techniques counted separately
    sub_technique_count: int
    covered: int
    partial: int
    gap: int
    not_applicable: int
    unscored: int
    coverage_pct: float  # (covered + 0.5*partial) / addressable * 100


@dataclass(frozen=True)
class CoverageRollup:
    total_techniques: int
    total_sub_techniques: int
    scored_count: int
    unscored_count: int
    covered: int
    partial: int
    gap: int
    not_applicable: int
    coverage_pct: float
    by_tactic: tuple[TacticCoverage, ...]


_STATUS_BUCKETS = (
    CoverageStatus.COVERED,
    CoverageStatus.PARTIAL,
    CoverageStatus.GAP,
    CoverageStatus.NOT_APPLICABLE,
)


def _validated(value: str | None) -> CoverageStatus | None:
    if value is None:
        return None
    try:
        return CoverageStatus(value)
    except ValueError:
        return None


def _pct(numer: float, denom: float) -> float:
    if denom == 0:
        return 0.0
    return round(numer / denom * 100, 1)


def _coverage_for_codes(codes: list[str], coverage_map: Mapping[str, str | None]) -> dict[str, int]:
    counts = {s.value: 0 for s in _STATUS_BUCKETS}
    counts["unscored"] = 0
    for code in codes:
        status = _validated(coverage_map.get(code))
        if status is None:
            counts["unscored"] += 1
        else:
            counts[status.value] += 1
    return counts


def compute(coverage_map: Mapping[str, str | None]) -> CoverageRollup:
    by_tactic: list[TacticCoverage] = []
    for ta in TACTICS:
        # Parent techniques mapped to this tactic.
        parent_codes = [t.id for t in parent_techniques() if ta.id in t.tactics]
        sub_codes = [t.id for t in TECHNIQUES if t.is_sub_technique and ta.id in t.tactics]
        all_codes = parent_codes + sub_codes
        counts = _coverage_for_codes(all_codes, coverage_map)
        addressable = (
            counts[CoverageStatus.COVERED.value]
            + counts[CoverageStatus.PARTIAL.value]
            + counts[CoverageStatus.GAP.value]
        )
        weighted = counts[CoverageStatus.COVERED.value] + 0.5 * counts[CoverageStatus.PARTIAL.value]
        by_tactic.append(
            TacticCoverage(
                tactic_id=ta.id,
                tactic_name=ta.name,
                technique_count=len(parent_codes),
                sub_technique_count=len(sub_codes),
                covered=counts[CoverageStatus.COVERED.value],
                partial=counts[CoverageStatus.PARTIAL.value],
                gap=counts[CoverageStatus.GAP.value],
                not_applicable=counts[CoverageStatus.NOT_APPLICABLE.value],
                unscored=counts["unscored"],
                coverage_pct=_pct(weighted, addressable),
            )
        )

    # Overall (uses every catalog entry exactly once).
    overall_counts = {s.value: 0 for s in _STATUS_BUCKETS}
    overall_counts["unscored"] = 0
    for t in TECHNIQUES:
        status = _validated(coverage_map.get(t.id))
        if status is None:
            overall_counts["unscored"] += 1
        else:
            overall_counts[status.value] += 1
    addressable_total = (
        overall_counts[CoverageStatus.COVERED.value]
        + overall_counts[CoverageStatus.PARTIAL.value]
        + overall_counts[CoverageStatus.GAP.value]
    )
    weighted_total = (
        overall_counts[CoverageStatus.COVERED.value]
        + 0.5 * overall_counts[CoverageStatus.PARTIAL.value]
    )
    scored_count = sum(overall_counts[s.value] for s in _STATUS_BUCKETS)

    parents = parent_techniques()
    sub_total = len(TECHNIQUES) - len(parents)
    return CoverageRollup(
        total_techniques=len(parents),
        total_sub_techniques=sub_total,
        scored_count=scored_count,
        unscored_count=overall_counts["unscored"],
        covered=overall_counts[CoverageStatus.COVERED.value],
        partial=overall_counts[CoverageStatus.PARTIAL.value],
        gap=overall_counts[CoverageStatus.GAP.value],
        not_applicable=overall_counts[CoverageStatus.NOT_APPLICABLE.value],
        coverage_pct=_pct(weighted_total, addressable_total),
        by_tactic=tuple(by_tactic),
    )


__all__ = ["CoverageRollup", "TacticCoverage", "compute"]
