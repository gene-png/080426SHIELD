"""Multi-provider LLM egress adapters (T6, Sprint 4).

These tests exercise the OpenAI and Gemini adapters that live BELOW the egress
seam in ``app.ai.llm``. The seam contract (redaction, the ``llm_calls`` audit
row, "AI suggests, code computes") is tested elsewhere and is untouched here —
these cases only assert that each adapter:

  * is selected by ``_build_provider`` on ``SHIELD_LLM_PROVIDER`` in live mode,
  * translates prompt + redacted payload into the provider's REST request shape,
  * parses the provider response body into ``LLMResponse`` (text + token counts),
  * raises loudly at construction when its API key is missing,
  * surfaces an HTTP error as a failed ``llm_calls`` row.

NO live network calls: ``httpx.Client`` is monkeypatched throughout.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import ai
from app.ai import llm as llm_mod
from app.ai.llm import (
    GeminiProvider,
    LLMClient,
    OpenAIProvider,
    VertexProvider,
    _build_provider,
)
from app.config import Settings
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus
from app.models.user import User, UserRole

# --------------------------------------------------------------------------- #
# httpx fake — captures the outgoing request and returns a canned response.
# --------------------------------------------------------------------------- #


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("POST", "https://example.test"),
                response=httpx.Response(self.status_code),
            )


class _FakeClient:
    """Stand-in for ``httpx.Client`` used as a context manager.

    Records the single POST it receives into ``captured`` and returns the
    ``response`` it was primed with.
    """

    def __init__(self, response: _FakeResponse, captured: dict) -> None:
        self._response = response
        self._captured = captured

    def __call__(self, *args, **kwargs) -> _FakeClient:
        # ``httpx.Client(timeout=...)`` — swallow constructor kwargs.
        return self

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def post(self, url, *, headers=None, json=None, params=None, **kwargs) -> _FakeResponse:
        self._captured["url"] = url
        self._captured["headers"] = headers or {}
        self._captured["json"] = json
        self._captured["params"] = params or {}
        return self._response


def _install_fake_httpx(monkeypatch, response: _FakeResponse) -> dict:
    captured: dict = {}
    fake = _FakeClient(response, captured)
    monkeypatch.setattr(llm_mod.httpx, "Client", fake)
    return captured


# --------------------------------------------------------------------------- #
# DB fixture (mirrors test_llm_client.py) for the failure-row test.
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db_factory(tmp_path) -> Iterator[sessionmaker]:
    db_path = tmp_path / "shield-providers.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _new_admin(db: Session) -> User:
    u = User(
        email="admin@example.com",
        password_hash="x" * 64,
        role=UserRole.ADMIN,
        display_name="Admin",
    )
    db.add(u)
    db.flush()
    return u


# --------------------------------------------------------------------------- #
# OpenAI adapter
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_openai_request_shape_and_response_parsing(monkeypatch) -> None:
    captured = _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "drafted narrative"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 7},
            },
        ),
    )
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    resp = provider.complete(
        "Draft the summary.",
        {"framework": "csf", "step": 3, "__purpose__": "csf.narrative"},
    )

    assert resp.content == "drafted narrative"
    assert resp.input_tokens == 42
    assert resp.output_tokens == 7

    # Request shape: bearer auth, model, max tokens, redacted payload embedded.
    assert "chat/completions" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    body = captured["json"]
    assert body["model"] == "gpt-4o-mini"
    # gpt-4o is a legacy chat model — it still takes the classic max_tokens key.
    assert body["max_tokens"] >= 1
    assert "max_completion_tokens" not in body
    blob = json.dumps(body["messages"])
    assert "Draft the summary." in blob
    assert "framework" in blob and "csf" in blob
    # Internal control keys are stripped before egress — never sent to the model.
    assert "__purpose__" not in blob


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    ["o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o4-mini", "gpt-5", "gpt-5-mini"],
)
def test_openai_reasoning_models_use_max_completion_tokens(monkeypatch, model) -> None:
    # Reasoning / `responses` families (o-series, gpt-5) REJECT the legacy
    # max_tokens key with a 400; they require max_completion_tokens (D-024/T6).
    captured = _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "choices": [{"message": {"content": "reasoned draft"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 3},
            },
        ),
    )
    provider = OpenAIProvider(model=model, api_key="sk-test")
    resp = provider.complete("Draft the summary.", {"framework": "csf"})

    assert resp.content == "reasoned draft"
    body = captured["json"]
    assert body["model"] == model
    assert body["max_completion_tokens"] >= 1
    assert "max_tokens" not in body


@pytest.mark.unit
def test_openai_missing_key_raises_loudly() -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIProvider(model="gpt-4o-mini", api_key="")


@pytest.mark.unit
def test_openai_selected_by_build_provider() -> None:
    settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="openai",
        shield_llm_model="gpt-4o-mini",
        openai_api_key="sk-test",
    )
    provider = _build_provider(settings)
    assert isinstance(provider, OpenAIProvider)
    assert provider.name == "openai"
    assert provider.model == "gpt-4o-mini"


# --------------------------------------------------------------------------- #
# Gemini adapter
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_gemini_request_shape_and_response_parsing(monkeypatch) -> None:
    captured = _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "candidates": [{"content": {"parts": [{"text": "gemini "}, {"text": "draft"}]}}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 9},
            },
        ),
    )
    provider = GeminiProvider(model="gemini-1.5-pro", api_key="g-test")
    resp = provider.complete(
        "Draft the summary.", {"framework": "ztmm", "__purpose__": "zt.narrative"}
    )

    assert resp.content == "gemini draft"
    assert resp.input_tokens == 100
    assert resp.output_tokens == 9

    # Request shape: model in the generateContent path; the API key travels in
    # the x-goog-api-key HEADER, NOT the URL/query — so it can never leak into an
    # HTTPStatusError message (see test_gemini_http_error_does_not_leak_key).
    assert "gemini-1.5-pro:generateContent" in captured["url"]
    assert "g-test" not in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "g-test"
    assert "key" not in captured["params"]
    blob = json.dumps(captured["json"])
    assert "Draft the summary." in blob
    assert "ztmm" in blob
    # Internal control keys are stripped before egress — never sent to the model.
    assert "__purpose__" not in blob


@pytest.mark.unit
def test_generate_content_body_gives_thinking_models_output_headroom() -> None:
    """gemini-2.5 'thinking' models spend part of maxOutputTokens on hidden
    reasoning; a 4096 cap truncated the longer csf/risk drafts mid-JSON in the
    2026-07-15 Vertex live sweep. The shared body must request enough headroom
    that the visible answer survives."""
    body = llm_mod._generate_content_body("Draft it.", {"k": "v"})
    assert body["generationConfig"]["maxOutputTokens"] >= 8192


@pytest.mark.unit
def test_generate_content_body_bounds_thinking_for_2_5_models() -> None:
    """gemini-2.5 'thinking' spends output budget on hidden reasoning that varies
    run-to-run; unbounded, it truncated zt_score even at the raised 8192 cap
    (2026-07-15 sweep). The body must cap the thinking budget for 2.5 models so
    the visible answer always has room — while leaving the API-key gemini-1.5
    path (which does NOT support thinkingConfig) untouched."""
    body_25 = llm_mod._generate_content_body("Draft it.", {"k": "v"}, model="gemini-2.5-flash")
    tc = body_25["generationConfig"]["thinkingConfig"]
    assert tc["thinkingBudget"] <= 2048
    # A generous answer budget remains after the bounded thinking.
    assert body_25["generationConfig"]["maxOutputTokens"] - tc["thinkingBudget"] >= 4096

    body_15 = llm_mod._generate_content_body("Draft it.", {"k": "v"}, model="gemini-1.5-pro")
    assert "thinkingConfig" not in body_15["generationConfig"]


@pytest.mark.unit
def test_generate_content_truncation_raises_loudly() -> None:
    """A truncated generation (finishReason=MAX_TOKENS) must FAIL LOUDLY at the
    parse seam — not return half a JSON document that dies later as an opaque
    JSONDecodeError in the engine's response parser (the 2026-07-15 sweep bug)."""
    truncated = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"scores": [{"tier": "hi'}]},
                "finishReason": "MAX_TOKENS",
            }
        ],
        "usageMetadata": {"promptTokenCount": 364, "candidatesTokenCount": 8192},
    }
    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        llm_mod._parse_generate_content(truncated)


