"""#125 - a ZT target the framework does not have must never be labelled "client".

`analyze_gaps` clamped an out-of-range engagement target to the engine default
and returned the CLAMPED value, while `routes/zt.py` labelled the audit row's
`target_stage_source` from whether the client had supplied a value at all. A DoD
engagement whose client chose Stage 4 - a stage the product offered them and DoD
ZTRA does not have - finalized an audit row reading `target_stage: 3,
target_stage_source: "client"`: the false value and the false attribution of it,
side by side, in the record that exists to establish provenance.

The guard keyed on whether a value was OFFERED, never on whether it SURVIVED.

These tests pin the engine half. The route half lives in `test_zt_routes.py`
(finalize + gap-analysis) and `test_intake_routes.py` (the write path).
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from app.zt.maturity import ZtFrameworkCode, level_count
from app.zt.scoring import (
    DEFAULT_TARGET_STAGE,
    Gap,
    GapAnalysis,
    PillarScoreResult,
    ScoreResult,
    analyze_gaps,
    resolve_target_stage,
)

CISA = ZtFrameworkCode.CISA_ZTMM_2_0
DOD = ZtFrameworkCode.DOD_ZTRA
ALL_FRAMEWORKS = [CISA, DOD]


# ---------------------------------------------------------------------------
# resolve_target_stage - the honest replacement for the silent clamp
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_resolve_reports_client_when_the_choice_is_valid_for_the_framework() -> None:
    assert resolve_target_stage(CISA, 4) == (4, "client")
    assert resolve_target_stage(DOD, 3) == (3, "client")


@pytest.mark.unit
def test_resolve_reports_default_when_the_client_chose_nothing() -> None:
    assert resolve_target_stage(CISA, None) == (DEFAULT_TARGET_STAGE, "default")
    assert resolve_target_stage(DOD, None) == (DEFAULT_TARGET_STAGE, "default")


@pytest.mark.unit
def test_resolve_never_attributes_an_out_of_range_choice_to_the_client() -> None:
    """The #125 defect, stated as the assertion that would have caught it.

    DoD ZTRA has three stages. A stored 4 is not the client's target because it
    is not a target at all - and the one thing the record must never say is that
    the client chose the value that came out the other side.
    """
    stage, source = resolve_target_stage(DOD, 4)
    assert source != "client", (
        "a stage the framework does not have was attributed to the client - "
        "this is #125, the false value and the false attribution side by side"
    )
    assert source == "client_out_of_range"
    # Literal 3, not DEFAULT_TARGET_STAGE. Writing the constant here would let
    # the test import its expected value from the module under test (#72), and
    # 3 is also DoD's ceiling, so the literal pins BOTH that the fallback is the
    # engine default and that it is inside this framework's ladder.
    assert stage == 3


@pytest.mark.unit
@pytest.mark.parametrize("bad", [0, -1, 5, 99])
def test_resolve_names_the_fault_for_every_out_of_range_choice(bad: int) -> None:
    _, source = resolve_target_stage(CISA, bad)
    assert source == "client_out_of_range"


# ---------------------------------------------------------------------------
# int() is not a validator - the second #125, found inside the first fix
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("truthy", [True, False])
def test_resolve_rejects_bools_rather_than_reading_them_as_stages(truthy: bool) -> None:
    """`int(True) is 1`, so an unguarded parse turns a stored bool into Stage 1.

    The failure that matters is not the number, it is the label: before this,
    `resolve_target_stage(CISA, True)` returned `(1, "client")` - a stage the
    client never chose, attributed to them.
    """
    stage, source = resolve_target_stage(CISA, truthy)
    assert source == "client_unparseable"
    assert stage == 3


@pytest.mark.unit
def test_resolve_rejects_a_fraction_instead_of_calling_it_a_client_choice() -> None:
    """The defect this function was written to end, reproduced in its own body.

    The first implementation tested `1 <= int(chosen) <= max_stage`, so 3.9
    passed the range check and was returned as `(3, "client")`: a silent clamp
    labelled as the client's decision - #125 exactly, one layer down.
    """
    stage, source = resolve_target_stage(CISA, 3.9)
    assert source != "client"
    assert source == "client_unparseable"
    assert stage == 3


@pytest.mark.unit
def test_resolve_judges_range_before_wholeness() -> None:
    """Order matters, and the repo already settled it in `routes/zt.py`, in
    the AI-apply comment reading "RANGE before wholeness".

    4.9 on DoD's 1-3 ladder is both out of range and not whole. Out-of-range is
    the more useful thing to report, and testing it in the other order would let
    a fraction mask a target the framework does not have.
    """
    assert resolve_target_stage(DOD, 4.9)[1] == "client_out_of_range"
    assert resolve_target_stage(CISA, 4.9)[1] == "client_out_of_range"
    # In range but not whole -> the wholeness verdict, not the range one.
    assert resolve_target_stage(CISA, 2.5)[1] == "client_unparseable"


@pytest.mark.unit
@pytest.mark.parametrize("value,expected", [("2", 2), ("4", 4), (2.0, 2), (4.0, 4)])
def test_resolve_accepts_a_value_the_client_plainly_meant(value: object, expected: int) -> None:
    """Refusing `"2"` or `2.0` is the same defect facing the other way."""
    assert resolve_target_stage(CISA, value) == (expected, "client")


@pytest.mark.unit
@pytest.mark.parametrize(
    "junk",
    [
        # Derived from the arms of `resolve_target_stage`'s own `except`, not
        # from values anyone thought of -- an enumeration cannot falsify an
        # ABSOLUTE claim, and the first draft of this list proved it: seven
        # hand-picked values, all green, over a live `OverflowError`.
        pytest.param([], id="TypeError-list"),
        pytest.param({}, id="TypeError-dict"),
        pytest.param(object(), id="TypeError-object"),
        pytest.param("abc", id="ValueError-nonnumeric"),
        pytest.param("", id="ValueError-empty"),
        # OverflowError. `float(10**400)` raises it, and an int wider than a
        # double is ordinary JSON. This arm was MISSING and the function raised.
        pytest.param(10**400, id="OverflowError-int-wider-than-double"),
        pytest.param(-(10**400), id="OverflowError-negative"),
        # Parse fine; rejected later by the finiteness guard.
        pytest.param(float("nan"), id="finite-guard-nan"),
        pytest.param(float("inf"), id="finite-guard-inf"),
        pytest.param(float("-inf"), id="finite-guard-neg-inf"),
    ],
)
def test_resolve_never_raises_on_any_stored_value(junk: object) -> None:
    """The docstring's claim, made checkable.

    An earlier draft asserted "never raises" while raising TypeError on a list
    and ValueError on a non-numeric string. A stored value is data, not a
    programming error: refusing to render an engagement that already exists is
    not an available response to it.

    A LATER draft still raised `OverflowError`, because this list was written by
    enumerating inputs rather than by reading the `except` it exists to pin --
    and the function's docstring claimed parity with `_as_number` in
    `routes/zt.py`, which carries exactly that catch. The cases below are keyed
    to the arms instead, so adding an arm without a case is visible.
    """
    stage, source = resolve_target_stage(CISA, junk)
    assert source == "client_unparseable"
    assert isinstance(stage, int)
    assert not isinstance(stage, bool)


# ---------------------------------------------------------------------------
# The fallback must be feedable straight back into the engine
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("framework", ALL_FRAMEWORKS)
@pytest.mark.parametrize("stored", [None, 0, 1, 4, 99, -3, 3.9, True, "abc", "3"])
def test_whatever_resolve_returns_is_a_target_analyze_gaps_accepts(
    framework: ZtFrameworkCode, stored: object
) -> None:
    """The invariant `min(DEFAULT_TARGET_STAGE, max_stage)` exists to guarantee.

    `analyze_gaps` REFUSES an out-of-range target now, so a fallback that
    escaped the framework's ladder would turn every out-of-range stored value
    into a 500 rather than a named fault - reinstating #125's blast radius by
    the back door. Asserting the literal fallback would not catch it: today
    DEFAULT_TARGET_STAGE is 3 and DoD's ceiling is 3, so dropping the `min()`
    changes nothing observable. Feeding the result back into the engine does
    catch it, for any framework whose ceiling ever falls below the default.
    """
    stage, _source = resolve_target_stage(framework, stored)
    assert 1 <= stage <= level_count(framework)
    analyze_gaps(framework, {}, target_stage=stage)  # must not raise


# ---------------------------------------------------------------------------
# analyze_gaps - refuses rather than clamps
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_analyze_gaps_refuses_an_out_of_range_target_instead_of_clamping() -> None:
    """Core principle 2. A silent clamp is a default-value fallback on error.

    Before this, `analyze_gaps(DOD, {}, target_stage=4)` returned a GapAnalysis
    carrying `target_stage=3` with nothing anywhere recording that 4 was asked
    for. Callers resolve first, via `resolve_target_stage`.
    """
    with pytest.raises(ValueError, match="target_stage"):
        analyze_gaps(DOD, {}, target_stage=4)
    with pytest.raises(ValueError, match="target_stage"):
        analyze_gaps(CISA, {}, target_stage=5)


@pytest.mark.unit
def test_analyze_gaps_still_accepts_every_in_range_target() -> None:
    for stage in (1, 2, 3, 4):
        assert analyze_gaps(CISA, {}, target_stage=stage).target_stage == stage
    for stage in (1, 2, 3):
        assert analyze_gaps(DOD, {}, target_stage=stage).target_stage == stage


# ---------------------------------------------------------------------------
# The constraint, pinned rather than asserted
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_dataclass_the_zt_exporter_reads_is_shape_pinned() -> None:
    """The #125 fix must not alter what reaches `app/zt/exporters.py`.

    `zt/exporters.py` renders the ZT client deliverable and is outside this
    change's scope, so the dataclasses it reads are pinned here by LITERAL field
    name. Written out rather than derived from the dataclasses themselves: a
    test that reads its expectation from the thing under test agrees with it by
    construction and cannot fail (#72, D-051).

    ALL FOUR are pinned. An earlier draft pinned `GapAnalysis` and `ScoreResult`
    and said in this docstring that it covered "the two dataclasses it reads" -
    a claim narrower than the reader would assume, sitting exactly where they
    would go to check it. `exporters.py` also reads eight fields off `Gap` rows
    and six off `PillarScoreResult`, at each of the three
    renderers in `zt/exporters.py`, so renaming `Gap.gap_size` or
    `PillarScoreResult.coverage_pct` broke every ZT deliverable while this test
    stayed green.
    """
    assert {f.name for f in fields(GapAnalysis)} == {
        "framework",
        "target_stage",
        "target_label",
        "gaps",
        "unscored_codes",
        "total_gap_count",
        "gap_count_by_pillar",
    }
    assert {f.name for f in fields(ScoreResult)} == {
        "framework",
        "total_capabilities",
        "answered_capabilities",
        "coverage_pct",
        "average_stage",
        "maturity_pct",
        "overall_stage_label",
        "by_pillar",
    }
    assert {f.name for f in fields(Gap)} == {
        "code",
        "name",
        "pillar_code",
        "pillar_name",
        "current_stage",
        "target_stage",
        "gap_size",
        "priority_score",
        "notes",
        "outcome",
    }
    assert {f.name for f in fields(PillarScoreResult)} == {
        "pillar_code",
        "pillar_name",
        "capability_count",
        "answered_count",
        "coverage_pct",
        "average_stage",
        "maturity_pct",
        "weakest_capability_codes",
    }
