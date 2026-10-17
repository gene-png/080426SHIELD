"""The Risk Register's statement of ZT targets whose origin is not recorded
(#1343, the register third; the deliverable and the ZT dashboard are the other
two).

#982 records who set a per-capability ZT target; a NULL origin means it was
stored before migration 0076, and some of those were set by earlier AI runs.
Synthesis compares each capability with that target (`routes/risk.py`), so a
finding can rest on a target nobody chose. `generate` records, per ZT source,
the codes of the capabilities whose applied target is such a target (with a
finding or without one), in
`risk_registers.provenance["unrecorded_target_codes"]` (a sibling key, as #915's
`capped_target_codes` is). This module is the ONE reader of that record and
the ONE place the lines are built, called by the consultant's register
response, the client's Risk dashboard and the three Risk exports, so the
surfaces cannot disagree about one register.

The sentence is approved verbatim at #736 comment 6220094031 item 5, in the
form `{code}: <sentence>` approved at 6225462107.
"""

from __future__ import annotations

from app.logging import get_logger
from app.zt.target_origin import TARGET_ORIGIN_NOT_RECORDED

_log = get_logger(__name__)

#: The provenance key, written by `routes/risk.py::generate`.
UNRECORDED_TARGET_KEY = "unrecorded_target_codes"


def unrecorded_target_codes(stored: object) -> dict[str, list[str]] | None:
    """Per ZT source, the capability codes whose applied target has no recorded origin;
    None when the register records nothing.

    Three states, kept apart as #915's reader keeps them: NO KEY is a register
    generated before this was recorded, and is silent; a READABLE record is the
    answer, including an empty list ("none"); an UNREADABLE one is "could not
    look", returned as None and logged loudly, never as a clean result. No
    current writer produces the third, so the check is a ratchet against a
    hand-edited blob.
    """
    if not isinstance(stored, dict) or UNRECORDED_TARGET_KEY not in stored:
        return None
    raw = stored[UNRECORDED_TARGET_KEY]
    if isinstance(raw, dict) and all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(c, str) for c in v)
        for k, v in raw.items()
    ):
        return {k: list(v) for k, v in raw.items()}
    _log.error(
        "risk.zt_target_origin.unreadable",
        got=type(raw).__name__,
        reason="unrecorded_target_codes is not a mapping of source to a list of codes",
    )
    return None


def unrecorded_target_lines(codes: dict[str, list[str]] | None) -> list[str]:
    """`{code}: <sentence>`, one line per code, in recorded order (each code
    once); empty when nothing was recorded or nothing is unrecorded."""
    if not codes:
        return []
    seen: list[str] = []
    for source_codes in codes.values():
        for code in source_codes:
            if code not in seen:
                seen.append(code)
    return [f"{code}: {TARGET_ORIGIN_NOT_RECORDED}" for code in seen]
