"""The CSF Playbook's weighted-floor Enterprise roll-up, public (#474 D').

Moved unchanged from `routes/csf.py` (`_enterprise_subcategories`, `_dims`),
so the Risk Register can CALL it rather than re-derive it (Gene, #736
5984218862). The one addition is `tier_evidence_capped`, taken from the same
`score_tier` call that produces `tier_levels`.
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
from app.csf.retired import catalog_rows
from app.models.csf_assessment import CsfAssessment
from app.models.csf_profile import CsfDimensionScore
from app.schemas.csf import EnterpriseSubcategory


def dimensions_of(row: CsfDimensionScore) -> DimensionScores:
    return DimensionScores(
        governance=row.governance,
        policy=row.policy,
        implementation=row.implementation,
        monitoring=row.monitoring,
        improvement=row.improvement,
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

    out: list[EnterpriseSubcategory] = []
    for code in sorted(by_subcat):
        tier_rows = by_subcat[code]
        results = {
            tier: score_tier(dimensions_of(row), has_evidence=row.has_evidence)
            for tier, row in tier_rows.items()
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
        targets = [row.target_level for row in tier_rows.values() if row.target_level]
        target = max(targets) if targets else None
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
            )
        )
    return out, tiers_in_use
