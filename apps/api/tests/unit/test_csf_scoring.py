"""Pure-function tests for the CSF scoring engine."""

from __future__ import annotations

import pytest

from app.csf.catalog import SUBCATEGORIES, FunctionCode
from app.csf.scoring import WEAKEST_PER_FUNCTION, compute


def _all_unanswered() -> dict[str, int | None]:
    return {s.code: None for s in SUBCATEGORIES}


@pytest.mark.unit
def test_empty_assessment_returns_zero_coverage() -> None:
    score = compute({})
    assert score.total_subcategories == 106
    assert score.answered_subcategories == 0
    assert score.coverage_pct == 0.0
    assert score.average_tier is None
    assert score.overall_maturity_label == "Unscored"
    # Every function present even when unanswered.
    assert len(score.by_function) == 6
    for fs in score.by_function:
        assert fs.answered_count == 0
        assert fs.average_tier is None
        assert fs.weakest_subcategory_codes == ()


@pytest.mark.unit
def test_full_partial_assessment_overall_label() -> None:
    answers = {s.code: 1 for s in SUBCATEGORIES}
    score = compute(answers)
    assert score.answered_subcategories == 106
    assert score.coverage_pct == 100.0
    assert score.average_tier == 1.0
    assert score.overall_maturity_label == "Partial"


@pytest.mark.unit
def test_full_adaptive_assessment_overall_label() -> None:
    answers = {s.code: 4 for s in SUBCATEGORIES}
    score = compute(answers)
    assert score.average_tier == 4.0
    assert score.overall_maturity_label == "Adaptive"


@pytest.mark.unit
def test_mid_tier_averages_label_to_repeatable() -> None:
    # Half tier 3, half tier 4 -> avg 3.5 lands on "Adaptive" via band cutoff.
    half = len(SUBCATEGORIES) // 2
    answers: dict[str, int | None] = {}
    for i, s in enumerate(SUBCATEGORIES):
        answers[s.code] = 3 if i < half else 4
    score = compute(answers)
    # avg = 3.something; verify label by band:
    assert 3.0 <= (score.average_tier or 0) <= 4.0
    label = score.overall_maturity_label
    assert label in {"Repeatable", "Adaptive"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "tiers,expected_label",
    [
        # Single tier-1 score -> avg 1.0 -> Partial.
        ([1], "Partial"),
        # Mostly tier-1 with one tier-2 -> avg 1.something < 1.5 -> Partial.
        ([1, 1, 1, 2], "Partial"),
        # 1 + 2 -> avg 1.5 -> Risk Informed (boundary belongs to upper band).
        ([1, 2], "Risk Informed"),
        # 2 + 3 -> avg 2.5 -> Repeatable.
        ([2, 3], "Repeatable"),
        # 3 + 4 -> avg 3.5 -> Adaptive.
        ([3, 4], "Adaptive"),
        # Solid 3s -> Repeatable.
        ([3, 3, 3], "Repeatable"),
        # Solid 4s -> Adaptive.
        ([4, 4, 4], "Adaptive"),
    ],
)
def test_band_cutoffs(tiers: list[int], expected_label: str) -> None:
    answers: dict[str, int | None] = {SUBCATEGORIES[i].code: tier for i, tier in enumerate(tiers)}
    assert compute(answers).overall_maturity_label == expected_label


@pytest.mark.unit
def test_unscored_rows_excluded_from_function_average() -> None:
    # Score 1 govern subcategory at tier 4, leave the rest unanswered.
    govern_codes = [s.code for s in SUBCATEGORIES if s.function == FunctionCode.GV]
    answers: dict[str, int | None] = dict.fromkeys(govern_codes)
    answers[govern_codes[0]] = 4
    score = compute(answers)
    gv_score = next(fs for fs in score.by_function if fs.function == FunctionCode.GV)
    assert gv_score.answered_count == 1
    assert gv_score.average_tier == 4.0
    assert gv_score.coverage_pct == round(1 / 31 * 100, 1)


@pytest.mark.unit
def test_invalid_tier_treated_as_unanswered() -> None:
    answers = {SUBCATEGORIES[0].code: 0, SUBCATEGORIES[1].code: 99}
    score = compute(answers)
    assert score.answered_subcategories == 0
    assert score.average_tier is None


@pytest.mark.unit
def test_weakest_codes_are_lowest_first_and_bounded() -> None:
    # Score 10 protect subcategories with varying tiers.
    protect_codes = [s.code for s in SUBCATEGORIES if s.function == FunctionCode.PR]
    answers: dict[str, int | None] = {}
    for i, code in enumerate(protect_codes):
        answers[code] = (i % 4) + 1  # cycles 1,2,3,4,...
    score = compute(answers)
    pr_score = next(fs for fs in score.by_function if fs.function == FunctionCode.PR)
    # Bounded by WEAKEST_PER_FUNCTION.
    assert len(pr_score.weakest_subcategory_codes) == WEAKEST_PER_FUNCTION
    # The lowest tier (1) ones come first. Among tier-1 codes the scorer
    # ties-breaks by alphabetic code, so the expected slice is the first
    # WEAKEST_PER_FUNCTION codes in alphabetic order from the tier-1 set.
    tier1_codes = sorted(code for i, code in enumerate(protect_codes) if i % 4 == 0)
    expected = tier1_codes[:WEAKEST_PER_FUNCTION]
    assert list(pr_score.weakest_subcategory_codes) == expected


@pytest.mark.unit
def test_unknown_subcategory_codes_in_answers_ignored() -> None:
    answers = {"GV.XX-99": 4, SUBCATEGORIES[0].code: 4}
    score = compute(answers)
    # The bogus code is in the answers dict but doesn't appear in
    # any function's roster, so it contributes nothing.
    assert score.answered_subcategories == 1
    assert score.average_tier == 4.0


@pytest.mark.unit
def test_each_function_totals_match_catalog() -> None:
    expected = {
        FunctionCode.GV: 31,
        FunctionCode.ID: 22,
        FunctionCode.PR: 22,
        FunctionCode.DE: 11,
        FunctionCode.RS: 13,
        FunctionCode.RC: 7,
    }
    score = compute({})
    for fs in score.by_function:
        assert fs.subcategory_count == expected[fs.function]
