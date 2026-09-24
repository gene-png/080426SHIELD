"""Runtime LLM API-key management (issue 2).

Before this, the only way to give SHIELD a provider key was an environment
variable read once at boot through the ``lru_cache``d ``get_settings()``. An
admin had no way to see that AI was offline, and no way to fix it without a
redeploy. This pins the replacement contract:

  * ``POST   /admin/llm-key``  validate, then store the key ENCRYPTED
  * ``DELETE /admin/llm-key``  remove it; AI falls back to the environment key
    if there is one (still live in live mode), else to fixture output (#472)
  * ``GET    /admin/ai-status`` reports readiness AND where the key came from

Two rules the tests below exist to enforce:

1. **A bad key is refused, never stored.** The key is validated against the
   provider first; a rejected key leaves the previous state untouched, so a
   typo can't silently take AI offline (FAIL LOUDLY).
2. **The key is never readable back.** No endpoint returns it, and the stored
   column holds ciphertext, not the key.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

#: Every test here is a unit test. Without this, `pytest -m unit` -- CI's
#: command -- deselected the whole file, and five of its tests had been failing
#: on any machine with an Anthropic key in its environment without CI noticing.
pytestmark = pytest.mark.unit

PASSWORD = "correct horse battery staple!"
GOOD_KEY = "sk-ant-test-valid-key-000000000000"
BAD_KEY = "sk-ant-test-rejected-key-00000000"


@pytest.fixture()
def app_client(tmp_path, monkeypatch) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-llmkey.db"
    url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", url)
    # Pin the provider/model rather than inheriting the developer's .env — a
    # placeholder SHIELD_LLM_MODEL there would otherwise make readiness fail
    # for a reason this spec isn't about.
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-opus-5")
    # Pin the mode and the ENVIRONMENT key too. A developer's .env carries a
    # real ANTHROPIC_API_KEY, which made `key_source` read "environment" and
    # failed every test asserting "none" -- ambient config, not the code.
    monkeypatch.setenv("SHIELD_LLM_MODE", "fixture")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    from app.config import get_settings as _get_settings

    _get_settings.cache_clear()
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.ai.keystore import get_key_validator
    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def fake_validator():
        # Never touch the network in unit tests: GOOD_KEY passes, everything
        # else is rejected the way a real provider 401 would be.
        def _validate(provider: str, model: str, api_key: str) -> tuple[bool, str]:
            if api_key == GOOD_KEY:
                return True, f"Validated against {provider}/{model}."
            return False, "The provider rejected this key (401)."

        return _validate

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_key_validator] = fake_validator
    with TestClient(app) as c:
        yield c, TestSession
    # Don't leak the pinned settings into other modules' tests.
    _get_settings.cache_clear()


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _admin(c: TestClient) -> dict[str, str]:
    bearer = _register(c, "admin@kentro.example")["tokens"]["access_token"]
    return {"Authorization": f"Bearer {bearer}"}


def _status(c: TestClient, headers: dict[str, str]) -> dict:
    r = c.get("/admin/ai-status", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_status_reports_no_key_and_that_it_can_be_configured(app_client):
    c, _ = app_client
    h = _admin(c)
    body = _status(c, h)
    assert body["ready"] is False
    assert body["can_configure"] is True, "the UI needs to know a key can be pasted"
    assert body["key_source"] == "none"
    assert "api_key" not in body and "key" not in body


def test_storing_a_valid_key_makes_ai_ready_and_records_the_source(app_client):
    c, _ = app_client
    h = _admin(c)

    r = c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    assert r.status_code == 200, r.text
    assert r.json()["ready"] is True
    assert r.json()["key_source"] == "database"

    # Survives a fresh read — it is persisted, not just cached in-process.
    assert _status(c, h)["ready"] is True


def test_a_rejected_key_is_refused_and_never_stored(app_client):
    c, _ = app_client
    h = _admin(c)

    r = c.post("/admin/llm-key", headers=h, json={"api_key": BAD_KEY})
    assert r.status_code == 400, r.text
    err = r.json()["error"]
    assert err["reason"] == "llm_key_rejected"
    assert "rejected" in err["message"].lower()

    # State is untouched: still offline, still no stored key.
    body = _status(c, h)
    assert body["ready"] is False
    assert body["key_source"] == "none"


def test_a_valid_key_is_not_stored_in_plaintext(app_client):
    c, TestSession = app_client
    h = _admin(c)
    assert c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY}).status_code == 200

    with TestSession() as db:
        rows = db.execute(text("SELECT encrypted_key FROM llm_credential")).scalars().all()
    assert rows, "a credential row should exist"
    for stored in rows:
        assert GOOD_KEY not in stored, "the API key must be encrypted at rest"


def test_the_key_is_never_returned_by_any_admin_endpoint(app_client):
    c, _ = app_client
    h = _admin(c)
    c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})

    for path in ("/admin/ai-status", "/admin/audit-entries"):
        r = c.get(path, headers=h)
        assert r.status_code == 200, r.text
        assert GOOD_KEY not in r.text, f"{path} leaked the API key"


def test_deleting_the_key_takes_ai_back_offline(app_client):
    c, _ = app_client
    h = _admin(c)
    c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    assert _status(c, h)["ready"] is True

    r = c.delete("/admin/llm-key", headers=h)
    assert r.status_code == 204, r.text

    body = _status(c, h)
    assert body["ready"] is False, "removing the key must take AI offline immediately"
    assert body["key_source"] == "none"
    assert body["can_configure"] is True


def test_key_changes_are_audited_without_recording_the_key(app_client):
    c, _ = app_client
    h = _admin(c)
    c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    c.delete("/admin/llm-key", headers=h)

    r = c.get("/admin/audit-entries", headers=h)
    actions = [e["action"] for e in r.json()["entries"]]
    assert "llm.key_set" in actions
    assert "llm.key_removed" in actions
    assert GOOD_KEY not in r.text


def test_non_admin_cannot_set_or_remove_the_key(app_client):
    c, _ = app_client
    admin = _admin(c)
    outsider = {
        "Authorization": "Bearer " + _register(c, "someone@atlas.example")["tokens"]["access_token"]
    }

    assert c.post("/admin/llm-key", headers=outsider, json={"api_key": GOOD_KEY}).status_code in (
        401,
        403,
    )
    assert c.delete("/admin/llm-key", headers=outsider).status_code in (401, 403)
    assert _status(c, admin)["key_source"] == "none"


def test_an_empty_key_is_rejected_before_any_provider_call(app_client):
    c, _ = app_client
    h = _admin(c)
    r = c.post("/admin/llm-key", headers=h, json={"api_key": "   "})
    assert r.status_code in (400, 422)
    assert _status(c, h)["key_source"] == "none"


# --- #472: readiness asks the provider, not the keystore -------------------
#
# `_ai_readiness` decided "configured" by asking whether an API key existed. A
# Vertex deployment authenticates with ADC and has no key, so a WORKING live
# deployment reported "No API key is loaded -- AI steps will generate offline
# (fixture) responses", and the Run-AI guard offered "Continue offline" over a
# call that went to Google with the client's data. The status now comes from
# the provider Run-AI would actually build, and says which of three things a
# Run-AI will do: `live`, `offline` (canned fixtures), or `broken` (fail).


def _pin(monkeypatch, **attrs) -> None:
    from app.config import get_settings

    for name, value in attrs.items():
        monkeypatch.setattr(get_settings(), name, value, raising=False)


def _store_raw_key(session_factory, provider: str) -> None:
    """Store a key WITHOUT the validator, for states no validator admits."""
    from app.ai import keystore

    db = session_factory()
    try:
        keystore.store_key(db, provider=provider, api_key=GOOD_KEY, actor_user_id=None)
        db.commit()
    finally:
        db.close()


def test_a_live_vertex_deployment_reports_live_not_offline(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    _pin(
        monkeypatch,
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-pro",
        gcp_project_id="shield-test-project",
    )
    body = _status(c, h)
    assert body["serves"] == "live", body
    assert body["ready"] is True, body["detail"]
    assert "offline" not in body["detail"].lower()


def _adc(monkeypatch, resolvable: bool) -> None:
    import app.config as config_mod

    monkeypatch.setattr(config_mod, "_google_auth_importable", lambda: True)
    monkeypatch.setattr(config_mod, "_adc_resolvable", lambda: resolvable)


def test_vertex_in_fixture_mode_is_offline_and_does_not_prescribe_a_key(app_client, monkeypatch):
    # "Load a key" names a control that cannot work for vertex -- it has no
    # key, and the validator refuses one -- so the remedy is the mode.
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider="vertex", gcp_project_id="shield-test-project")
    _adc(monkeypatch, resolvable=True)
    body = _status(c, h)
    assert body["serves"] == "offline", body
    assert body["ready"] is False
    assert "load a key" not in body["detail"].lower(), body["detail"]
    assert "SHIELD_LLM_MODE=live" in body["detail"]


def test_a_stored_key_on_vertex_reports_broken_with_the_real_cause(app_client, monkeypatch):
    c, sessions = app_client
    h = _admin(c)
    _pin(
        monkeypatch,
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        gcp_project_id="shield-test-project",
    )
    _store_raw_key(sessions, "vertex")
    body = _status(c, h)
    assert body["serves"] == "broken", body
    assert body["ready"] is False
    assert "Run-AI will fail" in body["detail"], body["detail"]
    assert "no key-based adapter" in body["detail"], body["detail"]


def test_live_mode_with_no_key_is_broken_not_offline(app_client, monkeypatch):
    # The old copy said "AI steps will generate offline (fixture) responses"
    # here. In live mode nothing falls back to fixtures: the call fails.
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_mode="live")
    body = _status(c, h)
    assert body["serves"] == "broken", body
    assert "offline" not in body["detail"].lower(), body["detail"]


def test_no_key_in_fixture_mode_is_offline(app_client):
    c, _ = app_client
    h = _admin(c)
    body = _status(c, h)
    assert body["serves"] == "offline", body
    assert "No API key is loaded" in body["detail"]


def test_an_environment_key_in_fixture_mode_is_offline(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, anthropic_api_key="sk-ant-env-key-0000000000000000")
    body = _status(c, h)
    assert body["key_source"] == "environment"
    assert body["serves"] == "offline", body


def test_a_stored_valid_key_is_live(app_client):
    c, _ = app_client
    h = _admin(c)
    r = c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    assert r.json()["serves"] == "live", r.json()
    assert _status(c, h)["serves"] == "live"


def test_a_placeholder_model_is_broken(app_client, monkeypatch):
    c, sessions = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_model="claude-opus-4-7")
    _store_raw_key(sessions, "anthropic")
    body = _status(c, h)
    assert body["serves"] == "broken", body
    assert "usable model id" in body["detail"]


# --- #472 round 1: "can a key be loaded HERE" is not "does it use a key" ---
#
# The first cut asked "does this provider use an API key" and treated every
# "no" as "keyless, so set the mode live". For a provider with NO live adapter
# that advice stops the api booting; for openai and gemini, which do use a key,
# "Load a key" named a control that refuses them (`live_validate_key` admits
# anthropic alone).


@pytest.mark.parametrize("provider", ["azure_openai", "bedrock", "local"])
def test_a_provider_with_no_live_adapter_is_not_told_to_go_live(app_client, monkeypatch, provider):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider=provider)
    body = _status(c, h)
    assert body["serves"] == "offline", body
    assert "SHIELD_LLM_MODE=live" not in body["detail"], body["detail"]
    assert "load a key" not in body["detail"].lower(), body["detail"]
    assert "no live adapter" in body["detail"], body["detail"]
    assert body["can_configure"] is False


@pytest.mark.parametrize(
    ("provider", "env_var"), [("openai", "OPENAI_API_KEY"), ("gemini", "GEMINI_API_KEY")]
)
def test_a_key_provider_that_cannot_take_a_key_here_is_pointed_at_the_environment(
    app_client, monkeypatch, provider, env_var
):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider=provider)
    body = _status(c, h)
    assert body["serves"] == "offline", body
    assert "load a key" not in body["detail"].lower(), body["detail"]
    assert env_var in body["detail"], body["detail"]
    assert body["can_configure"] is False


def test_an_environment_key_that_cannot_be_replaced_here_is_not_offered_a_paste(
    app_client, monkeypatch
):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider="openai", openai_api_key="sk-openai-env-0000")
    body = _status(c, h)
    assert body["key_source"] == "environment"
    assert body["serves"] == "offline", body
    assert "load a key" not in body["detail"].lower(), body["detail"]


def test_only_a_provider_whose_key_can_be_validated_here_can_be_configured(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    assert _status(c, h)["can_configure"] is True  # anthropic, the fixture's pin
    _pin(monkeypatch, shield_llm_provider="vertex", gcp_project_id="shield-test-project")
    assert _status(c, h)["can_configure"] is False


# --- #472 round 2: "set SHIELD_LLM_MODE=live" is advice only if live would BOOT
#
# Round 1 prescribed the mode for vertex from a hand summary. The boot
# preflight (`live_llm_readiness`) also wants a project, google-auth and
# resolvable ADC, and refuses to START the api without them -- so following the
# advice took the whole platform down, not just AI. The remedy now asks the
# preflight itself.


def test_vertex_without_a_project_is_told_what_live_mode_is_missing(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider="vertex", gcp_project_id="")
    _adc(monkeypatch, resolvable=True)
    body = _status(c, h)
    assert body["serves"] == "offline", body
    assert "GCP_PROJECT_ID" in body["detail"], body["detail"]
    assert "would not start" in body["detail"], body["detail"]


def test_vertex_without_resolvable_credentials_is_told_so(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider="vertex", gcp_project_id="shield-test-project")
    _adc(monkeypatch, resolvable=False)
    body = _status(c, h)
    assert "Application Default Credentials" in body["detail"], body["detail"]
    assert "would not start" in body["detail"], body["detail"]


def test_vertex_that_would_boot_is_told_plainly_to_go_live(app_client, monkeypatch):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider="vertex", gcp_project_id="shield-test-project")
    _adc(monkeypatch, resolvable=True)
    body = _status(c, h)
    assert "would not start" not in body["detail"], body["detail"]
    assert "Set SHIELD_LLM_MODE=live and restart the api." in body["detail"], body["detail"]


def test_an_environment_key_with_a_placeholder_model_is_not_told_to_go_live_blind(
    app_client, monkeypatch
):
    c, _ = app_client
    h = _admin(c)
    _pin(
        monkeypatch,
        anthropic_api_key="sk-ant-env-key-0000000000000000",
        shield_llm_model="claude-opus-4-7",
    )
    body = _status(c, h)
    assert body["key_source"] == "environment"
    assert "would not start" in body["detail"], body["detail"]
    assert "claude-opus-4-7" in body["detail"], body["detail"]


@pytest.mark.parametrize(
    ("provider", "project"), [("vertex", "shield-test-project"), ("bedrock", "")]
)
def test_a_provider_with_no_key_does_not_lead_with_a_missing_key(
    app_client, monkeypatch, provider, project
):
    c, _ = app_client
    h = _admin(c)
    _pin(monkeypatch, shield_llm_provider=provider, gcp_project_id=project)
    _adc(monkeypatch, resolvable=True)
    body = _status(c, h)
    assert not body["detail"].startswith("No API key is loaded"), body["detail"]
