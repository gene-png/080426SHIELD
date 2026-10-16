"""The CSF Playbook's weighted-floor Enterprise roll-up, public (#474 D').

Moved from `routes/csf.py` (`_enterprise_subcategories`, `_dims`), so the
Risk Register can CALL it rather than re-derive it (Gene, #736 5984218862).
Two additions since the move: `tier_evidence_capped` (#474 D'), taken from
the same `score_tier` call that produces `tier_levels`; and `no_notes`
(#1000), read through `codes_with_notes`, which moved here with `has_notes`
so the live run and this roll-up keep ONE statement of "has notes".

Options 1 and 3 (Gene, #736 6200638511, 6201691989): under the current rules
a subcategory with no scored tier gets no level (#1073), and the evidence cap
applies only to a frozen assessment (`csf/rules.py`). `coverage` states the C3
counts over the same rows.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, undefer_group

from app.csf.catalog import (
    is_core,
    is_core_primary,
    is_supporting_or_supplemental,
    subcategory_by_code,
)
from app.csf.playbook import (
    DimensionScores,
    Tier,
    gap_priority,
    is_gap,
    score_tier,
    weighted_floor_rollup,
)
from app.csf.retired import catalog_rows, has_recorded_value_besides_target
from app.csf.rules import evidence_cap_applies, scored_tiers_only, unscored_has_no_level
from app.logging import get_logger
from app.models.csf_assessment import CsfAnswer, CsfAssessment
from app.models.csf_profile import (
    EVIDENCE_STATUS_GROUP,
    CsfDimensionScore,
    CsfEvidenceStatus,
)
from app.schemas.csf import CsfCoverage, EnterpriseSubcategory

_log = get_logger(__name__)


def dimensions_of(row: CsfDimensionScore) -> DimensionScores:
    return DimensionScores(
        governance=row.governance,
        policy=row.policy,
        implementation=row.implementation,
        monitoring=row.monitoring,
        improvement=row.improvement,
    )


def has_notes(notes: str | None) -> bool:
    """#1000: ONE statement of "this answer has notes", read by the live run
    and the Enterprise table alike. Blank or whitespace-only is no notes."""
    return bool(notes and notes.strip())


def _answers(db: Session, a: CsfAssessment) -> dict[str, CsfAnswer]:
    rows = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars()
    return {ans.subcategory_code: ans for ans in rows}


def codes_with_notes(db: Session, a: CsfAssessment) -> set[str]:
    """The subcategory codes whose CURRENT interview answer has notes. A code
    with no answer row has none."""
    return {code for code, ans in _answers(db, a).items() if has_notes(ans.notes)}


def coverage(rows: list[EnterpriseSubcategory]) -> CsfCoverage:
    """The C3 counts (#736 6201620727 item 2; the fourth, `notes_not_scored`,
    is the advisor's Q-A recommendation in 6205425122 item 3) and the E3
    evidence counts, over the rolled-up in-scope subcategories.

    Each count is its OWN predicate, never a remainder, so the test that the
    four C3 counts add up to `total` can fail. A subcategory not scored is,
    in this order: `notes_not_scored` when its current answer has notes,
    `self_reported` when only the client's rating is recorded, and
    `not_answered` when neither is."""
    scored = [r for r in rows if r.scored]
    evidence = [_evidence_class(r) for r in scored]
    return CsfCoverage(
        total=len(rows),
        scored=len(scored),
        notes_not_scored=sum(1 for r in rows if not r.scored and not r.no_notes),
        self_reported=sum(
            1 for r in rows if not r.scored and r.no_notes and r.self_rating is not None
        ),
        not_answered=sum(1 for r in rows if not r.scored and r.no_notes and r.self_rating is None),
        evidence_on_file=evidence.count(CsfEvidenceStatus.ON_FILE.value),
        evidence_confirmed=evidence.count(CsfEvidenceStatus.CONFIRMED_IN_DISCUSSION.value),
        evidence_neither=evidence.count(CsfEvidenceStatus.NEITHER.value),
        evidence_mixed=evidence.count(_MIXED),
        notional=sum(1 for r in scored if _notional(r)),
    )


#: E3 (6205425122 item 3): a scored subcategory whose scored tiers do not all
#: carry the same evidence value. Its own count, never folded into another.
_MIXED = "mixed"


def _evidence_class(r: EnterpriseSubcategory) -> str:
    """One evidence value for a scored subcategory: the value every rolled-up
    tier carries, or `mixed` when they differ."""
    values = set(r.tier_evidence.values())
    if len(values) == 1:
        return values.pop()
    if not values:
        # A scored subcategory rolls up at least one tier by construction.
        raise ValueError(f"scored subcategory {r.subcategory_code} has no tier evidence")
    return _MIXED


#: E2: a level at or above Managed (4) with `neither` is notional.
NOTIONAL_FROM_LEVEL = 4


def _notional(r: EnterpriseSubcategory) -> bool:
    """E2 at subcategory level: the Enterprise level is Managed or Optimized
    and at least one rolled-up tier has `neither`. "At least one", not
    "every": a level resting partly on a tier nobody validated is not
    reported as validated (missing evidence reads as unconfirmed)."""
    return (r.enterprise_level or 0) >= NOTIONAL_FROM_LEVEL and (
        CsfEvidenceStatus.NEITHER.value in r.tier_evidence.values()
    )


def enterprise_subcategories(
    db: Session, a: CsfAssessment
) -> tuple[list[EnterpriseSubcategory], set[str]]:
    """The weighted-floor Enterprise roll-up per in-scope subcategory.

    #852: over the catalog's rows only. A row kept on a code the catalog no
    longer has (ID.AM-09) is not rolled up, and reading it here raised KeyError
    in `subcategory_by_code` below, a 500 on the enterprise profile, the gap
    actions and the playbook export alike. `enterprise_profile` discloses it."""
    rows = catalog_rows(
        db.execute(
            select(CsfDimensionScore)
            .where(CsfDimensionScore.assessment_id == a.id)
            .options(undefer_group(EVIDENCE_STATUS_GROUP))
        )
        .scalars()
        .all()
    )
    by_subcat: dict[str, dict[str, CsfDimensionScore]] = {}
    tiers_in_use: set[str] = set()
    for r in rows:
        if not r.in_scope:
            continue
        by_subcat.setdefault(r.subcategory_code, {})[r.tier] = r
        tiers_in_use.add(r.tier)

    answers = _answers(db, a)
    noted = {code for code, ans in answers.items() if has_notes(ans.notes)}
    # #1031, ruling 3, and Options 1 and 3 (Q2): a frozen assessment keeps the
    # rules it was approved under.
    scored_only = scored_tiers_only(a)
    cap = evidence_cap_applies(a)
    no_level = unscored_has_no_level(a)
    out: list[EnterpriseSubcategory] = []
    for code in sorted(by_subcat):
        tier_rows = by_subcat[code]
        scored = _scored_tiers(tier_rows)
        answer = answers.get(code)
        self_rating = answer.maturity_tier if answer is not None else None
        if not scored and no_level:
            out.append(_not_scored(code, tier_rows, self_rating, no_notes=code not in noted))
            continue
        # #1031: when NO tier is scored a frozen assessment keeps every row, so
        # the subcategory reads the seed rows' level 1, as it was delivered.
        rolled = (scored or tier_rows) if scored_only else tier_rows
        results = {
            tier: score_tier(dimensions_of(row), has_evidence=row.has_evidence, cap=cap)
            for tier, row in rolled.items()
        }
        tier_levels = {tier: r.level for tier, r in results.items()}
        rollup = weighted_floor_rollup(
            {Tier(t): lvl for t, lvl in tier_levels.items()},
            # Real IG Core/Supporting classification from the catalog (T5).
            # Absent subcategories return safe defaults, keeping older
            # assessments on rules 1/3/4/6 unchanged (C0 additive pattern).
            is_core_primary=is_core_primary(code),
            is_supporting_or_supplemental=is_supporting_or_supplemental(code),
        )
        # #1031, ruling 2 (a): the target comes from the rows that roll up,
        # so under the new rule a gap is measured against what was assessed.
        # A target that sits only on unscored tiers beside a scored one is
        # not counted, and is disclosed as "Not measured" (#736 6127667643).
        target_rows = list(rolled.values())
        targets = [row.target_level for row in target_rows if row.target_level]
        target = max(targets) if targets else None
        target_not_measured = target is None and any(
            row.target_level for t, row in tier_rows.items() if t not in rolled
        )
        gap = is_gap(rollup.score, target) if target is not None else False
        priority = (
            gap_priority(
                is_core=is_core(code),
                high_tier=Tier.HIGH.value in tier_rows,
                multi_system=len(tier_rows) > 1,
            )
            if gap
            else None
        )
        sc = subcategory_by_code(code)
        _log.debug(
            "csf.enterprise.rolled_up",
            subcategory_code=code,
            scored_only=scored_only,
            capped_rules=cap,
            tiers_rolled_up=sorted(results),
            tiers_unscored=sorted(set(tier_rows) - set(results)),
        )
        out.append(
            EnterpriseSubcategory(
                subcategory_code=code,
                name=getattr(sc, "name", code),
                function=str(getattr(sc, "function", "")),
                tier_levels=tier_levels,
                tier_evidence_capped={t: r.evidence_capped for t, r in results.items()},
                enterprise_level=rollup.score,
                rollup_rule=rollup.rule,
                target_level=target,
                gap=gap,
                priority=priority,
                scored=bool(scored),
                self_rating=self_rating,
                tier_evidence={t: rolled[t].evidence_status.value for t in results},
                no_notes=code not in noted,
                unscored_tiers=sorted(set(tier_rows) - set(results)),
                target_not_measured=target_not_measured,
            )
        )
    return out, tiers_in_use


def _scored_tiers(tier_rows: dict[str, CsfDimensionScore]) -> dict[str, CsfDimensionScore]:
    """#1031 (Gene, #736 6115464421): the tier rows somebody scored. A row
    nobody scored (`has_recorded_value_besides_target` False: a seed default,
    or a target alone, per ruling (a)) would score level 1 and pull a scored
    tier down. Known limit, by that predicate: an AI row scored 0 everywhere
    with nothing else written is indistinguishable from a seed row and is left
    out with it.

    Empty when NO tier is scored: the caller decides, by rule, whether that
    subcategory has no level (#1073) or keeps every row (frozen)."""
    return {t: r for t, r in tier_rows.items() if has_recorded_value_besides_target(r)}


def _not_scored(
    code: str,
    tier_rows: dict[str, CsfDimensionScore],
    self_rating: int | None,
    *,
    no_notes: bool,
) -> EnterpriseSubcategory:
    """A subcategory with no scored in-scope tier, under the current rules
    (Option 1, #1073): no level, no roll-up rule, no target and no gap. A
    target set on one of its tiers was measured against nothing, and says so
    (`target_not_measured`), as #1031 does for a target on an unscored tier
    beside a scored one."""
    sc = subcategory_by_code(code)
    _log.debug(
        "csf.enterprise.not_scored", subcategory_code=code, self_rated=self_rating is not None
    )
    return EnterpriseSubcategory(
        subcategory_code=code,
        name=getattr(sc, "name", code),
        function=str(getattr(sc, "function", "")),
        tier_levels={},
        enterprise_level=None,
        rollup_rule=None,
        target_level=None,
        gap=False,
        priority=None,
        scored=False,
        self_rating=self_rating,
        tier_evidence={},
        no_notes=no_notes,
        unscored_tiers=[],
        target_not_measured=any(row.target_level for row in tier_rows.values()),
    )
