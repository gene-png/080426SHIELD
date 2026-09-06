"""Zero Trust scoring + gap engine.

Pure functions. Given a `capability_code -> maturity_stage` map for a
chosen framework, produces:
  - Overall maturity stage (band-cutoff label)
  - Per-pillar stage rollup with coverage + weakest codes
  - Top-N prioritized gaps against a target stage

Framework awareness: the labels (Traditional/Initial/... for CISA,
Baseline/Target/... for DoD) are picked from the maturity module.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.zt.catalog import (
    Capability,
    capabilities,
    pillars,
)
from app.zt.maturity import (
    MaturityStage,
    ZtFrameworkCode,
    level_count,
    stage_label,
)

WEAKEST_PER_PILLAR = 5
DEFAULT_TARGET_STAGE = int(MaturityStage.STAGE_3)
DEFAULT_TOP_N = 20

# Pillar weights for gap prioritization. Identity + Data score highest
# in the typical FedRAMP / DoD risk picture because they sit closest to
# the protected resources; supporting pillars carry a 1.0 baseline.
_PILLAR_WEIGHTS: dict[str, float] = {
    # CISA codes
    "ID": 1.20,  # Identity
    "DT": 1.15,  # Data
    "DV": 1.10,  # Devices
    "NW": 1.05,  # Networks
    "AW": 1.10,  # Applications & Workloads
    "VA": 1.00,  # Visibility & Analytics (cross-cutting)
    "AO": 1.00,  # Automation & Orchestration (cross-cutting)
    "GV": 1.00,  # Governance (cross-cutting)
    # DoD codes
    "USR": 1.20,
    "DAT": 1.15,
    "DEV": 1.10,
    "NET": 1.05,
    "APP": 1.10,
    "VIS": 1.00,
    "AUT": 1.00,
}


@dataclass(frozen=True)
class PillarScoreResult:
    pillar_code: str
    pillar_name: str
    capability_count: int
    answered_count: int
    average_stage: float | None
    # average_stage normalized to a percentage of the framework's max level
    # (so a DoD pillar at "3" and a CISA pillar at "4" both read 100%).
    maturity_pct: float | None
    coverage_pct: float
    weakest_capability_codes: tuple[str, ...]


@dataclass(frozen=True)
class ScoreResult:
    framework: ZtFrameworkCode
    total_capabilities: int
    answered_capabilities: int
    coverage_pct: float
    average_stage: float | None
    maturity_pct: float | None
    overall_stage_label: str
    by_pillar: tuple[PillarScoreResult, ...]


@dataclass(frozen=True)
class Gap:
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    outcome: str
    current_stage: int
    target_stage: int
    gap_size: int
    priority_score: float
    notes: str | None


@dataclass(frozen=True)
class GapAnalysis:
    framework: ZtFrameworkCode
    target_stage: int
    target_label: str
    gaps: tuple[Gap, ...]
    unscored_codes: tuple[str, ...]
    total_gap_count: int
    gap_count_by_pillar: dict[str, int]


def _coverage_pct(answered: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(answered / total * 100, 1)


def _round_average(values: list[int]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _validated(stage: int | None, framework: ZtFrameworkCode) -> int | None:
    """Coerce a stored stage to a valid level for the framework, else None.

    Valid stages are 1..level_count(framework) (CISA 1-4, DoD 1-3). Anything
    out of range (including the retired DoD stage 0) is treated as unscored.
    """
    if stage is None:
        return None
    value = int(stage)
    if 1 <= value <= level_count(framework):
        return value
    return None


def _maturity_pct(avg: float | None, framework: ZtFrameworkCode) -> float | None:
    """Average stage as a percentage of the framework's top level."""
    if avg is None:
        return None
    return round(avg / level_count(framework) * 100, 1)


def _label_from_average(avg: float | None, framework: ZtFrameworkCode) -> str:
    if avg is None:
        return "Unscored"
    # Round to the nearest stage, clamped into the framework's range.
    stage = max(1, min(level_count(framework), round(avg)))
    return stage_label(stage, framework)


def _pillar_name_lookup(framework: ZtFrameworkCode) -> dict[str, str]:
    return {p.code: p.name for p in pillars(framework)}


