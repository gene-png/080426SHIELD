"""ATT&CK rows that credit a tool outside the client's CURRENT security subset (#851).

A row stores tool NAMES. They are checked against the client's security tool
list only when Run AI writes them, and a re-run skips a locked row and one a
consultant edited mid-run; a consultant's PATCH stores names as typed. So a
row can go on crediting a tool after the client's list stops offering it, and
R3 (`attack/computed.py::capability`) counts it as in place.

The ruling (advisor, #736 comment 5984022081): DISCLOSE it on the workspace,
refuse approve while a draft has any, and disclose after approval. R3 itself
is not changed here (option B, filed as #888).

**"The same tool" is decided by the run's own resolver, never by a second
comparison.** The resolver here is built exactly as Run AI builds its own
(`routes/attack.py::citation_resolver_for`), and a name is in the subset when
the resolver's NAME tiers know it (`CitationResolver.named_by`: the stored
name, case and whitespace, or the form the AI is shown). An inference -- a
vendor, a substring -- does not count: a tool that left the subset must not be
read as a sibling product that stayed.

`attack/retirement.py` joins names to plan entries by `strip().casefold()`.
It answers a different question (WHICH entry's disposition applies); the two
can disagree on a vendor-shaped name, and that is stated there too.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.attack.citations import CitationResolver
from app.attack.parents import is_computed_parent
from app.attack.pending import TOOL_FIELDS
from app.models.capability import CapabilityListStatus


@dataclass(frozen=True)
class OutsideCitation:
    """One tool one row credits outside the subset. `locked`: Run AI will not
    change this row, so the remedy is to remove the tool by hand."""

    technique_code: str
    field: str
    tool: str
    locked: bool


def is_outside_subset(name: str, subset: CitationResolver) -> bool:
    """THE ONE PREDICATE for "outside the subset" (D1 on #851, approved by the
    advisor, #736): any cited name the subset's name tiers do not know,
    whether it LEFT the subset (a confirmed "not security" or "not in use"
    sign-off, or a list approved again without it) or was typed by hand and
    was never on the list.

    The narrower reading (D1(b): only a name the client's list still holds,
    kept out of the subset) would add one condition here: that the name hits
    a resolver over `CapabilityMembership.withheld`. Nothing else changes."""
    return not subset.named_by(name)


#: The third state, said where the check could not run (advisor, #736
#: comment 6039558116: "not checked" is not a pass). Wording approved verbatim
#: (#736 comment 6040458893).
NOT_CHECKED_SENTENCE = (
    "The tools cited here were not checked against a security tool list, because "
    "the client has none."
)


#: R4, option (b) (#736): why nothing could be checked. No Tech Debt list at
#: all; only lists with no security-scope row; or only discarded lists. Under
#: R6b (#736 6094994432) "only lists with no security-scope row" is judged on
#: the versions in force: a service's approved or released versions where it
#: has any (its drafts ignored), else its drafts. A drafts-only client is
#: therefore checked against its newest draft, never "no_list".
NOT_CHECKED_NO_LIST = "no_list"
NOT_CHECKED_EMPTY = "empty"
NOT_CHECKED_DISCARDED = "discarded"


@dataclass(frozen=True)
class VersionFallback:
    """R4 (b): one Tech Debt service whose current list is not simply its
    newest version in force.

    In force (R6b, #736 6094994432): the service's APPROVED and RELEASED
    versions if it has any, its drafts ignored; else its drafts. `skipped`:
    every version in force passed over for holding no security-scope row, as
    (version, status), newest first by version number. So the statuses are
    all "draft" (a drafts-only service, C8a) or all approved / released
    (C8b), never mixed. `used_version`: the version that votes, or None when
    the service contributes nothing, in which case `reason` says why
    (`NOT_CHECKED_EMPTY`: every version in force is empty;
    `NOT_CHECKED_DISCARDED`: every version is discarded, and `skipped` is then
    empty). `reason` is None exactly when `used_version` is not."""

    service_id: uuid.UUID
    service_title: str
    skipped: tuple[tuple[int, str], ...]
    used_version: int | None
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.used_version is None) != (self.reason is not None):
            raise ValueError(
                "a service records a reason exactly when it contributes no version "
                f"(used_version={self.used_version!r}, reason={self.reason!r})"
            )


@dataclass(frozen=True)
class SubsetCheck:
    """#889 (Q7): whether the cited tools were checked against a security tool
    list, and what the check found, as ONE value so the two cannot disagree.

    `checked` False is the third state, "not checked": the client has no Tech
    Debt list, only lists with no security tool, or only discarded lists
    (`not_checked_reason`); a mix of the last two (one service empty, one
    only discarded) reports "empty", by `_current_list_versions`' precedence.
    Nothing can be outside a list that does not exist, so `outside` must then
    be empty, and building one that is not raises here."""

    checked: bool
    outside: tuple[OutsideCitation, ...] = ()
    #: R4 (b): the services whose newest version in force did not vote (R6b:
    #: approved or released where any exists, else drafts). Additive.
    fallbacks: tuple[VersionFallback, ...] = ()
    #: R4 (b): why nothing was checked (`NOT_CHECKED_*`); None when checked.
    not_checked_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.checked and self.outside:
            raise ValueError(
                f"a subset that was not checked cannot carry {len(self.outside)} tools "
                "outside it; `outside` is the check's own finding"
            )
        if self.checked and self.not_checked_reason is not None:
            raise ValueError(
                f"a checked subset cannot carry a not-checked reason "
                f"({self.not_checked_reason!r})"
            )

    def outside_tools(self) -> frozenset[str]:
        """The cited names to mark, exactly as stored."""
        return frozenset(o.tool for o in self.outside)

    def outside_codes(self) -> frozenset[str]:
        """The technique rows crediting at least one of them."""
        return frozenset(o.technique_code for o in self.outside)


#: #889 copy, approved verbatim (advisor, #736 comment 6090360421, on the plan
#: at 6089903057). C3: the per-tool mark, after " (unconfirmed)" and after the
#: retirement mark. COPIED to `apps/web/src/lib/attack/subset.ts`; change both.
OUTSIDE_MARK = " (not in the security tool list)"
#: C4: the XLSX legend row for that mark.
OUTSIDE_LEGEND = (
    f"Tools marked{OUTSIDE_MARK}",
    "Not in the client's security tool list when this report was finalized, so "
    "coverage may count a tool the client does not use.",
)


def outside_rows_sentence(rows: int) -> str:
    """C1: #851's approved S1, with a period in place of its colon. Counts
    ROWS, as the approve refusal does: one tool on two rows is two."""
    if rows == 1:
        return (
            "1 technique row credits a tool that is not in the client's security tool "
            "list, so its status may count a tool the client does not use."
        )
    return (
        f"{rows} technique rows credit a tool that is not in the client's security "
        "tool list, so their status may count a tool the client does not use."
    )


#: R4 copy, approved verbatim (advisor, #736 comment 6093188709). C5b replaces
#: `NOT_CHECKED_SENTENCE` where the reason is `NOT_CHECKED_EMPTY`.
NOT_CHECKED_EMPTY_SENTENCE = (
    "The tools cited here were not checked against a security tool list, because "
    "the client's security tool list has no security tools."
)


def not_checked_sentence(reason: str | None) -> str:
    """The "not checked" sentence for `reason`: C5b when every list is empty,
    C5 otherwise. "no_list" keeps C5 by the ruling, and "discarded" (only
    discarded lists) keeps C5 too, as ruled by the advisor in #736 comment
    6093549176."""
    return NOT_CHECKED_EMPTY_SENTENCE if reason == NOT_CHECKED_EMPTY else NOT_CHECKED_SENTENCE


def fallback_sentence(fallback: VersionFallback) -> str:
    """C9, in the deliverable and on the client dashboard, one per service that
    fell back. {m} is the version used. It names the service, so two services
    falling back to the same version read as two different lines (C9 as
    changed by the advisor, #736 comment 6093549176)."""
    return (
        f"In {fallback.service_title}, cited tools were checked against version "
        f"{fallback.used_version} of the client's security tool list, because the newest "
        "version has no security tools."
    )


def fallback_admin_sentence(fallback: VersionFallback) -> str:
    """C8a (the newest skipped version is a DRAFT) or C8b (approved or
    released), on the admin ATT&CK workspace only. {n} is the newest skipped
    version, {m} the version used.

    C8a is reachable only in a Tech Debt service with ONLY drafts (R6b, #736
    6094994432): where a service has an approved or released version its
    drafts are ignored, so none is ever skipped
    (`test_r6b_c8a_only_in_a_drafts_only_service`).

    C8b IS reachable: the Tech Debt approve route accepts a list with no
    security row (`test_r4_an_approved_empty_newest_version_reads_c8b`)."""
    n, status = fallback.skipped[0]
    m = fallback.used_version
    if status == "draft":
        return (
            f"In {fallback.service_title}, the newest security tool list (version {n}, a "
            f"draft) has no security tools, so these checks use version {m}. If version "
            f'{n} came from the wrong document, use "Discard draft" in that Tech Debt '
            "workspace."
        )
    return (
        f"In {fallback.service_title}, the newest security tool list (version {n}) has no "
        f"security tools, so these checks use version {m}."
    )


def used_fallbacks(fallbacks: Iterable[VersionFallback]) -> list[VersionFallback]:
    """The services that fell back to an earlier version (C8, C9): a service
    that contributes nothing has no version to name."""
    return [f for f in fallbacks if f.used_version is not None]


def subset_applies(list_statuses: Iterable[Any]) -> bool:
    """Whether there is a security tool list to judge a citation against: at
    least one Tech Debt list that is not DISCARDED feeds the subset.

    With none, NOTHING is outside it: an ATT&CK-only client's tools are all
    typed by a consultant (Run AI can cite nothing without a list), and
    flagging every one would refuse every approve that cites a tool. The
    same rule as #686's retirement labels: "no consolidation plan is not
    could not determine" (`attack/retirement.py`). Approved by the advisor
    (#736 comment 6039558116), with "not checked" said as a third state."""
    return any(s != CapabilityListStatus.DISCARDED for s in list_statuses)


def citations_outside_subset(
    rows: Iterable[Any], subset: CitationResolver, *, parents_computed: bool
) -> list[OutsideCitation]:
    """Every (row, field, tool) credited outside the subset, by technique code
    then field, locked or not: an unlocked row credits the tool too, until a
    re-run, and `locked` says which a re-run will NOT fix.

    A COMPUTED PARENT's own tools are skipped when the assessment computes its
    parents (`parents_computed`, the assessment's rule set, REQUIRED so no
    caller defaults it -- the same contract as `pending.pending_codes`). Under
    D-094 a parent's evidence is its children's: no deliverable prints its own
    tools (`exporters._delivered_rows`) and no score rests on them. And no
    control can clear one -- the coverage PATCH, Remove included, and Run AI
    both refuse a parent -- so flagging it refused approve with a remedy that
    cannot work (review finding F1 on #897). Its children are checked like any
    row. Under the OLD rules (an assessment approved before #620) a parent's
    own tools ARE delivered, so they are checked there."""
    out: list[OutsideCitation] = []
    for row in sorted(rows, key=lambda r: r.technique_code):
        if parents_computed and is_computed_parent(row.technique_code):
            continue
        for field in TOOL_FIELDS:
            for tool in getattr(row, field, None) or []:
                if isinstance(tool, str) and tool.strip() and is_outside_subset(tool, subset):
                    out.append(
                        OutsideCitation(
                            technique_code=row.technique_code,
                            field=field,
                            tool=tool,
                            locked=bool(row.locked),
                        )
                    )
    return out
