"""The per-capability target disclosures for DoD (#839), in the approved copy.

ONE derivation of the sentences, called by every surface that renders a
`GapAnalysis`: the workspace's gap endpoint, the client's dashboard and the
three deliverables. The copy is the advisor's C1 and C2 (#736, 18:56Z),
verbatim; the web renders the API's sentences and never rebuilds them.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.zt.catalog import all_codes, capabilities, capability_by_code
from app.zt.maturity import ZtFrameworkCode, level_count, stage_label
from app.zt.scoring import GapAnalysis, capability_max_stage

#: The typed reason for a stage above the capability's own maximum (#839, F1).
STAGE_ABOVE_CAPABILITY_MAX = "stage_above_capability_max"


def max_stage_for(framework: ZtFrameworkCode, code: str) -> int:
    """The highest stage this capability may be stored at, for every write path.

    The capability's own maximum (`capability_max_stage`) when the catalog has
    the row. A retired row the catalog no longer has (kept by 0063/0064, not
    scored) is held only to the framework's ladder, as before.

    #867 extracts `_validated_stage(raw, max_stage)` in `routes/zt.py`.
    Whichever of #839 and #867 merges second passes this function's value as
    that `max_stage`.
    """
    if code not in all_codes(framework):
        return level_count(framework)
    return capability_max_stage(framework, capability_by_code(code))


def stages_above_capability_max(
    framework: ZtFrameworkCode, answers: Mapping[str, int | None]
) -> tuple[str, ...]:
    """Catalog rows whose STORED maturity stage is above their own maximum, in
    catalog order (#839, F1).

    The write paths refuse such a stage now, so these rows predate the guard.
    They are left as stored and counted at the maximum (`scoring._validated`
    callers clamp them), and this is what their disclosure reads. A retired row
    is not here: it is not scored at all, and `zt/retired.py` discloses it. A
    stage outside the framework's ladder is not here either: the engine already
    treats it as unscored."""
    out = []
    for cap in capabilities(framework):
        stage = answers.get(cap.code)
        if stage is None or not 1 <= stage <= level_count(framework):
            continue
        if stage > capability_max_stage(framework, cap):
            out.append(cap.code)
    return tuple(out)


def stage_above_max_sentences(
    framework: ZtFrameworkCode, answers: Mapping[str, int | None]
) -> list[str]:
    """S1, approved verbatim (#736 comment 6049667540), one per row that
    `stages_above_capability_max` finds, in catalog order. ONE derivation for
    every surface: the workspace gap endpoint, the client dashboard and the
    three files. Empty when every stored stage is reachable."""
    out = []
    for code in stages_above_capability_max(framework, answers):
        cap = capability_by_code(code)
        stored = int(answers[code])  # type: ignore[arg-type]  # found non-None above
        top = capability_max_stage(framework, cap)
        out.append(
            f"{cap.dod_number} {cap.name} is recorded at stage {stored}, but it has no "
            f"DoD {stage_label(stored, framework)} activities, so every figure here "
            f"counts it as {stage_label(top, framework)} ({top})."
        )
    return out


def stage_above_max_message(framework: ZtFrameworkCode, code: str, stage: int) -> str | None:
    """The approved refusal (#736 comment 6048561596), or None when `stage` is
    within this capability's maximum. Only a catalog row can be over its own
    maximum, so `code` is in the catalog whenever this returns a sentence."""
    if stage <= max_stage_for(framework, code):
        return None
    cap = capability_by_code(code)
    level = stage_label(stage, framework)
    return (
        f"{cap.dod_number} {cap.name} has no DoD {level} activities, "
        f"so it cannot be scored {stage}."
    )


def target_cap_sentences(gap: GapAnalysis) -> list[str]:
    """C1 for each capped capability, then C2 for each capability with no
    Target level, in catalog order."""
    out = []
    for code in gap.capped_target_codes:
        cap = capability_by_code(code)
        out.append(
            f"{cap.dod_number} {cap.name} has no DoD Advanced activities, "
            "so its target is Target (2)."
        )
    for code in gap.no_target_level_codes:
        cap = capability_by_code(code)
        out.append(
            f"{cap.dod_number} {cap.name} has no DoD Target activities, "
            "so it moves from Below Target straight to Advanced."
        )
    return out
