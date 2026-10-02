"""Turn a provider failure into a typed, auditable outcome.

Found by the 2026-08-04 live run. A provider error propagated out of the
run-AI endpoints as an unhandled exception, so:

  * FastAPI returned a bare 500 with no ``reason``/``message``, and the
    workspace sat on "Running…" forever because nothing typed ever reached it;
  * the request transaction rolled back, taking the ``llm_calls`` row that
    ``LLMClient.invoke`` had already marked FAILED with it. Three real
    Anthropic calls consumed tokens and left ZERO rows behind.

``llm_calls`` is the egress evidence for a FedRAMP-targeted deployment. A call
that happened must leave a record even when it fails.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

import anthropic
import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.llm import LLMClient
from app.logging import get_logger

_log = get_logger(__name__)

AI_CALL_FAILED = "ai_call_failed"


def friendly_reason(exc: BaseException) -> str:
    """Plain-language cause an admin can act on, with the raw detail kept."""
    text = f"{type(exc).__name__}: {exc}"
    if re.search(r"stop_reason=max_tokens|MAX_TOKENS|did not finish cleanly", text):
        return (
            "The AI response was cut off before it finished, so nothing was applied. "
            "This usually means the draft exceeded the output budget for this job. "
            f"({text})"
        )
    # A read timeout is OUR client giving up, not the provider hanging up, and
    # it was folded into the branch below telling the admin to retry. For a job
    # too large to finish inside the limit on a non-streamed provider, every
    # retry times out the same way and is billed again -- so this copy says what
    # happened and does not promise a retry will help.
    # ReadTimeout only, deliberately: a ConnectTimeout is a case where a
    # retry CAN help, and it keeps the generic copy below.
    if re.search(r"ReadTimeout", text):
        return (
            "The AI provider did not finish within SHIELD's time limit for a single "
            "call, so nothing was applied. A job this large can hit that limit on "
            f"every attempt with this provider. ({text})"
        )
    if re.search(r"APIConnectionError|RemoteProtocolError|Server disconnected", text):
        return (
            "The AI provider closed the connection before responding. Nothing was "
            f"applied; you can retry. ({text})"
        )
    if re.search(r"AIResponseShapeError", text):
        return (
            "The AI returned a response in the wrong format, so nothing was applied. "
            "Re-run to try again; if it repeats, the prompt and the parser have "
            f"drifted apart. ({text})"
        )
    if re.search(r"401|Unauthorized|authentication", text, re.IGNORECASE):
        return f"The AI provider rejected the configured API key. ({text})"
    if re.search(r"429|rate.?limit", text, re.IGNORECASE):
        return f"The AI provider rate-limited this request. Try again shortly. ({text})"
    return f"The AI call failed and nothing was applied. ({text})"


#: HTTP statuses that mean the provider refused our CREDENTIALS, not the
#: request: every later call with the same key is refused the same way (#797).
_CREDENTIAL_STATUSES = frozenset({401, 403})


def is_credential_rejection(exc: BaseException) -> bool:
    """True when a provider refused the key itself, so retrying is pointless.

    TYPED, never a match on message text: `friendly_reason` above matches
    "401|authentication" in the text, which is right for choosing copy and
    wrong for deciding to stop a run. Two shapes, one per adapter family:

    * the Anthropic SDK raises an `APIStatusError` subclass carrying
      `status_code` (`AuthenticationError` 401, `PermissionDeniedError` 403);
    * the OpenAI, Gemini and Vertex adapters call `raise_for_status()`, which
      raises `httpx.HTTPStatusError` with the response's status.

    NOT a rejection, deliberately: 429 (rate limit), 5xx, timeouts, a dropped
    connection, a truncated or malformed answer -- each can succeed on the next
    batch. And not 400, although Gemini answers a bad key with 400
    API_KEY_INVALID: stopping on 400 would also stop on a genuine bad request,
    so on Gemini a bad key still costs one call per batch. Known, and narrower
    is the safe direction.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _CREDENTIAL_STATUSES
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in _CREDENTIAL_STATUSES
    return False


@contextmanager
def ai_call_boundary(db: Session, llm: LLMClient, *, purpose: str) -> Iterator[None]:
    """Wrap a Run-AI call so a provider failure is typed and leaves evidence.

    ``db.commit()`` on the failure path is deliberate: ``invoke`` has already
    written the FAILED row into this session, and letting the exception escape
    would roll it back. The run-AI endpoints only READ before reaching the
    model, so the audit row is the only pending work at this point.
    """
    try:
        yield
    except StarletteHTTPException:
        # Already typed (e.g. MissingFixtureError -> 503). Leave it alone.
        raise
    except Exception as exc:
        db.commit()
        charged_likely = llm.provider.name != "fixture"
        _log.error(
            "ai_call_boundary_failed",
            purpose=purpose,
            provider=llm.provider.name,
            charged_likely=charged_likely,
            error=f"{type(exc).__name__}: {exc}",
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "reason": AI_CALL_FAILED,
                "message": friendly_reason(exc),
                "charged_likely": charged_likely,
            },
        ) from exc