@pytest.mark.unit
def test_generate_content_normal_finish_parses(monkeypatch) -> None:
    """finishReason=STOP (or absent) parses normally — the guard only fires on a
    non-STOP terminal reason."""
    ok = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"ok": true}'}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }
    resp = llm_mod._parse_generate_content(ok)
    assert resp.content == '{"ok": true}'
    assert resp.output_tokens == 5


@pytest.mark.unit
def test_gemini_missing_key_raises_loudly() -> None:
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        GeminiProvider(model="gemini-1.5-pro", api_key="")


@pytest.mark.unit
def test_gemini_selected_by_build_provider() -> None:
    settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="gemini",
        shield_llm_model="gemini-1.5-pro",
        gemini_api_key="g-test",
    )
    provider = _build_provider(settings)
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"


# --------------------------------------------------------------------------- #
# Vertex adapter (ADC bearer token, D-029). Same generateContent schema as
# Gemini, so it shares the body-build / parse helpers; the token acquisition is
# monkeypatched so no google-auth / real ADC is needed in the unit run.
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_vertex_request_shape_and_response_parsing(monkeypatch) -> None:
    captured = _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "candidates": [{"content": {"parts": [{"text": "vertex "}, {"text": "draft"}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 6},
            },
        ),
    )
    provider = VertexProvider(
        model="gemini-2.5-flash", project="kentro-cloudmod-dev", region="us-central1"
    )
    # Avoid touching real google-auth / ADC — inject a canned bearer token.
    monkeypatch.setattr(provider, "_bearer_token", lambda: "ya29.canned-token")
    resp = provider.complete(
        "Draft the summary.", {"framework": "ztmm", "__purpose__": "zt.narrative"}
    )

    assert resp.content == "vertex draft"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 6

    # Regional aiplatform endpoint with the project/location/model path.
    assert (
        "us-central1-aiplatform.googleapis.com/v1/projects/kentro-cloudmod-dev/"
        "locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
        in captured["url"]
    )
    # ADC bearer travels in the Authorization header, never the URL/query.
    assert captured["headers"]["Authorization"] == "Bearer ya29.canned-token"
    assert "ya29" not in captured["url"]
    blob = json.dumps(captured["json"])
    assert "Draft the summary." in blob
    assert "ztmm" in blob
    # Internal control keys are stripped before egress — never sent to the model.
    assert "__purpose__" not in blob


