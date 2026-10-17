"""#1011: the client home card read "not checked" the same as "checked, none
found". `attack_covered_relies_on_outside_tool` is None in both "nothing could
be checked" and "no ATT&CK figure at all", and False for "checked, none found",
so the card said nothing in the first case and the unknown read as clean.

Plan: track1, #736 comment 6093958175. Ruling: the advisor, #736 comment
6094262391 (strings 1 to 3 approved, state B shows nothing).

The four states the home-card ATT&CK slot can be in, through
`GET /clients/{cid}/value-summary`:

| State | flag  | reason                          |
| A     | True  | None (checked, an outside tool) |
| B     | False | None (checked, none found)      |
| C     | None  | "no_list", "empty", "discarded" |
| D     | None  | None (no ATT&CK figure)         |

The reason values are written out below, never imported from the module that
produces them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.clients import ValueSummaryResponse
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_subset_after_release import (
    _approve_finalize,
    _cover,
    _r4_world,
    _release,
    _value_summary,
)
from tests.unit.test_attack_subset_drift import (
    EDR,
    LEGACY,
    _codes,
    _no_list_world,
    _with_storage,
    _world,
)

pytestmark = pytest.mark.unit

FIELD = "attack_subset_not_checked_reason"


# --- State C: not checked, and why ---------------------------------------------


@pytest.mark.parametrize("reason", ["no_list", "empty", "discarded"])
def test_state_c_carries_why_nothing_was_checked(
    app_parts, tmp_path, reason: str  # noqa: F811
) -> None:
    _with_storage(app_parts, tmp_path)
    w = _r4_world(app_parts, reason)
    _release(w, _approve_finalize(w))
    body = _value_summary(w)
    assert body["attack_uncovered_count"] is not None, body  # positive first
    assert body["attack_covered_relies_on_outside_tool"] is None, body
    assert body[FIELD] == reason, body


def test_state_c_in_t6s_no_list_world_reads_no_list(app_parts, tmp_path) -> None:  # noqa: F811
    """The world `test_t6_the_home_card_flag_is_null_with_no_list` builds (no
    Tech Debt list, a Covered row citing a tool the consultant typed): the flag
    is None, and the reason now says why. That test's docstring ("the card has
    nothing to say") predates #1011 and is left as it is (a prose follow-up)."""
    _with_storage(app_parts, tmp_path)
    w = _no_list_world(app_parts)
    _cover(w, _codes(w)[0], ["Tool A"])
    _release(w, _approve_finalize(w))
    body = _value_summary(w)
    assert body["attack_uncovered_count"] is not None, body  # positive first
    assert body["attack_covered_relies_on_outside_tool"] is None, body
    assert body[FIELD] == "no_list", body


# --- State B: checked, none found -------------------------------------------------


@pytest.mark.parametrize("world", ["checked", "fallback"])
def test_state_b_carries_no_reason(app_parts, tmp_path, world: str) -> None:  # noqa: F811
    """Checked and nothing outside, including a client whose newest list
    version fell back to an earlier one (C9): that list WAS checked."""
    _with_storage(app_parts, tmp_path)
    if world == "checked":
        w = _world(app_parts)
        _cover(w, _codes(w)[0], [EDR])
    else:
        w = _r4_world(app_parts, "fallback")
    _release(w, _approve_finalize(w))
    body = _value_summary(w)
    assert body["attack_uncovered_count"] is not None, body  # positive first
    assert body["attack_covered_relies_on_outside_tool"] is False, body
    assert body[FIELD] is None, body


# --- State A: checked, an outside tool found ---------------------------------------


def test_state_a_carries_no_reason(app_parts, tmp_path) -> None:  # noqa: F811
    _with_storage(app_parts, tmp_path)
    w = _world(app_parts)
    # #1016: LEGACY is the row's only tool, so its Covered status rests on
    # it, and the home card's "relies on" holds once LEGACY leaves the list.
    _cover(w, _codes(w)[0], [LEGACY])
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)
    body = _value_summary(w)
    assert body["attack_covered_relies_on_outside_tool"] is True, body  # positive first
    assert body[FIELD] is None, body


# --- State D: no ATT&CK figure -------------------------------------------------------


def test_state_d_carries_no_reason(app_parts, tmp_path) -> None:  # noqa: F811
    """No released ATT&CK assessment and no list: nothing to qualify, so the
    reason stays None although nothing could have been checked either."""
    _with_storage(app_parts, tmp_path)
    w = _no_list_world(app_parts)
    _cover(w, _codes(w)[0], [EDR])
    body = _value_summary(w)
    assert body["attack_uncovered_count"] is None, body
    assert body["attack_covered_relies_on_outside_tool"] is None, body
    assert body[FIELD] is None, body


# --- The validator: the reason exactly in state C --------------------------------------


def _fields(**over: object) -> dict:
    base: dict = {
        "tech_debt_savings_usd": None,
        "tech_debt_savings_cost_known": True,
        "tech_debt_savings_unresolved": False,
        "zt_gap_count": None,
        "zt_gap_unresolved": False,
        "zt_services": 0,
        "zt_targets_defaulted": None,
        "zt_targets_unusable": None,
        "zt_targets_computed_live": None,
        "attack_uncovered_count": 3,
        "attack_uncovered_unresolved": False,
        "attack_uncovered_withheld": False,
        "attack_not_verified_count": None,
        "attack_covered_relies_on_outside_tool": None,
        FIELD: "no_list",
        "csf_gap_count": None,
        "csf_gap_unresolved": False,
        "csf_services": 0,
        "csf_targets_defaulted": None,
        "csf_targets_unusable": None,
        "csf_targets_computed_live": None,
        "has_any_data": True,
        "has_unresolved": False,
    }
    base.update(over)
    return base


def test_the_validator_accepts_each_state() -> None:
    # Positive first: every legal pairing builds.
    for over in (
        {},  # C
        {"attack_covered_relies_on_outside_tool": True, FIELD: None},  # A
        {"attack_covered_relies_on_outside_tool": False, FIELD: None},  # B
        {"attack_uncovered_count": None, FIELD: None},  # D
    ):
        ValueSummaryResponse(**_fields(**over))


@pytest.mark.parametrize(
    ("over", "needle"),
    [
        # A reason beside no figure: state D cannot carry one.
        ({"attack_uncovered_count": None}, "without an ATT&CK figure"),
        # A reason beside a checked flag: A and B cannot carry one.
        ({"attack_covered_relies_on_outside_tool": False}, "beside a checked flag"),
        ({"attack_covered_relies_on_outside_tool": True}, "beside a checked flag"),
        # State C with no reason: the unknown would read as clean again.
        ({FIELD: None}, "carries no reason"),
        # A value nobody writes.
        ({FIELD: "unknown"}, "not a known reason"),
    ],
)
def test_the_validator_refuses_a_reason_outside_state_c(over: dict, needle: str) -> None:
    with pytest.raises(ValidationError) as exc:
        ValueSummaryResponse(**_fields(**over))
    assert needle in str(exc.value), str(exc.value)