def compute(framework: ZtFrameworkCode, answers: Mapping[str, int | None]) -> ScoreResult:
    names = _pillar_name_lookup(framework)
    pillar_results: list[PillarScoreResult] = []
    overall_values: list[int] = []
    total = 0
    answered = 0

    for p in pillars(framework):
        codes = [c.code for c in capabilities(framework) if c.pillar_code == p.code]
        pillar_total = len(codes)
        total += pillar_total

        scored_pairs: list[tuple[str, int]] = []
        for code in codes:
            s = _validated(answers.get(code), framework)
            if s is not None:
                scored_pairs.append((code, s))

        answered += len(scored_pairs)
        overall_values.extend(s for _, s in scored_pairs)

        scored_pairs.sort(key=lambda p: (p[1], p[0]))
        weakest = tuple(code for code, _ in scored_pairs[:WEAKEST_PER_PILLAR])

        pillar_avg = _round_average([s for _, s in scored_pairs])
        pillar_results.append(
            PillarScoreResult(
                pillar_code=p.code,
                pillar_name=names.get(p.code, p.code),
                capability_count=pillar_total,
                answered_count=len(scored_pairs),
                average_stage=pillar_avg,
                maturity_pct=_maturity_pct(pillar_avg, framework),
                coverage_pct=_coverage_pct(len(scored_pairs), pillar_total),
                weakest_capability_codes=weakest,
            )
        )

    avg_overall = _round_average(overall_values)
    return ScoreResult(
        framework=framework,
        total_capabilities=total,
        answered_capabilities=answered,
        coverage_pct=_coverage_pct(answered, total),
        average_stage=avg_overall,
        maturity_pct=_maturity_pct(avg_overall, framework),
        overall_stage_label=_label_from_average(avg_overall, framework),
        by_pillar=tuple(pillar_results),
    )


def _row_for(
    cap: Capability,
    current: int,
    target: int,
    notes: str | None,
    pillar_name: str,
) -> Gap:
    gap_size = max(0, target - current)
    weight = _PILLAR_WEIGHTS.get(cap.pillar_code, 1.0)
    priority = round(gap_size * weight, 2)
    return Gap(
        code=cap.code,
        pillar_code=cap.pillar_code,
        pillar_name=pillar_name,
        name=cap.name,
        outcome=cap.outcome,
        current_stage=current,
        target_stage=target,
        gap_size=gap_size,
        priority_score=priority,
        notes=notes,
    )


