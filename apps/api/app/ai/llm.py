"""LLM client - the ONLY path that calls an external AI provider.

Master Spec §4.4: provider env-configurable, never hardcoded. §12: every
call MUST pass through the redactor first. AI Prompt §6.13 + §6.14
reinforce both.

Two modes:
  fixture - canned, deterministic responses. Tests + offline dev use this.
  live    - real provider call. Production default for v1 is Anthropic.

The client's `invoke(...)` method:
  1. Redacts the input payload via app.ai.redact.redact_payload.
  2. Writes an `llm_calls` row with status=running BEFORE the provider
     call so a crash mid-call still leaves a record.
  3. Calls the provider (fixture or live).
  4. Updates the llm_calls row with status=completed | failed plus
     token counts + duration + redacted_counts.
  5. Returns the provider response.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any, Literal, Protocol

import httpx
from sqlalchemy.orm import Session

from app.ai.redact import RedactionMode, redact_payload
from app.config import Settings, get_settings
from app.logging import correlation_id_var, get_logger
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus

_log = get_logger(__name__)


class LLMResponse:
    """Provider response container. Token counts may be None if the provider
    didn't report them (fixture mode supplies them; some providers don't)."""

    __slots__ = ("content", "input_tokens", "output_tokens")

    def __init__(
        self,
        content: str,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        """Run the prompt + payload through the provider. Synchronous; the
        caller is on a Celery worker for anything that's not interactive."""
        ...


class FixtureProvider:
    """Deterministic canned responses for tests + offline dev.

    A fixture is registered per `purpose`. If the purpose isn't registered,
    `complete()` raises `KeyError` so a test that forgot to register a
    fixture fails loudly rather than silently calling out to the real
    provider.
    """

    name = "fixture"

    def __init__(self, model: str = "fixture-model-1") -> None:
        self.model = model
        self._fixtures: dict[str, Callable[[dict[str, Any]], LLMResponse]] = {}

    def register(self, purpose: str, fn: Callable[[dict[str, Any]], LLMResponse]) -> None:
        self._fixtures[purpose] = fn

    def register_static(self, purpose: str, response: LLMResponse) -> None:
        self.register(purpose, lambda _payload: response)

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        purpose = payload.get("__purpose__") or "default"
        if purpose not in self._fixtures and "default" not in self._fixtures:
            raise KeyError(
                f"No fixture registered for purpose={purpose!r}. Did you forget "
                "to call FixtureProvider.register()?"
            )
        fn = self._fixtures.get(purpose) or self._fixtures["default"]
        return fn(payload)


class AnthropicProvider:
    """Live Anthropic Claude provider.

    boto3 / anthropic SDKs are heavy and the test runs never hit them, so
    the SDK is imported lazily on first call.
    """

    name = "anthropic"

    def __init__(self, *, model: str, api_key: str) -> None:
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Either set it in .env or switch "
                "SHIELD_LLM_MODE to 'fixture'."
            )
        self.model = model
        self._api_key = api_key
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from anthropic import Anthropic

            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        client = self._ensure_client()
        # Payload is sent as JSON inside the user message. The redactor has
        # already run upstream, so this content is safe to egress.
        msg = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "text", "text": json.dumps(_egress_payload(payload))},
                    ],
                }
            ],
        )
        # `msg.content` is a list of blocks; gather the text blocks.
        text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        input_tokens = getattr(getattr(msg, "usage", None), "input_tokens", None)
        output_tokens = getattr(getattr(msg, "usage", None), "output_tokens", None)
        return LLMResponse(text, input_tokens, output_tokens)


_HTTP_TIMEOUT_SECONDS = 60.0
# gemini-2.5 "thinking" models spend part of this budget on hidden reasoning
# tokens before emitting the visible answer, so a 4096 cap truncated the longer
# csf_score / risk_synthesize drafts mid-JSON in the 2026-07-15 Vertex live
# sweep. 8192 gives the structured drafts real headroom above the thinking
# overhead; the finishReason guard in _parse_generate_content still FAILS LOUDLY
# if a generation ever exceeds even this (never silently returns half a doc).
_MAX_OUTPUT_TOKENS = 8192

