"""#828: a generateContent response with nothing to parse is refused by cause.

`_parse_generate_content` (Gemini and Vertex) indexed `candidates[0]` and
`content.parts` before any guard, so three documented shapes died as a bare
KeyError / IndexError with null tokens on the FAILED row:
  * the PROMPT was blocked: `promptFeedback.blockReason` is set and no
    candidate is returned
    (https://ai.google.dev/api/generate-content#PromptFeedback);
  * no candidate at all, with no block reason;
  * a STOP candidate with no `content` (or no `parts`).
Each is now a typed error naming the cause, and the FAILED `llm_calls` row
records the usage the provider reported (`usageMetadata`), because the prompt
was still sent and counted.

Every case goes through `LLMClient.invoke` with Gemini's transport faked; one
runs through Vertex, which shares the parser. Expected strings are written out.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.failures import friendly_reason
from app.ai.llm import GeminiProvider, LLMClient, NoUsableResponseError, VertexProvider
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
_USAGE = {"promptTokenCount": 3100, "totalTokenCount": 3100}

BLOCKED = (
    "generateContent returned no candidates: the prompt was blocked "
    "(blockReason=SAFETY). Nothing was generated or parsed."
)
NO_CANDIDATES = "generateContent returned no candidates. Nothing was generated or parsed."
NO_CONTENT = (
    "generateContent returned a candidate with no content (finishReason=STOP). "
    "Nothing was parsed."
)
NO_TEXT = (
    "generateContent returned a candidate with no text (finishReason=STOP). " "Nothing was parsed."
)
#: A distinctive output count, so a hardcoded 0 (or None) in a raise is caught.
_STOP_USAGE = {**_USAGE, "candidatesTokenCount": 7}


def _stop(parts: list, usage: dict = _STOP_USAGE) -> dict:
    return {
        "candidates": [{"content": {"role": "model", "parts": parts}, "finishReason": "STOP"}],
        "usageMetadata": usage,
    }


def _invoke(monkeypatch, db_factory, body: dict, provider=None):  # noqa: F811
    _install_fake_httpx(monkeypatch, _FakeResponse(200, body))
    if provider is None:
        provider = GeminiProvider(model="gemini-2.5-pro", api_key="g")
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


@pytest.mark.parametrize(
    ("body", "expected", "tokens"),
    [
        (
            {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": _USAGE},
            BLOCKED,
            (3100, None),
        ),
        ({"candidates": [], "usageMetadata": _USAGE}, NO_CANDIDATES, (3100, None)),
        ({"usageMetadata": _USAGE}, NO_CANDIDATES, (3100, None)),
        (
            {
                "candidates": [{"finishReason": "STOP"}],
                "usageMetadata": {**_USAGE, "candidatesTokenCount": 0},
            },
            NO_CONTENT,
            (3100, 0),
        ),
        (
            {
                "candidates": [{"content": {"role": "model"}, "finishReason": "STOP"}],
                "usageMetadata": {**_USAGE, "candidatesTokenCount": 0},
            },
            NO_CONTENT,
            (3100, 0),
        ),
    ],
    ids=["prompt-blocked", "empty-candidates", "no-candidates-key", "no-content", "no-parts"],
)
def test_a_response_with_nothing_to_parse_is_refused_by_cause(
    monkeypatch, db_factory, body, expected, tokens  # noqa: F811
) -> None:
    raised, status, error, recorded = _invoke(monkeypatch, db_factory, body)
    assert status == LLMCallStatus.FAILED
    assert error == f"NoUsableResponseError: {expected}"
    assert recorded == tokens
    assert str(raised) == expected


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([], NO_CONTENT),
        ([{"text": ""}], NO_TEXT),
        ([{"text": "  \n \t"}], NO_TEXT),
        ([{"functionCall": {"name": "f", "args": {}}}], NO_TEXT),
    ],
    ids=["empty-parts", "empty-text", "whitespace-text", "function-call-only"],
)
def test_a_stop_candidate_with_no_text_is_refused(
    monkeypatch, db_factory, parts, expected  # noqa: F811
) -> None:
    """#830 review F1: these passed the `parts is None` guard, joined to "",
    were recorded COMPLETED and died later in json.loads."""
    raised, status, error, recorded = _invoke(monkeypatch, db_factory, _stop(parts))
    assert status == LLMCallStatus.FAILED
    assert error == f"NoUsableResponseError: {expected}"
    assert recorded == (3100, 7)
    assert str(raised) == expected


def test_no_text_without_an_output_count_records_none(
    monkeypatch, db_factory  # noqa: F811
) -> None:
    """No `candidatesTokenCount` reported: the row says unknown, never 0."""
    body = _stop([{"text": ""}], usage=_USAGE)
    raised, status, error, recorded = _invoke(monkeypatch, db_factory, body)
    assert (status, error, recorded) == (
        LLMCallStatus.FAILED,
        f"NoUsableResponseError: {NO_TEXT}",
        (3100, None),
    )
    assert str(raised) == NO_TEXT


@pytest.mark.parametrize("message", [BLOCKED, NO_CANDIDATES, NO_CONTENT, NO_TEXT])
def test_none_of_the_messages_reads_as_cut_off(message) -> None:
    """#830 review F2: the reason these are not IncompleteResponseError is that
    nothing was cut short, so the admin must not be told it was."""
    copy = friendly_reason(NoUsableResponseError(message, input_tokens=1, output_tokens=0))
    assert "cut off" not in copy
    assert copy.startswith("The AI call failed and nothing was applied.")


def test_vertex_shares_the_refusal(monkeypatch, db_factory) -> None:  # noqa: F811
    provider = VertexProvider(model="gemini-2.5-pro", project="p", region="us-central1")
    monkeypatch.setattr(provider, "_bearer_token", lambda: "ya29.canned-token")
    body = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": _USAGE}
    raised, status, error, recorded = _invoke(monkeypatch, db_factory, body, provider)
    assert (status, error, recorded) == (
        LLMCallStatus.FAILED,
        f"NoUsableResponseError: {BLOCKED}",
        (3100, None),
    )
    assert str(raised) == BLOCKED