def resolve_target_stage(framework: ZtFrameworkCode, chosen: object) -> tuple[int, str]:
    """An engagement-level ZT target, plus WHERE IT CAME FROM.

    Returns `(stage, source)` with source one of:

      "client"               the client's stored choice, valid for this framework
      "default"              the client chose nothing; the engine default applies
      "client_out_of_range"  the stored choice is not a stage this framework has
      "client_unparseable"   the stored value is not a whole number at all

    The last two are the point of this function (#125). DoD ZTRA has three
    stages and the intake UI offers a fourth, so a stored 4 is not a target at
    all. `analyze_gaps` used to clamp it to 3 and the finalize audit row called
    that 3 the client's choice -- the false value and the false attribution of
    it side by side, in the record that exists to establish provenance.

    Absence and failure are separate states on purpose. "The client chose
    nothing" and "the client's choice could not be used" resolve to the same
    NUMBER and are not the same fact, and a caller that cannot tell them apart
    is the defect this replaces. For the same reason "could not be used because
    this framework has no such stage" is kept apart from "was never a stage
    number": the first is answerable by re-asking the client, the second means
    the stored bytes are junk and says so.

    RANGE IS JUDGED BEFORE COERCION, and the order is load-bearing rather than
    stylistic. An earlier draft ran `int(chosen)` inside the range test, so 3.9
    passed the test as 3.9 and was returned as 3 labelled "client" -- this
    function reproducing, in its own body, the exact defect it exists to end.
    `int()` is not a validator: `int(True) is 1` and `int(1.9) is 1`. So: reject
    bools, parse to a real number, judge RANGE (a 4.9 on a 1-3 ladder is more
    usefully reported as out of range than as a fraction), and only then reject
    anything not whole. `"2"` and `2.0` are accepted, because refusing a value
    the client plainly meant is the same defect facing the other way.

    This ordering, and the two reason names, are deliberately the same as the
    AI-apply path -- `_as_number` and the range check that follows it in
    `routes/zt.py` -- which had it right first.

    Never raises **for any input**, including types the annotation does not
    admit -- a stored value is data, not a programming error, and refusing to
    render an existing engagement is not an available response to it. An earlier
    draft claimed this while raising `TypeError` on a list and `ValueError` on a
    non-numeric string; `chosen` is typed `object` so the claim is now
    checkable rather than aspirational. A later one still raised `OverflowError`
    on an int too wide for a double, which is what an absolute claim costs when
    the test behind it enumerates values someone thought of rather than
    deriving them -- the parametrised sweep now covers all three arms of the
    `except`. The engine entry point `analyze_gaps`
    does raise, because by then the value has been resolved and anything out of
    range is a caller bug.
    """
    max_stage = level_count(framework)
    fallback = min(DEFAULT_TARGET_STAGE, max_stage)
    if chosen is None:
        return (fallback, "default")
    # `bool` is a subclass of `int`, so this must precede the numeric parse or a
    # stored `True` resolves to Stage 1 and gets attributed to the client.
    if isinstance(chosen, bool):
        return (fallback, "client_unparseable")
    try:
        n = float(chosen)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        # OverflowError is NOT decorative: `float(10**400)` raises it, and an
        # int wider than a double is ordinary JSON. `_as_number` in
        # `routes/zt.py` carries this same catch with a comment explaining what
        # an uncaught raise costs there; this function claimed parity with it
        # and omitted the one guard it had learned. A parity claim covers the
        # exception list too.
        return (fallback, "client_unparseable")
    if not math.isfinite(n):
        return (fallback, "client_unparseable")
    if not 1 <= n <= max_stage:
        return (fallback, "client_out_of_range")
    if n != int(n):
        return (fallback, "client_unparseable")
    return (int(n), "client")


def effective_target_stages(
    framework: ZtFrameworkCode,
    targets: Mapping[str, int | None] | None,
    target_stage: int,
) -> dict[str, int]:
    """The target actually applied to each capability: the per-capability
    override where there is a usable one, otherwise the engagement stage.

    Every capability in the framework gets an entry, so the result is a
    complete map rather than the sparse one `targets` usually is. That
    completeness is the point for `routes/clients.py::zt_dashboard`, which
    rolls these up through `compute_scores` to get a target percentage: a
    sparse map leaves `maturity_pct` None for every pillar nobody set a
    per-row target on, which is #124 -- the client read "Target maturity:
    Unscored, +0 points to target" beside a released PDF listing 37 gaps at
    Stage 4.

    EXTRACTED SO THERE IS ONE RULE, NOT TWO. This was a closure inside
    `analyze_gaps`, so the dashboard had no way to ask "what target did the
    gap engine use for this capability" except by rewriting the test --
    which is #84's shape exactly (`risk.py` re-deriving a gap comparison
    instead of calling `analyze_gaps`, and a complete call-site sweep
    reporting clean over it because a reimplementation shares the symptom
    and never the symbol). The dashboard's percentages and the deliverable's
    gap counts now cannot disagree about a target, because they read it from
    the same function rather than from two copies of the same three lines.

    `target_stage` must already be resolved -- callers take it from
    `resolve_target_stage` -- and this REFUSES an unresolved one rather than
    trusting a neighbouring call to do it. An earlier draft delegated the check
    to `analyze_gaps` on the grounds that refusing twice puts the refusal in two
    places. That was wrong in the direction that matters: `zt_dashboard` calls
    this function BEFORE `analyze_gaps`, and an out-of-range stage here yields a
    map of out-of-range values that `compute`'s `_validated` silently discards
    as unscored -- `target_pct` None and every gap 0.0, which is #124 exactly,
    reintroduced by the helper written to fix it. The protection was real and
    lived in a different call in a different file, which is the shape this repo
    keeps finding (a gate whose correctness sits in someone else's line).
    """
    max_stage = level_count(framework)
    if not (1 <= target_stage <= max_stage):
        raise ValueError(
            f"target_stage {target_stage} is out of range for {framework.value} "
            f"(valid 1-{max_stage}). Resolve a client-supplied target through "
            f"resolve_target_stage() first."
        )
    targets = targets or {}
    return {
        cap.code: _resolve_one(framework, targets.get(cap.code), target_stage)
        for cap in capabilities(framework)
    }


