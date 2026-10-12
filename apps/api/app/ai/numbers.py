"""The shared literal-number validator for AI-drafted prose (#1063, #1071).

THE RULE. AI-drafted narrative may state only numbers present in the input it
was given (#736 6115899208, P1 rule 1; 6115903398, G2). LICENSING IS STRICT
(#736 6116092992, ruling 2): numeric values in the payload, and the text of
the fields the caller declares as FACTS, license numbers; every other string
licenses nothing. A percent is a distinct form (ruling 1). Catalog codes and
names under the fields the caller declares as PROTECTED may be written as
given.

FAIL CLOSED (the design after review round 2 of #1088). The text is read as
SPANS: maximal runs of number-bearing tokens joined by the rules below. A span
is licensed in exactly two ways, and everything else is a hit:

  A. it is a PLAIN NUMERAL (`[-−]?[$€£]?digits[,ddd]*[.digits]?%?`) whose value
     the payload licenses ("40.0" equals "40"; "40%" equals only "40%");
  B. its display text equals, after an explicit normalisation (thousands
     commas removed, whitespace collapsed, case folded), a span found in a
     declared fact field.

So the module writes code only for the forms it ACCEPTS. A composition it has
never seen ("two dozen", "$5mn", "40 per cent", "–5%") is not a plain numeral
and is not in a fact, so it is refused without anyone having listed it.

JOINING RULES (where one span ends):
  - a comma joins only as a thousands separator (digit, comma, exactly three
    digits, then a non-digit): "3, 5 and 7" is three spans;
  - a period joins only digit to digit with no whitespace (a decimal point);
  - whitespace joins only where one side is a number WORD ("two dozen",
    "40 per cent", "5 million"), never numeral to numeral ("40 5");
  - a dash joins as a sign directly before a numeral, as a range between
    numerals with no whitespace ("3–5"), or in a compound with a number word
    ("twenty-one", "40-percent");
  - a slash joins numerals only, with no whitespace ("1/3", "10/12/2026");
  - a currency mark joins the numeral it touches; a percent mark joins the
    numeral before it, across at most one space.

WHAT IT DOES NOT DO. It does not check which fact a number is attached to.

FAIL LOUDLY. A hit is returned, never raised. Input it cannot read raises: a
non-string text, a non-mapping payload, a field list given as a str, a listed
field matching no key, a value of an unknown type, a non-finite number.

Owned by whichever of #1063 and EV-2 lands first; the other imports it. Nothing
calls it yet: no prompt and no egress path changes.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True)
class NumberAllowList:
    """`values`: canonical numbers licensed as plain numerals. `displays`:
    normalised spans from the declared fact fields, licensed verbatim.
    `protected`: exact strings (codes, names) that may be written as given."""

    values: frozenset[str]
    displays: frozenset[str]
    protected: frozenset[str]


@dataclass(frozen=True)
class NumberHit:
    """A number-bearing span the text states that the payload does not license."""

    raw: str
    normalized: str
    start: int
    end: int


# The closed list of number WORDS (case-insensitive). Ordinals other than
# "third" are left out on purpose: "first" and "second" ("a second review")
# are ordinary prose far more often than counts.
_NUMBER_WORDS = frozenset(
    {
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
        "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
        "hundred", "hundreds", "thousand", "thousands", "million", "millions",
        "billion", "billions", "dozen", "dozens",
        "half", "halves", "halved", "third", "thirds",
        "percent", "pct",
        "twice", "thrice", "double", "doubled", "doubles", "triple", "tripled",
        "triples",
    }
)  # fmt: skip
_FOLD_PREFIXES = frozenset(
    {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "hundred"}
)
# "quarter" counts only joined to another number token ("a quarter", "three
# quarters"): alone it is a reporting period ("this quarter").
_WEAK_WORDS = frozenset({"quarter", "quarters"})
# "a" / "an" count only directly before one of these ("a dozen", "a third").
_ARTICLE_TARGETS = frozenset({"dozen", "third", "quarter", "half"})
# Uppercase Roman numerals: two or more of I/V/X standalone, or any after one of
# these words (any case). C, D, L and M are left out: "CD", "MD", "XL" and "CV"
# are everyday acronyms. A lone "I" is a pronoun.
_ROMAN_CONTEXT = frozenset(
    {
        "tier", "level", "phase", "stage", "part", "volume", "rev", "revision",
        "type", "class", "annex", "appendix",
    }
)  # fmt: skip
_ROMAN_VALID = re.compile(r"^X{0,3}(?:IX|IV|V?I{0,3})$")
_EXEMPT_PHRASES: tuple[str, ...] = ("no one", "third-party", "third party")

_DASHES = "-‐‑‒–—−"
_CURRENCY = "$€£"
_PERCENT = "%％"
_TOKEN = re.compile(r"\w+|\S")
# Accepted form A. `\d` is Unicode-aware, so full-width and other-script
# digits are plain numerals; `Decimal` reads them.
_PLAIN = re.compile(
    r"(?P<sign>[-−])?(?P<cur>[$€£])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<pct>%)?"
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

# Token kinds.
_NUM, _WORD, _ROMAN, _WEAK, _ART, _CUR, _PCT, _DASH, _OTHER = (
    "num", "word", "roman", "weak", "art", "cur", "pct", "dash", "other"
)  # fmt: skip
_BEARING = frozenset({_NUM, _WORD, _ROMAN, _WEAK})
_WORDISH = frozenset({_WORD, _WEAK})


@dataclass
class _Tok:
    kind: str
    start: int
    end: int
    text: str


def _canonical(value: Decimal) -> str:
    """`40.0` -> "40", `40.50` -> "40.5", `-0` -> "0"; never exponent form."""
    if not value.is_finite():
        raise ValueError(f"numbers: non-finite value {value!r}")
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0") else text


def _mask(text: str, spans: Iterable[tuple[int, int]]) -> str:
    chars = list(text)
    for start, end in spans:
        for i in range(start, end):
            chars[i] = " "
    return "".join(chars)


def _protected_spans(text: str, protected: frozenset[str]) -> list[tuple[int, int]]:
    """Exact protected strings, except where a code CONTINUES past them: a
    dash, period, slash, underscore or colon followed by an alphanumeric, on
    either side ("T1003" inside "T1003.002", "T1003–002", "T1003/002"). A
    sentence's own full stop is followed by a space or the end."""
    cont = re.escape(_DASHES + "./_:")
    spans: list[tuple[int, int]] = []
    for token in sorted(protected, key=len, reverse=True):
        pattern = (
            rf"(?<![^\W_])(?<![^\W_][{cont}]){re.escape(token)}" rf"(?![^\W_])(?![{cont}][^\W_])"
        )
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text))
    return spans


