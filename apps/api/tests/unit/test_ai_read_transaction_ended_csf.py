"""#1025 holder 2, the CSF run: no pooled connection is held while the
provider is called (see `test_ai_read_transaction_ended.py`); 1 with
`end_read_transaction(db, where="csf.run_ai")` removed."""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import csf_run_ai
from tests._pool_count import sampling_provider_calls
from tests.unit.test_csf_run_ai import _bootstrap, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_the_csf_run_holds_no_connection_during_any_call(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    from app.routes import csf as csf_routes

    # One batch at a time, so a sample never counts a sibling batch's own
    # short ledger session mid-commit.
    monkeypatch.setattr(csf_routes, "_CSF_MAX_WORKERS", 1)
    c, provider = app_client
    h, svc_id = _bootstrap(c)
    provider.register("csf_score", lambda _p: LLMResponse('{"scores": []}'))
    with sampling_provider_calls(monkeypatch) as samples:
        csf_run_ai(c, svc_id, h)
    assert samples and set(samples) == {0}, samples