def capability_target_override(framework: ZtFrameworkCode, stored: object) -> int | None:
    """A stored per-capability target if it is usable, otherwise None.

    The single predicate for "does this capability override the engagement
    target" IN THIS ENGINE AND THE CLIENT DASHBOARD.
    `effective_target_stages` applies it and
    `engagement_target_capability_count` counts it, so the map and the count
    cannot disagree about any capability -- two copies of one three-line test
    is the shape that produced #84.

    STATED EXEMPTION, because an unqualified "the single predicate" would be
    false and false in the reassuring direction: `routes/risk.py` answers the
    same question inline, against a hardcoded 3
    (`r.target_stage if r.target_stage is not None else 3`), and calls nothing
    here. That IS #84 -- still open, deliberately untouched by #124, and the
    reason this docstring names a scope instead of a guarantee. Anyone changing
    the rule below has THREE consumers to consider, and the third does not
    import this module.

    DELIBERATE EXEMPTION, stated so it does not read as an oversight. An
    out-of-range PER-CAPABILITY target falls back to the engagement stage
    SILENTLY, the same shape #125 fixes one level up. It is left alone because
    naming that fault needs a counter on `GapAnalysis`, and that change is
    constrained not to alter the shape `zt/exporters.py` reads. Tracked in
    #188, which carries the expiry condition stated below.

    Not currently reachable, and the two writers are named rather than
    summarised, because an earlier draft of this comment said "no other code
    path writes `ZtAnswer.target_stage`" -- which is false, and false in the
    direction that stops a reader checking the writer they most need to see.
    Both writers bound the value first:

      routes/zt.py, `patch_answer` -- its `target_stage must be 1-` guard 422s
        on anything outside 1..level_count() for the answer's OWN framework.
      routes/zt.py, the AI-apply path -- `_as_number` plus the
        `if not 1 <= n <= max_stage` check `continue`s to a dropped-suggestion
        record, so an out-of-range suggestion is never written.

    Both bound the RANGE. Neither refuses a bool at the schema, so
    `patch_answer` writes Stage 1 for `true` -- tracked in #189, and out of
    scope here because an in-range 1 never reaches this fallback. Note
    `isinstance(True, int)` is True, so such a value would be taken as its int
    value rather than falling back; that is #189's blast radius and is
    deliberately UNCHANGED, because this extraction must not move a single gap
    count and the predicate is carried over as it stood rather than improved in
    passing.

    If a third writer appears, this exemption expires with it.
    """
    max_stage = level_count(framework)
    if isinstance(stored, int) and 1 <= stored <= max_stage:
        return stored
    return None


def _resolve_one(framework: ZtFrameworkCode, stored: object, target_stage: int) -> int:
    override = capability_target_override(framework, stored)
    return override if override is not None else target_stage


def engagement_target_capability_count(
    framework: ZtFrameworkCode, targets: Mapping[str, int | None] | None
) -> int:
    """How many capabilities take the ENGAGEMENT target because they carry no
    usable per-capability override.

    The client dashboard needs this to describe its own target honestly. Only
    Run-AI and the client's self-assessment write per-row targets, so the two
    ends of the range are both ordinary: a consultant-scored assessment
    overrides nothing and the engagement stage decides every capability, while
    a fully AI-scored one can override all of them and the engagement stage
    then decides nothing. Reporting "your target, chosen at intake" under a
    percentage that no intake choice contributed to would be #124's own defect
    -- a label that does not describe the number beside it -- pointed the other
    way.
    """
    targets = targets or {}
    return sum(
        1
        for cap in capabilities(framework)
        if capability_target_override(framework, targets.get(cap.code)) is None
    )


