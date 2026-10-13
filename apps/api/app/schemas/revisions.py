"""#1120 "Start a revision": the request body shared by ATT&CK, CSF and ZT."""

from __future__ import annotations

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
