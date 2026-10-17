"""#1025 holder 2, the ZT run: no pooled connection is held while
the provider is called (see `test_ai_read_transaction_ended.py`). It goes to
1 with the run's `end_read_transaction` line removed."""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import zt_run_ai
from tests._pool_count import sampling_provider_calls
from tests._zt_notes import noted_assessment
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_the_zt_run_holds_no_connection_during_its_call(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    c, provider = app_client
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    noted_assessment(c, h, svc_id)
    provider.register("zt_score", lambda _p: LLMResponse('{"capabilities": []}'))
    with sampling_provider_calls(monkeypatch) as samples:
        zt_run_ai(c, svc_id, h)
    assert samples and set(samples) == {0}, samples
