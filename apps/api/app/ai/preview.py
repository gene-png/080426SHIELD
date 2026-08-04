"""Shared run-ai payload contract for the redaction-preview gate (Sprint 5 T6).

`POST /ai/preview` must show EXACTLY what a real Run-AI would egress. To make
divergence impossible, each service's run-ai and the preview route build their
outbound payload through ONE function per service (``build_*_ai_request`` in the
service route module). That function returns a service-specific request object
that carries an :class:`AiPreviewPayload` — the redaction-relevant inputs
(``job_name``, ``inputs``, ``client_org_name``, ``name_hints``) that
``LLMClient.invoke`` would redact and send. The preview route runs that payload
through ``redact_payload`` WITHOUT writing an ``llm_calls`` row or constructing a
provider; run-ai runs the identical payload through ``run_job``. Same source,
never drifts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AiPreviewPayload:
    """The exact inputs a run-ai job would hand to ``LLMClient.invoke``.

    ``job_name`` is the AI engine job key (its ``call_purpose`` is the
    ``llm_calls.purpose`` the real run would record). ``inputs`` is the payload
    dict; ``client_org_name`` and ``name_hints`` are the redaction parameters the
    run-ai path passes. Everything here — and only this — determines the redacted
    payload and removed counts.
    """

    job_name: str
    inputs: dict[str, Any]
    client_org_name: str | None = None
    name_hints: tuple[str, ...] = field(default_factory=tuple)
