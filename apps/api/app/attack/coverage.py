"""ATT&CK coverage status enum + label helpers."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CoverageStatus(enum.StrEnum):
    """Per-technique defensive coverage status."""

    COVERED = "covered"
    PARTIAL = "partial"
    GAP = "gap"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class CoverageDefinition:
    status: CoverageStatus
    short_label: str
    description: str


COVERAGE_DEFINITIONS: tuple[CoverageDefinition, ...] = (
    CoverageDefinition(
        status=CoverageStatus.COVERED,
        short_label="Covered",
        description=(
            "Detection + response controls are in place for this technique "
            "across the relevant attack surface."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.PARTIAL,
        short_label="Partial",
        description=(
            "Controls exist but cover only part of the attack surface, or "
            "rely on signals with known blind spots."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.GAP,
        short_label="Gap",
        description=(
            "No reliable detection or response capability today. Treat as "
            "a remediation priority."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.NOT_APPLICABLE,
        short_label="N/A",
        description=(
            "Technique is not applicable to this environment (no exposed "
            "attack surface for this behavior)."
        ),
    ),
)


def coverage_label(value: CoverageStatus | str | None) -> str:
    if value is None:
        return "Unscored"
    target = value if isinstance(value, CoverageStatus) else CoverageStatus(value)
    for d in COVERAGE_DEFINITIONS:
        if d.status == target:
            return d.short_label
    return "Unknown"
