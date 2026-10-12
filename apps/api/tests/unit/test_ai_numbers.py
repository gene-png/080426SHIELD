"""The shared literal-number validator (`app.ai.numbers`), for #1063 and #1071.

THE RULE UNDER TEST comes from the advisor's rulings, not from the module:

- #736 6115899208 (track D rev 3, P1 rule 1 as amended): "write a number only
  if that exact value appears in" the input; "Do not write numbers as words";
  catalog identifiers "may be written as they appear in the input"; "Numbers
  that are part of a name given in the input, such as a product name, may be
  written as given."
- #736 6115903398 (EV-2, G2): "Do not write any number, date, year, version or
  count except a fact value copied exactly from `facts`"; "Framework
  identifiers present in the payload allow-list are permitted".
- Track D's design note rev 4, section 15.1: commas and `$` are stripped,
  `40.0` equals `40`, a `%` form is distinct from the bare number, Unicode
  digits count as digits, and a spelled number needs its digit form.

Every expected value below is TYPED here from those rules. Nothing is read from
the module's own tables (CLAUDE.md, #72): no word list, pattern or constant is
imported. The corpus is one class per row group, each with an ALLOWED case and
a REFUSED case (CLAUDE.md, D-087: a corpus enumerates classes).
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
    """The raw spellings the validator refuses, in order.

    SETUP, not outcome: the corpus rows list a few protected names per group,
    so only the ones each row's payload carries are passed, and every string
    value a row gives is declared a fact unless `facts` says otherwise. The
    strict rule itself (an undeclared string licenses nothing; an unmatched
    name is refused) has its own tests below."""
    present = tuple(f for f in protected if f in payload)
    if facts is None:
        facts = tuple(k for k, v in payload.items() if isinstance(v, str) and k not in present)
    allowed = allowed_numbers(payload, fact_fields=facts, protected_fields=present)
    return [hit.raw for hit in unallowed_numbers(text, allowed)]


# --- 1. Plain digits, thousands separators, decimals ---------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Twelve rows: 12 in all.", {"n": 12}, []),
        ("Twelve rows were read.", {"n": 11}, ["Twelve"]),
        ("12 rows were scored.", {"n": 12}, []),
        ("13 rows were scored.", {"n": 12}, ["13"]),
        ("Spend was 1,200 this year.", {"spend": 1200}, []),
        ("Spend was 1200 this year.", {"spend": "1,200"}, []),
        ("Spend was 1,300 this year.", {"spend": 1200}, ["1,300"]),
        ("Coverage stands at 40.0 here.", {"pct": 40}, []),
        ("Coverage stands at 40 here.", {"pct": 40.0}, []),
        ("Coverage stands at 40.5 here.", {"pct": Decimal("40.50")}, []),
        ("Coverage stands at 40.6 here.", {"pct": 40.5}, ["40.6"]),
    ],
)
def test_plain_digits_separators_and_decimals(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 2. Percent, currency, negative numbers, ranges ----------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # A percent is a DISTINCT form (#736 6116092992, ruling 1): percent
        # facts are sent in their display form, so a bare 40 does not license
        # "40%".
        ("Detection covers 40% of techniques.", {"pct": 40}, ["40%"]),
        ("Detection covers 40% of techniques.", {"pct": "40%"}, []),
        ("Detection covers 40 percent of techniques.", {"pct": "40%"}, []),
        # Dropping the % changes the claim: "40%" given does not license "40".
        ("Detection covers 40 techniques.", {"pct": "40%"}, ["40"]),
        ("Detection covers 45% of techniques.", {"pct": "40%"}, ["45%"]),
        ("The total is $40,000,962.", {"total": 40000962}, []),
        ("The total is $40,000,963.", {"total": 40000962}, ["$40,000,963"]),
        ("The balance moved by -3 points.", {"delta": -3}, []),
        ("The balance moved by -3 points.", {"delta": 3}, ["-3"]),
        ("Levels run 3-5 here.", {"lo": 3, "hi": 5}, []),
        ("Levels run 3-5 here.", {"lo": 3}, ["5"]),
        ("Levels run 3 to 5 here.", {"lo": 3}, ["5"]),
    ],
)
def test_percent_currency_negative_and_ranges(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 3. Spelled cardinals, ordinals, multiplicatives, fractions ----------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Three tools overlap.", {"n": 3}, []),
        ("Three tools overlap.", {"n": 4}, ["Three"]),
        ("Twenty-one tools overlap.", {"n": 21}, []),
        ("Twenty-one tools overlap.", {"n": 20}, ["Twenty-one"]),
        ("One hundred tools overlap.", {"n": 100}, []),
        ("Two thousand rows were read.", {"n": 2000}, []),
        ("The third finding repeats.", {"n": 3}, []),
        ("The third finding repeats.", {"n": 2}, ["third"]),
        ("Spend doubled in a year.", {}, ["doubled"]),
        ("Spend rose twice as fast.", {}, ["twice"]),
        ("Spend was cut by half.", {}, ["half"]),
        ("Spend was cut by half.", {"share": 0.5}, []),
        # Fixed phrases that carry no count are not numbers.
        ("No one owns this; a third-party tool covers it.", {}, []),
        ("A third party hosts it.", {}, []),
    ],
)
def test_spelled_numbers(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 4. Unicode digits and superscripts ----------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Full-width １２ rows.", {"n": 12}, []),
        ("Full-width １３ rows.", {"n": 12}, ["１３"]),
        ("Arabic-Indic ٣ rows.", {"n": 3}, []),
        ("Arabic-Indic ٣ rows.", {"n": 4}, ["٣"]),
        ("Area of 10² units.", {"a": 10}, ["²"]),
    ],
)
def test_unicode_digits_and_superscripts(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 5. Dates, years, versions -------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Released on 2026-10-12.", {"date": "2026-10-12"}, []),
        ("Released on 2026-10-12.", {}, ["2026", "10", "12"]),
        ("Approved in March 2026.", {"year": 2026}, []),
        ("Approved in March 2026.", {}, ["2026"]),
        ("It follows NIST 800-53 rev 5.", {}, ["800", "53", "5"]),
        ("It runs v2.1 of the agent.", {}, ["2.1"]),
        ("It runs v2.1 of the agent.", {"version": "2.1"}, []),
    ],
)
def test_dates_years_and_versions(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


# --- 6. Catalog codes, in and out of the payload -------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("PR.PS-01 is weak.", {"code": "PR.PS-01"}, []),
        ("PR.PS-02 is weak.", {"code": "PR.PS-01"}, ["02"]),
        ("T1003.001 and TA0006 apply.", {"t": "T1003.001", "ta": "TA0006"}, []),
        ("T1003.002 applies.", {"t": "T1003.001"}, ["1003.002"]),
        # A protected code licenses itself, not the numbers inside it.
        ("PR.PS-01 has 01 owner.", {"code": "PR.PS-01"}, ["01"]),
    ],
)
def test_catalog_codes(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload, protected=("code", "t", "ta")) == refused


# --- 7. Names carrying digits --------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Microsoft 365 E5 covers it.", {"tool": "Microsoft 365 E5"}, []),
        ("Microsoft 365 E3 covers it.", {"tool": "Microsoft 365 E5"}, ["365", "3"]),
        ("Microsoft 365 E5 covers it.", {}, ["365", "5"]),
    ],
)
def test_names_with_digits(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload, protected=("tool",)) == refused


# --- 8. Digits inside words ----------------------------------------------------


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        ("Hashes use SHA256 on x86.", {}, ["256", "86"]),
        ("Hashes use SHA256 on x86.", {"algo": "SHA256", "arch": "x86"}, []),
        ("It speaks IPv6.", {}, ["6"]),
    ],
)
def test_digits_inside_words(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload, protected=("algo", "arch")) == refused


# --- 9. Idempotent: text that passed once passes again -------------------------


def test_text_that_passed_passes_again() -> None:
    payload = {"pct": "40%", "code": "PR.PS-01", "total": 1200}
    allowed = allowed_numbers(payload, fact_fields=("pct",), protected_fields=("code",))
    text = "PR.PS-01 sits at 40% with 1,200 in spend."
    assert unallowed_numbers(text, allowed) == ()
    assert unallowed_numbers(text, allowed) == ()


# --- 10. Empty and very long text ----------------------------------------------


def test_empty_text_has_no_hits() -> None:
    assert unallowed_numbers("", allowed_numbers({}, fact_fields=(), protected_fields=())) == ()


def test_very_long_text_reports_every_hit_with_its_offsets() -> None:
    text = "Only 7 here. " * 5000 + "And 8 at the end."
    hits = unallowed_numbers(text, allowed_numbers({"n": 7}, fact_fields=(), protected_fields=()))
    assert [h.raw for h in hits] == ["8"]
    assert text[hits[0].start : hits[0].end] == "8"


# --- The hit's shape, and fail-loudly inputs -----------------------------------


def test_a_hit_carries_raw_normalized_and_offsets() -> None:
    text = "Spend was $1,300."
    (hit,) = unallowed_numbers(
        text, allowed_numbers({"s": 1200}, fact_fields=(), protected_fields=())
    )
    assert hit == NumberHit(raw="$1,300", normalized="1300", start=10, end=16)


def test_payload_walk_reads_nested_values() -> None:
    payload = {"facts": [{"id": "f1", "value": 17}, {"id": "f2", "label": "Has 4 rows"}]}
    assert _refused("17 and 4 hold.", payload, facts=("label",)) == []


def test_a_boolean_is_not_a_number() -> None:
    # `int(True)` is 1 (CLAUDE.md): a flag must not license the number 1.
    assert _refused("1 tool remains.", {"flag": True}) == ["1"]


def test_unallowed_numbers_refuses_a_non_string() -> None:
    with pytest.raises(TypeError):
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


def test_the_allow_list_is_a_value_object() -> None:
    allowed = allowed_numbers(
        {"n": 3, "code": "PR.PS-01"}, fact_fields=(), protected_fields=("code",)
    )
    assert isinstance(allowed, NumberAllowList)
    assert "3" in allowed.values
    assert "PR.PS-01" in allowed.protected


# --- Review round 1 of #1088 (findings 2, 3, 4, 6, 7, 8, 9) ----------------------
# Each class gets an allowed row and a refused row, typed from the rule: a number
# the text states must be a value present in the input.


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 2: k / M / B suffixes are scales, not decoration.
        ("Spend was $240k.", {"spend": 240000}, []),
        ("Spend was $240k.", {"spend": 240}, ["$240k"]),
        ("Spend was €1.2M.", {"spend": 1200000}, []),
        ("Spend was €1.2M.", {"spend": 1.2}, ["€1.2M"]),
        ("Spend was $3B.", {"spend": 3000000000}, []),
        ("Spend was $3B.", {"spend": 3}, ["$3B"]),
        # Finding 8: the euro and pound marks are currency, as `$` is.
        ("Spend was €1,200.", {"spend": 1200}, []),
        ("Spend was £1,300.", {"spend": 1200}, ["£1,300"]),
        # Finding 8: "1,908" is one thousand nine hundred and eight; "1.908" is not.
        ("1,908 values applied.", {"n": 1908}, []),
        ("1.908 values applied.", {"n": 1908}, ["1.908"]),
        # Finding 9: U+2212 MINUS SIGN is a minus sign.
        ("The balance moved by −3 points.", {"delta": -3}, []),
        ("The balance moved by −3 points.", {"delta": 3}, ["−3"]),
    ],
)
def test_scales_currencies_separators_and_minus(
    text: str, payload: dict, refused: list[str]
) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 3: fraction words are fractions, never ordinals or sums.
        ("One third of rows lack evidence.", {"share": "1/3"}, []),
        ("One third of rows lack evidence.", {"n": 3}, ["One third"]),
        ("One third of rows lack evidence.", {"n": 4}, ["One third"]),
        ("Two-thirds of rows lack evidence.", {"share": "2/3"}, []),
        ("Two-thirds of rows lack evidence.", {"n": 2}, ["Two-thirds"]),
        ("A third of rows lack evidence.", {"share": "1/3"}, []),
        ("A third of rows lack evidence.", {"n": 3}, ["A third"]),
        ("A quarter of rows lack evidence.", {"share": 0.25}, []),
        ("A quarter of rows lack evidence.", {}, ["A quarter"]),
        ("Three quarters of rows lack evidence.", {"share": 0.75}, []),
        ("Three quarters of rows lack evidence.", {"n": 3}, ["Three quarters"]),
        # A quarter as a period is not a fraction; "Q3" and "FY25" are numbers.
        ("Spend fell this quarter.", {}, []),
        ("Spend fell in Q3 FY25.", {"period": "Q3 FY25"}, []),
        ("Spend fell in Q3 FY25.", {}, ["3", "25"]),
        # Finding 8: a digit ordinal is its number.
        ("The 3rd finding repeats.", {"n": 3}, []),
        ("The 3rd finding repeats.", {"n": 2}, ["3"]),
    ],
)
def test_fractions_periods_and_digit_ordinals(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 7: Roman numerals, uppercase. A pronoun "I" is not one.
        ("Tier III applies.", {"tier": 3}, []),
        ("Tier III applies.", {"tier": 2}, ["III"]),
        ("IV of them apply.", {"n": 4}, []),
        ("IV of them apply.", {}, ["IV"]),
        ("I think it applies.", {}, []),
        # After a context word, a single letter counts.
        ("Phase V applies.", {"phase": 5}, []),
        ("Phase V applies.", {}, ["V"]),
        # Finding 7: Unicode letter-numbers (category Nl).
        ("Volume Ⅻ applies.", {"v": 12}, []),
        ("Volume Ⅻ applies.", {}, ["Ⅻ"]),
        # Finding 7: dozen and -fold state a value; vague magnitudes never match one.
        ("A dozen tools overlap.", {"n": 12}, []),
        ("A dozen tools overlap.", {"n": 11}, ["dozen"]),
        ("Spend grew tenfold.", {"x": 10}, []),
        ("Spend grew tenfold.", {}, ["tenfold"]),
        ("Hundreds of rows lack notes.", {"n": 300}, ["Hundreds"]),
        ("Dozens of rows lack notes.", {"n": 24}, ["Dozens"]),
    ],
)
def test_roman_letter_numbers_and_magnitudes(text: str, payload: dict, refused: list[str]) -> None:
    assert _refused(text, payload) == refused


@pytest.mark.parametrize(
    "text,payload,refused",
    [
        # Finding 4: a protected parent code does not license an invented sub-code.
        ("T1003 applies.", {"code": "T1003"}, []),
        ("T1003.002 applies.", {"code": "T1003"}, ["1003.002"]),
        ("PR.PS-01 is weak.", {"code": "PR.PS-01"}, []),
        ("PR.PS-01.3 is weak.", {"code": "PR.PS-01"}, ["01.3"]),
        # The sentence's own full stop is not a continuation.
        ("It is T1003.", {"code": "T1003"}, []),
    ],
)
def test_protected_parent_code_does_not_mask_a_sub_code(
    text: str, payload: dict, refused: list[str]
) -> None:
    assert _refused(text, payload, protected=("code",)) == refused


def test_protected_fields_given_as_a_string_is_refused() -> None:
    # `frozenset("code")` is {"c", "o", "d", "e"}: it would protect nothing.
    with pytest.raises(TypeError):
        allowed_numbers(
            {"code": "PR.PS-01"}, fact_fields=(), protected_fields="code"  # type: ignore[arg-type]
        )


def test_fact_fields_given_as_a_string_is_refused() -> None:
    with pytest.raises(TypeError):
        allowed_numbers(
            {"pct": "40%"}, fact_fields="pct", protected_fields=()  # type: ignore[arg-type]
        )


def test_a_protected_field_matching_no_key_is_refused() -> None:
    with pytest.raises(ValueError, match="code"):
        allowed_numbers({"n": 1}, fact_fields=(), protected_fields=("code",))


def test_a_fact_field_matching_no_key_is_refused() -> None:
    with pytest.raises(ValueError, match="pct"):
        allowed_numbers({"n": 1}, fact_fields=("pct",), protected_fields=())


# --- Strict licensing (#736 6116092992, ruling 2, option (a)) -------------------
# Only numeric values, and the values of fields the caller lists as facts,
# license numbers. Every other string licenses nothing: the validator fails
# closed on ids, timestamps and identifiers.


@pytest.mark.parametrize(
    "text,payload,facts,refused",
    [
        ("Finding 1 repeats.", {"finding_id": "f1"}, (), ["1"]),
        ("Rows from 2026 apply.", {"created_at": "2026-10-12T09:00:00Z"}, (), ["2026"]),
        ("Rows from 2026 apply.", {"year": "2026"}, ("year",), []),
        ("Detection covers 40%.", {"pct": "40%", "id": "x40"}, ("pct",), []),
        ("Detection covers 40.", {"pct": "40%", "id": "x40"}, ("pct",), ["40"]),
    ],
)
def test_only_numbers_and_declared_fact_fields_license(
    text: str, payload: dict, facts: tuple[str, ...], refused: list[str]
) -> None:
    allowed = allowed_numbers(payload, fact_fields=facts, protected_fields=())
    assert [h.raw for h in unallowed_numbers(text, allowed)] == refused
