"""The shared literal-number validator (`app.ai.numbers`), for #1063 and #1071.

THE RULE UNDER TEST comes from the advisor's rulings, not from the module:

- #736 6115899208 (P1 rule 1): write a number only if that exact value appears
  in the input; "Do not write numbers as words"; catalog identifiers and names
  given in the input may be written as given.
- #736 6115903398 (EV-2, G2): no number, date, year, version or count "except
  a fact value copied exactly from `facts`".
- #736 6116092992: ruling 1, a percent is a distinct form; ruling 2, strict
  licensing. #736 6116519635: F5, only what sits under a declared fact field
  licenses, numbers included; F6, a fact field licenses everything beneath
  it. Round 6: fact names match TOP-LEVEL keys, or a dotted path.
- The round-2 review of #1088 and the coordinator's design (fail closed):
  number-bearing text is read as whole SPANS; a span is licensed only as a
  plain numeral whose value is licensed, or as an exact display string from a
  fact field. Everything else in a span is a hit. The joining rules decide
  where one span ends: a comma, period or colon joins digit to digit with no
  whitespace (a thousands group or decimal stays a plain numeral; anything else
  is refused); whitespace joins beside a number word, before a magnitude or a
  short unit after a numeral, or "and" between number words; a dash joins as a
  sign, a range between numerals, a compound with a number word, or before a
  magnitude or unit; a slash joins numerals only.

Every expected value below is TYPED here from those rules. Nothing is read
from the module's own tables (CLAUDE.md, #72). The corpus enumerates classes,
each with an allowed case and a refused case (D-087).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.numbers import NumberAllowList, NumberHit, allowed_numbers, unallowed_numbers

pytestmark = pytest.mark.unit


def _refused(
    text: str,
    payload: dict,
    protected: tuple[str, ...] = (),
    facts: tuple[str, ...] | None = None,
) -> list[str]:
    """The raw spans the validator refuses, in order.

    SETUP, not outcome: rows list a few protected names per group, so only the
    ones each row's payload carries are passed, and every other key a row gives
    is declared a fact unless `facts` says otherwise. The strict rule itself
    (only fact fields license, ruling F5) has its own tests below."""
    present = tuple(f for f in protected if f in payload)
    if facts is None:
        facts = tuple(k for k in payload if k not in present)
    allowed = allowed_numbers(payload, fact_fields=facts, protected_fields=present)
    return [hit.raw for hit in unallowed_numbers(text, allowed)]


# --- 1. Plain numerals: digits, thousands separators, decimals -------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("12 rows were scored.", {"n": 12}, []),
        ("13 rows were scored.", {"n": 12}, ["13"]),
        ("Spend was 1,200 this year.", {"spend": 1200}, []),
        ("Spend was 1200 this year.", {"spend": "1,200"}, []),
        ("Spend was 1,300 this year.", {"spend": 1200}, ["1,300"]),
        ("Coverage stands at 40.0 here.", {"pct": 40}, []),
        ("Coverage stands at 40 here.", {"pct": 40.0}, []),
        ("Coverage stands at 40.5 here.", {"pct": Decimal("40.50")}, []),
        ("Coverage stands at 40.6 here.", {"pct": 40.5}, ["40.6"]),
        ("1,908 values applied.", {"n": 1908}, []),
        ("1.908 values applied.", {"n": 1908}, ["1.908"]),
    ],
)
def test_plain_numerals(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 2. Percent, currency, minus signs --------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Detection covers 40% of techniques.", {"pct": "40%"}, []),
        # Ruling 1: a bare 40 does not license "40%", nor "40%" a bare 40.
        ("Detection covers 40% of techniques.", {"pct": 40}, ["40%"]),
        ("Detection covers 40 techniques.", {"pct": "40%"}, ["40"]),
        ("The total is $40,000,962.", {"total": 40000962}, []),
        ("The total is $40,000,963.", {"total": 40000962}, ["$40,000,963"]),
        ("Spend was €1,200.", {"spend": 1200}, []),
        ("Spend was £1,300.", {"spend": 1200}, ["£1,300"]),
        ("The balance moved by -3 points.", {"delta": -3}, []),
        ("The balance moved by -3 points.", {"delta": 3}, ["-3"]),
        # U+2212 MINUS SIGN is a minus sign.
        ("The balance moved by −3 points.", {"delta": -3}, []),
        ("The balance moved by −3 points.", {"delta": 3}, ["−3"]),
    ],
)
def test_percent_currency_and_minus(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 3. Forms accepted ONLY verbatim from a fact field ----------------------------
# Review round 2, F1-F3, plus words, suffixes, ordinals and fractions: none is a
# plain numeral, so none is licensed by a value, only by the same display text.


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # F1: scale suffixes, every spelling.
        ("Spend was $5m.", {"spend": 5000000}, ["$5m"]),
        ("Spend was $5mn.", {"spend": 5}, ["$5mn"]),
        ("Spend was $5MM.", {"spend": 5000000}, ["$5MM"]),
        ("Spend was $5Bn.", {"spend": 5}, ["$5Bn"]),
        ("Spend was $240k.", {"spend": 240000}, ["$240k"]),
        ("Spend was $240k.", {"spend": "$240k"}, []),
        ("Spend was €1.2M.", {"spend": "€1.2M"}, []),
        # The display normalisation drops thousands commas on both sides.
        ("Spend was €1200k.", {"spend": "€1,200k"}, []),
        ("Spend was €1,200k.", {"spend": "€1200k"}, []),
        # F7: a lowercase "m" is never read as millions; the span is refused.
        ("It took 5m.", {"n": 5}, ["5m"]),
        # F2: spelled and variant percents.
        ("Coverage is forty percent.", {"pct": "40%"}, ["forty percent"]),
        ("Coverage is 40 per cent.", {"pct": "40%"}, ["40 per cent"]),
        ("Coverage is 40-percent.", {"pct": "40%"}, ["40-percent"]),
        ("Coverage is 40 percent.", {"pct": "40%"}, ["40 percent"]),
        ("Coverage is 40％.", {"pct": "40%"}, ["40％"]),
        ("Coverage is 40 percent.", {"note": "40 percent"}, []),
        # F3: compositions are whole spans.
        ("Two dozen tools overlap.", {"n": 24}, ["Two dozen"]),
        ("2 hundred tools overlap.", {"n": 200}, ["2 hundred"]),
        ("Half a dozen tools overlap.", {"n": 6}, ["Half a dozen"]),
        ("Five million rows.", {"n": 5000000}, ["Five million"]),
        # Spelled numbers: refused unless the fact text says the same words.
        ("Three tools overlap.", {"n": 3}, ["Three"]),
        ("Three tools overlap.", {"summary": "three tools"}, []),
        ("Twenty-one tools overlap.", {"n": 21}, ["Twenty-one"]),
        ("Spend doubled in a year.", {}, ["doubled"]),
        ("Spend rose twice as fast.", {}, ["twice"]),
        ("Spend was cut by half.", {"share": 0.5}, ["half"]),
        ("Spend grew tenfold.", {"x": 10}, ["tenfold"]),
        ("Hundreds of rows lack notes.", {"n": 300}, ["Hundreds"]),
        ("A dozen tools overlap.", {"n": 12}, ["A dozen"]),
        # Fractions.
        ("One third of rows lack evidence.", {"n": 3}, ["One third"]),
        ("One third of rows lack evidence.", {"share": "one third"}, []),
        ("Two-thirds of rows lack evidence.", {"share": "2/3"}, ["Two-thirds"]),
        ("A quarter of rows lack evidence.", {"share": 0.25}, ["A quarter"]),
        ("Three quarters of rows lack evidence.", {"n": 3}, ["Three quarters"]),
        # Ordinals with digits.
        ("The 3rd finding repeats.", {"n": 3}, ["3rd"]),
        ("The 3rd finding repeats.", {"rank": "3rd"}, []),
    ],
)
def test_forms_licensed_only_verbatim(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 4. What is NOT a number ------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "No one owns this; a third-party tool covers it.",
        "A third party hosts it.",
        "Spend fell this quarter.",
        "I think it applies.",
        # F7: C, D, L and M are not read as Roman numerals ("CD", "MD", "XL").
        "Backups go to CD and the MD signs off; size XL.",
        # Words outside the closed list.
        "It was the first step and the second review.",
    ],
)
def test_text_with_no_number(text: str) -> None:
    assert _refused(text, {}) == []


# --- 5. Unicode digits, superscripts, letter-numbers, Roman numerals -------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Full-width １２ rows.", {"n": 12}, []),
        ("Full-width １３ rows.", {"n": 12}, ["１３"]),
        ("Arabic-Indic ٣ rows.", {"n": 3}, []),
        ("Arabic-Indic ٣ rows.", {"n": 4}, ["٣"]),
        ("Area of 10² units.", {"a": 10}, ["10²"]),
        ("Volume Ⅻ applies.", {"v": 12}, ["Ⅻ"]),
        ("Volume Ⅻ applies.", {"v": "Ⅻ"}, []),
        ("Tier III applies.", {"tier": 3}, ["III"]),
        ("Tier III applies.", {"tier": "Tier III"}, []),
        ("IV of them apply.", {"n": 4}, ["IV"]),
        # F8: a context word in any case.
        ("It is tier V.", {"tier": 5}, ["V"]),
        ("Phase V applies.", {"phase": "Phase V"}, []),
    ],
)
def test_unicode_and_roman(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 6. Dates, years, versions, periods -------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Released on 2026-10-12.", {"date": "2026-10-12"}, []),
        ("Released on 2026-10-12.", {"y": 2026, "m": 10, "d": 12}, ["2026-10-12"]),
        ("Approved in March 2026.", {"year": 2026}, []),
        ("Approved in March 2026.", {}, ["2026"]),
        ("It follows NIST 800-53 rev 5.", {}, ["800-53", "5"]),
        ("It follows NIST 800-53 rev 5.", {"std": "800-53", "rev": 5}, []),
        ("It runs v2.1 of the agent.", {"version": "v2.1"}, []),
        ("It runs v2.1 of the agent.", {"version": "2.1"}, ["v2.1"]),
        ("Spend fell in Q3 FY25.", {"period": "Q3 FY25"}, []),
        ("Spend fell in Q3 FY25.", {}, ["Q3", "FY25"]),
        ("It needs 2FA.", {}, ["2FA"]),
    ],
)
def test_dates_versions_and_periods(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 7. Protected codes and names -------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("PR.PS-01 is weak.", {"code": "PR.PS-01"}, []),
        ("PR.PS-02 is weak.", {"code": "PR.PS-01"}, ["02"]),
        ("PR.PS-01 has 01 owner.", {"code": "PR.PS-01"}, ["01"]),
        ("PR.PS-01.3 is weak.", {"code": "PR.PS-01"}, ["01.3"]),
        ("T1003 applies.", {"code": "T1003"}, []),
        ("It is T1003.", {"code": "T1003"}, []),
        ("T1003.002 applies.", {"code": "T1003"}, ["T1003.002"]),
        # F4: an en dash, a slash and an underscore continue a code too.
        ("T1003–002 applies.", {"code": "T1003"}, ["T1003–002"]),
        ("T1003/002 applies.", {"code": "T1003"}, ["T1003/002"]),
        ("T1003_002 applies.", {"code": "T1003"}, ["T1003_002"]),
        ("Microsoft 365 E5 covers it.", {"tool": "Microsoft 365 E5"}, []),
        ("Microsoft 365 E3 covers it.", {"tool": "Microsoft 365 E5"}, ["365", "E3"]),
        ("Hashes use SHA256 on x86.", {"algo": "SHA256", "arch": "x86"}, []),
        ("Hashes use SHA256 on x86.", {}, ["SHA256", "x86"]),
    ],
)
def test_protected_codes_and_names(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload, protected=("code", "tool", "algo", "arch")) == refused


# --- 8. Joining rules: where one span ends -----------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # A comma followed by whitespace never joins.
        ("Techniques 3, 5 and 7 apply.", {"a": 3, "b": 5, "c": 7}, []),
        # Round 3, finding 4: a comma that is NOT a thousands group still joins
        # digit to digit with no space, because "3,5" is 3.5 in many locales
        # (the locale class); the span is then refused as not a plain numeral.
        ("Values 3,5 apply.", {"a": 3, "b": 5}, ["3,5"]),
        ("Spend was 1,200.", {"a": 1, "b": 200}, ["1,200"]),
        # A period joins only digit to digit, with no whitespace.
        ("We found 40. 5 more were added.", {"a": 40, "b": 5}, []),
        ("We found 40.5 rows.", {"a": 40, "b": 5}, ["40.5"]),
        # Whitespace joins only beside a number word, never numeral to numeral.
        ("Scores 40 5 apply.", {"a": 40, "b": 5}, []),
        ("Spend was 5 million.", {"a": 5}, ["5 million"]),
        # A dash joins as a sign, a range between numerals, or a compound with a
        # number word; a spaced dash between numerals does not.
        ("Levels run 3–5 here.", {"a": 3, "b": 5}, ["3–5"]),
        ("Levels run 3-5 here.", {"range": "3-5"}, []),
        ("Levels run 3 – 5 here.", {"a": 3, "b": 5}, []),
        ("A drop of –5% followed.", {"p": "5%"}, ["–5%"]),
        ("A drop of -5% followed.", {"p": "-5%"}, []),
        # A slash joins numerals only.
        ("Rows 1/3 apply.", {"a": 1, "b": 3}, ["1/3"]),
        ("Rows 3 / 5 apply.", {"a": 3, "b": 5}, []),
    ],
)
def test_joining_rules(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 9. Idempotent, empty, very long ----------------------------------------------


def test_text_that_passed_passes_again() -> None:
    payload = {"pct": "40%", "code": "PR.PS-01", "total": 1200}
    allowed = allowed_numbers(payload, fact_fields=("pct", "total"), protected_fields=("code",))
    text = "PR.PS-01 sits at 40% with 1,200 in spend."
    assert unallowed_numbers(text, allowed) == ()
    assert unallowed_numbers(text, allowed) == ()


def test_empty_text_has_no_hits() -> None:
    assert unallowed_numbers("", allowed_numbers({}, fact_fields=(), protected_fields=())) == ()


def test_very_long_text_reports_every_hit_with_its_offsets() -> None:
    text = "Only 7 here. " * 5000 + "And 8 at the end."
    hits = unallowed_numbers(
        text, allowed_numbers({"n": 7}, fact_fields=("n",), protected_fields=())
    )
    assert [h.raw for h in hits] == ["8"]
    assert text[hits[0].start : hits[0].end] == "8"


# --- 10. The hit's shape, strict licensing, fail-loudly inputs -------------------


def test_a_hit_carries_raw_normalized_and_offsets() -> None:
    text = "Spend was $1,300."
    (hit,) = unallowed_numbers(
        text, allowed_numbers({"s": 1200}, fact_fields=(), protected_fields=())
    )
    assert hit == NumberHit(raw="$1,300", normalized="1300", start=10, end=16)


def test_payload_walk_reads_nested_values() -> None:
    # F6: a fact field licenses everything beneath it, dicts and lists alike.
    payload = {"facts": [{"id": "f1", "value": 17}, {"id": "f2", "label": "Has 4 rows"}]}
    assert _refused("17 and 4 hold.", payload, facts=("facts",)) == []


def test_a_boolean_is_not_a_number() -> None:
    # `int(True)` is 1 (CLAUDE.md): a flag must not license the number 1.
    assert _refused("1 tool remains.", {"flag": True}) == ["1"]


@pytest.mark.parametrize(
    "text,payload,facts,refused",
    [
        ("Finding 1 repeats.", {"finding_id": "f1"}, (), ["1"]),
        ("Rows from 2026 apply.", {"created_at": "2026-10-12T09:00:00Z"}, (), ["2026"]),
        ("Rows from 2026 apply.", {"year": "2026"}, ("year",), []),
        # F5 (#736 6116519635): a number licenses only under a fact field.
        ("Service 40 is open.", {"service_id": 40}, (), ["40"]),
        ("Service 40 is open.", {"service_id": 40}, ("service_id",), []),
        # F6: a fact field licenses everything beneath it, at any depth.
        ("Count is 5.", {"facts": {"count": 5}}, ("facts",), []),
        ("Count is 6.", {"facts": {"count": 5}, "other": {"n": 6}}, ("facts",), ["6"]),
        ("Count is 5.", {"facts": [[{"deep": "5 rows"}]]}, ("facts",), []),
        ("Count is 5.", {"facts": {"rows": [5]}}, ("facts",), []),
        ("Detection covers 40%.", {"pct": "40%", "id": "x40"}, ("pct",), []),
        ("Detection covers 40.", {"pct": "40%", "id": "x40"}, ("pct",), ["40"]),
        # A plain numeral inside an undeclared string licenses nothing.
        ("Case 40 is open.", {"ticket": "Case 40"}, (), ["40"]),
        ("Case 40 is open.", {"ticket": "Case 40"}, ("ticket",), []),
    ],
)
def test_only_numbers_and_declared_fact_fields_license(
    text: str, payload: dict, facts: tuple[str, ...], refused: list[str]
) -> None:
    allowed = allowed_numbers(payload, fact_fields=facts, protected_fields=())
    assert [h.raw for h in unallowed_numbers(text, allowed)] == refused


def test_unallowed_numbers_refuses_a_non_string() -> None:
    with pytest.raises(TypeError, match="int"):
        unallowed_numbers(12, allowed_numbers({}, fact_fields=(), protected_fields=()))  # type: ignore[arg-type]


def test_allowed_numbers_refuses_a_non_mapping_payload() -> None:
    with pytest.raises(TypeError):
        allowed_numbers(["not", "a", "mapping"], fact_fields=(), protected_fields=())  # type: ignore[arg-type]


def test_allowed_numbers_refuses_a_value_it_cannot_read() -> None:
    with pytest.raises(TypeError):
        allowed_numbers({"blob": b"\x00\x01"}, fact_fields=(), protected_fields=())


def test_allowed_numbers_refuses_a_non_finite_number() -> None:
    with pytest.raises(ValueError):
        allowed_numbers({"x": float("nan")}, fact_fields=(), protected_fields=())


def test_protected_fields_given_as_a_string_is_refused() -> None:
    with pytest.raises(TypeError, match="str"):
        allowed_numbers(
            {"code": "PR.PS-01"}, fact_fields=(), protected_fields="code"  # type: ignore[arg-type]
        )


def test_fact_fields_given_as_a_string_is_refused() -> None:
    with pytest.raises(TypeError, match="str"):
        allowed_numbers(
            {"pct": "40%"}, fact_fields="pct", protected_fields=()  # type: ignore[arg-type]
        )


def test_a_protected_field_matching_no_key_is_refused() -> None:
    with pytest.raises(ValueError, match="code"):
        allowed_numbers({"n": 1}, fact_fields=(), protected_fields=("code",))


def test_a_fact_field_matching_no_key_is_refused() -> None:
    with pytest.raises(ValueError, match="pct"):
        allowed_numbers({"n": 1}, fact_fields=("pct",), protected_fields=())


def test_the_allow_list_is_a_value_object() -> None:
    allowed = allowed_numbers(
        {"n": 3, "code": "PR.PS-01", "note": "40 percent"},
        fact_fields=("n", "note"),
        protected_fields=("code",),
    )
    assert isinstance(allowed, NumberAllowList)
    assert "3" in allowed.values
    assert "PR.PS-01" in allowed.protected
    assert "40 percent" in allowed.displays


# --- Review round 3 of #1088 (findings 1 to 6) -------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 1: ordinals and fraction words beyond "third", and multipliers.
        ("A fifth of controls lack owners.", {}, ["A fifth"]),
        ("A fifth of controls lack owners.", {"share": "a fifth"}, []),
        ("Two-fifths of rows lack notes.", {}, ["Two-fifths"]),
        ("The tenth finding repeats.", {}, ["tenth"]),
        ("The tenth finding repeats.", {"rank": "tenth"}, []),
        ("The twelfth and twentieth rows apply.", {}, ["twelfth", "twentieth"]),
        ("The hundredth row applies.", {}, ["hundredth"]),
        ("Spend is doubling.", {}, ["doubling"]),
        ("Spend is tripling.", {}, ["tripling"]),
        ("Spend is halving.", {}, ["halving"]),
        ("Risk grew thousandfold.", {}, ["thousandfold"]),
        # Finding 2: a percent mark after ANY whitespace, and more percent marks.
        ("Coverage is 40\u00a0%.", {"pct": 40}, ["40\u00a0%"]),
        ("Coverage is 40\u202f%.", {"pct": 40}, ["40\u202f%"]),
        ("Coverage is 40  %.", {"pct": 40}, ["40  %"]),
        ("Coverage is 40\u00a0%.", {"pct": "40 %"}, []),
        ("Coverage is 40\u066a.", {"pct": 40}, ["40\u066a"]),
        ("Coverage is 40\u2030.", {"pct": 40}, ["40\u2030"]),
        ("Coverage is 40 per-cent.", {"pct": "40%"}, ["40 per-cent"]),
        ("It rose 5 percentage points.", {"n": 5}, ["5 percentage points"]),
        ("It rose 5 percentage points.", {"rise": "5 percentage points"}, []),
        # Finding 3: a separated scale or multiplier joins its numeral.
        ("Spend was $5 bn.", {"s": 5}, ["$5 bn"]),
        ("Spend was $5 bn.", {"s": "$5 bn"}, []),
        ("Spend was $5 MM.", {"s": 5}, ["$5 MM"]),
        ("Spend was $5 M.", {"s": 5}, ["$5 M"]),
        ("Spend was 5 K.", {"s": 5}, ["5 K"]),
        ("Spend was 5 trillion.", {"s": 5}, ["5 trillion"]),
        ("Spend was 5 lakh.", {"s": 5}, ["5 lakh"]),
        ("Spend was 5 crore.", {"s": 5}, ["5 crore"]),
        # "5 m" is refused on purpose: minutes, metres or millions, unknowable.
        ("It took 5 m.", {"s": 5}, ["5 m"]),
        ("Risk grew 5-fold.", {"s": 5}, ["5-fold"]),
        ("Risk grew \u00d73.", {"s": 3}, ["\u00d73"]),
        ("Risk grew 3\u00d7.", {"s": 3}, ["3\u00d7"]),
        ("Risk grew 3 x.", {"s": 3}, ["3 x"]),
        # A "×" before a numeral joins it across whitespace too.
        ("Risk grew \u00d7 3.", {"s": 3}, ["\u00d7 3"]),
        # Finding 4: a non-thousands comma or a colon makes one span.
        ("Values 1,20 apply.", {"a": 1, "b": 20}, ["1,20"]),
        ("Values 1,2005 apply.", {"a": 1, "b": 2005}, ["1,2005"]),
        ("A 3:1 ratio holds.", {"a": 3, "b": 1}, ["3:1"]),
        ("It starts at 10:30.", {"a": 10, "b": 30}, ["10:30"]),
        ("It starts at 10:30.", {"time": "10:30"}, []),
        # Advisory 6: "single" and "pair" are number words.
        ("A single tool covers it.", {}, ["single"]),
        ("A pair of tools overlap.", {}, ["pair"]),
    ],
)
def test_round_three_forms(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text",
    [
        # A magnitude letter with no numeral before it is prose.
        "Press x to exit and M to mute.",
        "A percentage of rows lack notes.",
        # Advisory 6, deliberate exclusions: "none", "nil", "couple", "several",
        # "score" and "gross" are prose far more often than counts.
        "None of the several tools; a couple of nil results; score and gross margin.",
    ],
)
def test_round_three_text_with_no_number(text: str) -> None:
    assert _refused(text, {}) == []


def test_an_all_numeric_protected_value_is_refused() -> None:
    # Finding 5: a numeral is not a code. Protecting "40" would mask it
    # everywhere and let "40%" and "$40" through.
    with pytest.raises(ValueError, match="code"):
        allowed_numbers({"code": "40"}, fact_fields=(), protected_fields=("code",))


# --- Review round 4 of #1088 (findings 1 to 4, and the advisory) ----------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 1: a short unit after a numeral joins it, any case, so the span
        # is not a plain numeral. Units outside any list are refused by shape.
        ("Spend was $5 Bn.", {"s": 5}, ["$5 Bn"]),
        ("Spend was $5 BN.", {"s": 5}, ["$5 BN"]),
        ("Spend was $5 mn.", {"s": 5}, ["$5 mn"]),
        ("Spend was $5 b.", {"s": 5}, ["$5 b"]),
        ("Spend was $5 bln.", {"s": 5}, ["$5 bln"]),
        ("Spend was $5 tn.", {"s": 5}, ["$5 tn"]),
        ("Spend was $5 grand.", {"s": 5}, ["$5 grand"]),
        ("It grew 3 X.", {"s": 3}, ["3 X"]),
        ("It rose 5 pp.", {"s": 5}, ["5 pp"]),
        ("It rose 50 bps.", {"s": 50}, ["50 bps"]),
        ("It rose 40 pc.", {"s": 40}, ["40 pc"]),
        ("It rose 5 percentage-point.", {"s": 5}, ["5 percentage-point"]),
        ("It took a 5-day window.", {"s": 5}, ["5-day"]),
        ("It moved 5 GBPS.", {"s": 5}, ["5 GBPS"]),
        ("It moved 5 Gbps.", {"s": 5}, ["5 Gbps"]),
        ("Spend was $5 Bn.", {"s": "$5 Bn"}, []),
        # ...but a short FUNCTION word after a numeral does not join.
        ("5 of 82 controls apply.", {"a": 5, "b": 82}, []),
        ("Rows 5 in all, 3 to go, 2 per user.", {"a": 5, "b": 3, "c": 2}, []),
        ("We added 3 new tools.", {"n": 3}, []),
        # A longer word after a numeral is prose, not a unit.
        ("12 rows were scored; 4 tools and 7 apps.", {"a": 12, "b": 4, "c": 7}, []),
        # Finding 2: the multiplier family, generated.
        ("Spend quadrupled.", {}, ["quadrupled"]),
        ("Spend is quadrupling.", {}, ["quadrupling"]),
        ("Spend trebled.", {}, ["trebled"]),
        ("Spend will halve.", {}, ["halve"]),
        ("Spend will quintuple.", {}, ["quintuple"]),
        # Finding 3: "first" and "second" inside a dash compound; "and" between
        # number words.
        ("The twenty-first control applies.", {}, ["twenty-first"]),
        ("The thirty-second control applies.", {}, ["thirty-second"]),
        ("Twenty controls apply.", {"c": "the twenty-first control"}, ["Twenty"]),
        ("The twenty-first control applies.", {"c": "the twenty-first control"}, []),
        ("One hundred and five rows.", {}, ["One hundred and five"]),
        ("One hundred and five rows.", {"n": "one hundred and five"}, []),
        ("Five rows.", {"n": "one hundred and five"}, ["Five"]),
        # Finding 4: a span with a digit or a unit is NOT case-folded.
        ("Spend was 45M.", {"s": "45m"}, ["45M"]),
        ("Spend was 45m.", {"s": "45m"}, []),
        ("Spend was €1.2M.", {"s": "€1.2m"}, ["€1.2M"]),
        # Spelled number words still fold case.
        ("Three tools overlap.", {"t": "three tools"}, []),
    ],
)
def test_round_four_forms(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text",
    [
        # Advisory: domain terms that are not counts.
        "Adopt Zero Trust across the estate.",
        "Enable single sign-on for every app.",
        "Rotate the key pair; store key pairs safely.",
        "Plan for double extortion.",
        "Send a one-time password; use one-time codes.",
        "Review third parties annually.",
        # A short unit with no numeral before it is prose.
        "The MM team and the b side.",
    ],
)
def test_round_four_text_with_no_number(text: str) -> None:
    assert _refused(text, {}) == []


# --- Review round 5 of #1088 ------------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 1: a number WORD joins a magnitude (only a unit is excluded).
        ("Spend was five bn.", {"c": "five controls"}, ["five bn"]),
        ("Risk grew five-fold.", {"c": "five controls"}, ["five-fold"]),
        ("Spend was ten M.", {"c": "ten controls"}, ["ten M"]),
        ("Risk grew three x.", {"c": "three controls"}, ["three x"]),
        # Finding 2: four-letter magnitude spellings, any case, and basis points.
        ("Spend was $5 mill.", {"s": 5}, ["$5 mill"]),
        ("Spend was $5 bill.", {"s": 5}, ["$5 bill"]),
        ("Spend was $5 trln.", {"s": 5}, ["$5 trln"]),
        ("Spend was 5 lacs.", {"s": 5}, ["5 lacs"]),
        ("Spend was 5 Lakhs.", {"s": 5}, ["5 Lakhs"]),
        ("Spend was 5 crores.", {"s": 5}, ["5 crores"]),
        ("It rose 5 basis points.", {"s": 5}, ["5 basis points"]),
        ("It rose 5 basis point.", {"s": 5}, ["5 basis point"]),
        ("It rose 5 basis points.", {"s": "5 basis points"}, []),
        ("Pay the bill.", {}, []),
        # Advisory 4: a spelled number word folds case even in a digit span; a
        # unit does not.
        ("Spend was 5 Million.", {"s": "5 million"}, []),
        ("Spend was 5 M.", {"s": "5 m"}, ["5 M"]),
        # Advisory 5: text next to an exempt phrase is still checked.
        ("Zero Trust 2.0 applies.", {}, ["2.0"]),
        ("Send a one-time code to 5 users.", {}, ["5"]),
    ],
)
def test_round_five_forms(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- Review round 6 of #1088 ------------------------------------------------------


def test_a_non_finite_decimal_outside_any_fact_still_raises() -> None:
    with pytest.raises(ValueError):
        allowed_numbers({"x": Decimal("NaN")}, fact_fields=(), protected_fields=())
    with pytest.raises(ValueError):
        allowed_numbers({"x": Decimal("Infinity")}, fact_fields=(), protected_fields=())


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Spend was $5 thou.", {"s": 5}, ["$5 thou"]),
        ("Spend was $5 Grand.", {"s": 5}, ["$5 Grand"]),
        ("Spend was $5 GRAND.", {"s": 5}, ["$5 GRAND"]),
        ("Spend was five mln.", {"c": "five controls"}, ["five mln"]),
    ],
)
def test_round_six_magnitudes(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text,payload,facts,refused",
    [
        # A top-level fact licenses its whole subtree.
        ("Values 5 and 7.", {"facts": {"value": 5, "meta": {"value": 7}}}, ("facts",), []),
        # A same-named key under a non-fact parent licenses nothing.
        ("Values 5 and 7.", {"value": 5, "meta": {"value": 7}}, ("value",), ["7"]),
        ("Id 9 applies.", {"value": 5, "meta": {"value": "9"}}, ("value",), ["9"]),
        # A dotted path names a nested fact, and only that subtree.
        (
            "5 rows; id 9.",
            {"service": {"summary": "5 rows", "id": 9}},
            ("service.summary",),
            ["9"],
        ),
        (
            "5 rows.",
            {"service": [{"summary": "5 rows"}, {"summary": "6 rows"}]},
            ("service.summary",),
            [],
        ),
    ],
)
def test_fact_names_match_top_level_keys_or_dotted_paths(
    text: str, payload: dict, facts: tuple[str, ...], refused: list[str]
) -> None:
    allowed = allowed_numbers(payload, fact_fields=facts, protected_fields=())
    assert [h.raw for h in unallowed_numbers(text, allowed)] == refused


@pytest.mark.parametrize(
    "payload,facts",
    [
        # A name present only below the top level does not match.
        ({"meta": {"value": 7}}, ("value",)),
        ({"service": {"summary": "5 rows"}}, ("service.nope",)),
        ({"service": {"summary": "5 rows"}}, ("summary",)),
    ],
)
def test_an_unmatched_fact_path_is_refused(payload: dict, facts: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        allowed_numbers(payload, fact_fields=facts, protected_fields=())


# --- Review round 7 of #1088 ------------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,protected,refused",
    [
        # A same-named key in a non-fact subtree is NOT protected: its numbers
        # are checked like any other text.
        (
            "40% of hosts unpatched in 2025.",
            {"name": "Acme Corp", "findings": [{"name": "40% of hosts unpatched in 2025"}]},
            ("name",),
            ["40%", "2025"],
        ),
        # A dotted path protects exactly that nested value (lists transparent).
        (
            "T1003 applies.",
            {"findings": [{"code": "T1003"}]},
            ("findings.code",),
            [],
        ),
    ],
)
def test_protected_names_match_top_level_keys_or_dotted_paths(
    text: str, payload: dict, protected: tuple[str, ...], refused: list[str]
) -> None:
    allowed = allowed_numbers(payload, fact_fields=(), protected_fields=protected)
    assert [h.raw for h in unallowed_numbers(text, allowed)] == refused


def test_a_protected_path_inside_a_fact_takes_precedence() -> None:
    # Precedence: the protected string is written as given and licenses no
    # number of its own; the rest of the fact still licenses.
    payload = {"facts": {"code": "PR.PS-01", "count": 5}}
    allowed = allowed_numbers(payload, fact_fields=("facts",), protected_fields=("facts.code",))
    assert unallowed_numbers("PR.PS-01 has 5 owners.", allowed) == ()
    assert [h.raw for h in unallowed_numbers("Owner 01 applies.", allowed)] == ["01"]


def test_a_protected_name_present_only_below_the_top_level_is_refused() -> None:
    with pytest.raises(ValueError):
        allowed_numbers({"findings": [{"name": "x"}]}, fact_fields=(), protected_fields=("name",))


def test_a_payload_key_containing_a_dot_is_refused() -> None:
    with pytest.raises(ValueError, match="service.id"):
        allowed_numbers({"service.id": 5}, fact_fields=(), protected_fields=())


@pytest.mark.parametrize(
    "facts,protected",
    [((1,), ()), ((), (None,)), (("ok", b"bytes"), ())],
)
def test_a_field_list_entry_that_is_not_a_str_is_refused(facts: tuple, protected: tuple) -> None:
    with pytest.raises(TypeError):
        allowed_numbers({"ok": 1}, fact_fields=facts, protected_fields=protected)
