"""The deferred-item alarm clock (`apps/api/scripts/fire_scheduled_triggers.py`).

Tested here rather than left to fire blind in CI, because its whole value is that
it is reliable: a mechanism nobody trusts gets muted, and a muted mechanism is the
"tracked but never comes up" state it exists to end.

Only the pure parsing half is covered. `main()` shells out to `gh`, and a test
that mocked `gh` would be asserting my model of the API rather than the API —
which is the shape CLAUDE.md records as a test that cannot fail.
"""

from __future__ import annotations

from datetime import date

import pytest
from scripts.fire_scheduled_triggers import parse_trigger


@pytest.mark.unit
def test_a_well_formed_trigger_parses() -> None:
    body = (
        "Some context about the deferred work.\n\n"
        "Trigger-date: 2026-10-01\n"
        "Trigger-reason: MVP item 8 is the last one; this opens when it merges.\n"
    )
    due, reason = parse_trigger(body)
    assert due == date(2026, 10, 1)
    assert reason.startswith("MVP item 8")


@pytest.mark.unit
def test_a_missing_date_raises_rather_than_being_skipped() -> None:
    """FAIL LOUDLY. A silently ignored alarm clock is worse than none, because
    the label implies one is set — the item then reads as scheduled while nothing
    will ever fire. That is the exact state this script exists to end, arriving
    through the script itself."""
    with pytest.raises(ValueError, match="no `Trigger-date:` line"):
        parse_trigger("Trigger-reason: because\n")


@pytest.mark.unit
def test_a_missing_reason_raises() -> None:
    """A date with no reason produces a comment nobody can act on, which is how a
    reminder becomes noise and then gets muted."""
    with pytest.raises(ValueError, match="no `Trigger-reason:` line"):
        parse_trigger("Trigger-date: 2026-10-01\n")


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad", ["01-10-2026", "2026/10/01", "October 1 2026", "2026-13-01", "soon"]
)
def test_a_malformed_date_raises_with_the_value_in_the_message(bad: str) -> None:
    """Including `soon` and `2026-13-01`: the first is what someone actually
    types when they mean "later", and the second parses as a date shape but is
    not one. Both must be refused, and the message must quote the value so the
    fix is obvious from the CI log alone."""
    with pytest.raises(ValueError, match="not an ISO date"):
        parse_trigger(f"Trigger-date: {bad}\nTrigger-reason: because\n")


@pytest.mark.unit
def test_the_labels_are_case_insensitive_but_the_date_is_not_guessed() -> None:
    """Tolerant about how the marker is typed, strict about what it means.

    Someone writing `trigger-date:` in lower case should not silently get no
    alarm; someone writing an ambiguous date should not get a guessed one.
    """
    due, _ = parse_trigger("trigger-date: 2026-10-01\ntrigger-reason: x\n")
    assert due == date(2026, 10, 1)
