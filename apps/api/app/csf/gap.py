"""CSF 2.0 gap analysis + remediation prioritization.

Pure functions. Given a `subcategory_code -> tier` map (plus optional
notes), produces a prioritized list of gaps the assessor should address
to lift the engagement's maturity floor.

Prioritization model:
  Each answered subcategory yields a `gap_size` = target_tier - current_tier.
  Default target is tier 3 (Repeatable) — the NIST-recommended floor
  for organizations beyond very small operations. The target is
  configurable per call so a federal customer aiming at Adaptive (tier 4)
  gets a different list.

Ordering:
  1. Gap size (largest first)
  2. Function "criticality weight" - GV + ID are baseline; PR + DE +
     RS + RC weight slightly higher because operational risk lands on
     them. Configurable but defaults reflect typical FedRAMP guidance.
  3. Alphabetic code (stable tie-breaker)

Unscored subcategories are surfaced separately so they don't drown
the list - the gap analysis is for known weaknesses, not unknown ones.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from app.csf.catalog import (
    FUNCTIONS,
    SUBCATEGORIES,
    FunctionCode,
    Subcategory,
)
from app.csf.maturity import MaturityTier, tier_label

_FUNCTION_NAME_BY_CODE: dict[FunctionCode, str] = {f.code: f.name for f in FUNCTIONS}

DEFAULT_TARGET_TIER = int(MaturityTier.REPEATABLE)
DEFAULT_TOP_N = 20

# Function criticality weights. Tunable - the order matters more than
# the absolute values. PROTECT / DETECT / RESPOND / RECOVER carry more
# operational urgency than GOVERN / IDENTIFY in NIST's published
# recommendations for organizations with mature governance already.
FUNCTION_WEIGHTS: dict[FunctionCode, float] = {
    FunctionCode.GV: 1.0,
    FunctionCode.ID: 1.0,
    FunctionCode.PR: 1.15,
    FunctionCode.DE: 1.20,
    FunctionCode.RS: 1.20,
    FunctionCode.RC: 1.15,
}


@dataclass(frozen=True)
class Gap:
    code: str
    function: FunctionCode
    function_name: str
    category: str
    name: str
    outcome: str
    current_tier: int
    target_tier: int
    gap_size: int
    priority_score: float
    notes: str | None


@dataclass(frozen=True)
class GapAnalysis:
    target_tier: int
    target_label: str
    gaps: tuple[Gap, ...]
    unscored_codes: tuple[str, ...]
    total_gap_count: int  # before truncation to top_n
    gap_count_by_function: dict[str, int]


def _function_name(fn: FunctionCode) -> str:
    return _FUNCTION_NAME_BY_CODE.get(fn, fn.value)


def _validated(tier: int | None) -> int | None:
    if tier is None:
        return None
    if 1 <= int(tier) <= 4:
        return int(tier)
    return None


def _row_for(sc: Subcategory, current: int, target: int, notes: str | None) -> Gap:
    gap_size = max(0, target - current)
    weight = FUNCTION_WEIGHTS.get(sc.function, 1.0)
    priority = round(gap_size * weight, 2)
    return Gap(
        code=sc.code,
        function=sc.function,
        function_name=_function_name(sc.function),
        category=sc.category,
        name=sc.name,
        outcome=sc.outcome,
        current_tier=current,
        target_tier=target,
        gap_size=gap_size,
        priority_score=priority,
        notes=notes,
    )


#: CSF 2.0 tiers run 1..4. ZT's equivalent ceiling depends on the framework
#: (CISA 4, DoD 3); CSF's is a constant, which is why `resolve_target_tier`
#: takes no framework argument where `resolve_target_stage` does.
MAX_TIER = 4


def resolve_target_tier(chosen: object) -> tuple[int, str]:
    """An engagement-level CSF target, plus WHERE IT CAME FROM (#184).

    Returns `(tier, source)` with source one of:

      "client"               the client's stored choice, a real CSF tier
      "default"              the client chose nothing; the engine default applies
      "client_out_of_range"  the stored choice is not a tier CSF has
      "client_unparseable"   the stored value is not a whole number at all

    The last two are the point of this function. "The client chose nothing" and
    "the client's choice could not be used" are different facts, and the second
    is answerable by re-asking them -- so flattening the two throws away the
    more actionable one. Both `routes/clients.py` and `routes/csf.py` computed
    `"client" if <stored> is not None else "default"`, keyed on whether a value
    was OFFERED rather than whether it SURVIVED, which is the line #125 was
    filed against in ZT.

    MIRRORED FROM `zt/scoring.py::resolve_target_stage`, deliberately, down to
    the exception list. A second design for the same question is how two
    services come to disagree about one client's target.

    It REPORTS rather than raises: a stored value is data, not a programming
    error, and refusing to render an existing engagement is not an available
    response to it. `analyze` raises, because by then the value has been
    resolved and anything out of range is a caller bug.

    `OverflowError` is not decorative -- `float(10**400)` raises it, and an int
    wider than a double is ordinary JSON. ZT's resolver records that omitting
    it is what an absolute claim costs when its test enumerates values someone
    thought of instead of deriving them; inherited here rather than relearned.
    """
    if chosen is None:
        return (DEFAULT_TARGET_TIER, "default")
    # `bool` subclasses `int`, so this must precede the numeric parse or a
    # stored `True` resolves to Tier 1 and gets attributed to the client.
    if isinstance(chosen, bool):
        return (DEFAULT_TARGET_TIER, "client_unparseable")
    try:
        n = float(chosen)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return (DEFAULT_TARGET_TIER, "client_unparseable")
    if not math.isfinite(n):
        return (DEFAULT_TARGET_TIER, "client_unparseable")
    if not 1 <= n <= MAX_TIER:
        return (DEFAULT_TARGET_TIER, "client_out_of_range")
    if n != int(n):
        return (DEFAULT_TARGET_TIER, "client_unparseable")
    return (int(n), "client")


def analyze(
    answers: Mapping[str, int | None],
    *,
    notes: Mapping[str, str | None] | None = None,
    target_tier: int = DEFAULT_TARGET_TIER,
    top_n: int = DEFAULT_TOP_N,
) -> GapAnalysis:
    """Return a prioritized gap analysis.

    `answers` keys not present in the canonical catalog are silently
    ignored (defensive against stale data).
    """
    if not (1 <= target_tier <= MAX_TIER):
        # REFUSE, do not clamp (#184, the CSF twin of #125). This clamped to
        # `DEFAULT_TARGET_TIER` and returned the clamped value, so
        # `GET /csf/services/{id}/gap-analysis?target_tier=99` answered 200
        # with `target_tier: 3` and a gap set computed against 3 -- a caller
        # asked one question and was answered a different one in the same
        # units. A silent clamp is a default-value fallback on error, which
        # core principle 2 forbids.
        #
        # Callers resolve a CLIENT-SUPPLIED tier through `resolve_target_tier`
        # first, which names the fault instead of raising. Reaching here means
        # a caller passed an unresolved value, which is a programming error.
        raise ValueError(
            f"target_tier {target_tier} is out of range for CSF 2.0 "
            f"(valid 1-{MAX_TIER}). Resolve a client-supplied tier through "
            f"resolve_target_tier() first."
        )
    notes = notes or {}

    rows: list[Gap] = []
    unscored: list[str] = []
    for sc in SUBCATEGORIES:
        t = _validated(answers.get(sc.code))
        if t is None:
            unscored.append(sc.code)
            continue
        if t >= target_tier:
            continue  # Met or exceeded - no gap.
        rows.append(_row_for(sc, t, target_tier, notes.get(sc.code)))

    # Order: priority_score desc, code asc.
    rows.sort(key=lambda g: (-g.priority_score, g.code))

    by_function: dict[str, int] = {}
    for g in rows:
        by_function[g.function.value] = by_function.get(g.function.value, 0) + 1

    return GapAnalysis(
        target_tier=target_tier,
        target_label=tier_label(target_tier),
        gaps=tuple(rows[:top_n]),
        unscored_codes=tuple(unscored),
        total_gap_count=len(rows),
        gap_count_by_function=by_function,
    )


__all__ = [
    "DEFAULT_TARGET_TIER",
    "DEFAULT_TOP_N",
    "FUNCTION_WEIGHTS",
    "Gap",
    "GapAnalysis",
    "analyze",
]
