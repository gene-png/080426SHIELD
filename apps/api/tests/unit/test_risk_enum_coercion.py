"""`_coerce_enum` accepts what the model plainly meant, and REPORTS what it did not.

#121, the parser half. The prompt half is `test_ai_prompt_enum_contract.py`;
this file pins the behaviour that makes the fix survive a model which does not
do as it is told.

## Two separate properties, and only one of them is leniency

**Accept case and separator variants.** `Very High`, `very-high` and
`VERY_HIGH` are one token typed three ways. Refusing them is the same defect as
the drift itself, facing the other way -- `CLAUDE.md` records exactly this for
`int()`: accepting `"2"` and `2.0` is right, and silently turning `1.9` into 1
is not. Nothing here invents a value the model did not send.

**Refuse, and SAY SO, anything else.** `severe` is not `very_high` typed
oddly; it is a different claim, and guessing at it would put a number on the
client's risk matrix that no one chose. So it stays refused -- and the refusal
is returned to the caller rather than collapsing to None, because the silent
collapse is what #121 actually cost: forty entries stored with no likelihood,
no impact and no tier, at HTTP 201, with every counter reading zero.

## The distinction the counter depends on

Absent and unresolvable are not the same event. A field the model never sent
has nothing to report; a field it sent and got wrong is the thing worth
counting. Conflating them makes the counter meaningless in the direction that
matters -- it would go non-zero on every sparse-but-valid response.
"""

from __future__ import annotations

import pytest

from app.risk.engine import Impact, Likelihood, RecommendedAction, RiskAxis
from app.routes.risk import _coerce_enum


@pytest.mark.unit
@pytest.mark.parametrize(
    "supplied, expected",
    [
        # Exactly as the prompt now instructs.
        ("very_high", Likelihood.VERY_HIGH),
        ("low", Likelihood.LOW),
        # The Title-Case form the OLD prompt instructed. This is the literal
        # #121 table row: `likelihood 'Very High' -> None` was the shipped
        # behaviour, and a model obeying that prompt produced it every time.
        ("Very High", Likelihood.VERY_HIGH),
        ("Very Low", Likelihood.VERY_LOW),
        # Separator and case variants a real model emits unprompted.
        ("very-high", Likelihood.VERY_HIGH),
        ("VERY_HIGH", Likelihood.VERY_HIGH),
        ("Very  High", Likelihood.VERY_HIGH),
        ("  medium  ", Likelihood.MEDIUM),
    ],
)
def test_a_token_the_model_plainly_meant_resolves(supplied, expected) -> None:
    member, rejected = _coerce_enum(Likelihood, supplied)
    assert member is expected
    assert rejected is None, "a resolved value must report no rejection"


@pytest.mark.unit
@pytest.mark.parametrize(
    "supplied",
    [
        "severe",
        "catastrophic",  # a real token, but of the WRONG enum
        "5",
        "high risk",
        "very_high_indeed",
    ],
)
def test_anything_else_is_refused_AND_reported(supplied) -> None:
    """The discriminating half.

    If this only asserted `member is None` it would pass against the original
    `_enum_or_none`, which returned None for these too — and would therefore
    pin nothing about #121. What it must assert is that the caller is TOLD.
    """
    member, rejected = _coerce_enum(Likelihood, supplied)
    assert member is None
    assert rejected == supplied, (
        "an unresolvable value must be handed back so it can be counted; "
        "returning None alone is the silent collapse #121 is about"
    )


@pytest.mark.unit
@pytest.mark.parametrize("supplied", [None, "", "   "])
def test_absence_is_not_a_rejection(supplied) -> None:
    """A field the model never sent has nothing to report.

    Counting these would make the rejection counter non-zero on every sparse
    but entirely valid response, which is the fastest way to get a real signal
    ignored.
    """
    member, rejected = _coerce_enum(Likelihood, supplied)
    assert member is None
    assert rejected is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "enum_cls, supplied, expected",
    [
        (Impact, "Catastrophic", Impact.CATASTROPHIC),
        (Impact, "negligible", Impact.NEGLIGIBLE),
        (RiskAxis, "Detection", RiskAxis.DETECTION),
        (RecommendedAction, "Remediate", RecommendedAction.REMEDIATE),
        (RecommendedAction, "transfer", RecommendedAction.TRANSFER),
    ],
)
def test_every_enum_the_route_validates_gets_the_same_treatment(
    enum_cls, supplied, expected
) -> None:
    """All four fields, not just the two that were broken.

    `axis` and `recommended_action` were never wrong — their prompt already
    named the exact tokens. They are covered here anyway because the fix is a
    shared function, and a fix applied to one caller and not its twins is the
    half-fix this repo keeps recording.
    """
    member, rejected = _coerce_enum(enum_cls, supplied)
    assert member is expected
    assert rejected is None


@pytest.mark.unit
def test_a_wrong_enums_token_does_not_leak_across_fields() -> None:
    """`high` is a Likelihood and not an Impact, and coercion must not blur that.

    Normalisation is case and separator only. If it ever became a fuzzy match,
    this is the assertion that would catch it — a value resolving against the
    wrong enum would put a tier on the client's matrix that nobody chose.
    """
    member, rejected = _coerce_enum(Impact, "very_high")
    assert member is None
    assert rejected == "very_high"
