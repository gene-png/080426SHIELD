"""A refusal count names techniques that KEEP the status they had, so a
technique the same run also applied is not counted (PR #951 narrow review).

`_run_mitre_map_batched` flattens every batch, and one technique can be
suggested more than once: refused once and applied once, it ends with the
applied status, and "keeps the status it had" would be false of it. The same
holds for `not_applicable_refused` (#841), whose copy says "and not applied".

Both orders are pinned, because the apply loop reads the suggestions in order.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import attack_run_ai
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _one_row_run_with_reason,
    _run_audit,
    app_client,
)

pytestmark = pytest.mark.unit


def _suggestion(code: str, status: str, reason: str | None) -> dict:
    return {
        "technique_code": code,
        "status": status,
        "reason_code": reason,
        "detection_tools": ["Tool A"],
        "prevention_tools": [],
        "response_tools": ["Tool A"],
        "rationale": f"{status} {reason}",
    }


def _run_twice_suggested(app_client, first: dict, second: dict) -> tuple[dict, dict]:  # noqa: F811
    c, TestSession, provider = app_client
    h, svc_id, row_id, code = _one_row_run_with_reason(c, TestSession, provider, "gap", None)
    provider.register_static(
        "mitre_map",
        LLMResponse(
            json.dumps(
                {
                    "techniques": [
                        first | {"technique_code": code},
                        second | {"technique_code": code},
                    ]
                }
            )
        ),
    )
    result = attack_run_ai(c, svc_id, h)
    row = next(t for t in result["coverage"] if t["id"] == row_id)
    return result, row


_REFUSED = _suggestion("", "partial", "reach_limited")
_APPLIED = _suggestion("", "partial", "prevention_limited")


@pytest.mark.parametrize(
    ("first", "second"),
    [(_REFUSED, _APPLIED), (_APPLIED, _REFUSED)],
    ids=["refused-then-applied", "applied-then-refused"],
)
def test_a_forbidden_reason_refusal_is_not_counted_when_the_run_applied_the_technique(
    app_client, first, second  # noqa: F811
) -> None:
    c, TestSession, _ = app_client
    result, row = _run_twice_suggested(app_client, first, second)
    # The applied suggestion landed: the row did NOT keep the status it had.
    assert (row["status"], row["reason_code"]) == ("partial", "prevention_limited")
    # The refusal itself is still recorded in the audit row.
    assert _run_audit(TestSession)["reason_codes_rejected"], "the refusal was not recorded"
    assert result["forbidden_reason_refused"] == 0


_NA = _suggestion("", "not_applicable", "platform_absent")
_GAP = _suggestion("", "gap", None)


@pytest.mark.parametrize(
    ("first", "second"),
    [(_NA, _GAP), (_GAP, _NA)],
    ids=["refused-then-applied", "applied-then-refused"],
)
def test_an_na_refusal_is_not_counted_when_the_run_applied_the_technique(
    app_client, first, second  # noqa: F811
) -> None:
    c, TestSession, _ = app_client
    result, row = _run_twice_suggested(app_client, first, second)
    assert (row["status"], row["rationale"]) == ("gap", "gap None")
    assert _run_audit(TestSession)["statuses_rejected"], "the refusal was not recorded"
    assert result["not_applicable_refused"] == 0
