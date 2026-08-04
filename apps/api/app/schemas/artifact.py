"""Artifact request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.artifact import ArtifactOrigin


class ArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    mime_type: str
    size_bytes: int
    sha256: str
    origin: ArtifactOrigin
    stage: str | None
    uploaded_by: uuid.UUID
    uploaded_at: datetime
    notes: str | None


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]
