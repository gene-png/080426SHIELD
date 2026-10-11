"""The Risk Register's statement of the DoD target cap (#915, S3).

Gene's ruling on #839 was "cap and say so": a DoD capability with no Advanced
activities has its target lowered to Target (2), and every surface the cap
reaches says so (#736 comment 6048561596). The Risk Register is one, because
synthesis compares each capability against the capped target
(`routes/risk.py`), so a capability at stage 2 is no finding there either.

`generate` records, per ZT source, the capabilities whose target the cap
lowered, in `risk_registers.provenance["capped_target_codes"]` (a sibling key,
so the pinned key sets of `targets` are unchanged). This module is the ONE
reader of that record and the ONE place the approved sentence is built, called
by the consultant's register response, the client's Risk dashboard and the
three Risk exports, so the surfaces cannot disagree about one register.

The copy is S3, approved verbatim, singular and plural, at #736 comment
6049667540.
"""

from __future__ import annotations

from app.logging import get_logger

_log = get_logger(__name__)

#: The provenance key, written by `routes/risk.py::generate`.
CAPPED_TARGET_KEY = "capped_target_codes"


def capped_target_codes(stored: object) -> dict[str, list[str]] | None:
    """Per ZT source, the codes whose target the cap lowered; None when the
    register records nothing.

    Three states, kept apart: NO KEY is a register generated before this was
    recorded, and is silent, because every such register is in it; a READABLE
    record is the answer, including an empty list ("the cap lowered nothing");
    an UNREADABLE one is "could not look", returned as None and logged loudly,
    never as a clean result. No current writer produces the third (`generate`
    writes a dict of lists of codes), so the check is a ratchet against a
    hand-edited blob.
    """
    if not isinstance(stored, dict) or CAPPED_TARGET_KEY not in stored:
        return None
    raw = stored[CAPPED_TARGET_KEY]
    if isinstance(raw, dict) and all(
        isinstance(k, str) and isinstance(v, list) and all(isinstance(c, str) for c in v)
        for k, v in raw.items()
    ):
        return {k: list(v) for k, v in raw.items()}
    _log.error(
        "risk.zt_capped.unreadable",
        got=type(raw).__name__,
        reason="capped_target_codes is not a mapping of source to a list of codes",
    )
    return None


def capped_target_sentence(codes: dict[str, list[str]] | None) -> str | None:
    """S3, singular or plural; None when nothing was recorded or nothing was
    lowered, so a register that predates the record prints no claim.

    Counts every recorded code. Only DoD capabilities can be lowered: a CISA
    capability defines every stage of its ladder, so `capability_max_stage`
    never sits below a CISA target, and the sentence names the DoD assessment.
    """
    if not codes:
        return None
    n = sum(len(v) for v in codes.values())
    if n == 0:
        return None
    if n == 1:
        return (
            "In the DoD Zero Trust assessment, 1 capability has no DoD Advanced "
            "activities, so its target is Target (2): it is a finding only below "
            "Target. The Zero Trust deliverable names it."
        )
    return (
        f"In the DoD Zero Trust assessment, {n} capabilities have no DoD Advanced "
        "activities, so their target is Target (2): each is a finding only below "
        "Target. The Zero Trust deliverable names them."
    )