# OpenAI reasoning / `responses` model families (the o-series and gpt-5) REJECT
# the legacy ``max_tokens`` Chat Completions key with an HTTP 400 and require
# ``max_completion_tokens`` instead. Older chat models (gpt-4o, gpt-4, gpt-3.5)
# still accept ``max_tokens``. Match on the model id prefix (D-024 / Sprint 6 T6).
_OPENAI_REASONING_RE = re.compile(r"^(o[1-9]|gpt-5)", re.IGNORECASE)


def _openai_token_limit_key(model: str) -> str:
    """Return the correct output-token-limit request key for an OpenAI model."""
    return "max_completion_tokens" if _OPENAI_REASONING_RE.match(model) else "max_tokens"


def _egress_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop internal control keys (``__purpose__`` and any other ``__``-prefixed
    routing metadata) before serializing to a real provider. Those keys are for
    ``FixtureProvider`` dispatch only — never content the model should see."""
    return {k: v for k, v in payload.items() if not str(k).startswith("__")}


# The Gemini API-key path (generativelanguage) and the Vertex ADC path
# (aiplatform) speak the IDENTICAL generateContent request/response schema, so
# the body-build and response-parse are factored here and shared by both
# adapters (D-024 / D-029). Only the endpoint host and the auth mechanism differ.


# gemini-2.5 model family enables "thinking" by default and, left unbounded,
# consumes a run-to-run-variable slice of the output budget before the visible
# answer — it truncated zt_score even at the raised 8192 cap in the 2026-07-15
# Vertex sweep. Bounding thinkingBudget guarantees the structured draft always
# has room. gemini-1.5 does NOT accept thinkingConfig (HTTP 400), so the field
# is added ONLY for 2.5+ models; the API-key gemini-1.5 path stays untouched.
_GEMINI_THINKING_RE = re.compile(r"gemini-2\.[5-9]", re.IGNORECASE)
_THINKING_BUDGET_TOKENS = 2048


def _generate_content_body(
    prompt: str, payload: dict[str, Any], *, model: str | None = None
) -> dict[str, Any]:
    """Shape a redacted prompt + payload into a generateContent request body."""
    generation_config: dict[str, Any] = {"maxOutputTokens": _MAX_OUTPUT_TOKENS}
    if model is not None and _GEMINI_THINKING_RE.search(model):
        generation_config["thinkingConfig"] = {"thinkingBudget": _THINKING_BUDGET_TOKENS}
    return {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}, {"text": json.dumps(_egress_payload(payload))}],
            }
        ],
        "generationConfig": generation_config,
    }


def _parse_generate_content(data: dict[str, Any]) -> LLMResponse:
    """Parse a generateContent response body into text + token counts.

    Guards the FAIL-LOUDLY contract: a truncated or otherwise non-STOP
    generation (``finishReason`` = ``MAX_TOKENS``, ``SAFETY``, ``RECITATION`` …)
    is raised here rather than returned as a half-formed answer. Otherwise the
    truncated JSON draft would flow downstream and die as an opaque
    ``JSONDecodeError`` in the engine's response parser, hiding the real cause
    (the 2026-07-15 Vertex live sweep hit exactly this on csf/risk). An absent
    ``finishReason`` (e.g. hand-built test fixtures) is treated as success.
    """
    candidate = data["candidates"][0]
    finish_reason = candidate.get("finishReason")
    if finish_reason is not None and finish_reason != "STOP":
        raise RuntimeError(
            f"generateContent did not finish cleanly (finishReason={finish_reason}). "
            "The response is incomplete and was NOT parsed; if this is MAX_TOKENS, "
            "raise maxOutputTokens for this purpose."
        )
    parts = candidate["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts)
    usage = data.get("usageMetadata") or {}
    return LLMResponse(
        text,
        usage.get("promptTokenCount"),
        usage.get("candidatesTokenCount"),
    )


class OpenAIProvider:
    """Live OpenAI provider via the Chat Completions REST API.

    A thin ``httpx`` adapter — no SDK dependency. It sits BELOW the egress
    seam: the payload it receives has already been redacted by
    ``LLMClient.invoke``. It only translates prompt + payload into an OpenAI
    request and parses the response text + token counts back out.
    """

    name = "openai"
    _URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, *, model: str, api_key: str) -> None:
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Either set it in .env or switch "
                "SHIELD_LLM_MODE to 'fixture'."
            )
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        body = {
            "model": self.model,
            _openai_token_limit_key(self.model): _MAX_OUTPUT_TOKENS,
            "messages": [
                {"role": "user", "content": f"{prompt}\n\n{json.dumps(_egress_payload(payload))}"},
            ],
        }
        with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = client.post(
                self._URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        return LLMResponse(
            text,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )


class GeminiProvider:
    """Live Google Gemini provider via the generateContent REST API.

    Thin ``httpx`` adapter, same seam contract as ``OpenAIProvider``: the
    payload is already redacted; this only shapes the request and parses text
    + token counts from the response.
    """

    name = "gemini"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
    # Key travels in the x-goog-api-key HEADER, never the URL query string. A
    # ``?key=SECRET`` query param leaks into httpx's HTTPStatusError message
    # (which embeds the full request URL) and would then be persisted to the
    # llm_calls.error_message column and the logs on any HTTP failure.

    def __init__(self, *, model: str, api_key: str) -> None:
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Either set it in .env or switch "
                "SHIELD_LLM_MODE to 'fixture'."
            )
        self.model = model
        self._api_key = api_key

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        url = f"{self._BASE_URL}/{self.model}:generateContent"
        with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self._api_key,
                },
                json=_generate_content_body(prompt, payload, model=self.model),
            )
        resp.raise_for_status()
        return _parse_generate_content(resp.json())


class VertexProvider:
    """Live Google Vertex AI provider via the regional generateContent REST API,
    authenticated with Application Default Credentials — NO static API key
    (D-029). ADC is inherited from the host gcloud config (bind-mounted into the
    api container) or a service account; this is Dave's GCP posture from
    kentro-cloud-modernization.

    Same seam contract and generateContent schema as ``GeminiProvider`` — the
    body-build/parse helpers are shared. The only differences: the regional
    ``{region}-aiplatform.googleapis.com`` endpoint and an ``Authorization:
    Bearer <ADC token>`` header instead of the ``x-goog-api-key`` header.

    The bearer token rides the Authorization header, never the URL/query, so it
    cannot leak into an ``HTTPStatusError`` message (which embeds only the
    request URL) and thence into ``llm_calls.error_message`` or the logs — the
    same discipline as the Gemini key-in-header lesson above.
    """

    name = "vertex"

    def __init__(self, *, model: str, project: str, region: str) -> None:
        if not project:
            raise RuntimeError(
                "GCP_PROJECT_ID is not set. Either set it in .env or switch "
                "SHIELD_LLM_MODE to 'fixture'."
            )
        self.model = model
        self._project = project
        self._region = region
        self._credentials: Any | None = None

    def _bearer_token(self) -> str:
        """Obtain (and lazily refresh) an ADC access token. Isolated so unit
        tests can inject a canned token without touching real credentials."""
        import google.auth
        import google.auth.transport.requests

        from app.config import _GCP_CLOUD_PLATFORM_SCOPE

        if self._credentials is None:
            credentials, _project = google.auth.default(scopes=[_GCP_CLOUD_PLATFORM_SCOPE])
            self._credentials = credentials
        credentials = self._credentials
        if not credentials.valid:
            credentials.refresh(google.auth.transport.requests.Request())
        return credentials.token

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        url = (
            f"https://{self._region}-aiplatform.googleapis.com/v1/projects/"
            f"{self._project}/locations/{self._region}/publishers/google/models/"
            f"{self.model}:generateContent"
        )
        token = self._bearer_token()
        with httpx.Client(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
                json=_generate_content_body(prompt, payload, model=self.model),
            )
        resp.raise_for_status()
        return _parse_generate_content(resp.json())


def _build_provider(settings: Settings) -> LLMProvider:
    if settings.shield_llm_mode == "fixture":
        # Fixture mode serves deterministic, demo-plausible canned responses so
        # the whole stack is exercisable OFFLINE (T6b / DECISIONS D-017). The
        # runtime provider is preloaded with a fixture for every job purpose; a
        # forgotten purpose surfaces as a typed HTTP 503, never a raw 500. The
        # bare FixtureProvider (no fixtures, loud KeyError) is reserved for
        # pytest, which overrides the LLM dependency and takes precedence.
        from app.ai.fixtures import build_runtime_provider

        return build_runtime_provider(model=settings.shield_llm_model)
    if settings.shield_llm_provider == "anthropic":
        return AnthropicProvider(
            model=settings.shield_llm_model,
            api_key=settings.anthropic_api_key,
        )
    if settings.shield_llm_provider == "openai":
        return OpenAIProvider(
            model=settings.shield_llm_model,
            api_key=settings.openai_api_key,
        )
    if settings.shield_llm_provider == "gemini":
        return GeminiProvider(
            model=settings.shield_llm_model,
            api_key=settings.gemini_api_key,
        )
    if settings.shield_llm_provider == "vertex":
        return VertexProvider(
            model=settings.shield_llm_model,
            project=settings.gcp_project_id,
            region=settings.gcp_region,
        )
    # azure_openai / bedrock / local are valid config values but have no
    # adapter yet — fail loudly rather than silently degrade (FAIL LOUDLY).
    raise RuntimeError(
        f"LLM provider {settings.shield_llm_provider!r} is not implemented yet. "
        "Set SHIELD_LLM_PROVIDER to anthropic, openai, gemini, or vertex, or switch "
        "SHIELD_LLM_MODE to 'fixture'."
    )


class LLMClient:
    """The blessed surface for AI calls. Routes never construct a provider
    directly; they go through `LLMClient.invoke(...)`."""

    def __init__(self, provider: LLMProvider, settings: Settings | None = None) -> None:
        self.provider = provider
        self._settings = settings or get_settings()

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> LLMClient:
        s = settings or get_settings()
        return cls(_build_provider(s), s)

    def invoke(
        self,
        db: Session,
        *,
        purpose: str,
        prompt: str,
        payload: dict[str, Any],
        requested_by: uuid.UUID,
        service_id: uuid.UUID | None = None,
        client_id: uuid.UUID | None = None,
        prompt_version: str = "v1",
        redaction_mode: RedactionMode | None = None,
        client_org_name: str | None = None,
        name_hints: tuple[str, ...] = (),
    ) -> tuple[LLMResponse, LLMCall]:
        """Redact, write the llm_calls row, call the provider, finalize the row."""
        mode = redaction_mode or self._settings.shield_redaction_mode  # type: ignore[assignment]
        cleaned_payload, removed_counts = redact_payload(
            payload,
            mode=mode,
            client_org_name=client_org_name,
            name_hints=name_hints,
        )

        call_mode: LLMCallMode = (
            LLMCallMode.FIXTURE if self._settings.shield_llm_mode == "fixture" else LLMCallMode.LIVE
        )

        row = LLMCall(
            service_id=service_id,
            client_id=client_id,
            purpose=purpose,
            prompt_version=prompt_version,
            provider=self.provider.name,
            model=self.provider.model,
            mode=call_mode,
            status=LLMCallStatus.RUNNING,
            requested_by=requested_by,
            redacted_counts=removed_counts or None,
            correlation_id=correlation_id_var.get(),
        )
        db.add(row)
        db.flush()

        # Pass the purpose into the fixture so tests can register per-purpose
        # responses. Real providers strip __-prefixed control keys before egress
        # (see _egress_payload) so this never reaches the model.
        send_payload = {**cleaned_payload, "__purpose__": purpose}

        started = time.monotonic()
        try:
            response = self.provider.complete(prompt, send_payload)
        except Exception as exc:  # noqa: BLE001 - boundary; log + record + re-raise
            row.status = LLMCallStatus.FAILED
            row.error_message = f"{type(exc).__name__}: {exc}"
            row.duration_ms = int((time.monotonic() - started) * 1000)
            db.flush()
            _log.error(
                "llm_call_failed",
                purpose=purpose,
                provider=self.provider.name,
                error=row.error_message,
            )
            raise

        row.status = LLMCallStatus.COMPLETED
        row.input_tokens = response.input_tokens
        row.output_tokens = response.output_tokens
        row.duration_ms = int((time.monotonic() - started) * 1000)
        from app.models._common import utcnow as _utcnow

        row.completed_at = _utcnow()
        db.flush()

        _log.info(
            "llm_call_completed",
            purpose=purpose,
            provider=self.provider.name,
            model=self.provider.model,
            mode=call_mode.value,
            duration_ms=row.duration_ms,
            redacted=removed_counts,
        )
        return response, row


LLMMode = Literal["fixture", "live"]
