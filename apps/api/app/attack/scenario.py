"""The ATT&CK what-if's code side (#802 slice A).

An admin removes tools from the client's last confirmed ATT&CK assessment and
sees how coverage would change. Only the techniques the removed tools appear on
are re-assessed, by a scoped AI call (`attack_scenario_delta`); every other
technique is the frozen assessment, byte for byte.

AI suggests, code computes:
- the AI may only say which REMAINING tools provide Detect, Prevent or Respond
  for an affected technique;
- this module drops and counts anything outside that (a technique outside the
  slice, a tool outside the change, a non-boolean);
- every status and percentage comes from R3's `computed.py` and the coverage
  rollup, never from the AI.

Nothing here writes. The rows it builds are copies; the base assessment's rows
are never mutated.
"""

from __future__ import annotations

import uuid
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.attack.analytics import CoverageRollup, compute
from app.attack.catalog import all_codes
from app.attack.computed import effective_coverage
from app.attack.pending import pending_codes, row_tools
from app.attack.release_readiness import unreviewed_codes
from app.attack.rules import parents_computed, statuses_computed
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus

_LISTS = ("detection_tools", "prevention_tools", "response_tools")
_FLAGS = (
    ("detection", "detection_tools"),
    ("prevention", "prevention_tools"),
    ("response", "response_tools"),
)


class UnknownTool(ValueError):
    """A removal names a tool the assessment does not cite."""

    def __init__(self, name: str) -> None:
        super().__init__(f"{name!r} is not a tool this assessment cites")
        self.name = name


class EmptyChangeList(ValueError):
    """A change list with nothing in it."""


class ScenarioShapeError(ValueError):
    """The AI's answer is not `{"rows": [...]}`. Counted as a failed batch by
    the caller, never read as "nothing to say"."""


def _key(name: object) -> str:
    return str(name or "").strip().casefold()


def _cited(rows: Iterable[Any]) -> dict[str, str]:
    """Every tool the rows cite, case-folded to the name as first stored."""
    out: dict[str, str] = {}
    for row in rows:
        for tool in row_tools(row):
            if isinstance(tool, str) and tool.strip():
                out.setdefault(_key(tool), tool)
    return out


def resolve_removed(rows: Sequence[Any], names: Iterable[str]) -> list[str]:
    """The removals as the names the assessment cites, de-duplicated, in the
    order given. Refuses an empty list and any name the assessment does not
    cite: a guess would assess a tool nobody named."""
    cited = _cited(rows)
    out: list[str] = []
    for name in names:
        found = cited.get(_key(name))
        if found is None:
            raise UnknownTool(str(name))
        if found not in out:
            out.append(found)
    if not out:
        raise EmptyChangeList("choose at least one tool to remove")
    return out


def affected_codes(rows: Iterable[Any], removed: Iterable[str]) -> list[str]:
    """The techniques a removed tool appears on, in any of the three lists,
    sorted. These, and only these, are sent to the AI."""
    gone = {_key(n) for n in removed}
    return sorted(
        row.technique_code for row in rows if any(_key(t) in gone for t in row_tools(row))
    )


@dataclass(frozen=True)
class ParsedDelta:
    """The accepted answer: new D/P/R lists for EVERY asked technique (empty
    when the AI named nothing for it), and the counted drops by reason."""

    lists: dict[str, dict[str, list[str]]]
    accepted: list[dict[str, Any]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)


def parse_delta(
    data: Mapping[str, Any], *, asked: Iterable[str], available: Iterable[str]
) -> ParsedDelta:
    """Validate one batch's answer against the contract.

    `asked` is the batch's slice of affected techniques; `available` is the
    client's tools minus the removed ones. A tool is matched case-folded and
    stored under its catalogue name, never the AI's spelling."""
    rows = data.get("rows") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ScenarioShapeError("the answer has no `rows` list")
    asked = list(asked)
    asked_set = set(asked)
    tools = {_key(t): t for t in available}
    lists = {code: {name: [] for name in _LISTS} for code in asked}
    accepted: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            dropped["not_an_object"] += 1
            continue
        code = row.get("technique_code")
        if code not in asked_set:
            dropped["technique_outside_slice"] += 1
            continue
        tool = tools.get(_key(row.get("tool")))
        if tool is None:
            dropped["tool_outside_change"] += 1
            continue
        flags = {flag: row.get(flag) for flag, _ in _FLAGS}
        # `bool` only: `1`, "yes" and a missing key are refused, never coerced.
        if not all(isinstance(v, bool) for v in flags.values()):
            dropped["not_boolean"] += 1
            continue
        for flag, list_name in _FLAGS:
            if flags[flag] and tool not in lists[code][list_name]:
                lists[code][list_name].append(tool)
        accepted.append(
            {
                "technique_code": code,
                "tool": tool,
                **flags,
                "rationale": str(row.get("rationale") or ""),
            }
        )
    return ParsedDelta(lists=lists, accepted=accepted, dropped=dict(dropped))


def _copy(row: Any) -> SimpleNamespace:
    """A detached copy of a coverage row, so nothing done to it reaches the
    base assessment's rows."""
    attrs = {
        k: (list(v) if isinstance(v, list) else v)
        for k, v in vars(row).items()
        if not k.startswith("_sa_")
    }
    return SimpleNamespace(**attrs)


def scenario_rows(
    base_rows: Iterable[Any], lists: Mapping[str, Mapping[str, list[str]]]
) -> list[SimpleNamespace]:
    """The base rows with the affected techniques' lists replaced. Citations
    and every other field are the base row's: a tool awaiting review there
    still awaits it here."""
    out: list[SimpleNamespace] = []
    for row in base_rows:
        copy = _copy(row)
        new = lists.get(row.technique_code)
        if new is not None:
            for name in _LISTS:
                setattr(copy, name, list(new[name]))
        out.append(copy)
    return out


