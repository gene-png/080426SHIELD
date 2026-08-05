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
    if re.search(r"APIConnectionError|RemoteProtocolError|Server disconnected|ReadTimeout", text):
        return (
            "The AI provider closed the connection before responding. Nothing was "
            f"applied; you can retry. ({text})"
        )
    if re.search(r"401|Unauthorized|authentication", text, re.IGNORECASE):
        return f"The AI provider rejected the configured API key. ({text})"
    if re.search(r"429|rate.?limit", text, re.IGNORECASE):
        return f"The AI provider rate-limited this request. Try again shortly. ({text})"
    return f"The AI call failed and nothing was applied. ({text})"


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
