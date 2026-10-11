"""#823: a response that carries NO stop signal is refused, on every provider.

A provider reports how a generation ended:
  * Anthropic Messages: `stop_reason`, one of end_turn, max_tokens,
    stop_sequence, tool_use, pause_turn, refusal. It is null only on the
    `message_start` event of a stream, before anything is generated
    (https://docs.anthropic.com/en/api/messages), so a final message without
    one never said it finished.
  * Gemini / Vertex generateContent: `candidates[].finishReason`, STOP for a
    natural end (https://ai.google.dev/api/generate-content#FinishReason). A
    candidate without one never said it finished.
OpenAI already refuses an absent `finish_reason` (#820). These three adapters
accepted absence as success; now each refuses it as an incomplete response,
and the FAILED `llm_calls` row records the usage the provider reported.

Every case goes through `LLMClient.invoke`, and expected strings are written
out here.
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


def _invoke(db_factory, provider):  # noqa: F811
    client = LLMClient(provider, settings=_LIVE)
    with db_factory() as db:
        admin = _new_admin(db)
        try:
            client.invoke(
                db, purpose="zt_score", prompt="x", payload={"a": 1}, requested_by=admin.id
            )
            raised = None
        except Exception as exc:  # noqa: BLE001 - the test reads what was raised
            raised = exc
        db.commit()
        row = db.execute(select(LLMCall)).scalar_one()
        return raised, row.status, row.error_message, (row.input_tokens, row.output_tokens)


# --- Anthropic ---------------------------------------------------------------

ANTHROPIC = (
    "Anthropic did not finish cleanly (no stop_reason). The response is incomplete "
    "and was NOT parsed; if this is max_tokens, the draft exceeded the output budget."
)


class _Message:
    def __init__(self, *, with_attribute: bool) -> None:
        self.content = [type("Block", (), {"type": "text", "text": '{"ok": true}'})()]
        if with_attribute:
            self.stop_reason = None
        self.usage = type("Usage", (), {"input_tokens": 3170, "output_tokens": 1553})()


def _anthropic(monkeypatch, message: _Message):
    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def get_final_message(self):
            return message

    provider = llm_mod.AnthropicProvider(model="claude-opus-5", api_key="k")
    messages = type("Messages", (), {"stream": lambda self, **kw: _Stream()})()
    monkeypatch.setattr(provider, "_ensure_client", lambda: type("C", (), {"messages": messages})())
    return provider


@pytest.mark.parametrize("with_attribute", [False, True], ids=["absent", "null"])
def test_anthropic_without_a_stop_reason_is_refused(
    monkeypatch, db_factory, with_attribute  # noqa: F811
) -> None:
    provider = _anthropic(monkeypatch, _Message(with_attribute=with_attribute))
    raised, status, error, tokens = _invoke(db_factory, provider)
    assert status == LLMCallStatus.FAILED
    assert error == f"IncompleteResponseError: {ANTHROPIC}"
    assert tokens == (3170, 1553)
    assert str(raised) == ANTHROPIC


# --- Gemini and Vertex (one parser) --------------------------------------------

GENERATE_CONTENT = (
    "generateContent did not finish cleanly (no finishReason). The response is "
    "incomplete and was NOT parsed; if this is MAX_TOKENS, raise maxOutputTokens for "
    "this purpose."
)


def _no_finish_reason(monkeypatch) -> None:
    _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {
                "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                "usageMetadata": {"promptTokenCount": 3100, "candidatesTokenCount": 1553},
            },
        ),
    )


def test_gemini_without_a_finish_reason_is_refused(monkeypatch, db_factory) -> None:  # noqa: F811
    _no_finish_reason(monkeypatch)
    raised, status, error, tokens = _invoke(
        db_factory, GeminiProvider(model="gemini-2.5-pro", api_key="g")
    )
    assert status == LLMCallStatus.FAILED
    assert error == f"IncompleteResponseError: {GENERATE_CONTENT}"
    assert tokens == (3100, 1553)
    assert str(raised) == GENERATE_CONTENT


def test_vertex_without_a_finish_reason_is_refused(monkeypatch, db_factory) -> None:  # noqa: F811
    _no_finish_reason(monkeypatch)
    provider = VertexProvider(model="gemini-2.5-pro", project="p", region="us-central1")
    monkeypatch.setattr(provider, "_bearer_token", lambda: "ya29.canned-token")
    raised, status, error, tokens = _invoke(db_factory, provider)
    assert status == LLMCallStatus.FAILED
    assert error == f"IncompleteResponseError: {GENERATE_CONTENT}"
    assert tokens == (3100, 1553)
    assert str(raised) == GENERATE_CONTENT
