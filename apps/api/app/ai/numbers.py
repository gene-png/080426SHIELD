"""The shared literal-number validator for AI-drafted prose (#1063, #1071).

THE RULE. AI-drafted narrative may state only numbers present in the input it
was given (#736 6115899208, P1 rule 1; 6115903398, G2). A number is any count,
amount, percentage, date part, year or version, whether written in digits,
in other Unicode digits, or in words. It is allowed when its value appears in
the payload's values, and catalog codes or names listed as PROTECTED (taken
from the payload's protected fields) may be written as given.

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

_WORDS = sorted({*_UNITS, *_TENS, *_HUNDRED, *_SCALES}, key=len, reverse=True)
_WORD_ALT = "|".join(_WORDS)
_SPELLED = re.compile(rf"\b(?:{_WORD_ALT})(?:[\s-]+(?:{_WORD_ALT}))*\b", re.IGNORECASE)
_MULTIPLE = re.compile(
    r"\b(?:" + "|".join(sorted(_MULTIPLES, key=len, reverse=True)) + r")\b", re.IGNORECASE
)
# Digits in any script (`\d` is Unicode-aware on str patterns). Digits inside a
# word count ("v2.1", "x86"): a version is a number under G2.
_NUMERIC = re.compile(
    r"(?P<cur>\$)?(?P<sign>-)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<pct>\s?%|\s+percent\b)?"
    r"(?:\s+(?P<scale>thousand|million|billion)\b)?",
    re.IGNORECASE,
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
    spans: list[tuple[int, int]] = []
    for token in sorted(protected, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])"
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
    scale = m.group("scale")
    if scale:
        num *= _SCALES[scale.lower()]
    if sign:
        num = -num
    normalized = _canonical(num) + ("%" if m.group("pct") else "")
    return NumberHit(raw=text[start : m.end()], normalized=normalized, start=start, end=m.end())


def _scan(text: str, protected: frozenset[str]) -> list[NumberHit]:
    """Every number `text` states, outside the protected strings and the exempt
    phrases, in order."""
    masked = _mask(text, _protected_spans(text, protected) + _exempt_spans(text))
    hits = [_numeric_hit(masked, m) for m in _NUMERIC.finditer(masked)]
    for m in _SPELLED.finditer(masked):
        words = [w.lower() for w in re.split(r"[\s-]+", m.group(0))]
        hits.append(NumberHit(m.group(0), str(_spelled_value(words)), m.start(), m.end()))
    for m in _MULTIPLE.finditer(masked):
        hits.append(NumberHit(m.group(0), _MULTIPLES[m.group(0).lower()], m.start(), m.end()))
    for i, c in enumerate(masked):
        if unicodedata.category(c) == "No":
            hits.append(NumberHit(c, _canonical(Decimal(str(unicodedata.numeric(c)))), i, i + 1))
    # Raw spans come from the masked text, whose offsets equal the original's.
    return sorted(
        (NumberHit(text[h.start : h.end], h.normalized, h.start, h.end) for h in hits),
        key=lambda h: h.start,
    )


def _walk(value: Any, key: str | None, protected_fields: frozenset[str], out: dict) -> None:
    if value is None or isinstance(value, bool):
        # `int(True)` is 1 (CLAUDE.md): a flag licenses no number.
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            _walk(v, str(k), protected_fields, out)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, key, protected_fields, out)
    elif isinstance(value, str):
        if key in protected_fields:
            if value.strip():
                out["protected"].add(value.strip())
        else:
            out["strings"].append(value)
    elif isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"numbers: non-finite value at {key!r}")
        try:
            out["values"].add(_canonical(Decimal(str(value))))
        except InvalidOperation as exc:
            raise ValueError(f"numbers: unreadable number at {key!r}: {value!r}") from exc
    else:
        raise TypeError(f"numbers: cannot read a {type(value).__name__} at {key!r}")


def allowed_numbers(
    payload: Mapping[str, Any], *, protected_fields: Iterable[str]
) -> NumberAllowList:
    """The numbers `payload` licenses. Strings under a key in `protected_fields`
    (at any depth) are protected tokens and license no number of their own;
    every other string licenses the numbers it states."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"numbers: payload must be a mapping, not {type(payload).__name__}")
    out: dict[str, Any] = {"values": set(), "protected": set(), "strings": []}
    _walk(payload, None, frozenset(protected_fields), out)
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
    if hit.normalized in allowed.values:
        return True
    # A percentage of a value given bare is that value with its unit; the
    # reverse ("40" for a given "40%") changes the claim and is refused.
    return hit.normalized.endswith("%") and hit.normalized[:-1] in allowed.values


def unallowed_numbers(text: str, allowed: NumberAllowList) -> tuple[NumberHit, ...]:
    """Every number `text` states that `allowed` does not license, in order."""
    if not isinstance(text, str):
        raise TypeError(f"numbers: text must be a str, not {type(text).__name__}")
    hits = tuple(h for h in _scan(text, allowed.protected) if not _is_allowed(h, allowed))
    _log.debug("numbers.checked", chars=len(text), refused=len(hits))
    return hits


__all__ = ["NumberAllowList", "NumberHit", "allowed_numbers", "unallowed_numbers"]
