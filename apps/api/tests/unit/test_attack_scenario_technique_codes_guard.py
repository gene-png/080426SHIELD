"""#984 / #986: the `technique_codes` guard also covers the what-if scenario job.

`technique_codes` is registered by payload key, so it guards every job that
sends that key, and `app/attack/scenario.py::batch_inputs` sends it from the
scenario's affected codes. A what-if run through its real route must pass the
guard, with the codes reaching the provider exactly as the scenario names them.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import FixtureProvider, LLMResponse
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import EDR, PURPOSE, _world

pytestmark = pytest.mark.unit


def test_a_what_if_run_passes_the_guard_with_its_codes_unchanged(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    sent: list[dict] = []
    provider = FixtureProvider()

    def _record(payload: dict) -> LLMResponse:
        sent.append({k: v for k, v in payload.items() if not k.startswith("__")})
        return LLMResponse(json.dumps({"rows": []}))

    provider.register(PURPOSE, _record)
    w.use(provider)
    created = w.create([EDR]).json()
    affected = created["affected_codes"]
    assert affected, "the what-if must affect techniques for this to test anything"

    r = w.run(created["id"])
    assert r.status_code == 202, r.text
    body = w.get(created["id"])

    assert body["run_status"] == "completed", body
    assert sorted(c for p in sent for c in p["technique_codes"]) == sorted(affected)