def _exempt_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in _EXEMPT_PHRASES:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE))
    return spans


def _is_numeric_char(c: str) -> bool:
    return c.isdecimal() or unicodedata.category(c) in ("No", "Nl")


def _is_roman(word: str, previous: str | None) -> bool:
    if not (re.fullmatch(r"[IVX]+", word) and _ROMAN_VALID.match(word)):
        return False
    return len(word) >= 2 or (previous is not None and previous.casefold() in _ROMAN_CONTEXT)


def _merges(t: _Tok, nxt: _Tok, masked: str) -> bool:
    """ "per cent" is one word; "a"/"an" merges into a following fraction or
    dozen word. Only across whitespace."""
    if not masked[t.end : nxt.start].isspace():
        return False
    if t.kind == "per":
        return nxt.kind == "cent"
    return t.kind == _ART and nxt.text.casefold() in _ARTICLE_TARGETS


def _word_kind(word: str, previous: str | None) -> str:
    low = word.casefold()
    if any(_is_numeric_char(c) for c in word):
        return _NUM
    if low in _NUMBER_WORDS:
        return _WORD
    if low.endswith("fold") and low[:-4] in _FOLD_PREFIXES:
        return _WORD
    if low in _WEAK_WORDS:
        return _WEAK
    if low in ("a", "an"):
        return _ART
    if _is_roman(word, previous):
        return _ROMAN
    if low == "per":
        return "per"
    if low == "cent":
        return "cent"
    return _OTHER