@pytest.mark.unit
def test_vertex_missing_project_raises_loudly() -> None:
    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID"):
        VertexProvider(model="gemini-2.5-flash", project="", region="us-central1")


@pytest.mark.unit
def test_vertex_selected_by_build_provider() -> None:
    settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        shield_llm_model="gemini-2.5-flash",
        gcp_project_id="kentro-cloudmod-dev",
        gcp_region="us-central1",
    )
    provider = _build_provider(settings)
    assert isinstance(provider, VertexProvider)
    assert provider.name == "vertex"
    assert provider.model == "gemini-2.5-flash"


@pytest.mark.unit
def test_vertex_http_error_does_not_leak_bearer_token(monkeypatch, db_factory) -> None:
    _install_fake_httpx(monkeypatch, _FakeResponse(500, {"error": "boom"}))
    provider = VertexProvider(
        model="gemini-2.5-flash", project="kentro-cloudmod-dev", region="us-central1"
    )
    monkeypatch.setattr(provider, "_bearer_token", lambda: "ya29.super-secret-adc-token")
    live_settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="vertex",
        gcp_project_id="kentro-cloudmod-dev",
    )
    client = LLMClient(provider, settings=live_settings)

    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(httpx.HTTPStatusError):  # bubbles through the seam
            client.invoke(
                db,
                purpose="zt.narrative",
                prompt="x",
                payload={"a": 1},
                requested_by=admin.id,
            )
        db.commit()

        row = db.execute(select(LLMCall)).scalar_one()
        assert row.status == LLMCallStatus.FAILED
        assert row.provider == "vertex"
        assert row.mode == LLMCallMode.LIVE
        assert row.error_message
        # The ADC bearer token must NEVER be persisted to the audit row — it
        # rides the Authorization header, so it can't leak via the error URL.
        assert "ya29.super-secret-adc-token" not in row.error_message
        assert "ya29" not in row.error_message


# --------------------------------------------------------------------------- #
# Not-implemented providers stay loud.
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("provider_name", ["azure_openai", "bedrock", "local"])
def test_unimplemented_providers_raise(provider_name) -> None:
    settings = Settings(shield_llm_mode="live", shield_llm_provider=provider_name)
    with pytest.raises(RuntimeError, match="not implemented"):
        _build_provider(settings)


# --------------------------------------------------------------------------- #
# HTTP error -> failed llm_calls row (mirrors the Anthropic failure invariant).
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_openai_http_error_records_failed_row(monkeypatch, db_factory) -> None:
    _install_fake_httpx(monkeypatch, _FakeResponse(500, {"error": "boom"}))
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-test")
    live_settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="openai",
        openai_api_key="sk-test",
    )
    client = LLMClient(provider, settings=live_settings)

    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(httpx.HTTPStatusError):  # bubbles through the seam
            client.invoke(
                db,
                purpose="csf.narrative",
                prompt="x",
                payload={"a": 1},
                requested_by=admin.id,
            )
        db.commit()

        row = db.execute(select(LLMCall)).scalar_one()
        assert row.status == LLMCallStatus.FAILED
        assert row.provider == "openai"
        assert row.mode == LLMCallMode.LIVE
        assert row.error_message
        assert row.duration_ms is not None and row.duration_ms >= 0


@pytest.mark.unit
def test_gemini_http_error_records_failed_row(monkeypatch, db_factory) -> None:
    _install_fake_httpx(monkeypatch, _FakeResponse(500, {"error": "boom"}))
    provider = GeminiProvider(model="gemini-1.5-pro", api_key="g-secret-key")
    live_settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider="gemini",
        gemini_api_key="g-secret-key",
    )
    client = LLMClient(provider, settings=live_settings)

    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(httpx.HTTPStatusError):  # bubbles through the seam
            client.invoke(
                db,
                purpose="zt.narrative",
                prompt="x",
                payload={"a": 1},
                requested_by=admin.id,
            )
        db.commit()

        row = db.execute(select(LLMCall)).scalar_one()
        assert row.status == LLMCallStatus.FAILED
        assert row.provider == "gemini"
        assert row.mode == LLMCallMode.LIVE
        assert row.error_message
        assert row.duration_ms is not None and row.duration_ms >= 0
        # The API key must NEVER be persisted to the audit row — it rides the
        # x-goog-api-key header, so it can't leak via the error URL (A1).
        assert "g-secret-key" not in row.error_message


@pytest.mark.unit
def test_ai_package_imports() -> None:
    # Guard against an accidental import-time regression in the module.
    assert ai is not None
