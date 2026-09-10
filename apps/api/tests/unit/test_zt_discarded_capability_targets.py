"""A per-capability target that could not be used must be NAMED, not just dropped (#188).

`analyze_gaps` falls back to the engagement target whenever a stored
`ZtAnswer.target_stage` is not a usable stage for the framework, and records
nothing. The client's document then shows a remediation row against a target
they did not choose, and no line anywhere says their stored value was
discarded.

The exemption was deliberate and is tracked here: naming the fault needs a
field on `GapAnalysis`, and `zt/exporters.py` reads that shape, which was
outside the constraint #125's branch worked under (rendered numbers unchanged).

## ABSENT and UNUSABLE are different events, and the whole fix is telling them apart

Most capabilities carry no per-row target at all. That is the ordinary case --
a consultant-scored assessment overrides nothing -- and reporting it would make
the disclosure fire on every engagement and be ignored by the second one.

A capability whose stored value *exists* and cannot be used is the opposite: a
choice was made, recorded, and then silently replaced. `CLAUDE.md` states this
as a standing rule -- "a rule that withholds a claim must separate 'the
evidence failed' from 'no evidence was offered'".

## The sharpest live path is a framework whose ceiling is lower

Stage 4 is a legitimate CISA target and does not exist in DoD ZTRA, which has
three. The same stored integer is therefore usable or not depending on which
framework is asking, with no edit to the row in between -- so this is not only
about malformed legacy data.

## Why the disclosure lands in the gap caption

`_gap_plan_caption` already tells the client "each row shows the target applied
to that capability". That sentence is true and, for a discarded row, misleading
in the specific way `CLAUDE.md` warns about: it is accurate, it sits exactly
where a confused reader looks, and it ends the search. The row does show the
target applied -- it just is not the one anybody chose. The disclosure belongs
in that sentence rather than in a footnote elsewhere.

## Bool is in the table for a reason, and it is NOT reachable through the database

`target_stage` is a `SmallInteger`, so SQLAlchemy stores `True` as 1 and the
value never comes back a bool. The row is here because
`capability_target_override` is a pure function with its own contract, and
measured on 2026-09-10 it returns `True` itself -- a bool as a stage. The
capability then silently leaves the gap list entirely (target 1, current 1, no
gap), which is a worse outcome than the fallback this issue is about. Claimed
as a contract defect, not as a client-facing one.
"""

from __future__ import annotations

import pytest

from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode, level_count
from app.zt.scoring import (
    analyze_gaps,
    discarded_capability_targets,
    effective_target_stages,
)

CISA = ZtFrameworkCode.CISA_ZTMM_2_0
DOD = ZtFrameworkCode.DOD_ZTRA


def _first_code(framework: ZtFrameworkCode) -> str:
    return capabilities(framework)[0].code


@pytest.mark.unit
@pytest.mark.parametrize(
    "stored",
    [
        pytest.param(None, id="absent"),
        pytest.param(1, id="lowest-valid"),
        pytest.param(3, id="mid-valid"),
    ],
)
def test_a_usable_or_absent_target_is_not_reported(stored) -> None:
    """The disclosure must not fire on the ordinary case.

    If it did, every engagement would carry it and the second reader would
    stop seeing it -- which is how a real disclosure becomes decoration.
    """
    code = _first_code(CISA)
    assert discarded_capability_targets(CISA, {code: stored}) == ()


@pytest.mark.unit
@pytest.mark.parametrize(
    "stored",
    [
        pytest.param(5, id="above-the-ceiling"),
        pytest.param(0, id="the-retired-stage-0"),
        pytest.param(-1, id="negative"),
        pytest.param("3", id="a-string-that-looks-right"),
        pytest.param(3.0, id="a-float-that-looks-right"),
        pytest.param(2.5, id="a-fraction"),
        pytest.param("x", id="not-a-number"),
        pytest.param(True, id="a-bool"),
        pytest.param(False, id="a-bool-that-is-zero"),
    ],
)
def test_a_stored_value_that_cannot_be_used_is_reported(stored) -> None:
    """Supplied and unusable. Somebody chose something and it was discarded."""
    code = _first_code(CISA)
    assert discarded_capability_targets(CISA, {code: stored}) == (code,)


@pytest.mark.unit
def test_the_same_value_is_usable_or_not_depending_on_the_framework() -> None:
    """Stage 4 is a real CISA target and does not exist in DoD ZTRA.

    No edit to the row in between -- which is why this is not only a story
    about malformed legacy data.
    """
    assert level_count(CISA) == 4 and level_count(DOD) == 3, "the premise moved"

    cisa_code = _first_code(CISA)
    assert discarded_capability_targets(CISA, {cisa_code: 4}) == ()

    dod_code = _first_code(DOD)
    assert discarded_capability_targets(DOD, {dod_code: 4}) == (dod_code,)


