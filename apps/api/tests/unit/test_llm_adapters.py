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


@pytest.mark.unit
@pytest.mark.parametrize("provider", get_args(LLMProvider))
def test_has_live_adapter_matches_the_boot_preflight_too(provider: str) -> None:
    """The preflight carries a THIRD hand-written provider list, and it is the
    one that decides whether the api boots. So `has_live_adapter` is pinned
    against it as well (round 2 on #472)."""
    settings = Settings(
        shield_llm_mode="live",
        shield_llm_provider=provider,
        shield_llm_model="some-real-model",
        # Pinned, so vertex stops at the project check and never reaches the
        # real ADC probe (round 4 on #472: tests are hermetic).
        gcp_project_id="",
    )
    _ready, detail = settings.live_llm_readiness()
    assert has_live_adapter(provider) is ("has no live adapter" not in detail), (
        provider,
        detail,
    )


@pytest.mark.unit
def test_the_adc_probe_is_reused_briefly_then_asked_again(monkeypatch) -> None:
    """Round 3 on #472: with no credentials configured, `google.auth.default()`
    pings the GCE metadata server (measured 3.2-3.9 s), and `/admin/ai-status`
    asks the preflight on every read for vertex in fixture mode. Round 4: a
    process-lifetime cache then kept a stale answer after the admin followed the
    advice. So the answer is reused for a SHORT window and re-asked after it."""
    google_auth = pytest.importorskip("google.auth")
    import app.config as config_mod

    calls = []

    def fake_default(*args, **kwargs):
        calls.append(1)
        raise google_auth.exceptions.DefaultCredentialsError("none")

    clock = [1000.0]
    monkeypatch.setattr(google_auth, "default", fake_default)
    monkeypatch.setattr(config_mod.time, "monotonic", lambda: clock[0])
    config_mod._reset_adc_cache()
    try:
        assert config_mod._adc_resolvable() is False
        assert config_mod._adc_resolvable() is False
        assert len(calls) == 1, "a second read inside the window probed again"
        clock[0] += config_mod._ADC_CACHE_SECONDS + 1
        assert config_mod._adc_resolvable() is False
        assert len(calls) == 2, "the answer outlived its window"
    finally:
        config_mod._reset_adc_cache()


@pytest.mark.unit
def test_an_unreadable_credentials_file_is_not_resolvable_rather_than_an_error(
    monkeypatch,
) -> None:
    google_auth = pytest.importorskip("google.auth")
    import app.config as config_mod

    def unreadable(*args, **kwargs):
        raise PermissionError("[Errno 13] Permission denied: '/gcloud/adc.json'")

    monkeypatch.setattr(google_auth, "default", unreadable)
    config_mod._reset_adc_cache()
    try:
        assert config_mod._adc_resolvable() is False
    finally:
        config_mod._reset_adc_cache()
