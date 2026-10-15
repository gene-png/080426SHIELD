"""The CSF Playbook's weighted-floor Enterprise roll-up, public (#474 D').

Moved from `routes/csf.py` (`_enterprise_subcategories`, `_dims`), so the
Risk Register can CALL it rather than re-derive it (Gene, #736 5984218862).
Two additions since the move: `tier_evidence_capped` (#474 D'), taken from
the same `score_tier` call that produces `tier_levels`; and `no_notes`
(#1000), read through `codes_with_notes`, which moved here with `has_notes`
so the live run and this roll-up keep ONE statement of "has notes".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.csf.rules import scored_tiers_only
from app.logging import get_logger
from app.models.csf_assessment import CsfAnswer, CsfAssessment
from app.models.csf_profile import CsfDimensionScore
from app.schemas.csf import EnterpriseSubcategory

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


def codes_with_notes(db: Session, a: CsfAssessment) -> set[str]:
    """The subcategory codes whose CURRENT interview answer has notes. A code
    with no answer row has none."""
    answers = db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == a.id)).scalars()
    return {ans.subcategory_code for ans in answers if has_notes(ans.notes)}


def enterprise_subcategories(
    db: Session, a: CsfAssessment
) -> tuple[list[EnterpriseSubcategory], set[str]]:
    """The weighted-floor Enterprise roll-up per in-scope subcategory.

    #852: over the catalog's rows only. A row kept on a code the catalog no
    longer has (ID.AM-09) is not rolled up, and reading it here raised KeyError
    in `subcategory_by_code` below, a 500 on the enterprise profile, the gap
    actions and the playbook export alike. `enterprise_profile` discloses it."""
    rows = catalog_rows(
        db.execute(select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id))
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

    noted = codes_with_notes(db, a)
    # #1031, ruling 3: an assessment approved before #1031 keeps its rule.
    scored_only = scored_tiers_only(a)
    out: list[EnterpriseSubcategory] = []
    for code in sorted(by_subcat):
        tier_rows = by_subcat[code]
        rolled = _scored_tiers(tier_rows) if scored_only else tier_rows
        results = {
            tier: score_tier(dimensions_of(row), has_evidence=row.has_evidence)
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
        # A subcategory none of whose tiers is scored keeps every row, level
        # and target alike, as before #1031 (#1073).
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
                no_notes=code not in noted,
                unscored_tiers=sorted(set(tier_rows) - set(results)),
                target_not_measured=target_not_measured,
            )
        )
    return out, tiers_in_use


def _scored_tiers(tier_rows: dict[str, CsfDimensionScore]) -> dict[str, CsfDimensionScore]:
    """#1031 (Gene, #736 6115464421): the tier rows the roll-up reads. A row
    nobody scored (`has_recorded_value_besides_target` False: a seed default,
    or a target alone, per ruling (a)) would score level 1 and pull a scored
    tier down. Known limit, by that predicate: an AI row scored 0 everywhere
    with nothing else written is indistinguishable from a seed row and is left
    out with it.

    When NO tier is scored every row is kept, so the subcategory still reads
    the seed rows' level 1, as before #1031. "Not measured" for that case needs
    `enterprise_level` to be None on every reader, and is #1073."""
    scored = {t: r for t, r in tier_rows.items() if has_recorded_value_besides_target(r)}
    return scored or tier_rows
