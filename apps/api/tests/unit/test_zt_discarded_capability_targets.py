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

## WHICH ROWS CAN REACH THIS -- the first draft of this section was wrong

It claimed a live path: the same stored integer usable under CISA and not under
DoD, "with no edit to the row in between". There is no such path. Capability
codes are framework-namespaced (`CISA.ID.01` vs `DOD.USR.01`), every `ZtAnswer`
is created from its own assessment's catalog, and both read paths take the
framework from the assessment -- so a DoD analysis can never look up a
CISA-keyed row. The test written to prove it used two DIFFERENT codes, which
should have been the tell.

The real population is rows written before the per-framework range guards, or
written outside the API. No current writer can produce one. The
framework-ceiling test below is kept because it pins the PREDICATE's dependence
on `level_count`, which is real; it is not evidence of a reachable defect.

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
def test_every_surface_that_reads_a_gap_analysis_exposes_the_discard() -> None:
    """The three consumers, checked as SCHEMA CONTRACTS rather than as one call.

    This replaces `test_the_dashboard_and_the_deliverable_cannot_disagree`,
    which asserted `analyze_gaps(...).unusable_target_codes ==
    discarded_capability_targets(...)`. `analyze_gaps` populates that field BY
    CALLING that function, so the assertion could not fail while the line
    existed -- its expected value came from the thing under test, and it was
    named for a claim about the dashboard while touching no dashboard code.

    Three surfaces read a ZT `GapAnalysis`: the exporter caption, the client
    dashboard, and the consultant gap-analysis endpoint. A fault disclosed in
    the PDF and hidden on the screen is two surfaces stating different things
    about one assessment -- and hiding it from the consultant is worse, since
    they are the one who can fix the row.

    Asserted on the response MODELS, so this fails if a field is dropped from
    a contract, which is the failure that would actually reintroduce the gap.
    """
    from app.schemas.clients import ZtDashboardResponse
    from app.schemas.zt import GapAnalysisResponse

    for model in (ZtDashboardResponse, GapAnalysisResponse):
        assert "unusable_target_codes" in model.model_fields, (
            f"{model.__name__} no longer carries the discard set. The "
            f"deliverable still discloses it, so this surface would state "
            f"something different about the same assessment."
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
    assert "could not be used" in disclosed, disclosed


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
    assert "could not be used" not in clean, clean
    assert "Engagement target S3" in clean, "the existing caption must survive"
