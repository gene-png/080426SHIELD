"""Why a technique is Partial, in the client's words (#554, slice R1).

Gene's H3 comment on #554 (2026-09-24): "405 techniques are Partial" is
unusable to a client without a reason. The seven Partial reason codes live in
`coverage.py` with definitions written for the model and the consultant; this
module holds what the CLIENT reads for each, plus the two states a Partial can
be in without one of the seven:

  * REASON NOT RECORDED -- a Partial with no reason. Only an assessment
    approved before #620 can hold one: under #620's rules approve refuses a
    reasonless Partial (`release_readiness.py`).
  * SET BY ITS SUB-TECHNIQUES -- a COMPUTED parent's Partial (D-094). Its
    reason is None by design, because its status is its children's; "Reason
    not recorded" would be false of it. It says only that the coverage is
    computed, never how the children compare: `computed_parent_status` returns
    Partial for children that are mixed, all Partial, or one Partial beside
    N/A siblings, and a wording that described the children was false for the
    last two (#798 review; the advisor's ruling on #736, 2026-10-02 18:34Z).

The wording is the text Gene's advisor approved as written on 2026-10-02
(condition 6): the R1 proposal on #554 (issue comment 5953613758) for the
seven codes and "Reason not recorded", and the advisor's #798 ruling (#736,
18:34Z) for "Set by its sub-techniques". Changing a word here changes client
deliverables.

**The vocabulary is not here on purpose.** `coverage.py` owns the codes and is
condition 5 (a scoring surface); this module only words them, and
`test_attack_partial_reason.py` derives its key set from `coverage.REASON_CODES`
so a new Partial code with no client wording goes red.

**R3.** Gene's Covered rule (R3) computes a row's status from Detect /
Prevent / Respond (`computed.py`, built in #808), and every surface prints the
"Detect: ... · Prevent: ... · Respond: ..." line beside the reason. A stored
reason on a computed row is shown only when its sentence is true of that line
(`_holds` below, for #842); otherwise the row reads "Set by what is in place".
`prevention_limited`'s wording is Option B of #842 (the advisor's ruling on
#736, comment 6053562002): it names a missing control, never a technique that
cannot be prevented, which is MITRE's list and has its own section (Gene's
decision 3 on #554).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.attack.computed import Capabilities, InPlace
from app.attack.coverage import CoverageStatus


@dataclass(frozen=True)
class PartialReason:
    """A short label (a cell, a chip) and one sentence (the explanation)."""

    label: str
    sentence: str

    def cell(self) -> str:
        """The XLSX "Why partial" cell: label, then sentence."""
        return f"{self.label}: {self.sentence}"


#: The seven Partial codes, in `coverage.REASON_CODES` order.
CLIENT_WORDING: dict[str, PartialReason] = {
    "missing_control_category": PartialReason(
        "A control type is missing",
        "Something already defends against this technique, but a whole category of "
        "control, such as prevention or response, is not in place.",
    ),
    "reach_limited": PartialReason(
        "Not covered everywhere",
        "Defended on most of your environment, but not on some systems, such as another "
        "operating system, a cloud or SaaS service, or unmanaged or off-network devices.",
    ),
    "detection_weak": PartialReason(
        "Detection is unreliable",
        "There is a signal for this activity, but it is noisy or approximate, or depends "
        "on custom detection rules that still need to be written and tuned.",
    ),
    "prevention_limited": PartialReason(
        "Detected, no blocking control",
        "This activity can be detected, but no control in place blocks it.",
    ),
    "evasive_variant_uncovered": PartialReason(
        "Advanced variants not covered",
        "Common forms of this technique are covered; advanced forms, such as "
        "kernel-level, firmware, encrypted or novel variants, are not.",
    ),
    "recovery_absent": PartialReason(
        "No recovery evidenced",
        "The attack would be detected, but no way to recover from it, such as backups "
        "or restore procedures, is evidenced.",
    ),
    "periodic_not_continuous": PartialReason(
        "Checked periodically, not continuously",
        "This is found only when a scheduled scan runs, not as it happens.",
    ),
}

REASON_NOT_RECORDED = PartialReason(
    "Reason not recorded",
    "This technique was assessed as partly covered, and no reason was recorded.",
)

SET_BY_SUB_TECHNIQUES = PartialReason(
    "Set by its sub-techniques",
    "This technique's coverage is computed from its sub-techniques; see each "
    "sub-technique for its own coverage and reason.",
)

#: #554 R3 (C7): a Partial whose status was COMPUTED from Detect / Prevent /
#: Respond and which carries no stored reason. Its reason is which of the three
#: are in place (the advisor's Q6), so "Reason not recorded" would be false.
SET_BY_WHAT_IS_IN_PLACE = PartialReason(
    "Set by what is in place",
    "This technique's status is computed from which of Detect, Prevent and Respond "
    "are in place.",
)

#: The order the count table lists them in: the codes, then the three states.
TABLE_ORDER: tuple[PartialReason, ...] = (
    *CLIENT_WORDING.values(),
    SET_BY_SUB_TECHNIQUES,
    SET_BY_WHAT_IS_IN_PLACE,
    REASON_NOT_RECORDED,
)

#: The XLSX legend row for the "Why partial" column.
WHY_PARTIAL_LEGEND = ("Why partial", "The reason a Partial technique is only partly covered.")


def _holds(code: str, caps: Capabilities) -> bool:
    """Whether every claim `code`'s client sentence makes is true of the computed
    line (for #842; the claims table approved on #736, comment 6053562002).

    `awaiting_review` satisfies neither an "in place" nor a "not in place"
    claim: tools are listed and none is confirmed, so neither is known. The
    claims are read from the sentences in `CLIENT_WORDING`; change both."""
    detect_in = caps.detect is InPlace.IN_PLACE
    if code == "prevention_limited":
        # "can be detected, but no control in place blocks it". A technique MITRE
        # lists no preventive control for reads "cannot be prevented", not this.
        return detect_in and caps.prevent is InPlace.NOT_IN_PLACE
    if code == "recovery_absent":
        # "would be detected, but no way to recover from it ... is evidenced".
        return detect_in and caps.respond is InPlace.NOT_IN_PLACE
    if code in ("detection_weak", "periodic_not_continuous"):
        # "There is a signal" / "found only when a scheduled scan runs".
        return detect_in
    if code == "missing_control_category":
        # "a whole category of control ... is not in place".
        return InPlace.NOT_IN_PLACE in caps.judged()
    if code in ("reach_limited", "evasive_variant_uncovered"):
        # "Defended on most" / "Common forms ... are covered": a computed Partial
        # always has something in place, so these hold of any computed Partial.
        return True
    raise ValueError(f"no claims are recorded for Partial reason {code!r}")


def partial_reason(
    status: str | None,
    reason_code: str | None,
    *,
    computed_parent: bool,
    capabilities: Capabilities | None = None,
) -> PartialReason | None:
    """What a client reads for one row, or None when the row is not Partial.

    `computed_parent` is True only under #620's rules (`parents_computed`) for a
    technique with sub-techniques; under rule 1 a parent was scored directly
    and reads like any other row.

    `capabilities` is set only for a row whose status #554 R3 computed from
    Detect / Prevent / Respond (`computed.EffectiveRow.capabilities`). Its stored
    reason is shown only when its sentence is true of that line (`_holds`, for
    #842, narrowing the advisor's Q7); otherwise, and without a stored reason, it
    reads `SET_BY_WHAT_IS_IN_PLACE`, never "Reason not recorded".

    An unknown code RAISES. Every writer validates the code against the status
    (`coverage.is_valid_reason`), so one here is a writer bug; rendering it as
    "Reason not recorded" would tell the client nobody recorded a reason when
    somebody did.
    """
    if status != CoverageStatus.PARTIAL.value:
        return None
    if computed_parent:
        return SET_BY_SUB_TECHNIQUES
    if reason_code is None:
        return SET_BY_WHAT_IS_IN_PLACE if capabilities is not None else REASON_NOT_RECORDED
    wording = CLIENT_WORDING.get(reason_code)
    if wording is None:
        raise ValueError(
            f"a Partial row carries reason_code {reason_code!r}, which is not a Partial "
            "reason; writes validate it, so this row was written past the validator"
        )
    if capabilities is not None and not _holds(reason_code, capabilities):
        return SET_BY_WHAT_IS_IN_PLACE
    return wording


def partial_reason_for_row(row: object, *, computed_parent: bool) -> PartialReason | None:
    """`partial_reason` for one coverage row: the ONE entry point the exporters
    and the client dashboard both call, so the two cannot read a row differently
    (for #842). A stored ORM row, or an `EffectiveRow` that was not computed,
    has no capabilities and reads its stored reason."""
    return partial_reason(
        row.status,
        row.reason_code,
        computed_parent=computed_parent,
        capabilities=getattr(row, "capabilities", None),
    )
