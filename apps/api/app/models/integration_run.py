"""Integration run: one client-level snapshot of the integration layer
(design note rev 4, sections 5 and 12; migration 0067).

A run records what it was computed FROM, at the time it ran, the way the Risk
Register's `provenance` does: the approved or released version of each service
it read (`inputs`), the crosswalk files and their sha256 (`crosswalks`), and the
code-computed cross-service findings (`findings`, section 12.4). It never
changes a score.

`inputs` per service: `{kind, version_id, version, approved_at}`, or
`{"not_included": "<reason>"}`; a service is never skipped silently.

NULL in any JSON column is "not recorded", never "none".

Nothing reads or writes this table yet (N4 is schema only).
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models._common import TimestampMixin, UUIDPKMixin

_JSON = JSON().with_variant(JSONB, "postgresql")


class IntegrationRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "integration_runs"

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    inputs: Mapped[dict | None] = mapped_column(_JSON)
    crosswalks: Mapped[list | None] = mapped_column(_JSON)
    findings: Mapped[list | None] = mapped_column(_JSON)
    ai_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_runs.id", ondelete="SET NULL")
    )
