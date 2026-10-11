"""#484: the OpenAI adapter refuses a response that did not finish cleanly.

The Anthropic adapter raises on a `stop_reason` outside its clean set, and the
generateContent adapters on a `finishReason` other than STOP. OpenAI's Chat
Completions reports the same thing as `choices[0].finish_reason`: `stop` is a
complete answer, and `length` is one cut off at the output cap
(https://platform.openai.com/docs/api-reference/chat/object). Before this
guard a `length` response came back as a success, the `llm_calls` row said
COMPLETED, and the truncated JSON then died in the engine's parser under the
wrong cause.

Every case goes through `LLMClient.invoke`, the one seam every job uses, and
asserts the `llm_calls` row. Expected strings are written out here.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.failures import friendly_reason
from app.ai.llm import LLMClient, OpenAIProvider
from app.config import Settings
from app.models.llm_call import LLMCall, LLMCallStatus
from tests.unit.test_llm_providers import (  # noqa: F401  (fixture)
    _FakeResponse,
    _install_fake_httpx,
    _new_admin,
    db_factory,
)

pytestmark = pytest.mark.unit

_LIVE = Settings(shield_llm_mode="live", shield_llm_provider="openai", openai_api_key="sk-test")


def _invoke(monkeypatch, db_factory, finish_reason: str | None):  # noqa: F811
    """`finish_reason` None sends a choice WITHOUT the key."""
    choice: dict = {"message": {"content": '{"rows": [{"id": 1'}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    _install_fake_httpx(
        monkeypatch,
        _FakeResponse(
            200,
            {"choices": [choice], "usage": {"prompt_tokens": 40, "completion_tokens": 8192}},
        ),
    )
    client = LLMClient(OpenAIProvider(model="gpt-4o-mini", api_key="sk-test"), settings=_LIVE)
    with db_factory() as db:
        admin = _new_admin(db)
        try:
            client.invoke(
                db, purpose="csf_score", prompt="x", payload={"a": 1}, requested_by=admin.id
            )
            raised = None
        except Exception as exc:  # noqa: BLE001 - the test reads what was raised
            raised = exc
        db.commit()
        row = db.execute(select(LLMCall)).scalar_one()
        return raised, row.status, row.error_message, (row.input_tokens, row.output_tokens)


@pytest.mark.parametrize("finish_reason", ["length", "content_filter"])
def test_an_unclean_finish_is_refused_and_recorded_failed(
    monkeypatch, db_factory, finish_reason  # noqa: F811
) -> None:
    raised, status, error, tokens = _invoke(monkeypatch, db_factory, finish_reason)
    expected = (
        f"OpenAI did not finish cleanly (finish_reason={finish_reason}). The response is "
        "incomplete and was NOT parsed; if this is length, the draft exceeded the output "
        "budget."
    )
    # The ledger first: before #484 this row said COMPLETED.
    assert status == LLMCallStatus.FAILED
    assert error == f"IncompleteResponseError: {expected}"
    # Generated and billed, though not parsed: the row records what it cost.
    assert tokens == (40, 8192)
    assert isinstance(raised, RuntimeError), raised
    assert str(raised) == expected


def test_a_cut_off_response_gets_the_cut_off_copy(monkeypatch, db_factory) -> None:  # noqa: F811
    """The admin is told the output was cut off, not that the JSON was bad."""
    raised, _status, _error, _tokens = _invoke(monkeypatch, db_factory, "length")
    assert friendly_reason(raised).startswith(
        "The AI response was cut off before it finished, so nothing was applied."
    )


def test_a_clean_finish_is_returned_and_recorded_completed(
    monkeypatch, db_factory  # noqa: F811
) -> None:
    raised, status, error, tokens = _invoke(monkeypatch, db_factory, "stop")
    assert raised is None
    assert (status, error, tokens) == (LLMCallStatus.COMPLETED, None, (40, 8192))


def test_an_absent_finish_reason_is_refused(monkeypatch, db_factory) -> None:  # noqa: F811
    """Fail closed (advisor, 2026-10-03, on #820): nothing says the response
    finished, so it is refused like a cut-off one, with its usage recorded."""
    raised, status, error, tokens = _invoke(monkeypatch, db_factory, None)
    expected = (
        "OpenAI did not finish cleanly (no finish_reason). The response is incomplete and "
        "was NOT parsed; if this is length, the draft exceeded the output budget."
    )
    assert status == LLMCallStatus.FAILED
    assert error == f"IncompleteResponseError: {expected}"
    assert tokens == (40, 8192)
    assert str(raised) == expected
