"""AI-related request/response schemas (Sprint 5 T6: redaction preview)."""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel


class AiPreviewRequest(BaseModel):
    """Which service's next Run-AI to preview. Tenant is resolved from the
    caller (client pinned by user, admin via X-Client-Id), like run-ai itself."""

    service_id: uuid.UUID


class AiPreviewResponse(BaseModel):
    """What a real Run-AI would egress, AFTER redaction — never sent anywhere.

    ``payload`` is the redacted outbound payload (the same object the provider
    would receive); ``removed_counts`` is what the redactor stripped, keyed by
    category (pii kind / name / address / client_org). No ``llm_calls`` row is
    written and no provider is constructed to produce this.
    """

    purpose: str
    redaction_mode: str
    payload: dict[str, Any]
    removed_counts: dict[str, int]
