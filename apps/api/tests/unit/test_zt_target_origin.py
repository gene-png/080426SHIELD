"""#1343: the per-capability ZT targets whose origin is not recorded, as the
client outputs will disclose them (approved scope, #736 6225076633).

A code is listed when its stored target is the one the gap engine APPLIES
(a usable per-capability override) and nobody recorded who set it
(`target_source` NULL: stored before migration 0076, some by earlier AI runs).
A target the consultant set, no target at all, and an unusable target (the
engine falls back to the engagement stage, so it decides nothing) are not.
The expected codes below are written from that rule, not computed by the
helper under test.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.zt.catalog import capabilities
from app.zt.maturity import ZtFrameworkCode

pytestmark = pytest.mark.unit

#: Approved verbatim at #736 comment 6220094031 item 5 (the questionnaire's
#: line), reused for the client outputs by 6225076633.
NOT_RECORDED = "Who set this target is not recorded. An earlier AI run may have set it."


def _row(code: str, target, source):
    return SimpleNamespace(capability_code=code, target_stage=target, target_source=source)


def test_only_an_applied_target_with_no_recorded_origin_is_listed() -> None:
    from app.zt.target_origin import unrecorded_target_codes

    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    a, b, c, d, e = (cap.code for cap in list(capabilities(fw))[:5])
    rows = [
        _row(a, 3, None),  # applied, origin not recorded: listed
        _row(b, 3, "consultant"),  # applied, the consultant set it
        _row(c, None, None),  # no per-capability target
        _row(d, 9, None),  # unusable: the engine applies the engagement stage
        _row(e, 2, None),  # applied, origin not recorded: listed
        _row("NOT.A.CODE", 3, None),  # not in this framework
    ]
    assert unrecorded_target_codes(fw, rows) == (a, e)


def test_a_bool_target_is_not_an_applied_target() -> None:
    from app.zt.target_origin import unrecorded_target_codes

    fw = ZtFrameworkCode.DOD_ZTRA
    code = capabilities(fw)[0].code
    assert unrecorded_target_codes(fw, [_row(code, True, None)]) == ()


def test_the_sentence_is_the_approved_one() -> None:
    from app.zt.target_origin import TARGET_ORIGIN_NOT_RECORDED

    assert TARGET_ORIGIN_NOT_RECORDED == NOT_RECORDED