@pytest.mark.unit
def test_a_bool_never_becomes_a_stage() -> None:
    """The contract defect, asserted separately from the fallback it causes.

    Measured before the fix: `capability_target_override(CISA, True)` returned
    `True` -- a bool used as a stage. `Gap.target_stage` became `True`, the
    capability compared equal to its own current stage, and it left the gap
    list with nothing recording that it had ever had a target.

    Not reachable through the database (`SmallInteger` stores `True` as 1), so
    this pins a function's contract rather than a client-facing path.
    """
    code = _first_code(CISA)
    applied = effective_target_stages(CISA, {code: True}, 3)
    assert applied[code] == 3, "a bool must fall back, not become Stage 1"
    assert not isinstance(applied[code], bool), "a stage must never be a bool"


@pytest.mark.unit
def test_the_gap_analysis_carries_the_discarded_codes() -> None:
    """The field the deliverable reads. A tuple, mirroring `unscored_codes`.

    Codes rather than a bare count, so the disclosure can name them and the
    count stays derivable -- `CLAUDE.md` rule 1: let the list be the count.
    """
    code = _first_code(CISA)
    result = analyze_gaps(CISA, {code: 1}, target_stage=3, targets={code: 7})
    assert result.unusable_target_codes == (code,)

    clean = analyze_gaps(CISA, {code: 1}, target_stage=3, targets={code: 4})
    assert clean.unusable_target_codes == ()


@pytest.mark.unit
def test_the_discarded_row_still_appears_against_the_fallback_target() -> None:
    """Disclosing must not also DROP the row.

    The remediation item is still real -- the client is at Stage 1 and the
    engagement wants 3. Withholding it to signal uncertainty would take a
    finding out of the client's plan, which is the withholding-from-a-ratio
    mistake `CLAUDE.md` records pointed at a list instead of a fraction.
    """
    code = _first_code(CISA)
    result = analyze_gaps(CISA, {code: 1}, target_stage=3, targets={code: 7})
    row = next((g for g in result.gaps if g.code == code), None)
    assert row is not None, "the gap was dropped instead of disclosed"
    assert row.target_stage == 3, "the row must show the target actually applied"
    assert code in result.unusable_target_codes


@pytest.mark.unit
def test_the_dashboard_and_the_deliverable_cannot_disagree() -> None:
    """One rule, two consumers -- the argument `effective_target_stages` makes.

    `zt_dashboard` and `analyze_gaps` both resolve targets through the same
    function. If the discard set were derived separately for the deliverable,
    the dashboard could show a target percentage built on a substitution its
    own page never mentions. Same defect as #84, one surface over.
    """
    code = _first_code(CISA)
    targets = {code: 9}

    applied = effective_target_stages(CISA, targets, 3)
    discarded = discarded_capability_targets(CISA, targets)
    result = analyze_gaps(CISA, {code: 1}, target_stage=3, targets=targets)

    assert applied[code] == 3
    assert discarded == (code,)
    assert result.unusable_target_codes == discarded, (
        "the gap engine and the shared rule disagree about which stored "
        "targets were discarded. They must read the same function."
    )


@pytest.mark.unit
def test_the_client_document_says_the_stored_target_was_not_used() -> None:
    """The disclosure the client actually reads (#188's point).

    Before this, the deliverable showed a remediation row against a target the
    client did not choose, with `_gap_plan_caption` stating "each row shows the
    target applied to that capability" -- true, and the reason nobody looked
    further.
    """
    from app.zt.exporters import _gap_plan_caption

    code = _first_code(CISA)
    disclosed = _gap_plan_caption(analyze_gaps(CISA, {code: 1}, target_stage=3, targets={code: 7}))
    assert code in disclosed, f"the caption does not name the row: {disclosed!r}"
    assert "not a valid stage" in disclosed, disclosed


@pytest.mark.unit
def test_an_ordinary_engagement_carries_no_disclosure() -> None:
    """The positive control, and it is what keeps the disclosure meaningful.

    A sentence printed on every deliverable is decoration by the second one.
    Without this, a caption that appended the text unconditionally would pass
    the test above.
    """
    from app.zt.exporters import _gap_plan_caption

    code = _first_code(CISA)
    clean = _gap_plan_caption(analyze_gaps(CISA, {code: 1}, target_stage=3, targets={code: 4}))
    assert "not a valid stage" not in clean, clean
    assert "Engagement target S3" in clean, "the existing caption must survive"
