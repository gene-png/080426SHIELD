"""CSF IG metric cross-reference metadata (Sprint 2 / T5).

The weighted-floor roll-up (app.csf.playbook.weighted_floor_rollup) has two
rules that only fire when the caller supplies real IG-metric flags:

  - Rule 2: Primary alignment to a Core metric -> strict floor.
  - Rule 5: only LOW is lowest AND Supporting-aligned/Supplemental -> HIGH/MOD.

Before this task the csf route passed hard-coded ``False`` for every flag, so
Rules 2 and 5 could never fire. These tests prove the catalog now sources the
Core/Supplemental + Primary/Supporting classification (imported additively from
the "Reference Data" tab of the Step 2.x Working Profile XLSX toolkit) and that
feeding those flags actually activates Rules 2 and 5 - while subcategories
absent from the mapping still fall back to the safe defaults (C0 additive
pattern: older assessments roll up unchanged).

"AI suggests, code computes" - this is deterministic catalog data; no LLM.
"""

from __future__ import annotations

import pytest

from app.csf.catalog import (
    SUBCATEGORIES,
    Alignment,
    CoreClass,
    ig_metadata_for,
    is_core,
    is_core_primary,
    is_supporting_or_supplemental,
)
from app.csf.playbook import Tier, gap_priority, weighted_floor_rollup

# Known classifications sourced from the XLSX Reference Data tab.
_CORE_PRIMARY = "GV.SC-01"  # Core / Primary
_CORE_SUPPORTING = "DE.CM-02"  # Core / Supporting
_SUPPLEMENTAL_SUPPORTING = "GV.OC-02"  # Supplemental / Supporting
_SUPPLEMENTAL_PRIMARY = "GV.OC-01"  # Supplemental / Primary
_ABSENT = "ZZ.ZZ-99"  # not in the mapping (nor the catalog)


@pytest.mark.unit
def test_ig_metadata_classifies_a_core_primary_subcategory() -> None:
    meta = ig_metadata_for(_CORE_PRIMARY)
    assert meta is not None
    assert meta.core_class is CoreClass.CORE
    assert meta.alignment is Alignment.PRIMARY
    assert is_core(_CORE_PRIMARY) is True
    assert is_core_primary(_CORE_PRIMARY) is True
    # Core+Primary is neither Supporting nor Supplemental.
    assert is_supporting_or_supplemental(_CORE_PRIMARY) is False


@pytest.mark.unit
def test_rule_2_fires_for_core_primary_subcategory() -> None:
    """Core+Primary with a tier gap -> strict floor (Rule 2)."""
    assert is_core_primary(_CORE_PRIMARY) is True
    res = weighted_floor_rollup(
        {Tier.HIGH: 2, Tier.MODERATE: 4, Tier.LOW: 5},
        is_core_primary=is_core_primary(_CORE_PRIMARY),
        is_supporting_or_supplemental=is_supporting_or_supplemental(_CORE_PRIMARY),
    )
    assert res.rule == 2
    assert res.score == 2  # strict floor (lowest tier score)


@pytest.mark.unit
def test_rule_5_fires_for_supporting_subcategory() -> None:
    """Only LOW is lowest AND Supporting-aligned -> HIGH/MOD score (Rule 5)."""
    assert is_core_primary(_CORE_SUPPORTING) is False  # must NOT be Core+Primary
    assert is_supporting_or_supplemental(_CORE_SUPPORTING) is True
    res = weighted_floor_rollup(
        {Tier.HIGH: 4, Tier.MODERATE: 4, Tier.LOW: 2},
        is_core_primary=is_core_primary(_CORE_SUPPORTING),
        is_supporting_or_supplemental=is_supporting_or_supplemental(_CORE_SUPPORTING),
    )
    assert res.rule == 5
    assert res.score == 4  # the higher (HIGH/MOD) score, documented exception


@pytest.mark.unit
def test_rule_5_fires_for_supplemental_subcategory() -> None:
    """A Supplemental subcategory also satisfies the Rule 5 override branch."""
    meta = ig_metadata_for(_SUPPLEMENTAL_SUPPORTING)
    assert meta is not None and meta.core_class is CoreClass.SUPPLEMENTAL
    assert is_core(_SUPPLEMENTAL_SUPPORTING) is False
    assert is_core_primary(_SUPPLEMENTAL_SUPPORTING) is False
    assert is_supporting_or_supplemental(_SUPPLEMENTAL_SUPPORTING) is True
    res = weighted_floor_rollup(
        {Tier.HIGH: 5, Tier.LOW: 3},
        is_core_primary=is_core_primary(_SUPPLEMENTAL_SUPPORTING),
        is_supporting_or_supplemental=is_supporting_or_supplemental(_SUPPLEMENTAL_SUPPORTING),
    )
    assert res.rule == 5
    assert res.score == 5


