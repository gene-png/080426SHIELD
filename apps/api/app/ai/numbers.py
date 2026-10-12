"""The shared literal-number validator for AI-drafted prose (#1063, #1071).

THE RULE. AI-drafted narrative may state only numbers present in the input it
was given (#736 6115899208, P1 rule 1; 6115903398, G2). LICENSING IS STRICT
(#736 6116092992, ruling 2; 6116519635, F5 and F6): only what sits under a
field the caller declares as a FACT (a top-level key, or a dotted path to a
nested one) licenses numbers, at any depth beneath it
(numbers, and the text of strings); anything outside every fact field, number
or string, licenses nothing. A percent is a distinct form (ruling 1). Catalog codes and
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

So the module writes code only for the forms it ACCEPTS. A composition ("two
dozen", "40 per cent", "–5%") or an ATTACHED unit ("$5mn") is not a plain
numeral and is not in a fact, so it is refused without a list. A SEPARATED unit
("$5 Bn", "50 bps") is caught by SHAPE: any short alphabetic token after a
numeral joins it (see the unit rule below), so it too needs no list. Only the
stoplist of short function words that may follow a number is enumerated.

JOINING RULES (where one span ends):
  - a comma, period or colon joins digit to digit with no whitespace: a
    thousands group ("1,200") and a decimal ("40.5") are plain numerals; any
    other ("3,5", "1,20", "3:1", "10:30") is one span refused unless a fact says
    it verbatim. "3, 5 and 7" is three spans;
  - whitespace joins only where one side is a number WORD ("two dozen",
    "40 per cent", "5 million"), where a magnitude or a short unit follows a
    numeral ("$5 bn", "5 M", "3 x", "$5 Bn", "50 bps"; see THE UNIT RULE) or
    "×" precedes one ("× 3"), or across "and" after a scale word ("one
    hundred and five"); never numeral to numeral;
  - a dash joins as a sign directly before a numeral, as a range between
    numerals with no whitespace ("3–5"), in a compound with a number word
    ("twenty-one", "twenty-first", "40-percent"), or before a magnitude or
    short unit ("5-fold", "5-day");
  - a slash joins numerals only, with no whitespace ("1/3", "10/12/2026");
  - a currency mark joins the numeral it touches; a percent mark ("%", "％",
    "٪", "‰") joins the span before it across any whitespace.

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


# The closed lists of number WORDS (case-insensitive), GENERATED from the
# cardinal stems so an ordinal or fraction cannot silently drop out of a
# hand-kept list again (#1088 round 3, finding 1).
_CARDINALS: tuple[str, ...] = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty", "thirty",
    "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
)  # fmt: skip
_SCALES: tuple[str, ...] = ("hundred", "thousand", "million", "billion", "trillion")
_ORDINAL_IRREGULAR = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}


def _ordinal(cardinal: str) -> str:
    if cardinal in _ORDINAL_IRREGULAR:
        return _ORDINAL_IRREGULAR[cardinal]
    if cardinal.endswith("y"):
        return cardinal[:-1] + "ieth"
    return cardinal + "th"


# "first" and "second" are left out on purpose: they are ordinary prose ("the
# first step", "a second review") far more often than counts. "zeroth" is not
# a word anyone writes.
_ORDINALS = frozenset(_ordinal(c) for c in (*_CARDINALS[3:], *_SCALES)) | {"third"}
# The multiplier family, generated like the ordinals (#1088 round 4, F2):
# base, -d, -s and -ing for each stem ("quadruple", "quadrupled",
# "quadruples", "quadrupling").
_MULTIPLIER_STEMS: tuple[str, ...] = (
    "double", "triple", "treble", "quadruple", "quintuple", "sextuple",
    "septuple", "octuple",
)  # fmt: skip
_MULTIPLIERS = frozenset(
    form for stem in _MULTIPLIER_STEMS for form in (stem, stem + "d", stem + "s", stem[:-1] + "ing")
)
_TENS: frozenset[str] = frozenset(_CARDINALS[20:])
_NUMBER_WORDS = frozenset(
    {
        *_CARDINALS,
        *_SCALES,
        *(s + "s" for s in _SCALES),
        "lakh", "lakhs", "crore", "crores",
        *_ORDINALS,
        *(o + "s" for o in _ORDINALS),  # fractions: "fifths", "tenths"
        "dozen", "dozens", "single", "pair", "pairs",
        "half", "halves", "halve", "halved", "halving",
        "percent", "pct",
        "twice", "thrice",
        *_MULTIPLIERS,
    }
)  # fmt: skip
# Deliberate exclusions (#1088 round 3, advisory 6): "none", "nil", "couple",
# "several", "score" and "gross" are prose far more often than counts ("none of
# the tools", "a couple of findings", "risk score", "gross margin").
_SCALE_WORDS = frozenset(
    {*_SCALES, *(s + "s" for s in _SCALES), "lakh", "lakhs", "crore", "crores"}
)
_FOLD_PREFIXES = frozenset((*_CARDINALS[2:], *_SCALES))
# "quarter" counts only joined to another number token ("a quarter", "three
# quarters"): alone it is a reporting period ("this quarter").
_WEAK_WORDS = frozenset({"quarter", "quarters"})
# "a" / "an" count only directly before one of these ("a dozen", "a fifth").
_ARTICLE_TARGETS = frozenset({"dozen", "half", "quarter", *_ORDINALS})
# A magnitude or multiplier token AFTER a numeral, across whitespace or a dash
# ("$5 bn", "5 M", "5 K", "5-fold", "3 x", "3×"), or "×" BEFORE one ("×3").
# Case-sensitive. Alone it is prose ("press x", "M to mute"). "5 m" is joined
# and therefore refused on purpose: minutes, metres or millions, unknowable.
_MAGNITUDES = frozenset({"bn", "MM", "M", "K", "B", "T", "k", "m", "x", "fold", "\u00d7"})
# Longer magnitude spellings, matched case-insensitively (#1088 round 5, F2).
# Four-lowercase-letter forms would otherwise pass as nouns (see THE UNIT RULE).
_MAGNITUDES_ANY_CASE = frozenset(
    {"mill", "mln", "bill", "bln", "trln", "lac", "lacs", "thou", "grand"}
)
# THE UNIT RULE (#1088 round 4, F1). Any other short alphabetic token after a
# numeral (across whitespace or a dash) is treated as a unit and joins it, so a
# separated unit fails by its shape rather than by a list ("$5 Bn", "$5 tn",
# "50 bps", "40 pc", "5-day"). RESIDUAL, stated honestly: a four-lowercase
# unit abbreviation that is in no list ("kbps", "mbps") reads as a count noun
# and passes with the bare numeral, as "12 rows" must.
# "Short" is one to three letters in any case, or four letters with a capital
# ("GBPS", "Gbps"; five-letter "MMBTU" is out). Four lowercase letters are left out on
# purpose: "12 rows", "4 tools", "7 apps" are counts followed by nouns, and
# joining them would refuse ordinary prose.
# The stoplist below holds the short FUNCTION words that follow a number in
# prose. "per" never joins either: it is its own token kind, merged only into
# "per cent" / "per-cent"; in "2 per user" the rate word does not change the
# value, and the numeral alone is what the payload licenses. "rev" is here because
# "800-53 rev 5" names a revision, not a unit.
_UNIT_STOPWORDS = frozenset(
    {
        "a", "an", "the", "of", "in", "on", "at", "to", "and", "or", "nor",
        "for", "by", "is", "are", "was", "be", "as", "if", "so", "but",
        "out", "off", "up", "via", "vs", "new", "old", "all", "any", "few",
        "key", "top", "not", "no", "its", "our", "who", "has", "had", "may",
        "can", "now", "i", "we", "it", "rev",
    }
)  # fmt: skip
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
# Fixed phrases that carry no count: "no one", "third party/parties", and
# domain terms (#1088 round 4, advisory): "Zero Trust", "single sign-on",
# "key pair(s)", "double extortion", "one-time" (password, code).
_EXEMPT_PHRASES: tuple[str, ...] = (
    "no one", "third-party", "third party", "third parties", "zero trust",
    "single sign-on", "key pairs", "key pair", "double extortion", "one-time",
)  # fmt: skip

_DASHES = "-‐‑‒–—−"
_CURRENCY = "$€£"
# "%", full-width "％", Arabic "٪" (U+066A) and per mille "‰" (U+2030).
_PERCENT = "%\uff05\u066a\u2030"
_TOKEN = re.compile(r"\w+|\S")
# Accepted form A. `\d` is Unicode-aware, so full-width and other-script
# digits are plain numerals; `Decimal` reads them.
_PLAIN = re.compile(
    r"(?P<sign>[-−])?(?P<cur>[$€£])?"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<pct>%)?"
)
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")

# Token kinds.
_NUM, _WORD, _ROMAN, _WEAK, _MAG, _UNIT, _ART, _CUR, _PCT, _DASH, _OTHER = (
    "num", "word", "roman", "weak", "mag", "unit", "art", "cur", "pct", "dash", "other"
)  # fmt: skip
_BEARING = frozenset({_NUM, _WORD, _ROMAN, _WEAK, _MAG, _UNIT})
# Tokens that make a span a number on their own; a span of only "quarter" or
# only a magnitude letter is prose.
_STRONG = frozenset({_NUM, _WORD, _ROMAN})  # a lone magnitude or unit is prose
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
        spans.extend(
            (m.start(), m.end())
            for m in re.finditer(pattern, text)
            if not _edge_touched(text, m.start(), m.end())
        )
    return spans


_NEXT_WORD = re.compile(r"[\s" + re.escape(_DASHES) + r"]+(\w+)")


def _edge_touched(text: str, start: int, end: int) -> bool:
    """Whether a protected match has a DIGIT at an edge that a number form
    touches (#1088 round 8). Masking it would hide a number the text states:
    "Windows 10%" for protected "Windows 10", "$40 hosts" for "40 hosts".
    After a trailing digit: a percent mark (across any whitespace), or a
    magnitude, unit or scale word. Before a leading digit: a currency mark or
    a sign. Such a match is NOT masked, so the number is checked."""
    if _is_numeric_char(text[end - 1]):
        rest = text[end:]
        if re.match(rf"\s*[{_PERCENT}]", rest):
            return True
        m = _NEXT_WORD.match(rest)
        if m and _is_magnitude_like(m.group(1)):
            return True
    if _is_numeric_char(text[start]) and start > 0:
        before = text[start - 1]
        if before in _CURRENCY or before in _DASHES:
            return True
    return False


def _is_magnitude_like(word: str) -> bool:
    low = word.casefold()
    return (
        word in _MAGNITUDES
        or low in _MAGNITUDES_ANY_CASE
        or low in _SCALE_WORDS
        or low in ("percent", "pct")
        or _is_unit_shape(word)
    )


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


def _merge_length(toks: list[_Tok], i: int, masked: str) -> int:
    """How many tokens from `i` form one number word: "per cent" and
    "per-cent", "percentage point(s)", and "a"/"an" before a fraction or
    dozen word ("a fifth"). 0 when none does."""
    t = toks[i]
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if nxt is None:
        return 0
    spaced = masked[t.end : nxt.start].isspace()
    if t.kind == "per":
        if spaced and nxt.kind == "cent":
            return 2
        after = toks[i + 2] if i + 2 < len(toks) else None
        if (
            nxt.kind == _DASH
            and after is not None
            and after.kind == "cent"
            and t.end == nxt.start
            and nxt.end == after.start
        ):
            return 3
        return 0
    if t.kind == "percentage" and nxt.kind == _DASH:
        after = toks[i + 2] if i + 2 < len(toks) else None
        if (
            after is not None
            and after.kind in ("point", "points")
            and t.end == nxt.start
            and nxt.end == after.start
        ):
            return 3
    if t.kind in ("percentage", "basis") and spaced and nxt.kind in ("point", "points"):
        return 2
    if t.kind == _ART and spaced and nxt.text.casefold() in _ARTICLE_TARGETS:
        return 2
    return 0


def _is_unit_shape(word: str) -> bool:
    if not word.isalpha() or word.casefold() in _UNIT_STOPWORDS:
        return False
    # Four letters count only with a capital in them ("GBPS", "Gbps", "KWhs"):
    # four lowercase letters are a noun after a count ("12 rows").
    return len(word) <= 3 or (len(word) == 4 and not word.islower())


def _word_kind(word: str, previous: str | None) -> str:
    low = word.casefold()
    if any(_is_numeric_char(c) for c in word):
        return _NUM
    if word in _MAGNITUDES or low in _MAGNITUDES_ANY_CASE:
        return _MAG
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
    if low in ("per", "cent", "percentage", "basis", "point", "points"):
        return low
    if _is_unit_shape(word):
        return _UNIT
    return _OTHER


def _tokens(masked: str) -> list[_Tok]:
    toks: list[_Tok] = []
    previous_word: str | None = None
    for m in _TOKEN.finditer(masked):
        t = m.group(0)
        if t[0].isalnum() or t[0] == "_" or _is_numeric_char(t[0]):
            kind = _word_kind(t, previous_word)
            previous_word = t
        elif t in _MAGNITUDES:
            kind = _MAG  # "×"
        elif t in _CURRENCY:
            kind = _CUR
        elif t in _PERCENT:
            kind = _PCT
        elif t in _DASHES:
            kind = _DASH
        else:
            kind = _OTHER
        toks.append(_Tok(kind, m.start(), m.end(), t))
    # "first" and "second" are number words INSIDE a dash compound with a tens
    # word ("twenty-first", "thirty-second"), so the span is whole on both the
    # fact and the text side (#1088 round 4, F3). Alone they stay prose.
    for k in range(2, len(toks)):
        t, dash, tens = toks[k], toks[k - 1], toks[k - 2]
        if (
            t.text.casefold() in ("first", "second")
            and dash.kind == _DASH
            and tens.end == dash.start
            and dash.end == t.start
            and tens.text.casefold() in _TENS
        ):
            t.kind = _WORD
    # "per cent" is one number word; "a"/"an" before a fraction or dozen word
    # merges into it. Any other "per", "cent", "a" or "an" is plain prose.
    merged: list[_Tok] = []
    i = 0
    while i < len(toks):
        t = toks[i]
        n = _merge_length(toks, i, masked)
        if n:
            last = toks[i + n - 1]
            merged.append(_Tok(_WORD, t.start, last.end, masked[t.start : last.end]))
            i += n
            continue
        if t.kind in ("per", "cent", "percentage", "basis", "point", "points", _ART):
            t = _Tok(_OTHER, t.start, t.end, t.text)
        merged.append(t)
        i += 1
    return merged


def _joins(a: _Tok, gap: list[_Tok], gap_text: str, b: _Tok) -> bool:
    """Whether bearing tokens `a` and `b`, with `gap` between them, are one span."""
    # A number word joins a number-bearing neighbour, never a unit or magnitude
    # ("hundredth row" is a word and a noun, not a unit).
    loose = (_UNIT,)  # a magnitude DOES join a number word ("five bn", "five-fold")
    wordish = (a.kind in _WORDISH and b.kind not in loose) or (
        b.kind in _WORDISH and a.kind not in loose
    )
    # A magnitude or unit joins the numeral before it ("5 bn", "3×", "5-fold"),
    # and "×" joins the numeral after it ("×3"). A magnitude also joins a
    # number WORD through `wordish` above ("five bn"); a unit never does.
    magnitude = (a.kind == _NUM and b.kind in (_MAG, _UNIT)) or (
        a.text == "\u00d7" and b.kind == _NUM
    )
    if not gap:
        if gap_text == "":
            return True  # adjacent: "3" then "×"
        return gap_text.isspace() and (wordish or magnitude)
    if (
        len(gap) == 1
        and a.text.casefold() in _SCALES  # "one hundred and five", not "tenth and twelfth"
        and b.kind == _WORD
        and re.fullmatch(r"\s+and\s+", gap_text, re.IGNORECASE) is not None
    ):
        return True  # "one hundred and five" (#1088 round 4, F3)
    if len(gap) != 1 or gap_text != gap[0].text:
        return False  # anything with whitespace around punctuation breaks a span
    sep = gap[0].text
    a_digit = a.text[-1:].isdecimal()
    if sep in (",", ".", ":"):
        # Digit to digit with no whitespace is ONE span: a thousands group
        # ("1,200"), a decimal ("40.5"), or anything else ("3,5" is 3.5 in many
        # locales; "1,20", "3:1", "10:30"), which is then refused as not a
        # plain numeral unless a fact says it verbatim (#1088 round 3, F4).
        return a_digit and b.text[:1].isdecimal()
    if sep == "/":
        return a.kind == _NUM and b.kind == _NUM
    if gap[0].kind == _DASH:
        return wordish or (a.kind == _NUM and b.kind in (_NUM, _MAG, _UNIT))
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
                spans[-1][4] |= t.kind in _STRONG
                joined = True
        if not joined:
            spans.append([t.start, t.end, i, 1, t.kind in _STRONG])
        last_bearing = i
    out: list[tuple[int, int]] = []
    for start, end, first, _n, strong in spans:
        if not strong:
            continue  # a lone "quarter" or magnitude letter is prose, not a number
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
        # A percent mark after the span, after ANY whitespace, including a
        # no-break or narrow no-break space (#1088 round 3, finding 2).
        rest = masked[end:]
        m = re.match(rf"\s*[{_PERCENT}]", rest)
        if m:
            end += m.end()
        out.append((start, end))
    return out


def _normalize_display(raw: str) -> str:
    """Thousands commas removed and whitespace collapsed. Case is folded ONLY
    for a span with no digit or numeric character, i.e. spelled number words
    and Roman numerals: a unit's case carries meaning ("45m" is not "45M",
    #1088 round 4, F4)."""
    text = re.sub(r"\s+", " ", _THOUSANDS.sub("", raw)).strip()
    if any(_is_numeric_char(c) for c in text):
        # Fold only the spelled number words ("5 Million" is "5 million"); a
        # unit keeps its case (#1088 round 5, advisory 4).
        return re.sub(
            r"[^\W\d_]+",
            lambda m: (
                m.group(0).casefold() if m.group(0).casefold() in _NUMBER_WORDS else m.group(0)
            ),
            text,
        )
    return text.casefold()


def _plain_value(raw: str) -> str | None:
    """The canonical value of a plain numeral, or None if `raw` is not one."""
    m = _PLAIN.fullmatch(raw)
    if m is None:
        return None
    num = Decimal(m.group("num").replace(",", ""))
    if m.group("sign"):
        num = -num
    return _canonical(num) + ("%" if m.group("pct") else "")


def _walk(
    value: Any,
    key: str | None,
    path: tuple[str, ...],
    fields: dict[str, Any],
    out: dict,
    in_fact: bool,
) -> None:
    """`path`: the keys from the root (lists are transparent). `in_fact`: the
    path passed through a declared fact. Rulings F5 and F6 (#736 6116519635):
    numbers and strings license ONLY under a fact, and a fact licenses
    everything beneath it, dicts and lists alike. Facts are matched by their
    path from the TOP LEVEL ("summary" or "service.summary"), never by a key
    name found at any depth (#1088 round 6): a same-named key inside a
    non-fact subtree, such as an id, licenses nothing. Protected names match
    the same way (#1088 round 7): a same-named key elsewhere is NOT protected,
    so its text is checked like any other."""
    if value is None or isinstance(value, bool):
        # `int(True)` is 1 (CLAUDE.md): a flag licenses no number.
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if "." in str(k) and _ambiguous(str(k), fields["declared"]):
                # A dotted key is allowed (CSF and ATT&CK codes are natural
                # keys) unless it equals a declared dotted path or a prefix of
                # one, where it could be read either way (#1088 round 8).
                raise ValueError(
                    f"numbers: payload key {str(k)!r} is ambiguous with a declared dotted path"
                )
            child = (*path, str(k))
            out["paths"].add(child)
            _walk(v, str(k), child, fields, out, in_fact or child in fields["facts"])
    elif isinstance(value, (list, tuple)):
        for v in value:
            _walk(v, key, path, fields, out, in_fact)
    elif isinstance(value, str):
        # PRECEDENCE: a protected path wins over an enclosing fact. Its string
        # is written as given and licenses no number of its own; the rest of
        # the fact still licenses (#1088 round 7).
        if path in fields["protected"]:
            if value.strip() and not any(c.isalpha() for c in value):
                # A numeral is not a code: protecting "40" would mask it
                # everywhere and let "40%" and "$40" through (#1088 round 3, F5).
                raise ValueError(
                    f"numbers: protected field {key!r} holds an all-numeric value; "
                    "list it as a fact field instead"
                )
            if value.strip():
                out["protected"].add(value.strip())
        elif in_fact:
            out["strings"].append(value)
        # Any other string licenses nothing (ruling 2): ids, timestamps and
        # identifiers carry digits that are not facts.
    elif isinstance(value, (int, float, Decimal)):
        # Finiteness is checked BEFORE the fact test, so a NaN or Infinity is
        # refused wherever it sits, not only inside a fact (#1088 round 6).
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"numbers: non-finite value at {key!r}")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError(f"numbers: non-finite value at {key!r}")
        if not in_fact:
            return  # F5: a number outside every fact field licenses nothing
        try:
            out["values"].add(_canonical(Decimal(str(value))))
        except InvalidOperation as exc:
            raise ValueError(f"numbers: unreadable number at {key!r}: {value!r}") from exc
    else:
        raise TypeError(f"numbers: cannot read a {type(value).__name__} at {key!r}")