@dataclass(frozen=True)
class Comparison:
    """Coverage today against with-these-changes, and each technique whose
    computed status moved, as (code, today, after)."""

    today: CoverageRollup
    after: CoverageRollup
    changed: list[tuple[str, str | None, str | None]]


def _rollup(assessment: Any, rows: Iterable[Any]) -> tuple[CoverageRollup, dict[str, str | None]]:
    """The client dashboard's own derivation (`routes/clients.attack_dashboard`):
    R3's computed statuses, the one pending set, the one rollup."""
    valid = all_codes()
    eff = effective_coverage(assessment, rows)
    statuses = {r.technique_code: r.status for r in eff if r.technique_code in valid}
    withheld = pending_codes(eff, parents_computed=parents_computed(assessment))
    return compute(statuses, withheld), statuses


def compare(assessment: Any, base_rows: Sequence[Any], what_if_rows: Sequence[Any]) -> Comparison:
    """Both sides computed the same way from the same assessment's rules."""
    today, before = _rollup(assessment, base_rows)
    after, now = _rollup(assessment, what_if_rows)
    changed = [
        (code, before.get(code), now.get(code))
        for code in sorted(set(before) | set(now))
        if before.get(code) != now.get(code)
    ]
    return Comparison(today=today, after=after, changed=changed)


def confirmed_base(db: Session, service_id: uuid.UUID) -> AttackAssessment | None:
    """The newest ATT&CK assessment of the service that is APPROVED or
    RELEASED, whose statuses R3 computes, and whose review queue is empty:
    #554's (c1) plus the review gate, the same predicate the release flip
    re-computes. None when no assessment meets all three -- a draft, a
    pre-R3 approval and an unreviewed queue are none of them "confirmed"."""
    candidates = (
        db.execute(
            select(AttackAssessment)
            .where(
                AttackAssessment.service_id == service_id,
                AttackAssessment.status.in_(
                    (AttackAssessmentStatus.APPROVED, AttackAssessmentStatus.RELEASED)
                ),
            )
            .order_by(AttackAssessment.version.desc())
        )
        .scalars()
        .all()
    )
    for assessment in candidates:
        if statuses_computed(assessment) and not unreviewed_codes(db, assessment):
            return assessment
    return None


def is_stale(db: Session, service_id: uuid.UUID, base_id: uuid.UUID) -> bool:
    """True when a newer assessment is now the confirmed base. A stale
    scenario is shown as stale, never re-based or recomputed silently."""
    newest = confirmed_base(db, service_id)
    return newest is not None and newest.id != base_id


#: Techniques per AI call, as `mitre_map` batches them.
BATCH_SIZE = 25


def _without(tools: Iterable[Any] | None, gone: set[str]) -> list[str]:
    return [t for t in tools or [] if isinstance(t, str) and _key(t) not in gone]


def batch_inputs(
    base_rows: Sequence[Any],
    affected: Sequence[str],
    removed: Sequence[str],
    capability_payload: Sequence[Mapping[str, Any]],
    *,
    size: int = BATCH_SIZE,
) -> list[dict[str, Any]]:
    """One input per batch of affected techniques: the slice, those frozen rows
    with the removed tools taken out, the removals, and the client's tools that
    remain (the same four fields `mitre_map` sends for a capability)."""
    gone = {_key(n) for n in removed}
    by_code = {r.technique_code: r for r in base_rows}
    remaining = [dict(c) for c in capability_payload if _key(c.get("name")) not in gone]
    out: list[dict[str, Any]] = []
    for i in range(0, len(affected), size):
        codes = list(affected[i : i + size])
        out.append(
            {
                "technique_codes": codes,
                "frozen_rows": [
                    {
                        "technique_code": code,
                        **{name: _without(getattr(by_code[code], name), gone) for name in _LISTS},
                    }
                    for code in codes
                ],
                "removed_tools": list(removed),
                "available_tools": remaining,
            }
        )
    return out


@dataclass(frozen=True)
class Merged:
    """Every affected technique's new lists, the accepted AI rows, the counted
    drops, and the techniques no batch re-assessed."""

    lists: dict[str, dict[str, list[str]]]
    accepted: list[dict[str, Any]]
    dropped: dict[str, int]
    not_reassessed: list[str]


def merge_batches(inputs: Sequence[Mapping[str, Any]], parsed: Mapping[int, ParsedDelta]) -> Merged:
    """Join the batches. A batch with no usable answer (`parsed` has no entry
    for it) is NOT the frozen row passed off as re-assessed: its techniques
    take the removal alone -- the removed tools stripped by code -- and are
    named in `not_reassessed`, which the result discloses."""
    lists: dict[str, dict[str, list[str]]] = {}
    accepted: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    not_reassessed: list[str] = []
    for i, batch in enumerate(inputs):
        answer = parsed.get(i)
        if answer is None:
            for row in batch["frozen_rows"]:
                lists[row["technique_code"]] = {name: list(row[name]) for name in _LISTS}
                not_reassessed.append(row["technique_code"])
            continue
        lists.update(answer.lists)
        accepted.extend(answer.accepted)
        dropped.update(answer.dropped)
    return Merged(
        lists=lists, accepted=accepted, dropped=dict(dropped), not_reassessed=sorted(not_reassessed)
    )


#: The AI purpose. Registered only once #806 releases its prompt text.
PURPOSE = "attack_scenario_delta"


def analysis_available() -> bool:
    """True when the what-if's AI job is registered. False until #806's prompt
    text lands; the run route refuses with a typed 503 rather than failing
    inside a background job."""
    from app.ai.engine import registered_jobs

    return PURPOSE in registered_jobs()