def analyze_gaps(
    framework: ZtFrameworkCode,
    answers: Mapping[str, int | None],
    *,
    notes: Mapping[str, str | None] | None = None,
    target_stage: int = DEFAULT_TARGET_STAGE,
    targets: Mapping[str, int | None] | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> GapAnalysis:
    """Gaps where current < target. `targets` supplies per-capability targets
    (Work Order D3); a capability with no per-capability target falls back to
    the engagement-level `target_stage`."""
    max_stage = level_count(framework)
    if not (1 <= target_stage <= max_stage):
        # REFUSE, do not clamp. This clamped to `min(DEFAULT_TARGET_STAGE,
        # max_stage)` and returned the clamped value, so a DoD engagement asked
        # for stage 4 got a GapAnalysis reading 3 with nothing recording that 4
        # was ever asked for -- and `routes/zt.py` then stamped the audit row
        # `target_stage_source: "client"` over it (#125). A silent clamp is a
        # default-value fallback on error, which core principle 2 forbids.
        #
        # Callers resolve a CLIENT-SUPPLIED target through `resolve_target_stage`
        # first, which names the fault instead of raising. Reaching here means a
        # caller passed an unresolved value, which is a programming error.
        raise ValueError(
            f"target_stage {target_stage} is out of range for {framework.value} "
            f"(valid 1-{max_stage}). Resolve a client-supplied target through "
            f"resolve_target_stage() first."
        )
    notes = notes or {}
    names = _pillar_name_lookup(framework)
    # ONE rule for "which target applies to this capability", shared with the
    # client dashboard rather than copied into it -- see
    # `effective_target_stages`, which carries the per-capability exemptions.
    resolved_targets = effective_target_stages(framework, targets, target_stage)

    rows: list[Gap] = []
    unscored: list[str] = []
    for cap in capabilities(framework):
        s = _validated(answers.get(cap.code), framework)
        if s is None:
            unscored.append(cap.code)
            continue
        cap_target = resolved_targets[cap.code]
        if s >= cap_target:
            continue
        pillar_name = names.get(cap.pillar_code, cap.pillar_code)
        rows.append(_row_for(cap, s, cap_target, notes.get(cap.code), pillar_name))

    rows.sort(key=lambda g: (-g.priority_score, g.code))

    by_pillar: dict[str, int] = {}
    for g in rows:
        by_pillar[g.pillar_code] = by_pillar.get(g.pillar_code, 0) + 1

    return GapAnalysis(
        framework=framework,
        target_stage=target_stage,
        target_label=stage_label(target_stage, framework),
        gaps=tuple(rows[:top_n]),
        unscored_codes=tuple(unscored),
        total_gap_count=len(rows),
        gap_count_by_pillar=by_pillar,
    )


@dataclass(frozen=True)
class RoadmapItem:
    month: int  # 1..horizon_months
    code: str
    pillar_code: str
    pillar_name: str
    name: str
    current_stage: int
    target_stage: int
    priority_score: float


def build_roadmap(gaps: Sequence[Gap], *, horizon_months: int = 12) -> tuple[RoadmapItem, ...]:
    """Sequence prioritized gaps across a fixed horizon (Work Order D3).

    `gaps` are assumed already ordered by descending priority (as analyze_gaps
    returns them). Identity/User and Data pillars already carry higher weight in
    the priority score, so they naturally land in earlier months. The list is
    spread evenly so each month gets roughly the same number of items.
    """
    n = len(gaps)
    if n == 0 or horizon_months <= 0:
        return ()
    per_month = max(1, math.ceil(n / horizon_months))
    return tuple(
        RoadmapItem(
            month=min(horizon_months, i // per_month + 1),
            code=g.code,
            pillar_code=g.pillar_code,
            pillar_name=g.pillar_name,
            name=g.name,
            current_stage=g.current_stage,
            target_stage=g.target_stage,
            priority_score=g.priority_score,
        )
        for i, g in enumerate(gaps)
    )


__all__ = [
    "DEFAULT_TARGET_STAGE",
    "DEFAULT_TOP_N",
    "Gap",
    "GapAnalysis",
    "PillarScoreResult",
    "RoadmapItem",
    "ScoreResult",
    "WEAKEST_PER_PILLAR",
    "analyze_gaps",
    "build_roadmap",
    "capability_target_override",
    "compute",
    "effective_target_stages",
    "engagement_target_capability_count",
    "resolve_target_stage",
]
