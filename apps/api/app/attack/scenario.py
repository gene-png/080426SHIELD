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

import re
import unicodedata
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
#: Unicode categories a name, vendor or category may not hold (#826): every
#: control character (Cc: C0, DEL and C1), the line and paragraph separators
#: (Zl, Zp), and a lone surrogate (Cs; a valid pair such as an emoji is ONE
#: code point here, not Cs). Named by category, so the set is Unicode's, not a
#: hand list. Two of them Postgres cannot store in the change list (jsonb),
#: each an untyped 500 at insert, both measured on postgres:16: NUL
#: ("unsupported Unicode escape sequence") and a lone surrogate ("Unicode low
#: surrogate must follow a high surrogate", #831 review, F2). The rest store,
#: but a name is one line of visible text. Format characters (Cf, a zero-width
#: joiner) are deliberately NOT refused: scripts use them.
_UNPRINTABLE = frozenset({"Cc", "Zl", "Zp", "Cs"})

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
    """A name, vendor or category longer than `MAX_TEXT`; `field` is the
    panel's label for it."""

    def __init__(self, name: str, field: str) -> None:
        super().__init__(name)
        self.field = field


class Unprintable(AddedToolRefused):
    """A name, vendor or category holding a character in `_UNPRINTABLE`;
    `field` is the panel's label for it (#826)."""

    def __init__(self, name: str, field: str) -> None:
        super().__init__(name)
        self.field = field


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
    check_characters: bool = True,
) -> list[AddedTool]:
    """The admin's added tools, or a typed refusal naming the first bad one.

    Whether a name can stand beside the client's tools is decided by CALLING
    the resolver the run uses (`CitationResolver`, with the egress's org name,
    mode and hints), never by a second key: it collapses internal whitespace
    and indexes the shown forms, and a looser check here let a name through
    that the run then could not credit (#818 review, F1). An added tool is
    refused when any string the model can cite for it -- its name, or the form
    it is SHOWN as -- is a hit in the resolver's real-name or alias tier
    (`CitationResolver.named_by`), CONFIRMED OR AMBIGUOUS, among the client's
    and earlier-added tools. Ambiguous counts: when the client's own tools
    already collide, a name that resolves ambiguously is still their tool, and
    a confirmed-only check let it through (#818 narrow review). Those two tiers
    are the only ones that index a name, so a name that clears this check
    cannot disturb another tool's resolution either. An inference (a word of a
    name, a vendor) never decides a credit, so it does not refuse.

    A refusal names the cause: a spelling of a client tool (B4/B4b), a second
    spelling of an earlier added tool, or a name the model could not tell apart
    from another tool (B5)."""
    raw = list(raw)
    if len(raw) > limit:
        raise TooMany(limit)
    hints = tuple(name_hints)
    client = list(dict.fromkeys(t for t in client_tools if isinstance(t, str) and t.strip()))

    def resolver(names: Sequence[str], mode: RedactionMode = redaction_mode) -> CitationResolver:
        return CitationResolver(
            [Candidate(name=n) for n in names],
            client_org_name=client_org_name,
            redaction_mode=mode,
            name_hints=hints,
        )

    def citable(name: str) -> set[str]:
        """The strings the model can cite for a tool: as stored and as shown."""
        shown, _counts = redact_for_ai(
            name, mode=redaction_mode, client_org_name=client_org_name or None, name_hints=hints
        )
        return {name, shown}

    out: list[AddedTool] = []
    for entry in raw:
        entry = entry if isinstance(entry, Mapping) else {}
        name = _text(entry.get("name"))
        if name is None:
            raise BlankName()
        vendor, category = _text(entry.get("vendor")), _text(entry.get("category"))
        # The panel's own labels (B2).
        fields = (
            ("Name", name),
            ("Vendor (optional)", vendor),
            ("Category (optional)", category),
        )
        for label, value in fields:
            if value is not None and len(value) > MAX_TEXT:
                raise TooLong(name, label)
        functions = entry.get("security_functions")
        functions = list(functions) if isinstance(functions, list) else []
        for value in functions:
            # `isinstance` first: a list or dict is unhashable and `in` on a
            # dict would raise -- an untyped 500 (#818 review, F2).
            if not isinstance(value, str) or value not in _FUNCTION_FLAG:
                raise BadFunction(name, value)
        if not functions:
            raise NoFunctions(name)

        earlier = [t.name for t in out]
        before = resolver([*client, *earlier])
        # Taken in a NAME tier, confirmed or ambiguous: an ambiguity among the
        # client's own tools is still their tool (#818 narrow review, 1).
        if any(before.named_by(form) for form in citable(name)):
            raise _why_refused(name, before, resolver(client, "off"), client, earlier, citable)
        # After the checks above, so a client's own tool spelled with a tab is
        # still named as theirs (B4), the more useful refusal (#826). Skipped
        # when re-checking STORED tools for collisions (`check_characters`):
        # a row stored before #826 is not a collision (#831 review, F1).
        for label, value in fields if check_characters else ():
            if value is not None and any(unicodedata.category(ch) in _UNPRINTABLE for ch in value):
                raise Unprintable(name, label)
        out.append(
            AddedTool(
                name=name,
                vendor=vendor,
                category=category,
                functions=tuple(f for f in _FUNCTION_FLAG if f in functions),
            )
        )
    return out


