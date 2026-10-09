"""The Risk Register's statement of where its CSF risks come from (#474 D').

Gene (#736 5984256202): CSF Risk findings come from Kentro's evidence-based
Playbook assessment, while the client's CSF dashboard keeps showing the
self-assessment, so every surface showing Risk's CSF findings says so, and
only when the register has CSF findings. ONE builder for the consultant's
register, the client's Risk dashboard and the three exports.
"""

from __future__ import annotations

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
