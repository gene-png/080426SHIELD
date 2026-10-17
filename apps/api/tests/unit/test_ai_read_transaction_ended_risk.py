"""#1025 holder 2, #1026: Risk generate is synchronous, and its REQUEST
session read the inputs before the batch workers call the provider. It holds
no pooled connection while they do (see `test_ai_read_transaction_ended.py`);
1 with `end_read_transaction(db, where="risk.generate")` removed."""

from __future__ import annotations

import pytest

from tests._pool_count import sampling_provider_calls
from tests.unit.test_risk_dashboard import (  # noqa: F401  (fixture)
    _register,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit


def test_risk_generate_holds_no_connection_while_its_workers_call(
    app_client, monkeypatch  # noqa: F811
) -> None:
    from app.routes import risk as risk_routes

    # One batch at a time, so a sample never counts a sibling worker's
    # session mid-commit.
    monkeypatch.setattr(risk_routes, "_RISK_MAX_WORKERS", 1)
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    cid = client["user"]["client_id"]
    c.headers["X-Client-Id"] = cid
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    _seed_attack_and_zt(c, bearer, cid)
    with sampling_provider_calls(monkeypatch) as samples:
        r = c.post(f"/risk/clients/{cid}/register/generate", headers=h)
    assert r.status_code == 201, r.text
    assert samples and set(samples) == {0}, samples
