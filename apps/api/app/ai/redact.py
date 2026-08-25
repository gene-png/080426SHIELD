"""PII redactor - the SECURITY BOUNDARY in front of every LLM call.

Master Spec §12 + §12.1. SHIELD v1 accepts the risk of egress to a
commercial LLM provider (Anthropic Claude by default); this module is
the primary compensating control. It is intentionally pure: no I/O, no
DB, no clock. It can be reviewed line-by-line in an OWASP audit.

Functions:
  redact_for_ai(text, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_text, removed_counts)
  redact_payload(obj, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_obj, removed_counts)

`removed_counts` is a dict like `{"email": 3, "phone": 1, ...}`. It
becomes the `removed_items` JSON column on `artifact_redactions` (Master
Spec §11) and gets logged on the corresponding `llm_calls` audit row.
Counts only - no payload contents.

Modes:
  strict   - removes everything below.
  standard - removes everything EXCEPT addresses and the client's org name.
             Useful when the prompt explicitly needs the org context.
  off      - pass-through. Refused at startup outside development by
             config.assert_safe_for_runtime() (Phase 1). This module
             accepts `off` so unit tests can compare "redacted vs raw"
             paths; production never reaches here with mode=off.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

RedactionMode = Literal["strict", "standard", "off"]

# ---------------------------------------------------------------------------
# Replacement placeholders
# ---------------------------------------------------------------------------

PLACEHOLDER_EMAIL = "[EMAIL]"
PLACEHOLDER_PHONE = "[PHONE]"
PLACEHOLDER_SSN = "[SSN]"
PLACEHOLDER_EIN = "[EIN]"
PLACEHOLDER_CAGE = "[CAGE]"
PLACEHOLDER_CONTRACT = "[CONTRACT]"
PLACEHOLDER_ADDRESS = "[ADDRESS]"
PLACEHOLDER_NAME = "[NAME]"
PLACEHOLDER_CLIENT = "[CLIENT]"
PLACEHOLDER_SIGNATURE = "[SIGNATURE_BLOCK]"

# ---------------------------------------------------------------------------
# Regexes. Compiled once at import. Designed to favor false-positives
# (over-redact) over false-negatives (leak), because this is a security
# boundary and we'd rather lose some fidelity than leak PII.
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# Phones: matches any "phone-shaped" run - optional `+`, 10-20 chars of
# digits plus the usual separators. Order matters: SSN / EIN / contract /
# CAGE patterns run before phone so they remove their substrings first
# and the phone pass doesn't double-strike.
_RE_PHONE = re.compile(
    r"""
    (?<!\d)                              # not in the middle of a longer digit run
    \+?[\d]                              # opens with optional + then a digit
    [\d\s.\-()]{8,18}                    # 8-18 more digit-or-separator chars
    \d                                   # ends with a digit
    """,
    re.VERBOSE,
)

_RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_RE_EIN = re.compile(r"\b\d{2}-\d{7}\b")

# CAGE code: exactly 5 alphanumeric characters, often introduced as
# "CAGE 1A2B3" or just "1A2B3" in a list. The introducer keyword form is
# the only one we redact - the bare 5-char-alnum is too generic to flag
# without a huge false-positive rate.
_RE_CAGE = re.compile(r"\bCAGE[\s:#-]*([A-Z0-9]{5})\b", re.IGNORECASE)

# Contract numbers: common govcon shapes include W91QUZ-23-C-0001,
# HQ0034-22-D-0007, FA8732-21-F-1234. The prefix mixes letters and
# digits (e.g. W91QUZ) so it's [A-Z0-9]{4,8}, not [A-Z]{2,6}.
_RE_CONTRACT = re.compile(
    r"\b[A-Z0-9]{4,8}-\d{2}-[A-Z]-\d{4,5}[A-Z]?\b",
)

_SIGNATURE_OPENERS = (
    "sincerely",
    "regards",
    "best regards",
    "kind regards",
    "best",
    "thanks",
    "thank you",
    "cheers",
    "respectfully",
    "v/r",
)


def _count_replacements(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _redact_signature_blocks(text: str) -> tuple[str, int]:
    """Strip everything from a signature opener line to end of input.

    Each line is checked. The first signature opener we see is the cut
    point - everything from that line onward becomes the placeholder.
    """
    lines = text.splitlines(keepends=True)
    cut: int | None = None
    for idx, raw in enumerate(lines):
        stripped = raw.strip().lower().rstrip(",.!")
        if stripped in _SIGNATURE_OPENERS:
            cut = idx
            break
    if cut is None:
        return text, 0
    head = "".join(lines[:cut])
    return head + PLACEHOLDER_SIGNATURE + "\n", 1


_STREET_WORDS = (
    "Street",
    "St",
    "Avenue",
    "Ave",
    "Road",
    "Rd",
    "Drive",
    "Dr",
    "Lane",
    "Ln",
    "Boulevard",
    "Blvd",
    "Court",
    "Ct",
    "Way",
    "Highway",
    "Hwy",
    "Parkway",
    "Pkwy",
    "Plaza",
    "Square",
)

# HORIZONTAL whitespace: everything `\s` matches EXCEPT the ten characters
# `str.splitlines()` treats as a line break. Every separator in the ADDRESS rule
# is built from it, so "the rule does not cross a line" is one definition in one
# place rather than a property each pattern re-asserts.
#
# NOT every separator in the MODULE, and the difference is deliberate rather than
# an oversight: `_RE_PHONE` (`[\d\s.\-()]`) and `_RE_CAGE` (`[\s:#-]*`) still
# contain `\s` and still cross line breaks. Both are filed rather than fixed here so
# #130's cost stays visible -- #140 and #137 -- and both have defects beyond the
# newline one. Stated because a reader who greps `\s` will find them, and an
# unstated exemption reads as an oversight to whoever finds it next.
#
# WHY A SUBTRACTION AND NOT A LIST. The first version of this fix enumerated
# `[ \t\xa0]`, which reads as "space, tab, non-breaking space -- surely
# that is all of them". `\s` matches 19 horizontal characters, so that list
# silently dropped SIXTEEN of them: U+2000-U+200A (en, em, thin, hair and
# friends), U+202F narrow no-break, U+205F medium mathematical, U+3000
# ideographic, U+1680 ogham, and U+001F. That is a LEAK, not a residual, and it
# was invisible because the decision was framed as being about NEWLINES and
# nobody re-derived what else was in the class being replaced. Thin and
# narrow-no-break spaces are what PDF and Word extraction emit, which is exactly
# how client letterhead reaches this boundary.
#
# `[^\S\r\n]` -- the obvious idiom, and what the adversarial review of this
# fix suggested -- is also wrong: it still crosses `\v`, `\f`, `\x1c`-`\x1e`,
# `\x85`, U+2028 and U+2029, every one of which IS a line break. Subtract the
# whole vertical set instead, and let `\S` define the horizontal one.
_HSPACE = r"[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]"

# The street rule's failure mode is worse than the suite rule's. Its leading
# `\d{1,6}` reaches BACKWARD over a line break and takes a number that belonged
# to the previous line -- "Servers reviewed: 5\nMain Street office is unstaffed."
# became "Servers reviewed: [ADDRESS] office is unstaffed.", losing the count and
# reading as an ordinary sentence afterwards. It was also the one sub-pattern
# still using `\s` after #130's first fix, while the truth table carried a
# comment claiming the guarantee held for all three.
#
# Cost of the change, named rather than discovered: an address wrapped across a
# line break now leaks. That coverage was real (unlike `Flat`'s, which existed
# only through the `\bFl` bug) but was never clean -- the trailing directional
# falls outside the pattern, so `1600 Pennsylvania\nAvenue NW` redacted to
# `[ADDRESS] NW` either way. Pinned as an accepted residual.
_STREET_SEP = _HSPACE

_STREET_PAT = (
    r"\b\d{1,6}"
    + _STREET_SEP
    + r"+([A-Z][A-Za-z]+"
    + _STREET_SEP
    + r"+){1,4}(?:"
    + "|".join(_STREET_WORDS)
    + r")\b"
)

# Unit/suite designators. The suffix decides, not the keyword: every keyword
# here is also an ordinary English word or the start of a product name, so the
# rule can only be as good as its answer to "is what follows designator-shaped".
#
# Split by whether the keyword is an ABBREVIATION, because only an abbreviation
# takes a trailing period. That distinction is load-bearing rather than tidy: a
# period-plus-space separator is also how a SENTENCE ends, so allowing it after
# a spelled-out word made the rule swallow the start of the next sentence --
# "covers this unit. 3 findings remain." -> "covers this [ADDRESS] findings
# remain." That is #130's own disease surviving the fix through the separator
# class instead of the boundary. "Ste." and "Apt." are abbreviations and take a
# period; "Unit" and "Floor" are words and do not.
_SUITE_KEY_ABBREV = r"(?:Ste|Apt|Fl)"
_SUITE_KEY_WORD = r"(?:Suite|Unit|Floor|PO" + _HSPACE + r"+Box|P\.O\." + _HSPACE + r"+Box)"

# Separators. Deliberately NOT `\s`: a newline lets the rule reach into the next
# line of a bulleted list and merge two items into one corrupted line
# ("- Business Unit\n- 3rd party risk tooling"). Client notes are full of
# bullets; a designator wrapped mid-line is rare and is a listed residual.
_SUITE_SEP = r"(?:" + _HSPACE + r"|[#\-])"
# Abbreviations only: the same class plus the abbreviating period.
_SUITE_SEP_ABBREV = r"(?:" + _HSPACE + r"|[.#\-])"

# Spelled-out designators ("Suite Twelve", "Apt Twenty-One"). Without these the
# digit rule below silently drops a whole class of real addresses.
_NUMWORD = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|first|second|third)"
)


def _suite_branches(sep: str) -> str:
    """The five suffix shapes, parameterised by which separator class applies.

    Identical for abbreviated and spelled-out keywords except for the period --
    written once and called twice rather than copied, because a second copy of a
    security-boundary rule drifts (CLAUDE.md's parity lesson).
    """
    return (
        r"(?:"
        # 1. NO separator, and a digit immediately: "Suite400", "PO Box99",
        #    "Apt3B". Nobody types these, but OCR'd letterhead and exported
        #    spreadsheet cells arrive this way and reach here through Tech Debt
        #    extraction. Requiring a DIGIT (rather than any character, as before
        #    #130) is what stops the keyword eating the rest of "Suitecrm",
        #    "Unitrends", "Flowmon".
        r"\d[A-Za-z0-9\-]*"
        # 2. A separator, then a number that may carry a short letter prefix and
        #    an internal separator: "Suite 400", "Ste-400", "Suite B3",
        #    "Suite B-201", "Apt A-12". The letter prefix is capped at 3 and the
        #    internal separator cannot be a space -- both deliberate. Uncapped,
        #    it swallows "Adobe Creative Suite Enterprise 2024"; with a space
        #    allowed, "the floor is 3 meters" matches. Before this branch handled
        #    the letter-hyphen-digit form, "Suite B-201" produced
        #    "[ADDRESS]-201": the unit number survived while the output LOOKED
        #    redacted, which is the silent-success shape this module exists to
        #    avoid.
        r"|" + sep + r"+[A-Za-z]{0,3}[.\-]?\d[A-Za-z0-9\-]*"
        # 3. Spelled out, possibly multi-token: "Suite One Hundred Twenty".
        r"|" + sep + r"+" + _NUMWORD + r"(?:(?:" + _HSPACE + r"|-)" + _NUMWORD + r")*"
        # 4. Roman numerals, and this branch MUST stay case-scoped even though
        #    the pattern compiles IGNORECASE: lowercase i/v/x/l spell ordinary
        #    English words, so a case-blind branch redacts "Unit ill defined" --
        #    the #130 disease again. Verified by reverting `(?-i:` alone and
        #    watching that case go red; "Unit did not respond" is NOT evidence
        #    for this and an earlier draft of this comment wrongly claimed it
        #    was, because `d` is not in the class. C/D/M are left out for the
        #    same reason: they would add "did", "dim" and "mild" as collisions to
        #    buy roman numerals above 89, which no suite number needs.
        r"|" + sep + r"+(?-i:[IVXL]{1,6})"
        # 5. A single lettered designator: "Suite A", "Apt B". Deliberately one
        #    character: widening it to [A-Z]{1,3} to catch "Suite AB" also
        #    corrupts "Adobe Creative Suite CC" and "Sophos Security Suite XG",
        #    which is #130 reintroduced on another branch. "Suite AB" is an
        #    accepted residual -- see the truth table in
        #    tests/unit/test_redact_address_matrix.py.
        #
        #    The lookahead refuses when a number follows, because matching just
        #    the letter would leave it behind: "Suite B 201" became
        #    "[ADDRESS] 201", a partial match that READS as a completed
        #    redaction. Declining outright is the honest failure -- the whole
        #    string survives, which the truth table records as a leak, rather
        #    than half of it vanishing under an output that looks finished.
        r"|" + sep + r"+[A-Za-z0-9](?!" + sep + r"*\d)"
        r")\b"
    )


_SUITE_PAT = (
    r"\b"
    + _SUITE_KEY_ABBREV
    + _suite_branches(_SUITE_SEP_ABBREV)
    + r"|\b"
    + _SUITE_KEY_WORD
    + _suite_branches(_SUITE_SEP)
)

# The value can also PRECEDE the keyword, which the pre-#130 pattern never
# modelled. The shape has exactly one member: only Floor/Fl take a number in
# front -- nobody writes "200 Suite" or "4B Apt". This is NEW coverage closing a
# live leak, not coverage preserved through the fix: before #130, "2nd Floor"
# produced "2nd [ADDRESS]" (the `\bFl`-eats-`oor` bug firing, number left
# behind) and "3rd Fl" matched nothing at all.
#
# The ordinal suffix is REQUIRED, and the separator is not `\s`. Both are there
# because this branch is the one that reaches leftward into prose: with a bare
# number allowed, "We reviewed 3 floor plans." became "We reviewed [ADDRESS]
# plans." -- floor plans, floor switches and floor wardens are ordinary facility
# and network-assessment vocabulary. With `\s` it also crossed a newline
# ("the top 3\nfloor switches"), which is precisely the merge the separator class
# above is written to prevent. "3 Floor" with no ordinal is a listed residual;
# "3 Floor Lane" is caught by the street rule instead.
_PRE_KEYWORD_PAT = r"\b\d{1,4}(?:st|nd|rd|th)" + _HSPACE + r"+(?:Floor|Fl)\b"

_RE_ADDRESS = re.compile(
    f"{_STREET_PAT}|{_SUITE_PAT}|{_PRE_KEYWORD_PAT}",
    re.IGNORECASE,
)


def _redact_addresses(text: str) -> tuple[str, int]:
    """Best-effort street-address redaction.

    Matches a leading digit run + street keyword, a unit/suite designator, or a
    number preceding "Floor"/"Fl". Heuristic by nature, so the decisions are
    pinned as a truth table in `tests/unit/test_redact_address_matrix.py` --
    including the cells that are knowingly wrong and accepted (D-058).

    This rule is NOT free to make over-eager. `redact_for_ai` is the single LLM
    egress path, so a keyword that over-matches corrupts every AI input across
    all five services, silently: the model receives plausible-looking text, no
    error is raised, and nothing surfaces it. That was #130.
    """
    count = _count_replacements(_RE_ADDRESS, text)
    if count == 0:
        return text, 0
    return _RE_ADDRESS.sub(PLACEHOLDER_ADDRESS, text), count


def redact_org_name(text: str, org_name: str) -> tuple[str, int]:
    """Replace the client's legal name (case-insensitive, whole-token).

    Public since #33 finding 5, when the ATT&CK citation resolver needed to know
    what a tool name looks like after redaction. That resolver now calls
    `redact_for_ai` instead — the whole pipeline rather than this one rule —
    because this rule is only one of the ten passes `redact_for_ai` runs in
    strict mode (eight in standard, where this rule and the address rule are
    skipped) and the others also rewrite tool
    names. The address rule was the egregious case and is fixed (#130); it still
    rewrites a keyword followed by a number, so the reason stands. Kept public:
    it is a coherent unit and is tested directly.
    """
    if not org_name.strip():
        return text, 0
    pat = re.compile(rf"\b{re.escape(org_name)}\b", re.IGNORECASE)
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_CLIENT, text), count


def _redact_names(text: str, name_hints: Iterable[str]) -> tuple[str, int]:
    """Replace exact-match names from `name_hints` (case-insensitive)."""
    hints = [h for h in name_hints if h and len(h) >= 2]
    if not hints:
        return text, 0
    pat = re.compile(
        r"\b(?:" + "|".join(re.escape(h) for h in hints) + r")\b",
        re.IGNORECASE,
    )
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_NAME, text), count


def redact_for_ai(
    text: str,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[str, dict[str, int]]:
    """Redact PII from `text`. Returns the cleaned text + a counts dict.

    `mode="off"` returns the original text and an empty counts dict.
    Production refuses `off` via `Settings.assert_safe_for_runtime`.
    """
    counts: dict[str, int] = {}
    if mode == "off":
        return text, counts

    # Signature blocks first: they hide tail content from being redacted
    # twice when the block contains names + phones + emails.
    cleaned, c = _redact_signature_blocks(text)
    if c:
        counts["signature_block"] = c

    for key, pat, placeholder in (
        ("email", _RE_EMAIL, PLACEHOLDER_EMAIL),
        ("ssn", _RE_SSN, PLACEHOLDER_SSN),
        ("ein", _RE_EIN, PLACEHOLDER_EIN),
        ("contract", _RE_CONTRACT, PLACEHOLDER_CONTRACT),
        ("phone", _RE_PHONE, PLACEHOLDER_PHONE),
    ):
        c = _count_replacements(pat, cleaned)
        if c:
            cleaned = pat.sub(placeholder, cleaned)
            counts[key] = c

    # CAGE: keep only the placeholder, not the introducer keyword.
    cage_count = _count_replacements(_RE_CAGE, cleaned)
    if cage_count:
        cleaned = _RE_CAGE.sub(PLACEHOLDER_CAGE, cleaned)
        counts["cage"] = cage_count

    # Name hints
    cleaned, c = _redact_names(cleaned, name_hints)
    if c:
        counts["name"] = c

    if mode == "strict":
        # Addresses + org name only in strict mode.
        cleaned, c = _redact_addresses(cleaned)
        if c:
            counts["address"] = c
        if client_org_name:
            cleaned, c = redact_org_name(cleaned, client_org_name)
            if c:
                counts["client_org"] = c

    return cleaned, counts


def redact_payload(
    obj: Any,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[Any, dict[str, int]]:
    """Recursively redact strings inside an arbitrary JSON-shaped payload.

    Returns the cleaned object + a counts dict aggregated across every
    string encountered. dict keys are not redacted (they're typically
    field names like "email", which we want preserved).
    """
    totals: dict[str, int] = {}

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            cleaned, counts = redact_for_ai(
                node,
                mode=mode,
                client_org_name=client_org_name,
                name_hints=name_hints,
            )
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
            return cleaned
        if isinstance(node, Mapping):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return type(node)(_walk(v) for v in node)
        return node

    return _walk(obj), totals
