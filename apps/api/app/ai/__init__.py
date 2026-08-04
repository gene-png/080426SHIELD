"""AI integration boundary.

Master Spec §12: PII redaction is a SECURITY BOUNDARY on every LLM call,
not a cosmetic step. SHIELD v1 accepts the risk of commercial LLM egress;
the redactor is the primary compensating control.

The redactor module (`app.ai.redact`) is intentionally small and pure -
no DB access, no network, no LLM client. It can be audited line-by-line.
The AI client (`app.ai.llm`, lands in Phase 3 stage 3) is the only path
that calls a provider; it MUST route every payload through the redactor
before send.
"""

from app.ai.redact import (
    RedactionMode,
    redact_for_ai,
    redact_payload,
)

__all__ = ["RedactionMode", "redact_for_ai", "redact_payload"]
