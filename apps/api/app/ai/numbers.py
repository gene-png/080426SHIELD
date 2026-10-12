"""The shared literal-number validator for AI-drafted prose (#1063, #1071).

THE RULE. AI-drafted narrative may state only numbers present in the input it
was given (#736 6115899208, P1 rule 1; 6115903398, G2). A number is any count,
amount, percentage, date part, year or version, whether written in digits,
in other Unicode digits, or in words. LICENSING IS STRICT (#736 6116092992,
ruling 2): a number is allowed only when it equals a numeric value in the
payload, or a number stated in a field the caller lists as a FACT. Every other
string licenses nothing. A percent is a distinct form (ruling 1): "40" and
"40%" each license only themselves. Catalog codes and names under the fields
the caller lists as PROTECTED may be written as given.

WHAT IT DOES NOT DO. It does not check which fact a number is attached to: a
model that writes an allowed number in the wrong sentence passes. That is the
consultant's review, not this module's.

FAIL LOUDLY. A hit is not an error, so `unallowed_numbers` returns hits and
never raises on one. Input it cannot read is an error: a non-string text, a
non-mapping payload, a value of an unknown type, or a non-finite number all
raise, so "I could not look" never shares a branch with "nothing to report"
(CLAUDE.md, the silent-success rule).

Owned by whichever of #1063 (findings report) and EV-2 lands first; the other
imports it. Parity is by calling this module, never by reimplementing it.

Nothing is wired to it yet: no prompt and no egress path calls it. The callers
are the #1063 report jobs and EV-2's summary, each in its own PR.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True)
class NumberAllowList:
    """`values`: normalised numbers present in the payload. `protected`: the
    exact strings (catalog codes, names) that may be written as given."""

    values: frozenset[str]
    protected: frozenset[str]


@dataclass(frozen=True)
class NumberHit:
    """A number the text states that the payload does not license."""

    raw: str
    normalized: str
    start: int
    end: int


# Phrases that carry no count, masked before the word scan. Each is a fixed
# phrase, not a word: "one" and "third" alone are still numbers.
_EXEMPT_PHRASES: tuple[str, ...] = ("no one", "third-party", "third party")

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "twentieth": 20,
    "thirtieth": 30,
    "fortieth": 40,
    "fiftieth": 50,
    "sixtieth": 60,
    "seventieth": 70,
    "eightieth": 80,
    "ninetieth": 90,
}
_HUNDRED = {"hundred": 100, "hundredth": 100}
_SCALES = {
    "thousand": 1_000,
    "thousandth": 1_000,
    "million": 1_000_000,
    "millionth": 1_000_000,
    "billion": 1_000_000_000,
}
_MULTIPLES = {
    "twice": "2",
    "double": "2",
    "doubled": "2",
    "doubles": "2",
    "doubling": "2",
    "thrice": "3",
    "triple": "3",
    "tripled": "3",
    "triples": "3",
    "tripling": "3",
    "half": "0.5",
    "halved": "0.5",
    "halves": "0.5",
    "halving": "0.5",
}

# Fraction words (#1088 finding 3). A fraction needs a numerator before it
# ("a third", "one third", "two-thirds", "three quarters"): valued as the
# fraction, never as an ordinal or a sum. A bare "quarter" is excluded on
# purpose: "this quarter" is a reporting period, not a count.
_DENOMINATORS = {
    "half": 2,
    "halves": 2,
    "third": 3,
    "thirds": 3,
    "quarter": 4,
    "quarters": 4,
    "fourth": 4,
    "fourths": 4,
    "fifth": 5,
    "fifths": 5,
    "sixth": 6,
    "sixths": 6,
    "seventh": 7,
    "sevenths": 7,
    "eighth": 8,
    "eighths": 8,
    "ninth": 9,
    "ninths": 9,
    "tenth": 10,
    "tenths": 10,
}
_NUMERATORS = {
    "a": 1,
    "an": 1,
    **{
        w: v for w, v in _UNITS.items() if 1 <= v <= 10 and not w.endswith(("st", "nd", "rd", "th"))
    },
}
_FRACTION = re.compile(
    r"\b(?P<num>"
    + "|".join(sorted(_NUMERATORS, key=len, reverse=True))
    + r")[\s-]+(?P<den>"
    + "|".join(sorted(_DENOMINATORS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)
# "dozen" and "-fold" state a value. Vague magnitudes ("hundreds", "dozens",
# "thousands") state a count no input value can match, so they are always
# refused: the normalised form carries a "~" that no number ever has.
_DOZEN = re.compile(r"\bdozen\b", re.IGNORECASE)
_FOLD = re.compile(
    r"\b(?P<n>two|three|four|five|six|seven|eight|nine|ten|hundred|thousand)fold\b",
    re.IGNORECASE,
)
_FOLD_VALUES = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "hundred": 100,
    "thousand": 1000,
}
_VAGUE = re.compile(r"\b(?:dozens|hundreds|thousands|millions|billions)\b", re.IGNORECASE)
# Roman numerals (#1088 finding 7), UPPERCASE only. Standalone, only two or more
# of I/V/X ("IV", "XII"): a lone "I" is a pronoun, and C/D/L/M are left out
# because "CD", "DC", "MD", "CV" and "XL" are common acronyms. After a context
# word ("Tier I", "Phase V", "Level X") a single letter counts too.
_ROMAN_VALID = re.compile(r"^X{0,3}(?:IX|IV|V?I{0,3})$")
_ROMAN_CONTEXT = re.compile(
    r"\b(?:Tier|Level|Phase|Stage|Part|Volume|Rev|Revision|Type|Class|Annex|Appendix)\s+(?P<r>[IVX]+)\b"
)
_ROMAN_STANDALONE = re.compile(r"(?<![A-Za-z0-9])(?P<r>[IVX]{2,})(?![A-Za-z0-9])")
_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10}

_WORDS = sorted({*_UNITS, *_TENS, *_HUNDRED, *_SCALES}, key=len, reverse=True)
_WORD_ALT = "|".join(_WORDS)
_SPELLED = re.compile(rf"\b(?:{_WORD_ALT})(?:[\s-]+(?:{_WORD_ALT}))*\b", re.IGNORECASE)
_MULTIPLE = re.compile(
    r"\b(?:" + "|".join(sorted(_MULTIPLES, key=len, reverse=True)) + r")\b", re.IGNORECASE
)
# Digits in any script (`\d` is Unicode-aware on str patterns). Digits inside a
# word count ("v2.1", "x86"): a version is a number under G2.
# U+2212 MINUS SIGN is a minus sign (#1088 finding 9). A digit fraction
# ("1/3") is one number, but not inside a date ("10/12/2026"): the lookarounds
# leave a date to the plain-number branch, which reads each part.
_DIGIT_FRACTION = re.compile(r"(?<![\d/])(?P<n>\d+)/(?P<d>\d+)(?![\d/])")
# A k / M / B / bn suffix directly after the number is a scale (#1088 finding
# 2). A lowercase "m" is left out on purpose: "5m" is as often minutes or
# metres as millions.
_SUFFIX_SCALES = {"k": 1_000, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "bn": 1_000_000_000}
_NUMERIC = re.compile(
    r"(?P<cur>[$\u20ac\u00a3])?(?P<sign>[-\u2212])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:(?P<sfx>bn|[kKMB])(?![A-Za-z0-9]))?"
    r"(?P<pct>\s?%|\s+(?i:percent)\b)?"
    r"(?:\s+(?P<scale>(?i:thousand|million|billion))\b)?"
    # Case-sensitive overall: "M" is a million and "m" is not (see above).
)


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
    """Exact protected strings. Not when a code CONTINUES past them ("T1003"
    inside "T1003.002", "PR.PS-01" inside "PR.PS-01.3"): a "." or "-" followed
    by an alphanumeric is the code-continuation shape, and masking the parent
    would hide an invented sub-code (#1088 finding 4). A sentence's own full
    stop is followed by a space or the end, so "It is T1003." still masks."""
    spans: list[tuple[int, int]] = []
    for token in sorted(protected, key=len, reverse=True):
        pattern = (
            rf"(?<![A-Za-z0-9])(?<![A-Za-z0-9][.-]){re.escape(token)}"
            rf"(?![A-Za-z0-9])(?![.-][A-Za-z0-9])"
        )
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text))
    return spans


def _exempt_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in _EXEMPT_PHRASES:
        pattern = r"\b" + re.escape(phrase).replace(r"\ ", r"\s+") + r"\b"
        spans.extend((m.start(), m.end()) for m in re.finditer(pattern, text, re.IGNORECASE))
    return spans


def _spelled_value(words: list[str]) -> int:
    total = 0
    current = 0
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word in _HUNDRED:
            current = (current or 1) * 100
        else:
            total += (current or 1) * _SCALES[word]
            current = 0
    return total + current


def _numeric_hit(text: str, m: re.Match[str]) -> NumberHit:
    start = m.start()
    sign = m.group("sign")
    if sign:
        sign_at = m.start("sign")
        before = text[sign_at - 1] if sign_at > 0 else " "
        if before.isalnum() or before == ".":
            # "3-5", "800-53", "PR.PS-02": a separator, not a minus sign. A
            # "$" cannot precede it here: "$" is not alphanumeric.
            sign = None
            start = m.start("num")
    # `Decimal` reads digits in any script ("１３", "٣"), as the docs promise.
    num = Decimal(m.group("num").replace(",", ""))
    if m.group("sfx"):
        num *= _SUFFIX_SCALES[m.group("sfx")]
    scale = m.group("scale")
    if scale:
        num *= _SCALES[scale.lower()]
    if sign:
        num = -num
    normalized = _canonical(num) + ("%" if m.group("pct") else "")
    return NumberHit(raw=text[start : m.end()], normalized=normalized, start=start, end=m.end())


def _fraction_text(value: Fraction) -> str:
    """A terminating fraction as its decimal ("0.25"); otherwise "n/d"."""
    d = value.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        return _canonical(Decimal(value.numerator) / Decimal(value.denominator))
    return f"{value.numerator}/{value.denominator}"


def _roman_value(letters: str) -> int | None:
    if not _ROMAN_VALID.match(letters):
        return None
    total = 0
    for i, c in enumerate(letters):
        v = _ROMAN_VALUES[c]
        nxt = _ROMAN_VALUES[letters[i + 1]] if i + 1 < len(letters) else 0
        total += -v if v < nxt else v
    return total


def _word_hits(masked: str) -> tuple[list[NumberHit], str]:
    """Fraction, dozen, -fold, vague-magnitude and Roman hits, and the text
    with their spans masked so the spelled-number scan does not count them
    again ("one third" is one fraction, not 1 and 3)."""
    hits: list[NumberHit] = []
    spans: list[tuple[int, int]] = []

    def add(start: int, end: int, normalized: str) -> None:
        hits.append(NumberHit(masked[start:end], normalized, start, end))
        spans.append((start, end))

    for m in _FRACTION.finditer(masked):
        value = Fraction(_NUMERATORS[m.group("num").lower()], _DENOMINATORS[m.group("den").lower()])
        add(m.start(), m.end(), _fraction_text(value))
    for m in _DOZEN.finditer(masked):
        add(m.start(), m.end(), "12")
    for m in _FOLD.finditer(masked):
        add(m.start(), m.end(), str(_FOLD_VALUES[m.group("n").lower()]))
    for m in _VAGUE.finditer(masked):
        add(m.start(), m.end(), "~" + m.group(0).lower())
    for pattern in (_ROMAN_CONTEXT, _ROMAN_STANDALONE):
        for m in pattern.finditer(masked):
            value = _roman_value(m.group("r"))
            if value is not None and not any(s <= m.start("r") < e for s, e in spans):
                add(m.start("r"), m.end("r"), str(value))
    return hits, _mask(masked, spans)


def _scan(text: str, protected: frozenset[str]) -> list[NumberHit]:
    """Every number `text` states, outside the protected strings and the exempt
    phrases, in order."""
    masked = _mask(text, _protected_spans(text, protected) + _exempt_spans(text))
    hits, masked = _word_hits(masked)
    fraction_spans = []
    for m in _DIGIT_FRACTION.finditer(masked):
        value = Fraction(int(m.group("n")), int(m.group("d"))) if int(m.group("d")) else None
        if value is not None:
            hits.append(NumberHit(m.group(0), _fraction_text(value), m.start(), m.end()))
            fraction_spans.append((m.start(), m.end()))
    masked = _mask(masked, fraction_spans)
    hits += [_numeric_hit(masked, m) for m in _NUMERIC.finditer(masked)]
    for m in _SPELLED.finditer(masked):
        words = [w.lower() for w in re.split(r"[\s-]+", m.group(0))]
        hits.append(NumberHit(m.group(0), str(_spelled_value(words)), m.start(), m.end()))
    for m in _MULTIPLE.finditer(masked):
        hits.append(NumberHit(m.group(0), _MULTIPLES[m.group(0).lower()], m.start(), m.end()))
    for i, c in enumerate(masked):
        # "No" (superscripts, vulgar fractions) and "Nl" (letter-numbers such
        # as U+216B ROMAN NUMERAL TWELVE) carry a numeric value.
        if unicodedata.category(c) in ("No", "Nl"):
            hits.append(NumberHit(c, _canonical(Decimal(str(unicodedata.numeric(c)))), i, i + 1))
    # Raw spans come from the masked text, whose offsets equal the original's.
    return sorted(
        (NumberHit(text[h.start : h.end], h.normalized, h.start, h.end) for h in hits),
        key=lambda h: h.start,
    )


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
        # Any other string licenses nothing (#736 6116092992, ruling 2): ids,
        # timestamps and identifiers carry digits that are not facts.
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
    """The numbers `payload` licenses, STRICTLY (#736 6116092992, ruling 2):

    - every numeric value, at any depth, licenses itself;
    - a string under a key in `fact_fields` (any depth) licenses the numbers
      it states, read with the protected strings masked;
    - a string under a key in `protected_fields` is a protected token: it may
      be written as given and licenses no number of its own;
    - every other string licenses nothing.

    A listed name that matches no key in `payload` is refused with a
    ValueError: a caller that names a field the payload does not carry has
    licensed or protected nothing, and would not know it.
    """
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
    for s in out["strings"]:
        out["values"].update(h.normalized for h in _scan(s, protected))
    allowed = NumberAllowList(values=frozenset(out["values"]), protected=protected)
    _log.debug(
        "numbers.allow_list_built",
        values=len(allowed.values),
        protected=len(allowed.protected),
    )
    return allowed


def _is_allowed(hit: NumberHit, allowed: NumberAllowList) -> bool:
    # A percent is a DISTINCT form (#736 6116092992, ruling 1): code sends a
    # percent fact in its display form ("40%"), so "40" and "40%" license only
    # themselves.
    return hit.normalized in allowed.values


def unallowed_numbers(text: str, allowed: NumberAllowList) -> tuple[NumberHit, ...]:
    """Every number `text` states that `allowed` does not license, in order."""
    if not isinstance(text, str):
        raise TypeError(f"numbers: text must be a str, not {type(text).__name__}")
    hits = tuple(h for h in _scan(text, allowed.protected) if not _is_allowed(h, allowed))
    _log.debug("numbers.checked", chars=len(text), refused=len(hits))
    return hits


__all__ = ["NumberAllowList", "NumberHit", "allowed_numbers", "unallowed_numbers"]
