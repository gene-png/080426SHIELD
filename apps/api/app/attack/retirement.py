"""Which tools an ATT&CK assessment cites are PLANNED RETIREMENTS (#686, D-105).

## The decision

Gene, 2026-09-26: a Tech Debt tool whose disposition is `cut` is a planned
retirement. It STILL COUNTS toward ATT&CK coverage, because it is still
deployed, and every surface that counts it labels it "planned retirement" so
the client can see which coverage will drop. Coverage is not recomputed here
and nothing in `attack/analytics.py` changes: this module only labels.

## The join, and why each rule is what it is

An ATT&CK row stores tool NAMES (`detection_tools` and its two twins), never an
item id. Two writers put them there: the AI run, through `CitationResolver`,
which stores the canonical name of an entry in
`routes/attack.py::_client_capability_membership` (a redacted alias is resolved
back to that name before anything is stored, so #133 never reaches this join);
and the consultant's coverage PATCH, which stores free text. Disposition lives
on the LIVE `CapabilityItem`, and one tool can sit on several lists.

So a cited name is matched, by `strip().casefold()`, against EVERY entry the
membership was built from -- before its de-duplication, because the dedupe
keeps one list's row and the disposition may differ on another -- and each
entry is followed by its `item_id` to the live item:

  * Only an APPROVED or RELEASED list's `cut` is a plan. A consultant's
    unreviewed draft disposition is not "the consolidation plan", so a tool
    cut only on a DRAFT list reads as NOT retiring.
  * Every approved/released entry `cut`  ->  PLANNED.
  * Every approved/released entry known and none `cut`  ->  NOT retiring.
    An undecided (None) disposition is not a plan to retire.
  * Approved/released entries that DISAGREE, or one whose live item is gone,
    ->  UNKNOWN. Picking either side would assert a plan nobody stated.
  * A name matching no entry at all  ->  UNKNOWN. That is a consultant's free
    text, or a draft-list rename after the AI cited the old name; either way
    the plan cannot be read for it, and saying nothing would be a silent
    "not retiring".
  * Matched only on DRAFT lists  ->  NOT retiring, per the first bullet.

**"No consolidation plan" is not "could not determine".** A client with no
APPROVED or RELEASED Tech Debt list has no plan in which a tool could be cut,
so nothing is marked and no unknown count is printed. Marking every tool of a
client who never bought Tech Debt "retirement status unknown" would be true
of the join and false of the client.

## Freshness

Every caller reads the LIVE disposition. A deliverable freezes it by being
rendered at finalize; the client dashboard reads it on every request and says
so beside the labels. Freezing it for the dashboard is filed separately.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from app.attack.pending import row_tools

#: Suffixes on a tool name, after the existing " (unconfirmed)" when both apply.
#: COPIED to `apps/web/src/lib/attack/retirement.ts`; change both.
PLANNED_MARK = " (planned retirement)"
UNKNOWN_MARK = " (retirement status unknown)"

_COUNTED_STATUSES = frozenset({"covered", "partial"})


class Retirement(enum.StrEnum):
    PLANNED = "planned_retirement"
    NOT_RETIRING = "not_retiring"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PlanEntry:
    """One membership entry, as this module needs it.

    `in_plan` is True when the entry's list is APPROVED or RELEASED. `cut` is
    the live item's disposition read as cut-or-not, or None when the live
    item is gone.
    """

    name: str
    in_plan: bool
    cut: bool | None


def _key(name: object) -> str:
    return str(name or "").strip().casefold()


@dataclass(frozen=True)
class RetirementIndex:
    """The verdict per cited name. `has_plan` False marks nothing at all."""

    has_plan: bool
    by_key: Mapping[str, Retirement] = field(default_factory=dict)

    def state(self, tool: str) -> Retirement | None:
        """None when there is no plan to read; otherwise one of the three."""
        if not self.has_plan:
            return None
        return self.by_key.get(_key(tool), Retirement.UNKNOWN)

    def mark(self, tool: str) -> str:
        """The suffix a renderer appends to `tool`, or ""."""
        s = self.state(tool)
        if s is Retirement.PLANNED:
            return PLANNED_MARK
        if s is Retirement.UNKNOWN:
            return UNKNOWN_MARK
        return ""

    def marks(self, tools: Iterable[str]) -> dict[str, str]:
        """The non-trivial verdicts for `tools`, keyed by the exact string, for
        an API response: PLANNED and UNKNOWN only."""
        out: dict[str, str] = {}
        for t in tools:
            s = self.state(t)
            if s in (Retirement.PLANNED, Retirement.UNKNOWN):
                out[t] = s.value
        return out


NO_PLAN = RetirementIndex(has_plan=False)


def build_index(entries: Iterable[PlanEntry], *, has_plan: bool) -> RetirementIndex:
    """Fold the entries into one verdict per casefold name (rules above)."""
    if not has_plan:
        return NO_PLAN
    grouped: dict[str, list[PlanEntry]] = {}
    for e in entries:
        k = _key(e.name)
        if k:
            grouped.setdefault(k, []).append(e)
    by_key: dict[str, Retirement] = {}
    for k, group in grouped.items():
        planned = [e for e in group if e.in_plan]
        if not planned:
            by_key[k] = Retirement.NOT_RETIRING
            continue
        cuts = {e.cut for e in planned}
        if None in cuts or len(cuts) > 1:
            by_key[k] = Retirement.UNKNOWN
        elif cuts == {True}:
            by_key[k] = Retirement.PLANNED
        else:
            by_key[k] = Retirement.NOT_RETIRING
    return RetirementIndex(has_plan=True, by_key=by_key)


@dataclass(frozen=True)
class RetirementSummary:
    """What the count sentences say. `of_techniques` is the caller's covered +
    partial from its own rollup, so the sentence cannot disagree with the
    percentage it sits beside."""

    planned: int
    planned_only: int
    of_techniques: int
    unknown_tools: int


def summarize(
    rows: Iterable[Any],
    index: RetirementIndex,
    *,
    counted_codes: Iterable[str] | None = None,
    of_techniques: int,
) -> RetirementSummary | None:
    """Counts over the rows a deliverable lists, or None when there is no plan.

    `rows` are the rows whose tools the surface prints (a computed parent's
    are not, and the caller passes it with no tools). A technique counts toward
    `planned` / `planned_only` when its status is covered or partial and it is
    in `counted_codes` (the caller's non-withheld set), because only those are
    inside the percentage. `unknown_tools` counts DISTINCT names across every
    listed row, since the label appears on every row that cites them.
    """
    if not index.has_plan:
        return None
    counted = None if counted_codes is None else frozenset(counted_codes)
    planned = planned_only = 0
    unknown: set[str] = set()
    for row in rows:
        tools = row_tools(row)
        for t in tools:
            if index.state(t) is Retirement.UNKNOWN:
                unknown.add(_key(t))
        if getattr(row, "status", None) not in _COUNTED_STATUSES or not tools:
            continue
        if counted is not None and row.technique_code not in counted:
            continue
        states = [index.state(t) for t in tools]
        if Retirement.PLANNED in states:
            planned += 1
            if all(s is Retirement.PLANNED for s in states):
                planned_only += 1
    return RetirementSummary(
        planned=planned,
        planned_only=planned_only,
        of_techniques=of_techniques,
        unknown_tools=len(unknown),
    )


def summary_sentences(s: RetirementSummary | None) -> list[str]:
    """The approved count sentences, each only when its count is non-zero."""
    if s is None:
        return []
    out: list[str] = []
    if s.planned:
        techs = "technique" if s.of_techniques == 1 else "techniques"
        cites = "cites" if s.planned == 1 else "cite"
        rely = "relies" if s.planned_only == 1 else "rely"
        out.append(
            f"{s.planned} of the {s.of_techniques} covered or partial {techs} {cites} a "
            f"tool marked for planned retirement; {s.planned_only} {rely} on such "
            "tools alone."
        )
    if s.unknown_tools:
        tools = "tool" if s.unknown_tools == 1 else "tools"
        out.append(
            f"Retirement status could not be determined for {s.unknown_tools} cited {tools}."
        )
    return out