def _tokens(masked: str) -> list[_Tok]:
    toks: list[_Tok] = []
    previous_word: str | None = None
    for m in _TOKEN.finditer(masked):
        t = m.group(0)
        if t[0].isalnum() or t[0] == "_" or _is_numeric_char(t[0]):
            kind = _word_kind(t, previous_word)
            previous_word = t
        elif t in _CURRENCY:
            kind = _CUR
        elif t in _PERCENT:
            kind = _PCT
        elif t in _DASHES:
            kind = _DASH
        else:
            kind = _OTHER
        toks.append(_Tok(kind, m.start(), m.end(), t))
    # "per cent" is one number word; "a"/"an" before a fraction or dozen word
    # merges into it. Any other "per", "cent", "a" or "an" is plain prose.
    merged: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is not None and t.kind in ("per", _ART) and _merges(t, nxt, masked):
            merged.append(_Tok(_WORD, t.start, nxt.end, masked[t.start : nxt.end]))
            i += 2
            continue
        if t.kind in ("per", "cent", _ART):
            t = _Tok(_OTHER, t.start, t.end, t.text)
        merged.append(t)
        i += 1
    return merged


def _joins(a: _Tok, gap: list[_Tok], gap_text: str, b: _Tok) -> bool:
    """Whether bearing tokens `a` and `b`, with `gap` between them, are one span."""
    wordish = a.kind in _WORDISH or b.kind in _WORDISH
    if not gap:
        if gap_text == "":
            return True  # adjacent ("5" then "mn" cannot happen: \w+ is one token)
        return gap_text.isspace() and wordish
    if len(gap) != 1 or gap_text != gap[0].text:
        return False  # anything with whitespace around punctuation breaks a span
    sep = gap[0].text
    a_digit = a.text[-1:].isdecimal()
    if sep == ",":
        # Exactly three digits, then a non-digit ("1,200", "1,200k").
        return a_digit and re.match(r"\d{3}(?!\d)", b.text) is not None
    if sep == ".":
        return a_digit and b.text[:1].isdecimal()
    if sep == "/":
        return a.kind == _NUM and b.kind == _NUM
    if gap[0].kind == _DASH:
        return wordish or (a.kind == _NUM and b.kind == _NUM)
    return False


def _spans(text: str, protected: frozenset[str]) -> list[tuple[int, int]]:
    """The number-bearing spans of `text`, as (start, end), in order."""
    masked = _mask(text, _protected_spans(text, protected) + _exempt_spans(text))
    toks = _tokens(masked)
    spans: list[list[int]] = []  # [start, end, first_bearing_index, n_bearing, has_strong]
    last_bearing: int | None = None
    for i, t in enumerate(toks):
        if t.kind not in _BEARING:
            continue
        joined = False
        if last_bearing is not None and spans:
            a = toks[last_bearing]
            gap = toks[last_bearing + 1 : i]
            if _joins(a, gap, masked[a.end : t.start], t):
                spans[-1][1] = t.end
                spans[-1][4] |= t.kind != _WEAK
                joined = True
        if not joined:
            spans.append([t.start, t.end, i, 1, t.kind != _WEAK])
        last_bearing = i
    out: list[tuple[int, int]] = []
    for start, end, first, _n, strong in spans:
        if not strong:
            continue  # a lone "quarter" is a period, not a number
        # A sign directly before the first numeral, preceded by no word char.
        if first > 0 and toks[first].kind == _NUM:
            p = toks[first - 1]
            before = masked[p.start - 1] if p.start > 0 else " "
            if p.end == start and p.kind == _DASH and not (before.isalnum() or before == "_"):
                start = p.start
                if first > 1:
                    q = toks[first - 2]
                    if q.kind == _CUR and q.end == start:
                        start = q.start
            elif p.end == start and p.kind == _CUR:
                start = p.start
                if first > 1:
                    q = toks[first - 2]
                    if q.kind == _DASH and q.end == start:
                        before = masked[q.start - 1] if q.start > 0 else " "
                        if not (before.isalnum() or before == "_"):
                            start = q.start
        # A percent mark after the span, adjacent or after one space.
        rest = masked[end:]
        m = re.match(rf"( ?)([{_PERCENT}])", rest)
        if m:
            end += m.end()
        out.append((start, end))
    return out


def _normalize_display(raw: str) -> str:
    return re.sub(r"\s+", " ", _THOUSANDS.sub("", raw)).strip().casefold()


