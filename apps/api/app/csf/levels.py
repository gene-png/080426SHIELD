"""CSF Playbook maturity levels by name (W4, #736 6205956728: every level by
name, 6202644525 item 1). The bands are `csf/playbook.py::maturity_level`'s.

Read by the Playbook files (`csf/playbook_export.py`, from CSF PR (a),
#1203) and by the Risk Register's CSF finding label
(`routes/risk.py::_gather_findings`, from CSF PR (b), #1242). Both PRs add
this file identically, so whichever lands second merges it without a
conflict.

Not the only copy: the bands are also hand-typed in `playbook_export.py`'s
cover and METHODOLOGY text and, on the web, in `lib/csf/optionsCopy.ts` and
`lib/csf/editorHelp.ts`. A rename starts here and sweeps those (see #1248).
"""

from __future__ import annotations

LEVEL_NAMES: dict[int, str] = {
    1: "Ad hoc",
    2: "Developing",
    3: "Defined",
    4: "Managed",
    5: "Optimized",
}


def level_name(level: int) -> str:
    """A level's name. A level outside 1..5 is a defect upstream, so it raises
    rather than print an invented name."""
    if level not in LEVEL_NAMES:
        raise ValueError(f"CSF level {level!r} has no name")
    return LEVEL_NAMES[level]
