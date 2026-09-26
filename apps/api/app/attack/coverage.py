"""ATT&CK coverage status vocabulary: statuses, reason codes, labels (#554).

Decided by the owner on 2026-09-24 (#554, the vocabulary comment). The rules are
stated here, where a reader looking up a code will find them, because the
vocabulary exists to stop one specific abuse: moving rows out of the gap list.

STATUSES. Four assess the technique: covered, partial, gap, not_applicable. Two
do not:
  * `outside_control_surface`: the technique applies and the client's control
    surface does not reach it (an adversary researches the organisation whatever
    anyone does). It stays in the catalogue total and OUTSIDE the assessed
    denominator, with its own line in the deliverable.
  * `unable_to_determine`: nobody verified it. It is also OUTSIDE the assessed
    denominator and never counted as partial or gap. The owner's decision makes
    it a release blocker; that gate is a later slice.

NOT YET WRITABLE. The two new statuses are defined, stored and counted, and
nothing may WRITE them yet: `WRITABLE` below is still the original four. Every
reporting surface renders them as of #621 (the client and admin dashboards, the
exporters and finalize summary, the home value card, the risk link scope). What
remains before the widening slice may add them to `WRITABLE`:
  * the release-readiness gate (#622), which does not exist yet;
  * the owner's call on how the Risk Register treats an unverified technique
    (#621 keeps it uncitable and names it "Not verified"; not yet confirmed).
The PATCH refuses them typed, and the AI write-back refuses a suggestion carrying
one WHOLE and records it (`statuses_rejected`), until that slice widens
`WRITABLE`. My call, overturnable, recorded on #554.

REASON CODES. A reason means something only for the status it belongs to:
  * Partial: seven codes, below.
  * not_applicable: `platform_absent` only. A real scoping exclusion is
    evidence-backed and verifiable.
  * outside_control_surface: three sub-cases, below.
  * covered, gap, unable_to_determine: none. An unverified row carries a
    NARRATIVE instead.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class CoverageStatus(enum.StrEnum):
    """Per-technique defensive coverage status."""

    COVERED = "covered"
    PARTIAL = "partial"
    GAP = "gap"
    NOT_APPLICABLE = "not_applicable"
    OUTSIDE_CONTROL_SURFACE = "outside_control_surface"
    UNABLE_TO_DETERMINE = "unable_to_determine"


#: What a consultant or the AI may write today. See "NOT YET WRITABLE" above.
WRITABLE: frozenset[CoverageStatus] = frozenset(
    {
        CoverageStatus.COVERED,
        CoverageStatus.PARTIAL,
        CoverageStatus.GAP,
        CoverageStatus.NOT_APPLICABLE,
    }
)

#: The statuses whose rows form the assessed denominator of `coverage_pct`.
#: READ, not restated: `analytics.compute` and the client dashboard's
#: `total_evaluated` (`routes/clients.py`) sum over this set, and
#: `test_attack_assessed_is_the_one_definition.py` fails on a hand-written
#: covered + partial + gap anywhere under `app/`. The web keeps its own copy,
#: `ASSESSED` in `apps/web/src/lib/dashboards/attack.ts` (the Detect / Prevent /
#: Respond denominator) -- change both.
ASSESSED: frozenset[CoverageStatus] = frozenset(
    {CoverageStatus.COVERED, CoverageStatus.PARTIAL, CoverageStatus.GAP}
)

#: Stored statuses that are NOT a consultant's judgement: nobody verified the
#: technique (#554). ONE definition of "scored" for both client documents: the
#: ATT&CK deliverable's `scored_count` (`analytics.compute`) and the Risk
#: Register's citable scope (`risk/link_scope.py`) both exclude these, and
#: `test_scored_means_the_same_rows_in_both_documents` pins the two as equal.
UNJUDGED: frozenset[CoverageStatus] = frozenset({CoverageStatus.UNABLE_TO_DETERMINE})


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
            "Something defends against this technique, and a named part of that "
            "defence is missing."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.GAP,
        short_label="Gap",
        description=(
            "Nothing defends against this technique today. Treat as a remediation "
            "priority. A missing control with nothing else defending is a gap, never "
            "N/A."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.NOT_APPLICABLE,
        short_label="N/A",
        description=(
            "The technique cannot occur here: the platform it targets is absent from "
            "the environment (reason `platform_absent`, verifiable from an asset "
            "inventory). An argument about reach is not N/A."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.OUTSIDE_CONTROL_SURFACE,
        short_label="Outside control surface",
        description=(
            "The technique applies, and the client's control surface does not reach "
            "it: the adversary acts on infrastructure or accounts the client neither "
            "owns nor governs. Counted in the catalogue total, not in coverage."
        ),
    ),
    CoverageDefinition(
        status=CoverageStatus.UNABLE_TO_DETERMINE,
        short_label="Not verified",
        description=(
            "Nobody verified this technique. Carries a narrative saying what could "
            "not be established. Not counted in coverage."
        ),
    ),
)


@dataclass(frozen=True)
class ReasonCode:
    code: str
    status: CoverageStatus
    definition: str


REASON_CODES: tuple[ReasonCode, ...] = (
    # --- Partial: something defends it; name what is missing -----------------
    ReasonCode(
        "missing_control_category",
        CoverageStatus.PARTIAL,
        "A named category of control is absent, while another control still "
        "defends the technique. missing_control_category is legitimate for Partial "
        "(something defends it, a category is missing) and forbidden for N/A "
        "(nothing defends it -- that is a gap). The test: is anything defending it "
        "at all? Same words, opposite meanings; confusing them moves rows out of "
        "the gap list, which is the direction that flatters the client.",
    ),
    ReasonCode(
        "reach_limited",
        CoverageStatus.PARTIAL,
        "Covered on the main estate, not on part of it: another operating system, "
        "another cloud, SaaS, unmanaged or off-network hosts.",
    ),
    ReasonCode(
        "detection_weak",
        CoverageStatus.PARTIAL,
        "A signal exists but is noisy, heuristic, or depends on custom rules being "
        "written and tuned.",
    ),
    ReasonCode(
        "prevention_limited",
        CoverageStatus.PARTIAL,
        "Detectable but not preventable, including where legitimate use needs the "
        "same capability.",
    ),
    ReasonCode(
        "evasive_variant_uncovered",
        CoverageStatus.PARTIAL,
        "Common forms are covered; advanced forms (kernel, firmware, encrypted, novel) are not.",
    ),
    ReasonCode(
        "recovery_absent",
        CoverageStatus.PARTIAL,
        "The attack is detected, and no recovery or backup capability is evidenced.",
    ),
    ReasonCode(
        "periodic_not_continuous",
        CoverageStatus.PARTIAL,
        "Found only at scan intervals, not continuously.",
    ),
    # --- not_applicable: the one true scoping exclusion ----------------------
    ReasonCode(
        "platform_absent",
        CoverageStatus.NOT_APPLICABLE,
        "The platform the technique targets is not present in the environment, "
        "verifiable from an asset inventory.",
    ),
    # --- outside_control_surface: which surface the client cannot reach ------
    ReasonCode(
        "adversary_preparation",
        CoverageStatus.OUTSIDE_CONTROL_SURFACE,
        "Activity on the adversary's own infrastructure before any contact: "
        "developing, obtaining or staging capabilities, establishing accounts, "
        "acquiring access.",
    ),
    ReasonCode(
        "external_reconnaissance",
        CoverageStatus.OUTSIDE_CONTROL_SURFACE,
        "The adversary researching the organisation in public or purchased sources.",
    ),
    ReasonCode(
        "third_party_compromise",
        CoverageStatus.OUTSIDE_CONTROL_SURFACE,
        "Compromise of infrastructure or accounts the organisation neither owns nor governs.",
    ),
)

_BY_CODE = {r.code: r for r in REASON_CODES}


def reason_codes_for(status: CoverageStatus | str | None) -> tuple[str, ...]:
    """The reason codes that are valid for `status`; empty when none are."""
    if status is None:
        return ()
    value = CoverageStatus(status)
    return tuple(r.code for r in REASON_CODES if r.status == value)


def reason_definition(code: str) -> str:
    return _BY_CODE[code].definition


def is_valid_reason(status: CoverageStatus | str | None, code: str | None) -> bool:
    """A reason is valid only for the status it belongs to. None is always valid:
    a MISSING reason is a release-readiness question, not a click-time one."""
    if code is None:
        return True
    return code in reason_codes_for(status)


def coverage_label(value: CoverageStatus | str | None) -> str:
    if value is None:
        return "Unscored"
    target = value if isinstance(value, CoverageStatus) else CoverageStatus(value)
    for d in COVERAGE_DEFINITIONS:
        if d.status == target:
            return d.short_label
    return "Unknown"
