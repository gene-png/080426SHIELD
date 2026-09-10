"""A JSON boolean is not a number, and Pydantic's lax mode disagrees (#189).

`bool` subclasses `int`, so `isinstance(True, int)` is True and Pydantic v2's
lax mode accepts `true` for any `int` field -- as the integer 1, *before* any
range check runs. `PATCH {"maturity_stage": true}` therefore writes **Stage 1**
to the database and returns 200: a stage nobody chose, attributed to whoever
made the request.

## Why an annotated type and not a third hand-rolled guard

Two writers of these columns already refuse bools, each with its own guard and
its own comment saying why -- `routes/zt.py::_as_number` ("bool is an int
subclass, but `True` is not a stage") and `zt/scoring.py::resolve_target_stage`
("a stored `True` resolves to Stage 1 and gets attributed to the client"). A
third copy would be a third place to drift. This puts the rule where the field
is DECLARED, so no route has to remember it.

## Why not `Field(strict=True)`, which #189 offers first

The issue offers two fixes as if they were equivalent. Measured, they are not:

    strict=True       true -> rejected   2.0 -> REJECTED   "2" -> REJECTED
    BeforeValidator   true -> rejected   2.0 -> 2          "2" -> 2

`strict=True` fails #189's own acceptance criterion, which asks that `2`, `2.0`
and `"2"` stay accepted, and it contradicts `CLAUDE.md` directly: "Accept `"2"`
and `2.0`: refusing a value the model plainly meant is the same defect facing
the other way." A browser posting a `<select>` value sends `"2"`. Only the
BeforeValidator refuses the one input that is actually wrong.

## A range bound is not this guard, however much it looks like one

Before this type existed, every inbound int field that refused `False` did so
through a `ge=1` or `ge=2` floor that happens to sit above zero -- never on
purpose, and never for `True`, which is 1 and clears any floor of 1. Protection
that is a side effect of a range bound expires silently the day someone widens
the range. `tests/unit/test_bool_is_not_a_number.py` therefore asserts the
REASON a bool was refused rather than merely that it was.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator

# The test keys on this marker to tell "refused because bool" apart from
# "refused by a range bound that happens to exclude 0 or 1". Changing the
# wording is fine; dropping the marker makes that test unable to discriminate,
# and it says so when it fails.
BOOL_REFUSAL_MARKER = "is a boolean, not a number"


def _refuse_bool(value: Any) -> Any:
    """Reject `True`/`False` before Pydantic can silently read them as 1/0."""
    if isinstance(value, bool):
        raise ValueError(
            f"{value!r} {BOOL_REFUSAL_MARKER}. Send the number itself -- "
            f"`true` is not a score, a stage, a tier or a count."
        )
    return value


#: An `int` that refuses a boolean. Everything else Pydantic's lax mode accepts
#: for an int -- `2`, `2.0`, `"2"` -- is still accepted; `1.9` and `"two"` are
#: still refused. Use it for any inbound int, and pair it with the `ge`/`le`
#: bounds the field already needs: this type says nothing about range.
IntNotBool = Annotated[int, BeforeValidator(_refuse_bool)]
