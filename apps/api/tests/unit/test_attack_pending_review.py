"""#102 / plan 5.1: unconfirmed support must not feed the coverage score.

`run_ai` assigns a technique's status from the model INDEPENDENTLY of what
happened to that row's citations, so a technique whose every citation was
rejected kept `covered` with an EMPTY tool list and carried full weight in
`coverage_pct` and the client PDF. W2 surfaced the counts and deliberately did
not change the score; this is the half that does.

THE RULE (5.1, owner-confirmed 2026-08-08 — not to be re-litigated here):

    A technique's status counts toward the score only when it is backed by a
    CONFIRMED citation — not merely a resolved one, and not a flagged one. A
    technique whose support is unconfirmed gets its OWN visible state. It is
    never collapsed into `gap`.

Scoring as `gap` was considered and REJECTED: gap says *nothing was found*,
pending-review says *something was found but is not confirmed yet*. Collapsing
the second into the first is a false negative dressed as a finding — it sends a
consultant hunting for a control the client already owns.

`pending_review` is also NOT folded into `unscored`. `unscored` means "no human
or model has assigned a status"; pending-review means "a status exists and its
evidence is unconfirmed". One number for both meanings is the same conflation
one layer down.

The state is DERIVED, never stored as the status. Clearing a flag must move the
technique into whichever of covered/partial/gap its stored status says — so the
status has to survive untouched underneath.
"""

from __future__ import annotations

import pytest

from app.attack.analytics import compute
from app.attack.catalog import TECHNIQUES

_T = [t.id for t in TECHNIQUES]


def _map(**by_code: str) -> dict[str, str | None]:
    return dict(by_code)


@pytest.mark.unit
def test_a_pending_technique_is_not_counted_as_covered() -> None:
    covered = compute(_map(**{_T[0]: "covered"}))
    pending = compute(_map(**{_T[0]: "covered"}), pending_codes={_T[0]})
    assert covered.covered == 1
    assert pending.covered == 0
    assert pending.pending_review == 1


@pytest.mark.unit
def test_a_pending_technique_is_not_counted_as_a_gap() -> None:
    """Asserted on the NUMBER, not the label — 5.1 invariant 2.

    Collapsing pending into gap is the false negative this rule rejects: it
    sends a consultant hunting for a control the client already owns.
    """
    rollup = compute(_map(**{_T[0]: "covered"}), pending_codes={_T[0]})
    assert rollup.gap == 0


@pytest.mark.unit
def test_a_pending_technique_is_not_folded_into_unscored() -> None:
    """`unscored` means no status was ever assigned. These have one."""
    baseline = compute({})
    rollup = compute(_map(**{_T[0]: "covered"}), pending_codes={_T[0]})
    assert rollup.unscored_count == baseline.unscored_count - 1
    assert rollup.pending_review == 1


@pytest.mark.unit
def test_flagging_every_citation_cannot_raise_the_score() -> None:
    """5.1 invariant 1: a run whose citations are ALL flagged produces a
    coverage percentage no higher than the same run with them rejected."""
    statuses = {_T[i]: "covered" for i in range(10)}
    all_flagged = compute(statuses, pending_codes=set(statuses))
    as_if_rejected = compute({})
    assert all_flagged.coverage_pct <= as_if_rejected.coverage_pct or (
        all_flagged.coverage_pct == 0.0
    )


@pytest.mark.unit
def test_clearing_a_flag_moves_the_technique_to_its_stored_status() -> None:
    """5.1 invariant 3 — and the reason `pending_review` is derived rather than
    written over `status`: the status must survive underneath to move back to."""
    before = compute(_map(**{_T[0]: "partial"}), pending_codes={_T[0]})
    after = compute(_map(**{_T[0]: "partial"}))
    assert before.pending_review == 1 and before.partial == 0
    assert after.pending_review == 0 and after.partial == 1
    assert after.coverage_pct > before.coverage_pct


@pytest.mark.unit
def test_every_technique_lands_in_exactly_one_bucket() -> None:
    """5.1 invariant 4. No row may fall between states."""
    statuses = {_T[0]: "covered", _T[1]: "partial", _T[2]: "gap", _T[3]: "not_applicable"}
    r = compute(statuses, pending_codes={_T[0]})
    total = (
        r.covered
        + r.partial
        + r.gap
        + r.not_applicable
        + r.unscored_count
        + r.pending_review
    )
    assert total == len(TECHNIQUES)


@pytest.mark.unit
def test_pending_is_excluded_from_addressable_not_scored_as_zero() -> None:
    """Excluded from BOTH numerator and denominator, like `unscored`.

    Scoring it as a zero in the denominator would understate coverage rather
    than withhold a claim, which is a different (and also wrong) answer.
    """
    two_covered = compute(_map(**{_T[0]: "covered", _T[1]: "covered"}))
    one_pending = compute(
        _map(**{_T[0]: "covered", _T[1]: "covered"}), pending_codes={_T[1]}
    )
    assert two_covered.coverage_pct == 100.0
    assert one_pending.coverage_pct == 100.0, (
        "pending was scored as a zero instead of being withheld — that understates "
        "coverage rather than declining to claim it"
    )
    assert one_pending.pending_review == 1


@pytest.mark.unit
def test_a_pending_code_with_no_status_stays_unscored() -> None:
    """Nothing was found AND nothing is unconfirmed. `pending_review` must not
    manufacture a state for a technique nobody assessed."""
    r = compute({}, pending_codes={_T[0]})
    assert r.pending_review == 0
    assert r.unscored_count == len(TECHNIQUES)


@pytest.mark.unit
def test_a_not_applicable_technique_is_never_pending() -> None:
    """`not_applicable` is outside `addressable` already; flagging its evidence
    changes nothing about a claim that was never made."""
    r = compute(_map(**{_T[0]: "not_applicable"}), pending_codes={_T[0]})
    assert r.pending_review == 0
    assert r.not_applicable == 1


@pytest.mark.unit
def test_tactic_rollups_carry_pending_too() -> None:
    """The heatmap is per-tactic; a number that is honest only in the total is
    not honest where a consultant reads it."""
    code = _T[0]
    r = compute(_map(**{code: "covered"}), pending_codes={code})
    touched = [t for t in r.by_tactic if t.pending_review > 0]
    assert touched, "no tactic reported the pending technique"
    for t in touched:
        assert t.covered == 0
