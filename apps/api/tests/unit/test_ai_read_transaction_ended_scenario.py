"""#1025 holder 2, the ATT&CK what-if: its run (#1025) and its parse route
(#1027) hold no pooled connection while the provider is called (see
`test_ai_read_transaction_ended.py`); each 1 with its line removed."""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse
from tests._pool_count import sampling_provider_calls
from tests.unit.test_ai_runs_attack import (  # noqa: F401  (app_parts: fixture)
    LiveLookingProvider,
    app_parts,
)
from tests.unit.test_attack_scenario_routes import EDR, _flags, _run_to_completion, _world

pytestmark = pytest.mark.unit


def test_the_what_if_run_holds_no_connection_during_any_call(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    from app.routes import attack_scenarios
    from tests.unit.test_attack_scenario_routes import SIEM

    # One batch at a time, so a sample never counts a sibling batch's own
    # short ledger session mid-commit.
    monkeypatch.setattr(attack_scenarios, "_MAX_WORKERS", 1)
    w = _world(app_parts)
    w.answer({w.a: [_flags(w.a, SIEM, d=True)]})
    r = w.create([EDR])
    assert r.status_code == 201, r.text
    with sampling_provider_calls(monkeypatch) as samples:
        body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "completed", body["run_error"]
    assert samples and set(samples) == {0}, samples


def test_the_what_if_parse_holds_no_connection_during_its_call(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    from app.attack import scenario_intent
    from tests.unit.test_attack_scenario_intent_routes import VAGUE

    w = _world(app_parts)
    provider = LiveLookingProvider()
    provider.register(
        scenario_intent.PURPOSE,
        lambda _p: LLMResponse(json.dumps({"remove": [EDR], "add": [], "unclear": []})),
    )
    w.use(provider)
    with sampling_provider_calls(monkeypatch) as samples:
        r = w.c.post(
            f"/attack/services/{w.svc_id}/scenarios/parse",
            headers=w.h,
            json={"text": VAGUE, "serves": "live"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "ai", r.json()
    assert samples and set(samples) == {0}, samples
