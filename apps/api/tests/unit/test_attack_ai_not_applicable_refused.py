"""#841: the AI may not mark an ATT&CK technique not applicable.

N/A is a scoping RULING: it takes the technique out of the coverage
denominator, so an AI-written N/A raised the client's percentage on the model's
word, with no evidence behind it (the payload carries no asset inventory that
could support `platform_absent`) and nothing reviewing it. The advisor's ruling
(issue 841, comment 5983735013): the Run-AI write path refuses `not_applicable`
WHOLE and records it in `statuses_rejected`; a consultant can still rule a
technique N/A through the PATCH.

Every assertion goes through the endpoints: the Run-AI run's result, the audit
row it writes, the admin heatmap, and the PATCH. Expected values are written out.
"""

from __future__ import annotations

import pytest

from tests._ai_runs import attack_run_ai
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _SUGGESTED_RATIONALE,
    _one_row_run_with_reason,
    _run_audit,
    app_client,
)

pytestmark = pytest.mark.unit


def test_an_ai_not_applicable_is_refused_whole_and_counted(app_client) -> None:  # noqa: F811
    c, TestSession, provider = app_client
    h, svc_id, row_id, code = _one_row_run_with_reason(
        c, TestSession, provider, "not_applicable", "platform_absent"
    )
    before = next(
        t
        for t in c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()[
            "coverage"
        ]
        if t["id"] == row_id
    )
    result = attack_run_ai(c, svc_id, h)
    row = next(t for t in result["coverage"] if t["id"] == row_id)
    # The row keeps what it had (unscored): no status, no tools, no rationale,
    # and nobody recorded as having answered it.
    assert row["status"] is None
    assert (row["answered_by"], row["answered_at"]) == (
        before["answered_by"],
        before["answered_at"],
    )
    assert not row["detection_tools"]
    assert row["rationale"] != _SUGGESTED_RATIONALE
    # Disclosed on the run (the workspace's N1 line) and in the audit row.
    assert result["not_applicable_refused"] == 1
    # One entry per batch that made the suggestion; every one names this row.
    rejected = _run_audit(TestSession)["statuses_rejected"]
    # More than one batch made the same suggestion, so the count of 1 above is
    # the DISTINCT-technique count, not the number of suggestions.
    assert len(rejected) > 1, rejected
    assert rejected and all(
        e == {"technique_code": code, "status": "not_applicable"} for e in rejected
    )


def test_a_consultants_gap_survives_an_ai_not_applicable(app_client) -> None:  # noqa: F811
    """The flattering direction: an AI N/A over a consultant's gap took the gap
    out of the denominator. Now the gap stays, and the heatmap still counts it."""
    c, TestSession, provider = app_client
    h, svc_id, row_id, _code = _one_row_run_with_reason(
        c, TestSession, provider, "not_applicable", "platform_absent"
    )
    r = c.patch(f"/attack/coverage/{row_id}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text

    result = attack_run_ai(c, svc_id, h)
    row = next(t for t in result["coverage"] if t["id"] == row_id)
    assert row["status"] == "gap"
    assert result["not_applicable_refused"] == 1

    heat = c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()
    assert (heat["gap"], heat["not_applicable"]) == (1, 0)
    assert heat["coverage_pct"] == 0.0  # one assessed row, a gap


def test_a_consultant_can_still_rule_a_technique_not_applicable(app_client) -> None:  # noqa: F811
    c, TestSession, provider = app_client
    h, _svc_id, row_id, _code = _one_row_run_with_reason(c, TestSession, provider, "gap", None)
    r = c.patch(
        f"/attack/coverage/{row_id}",
        headers=h,
        json={"status": "not_applicable", "reason_code": "platform_absent"},
    )
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reason_code"]) == ("not_applicable", "platform_absent")


def test_a_run_with_nothing_refused_says_zero(app_client) -> None:  # noqa: F811
    c, TestSession, provider = app_client
    h, svc_id, _row_id, _code = _one_row_run_with_reason(c, TestSession, provider, "gap", None)
    result = attack_run_ai(c, svc_id, h)
    assert result["not_applicable_refused"] == 0
