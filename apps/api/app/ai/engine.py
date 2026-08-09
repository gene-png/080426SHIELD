"""AI engine: a small job registry over the single LLM egress path (Work Order C1).

Every AI feature runs through `run_job(job_name, ...)`. A job is just a prompt
template plus a result parser; the engine reuses `LLMClient.invoke` so redaction
and `llm_calls` logging happen once, in one place. Adding a new AI feature is a
new `AIJob` registration — no engine change.

The score/map/synthesize jobs return DRAFT SUGGESTIONS only (scores, statuses,
links, narrative). Deterministic math (totals, tiers, roll-ups) is never done by
the AI — it lives in the per-domain pure functions.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm import LLMClient
from app.models.llm_call import LLMCall


@dataclass(frozen=True)
class AIJob:
    """A registered AI job: a prompt + a parser for the provider's response."""

    name: str
    prompt: str
    parser: Callable[[str], Any]
    prompt_version: str = "v1"
    # The `llm_calls.purpose` + fixture key. Defaults to `name`; tech_debt keeps
    # its historical "extract.capabilities" purpose for fixture compatibility.
    purpose: str | None = None

    @property
    def call_purpose(self) -> str:
        return self.purpose or self.name


@dataclass(frozen=True)
class JobResult:
    data: Any
    llm_call: LLMCall


_REGISTRY: dict[str, AIJob] = {}
_REGISTERED_DEFAULTS = False


def register_job(job: AIJob) -> None:
    _REGISTRY[job.name] = job


def _ensure_defaults() -> None:
    global _REGISTERED_DEFAULTS
    if _REGISTERED_DEFAULTS:
        return
    # Import for side effect: registers the built-in jobs. Imported lazily to
    # avoid a circular import at module load.
    #
    # The flag is set AFTER the import, not before. Setting it first is a
    # check-then-set race: a second thread entering while the first is still
    # importing sees the flag already true, returns early, and then reads an
    # EMPTY registry. Every concurrent worker in the batched mitre_map run hit
    # exactly that — `No AI job registered as 'mitre_map'. Registered: ()`.
    # Re-entering the import is harmless: Python caches modules and
    # register_job() overwrites by name, so the worst case is idempotent work.
    from app.ai import jobs  # noqa: F401

    _REGISTERED_DEFAULTS = True


def get_job(name: str) -> AIJob:
    _ensure_defaults()
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"No AI job registered as {name!r}. Registered: {registered_jobs()}"
        ) from exc


def registered_jobs() -> tuple[str, ...]:
    _ensure_defaults()
    return tuple(sorted(_REGISTRY))


def run_job(
    db: Session,
    llm: LLMClient,
    job_name: str,
    *,
    inputs: dict[str, Any],
    requested_by: uuid.UUID,
    service_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> JobResult:
    """Run an AI job: redact + log (via LLMClient) + call + parse."""
    job = get_job(job_name)
    response, call_row = llm.invoke(
        db,
        purpose=job.call_purpose,
        prompt=job.prompt,
        payload=inputs,
        requested_by=requested_by,
        service_id=service_id,
        client_id=client_id,
        prompt_version=job.prompt_version,
        client_org_name=client_org_name,
        name_hints=tuple(name_hints),
    )
    return JobResult(data=job.parser(response.content), llm_call=call_row)


class AIResponseShapeError(ValueError):
    """The model returned valid JSON of the wrong SHAPE (issue #41).

    Distinct from a JSON syntax error: `json.loads` is perfectly happy with a
    bare list, so nothing downstream noticed. Every consumer then did
    ``data if isinstance(data, dict) else {}`` and discarded the whole response,
    reporting zero changes — indistinguishable from the model agreeing with
    everything. Raised so it travels the existing failure path instead: through
    `ai_call_boundary` to a typed 502 for a single-call job, or counted as a
    failed batch for a batched one. Either way the run is never silently empty.
    """


def parse_json_object(content: str) -> dict:
    """`parse_json`, but the top level MUST be an object.

    Every prompt that uses this mandates one — `{"scores": …}`,
    `{"capabilities": …}`, `{"entries": …}`, `{"techniques": …}` — so a
    non-object top level is always a contract violation and never a valid empty
    answer. A bare list is the likeliest drift: the model returns the array it
    was asked to nest under a key.
    """
    data = parse_json(content)
    if not isinstance(data, dict):
        raise AIResponseShapeError(
            "The AI response must be a JSON object with the expected top-level "
            f"key, but the top level was {type(data).__name__}. Nothing was applied."
        )
    return data


def parse_json(content: str) -> Any:
    """Best-effort JSON parse of an LLM response, tolerating ```json fences."""
    text = content.strip()
    if text.startswith("```"):
        parts = text.split("```")
        # ["", "json\n{...}", ""] or ["", "{...}", ""]
        if len(parts) >= 2:
            text = parts[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
    return json.loads(text.strip())
