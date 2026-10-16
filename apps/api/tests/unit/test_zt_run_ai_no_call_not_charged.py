"""#1219: a LIVE ZT run that sent nothing made no provider call, so its run
says "not charged" (`charged_likely` False), never "not known" (None).

#1084 skips the call when every capability is blank. With no `llm_calls`
row, the framework could only answer None for a live run, which the
workspace prints on a failed run as "It may have made a live AI call, which
the provider may charge for". The job knows it called nothing, and says so.

Driven through `POST /zt/services/{id}/run-ai` with a provider presenting
as live, as `test_zt_run_ai.py`'s live tests do.
"""

from __future__ import annotations

import pytest

from tests._ai_runs import get_run, start_run
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _live_blank_service(c, provider, monkeypatch) -> tuple[dict, str]:
    monkeypatch.setattr(type(provider), "name", "anthropic", raising=False)
    h, svc_id, _ = _admin_service(c, "zero_trust_cisa")
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    # Every row is created blank, so nothing would be sent.
    assert all(not (x["notes"] or "").strip() for x in a.json()["answers"])
    return h, svc_id


def test_a_completed_live_run_that_sent_nothing_was_not_charged(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """Red before #1219: a completed live no-call run stored None."""
    c, provider = app_client
    h, svc_id = _live_blank_service(c, provider, monkeypatch)

    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h, serves="live")
    run = get_run(c, started["run_id"], h)

    assert run["status"] == "completed", run
    assert run["result"]["capabilities_sent"] == 0, run["result"]
    assert run["charged_likely"] is False, run


def test_a_live_run_that_sent_nothing_and_then_failed_was_not_charged(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The failure the workspace prints the charge sentence for. The run
    crashes in its apply, after the no-call branch.

    Red before #1219: the failed run stored None, read as "may have made a
    live AI call"."""
    import app.routes.zt as zt_routes

    c, provider = app_client
    h, svc_id = _live_blank_service(c, provider, monkeypatch)

    def _crash(**_: object) -> list:
        raise RuntimeError("apply failed after the no-call branch")

    monkeypatch.setattr(zt_routes, "_zt_omitted", _crash)

    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h, serves="live")
    run = get_run(c, started["run_id"], h)

    assert run["status"] == "failed", run
    assert run["charged_likely"] is False, run


def test_a_live_run_that_called_the_provider_is_still_charged(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The other half: a row with notes is sent, the call is made, and the
    run is charged as before. The declaration must not leak to it."""
    from app.ai.llm import LLMResponse

    c, provider = app_client
    h, svc_id = _live_blank_service(c, provider, monkeypatch)
    ans = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=h).json()["answers"][0]
    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"notes": "MFA everywhere."})
    assert r.status_code == 200, r.text
    provider.register_static("zt_score", LLMResponse('{"capabilities": []}'))

    started = start_run(c, f"/zt/services/{svc_id}/run-ai", h, serves="live")
    run = get_run(c, started["run_id"], h)

    assert run["status"] == "completed", run
    assert run["result"]["capabilities_sent"] == 1, run["result"]
    assert run["charged_likely"] is True, run