def _plain_value(raw: str) -> str | None:
    """The canonical value of a plain numeral, or None if `raw` is not one."""
    m = _PLAIN.fullmatch(raw)
    if m is None:
        return None
    num = Decimal(m.group("num").replace(",", ""))
    if m.group("sign"):
        num = -num
    return _canonical(num) + ("%" if m.group("pct") else "")


def _walk(value: Any, key: str | None, fields: dict[str, frozenset[str]], out: dict) -> None:
    if value is None or isinstance(value, bool):
        # `int(True)` is 1 (CLAUDE.md): a flag licenses no number.
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            out["keys"].add(str(k))
            _walk(v, str(k), fields, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, key, fields, out)
    elif isinstance(value, str):
        if key in fields["protected"]:
            if value.strip():
                out["protected"].add(value.strip())
        elif key in fields["facts"]:
            out["strings"].append(value)
        # Any other string licenses nothing (ruling 2): ids, timestamps and
        # identifiers carry digits that are not facts.
    elif isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"numbers: non-finite value at {key!r}")
        try:
            out["values"].add(_canonical(Decimal(str(value))))
        except InvalidOperation as exc:
            raise ValueError(f"numbers: unreadable number at {key!r}: {value!r}") from exc
    else:
        raise TypeError(f"numbers: cannot read a {type(value).__name__} at {key!r}")


def _field_names(names: Iterable[str], what: str) -> frozenset[str]:
    if isinstance(names, str):
        # `frozenset("code")` is {"c", "o", "d", "e"}: it would match nothing.
        raise TypeError(f"numbers: {what} must be an iterable of names, not a str")
    return frozenset(names)


def allowed_numbers(
    payload: Mapping[str, Any],
    *,
    fact_fields: Iterable[str],
    protected_fields: Iterable[str],
) -> NumberAllowList:
    """What `payload` licenses, strictly: every numeric value at any depth; and
    for every string under a key in `fact_fields` (any depth), each of its
    spans verbatim and each plain numeral's value. Strings under
    `protected_fields` may be written as given and license nothing else. Any
    other string licenses nothing. A listed name that matches no key raises."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"numbers: payload must be a mapping, not {type(payload).__name__}")
    fields = {
        "facts": _field_names(fact_fields, "fact_fields"),
        "protected": _field_names(protected_fields, "protected_fields"),
    }
    out: dict[str, Any] = {"values": set(), "protected": set(), "strings": [], "keys": set()}
    _walk(payload, None, fields, out)
    unmatched = (fields["facts"] | fields["protected"]) - out["keys"]
    if unmatched:
        raise ValueError(f"numbers: listed fields match no key in the payload: {sorted(unmatched)}")
    protected = frozenset(out["protected"])
    displays: set[str] = set()
    for s in out["strings"]:
        for start, end in _spans(s, protected):
            raw = s[start:end]
            displays.add(_normalize_display(raw))
            value = _plain_value(raw)
            if value is not None:
                out["values"].add(value)
    allowed = NumberAllowList(
        values=frozenset(out["values"]), displays=frozenset(displays), protected=protected
    )
    _log.debug(
        "numbers.allow_list_built",
        values=len(allowed.values),
        displays=len(allowed.displays),
        protected=len(allowed.protected),
    )
    return allowed


def unallowed_numbers(text: str, allowed: NumberAllowList) -> tuple[NumberHit, ...]:
    """Every number-bearing span of `text` that `allowed` does not license."""
    if not isinstance(text, str):
        raise TypeError(f"numbers: text must be a str, not {type(text).__name__}")
    hits: list[NumberHit] = []
    for start, end in _spans(text, allowed.protected):
        raw = text[start:end]
        value = _plain_value(raw)
        if value is not None:
            if value in allowed.values:
                continue
            hits.append(NumberHit(raw, value, start, end))
            continue
        display = _normalize_display(raw)
        if display not in allowed.displays:
            hits.append(NumberHit(raw, display, start, end))
    _log.debug("numbers.checked", chars=len(text), refused=len(hits))
    return tuple(hits)


__all__ = ["NumberAllowList", "NumberHit", "allowed_numbers", "unallowed_numbers"]
