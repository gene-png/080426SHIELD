"""#508: `/ready`'s LLM check says what `/admin/ai-status` says.

`_probe_llm` read `SHIELD_LLM_MODE` alone, so with a key an admin had stored
(`POST /admin/llm-key`) it reported "fixture mode (AI suggestions are
deterministic offline)" while every Run-AI called the provider with the
client's data (D-037, #755). It now CALLS `_ai_readiness`, the function
`/admin/ai-status` calls, so the two cannot disagree. Each test reads both.
"""

from __future__ import annotations

import pytest

from tests.unit.test_admin_llm_key import (  # noqa: F401  (fixture)
    GOOD_KEY,
    _admin,
    _pin,
    _status,
    app_client,
)

pytestmark = pytest.mark.unit


def _llm_check(c, headers: dict) -> dict:
    r = c.get("/ready", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["checks"]["llm"]


def test_no_key_in_fixture_mode_reads_as_ai_status_does(app_client) -> None:  # noqa: F811
    c, _ = app_client
    h = _admin(c)
    status = _status(c, h)
    assert status["serves"] == "offline"
    check = _llm_check(c, h)
    assert check["detail"] == status["detail"]
    assert (check["status"], check["required"]) == ("ok", False)


def test_a_stored_key_in_fixture_mode_is_reported_live_not_offline(
    app_client,  # noqa: F811
) -> None:
    """The #755 trap: a stored key makes every Run-AI call the provider, even
    with SHIELD_LLM_MODE=fixture. The operator must not be told "offline"."""
    c, _ = app_client
    h = _admin(c)
    r = c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    assert r.status_code == 200, r.text
    status = _status(c, h)
    assert status["serves"] == "live"
    check = _llm_check(c, h)
    assert check["detail"] == status["detail"]
    assert "offline" not in check["detail"].lower()
    assert "fixture mode" not in check["detail"].lower()
    assert check["status"] == "ok"


def test_a_broken_configuration_is_down(app_client, monkeypatch) -> None:  # noqa: F811
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_mode="live")
    status = _status(c, h)
    assert status["serves"] == "broken"
    check = _llm_check(c, h)
    assert check["detail"] == status["detail"]
    assert check["status"] == "down"
    assert check["required"] is False  # informational, as before


def test_an_unreadable_configuration_is_down_and_never_offline(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """`/ready` must answer while the database it reports on is down, and the
    keystore lives in it. Could not look is not "offline"."""
    import app.routes.admin as admin_mod

    c, _ = app_client
    h = _admin(c)

    def _unreadable(db, s):  # noqa: ANN001, ANN202
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(admin_mod, "_ai_readiness", _unreadable)
    check = _llm_check(c, h)
    assert check["status"] == "down"
    assert check["detail"].startswith("unknown — could not read the AI configuration")
    assert "offline" not in check["detail"].lower()
