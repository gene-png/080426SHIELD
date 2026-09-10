"""The per-capability target rule, tested as a unit rather than through a route.

`analyze_gaps` used to carry this as an inner closure, so it could only be
exercised through a gap count -- which is how a change to the predicate could
move a client-facing number with nothing naming the predicate as the cause.
#124 extracted it (`effective_target_stages`, `capability_target_override`,
`engagement_target_capability_count`) so the client dashboard and the gap engine
apply ONE rule instead of two copies; these pin the rule itself.

The expected values come from the framework definitions and from the documented
exemptions, never from calling the function under test.
"""

from __future__ import annotations

import pytest

from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import (
    analyze_gaps,
    capability_target_override,
    effective_target_stages,
    engagement_target_capability_count,
)

CISA = ZtFrameworkCode.CISA_ZTMM_2_0
DOD = ZtFrameworkCode.DOD_ZTRA


def _first_code(framework: ZtFrameworkCode) -> str:
    return next(iter(capabilities(framework))).code


# --- the predicate ---------------------------------------------------------
#
# CISA runs 1-4, DoD 1-3. Cases are enumerated per FRAMEWORK because the whole
# reason ZT needs a resolver is that the two ladders differ in length: a stored
# 4 is an ordinary target on CISA and out of range on DoD, and #125 exists
# because one code path treated them identically.


@pytest.mark.unit
@pytest.mark.parametrize(
    ("framework", "stored", "expected"),
    [
        (CISA, 1, 1),
        (CISA, 4, 4),
        (CISA, 5, None),  # above CISA's ladder
        (CISA, 0, None),
        (CISA, -1, None),
        (CISA, None, None),
        (DOD, 3, 3),
        (DOD, 4, None),  # a real stored value: the intake UI offered it (#125)
        (DOD, 1, 1),
    ],
)
def test_capability_target_override_bounds_by_framework(framework, stored, expected) -> None:
    assert capability_target_override(framework, stored) == expected


@pytest.mark.unit
def test_capability_target_override_refuses_a_bool() -> None:
    """THE PINNED EXEMPTION WAS DELIBERATELY REMOVED. This is its inverse.

    This test previously asserted `capability_target_override(CISA, True) == 1`
    and existed as a tripwire so the predicate could not change silently. It
    fired, exactly as designed, on the branch that closed #188 -- and it is
    being inverted rather than deleted, because the tripwire worked and the
    record of what it was guarding is worth keeping.

    `CLAUDE.md` core principle 3 requires saying so explicitly rather than
    quietly editing a test to green, so: **the old assertion pinned real
    behaviour and that behaviour is now considered wrong.** The reason it was
    left alone -- "#124 was constrained to move no gap count" -- expired with
    that constraint, and #189 settled the general question that a bool is not
    a number.

    **It does move a gap count, in the case it applies to.** A capability at
    current stage 2 with a stored `True` previously got target `True` (== 1),
    2 >= 1, and produced NO gap row. It now falls back to the engagement stage
    and produces one. That is the intended correction -- a capability the
    client set something on was silently absent from their remediation plan --
    and it is stated here because the old docstring's "must not move a single
    gap count" is the sentence this change invalidates.

    Still not reachable in production: `ZtAnswer.target_stage` is a
    `SmallInteger`, so a Python bool never comes back from the database, and
    both writers call `int()` before assignment. This pins the predicate's
    contract, not a live path.
    """
    assert capability_target_override(CISA, True) is None
    assert capability_target_override(CISA, False) is None


# --- the map ---------------------------------------------------------------


@pytest.mark.unit
def test_effective_target_stages_covers_every_capability() -> None:
    """Completeness is the property #124 needed and the sparse map lacked.

    `compute` reports a pillar as Unscored when nothing in it has a value, so a
    map missing the capabilities nobody set a per-row target on is what made
    the client read "Target maturity: Unscored".
    """
    codes = {cap.code for cap in capabilities(CISA)}
    resolved = effective_target_stages(CISA, {}, 3)
    assert set(resolved) == codes
    assert set(resolved.values()) == {3}


@pytest.mark.unit
def test_effective_target_stages_prefers_a_usable_override() -> None:
    code = _first_code(CISA)
    resolved = effective_target_stages(CISA, {code: 2}, 4)
    assert resolved[code] == 2, "a usable per-row target wins"
    others = {v for k, v in resolved.items() if k != code}
    assert others == {4}, "everything else takes the engagement stage"


