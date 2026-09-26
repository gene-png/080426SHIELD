"""ATT&CK coverage heatmap analytics.

Pure functions over a `technique_code -> status` map. Returns per-tactic
coverage breakdowns (counts + percentages by status) that the admin
heatmap UI can render directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.attack.catalog import TACTICS, TECHNIQUES, parent_techniques
from app.attack.coverage import ASSESSED, UNJUDGED, CoverageStatus


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
    # #102 / plan 5.1: a status exists but its supporting citations are
    # unconfirmed. Its OWN state — never collapsed into `gap` (which says
    # nothing was found) and never folded into `unscored` (which says no status
    # was assigned). Excluded from `addressable`, so it withholds a claim rather
    # than scoring a zero.
    pending_review: int
    # #554: rows the assessed denominator excludes, counted so they can be
    # stated beside the percentage rather than silently shrinking it.
    outside_control_surface: int
    unable_to_determine: int
    coverage_pct: float  # (covered + 0.5*partial) / addressable * 100


@dataclass(frozen=True)
class CoverageRollup:
    total_techniques: int
    total_sub_techniques: int
    scored_count: int
    unscored_count: int
    #: Every technique the rollup tallied: the "Y" of "Scored: X/Y". Derived from
    #: the tally, so it cannot disagree with the rows (#621 round 2).
    catalogue_count: int
    covered: int
    partial: int
    gap: int
    not_applicable: int
    pending_review: int
    outside_control_surface: int
    unable_to_determine: int
    coverage_pct: float
    by_tactic: tuple[TacticCoverage, ...]


# Every status. `_validated` maps anything NOT in the enum to unscored, so a
# status missing here would vanish from every count while still stored (#554).
_STATUS_BUCKETS = tuple(CoverageStatus)


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


#: Statuses that a pending-review flag can hold back: the ones that make a
#: POSITIVE claim, and so are the only ones that can be unsupported.
#:
#: `not_applicable` is already outside `addressable`, so flagging its evidence
#: changes nothing about a claim that was never made, and `None` (unscored) has
#: no claim to withhold.
#:
#: `gap` was in this tuple and has been REMOVED. A gap is an ABSENCE claim --
#: its evidence is the lack of a citation, so there is nothing to withhold --
#: and withholding one is not neutral: `addressable` is the denominator, so
#: dropping a gap out of it RAISES `coverage_pct` while deleting a finding. Ten
#: covered beside ten gaps went from 50% to 100% when the gaps were flagged.
#: That is 5.1 invariant 1 read backwards. See
#: `test_withholding_a_gap_would_raise_the_score`, and `app/attack/pending.py`,
#: which never emits a gap code in the first place -- this tuple is the second
#: of the two locks, not the only one.
_WITHHOLDABLE = (CoverageStatus.COVERED, CoverageStatus.PARTIAL)


def _tally(
    codes: list[str],
    coverage_map: Mapping[str, str | None],
    pending_codes: frozenset[str],
) -> dict[str, int]:
    counts = {s.value: 0 for s in _STATUS_BUCKETS}
    counts["unscored"] = 0
    counts["pending_review"] = 0
    for code in codes:
        status = _validated(coverage_map.get(code))
        if status is None:
            counts["unscored"] += 1
        elif code in pending_codes and status in _WITHHOLDABLE:
            counts["pending_review"] += 1
        else:
            counts[status.value] += 1
    return counts


def compute(
    coverage_map: Mapping[str, str | None],
    pending_codes: Iterable[str] | None = None,
) -> CoverageRollup:
    """Roll coverage up per tactic and overall.

    `pending_codes` are techniques whose supporting citations are unconfirmed
    (#102). They are DERIVED here rather than written over `status`: 5.1 requires
    that clearing a flag moves the technique into whichever of covered/partial/
    gap its stored status says, so that status has to survive underneath.

    A code with no status, or one marked `not_applicable`, is never pending —
    there is no claim to withhold.
    """
    pending = frozenset(pending_codes or ())
    by_tactic: list[TacticCoverage] = []
    for ta in TACTICS:
        # Parent techniques mapped to this tactic.
        parent_codes = [t.id for t in parent_techniques() if ta.id in t.tactics]
        sub_codes = [t.id for t in TECHNIQUES if t.is_sub_technique and ta.id in t.tactics]
        all_codes = parent_codes + sub_codes
        counts = _tally(all_codes, coverage_map, pending)
        addressable = sum(counts[s.value] for s in ASSESSED)
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
                pending_review=counts["pending_review"],
                outside_control_surface=counts[CoverageStatus.OUTSIDE_CONTROL_SURFACE.value],
                unable_to_determine=counts[CoverageStatus.UNABLE_TO_DETERMINE.value],
                coverage_pct=_pct(weighted, addressable),
            )
        )

    # Overall (uses every catalog entry exactly once).
    overall_counts = _tally([t.id for t in TECHNIQUES], coverage_map, pending)
    addressable_total = sum(overall_counts[s.value] for s in ASSESSED)
    weighted_total = (
        overall_counts[CoverageStatus.COVERED.value]
        + 0.5 * overall_counts[CoverageStatus.PARTIAL.value]
    )
    # A withheld claim is still an ASSIGNED status, so it counts as scored.
    #
    # An UNJUDGED status (`unable_to_determine`) does not: nobody verified the
    # technique, and "scored" must mean the same rows in the ATT&CK deliverable
    # as in the Risk Register's citable scope (`risk/link_scope.py` reads the
    # same `UNJUDGED`). This REVERSES D-092 Decision 3's rule, which counted it
    # as scored (#621 round 2, finding 1).
    #
    # The total on screen still must not shrink as rows move out of "scored" --
    # that was the reason for the old rule. It holds because every "X/Y"
    # renderer now takes Y from `catalogue_count`, the size of the tally
    # itself, rather than from scored + unscored.
    scored_count = (
        sum(overall_counts[s.value] for s in _STATUS_BUCKETS if s not in UNJUDGED)
        + overall_counts["pending_review"]
    )
    catalogue_count = sum(overall_counts.values())

    parents = parent_techniques()
    sub_total = len(TECHNIQUES) - len(parents)
    return CoverageRollup(
        total_techniques=len(parents),
        total_sub_techniques=sub_total,
        scored_count=scored_count,
        unscored_count=overall_counts["unscored"],
        catalogue_count=catalogue_count,
        covered=overall_counts[CoverageStatus.COVERED.value],
        partial=overall_counts[CoverageStatus.PARTIAL.value],
        gap=overall_counts[CoverageStatus.GAP.value],
        not_applicable=overall_counts[CoverageStatus.NOT_APPLICABLE.value],
        pending_review=overall_counts["pending_review"],
        outside_control_surface=overall_counts[CoverageStatus.OUTSIDE_CONTROL_SURFACE.value],
        unable_to_determine=overall_counts[CoverageStatus.UNABLE_TO_DETERMINE.value],
        coverage_pct=_pct(weighted_total, addressable_total),
        by_tactic=tuple(by_tactic),
    )


__all__ = ["CoverageRollup", "TacticCoverage", "compute"]
