"""Zero Trust maturity scales.

The two frameworks use different-length ladders (Work Order A4):

CISA ZTMM 2.0 — 4 levels:  Traditional (1) -> Initial (2) -> Advanced (3) -> Optimal (4)
DoD ZTRA      — 3 levels:  Not Started (1) -> Target (2) -> Advanced (3)

A capability's stored `maturity_stage` is an integer in 1..level_count(framework).
`level_count` lets the scoring engine normalize per framework so a DoD "3" and a
CISA "4" are both the top of their scale. Labels are picked by framework at
render time via `stage_label`; `stage_definitions` returns the framework's ladder
so the catalog only ever offers stages that exist for that framework.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class ZtFrameworkCode(enum.StrEnum):
    CISA_ZTMM_2_0 = "cisa_ztmm_2_0"
    DOD_ZTRA = "dod_ztra"


class MaturityStage(enum.IntEnum):
    STAGE_1 = 1
    STAGE_2 = 2
    STAGE_3 = 3
    STAGE_4 = 4


@dataclass(frozen=True)
class StageDefinition:
    stage: int
    label: str
    description: str


CISA_STAGES: tuple[StageDefinition, ...] = (
    StageDefinition(
        1,
        "Traditional",
        "Manual, perimeter-centric controls. Limited automation; static trust decisions.",
    ),
    StageDefinition(
        2,
        "Initial",
        "Starting Zero Trust adoption. Inventory and identity verified but trust is "
        "still mostly implicit after auth.",
    ),
    StageDefinition(
        3,
        "Advanced",
        "Cross-pillar coordination; risk-adaptive access decisions; automated response "
        "to a defined set of conditions.",
    ),
    StageDefinition(
        4,
        "Optimal",
        "Fully automated, continuously evaluated trust. Just-in-time access. Self-healing "
        "controls informed by analytics.",
    ),
)


DOD_STAGES: tuple[StageDefinition, ...] = (
    StageDefinition(
        1,
        "Not Started",
        "Foundational hygiene only — no formal Zero Trust activity adopted yet for this "
        "capability.",
    ),
    StageDefinition(
        2,
        "Target",
        "Target-phase (FY27) capability in place: the foundational Zero Trust activities "
        "are implemented.",
    ),
    StageDefinition(
        3,
        "Advanced",
        "Advanced-phase capability: mature, integrated, and continuously adaptive.",
    ),
)


def stage_definitions(framework: ZtFrameworkCode) -> tuple[StageDefinition, ...]:
    """Framework-appropriate maturity ladder (CISA: 4 stages, DoD: 3 stages)."""
    if framework == ZtFrameworkCode.DOD_ZTRA:
        return DOD_STAGES
    return CISA_STAGES


def level_count(framework: ZtFrameworkCode) -> int:
    """Number of maturity levels for the framework (CISA 4, DoD 3)."""
    return len(stage_definitions(framework))


def stage_label(stage: MaturityStage | int | None, framework: ZtFrameworkCode) -> str:
    if stage is None:
        return "Unscored"
    value = int(stage)
    for d in stage_definitions(framework):
        if d.stage == value:
            return d.label
    return "Unknown"