@pytest.mark.unit
def test_effective_target_stages_falls_back_when_the_override_is_unusable() -> None:
    """The documented silent fallback (#188), pinned so the VALUE cannot drift.

    Not a notification for #188, and an earlier draft implied it was. #188's
    documented fix is a COUNTER on `GapAnalysis` naming the dropped override --
    which leaves this map value at 2 and this assertion green. Whoever adds
    that counter needs a companion test asserting it; this one only guarantees
    that an unusable override falls back to the engagement stage rather than
    to `DEFAULT_TARGET_STAGE` or to a clamp.
    """
    code = _first_code(DOD)
    resolved = effective_target_stages(DOD, {code: 4}, 2)
    assert resolved[code] == 2, "an out-of-range override falls back, not clamps to 3"


@pytest.mark.unit
def test_effective_target_stages_ignores_codes_outside_the_framework() -> None:
    """The dashboard passes unfiltered rows; finalize filters them. Both must
    agree, so a stray code must not reach the result."""
    resolved = effective_target_stages(CISA, {"NOT_A_CODE": 2}, 3)
    assert "NOT_A_CODE" not in resolved


@pytest.mark.unit
def test_effective_target_stages_refuses_an_unresolved_engagement_target() -> None:
    """Fail loudly rather than leaning on the caller's next line.

    An out-of-range stage would otherwise produce a map of out-of-range values
    that `compute` discards as unscored -- #124 exactly, reintroduced by the
    helper written to fix it. `zt_dashboard` calls this BEFORE `analyze_gaps`,
    so `analyze_gaps` raising is not protection here.
    """
    with pytest.raises(ValueError, match="out of range"):
        effective_target_stages(DOD, {}, 4)


# --- the count -------------------------------------------------------------


@pytest.mark.unit
def test_engagement_target_capability_count_spans_both_ends() -> None:
    total = len(list(capabilities(CISA)))

    # Nothing overridden: the consultant-scored engagement, and #124's case.
    assert engagement_target_capability_count(CISA, {}) == total
    assert engagement_target_capability_count(CISA, None) == total

    # Everything overridden: a fully AI-scored or self-assessed engagement, in
    # which the intake choice decides nothing and must not be credited.
    everything = {cap.code: 3 for cap in capabilities(CISA)}
    assert engagement_target_capability_count(CISA, everything) == 0

    # One override.
    one = {_first_code(CISA): 3}
    assert engagement_target_capability_count(CISA, one) == total - 1


@pytest.mark.unit
def test_engagement_target_count_does_not_credit_an_unusable_override() -> None:
    """An override that cannot be used means the engagement stage decided that
    capability, so it must be COUNTED -- the count and the map have to agree
    about every capability or the dashboard's caption stops describing its
    own number."""
    code = _first_code(DOD)
    total = len(list(capabilities(DOD)))
    assert engagement_target_capability_count(DOD, {code: 4}) == total


@pytest.mark.unit
def test_the_count_and_the_map_agree_capability_by_capability() -> None:
    """The invariant the extraction exists to guarantee, stated directly.

    Two copies of one three-line predicate is #84's shape; this asserts the two
    consumers cannot disagree rather than trusting that they were written the
    same way.
    """
    targets: dict[str, int | None] = {}
    for i, cap in enumerate(capabilities(CISA)):
        targets[cap.code] = [None, 2, 9, 4][i % 4]

    # STATED PRECONDITION, not decoration. `fell_back` below infers "this
    # capability took the engagement stage" from `stage == 3`, which cannot
    # distinguish a fallback from an override that happens to EQUAL 3. The
    # fixture avoids 3 -- and without this line it would do so by luck, so the
    # day someone edits that list the test goes quietly weaker instead of red.
    assert 3 not in targets.values(), "the proxy below is blind to an override of 3"

    resolved = effective_target_stages(CISA, targets, 3)
    fell_back = sum(1 for code, stage in resolved.items() if stage == 3 and targets[code] != 3)
    assert engagement_target_capability_count(CISA, targets) == fell_back


@pytest.mark.unit
def test_analyze_gaps_uses_the_same_map_it_shares_with_the_dashboard() -> None:
    """The end the extraction was for: the deliverable's gap set and the
    dashboard's target map are derived from one rule.

    Every capability is scored one stage below whatever the shared map says its
    target is, so the gap count must be the full capability count -- computed
    from the map, not from `analyze_gaps`' own answer.
    """
    targets: dict[str, int | None] = {}
    for i, cap in enumerate(capabilities(CISA)):
        targets[cap.code] = [None, 4, 7][i % 3]

    resolved = effective_target_stages(CISA, targets, 3)
    answers = {code: max(1, stage - 1) for code, stage in resolved.items()}
    gap = analyze_gaps(CISA, answers, targets=targets, target_stage=3)

    expected = sum(1 for code, stage in resolved.items() if answers[code] < stage)
    assert gap.total_gap_count == expected
    assert gap.total_gap_count > 0, "precondition: the fixture must produce gaps"
