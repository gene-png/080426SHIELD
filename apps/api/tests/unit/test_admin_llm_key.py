"""Runtime LLM API-key management (issue 2).

Before this, the only way to give SHIELD a provider key was an environment
variable read once at boot through the ``lru_cache``d ``get_settings()``. An
admin had no way to see that AI was offline, and no way to fix it without a
redeploy. This pins the replacement contract:

  * ``POST   /admin/llm-key``  validate, then store the key ENCRYPTED
  * ``DELETE /admin/llm-key``  remove it and fall back to fixture mode
  * ``GET    /admin/ai-status`` reports readiness AND where the key came from

Two rules the tests below exist to enforce:

1. **A bad key is refused, never stored.** The key is validated against the
   provider first; a rejected key leaves the previous state untouched, so a
   typo can't silently take AI offline (FAIL LOUDLY).
2. **The key is never readable back.** No endpoint returns it, and the stored
   column holds ciphertext, not the key.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

PASSWORD = "correct horse battery staple!"
GOOD_KEY = "sk-ant-test-valid-key-000000000000"
BAD_KEY = "sk-ant-test-rejected-key-00000000"


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-llmkey.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    # Pin the provider/model rather than inheriting the developer's .env — a
    # placeholder SHIELD_LLM_MODEL there would otherwise make readiness fail
    # for a reason this spec isn't about.
    os.environ["SHIELD_LLM_PROVIDER"] = "anthropic"
    os.environ["SHIELD_LLM_MODEL"] = "claude-opus-5"

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
