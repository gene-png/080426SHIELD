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
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.redact import RedactionMode, redact_for_ai
from app.attack.analytics import CoverageRollup, compute
from app.attack.catalog import NOT_PREVENTABLE, all_codes
from app.attack.citations import Candidate, CitationResolver
from app.attack.computed import (
    _ASSESSED,
    InPlace,
    awaiting_review_count,
    capability,
    effective_coverage,
)
from app.attack.parents import is_computed_parent
from app.attack.pending import pending_codes, row_tools
from app.attack.release_readiness import unreviewed_codes
from app.attack.rules import parents_computed, statuses_computed
from app.models.attack_assessment import AttackAssessment, AttackAssessmentStatus
from app.models.capability import CapabilityListStatus, SecurityFunction

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


@dataclass(frozen=True)
class Removed:
    """The removed tools and every spelling of them, decided ONCE and used by
    every question this module asks about a removal: which techniques are
    affected, which functions they lost, what the frozen rows keep, and which
    tools stay (#815 review rounds 1 and 2, F2).

    A list can hold `<Client> SOC Platform` AND `[CLIENT] SOC Platform`
    (`citations.py`, the alias tier): one tool, which the egress shows the
    model as one string. A name is a spelling of a removed tool when its
    STORED form is a removed tool's stored or shown form, or its SHOWN form is
    a removed tool's stored form. Shown-to-shown alone is NOT a match: two
    distinct tools can redact to one placeholder, and a derived key never
    decides on its own (CLAUDE.md, the derived-key tier). Such a kept tool is
    kept, and `shares_shown_form` names it so its credit can be refused.
    """

    names: tuple[str, ...]
    stored: frozenset[str]
    shown: frozenset[str]
    show: Callable[[str], str]

    def covers(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        key = _key(name)
        return key in self.stored or key in self.shown or self.show(name) in self.stored

    def shares_shown_form(self, name: str) -> bool:
        """A kept tool the model cannot tell apart from a removed one."""
        return not self.covers(name) and self.show(name) in self.shown


def removed_spellings(
    names: Iterable[str],
    *,
    client_org_name: str | None,
    redaction_mode: RedactionMode,
    name_hints: Iterable[str] = (),
) -> Removed:
    """The shown form is asked of `redact_for_ai`, the egress's own redactor,
    with the egress's mode and hints -- what `CitationResolver` asks when it
    indexes its aliases, so the two cannot disagree."""
    hints = tuple(name_hints)

    def show(name: str) -> str:
        shown, _counts = redact_for_ai(
            name,
            mode=redaction_mode,
            client_org_name=client_org_name or None,
            name_hints=hints,
        )
        return _key(shown)

    names = tuple(names)
    return Removed(
        names=names,
        stored=frozenset(_key(n) for n in names),
        shown=frozenset(show(n) for n in names),
        show=show,
    )


def _plain(names: Iterable[str]) -> Removed:
    """Removals compared by stored spelling only: for callers with no client
    to redact for (the pure tests). The routes always pass `removed_spellings`."""
    return removed_spellings(names, client_org_name=None, redaction_mode="off")


def _as_removed(removed: Removed | Iterable[str]) -> Removed:
    return removed if isinstance(removed, Removed) else _plain(removed)


def remaining_tools(candidates: Iterable[Any], removed: Removed) -> list[Any]:
    """The client's tools that stay, by `.name`: every spelling of a removed
    tool goes."""
    return [c for c in candidates if not removed.covers(c.name)]


def _cited(rows: Iterable[Any]) -> dict[str, str]:
    """Every tool the rows cite, case-folded to the name as first stored."""
    out: dict[str, str] = {}
    for row in rows:
        for tool in row_tools(row):
            if isinstance(tool, str) and tool.strip():
                out.setdefault(_key(tool), tool)
    return out


def cited_key(name: object) -> str:
    """A tool name as this module compares names: trimmed and case-folded."""
    return _key(name)


def cited_tools(rows: Iterable[Any]) -> list[str]:
    """The tools the rows cite, one spelling each, sorted case-insensitively:
    the names a removal may pick."""
    return sorted(_cited(rows).values(), key=str.casefold)


def resolve_removed(rows: Sequence[Any], names: Iterable[str]) -> list[str]:
    """The removals as the names the assessment cites, de-duplicated, in the
    order given. Refuses any name the assessment does not cite: a guess would
    assess a tool nobody named. An EMPTY list is valid since slice B -- a
    what-if may only add -- and `require_change` refuses a change of nothing."""
    cited = _cited(rows)
    out: list[str] = []
    for name in names:
        found = cited.get(_key(name))
        if found is None:
            raise UnknownTool(str(name))
        if found not in out:
            out.append(found)
    return out


# --- slice B: tools the client doesn't have ------------------------------------

#: The advisor's cap (14:58Z): added tools per what-if, to bound the cost.
MAX_ADDED = 10
#: The longest name, vendor or category an admin may enter.
MAX_TEXT = 200

#: An added tool's declared functions, as the Tech Debt classification spells
#: them (`SecurityFunction`), and the coverage flag each maps to, in D/P/R order.
_FUNCTION_FLAG = {
    SecurityFunction.DETECT.value: "detection",
    SecurityFunction.PREVENT.value: "prevention",
    SecurityFunction.RESPOND.value: "response",
}


@dataclass(frozen=True)
class AddedTool:
    """A tool the client does not have, as the admin described it. Its
    functions are EVIDENCE for the AI, as a real tool's classification is;
    code never credits a function from them."""

    name: str
    vendor: str | None
    category: str | None
    functions: tuple[str, ...]

    def payload(self) -> dict[str, Any]:
        """The same four fields `mitre_map` sends for a capability."""
        return {
            "name": self.name,
            "vendor": self.vendor,
            "category": self.category,
            "security_functions": list(self.functions),
        }

    @classmethod
    def from_stored(cls, entry: Mapping[str, Any]) -> AddedTool:
        return cls(
            name=entry["name"],
            vendor=entry.get("vendor"),
            category=entry.get("category"),
            functions=tuple(entry.get("security_functions") or ()),
        )


class AddedToolRefused(ValueError):
    """An added tool the what-if will not take, by the name the admin typed."""

    def __init__(self, name: str = "") -> None:
        super().__init__(name)
        self.name = name


class AlreadyClients(AddedToolRefused):
    """A spelling of a tool the client has (copy B4)."""


class Indistinct(AddedToolRefused):
    """Shown to the AI as the same string as another tool (copy B5)."""


class NoFunctions(AddedToolRefused):
    """No Detect, Prevent or Respond chosen (copy B6)."""


class BlankName(AddedToolRefused):
    """No name."""


class Duplicate(AddedToolRefused):
    """The same tool twice in one change list."""


class TooLong(AddedToolRefused):
    """A name, vendor or category longer than `MAX_TEXT`."""


class BadFunction(AddedToolRefused):
    """A function that is not detect, prevent or respond."""

    def __init__(self, name: str, value: object) -> None:
        super().__init__(name)
        self.value = value


class TooMany(ValueError):
    """More than `MAX_ADDED` added tools (copy B7)."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"at most {limit} added tools")
        self.limit = limit


def _text(value: object) -> str | None:
    return value.strip() or None if isinstance(value, str) else None


def validate_added(
    raw: Sequence[Any],
    *,
    client_tools: Iterable[str],
    client_org_name: str | None,
    redaction_mode: RedactionMode,
    name_hints: Iterable[str] = (),
    limit: int = MAX_ADDED,
) -> list[AddedTool]:
    """The admin's added tools, or a typed refusal naming the first bad one.

    A name that is any spelling of a client tool is refused (slice A's
    cross-tier rule, `Removed.covers`: an admin cannot type a client tool, or
    its `[CLIENT]` twin, and have it treated as new). A name the model would be
    SHOWN as the same string as a client tool or another added tool is refused
    too: its credit could not be told apart (`Removed.shares_shown_form`)."""
    raw = list(raw)
    if len(raw) > limit:
        raise TooMany(limit)
    client = removed_spellings(
        client_tools,
        client_org_name=client_org_name,
        redaction_mode=redaction_mode,
        name_hints=name_hints,
    )
    out: list[AddedTool] = []
    seen: list[str] = []
    for entry in raw:
        entry = entry if isinstance(entry, Mapping) else {}
        name = _text(entry.get("name"))
        if name is None:
            raise BlankName()
        vendor, category = _text(entry.get("vendor")), _text(entry.get("category"))
        if any(v is not None and len(v) > MAX_TEXT for v in (name, vendor, category)):
            raise TooLong(name)
        if _key(name) in {_key(n) for n in seen}:
            raise Duplicate(name)
        functions = entry.get("security_functions")
        functions = list(functions) if isinstance(functions, list) else []
        for value in functions:
            if value not in _FUNCTION_FLAG:
                raise BadFunction(name, value)
        if not functions:
            raise NoFunctions(name)
        if client.covers(name):
            raise AlreadyClients(name)
        earlier = removed_spellings(
            seen,
            client_org_name=client_org_name,
            redaction_mode=redaction_mode,
            name_hints=name_hints,
        )
        if (
            client.shares_shown_form(name)
            or earlier.covers(name)
            or earlier.shares_shown_form(name)
        ):
            raise Indistinct(name)
        seen.append(name)
        out.append(
            AddedTool(
                name=name,
                vendor=vendor,
                category=category,
                functions=tuple(f for f in _FUNCTION_FLAG if f in functions),
            )
        )
    return out


def require_change(removed: Sequence[str], added: Sequence[AddedTool]) -> None:
    """A what-if must remove or add something (copy B8)."""
    if not removed and not added:
        raise EmptyChangeList("choose at least one tool to remove or add")


def open_functions(
    rows: Iterable[Any],
    added: Sequence[AddedTool],
    *,
    removed: Removed | None = None,
) -> dict[str, list[str]]:
    """The techniques an added tool could change, and the functions it may be
    asked about there: for every assessed, non-parent technique, each function
    some added tool declares that is NOT in place in the frozen row (after the
    removal), judged by R3's own `computed.capability`. Prevention is never
    open where the technique cannot be prevented. Techniques with none are
    left out."""
    declared = {_FUNCTION_FLAG[f] for t in added for f in t.functions}
    if not declared:
        return {}
    gone = removed if removed is not None else _plain(())
    out: dict[str, list[str]] = {}
    for row in rows:
        code = row.technique_code
        if row.status not in _ASSESSED or is_computed_parent(code):
            continue
        opened = []
        for flag, list_name in _FLAGS:
            if flag not in declared:
                continue
            if flag == "prevention" and code in NOT_PREVENTABLE:
                continue
            tools = _without(getattr(row, list_name), gone)
            if capability(tools, row.unconfirmed_citations) is not InPlace.IN_PLACE:
                opened.append(flag)
        if opened:
            out[code] = opened
    return out


def split_higher(
    comparison: Comparison,
    affected: Iterable[str],
    accepted: Iterable[Mapping[str, Any]],
    *,
    added_names: Iterable[str],
) -> tuple[list[str], list[str]]:
    """The affected techniques that would score higher, split by cause:
    (credited to a REMAINING tool -- copy 18's warning; credited to an ADDED
    tool -- B11's result). A rise counts for an added tool only where an
    accepted row names one WITH a function: a row with every function false
    explains nothing."""
    added = {_key(n) for n in added_names}
    credited = {
        a["technique_code"]
        for a in accepted
        if _key(a.get("tool")) in added and any(a.get(f) is True for f, _ in _FLAGS)
    }
    rises = scored_higher(comparison, affected)
    return (
        [c for c in rises if c not in credited],
        [c for c in rises if c in credited],
    )


def affected_codes(rows: Iterable[Any], removed: Removed | Iterable[str]) -> list[str]:
    """The techniques any spelling of a removed tool appears on, in any of the
    three lists, sorted. These, and only these, are sent to the AI."""
    gone = _as_removed(removed)
    return sorted(row.technique_code for row in rows if any(gone.covers(t) for t in row_tools(row)))


@dataclass(frozen=True)
class ParsedDelta:
    """The accepted answer: new D/P/R lists for EVERY asked technique (empty
    when the AI named nothing for it), and the counted drops by reason."""

    lists: dict[str, dict[str, list[str]]]
    accepted: list[dict[str, Any]] = field(default_factory=list)
    dropped: dict[str, int] = field(default_factory=dict)


def parse_delta(
    data: Mapping[str, Any],
    *,
    asked: Iterable[str],
    available: Iterable[str | Candidate],
    lost: Mapping[str, Iterable[str]],
    opened: Mapping[str, Iterable[str]] | None = None,
    added_names: Iterable[str] = (),
    indistinct: Iterable[str] = (),
    client_org_name: str | None = None,
    redaction_mode: RedactionMode = "strict",
    name_hints: tuple[str, ...] = (),
) -> ParsedDelta:
    """Validate one batch's answer against the contract.

    `asked` is the batch's slice of affected techniques; `available` is the
    client's tools minus the removed ones. A tool is resolved by `mitre_map`'s
    own `CitationResolver`, called with the egress's org name, mode and hints,
    so a client-named tool cited in the redacted form the model was shown
    resolves to its stored name (#33 finding 5). Only a CONFIRMED resolution is
    credited: an inference (a word of a name, a vendor) has no review queue
    here, so it is dropped and counted as `tool_unconfirmed`.

    `lost` is each technique's `lost_functions` (see `batch_inputs`): the AI is
    asked only about those, so a row setting any OTHER function true is
    dropped whole and counted as `function_not_lost` (the advisor, 05:25Z).

    `opened` is each technique's `open_functions` (slice B): a function there
    may be credited only to an ADDED tool (`added_names`). A row crediting one
    of the client's tools for a function that is open and not lost is dropped
    whole and counted as `tool_not_added`."""
    rows = data.get("rows") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ScenarioShapeError("the answer has no `rows` list")
    asked = list(asked)
    asked_set = set(asked)
    indistinct_names = set(indistinct)
    opened = opened or {}
    added_keys = {_key(n) for n in added_names}
    resolver = CitationResolver(
        [c if isinstance(c, Candidate) else Candidate(name=c) for c in available],
        client_org_name=client_org_name,
        redaction_mode=redaction_mode,
        name_hints=name_hints,
    )
    lists = {code: {name: [] for name in _LISTS} for code in asked}
    accepted: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, Mapping):
            dropped["not_an_object"] += 1
            continue
        code = row.get("technique_code")
        # `isinstance` first: a list or dict is unhashable, and `in` on a set
        # would raise and lose every batch's answer (#815 review, F1).
        if not isinstance(code, str) or code not in asked_set:
            dropped["technique_outside_slice"] += 1
            continue
        resolution = resolver.resolve(row.get("tool"))
        if resolution.name is None:
            dropped["tool_outside_change"] += 1
            continue
        # `indistinct`: kept tools the model is shown as the SAME string as a
        # removed one (`Removed.shares_shown_form`). Which one it meant cannot
        # be known, so the credit is refused and counted, never given.
        if not resolution.confirmed or resolution.name in indistinct_names:
            dropped["tool_unconfirmed"] += 1
            continue
        tool = resolution.name
        flags = {flag: row.get(flag) for flag, _ in _FLAGS}
        # `bool` only: `1`, "yes" and a missing key are refused, never coerced.
        if not all(isinstance(v, bool) for v in flags.values()):
            dropped["not_boolean"] += 1
            continue
        lost_here = set(lost.get(code) or ())
        open_here = set(opened.get(code) or ())
        claimed = {flag for flag, value in flags.items() if value}
        if claimed - lost_here - open_here:
            dropped["function_not_lost"] += 1
            continue
        if (claimed - lost_here) and _key(tool) not in added_keys:
            dropped["tool_not_added"] += 1
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
    #: Q4: techniques scored as if tools awaiting review were not in place.
    today_awaiting: int = 0
    after_awaiting: int = 0


def _rollup(
    assessment: Any, rows: Iterable[Any]
) -> tuple[CoverageRollup, dict[str, str | None], int]:
    """The client dashboard's own derivation (`routes/clients.attack_dashboard`):
    R3's computed statuses, the one pending set, the one rollup, and Q4's
    awaiting-review count (`computed.awaiting_review_count`)."""
    valid = all_codes()
    eff = effective_coverage(assessment, rows)
    statuses = {r.technique_code: r.status for r in eff if r.technique_code in valid}
    withheld = pending_codes(eff, parents_computed=parents_computed(assessment))
    return compute(statuses, withheld), statuses, awaiting_review_count(eff)


def compare(assessment: Any, base_rows: Sequence[Any], what_if_rows: Sequence[Any]) -> Comparison:
    """Both sides computed the same way from the same assessment's rules."""
    today, before, today_awaiting = _rollup(assessment, base_rows)
    after, now, after_awaiting = _rollup(assessment, what_if_rows)
    changed = [
        (code, before.get(code), now.get(code))
        for code in sorted(set(before) | set(now))
        if before.get(code) != now.get(code)
    ]
    return Comparison(
        today=today,
        after=after,
        changed=changed,
        today_awaiting=today_awaiting,
        after_awaiting=after_awaiting,
    )


#: The order "higher" means: Gap < Partial < Covered. Not applicable and an
#: unscored technique are not on it, so a move to or from them is never higher.
_RANK = {"gap": 0, "partial": 1, "covered": 2}


def scored_higher(comparison: Comparison, affected: Iterable[str]) -> list[str]:
    """The affected techniques whose computed status after the change ranks
    HIGHER than in the base, sorted. Removing tools cannot add capability, so
    each one is the AI crediting a remaining tool the last confirmed assessment
    did not (the advisor's addition, 05:05Z): shown, never hidden."""
    affected = set(affected)
    return sorted(
        code
        for code, before, after in comparison.changed
        if code in affected and before in _RANK and after in _RANK and _RANK[after] > _RANK[before]
    )


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


def _aware(value: datetime) -> datetime:
    """SQLite hands timestamps back naive; every stored one is UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def tools_added_since(
    offered: Iterable[Any],
    lists: Iterable[Any],
    created_at: Mapping[str, datetime],
    base_approved_at: datetime | None,
    overridden_at: Mapping[str, datetime] | None = None,
) -> list[str] | None:
    """The offered tools added to the client's list, or brought into scope,
    AFTER the base was approved (the advisor's (b2) at 08:10Z and (ii) at
    08:57Z), by name; or None when that cannot be checked.

    `offered` are `CapabilityProvenance`s (`.capability.name`, `.item_id`);
    `created_at` maps an item id to its row's `created_at`; `overridden_at` maps
    an item id to the time of its latest
    `capability_item.security_classification_overridden` audit entry. A tool
    counts when the capability item it was offered from was created after
    `base_approved_at`, OR had its security classification overridden after it
    -- an OLD row an override brought into scope is as new to the AI as a new
    row. For a live row the item is the row itself; for a snapshot entry, the
    row its `item_id` names.

    None -- NEVER an empty list -- whenever the answer is not known, because
    missing data defaults to unconfirmed:
    - the base has no approval time;
    - ANY of the client's lists was approved before migration 0043 (APPROVED or
      RELEASED with no `approved_membership`): its membership at any earlier
      moment was never recorded, so it cannot be checked;
    - an offered tool names no item, or an item whose row is gone.

    Four limits, stated here and in #815's body:
    - **a RENAME after the base was approved is missed.** A renamed row keeps
      its `created_at`, so the tool reads as one the base had;
    - **lists approved before 0043 cannot be checked**, which is the second
      None above, never a guess;
    - **a discarded draft re-uploaded OVERCOUNTS.** Every re-uploaded tool is a
      new row, so each reads as added though the base may have had it;
    - **an override on a row ALREADY in scope OVERCOUNTS.** The audit entry
      records that an override happened, not that it changed the row's scope:
      overriding a provisional negative (in scope until a consultant confirms
      it) or re-picking an in-scope row's functions after the base reads as
      "brought into scope" though the base was offered that row (#815 review).
    """
    if base_approved_at is None:
        return None
    if any(
        cl.status in (CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED)
        and cl.approved_membership is None
        for cl in lists
    ):
        return None
    base = _aware(base_approved_at)
    overrides = overridden_at or {}
    added: list[str] = []
    for p in offered:
        made = created_at.get(p.item_id) if p.item_id else None
        if made is None:
            return None
        override = overrides.get(p.item_id)
        if _aware(made) > base or (override is not None and _aware(override) > base):
            added.append(p.capability.name)
    return sorted(added, key=str.casefold)


#: Techniques per AI call, as `mitre_map` batches them.
BATCH_SIZE = 25


def _without(tools: Iterable[Any] | None, gone: Removed) -> list[str]:
    return [t for t in tools or [] if isinstance(t, str) and not gone.covers(t)]


def _lost(row: Any, gone: Removed) -> list[str]:
    """The functions a removed tool was listed for on this row, in D/P/R
    order: the only ones the AI is asked about."""
    return [
        flag
        for flag, list_name in _FLAGS
        if any(gone.covers(t) for t in getattr(row, list_name) or [])
    ]


def batch_inputs(
    base_rows: Sequence[Any],
    affected: Sequence[str],
    removed: Removed | Sequence[str],
    capability_payload: Sequence[Mapping[str, Any]],
    *,
    size: int = BATCH_SIZE,
    added: Sequence[AddedTool] = (),
) -> list[dict[str, Any]]:
    """One input per batch of affected techniques: the slice, those frozen rows
    with the removed tools taken out, the removals, and the client's tools that
    remain (the same four fields `mitre_map` sends for a capability)."""
    gone = _as_removed(removed)
    by_code = {r.technique_code: r for r in base_rows}
    remaining = [dict(c) for c in capability_payload if not gone.covers(c.get("name"))]
    added_payload = [t.payload() for t in added]
    opened = open_functions(base_rows, added, removed=gone)
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
                "lost_functions": {code: _lost(by_code[code], gone) for code in codes},
                "open_functions": {code: list(opened.get(code, [])) for code in codes},
                "removed_tools": list(gone.names),
                "added_tools": added_payload,
                "available_tools": remaining + added_payload,
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
    """Join the batches. Every affected technique starts from its frozen row,
    the removed tools stripped by code, and KEEPS those credits: an answered
    batch can only ADD tools to them (the advisor, 05:25Z), so a tool the AI
    leaves out never loses a function the last confirmed assessment gave it.

    A batch with no usable answer (`parsed` has no entry for it) is NOT the
    frozen row passed off as re-assessed: its techniques take the removal
    alone and are named in `not_reassessed`, which the result discloses."""
    lists: dict[str, dict[str, list[str]]] = {}
    accepted: list[dict[str, Any]] = []
    dropped: Counter[str] = Counter()
    not_reassessed: list[str] = []
    for i, batch in enumerate(inputs):
        answer = parsed.get(i)
        for row in batch["frozen_rows"]:
            code = row["technique_code"]
            added = answer.lists.get(code, {}) if answer is not None else {}
            lists[code] = {
                name: list(row[name]) + [t for t in added.get(name, []) if t not in row[name]]
                for name in _LISTS
            }
            if answer is None:
                not_reassessed.append(code)
        if answer is not None:
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
