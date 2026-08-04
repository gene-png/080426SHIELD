"""NIST CSF 2.0 maturity tiers.

CSF 2.0 retained the four-tier maturity model from CSF 1.1:
  Tier 1 (Partial)        - ad hoc, reactive practices
  Tier 2 (Risk Informed)  - risk awareness exists but not org-wide
  Tier 3 (Repeatable)     - formal, organization-wide policies
  Tier 4 (Adaptive)       - continuous improvement driven by lessons learned

Tiers are an org-level maturity statement in NIST's text, but in
practice assessors score per-subcategory and roll up. We adopt the
per-subcategory convention because it produces actionable gap output.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class MaturityTier(enum.IntEnum):
    PARTIAL = 1
    RISK_INFORMED = 2
    REPEATABLE = 3
    ADAPTIVE = 4


@dataclass(frozen=True)
class TierDefinition:
    tier: MaturityTier
    short_label: str
    description: str


TIER_DEFINITIONS: tuple[TierDefinition, ...] = (
    TierDefinition(
        tier=MaturityTier.PARTIAL,
        short_label="Partial",
        description=(
            "Risk management practices are ad hoc and reactive. Cybersecurity "
            "activities depend on individuals; there is limited awareness at "
            "the organizational level."
        ),
    ),
    TierDefinition(
        tier=MaturityTier.RISK_INFORMED,
        short_label="Risk Informed",
        description=(
            "Risk-management practices are approved by management but may not "
            "be established as organization-wide policy. Awareness exists but "
            "is not consistently shared."
        ),
    ),
    TierDefinition(
        tier=MaturityTier.REPEATABLE,
        short_label="Repeatable",
        description=(
            "Formal policies define cybersecurity practices that are regularly "
            "updated. Risk-informed methods are applied organization-wide. "
            "Information is shared with internal stakeholders."
        ),
    ),
    TierDefinition(
        tier=MaturityTier.ADAPTIVE,
        short_label="Adaptive",
        description=(
            "Practices adapt based on lessons learned, predictive indicators, "
            "and continuous improvement. Cybersecurity is part of the "
            "organizational culture and informs supplier and partner choices."
        ),
    ),
)


def tier_label(tier: MaturityTier | int | None) -> str:
    if tier is None:
        return "Unscored"
    value = int(tier)
    for d in TIER_DEFINITIONS:
        if int(d.tier) == value:
            return d.short_label
    return "Unknown"
