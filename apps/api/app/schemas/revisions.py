"""#1120 "Start a revision": the request body shared by ATT&CK, CSF and ZT."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RevisionStartRequest(BaseModel):
    #: Why this revision is started; saved in the audit row (V2b). Required.
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reason is required")
        return stripped


class RevisionInfo(BaseModel):
    """#1120: what a revision copied and why, for the V3, V4 and V5 banners.
    NULL on every record no revision minted."""

    #: The version the revision copied (V5's {v}).
    from_version: int
    #: Who started it, and when (V5's {name} and {date}).
    started_by_name: str
    started_at: datetime
    #: V5's {reason}, as typed.
    reason: str
    #: True when the source was approved under EARLIER rules (a stamp of 1),
    #: so some results may differ from what the client has (V3).
    rules_changed: bool
    #: ATT&CK codes the current catalog no longer holds, not copied (V4).
    retired_codes: list[str]
