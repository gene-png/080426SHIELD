"""Option 1, code decides what is scored (Gene, #736 6201620727 item 1): a
subcategory whose current answer has blank notes is left out of the
csf_score payload BEFORE egress, in every mode, so the preview is exactly
what egresses.

P1 (#736 6204461502) is Gene's, so both answers are pinned here through
`LEAVE_OUT_EVERY_BLANK_NOTES`:

- True: every blank-notes subcategory is left out, a consultant-scored one
  included.
- False (Q1 (a) read literally): a blank-notes subcategory with a recorded
  value on an in-scope tier is still sent.

Red-on-revert: with the leave-out removed from `_csf_ai_request_for`, the
first test sees all three codes egress and goes red.

Each payload is captured where it reaches the provider, after redaction.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from app.csf.catalog import SUBCATEGORIES
from tests._ai_runs import csf_run_ai
from tests.unit.test_csf_run_ai import _bootstrap, app_client  # noqa: F401

pytestmark = pytest.mark.unit

NOTED = SUBCATEGORIES[0].code
RATED_ONLY = SUBCATEGORIES[1].code
SCORED_BLANK = SUBCATEGORIES[2].code
NOTE = "Access reviews are run quarterly by the IT lead."


def _answer(c, h: dict, svc: str, code: str, body: dict) -> None:
    latest = c.get(f"/csf/services/{svc}/assessments/latest", headers=h).json()
    answer_id = next(a["id"] for a in latest["answers"] if a["subcategory_code"] == code)
    r = c.patch(f"/csf/answers/{answer_id}", headers=h, json=body)
    assert r.status_code == 200, r.text


def _score(c, h: dict, svc: str, code: str) -> None:
    rows = c.get(f"/csf/services/{svc}/profile/high", headers=h).json()["rows"]
    sid = next(r["id"] for r in rows if r["subcategory_code"] == code)
    r = c.patch(f"/csf/dimension-scores/{sid}", headers=h, json={"governance": 2})
    assert r.status_code == 200, r.text


def _world(c) -> tuple[dict, str]:
    """High seeded; one code with notes, one with a rating only, one with no
    notes but a consultant's score on its tier."""
    h, svc = _bootstrap(c)
    _answer(c, h, svc, NOTED, {"maturity_tier": 2, "notes": NOTE})
    _answer(c, h, svc, RATED_ONLY, {"maturity_tier": 3})
    _score(c, h, svc, SCORED_BLANK)
    return h, svc


def _capture(provider) -> list[dict]:
    sent: list[dict] = []

    def _answer_nothing(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"scores": []}')

    provider.register("csf_score", _answer_nothing)
    return sent


def _sent_codes(sent: list[dict]) -> set[str]:
    return {code for p in sent for code in p["subcategories"]}


def _answer_codes(sent: list[dict]) -> set[str]:
    return {code for p in sent for code in p["answers"]}


def test_only_subcategories_with_notes_egress(app_client) -> None:  # noqa: F811
    c, provider = app_client
    h, svc = _world(c)
    sent = _capture(provider)
    body = csf_run_ai(c, svc, h)
    assert sent, "a code with notes is sent"  # positive first
    assert _sent_codes(sent) == {NOTED}, _sent_codes(sent)
    assert _answer_codes(sent) == {NOTED}, _answer_codes(sent)
    # C4's count: every high row left out, i.e. all but the one sent.
    assert body["no_notes_count"] == len(SUBCATEGORIES) - 1, body["no_notes_count"]


def test_the_preview_shows_the_same_leave_out(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    h, svc = _world(c)
    r = c.post("/ai/preview", json={"service_id": svc}, headers=h)
    assert r.status_code == 200, r.text
    payload = r.json()["payload"]
    assert payload["subcategories"] == [NOTED], payload["subcategories"]
    assert set(payload["answers"]) == {NOTED}
    assert set(payload["subcategory_definitions"]) == {NOTED}


def test_the_literal_q1a_predicate_still_sends_a_scored_blank_subcategory(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.routes.csf.LEAVE_OUT_EVERY_BLANK_NOTES", False)
    c, provider = app_client
    h, svc = _world(c)
    sent = _capture(provider)
    csf_run_ai(c, svc, h)
    assert _sent_codes(sent) == {NOTED, SCORED_BLANK}, _sent_codes(sent)
    assert RATED_ONLY not in _answer_codes(sent)


def test_nothing_to_send_makes_no_call(app_client) -> None:  # noqa: F811
    c, provider = app_client
    h, svc = _bootstrap(c)
    _answer(c, h, svc, RATED_ONLY, {"maturity_tier": 3})
    sent = _capture(provider)
    body = csf_run_ai(c, svc, h)
    assert sent == [], "no subcategory has notes, so nothing egresses"
    assert (body["batches_total"], body["suggestions_received"]) == (0, 0), body
    assert body["no_notes_count"] == len(SUBCATEGORIES), body["no_notes_count"]
