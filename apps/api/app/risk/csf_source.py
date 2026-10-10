"""The Risk Register's statement of where its CSF risks come from (#474 D').

Gene (#736 5984256202): CSF Risk findings come from Kentro's evidence-based
Playbook assessment, while the client's CSF dashboard keeps showing the
self-assessment, so every surface showing Risk's CSF findings says so, and
only when the register has CSF findings. ONE builder for the consultant's
register, the client's Risk dashboard and the three exports.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.csf.retired import has_recorded_value_besides_target
from app.logging import get_logger

_log = get_logger(__name__)

#: The provenance key, written by `routes/risk.py::generate`.
CSF_FINDINGS_KEY = "csf_findings"

#: Approved verbatim, #736 comment 5984256202.
CSF_SOURCE_NOTE = (
    "CSF risks in this register come from Kentro's evidence-based assessment. "
    "They can differ from your self-assessment on the CSF dashboard."
)


def csf_source_note(stored: object) -> str | None:
    """The note when the register recorded at least one CSF finding; None when
    it recorded none, or predates the record (silent: no claim either way)."""
    if not isinstance(stored, dict) or CSF_FINDINGS_KEY not in stored:
        return None
    raw = stored[CSF_FINDINGS_KEY]
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return CSF_SOURCE_NOTE if raw > 0 else None
    _log.error("risk.csf_source.unreadable", got=type(raw).__name__)
    return None


@dataclass(frozen=True)
class CsfPlaybookMeasure:
    """What a CSF source's Playbook measured (#474 D', R10, #736 6102665946).

    `state`: `measured`, `no_targets` or `no_scores` (below). `finding_codes`:
    the subcategories that may raise a finding. `unscored_targeted`: in the
    `measured` state, how many targeted subcategories have no tier row that is
    both scored and targeted, so raise no finding; 0 in the other two states,
    whose own line already says nothing was measured."""

    state: str
    finding_codes: frozenset[str]
    unscored_targeted: int


def scored_and_targeted(row: Any) -> bool:
    """R10: ONE tier row carrying BOTH a recorded value other than its target
    (`csf/retired.py::has_recorded_value_besides_target`, CALLED) AND a
    target. Per ROW, never per subcategory: a Playbook row is one tier, so a
    score on HIGH beside a target on MODERATE measured nothing against it."""
    return has_recorded_value_besides_target(row) and row.target_level is not None


def csf_playbook_measure(rows: Iterable[Any]) -> CsfPlaybookMeasure:
    """#474 D' (advisor, #736 6087786886 item 4, 6090360421; R10, 6102665946):
    what a CSF source's Playbook could measure, over its catalog rows. The ONE
    reader for the register's state, its CSF findings, its disclosed count and
    the Inputs panel's flag (`routes/risk.py`), so they cannot disagree.

    - `measured`: at least one in-scope tier row is scored AND targeted
      (`scored_and_targeted`). Only such codes raise a finding; the level is
      still the Enterprise roll-up's, and `is_gap` decides.
    - `no_targets`: a value is recorded, but no in-scope row has a target, so
      `is_gap` can raise nothing;
    - `no_scores`: otherwise. No in-scope row has a recorded value other than
      a target (no rows at all, or targets only), OR scores and targets exist
      but never on the same row (R10: nothing was measured against a target).

    Citability (`link_scope.csf_playbook_scope`) calls the WIDER
    `has_recorded_score`, which also counts a target, so a target-only code
    stays citable while raising no finding."""
    in_scope = [r for r in rows if r.in_scope]
    finding_codes = frozenset(r.subcategory_code for r in in_scope if scored_and_targeted(r))
    targeted = {r.subcategory_code for r in in_scope if r.target_level is not None}
    if finding_codes:
        return CsfPlaybookMeasure("measured", finding_codes, len(targeted - finding_codes))
    if any(has_recorded_value_besides_target(r) for r in in_scope) and not targeted:
        return CsfPlaybookMeasure("no_targets", frozenset(), 0)
    return CsfPlaybookMeasure("no_scores", frozenset(), 0)


#: R10 (#736 6102665946): the provenance key holding the `measured` CSF
#: source's `unscored_targeted`, written by `routes/risk.py::generate` and
#: read back by `csf_unscored_targets_note` for the three files.
CSF_UNSCORED_TARGETS_KEY = "csf_unscored_targets"


def csf_unscored_targets_sentence(n: int) -> str | None:
    """Approved verbatim, #736 6102665946 (R10). None when n is 0."""
    if n == 1:
        return "1 targeted subcategory has no recorded scores and raises no finding."
    if n > 1:
        return f"{n} targeted subcategories have no recorded scores and raise no finding."
    return None


def csf_unscored_targets_note(stored: object) -> str | None:
    """The R10 count sentence from a register's provenance. None when the key
    is absent (a register generated before R10: no claim either way) or 0;
    an unreadable value is logged and reads None."""
    if not isinstance(stored, dict) or CSF_UNSCORED_TARGETS_KEY not in stored:
        return None
    raw = stored[CSF_UNSCORED_TARGETS_KEY]
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0:
        return csf_unscored_targets_sentence(raw)
    _log.error("risk.csf_unscored_targets.unreadable", got=type(raw).__name__)
    return None
