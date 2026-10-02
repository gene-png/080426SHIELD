"""An ATT&CK technique's status, COMPUTED from Detect / Prevent / Respond (#554 R3).

## The decisions (relayed by the advisor on #554, 2026-10-02)

* **Covered** only when Detect, Prevent and Respond are all in place. Any other
  combination is **Partial**; nothing in place in any of the three is a **Gap**.
  AI suggests (the tool lists and a status), code computes (this module).
* **In place** (Q1, option c1): at least one tool in that capability's list
  whose citation is not pending review -- `pending.py`'s definition, so an
  exact name match counts with no human step. The release gate's review queue
  (`review_queue` below) is the human step.
* **Cannot be prevented** (Q2, Q3): MITRE ATT&CK lists no preventive control
  for the technique (`catalog.NOT_PREVENTABLE`). It is judged on Detect and
  Respond, and is Covered when both are in place.
* **Awaiting review** is the third value (Q4): tools are listed and none is
  confirmed. The status is scored at the LOWER bound -- as if those tools were
  not in place -- and every surface says "awaiting review" rather than "not in
  place", with `awaiting_review_count` beside the percentage. Withholding the
  row instead (#102) would raise the figure for a row that can only be Gap or
  Partial, the optimistic move `pending.py` warns about.
* **Retirement is ignored** (Q5): this is the "today" figure. #801 adds "after
  planned changes", the same computation with retiring tools taken out.

## Which rows are computed

Only rows whose STORED status is covered, partial or gap -- someone assessed
them. N/A and outside-the-control-surface are rulings, Not verified and unset
are absences, and computing any of them would overwrite a fact with a guess.
A computed parent (#620) is recomputed from its children's COMPUTED statuses,
through the same `computed_parent_status` the write path uses.

## Derived at read, never stored

The stored `status` stays what it was -- the AI's (or a consultant's) suggestion
-- and `effective_coverage` returns rows whose `status` is the computed one.
Every reader of an ATT&CK assessment's rows goes through it, so the rollup, the
dashboard, the deliverables, the risk feed and the release gate cannot disagree.
An assessment approved before R3 (`rules.statuses_computed` False) gets its
rows back unchanged.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.attack.catalog import NOT_PREVENTABLE
from app.attack.coverage import CoverageStatus
from app.attack.parents import PARENT_CHILDREN, computed_parent_status
from app.attack.pending import uncleared_tools
from app.attack.rules import parents_computed, statuses_computed

#: Stored statuses that mean "assessed": these are recomputed.
_ASSESSED = frozenset(
    {CoverageStatus.COVERED.value, CoverageStatus.PARTIAL.value, CoverageStatus.GAP.value}
)


class InPlace(enum.StrEnum):
    IN_PLACE = "in_place"
    NOT_IN_PLACE = "not_in_place"
    AWAITING_REVIEW = "awaiting_review"
    CANNOT_BE_PREVENTED = "cannot_be_prevented"


#: The client copy for each value, approved on #554 (21:55Z). COPIED to
#: `apps/web/src/lib/dashboards/attack.ts`; change both.
IN_PLACE_TEXT: dict[InPlace, str] = {
    InPlace.IN_PLACE: "in place",
    InPlace.NOT_IN_PLACE: "not in place",
    InPlace.AWAITING_REVIEW: "awaiting review",
    InPlace.CANNOT_BE_PREVENTED: "cannot be prevented",
}


@dataclass(frozen=True)
class Capabilities:
    detect: InPlace
    prevent: InPlace
    respond: InPlace

    def judged(self) -> tuple[InPlace, ...]:
        """The capabilities the status is judged on: all three, or Detect and
        Respond for a technique that cannot be prevented."""
        if self.prevent is InPlace.CANNOT_BE_PREVENTED:
            return (self.detect, self.respond)
        return (self.detect, self.prevent, self.respond)

    @property
    def awaiting(self) -> bool:
        return InPlace.AWAITING_REVIEW in self.judged()

    @property
    def cannot_be_prevented(self) -> bool:
        return self.prevent is InPlace.CANNOT_BE_PREVENTED

    def line(self) -> str:
        """The approved line: `Detect: in place · Prevent: … · Respond: …`."""
        return (
            f"Detect: {IN_PLACE_TEXT[self.detect]} · "
            f"Prevent: {IN_PLACE_TEXT[self.prevent]} · "
            f"Respond: {IN_PLACE_TEXT[self.respond]}"
        )


def capability(tools: Iterable[Any] | None, unconfirmed_citations: list | None) -> InPlace:
    """One capability from its tool list and the row's citation record."""
    names = [t for t in tools or [] if isinstance(t, str) and t.strip()]
    if not names:
        return InPlace.NOT_IN_PLACE
    # NULL: the citations were never resolved, so nothing says any tool was
    # checked (migration 0044). Absence of evidence is not confirmation.
    if unconfirmed_citations is None:
        return InPlace.AWAITING_REVIEW
    flagged = uncleared_tools(unconfirmed_citations)
    if any(t not in flagged for t in names):
        return InPlace.IN_PLACE
    return InPlace.AWAITING_REVIEW


