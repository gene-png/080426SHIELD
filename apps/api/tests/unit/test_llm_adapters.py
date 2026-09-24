"""`has_live_adapter` agrees with `_build_provider`, the thing it describes (#472).

Readiness uses `has_live_adapter` to decide whether "set SHIELD_LLM_MODE=live"
is advice or a way to stop the api booting. It is a set, and a set can drift
from the if-chain it summarises. So the expected value here is derived from
the chain: build each provider in live mode and see whether it refuses as
unimplemented. Every member of `LLMProvider` is asked, so a new provider
cannot be added to the Literal without being classified.
"""

from __future__ import annotations

from typing import get_args

import pytest

from app.ai.llm import _build_provider, has_live_adapter
from app.config import LLMProvider, Settings


def _builds_live(provider: str) -> bool:
    settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider=provider,
        shield_llm_model="some-real-model",
        anthropic_api_key="k",
        openai_api_key="k",
        gemini_api_key="k",
        gcp_project_id="p",
    )
    try:
        _build_provider(settings)
    except RuntimeError as exc:
        if "not implemented" in str(exc):
            return False
        raise
    return True


@pytest.mark.unit
@pytest.mark.parametrize("provider", get_args(LLMProvider))
def test_has_live_adapter_matches_what_build_provider_does(provider: str) -> None:
    assert has_live_adapter(provider) is _builds_live(provider), provider


@pytest.mark.unit
def test_the_question_is_asked_of_more_than_one_answer() -> None:
    """A selector that selects nothing passes: both answers must occur."""
    answers = {has_live_adapter(p) for p in get_args(LLMProvider)}
    assert answers == {True, False}