def _ambiguous(key: str, declared: frozenset[str]) -> bool:
    return any(d == key or d.startswith(key + ".") for d in declared)


def _field_paths(names: Iterable[str], what: str) -> frozenset[tuple[str, ...]]:
    """Each name as a path from the top level: "summary" -> ("summary",),
    "service.summary" -> ("service", "summary")."""
    if isinstance(names, str):
        # `frozenset("code")` is {"c", "o", "d", "e"}: it would match nothing.
        raise TypeError(f"numbers: {what} must be an iterable of names, not a str")
    paths: set[tuple[str, ...]] = set()
    for name in names:
        if not isinstance(name, str):
            raise TypeError(f"numbers: {what} entries must be str, not {type(name).__name__}")
        paths.add(tuple(name.split(".")))
    return frozenset(paths)


def allowed_numbers(
    payload: Mapping[str, Any],
    *,
    fact_fields: Iterable[str],
    protected_fields: Iterable[str],
) -> NumberAllowList:
    """What `payload` licenses, strictly. Each name in `fact_fields` is a path
    from the TOP LEVEL ("summary", or dotted "service.summary"; lists are
    transparent). Beneath a fact, at any depth: every numeric value, and for
    every string each of its spans verbatim and each plain numeral's value.
    Strings at a path in `protected_fields` (matched the same way) may be
    written as given and license nothing else; a protected path inside a fact
    takes precedence over the fact for that one value. Anything outside every
    fact licenses nothing. A path that matches nothing, a dotted payload key
    that is ambiguous with a declared dotted path, or a non-str entry in either
    list raises."""
    if not isinstance(payload, Mapping):
        raise TypeError(f"numbers: payload must be a mapping, not {type(payload).__name__}")
    fields = {
        # A fact is a path from the top level: "summary", or "service.summary".
        "facts": _field_paths(fact_fields, "fact_fields"),
        "protected": _field_paths(protected_fields, "protected_fields"),
    }
    fields["declared"] = frozenset(".".join(p) for p in fields["facts"] | fields["protected"])
    out: dict[str, Any] = {
        "values": set(),
        "protected": set(),
        "strings": [],
        "paths": set(),
    }
    _walk(payload, None, (), fields, out, False)
    unmatched = sorted(".".join(f) for f in (fields["facts"] | fields["protected"]) - out["paths"])
    if unmatched:
        raise ValueError(f"numbers: listed fields match nothing in the payload: {unmatched}")
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