def capabilities(row: Any) -> Capabilities:
    citations = row.unconfirmed_citations
    prevent = (
        InPlace.CANNOT_BE_PREVENTED
        if row.technique_code in NOT_PREVENTABLE
        else capability(row.prevention_tools, citations)
    )
    return Capabilities(
        detect=capability(row.detection_tools, citations),
        prevent=prevent,
        respond=capability(row.response_tools, citations),
    )


def status_from(caps: Capabilities) -> str:
    """Covered / Partial / Gap, with "awaiting review" at the lower bound."""
    in_place = [c is InPlace.IN_PLACE for c in caps.judged()]
    if all(in_place):
        return CoverageStatus.COVERED.value
    if not any(in_place):
        return CoverageStatus.GAP.value
    return CoverageStatus.PARTIAL.value


class EffectiveRow:
    """A stored row seen through R3: `status` (and a parent's `reason_code`) is
    computed; every other attribute is the stored row's. Read-only by design:
    the write paths take the ORM rows themselves."""

    __slots__ = ("_row", "status", "reason_code", "suggested_status", "capabilities")

    def __init__(
        self,
        row: Any,
        *,
        status: str | None,
        reason_code: str | None,
        capabilities: Capabilities | None,
    ) -> None:
        self._row = row
        self.status = status
        self.reason_code = reason_code
        self.suggested_status = row.status
        self.capabilities = capabilities

    def __getattr__(self, name: str) -> Any:
        return getattr(self._row, name)

    @property
    def is_computed(self) -> bool:
        """True for a leaf whose status this module computed."""
        return self.capabilities is not None


def effective_coverage(assessment: Any, rows: Iterable[Any]) -> list[Any]:
    """The rows every reader uses: computed under R3, unchanged before it."""
    rows = list(rows)
    if not statuses_computed(assessment):
        return rows
    parents = parents_computed(assessment)
    out: dict[str, EffectiveRow] = {}
    for row in rows:
        code = row.technique_code
        if (parents and code in PARENT_CHILDREN) or row.status not in _ASSESSED:
            out[code] = EffectiveRow(
                row, status=row.status, reason_code=row.reason_code, capabilities=None
            )
            continue
        caps = capabilities(row)
        out[code] = EffectiveRow(
            row, status=status_from(caps), reason_code=row.reason_code, capabilities=caps
        )
    if parents:
        for code, kids in PARENT_CHILDREN.items():
            parent = out.get(code)
            if parent is None:
                continue
            children = [
                (out[k].status, out[k].reason_code) if k in out else (None, None) for k in kids
            ]
            parent.status, parent.reason_code = computed_parent_status(children)
    return [out[row.technique_code] for row in rows]


def awaiting_review_count(rows: Iterable[Any]) -> int:
    """How many computed techniques are scored as if tools awaiting review were
    not in place (Q4's disclosure)."""
    return sum(
        1
        for r in rows
        if isinstance(r, EffectiveRow) and r.is_computed and r.capabilities.awaiting
    )


def review_queue(rows: Iterable[Any]) -> tuple[str, ...]:
    """Codes awaiting a consultant's review (Q1, 22:20Z), sorted.

    A computed leaf whose computed status differs from its stored suggestion,
    unless a consultant accepted THAT computed status. A review of an earlier
    computed status does not carry over: a different outcome is reviewed again.
    Parents are excluded; their children are what is reviewed."""
    return tuple(
        sorted(
            r.technique_code
            for r in rows
            if isinstance(r, EffectiveRow)
            and r.is_computed
            and r.status != r.suggested_status
            and r.reviewed_status != r.status
        )
    )


__all__ = [
    "IN_PLACE_TEXT",
    "Capabilities",
    "EffectiveRow",
    "InPlace",
    "awaiting_review_count",
    "capabilities",
    "capability",
    "effective_coverage",
    "review_queue",
    "status_from",
]
