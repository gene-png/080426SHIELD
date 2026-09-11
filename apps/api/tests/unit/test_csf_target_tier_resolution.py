"""CSF must refuse an out-of-range target tier, not clamp it and report the clamp (#184).

`csf/gap.py::analyze` did this:

    if not (1 <= target_tier <= 4):
        target_tier = DEFAULT_TARGET_TIER

so `GET /csf/services/{id}/gap-analysis?target_tier=99` returned **200** with
`target_tier: 3` in the body and the gap set computed against 3. The caller
asked one question and was answered a different one, in the same units — the
hardest kind to notice.

That is the defect #125 fixed in ZT, still live in CSF. `zt/scoring.py`'s
comment says why it is wrong, and every word applies one service over:

    REFUSE, do not clamp. ... A silent clamp is a default-value fallback on
    error, which core principle 2 forbids.

## Reachable from a query string, which the ZT original was not

ZT's version needed a stored value out of range. CSF declares the target as a
bare unbounded query parameter (`target_tier: int = 3`, no `Query(ge=, le=)`),
so a URL is enough. No legacy data required.

## The source label is the other half, and it has the #125 shape exactly

Both `routes/clients.py` and `routes/csf.py` compute:

    "client" if <the stored value> is not None else "default"

keyed on whether a value was OFFERED, never on whether it SURVIVED. So a
stored tier the engine then discarded is reported to the client as their own
choice. #125 is filed against that line's ZT twin.

## Mirrored from ZT rather than designed again

`resolve_target_tier` returns `(tier, source)` with the same four source values
`resolve_target_stage` uses, and for the same reason: "the client chose
nothing" and "the client's choice could not be used" are different facts, and
the second is answerable by re-asking them. Flattening them throws away the
more actionable one.

CSF needs no framework argument — its ceiling is a constant 4, where ZT's
depends on CISA (4) vs DoD (3).

## What this file does NOT assert

That any stored CSF tier is currently out of range. `schemas/intake.py` bounds
`csf_target_tier` at `ge=2, le=4` and CSF's ceiling is 4, so a stored intake
tier is always valid — #184 says so explicitly. The live half is the query
parameter; the resolver is the latent half, fixed here because a guard that
exists only on one of two paths is the half-fix this repo keeps recording.
"""

from __future__ import annotations

import pytest

from app.csf.gap import DEFAULT_TARGET_TIER, analyze, resolve_target_tier

# The tier a refused or absent choice falls back to.
FALLBACK = DEFAULT_TARGET_TIER


@pytest.mark.unit
@pytest.mark.parametrize("chosen, expected", [(1, 1), (2, 2), (3, 3), (4, 4)])
def test_a_valid_tier_is_the_clients_own_choice(chosen, expected) -> None:
    assert resolve_target_tier(chosen) == (expected, "client")


@pytest.mark.unit
def test_no_choice_is_the_default_and_says_so() -> None:
    """Absent is not a fault. It must not be reported as one."""
    assert resolve_target_tier(None) == (FALLBACK, "default")


@pytest.mark.unit
@pytest.mark.parametrize("chosen", [0, 5, 99, -5])
def test_a_tier_outside_the_ladder_is_named_out_of_range(chosen) -> None:
    """The fact that makes it actionable: they chose, and it could not be used.

    Reported rather than raised, because a STORED value is data, not a
    programming error — refusing to render an existing engagement is not an
    available response to it. `analyze` raises; this reports.
    """
    assert resolve_target_tier(chosen) == (FALLBACK, "client_out_of_range")


@pytest.mark.unit
@pytest.mark.parametrize(
    "chosen",
    [
        pytest.param(True, id="bool-true"),
        pytest.param(False, id="bool-false"),
        pytest.param("three", id="a-word"),
        pytest.param(2.5, id="a-fraction"),
        pytest.param([3], id="a-list"),
        pytest.param(float("nan"), id="nan"),
        pytest.param(float("inf"), id="inf"),
        pytest.param(10**400, id="wider-than-a-double"),
    ],
)
def test_a_value_that_is_not_a_whole_number_is_named_unparseable(chosen) -> None:
    """Every arm of the parse, derived from ZT's rather than guessed.

    `10**400` is here because `float()` raises `OverflowError` on it and an int
    wider than a double is ordinary JSON — ZT's resolver records that omitting
    it is "what an absolute claim costs when the test behind it enumerates
    values someone thought of rather than deriving them". Inherited on purpose.

    `True` is first because `bool` subclasses `int`: without an explicit guard
    ahead of the numeric parse, a stored `True` resolves to Tier 1 and is
    attributed to the client.
    """
    assert resolve_target_tier(chosen) == (FALLBACK, "client_unparseable")


@pytest.mark.unit
@pytest.mark.parametrize("chosen, expected", [("3", 3), (3.0, 3)])
def test_a_tier_the_caller_plainly_meant_is_accepted(chosen, expected) -> None:
    """The positive control against a guard that refuses everything.

    `CLAUDE.md`: "Accept `2` and `2.0`: refusing a value the model plainly
    meant is the same defect facing the other way." A browser posting a
    `<select>` sends the string.
    """
    assert resolve_target_tier(chosen) == (expected, "client")


@pytest.mark.unit
@pytest.mark.parametrize("target_tier", [0, 5, 99, -5])
def test_the_engine_refuses_an_unresolved_tier_instead_of_clamping(target_tier) -> None:
    """**The #184 assertion.** Measured before the fix, all of these returned 3.

    By the time a value reaches `analyze` it has been resolved, so anything out
    of range is a caller bug and belongs in the error path. A silent clamp is a
    default-value fallback on error.
    """
    with pytest.raises(ValueError) as caught:
        analyze({}, target_tier=target_tier)
    # ANCHORED. `str(target_tier) in ...` carries no literal text, so it could
    # be satisfied by an unrelated coincidence in the haystack -- and this
    # haystack contains "(valid 1-4)", so the bare form would pass for the
    # wrong reason the moment 1 or 4 joined the parametrisation. Caught by
    # `check_test_integrity` (TI002) before pytest ran.
    assert f"target_tier {target_tier} " in str(caught.value), (
        f"the refusal does not name the value that was refused, so a caller "
        f"cannot tell what was wrong. Message: {str(caught.value)!r}"
    )
    assert "resolve_target_tier" in str(caught.value), (
        "the refusal does not name the function that turns a client-supplied "
        "value into a safe one, so the reader is told what failed and not what "
        "to do instead"
    )


@pytest.mark.unit
@pytest.mark.parametrize("target_tier", [1, 2, 3, 4])
def test_the_engine_still_accepts_every_real_tier(target_tier) -> None:
    """The positive control. A guard that raised on everything would pass above."""
    assert analyze({}, target_tier=target_tier).target_tier == target_tier


@pytest.mark.unit
def test_the_default_is_reachable_without_passing_anything() -> None:
    """`analyze()` with no target must not trip its own new guard."""
    assert analyze({}).target_tier == FALLBACK
