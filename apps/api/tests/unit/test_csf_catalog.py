"""Phase 4 stage 1: CSF 2.0 catalog integrity.

Locks down counts + structural invariants so a regression that drops
a subcategory or renames a function trips the test rather than
silently shipping a broken assessment.
"""

from __future__ import annotations

import re

import pytest

from app.csf.catalog import (
    CATEGORIES,
    FUNCTIONS,
    SUBCATEGORIES,
    FunctionCode,
    all_codes,
    category_by_code,
    function_by_code,
    subcategories_for_function,
    subcategory_by_code,
)
from app.csf.maturity import (
    TIER_DEFINITIONS,
    MaturityTier,
    tier_label,
)

CODE_PATTERN = re.compile(r"^(GV|ID|PR|DE|RS|RC)\.[A-Z]{2}-\d{2}$")
CATEGORY_PATTERN = re.compile(r"^(GV|ID|PR|DE|RS|RC)\.[A-Z]{2}$")


@pytest.mark.unit
def test_function_count_is_six() -> None:
    assert len(FUNCTIONS) == 6
    codes = {f.code for f in FUNCTIONS}
    assert codes == set(FunctionCode)


@pytest.mark.unit
def test_category_count_is_22() -> None:
    # CSF 2.0 Core: 6 functions / 22 categories / 106 subcategories.
    assert len(CATEGORIES) == 22
    # And each category is well-formed.
    for cat in CATEGORIES:
        assert CATEGORY_PATTERN.fullmatch(cat.code), cat.code
        # The 2-char prefix of the category code matches its function.
        assert cat.code.split(".", 1)[0] == cat.function.value


@pytest.mark.unit
def test_subcategory_count_is_106() -> None:
    assert len(SUBCATEGORIES) == 106


@pytest.mark.unit
def test_subcategory_codes_are_unique() -> None:
    codes = [s.code for s in SUBCATEGORIES]
    assert len(codes) == len(set(codes)), "duplicate subcategory codes"


@pytest.mark.unit
def test_subcategory_codes_match_pattern() -> None:
    for sc in SUBCATEGORIES:
        assert CODE_PATTERN.fullmatch(sc.code), sc.code


@pytest.mark.unit
def test_subcategory_function_matches_code_prefix() -> None:
    for sc in SUBCATEGORIES:
        prefix = sc.code.split(".", 1)[0]
        assert sc.function.value == prefix
        assert sc.code.startswith(sc.category + "-")


@pytest.mark.unit
@pytest.mark.parametrize(
    "function_code,expected",
    [
        (FunctionCode.GV, 31),
        (FunctionCode.ID, 22),
        (FunctionCode.PR, 22),
        (FunctionCode.DE, 11),
        (FunctionCode.RS, 13),
        (FunctionCode.RC, 7),
    ],
)
def test_subcategory_counts_per_function(function_code: FunctionCode, expected: int) -> None:
    assert len(subcategories_for_function(function_code)) == expected


@pytest.mark.unit
def test_every_subcategory_has_a_real_category() -> None:
    category_codes = {c.code for c in CATEGORIES}
    for sc in SUBCATEGORIES:
        assert sc.category in category_codes


@pytest.mark.unit
def test_all_codes_helper_matches_full_set() -> None:
    assert all_codes() == frozenset(s.code for s in SUBCATEGORIES)


@pytest.mark.unit
def test_function_lookup_round_trip() -> None:
    for fn in FUNCTIONS:
        assert function_by_code(fn.code) is fn
        assert function_by_code(fn.code.value) is fn
    with pytest.raises((KeyError, ValueError)):
        function_by_code("XX")


@pytest.mark.unit
def test_category_lookup_round_trip() -> None:
    for cat in CATEGORIES:
        assert category_by_code(cat.code) is cat
    with pytest.raises(KeyError):
        category_by_code("GV.XX")


@pytest.mark.unit
def test_subcategory_lookup_round_trip() -> None:
    sample = SUBCATEGORIES[0]
    assert subcategory_by_code(sample.code) is sample
    with pytest.raises(KeyError):
        subcategory_by_code("GV.XX-99")


# ---------------------------------------------------------------------------
# Maturity tiers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_four_tier_definitions() -> None:
    assert len(TIER_DEFINITIONS) == 4
    assert [t.tier for t in TIER_DEFINITIONS] == [
        MaturityTier.PARTIAL,
        MaturityTier.RISK_INFORMED,
        MaturityTier.REPEATABLE,
        MaturityTier.ADAPTIVE,
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,expected",
    [
        (1, "Partial"),
        (2, "Risk Informed"),
        (3, "Repeatable"),
        (4, "Adaptive"),
        (MaturityTier.PARTIAL, "Partial"),
        (MaturityTier.ADAPTIVE, "Adaptive"),
        (None, "Unscored"),
        (99, "Unknown"),
    ],
)
def test_tier_label(value, expected: str) -> None:
    assert tier_label(value) == expected