def _why_refused(
    name: str,
    before: CitationResolver,
    client_real: CitationResolver,
    client: Sequence[str],
    earlier: Sequence[str],
    citable: Callable[[str], set[str]],
) -> AddedToolRefused:
    """The cause, for a name the resolver could not keep apart. A spelling of a
    client tool: the name itself already resolves to one (case, whitespace, or
    its `[CLIENT]` twin), or the form it is SHOWN as is a client tool's stored
    name. A second spelling of an earlier added tool, likewise. Anything else
    -- two tools shown as one placeholder -- cannot be told apart."""
    own = before.named_by(name)
    shown_hits = {n for form in citable(name) - {name} for n in client_real.named_by(form)}
    if own & set(client) or shown_hits & set(client):
        return AlreadyClients(name)
    if own & set(earlier):
        return Duplicate(name)
    return Indistinct(name)


# --- slice C: the chat box's deterministic matcher -------------------------------

#: The longest description the chat box takes (copy C8).
MAX_CHAT = 500

_LEAD = re.compile(r"^\s*what\s+if(?:\s+we)?\s+", re.IGNORECASE)
#: Clause breaks: a comma, a semicolon, the word "and", or a full stop that
#: ends a sentence -- never the one inside a name like `Tenable.io`.
_SPLIT = re.compile(r"\s*(?:[,;]|\.(?=\s|$)|\band\b)\s*", re.IGNORECASE)
_REMOVE = re.compile(r"^(?:remove|retire|drop|cut)\s+(?P<a>.+)$", re.IGNORECASE)
_ADD = re.compile(r"^(?:add|introduce)\s+(?P<a>.+)$", re.IGNORECASE)
#: The verb is read from WHICH alternative matched: IGNORECASE matches a
#: long s as "s", and `.lower()` keeps it, so a lookup keyed on the typed
#: text raised (#824 narrow review, F1).
_SWAP = re.compile(r"^(?:(?P<swap>swap)|(?P<replace>replace))\s+(?P<rest>.+)$", re.IGNORECASE)
#: Where a swap's two names may divide: "swap X for Y", "replace X with Y".
_SWAP_JOIN = {
    "swap": re.compile(r"\s+for\s+", re.IGNORECASE),
    "replace": re.compile(r"\s+with\s+", re.IGNORECASE),
}
_QUOTES = "\"'\u201c\u201d\u2018\u2019"


@dataclass(frozen=True)
class NotUnderstood:
    """A clause the matcher will not guess at: the clause as typed, why, and
    (for `already_clients`) the tool it named."""

    text: str
    reason: str
    name: str | None = None


@dataclass(frozen=True)
class ParsedChange:
    """A PROPOSED change list. It pre-fills the picker; nothing is stored or
    run from it -- Continue and Run stay the only paths."""

    removed: list[str]
    added: list[str]
    not_understood: list[NotUnderstood]


