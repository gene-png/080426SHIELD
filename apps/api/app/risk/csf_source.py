"""The Risk Register's statement of where its CSF risks come from (#474 D').

Gene (#736 5984256202): CSF Risk findings come from Kentro's evidence-based
Playbook assessment, while the client's CSF dashboard keeps showing the
self-assessment, so every surface showing Risk's CSF findings says so, and
only when the register has CSF findings. ONE builder for the consultant's
register, the client's Risk dashboard and the three exports.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.csf.retired import has_recorded_score
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


def csf_playbook_state(rows: Iterable[object]) -> str:
    """#474 D' (advisor, #736 6087786886, item 4): what a CSF source's Playbook
    could measure, over its catalog rows.

    - `no_scores`: no in-scope row has a recorded score
      (`csf/retired.py::has_recorded_score`, CALLED), including no rows at all;
    - `no_targets`: rows are recorded, but no in-scope row has a target level,
      so `is_gap` can raise nothing;
    - `measured`: otherwise.

    The same predicate decides which codes are citable
    (`link_scope.csf_playbook_scope`), so a register cannot say "no scores"
    while citing a scored code."""
    in_scope = [r for r in rows if r.in_scope]
    if not any(has_recorded_score(r) for r in in_scope):
        return "no_scores"
    if all(r.target_level is None for r in in_scope):
        return "no_targets"
    return "measured"
