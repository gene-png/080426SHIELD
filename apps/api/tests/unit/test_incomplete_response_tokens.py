"""#820 review F1: a response that did not finish cleanly still COST tokens.

Every live adapter refuses a response that stopped short (Anthropic
`stop_reason`, generateContent `finishReason`, OpenAI `finish_reason`, the last
in `test_openai_finish_reason.py`). The call was generated and billed, so the
FAILED `llm_calls` row records the usage the provider reported. Before, the
except branch in `LLMClient.invoke` wrote only status, error and duration, and a
call billed up to the cap read as zero tokens (the N-019 shape).

Each adapter goes through `LLMClient.invoke` with its transport faked, and the
row is read back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai import llm as llm_mod
from app.ai.llm import GeminiProvider, LLMClient, VertexProvider
from app.config import Settings
from app.models.llm_call import LLMCall, LLMCallStatus
from tests.unit.test_llm_providers import (  # noqa: F401  (fixture)
    _FakeResponse,
    _install_fake_httpx,
    _new_admin,
    db_factory,
)

pytestmark = pytest.mark.unit

_LIVE = Settings(shield_llm_mode="live", shield_llm_provider="gemini", gemini_api_key="g")


def _row_after(db_factory, provider):  # noqa: F811
    client = LLMClient(provider, settings=_LIVE)
    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(RuntimeError, match="did not finish cleanly"):
            client.invoke(
                db, purpose="csf_score", prompt="x", payload={"a": 1}, requested_by=admin.id
            )
        db.commit()
        row = db.execute(select(LLMCall)).scalar_one()
        return row.status, row.error_message, (row.input_tokens, row.output_tokens)


class _Message:
    """`get_final_message()`'s reply: cut off at the cap."""

    def __init__(self) -> None:
        self.content = [type("Block", (), {"type": "text", "text": '{"rows": [{"id'})()]
        self.stop_reason = "max_tokens"
        self.usage = type("Usage", (), {"input_tokens": 4715, "output_tokens": 64000})()


class _Stream:
    def __enter__(self) -> _Stream:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def get_final_message(self) -> _Message:
        return _Message()


def test_anthropic_cut_off_records_its_tokens(monkeypatch, db_factory) -> None:  # noqa: F811
    provider = llm_mod.AnthropicProvider(model="claude-opus-5", api_key="k")
    fake = type(
        "Client", (), {"messages": type("M", (), {"stream": lambda self, **kw: _Stream()})()}
    )()
    monkeypatch.setattr(provider, "_ensure_client", lambda: fake)
    status, error, tokens = _row_after(db_factory, provider)
    assert status == LLMCallStatus.FAILED
    assert error.startswith(
        "IncompleteResponseError: Anthropic did not finish cleanly (stop_reason=max_tokens)."
    )
    assert tokens == (4715, 64000)


def _cut_off_generate_content(monkeypatch) -> None:
    _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": '{"rows": [{"id'}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 3100, "candidatesTokenCount": 8192},
            },
        ),
    )


def test_gemini_cut_off_records_its_tokens(monkeypatch, db_factory) -> None:  # noqa: F811
    _cut_off_generate_content(monkeypatch)
    status, error, tokens = _row_after(
        db_factory, GeminiProvider(model="gemini-2.5-pro", api_key="g")
    )
    assert status == LLMCallStatus.FAILED
    assert error.startswith(
        "IncompleteResponseError: generateContent did not finish cleanly (finishReason=MAX_TOKENS)."
    )
    assert tokens == (3100, 8192)


def test_vertex_cut_off_records_its_tokens(monkeypatch, db_factory) -> None:  # noqa: F811
    _cut_off_generate_content(monkeypatch)
    provider = VertexProvider(model="gemini-2.5-pro", project="p", region="us-central1")
    monkeypatch.setattr(provider, "_bearer_token", lambda: "ya29.canned-token")
    status, error, tokens = _row_after(db_factory, provider)
    assert status == LLMCallStatus.FAILED
    assert error.startswith(
        "IncompleteResponseError: generateContent did not finish cleanly (finishReason=MAX_TOKENS)."
    )
    assert tokens == (3100, 8192)


def test_an_ordinary_failure_still_records_no_tokens(monkeypatch, db_factory) -> None:  # noqa: F811
    """Only a response the provider generated carries usage; a 500 did not."""
    _install_fake_httpx(monkeypatch, _FakeResponse(500, {"error": "boom"}))
    client = LLMClient(GeminiProvider(model="gemini-2.5-pro", api_key="g"), settings=_LIVE)
    with db_factory() as db:
        admin = _new_admin(db)
        with pytest.raises(Exception, match="HTTP 500"):
            client.invoke(
                db, purpose="csf_score", prompt="x", payload={"a": 1}, requested_by=admin.id
            )
        db.commit()
        row = db.execute(select(LLMCall)).scalar_one()
        assert row.status == LLMCallStatus.FAILED
        assert (row.input_tokens, row.output_tokens) == (None, None)