class _Refused(Exception):
    def __init__(self, reason: str, name: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.name = name


@dataclass(frozen=True)
class _Clauses:
    """A description split into clauses, with what the split could not decide."""

    texts: list[str]
    #: clauses where two cited names claim overlapping words: neither is chosen
    clashing: frozenset[int]
    #: `span(i, j)`: clauses i..j-1 exactly as typed, separators and all
    span: Callable[[int, int], str]


def _clauses(text: str, forms: Sequence[str]) -> _Clauses:
    """The text split into clauses, WITHOUT cutting a cited tool's name: a
    cited name that itself contains a break ("Identity and Access Manager",
    "Acme, Inc. EDR") is held whole while the rest is split (#824 review, B1).
    A name the base does not cite cannot be protected this way; the caller
    refuses a span that may have been cut instead (see `parse_change`).

    Held words are found as POSITIONS and the breaks inside them skipped, so
    nothing is substituted into the text and no typed character can collide
    with a marker (the earlier NUL-sentinel form raised on a typed NUL, #824
    narrow review). Two cited names claiming overlapping words are NOT
    resolved by length or order: the clause is reported as `clashing`."""
    text = _LEAD.sub("", text.strip()).rstrip("?").strip()
    found: list[tuple[int, int]] = []
    for name in {f for f in forms if _SPLIT.search(f)}:
        pattern = re.compile(
            r"(?<!\w)" + r"\s+".join(re.escape(w) for w in name.split()) + r"(?!\w)",
            re.IGNORECASE,
        )
        found.extend((m.start(), m.end()) for m in pattern.finditer(text))
    # [start, end, how many matches]: overlapping matches merge into one.
    regions: list[list[int]] = []
    for lo, hi in sorted(found):
        if regions and lo < regions[-1][1]:
            regions[-1][1] = max(regions[-1][1], hi)
            regions[-1][2] += 1
        else:
            regions.append([lo, hi, 1])

    def held(lo: int, hi: int, *, clash: bool = False) -> bool:
        return any(a < hi and lo < b and (n > 1 or not clash) for a, b, n in regions)

    pieces: list[tuple[str, int, int]] = []
    at = 0
    breaks = [m for m in _SPLIT.finditer(text) if not held(m.start(), m.end())]
    for brk in [*breaks, None]:
        stop = brk.start() if brk is not None else len(text)
        if text[at:stop].strip():
            pieces.append((text[at:stop].strip(), at, stop))
        if brk is not None:
            at = brk.end()

    def span(i: int, j: int) -> str:
        return text[pieces[i][1] : pieces[j - 1][2]].strip()

    return _Clauses(
        texts=[p for p, _a, _b in pieces],
        clashing=frozenset(i for i, (_p, a, b) in enumerate(pieces) if held(a, b, clash=True)),
        span=span,
    )


def _bare(name: str) -> str:
    return name.strip().strip(_QUOTES).strip()


#: The chat box's AI reading trims a name the same way (`scenario_intent`).
bare_name = _bare


def added_reason(exc: Exception) -> tuple[str, str | None]:
    """The not-understood reason, and for `already_clients` the tool, for an
    addition `validate_added` refused. One mapping for the matcher and the
    AI reading, so the two cannot disagree about a refusal."""
    if isinstance(exc, TooMany):
        return "too_many", None
    if isinstance(exc, AlreadyClients):
        return "already_clients", exc.name
    if isinstance(exc, Indistinct):
        return "indistinct", None
    if isinstance(exc, Duplicate):
        return "duplicate", None
    return "unrecognised", None


def _kind(clause: str) -> str:
    if _REMOVE.match(clause):
        return "remove"
    if _SWAP.match(clause):
        return "swap"
    if _ADD.match(clause):
        return "add"
    return "bare"


def parse_change(
    text: str,
    *,
    cited: Sequence[str],
    client_tools: Sequence[str],
    client_org_name: str | None,
    redaction_mode: RedactionMode,
    name_hints: Iterable[str] = (),
) -> ParsedChange:
    """Turn the admin's description into a proposed change list, by code
    (#802 slice C, approved 18:32Z; the AI parse is NOT part of it).

    The forms, case-insensitive: remove / retire / drop / cut X; add /
    introduce Y; swap X for Y; replace X with Y.

    **Never a fragment of a name** (#824 review, B1):
    - a cited name containing a clause break is held whole while splitting;
    - an add or a swap followed by a clause with no verb may be ONE name cut
      at a break ("add Endpoint Detection and Response Suite", "add Acme Inc.
      Scanner"), so the whole span is not understood rather than guessed;
    - a swap divides where its REMOVAL half names a cited tool; several such
      divisions are ambiguous, whatever their added halves do.

    A clause with no verb shares the previous verb only after a SUCCESSFUL
    removal ("retire X and Y"): a failed one shares nothing (B7), and an add
    never shares, since any words would make a "new tool".

    A clause that parses as a verb (remove, add or swap) AND whose whole text
    names a cited tool, through `named_by` with its alias tier ("Add Manager"),
    is not understood, wherever it stands, and nothing is proposed for it. It
    is read neither as the verb nor as the tool (the advisor's fallback after
    #824 round 5). Likewise a held cited name with a verb clause after its
    first break ("Splunk and Add Manager") is not removed (after round 6).

    Each name is checked by the code the create route uses: a removal must hit
    exactly ONE cited tool in the resolver's name tiers
    (`CitationResolver.named_by`: case, whitespace, the `[CLIENT]` twin, never
    an inference); an addition must pass `validate_added`, the cap of
    `MAX_ADDED` included (B4). So the chat never proposes a name Continue
    would refuse for its NAME; an added tool's functions are the admin's to
    choose before Continue. Anything else is not understood, quoted back."""
    hints = tuple(name_hints)
    resolver = CitationResolver(
        [Candidate(name=c) for c in cited],
        client_org_name=client_org_name,
        redaction_mode=redaction_mode,
        name_hints=hints,
    )
    removed: list[str] = []
    added: list[str] = []
    not_understood: list[NotUnderstood] = []

    def removal(name: str) -> str:
        hits = resolver.named_by(_bare(name))
        if not hits:
            raise _Refused("unknown_tool")
        if len(hits) > 1:
            raise _Refused("ambiguous_tool")
        (tool,) = hits
        parts = [p for p in _SPLIT.split(_bare(name)) if p.strip()]
        if len(parts) > 1 and all(len(resolver.named_by(_bare(p))) == 1 for p in parts):
            # The words name one cited tool AND several: not a guess either way.
            raise _Refused("ambiguous_tool")
        if any(_kind(p.strip()) != "bare" for p in parts[1:]):
            # "Splunk and Add Manager" is one cited tool AND "Splunk" plus an
            # addition of "Manager": neither reading is chosen (the advisor's
            # fallback after #824 round 6).
            raise _Refused("ambiguous_tool")
        if tool in removed:
            raise _Refused("duplicate")
        return tool

    def addition(name: str) -> str:
        entries = [{"name": n, "security_functions": ["detect"]} for n in added]
        entries.append({"name": _bare(name), "security_functions": ["detect"]})
        try:
            *_, tool = validate_added(
                entries,
                client_tools=client_tools,
                client_org_name=client_org_name,
                redaction_mode=redaction_mode,
                name_hints=hints,
                limit=MAX_ADDED,
            )
        except (TooMany, AddedToolRefused) as exc:
            raise _Refused(*added_reason(exc)) from exc
        if _SPLIT.search(_bare(name)):
            # A break inside a NEW name means it may be one name cut apart or
            # several; only a cited name held for removal kept it whole, which
            # is no evidence about an addition (#824 narrow review, F4). After
            # the check above, so a client's own tool still names itself (B4).
            raise _Refused("split_name")
        return tool.name

    def swap(verb: str, rest: str) -> tuple[str, str]:
        # A division is PLAUSIBLE when its removal half names a cited tool.
        # Exactly one plausible division is checked on its own terms; several
        # are ambiguous whatever their added halves do, so a division is never
        # chosen because another one failed (#824 narrow review).
        cuts = list(_SWAP_JOIN[verb].finditer(rest))
        plausible = [m for m in cuts if resolver.named_by(_bare(rest[: m.start()]))]
        if len(plausible) > 1:
            raise _Refused("ambiguous_split")
        if plausible:
            (m,) = plausible
        elif len(cuts) == 1:
            (m,) = cuts
        else:
            raise _Refused("unrecognised")
        return removal(rest[: m.start()]), addition(rest[m.end() :])

    split = _clauses(text, resolver.citable_forms())
    clauses, span = split.texts, split.span
    sharing = False
    i = 0
    while i < len(clauses):
        clause = clauses[i]
        if i in split.clashing:
            not_understood.append(NotUnderstood(text=clause, reason="ambiguous_tool"))
            sharing = False
            i += 1
            continue
        kind = _kind(clause)
        if kind != "bare" and resolver.named_by(_bare(clause)):
            # "Add Manager" is a cited tool AND an addition of "Manager". Neither
            # reading is chosen, in ANY position: a rule keyed on what came
            # before kept finding a position it missed (#824 rounds 4 and 5, the
            # advisor's fallback).
            not_understood.append(NotUnderstood(text=clause, reason="ambiguous_tool"))
            sharing = False
            i += 1
            continue
        # An add or swap with bare clauses after it may be one name cut apart.
        j = i + 1
        while kind in ("add", "swap") and j < len(clauses) and _kind(clauses[j]) == "bare":
            j += 1
        if j > i + 1:
            not_understood.append(NotUnderstood(text=span(i, j), reason="split_name"))
            sharing = False
            i = j
            continue
        try:
            if kind == "remove":
                sharing = False
                removed.append(removal(_REMOVE.match(clause)["a"]))
                sharing = True
            elif kind == "swap":
                sharing = False
                m = _SWAP.match(clause)
                gone, new = swap("swap" if m["swap"] is not None else "replace", m["rest"])
                removed.append(gone)
                added.append(new)
            elif kind == "add":
                sharing = False
                added.append(addition(_ADD.match(clause)["a"]))
            elif sharing:
                sharing = False
                removed.append(removal(clause))
                sharing = True
            else:
                raise _Refused("unrecognised")
        except _Refused as why:
            not_understood.append(NotUnderstood(text=clause, reason=why.reason, name=why.name))
        i += 1
    return ParsedChange(removed=removed, added=added, not_understood=not_understood)


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
    assessment: Any,
    base_rows: Sequence[Any],
    lists: Mapping[str, Mapping[str, list[str]]],
    comparison: Comparison,
    affected: Iterable[str],
    *,
    added_names: Iterable[str],
) -> tuple[list[str], list[str]]:
    """The affected techniques that would score higher, by cause: (copy 18's
    warning; B11's result). A technique can be in BOTH.

    COUNTERFACTUAL, not "was an added tool named": the after-status is computed
    again from the what-if's lists WITHOUT the added tools, by the same R3
    rules (#818 review, F3), and the advisor's option (b) at 16:47Z decides:
    - a rise the REMAINING tools alone still produce is copy 18's anomaly,
      even when an added tool was credited too;
    - a rise where the added tools reach a HIGHER final status than the
      remaining tools alone (Gap to Partial on a remaining tool, then Covered
      with an added one; or a rise the remaining tools do not produce at all)
      is B11's result too.
    A row naming an added tool with every function false put nothing in the
    lists, so it explains nothing."""
    affected = list(affected)
    rises = scored_higher(comparison, affected)
    added = {_key(n) for n in added_names}
    if not added:
        return rises, []
    without = {
        code: {name: [t for t in tools if _key(t) not in added] for name, tools in row.items()}
        for code, row in lists.items()
    }
    alone = compare(assessment, base_rows, scenario_rows(base_rows, without))
    survives = set(scored_higher(alone, affected))
    with_added = {code: after for code, _before, after in comparison.changed}
    before = {code: b for code, b, _after in comparison.changed}
    alone_after = {code: after for code, _before, after in alone.changed}

    def raised_by_added(code: str) -> bool:
        reached_alone = alone_after.get(code, before[code])
        return _RANK.get(with_added[code], -1) > _RANK.get(reached_alone, -1)

    return (
        [c for c in rises if c in survives],
        [c for c in rises if raised_by_added(c)],
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
    added: Sequence[AddedTool] = (),
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
    may be credited only to an ADDED tool (`added`). A row crediting one of the
    client's tools for a function that is open and not lost is dropped whole
    and counted as `tool_not_added`.

    An added tool may be credited only for the functions DECLARED for it, in a
    lost function as much as an open one (the advisor, 16:00Z, #818 F6): the
    admin's choice is the only evidence there is. A row crediting it with any
    other is dropped whole and counted as `function_not_declared`."""
    rows = data.get("rows") if isinstance(data, Mapping) else None
    if not isinstance(rows, list):
        raise ScenarioShapeError("the answer has no `rows` list")
    asked = list(asked)
    asked_set = set(asked)
    indistinct_names = set(indistinct)
    opened = opened or {}
    declared = {_key(t.name): {_FUNCTION_FLAG[f] for f in t.functions} for t in added}
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
        if (claimed - lost_here) and _key(tool) not in declared:
            dropped["tool_not_added"] += 1
            continue
        if _key(tool) in declared and claimed - declared[_key(tool)]:
            dropped["function_not_declared"] += 1
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
