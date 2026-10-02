"""Run-AI run schemas (#645): the POST body, the 202, and the polled run."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AiSource(BaseModel):
    """Whether an assessment's AI suggestions came from a live model or test
    data (#646), as every surface states it. From `app.ai.mode_stamp.ai_mode_for`,
    the one derivation: the subject's COMPLETED runs, by mode."""

    state: Literal["live", "fixture", "mixed", "none", "unknown"]
    sentence: str
    live_runs: int
    fixture_runs: int


#: What the consultant acknowledged a Run-AI would do: call the provider, or
#: serve canned offline output. The AI status's third value, "broken", is never
#: something a run can be started under, so it is not one of these.
Serves = Literal["live", "offline"]


class RunAiRequest(BaseModel):
    """The Run-AI POST body.

    `serves` is typed `str | None` rather than `Serves` on purpose. A missing
    or unknown value is refused by the route with a typed `{reason, message}`
    422 (`serves_required`), the convention every Run-AI refusal already uses.
    A `Literal` here would hand the refusal to FastAPI's schema handler, which
    answers with a generic `schema_*` code no client copy maps (CLAUDE.md, the
    `Query(ge=...)` entry).
    """

    serves: str | None = None


class AiRunStarted(BaseModel):
    """The 202 a Run-AI POST answers with: the run to poll."""

    run_id: uuid.UUID
    status: Literal["running"]
    serves: Serves
    deadline_at: datetime
    # The latest the run can hold the lock: `deadline_at` plus the reaper's
    # margin. What every "locked until" says.
    lock_until: datetime
    # True when this POST found a run already in progress, in the same mode,
    # and handed back its id instead of starting a second one.
    joined: bool


class AiRunResponse(BaseModel):
    """One run, as the workspace polls it."""

    id: uuid.UUID
    service_id: uuid.UUID
    purpose: str
    # What the run worked on: the assessment, or the Tech Debt document. A
    # workspace shows a run's disclosures only for its own assessment.
    subject_id: uuid.UUID
    status: Literal["running", "completed", "failed"]
    serves: Serves
    started_at: datetime
    deadline_at: datetime
    lock_until: datetime
    finished_at: datetime | None
    batches_total: int | None
    batches_failed: int | None
    applied_count: int | None
    # Every disclosure the workspace renders about the run (#271). NULL until
    # the run completes; a FAILED run applied nothing and has none.
    result: dict[str, Any] | None
    error_reason: str | None
    error_message: str | None
    # NULL is "not known", which the workspace says, never "no".
    charged_likely: bool | None


class AiRunSummary(BaseModel):
    """What a workspace needs on load: is a run holding the lock, what did the
    newest run end as, and which run's results are the ones standing.

    `last_completed` is separate from `latest` for #271: a later total failure
    must not hide an earlier partial run whose data still stands.
    """

    running: AiRunResponse | None
    latest: AiRunResponse | None
    last_completed: AiRunResponse | None