@pytest.mark.unit
def test_supplemental_primary_triggers_rule_5_via_the_class_clause() -> None:
    """A Supplemental+Primary code satisfies Rule 5 SOLELY through the
    ``core_class is SUPPLEMENTAL`` clause of is_supporting_or_supplemental.

    GV.OC-02 (the other Supplemental fixture) is *also* Supporting, so it
    short-circuits on the alignment operand and never proves the class clause.
    GV.OC-01 is Supplemental with PRIMARY alignment: alignment is NOT Supporting,
    so True here can only come from the Supplemental class check. This guards
    the ``or core_class is SUPPLEMENTAL`` branch from silent removal.
    """
    meta = ig_metadata_for(_SUPPLEMENTAL_PRIMARY)
    assert meta is not None
    assert meta.core_class is CoreClass.SUPPLEMENTAL
    assert meta.alignment is Alignment.PRIMARY  # NOT Supporting
    # Supplemental is not Core, so despite PRIMARY alignment this is not Rule 2.
    assert is_core(_SUPPLEMENTAL_PRIMARY) is False
    assert is_core_primary(_SUPPLEMENTAL_PRIMARY) is False
    # ...yet it is still a Rule 5 override candidate via the Supplemental class.
    assert is_supporting_or_supplemental(_SUPPLEMENTAL_PRIMARY) is True
    res = weighted_floor_rollup(
        {Tier.HIGH: 5, Tier.LOW: 3},
        is_core_primary=is_core_primary(_SUPPLEMENTAL_PRIMARY),
        is_supporting_or_supplemental=is_supporting_or_supplemental(_SUPPLEMENTAL_PRIMARY),
    )
    assert res.rule == 5
    assert res.score == 5


@pytest.mark.unit
def test_absent_subcategory_falls_back_to_safe_defaults() -> None:
    """Codes absent from the mapping keep the pre-T5 safe defaults."""
    assert ig_metadata_for(_ABSENT) is None
    assert is_core(_ABSENT) is False
    assert is_core_primary(_ABSENT) is False
    assert is_supporting_or_supplemental(_ABSENT) is False
    # Same tier shape as the Rule 5 case, but with defaults it must NOT fire
    # Rule 2 or 5 - it falls through to Rule 6 (lower score + reasoning).
    res = weighted_floor_rollup(
        {Tier.HIGH: 4, Tier.MODERATE: 4, Tier.LOW: 2},
        is_core_primary=is_core_primary(_ABSENT),
        is_supporting_or_supplemental=is_supporting_or_supplemental(_ABSENT),
    )
    assert res.rule == 6
    assert res.score == 2


@pytest.mark.unit
def test_gap_priority_uses_real_core_flag() -> None:
    """gap_priority escalates for Core metrics; absent codes stay P3."""
    assert gap_priority(is_core=is_core(_CORE_PRIMARY), high_tier=True, multi_system=True) == "P1"
    assert gap_priority(is_core=is_core(_CORE_PRIMARY), high_tier=False, multi_system=False) == "P2"
    assert gap_priority(is_core=is_core(_ABSENT), high_tier=False, multi_system=False) == "P3"


@pytest.mark.unit
def test_is_core_primary_implies_is_core() -> None:
    """Invariant: every Core+Primary code is also Core."""
    for sc in SUBCATEGORIES:
        if is_core_primary(sc.code):
            assert is_core(sc.code) is True


@pytest.mark.unit
def test_mapping_covers_the_catalog_subcategories() -> None:
    """Every catalog subcategory that carries a classification resolves to a
    valid enum pair (additive: absent codes are allowed to return None)."""
    classified = [sc for sc in SUBCATEGORIES if ig_metadata_for(sc.code) is not None]
    # The XLSX Reference Data tab classifies the vast majority of the catalog;
    # guard against a regression that silently empties the mapping.
    assert len(classified) >= 100
    for sc in classified:
        meta = ig_metadata_for(sc.code)
        assert meta.core_class in CoreClass
        assert meta.alignment in Alignment
