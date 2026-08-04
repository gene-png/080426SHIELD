"""Settings safety checks."""

from __future__ import annotations

import pytest

from app import config
from app.config import Settings


@pytest.mark.unit
def test_production_rejects_redaction_off() -> None:
    s = Settings(environment="production", shield_redaction_mode="off", jwt_signing_secret="x" * 64)
    with pytest.raises(RuntimeError, match="SHIELD_REDACTION_MODE"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_production_rejects_placeholder_jwt_secret() -> None:
    s = Settings(environment="production", shield_redaction_mode="strict")
    with pytest.raises(RuntimeError, match="JWT_SIGNING_SECRET"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_development_permits_loose_config() -> None:
    s = Settings(environment="development", shield_redaction_mode="off")
    s.assert_safe_for_runtime()


# --- Live-mode LLM boot preflight (D-026) --------------------------------------


@pytest.mark.unit
def test_live_mode_missing_anthropic_key_raises_at_boot() -> None:
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="anthropic",
        anthropic_api_key="",
        shield_llm_model="claude-sonnet-5",
    )
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_missing_sdk_raises_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_anthropic_sdk_importable", lambda: False)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="anthropic",
        anthropic_api_key="sk-test",
        shield_llm_model="claude-sonnet-5",
    )
    with pytest.raises(RuntimeError, match="SDK"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_placeholder_model_raises_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_anthropic_sdk_importable", lambda: True)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="anthropic",
        anthropic_api_key="sk-test",
        shield_llm_model="claude-opus-4-7",
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_valid_anthropic_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_anthropic_sdk_importable", lambda: True)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="anthropic",
        anthropic_api_key="sk-test",
        shield_llm_model="claude-sonnet-5",
    )
    s.assert_safe_for_runtime()
    ready, detail = s.live_llm_readiness()
    assert ready is True
    assert "claude-sonnet-5" in detail


@pytest.mark.unit
def test_live_mode_openai_missing_key_raises_at_boot() -> None:
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="openai",
        openai_api_key="",
        shield_llm_model="gpt-5",
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_unimplemented_provider_raises_at_boot() -> None:
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="bedrock",
        shield_llm_model="anything",
    )
    with pytest.raises(RuntimeError, match="no live adapter"):
        s.assert_safe_for_runtime()


# --- Vertex (ADC) live-mode preflight (D-029) ----------------------------------


@pytest.mark.unit
def test_live_mode_vertex_missing_project_raises_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_google_auth_importable", lambda: True)
    monkeypatch.setattr(config, "_adc_resolvable", lambda: True)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-flash",
        gcp_project_id="",
    )
    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_vertex_missing_google_auth_raises_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "_google_auth_importable", lambda: False)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-flash",
        gcp_project_id="kentro-cloudmod-dev",
    )
    with pytest.raises(RuntimeError, match="google-auth"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_vertex_unresolvable_adc_raises_at_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_google_auth_importable", lambda: True)
    monkeypatch.setattr(config, "_adc_resolvable", lambda: False)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-flash",
        gcp_project_id="kentro-cloudmod-dev",
    )
    with pytest.raises(RuntimeError, match="Application Default Credentials"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_live_mode_valid_vertex_boots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "_google_auth_importable", lambda: True)
    monkeypatch.setattr(config, "_adc_resolvable", lambda: True)
    s = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-flash",
        gcp_project_id="kentro-cloudmod-dev",
    )
    s.assert_safe_for_runtime()
    ready, detail = s.live_llm_readiness()
    assert ready is True
    assert "vertex" in detail
    assert "gemini-2.5-flash" in detail


@pytest.mark.unit
def test_fixture_mode_unaffected_by_llm_preflight() -> None:
    # Fixture mode boots even with an empty key and the stale placeholder model.
    s = Settings(
        shield_llm_mode="fixture",
        shield_llm_provider="anthropic",
        anthropic_api_key="",
        shield_llm_model="claude-opus-4-7",
    )
    s.assert_safe_for_runtime()


@pytest.mark.unit
def test_default_model_is_not_the_stale_placeholder() -> None:
    assert Settings().shield_llm_model not in config._KNOWN_PLACEHOLDER_MODELS


# --- OIDC exchange boot preflight (D-032) --------------------------------------


@pytest.mark.unit
def test_oidc_disabled_by_default_and_boots() -> None:
    s = Settings()
    assert s.shield_auth_oidc_enabled is False
    # Flag off: the OIDC readiness gate is not consulted at all, so obviously
    # blank Keycloak settings still boot fine.
    s = Settings(shield_auth_oidc_enabled=False, keycloak_jwks_url="", keycloak_issuer="")
    s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_empty_jwks_url_raises_at_boot() -> None:
    s = Settings(shield_auth_oidc_enabled=True, keycloak_jwks_url="")
    with pytest.raises(RuntimeError, match="KEYCLOAK_JWKS_URL"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_empty_issuer_raises_at_boot() -> None:
    s = Settings(shield_auth_oidc_enabled=True, keycloak_issuer="")
    with pytest.raises(RuntimeError, match="KEYCLOAK_ISSUER"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_non_http_issuer_raises_at_boot() -> None:
    s = Settings(shield_auth_oidc_enabled=True, keycloak_issuer="keycloak/realms/shield")
    with pytest.raises(RuntimeError, match="http"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_empty_audience_raises_at_boot() -> None:
    s = Settings(shield_auth_oidc_enabled=True, keycloak_audience="")
    with pytest.raises(RuntimeError, match="KEYCLOAK_AUDIENCE"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_empty_client_id_raises_at_boot() -> None:
    s = Settings(shield_auth_oidc_enabled=True, keycloak_client_id="")
    with pytest.raises(RuntimeError, match="KEYCLOAK_CLIENT_ID"):
        s.assert_safe_for_runtime()


@pytest.mark.unit
def test_oidc_enabled_with_full_config_boots() -> None:
    s = Settings(shield_auth_oidc_enabled=True)
    s.assert_safe_for_runtime()  # defaults are all non-empty http(s) values
    ready, detail = s.oidc_readiness()
    assert ready is True
    assert "shield" in detail
