"""Run one AI job as concurrent batches, inside a Run-AI run (#645).

Shared by `mitre_map` (routes/attack.py) and `csf_score` (routes/csf.py, #479),
which split one job too large for any provider's output cap into many calls.
Each caller decides how its job splits and what a batch's answer means; this
decides how the batches run, fail and are accounted for, in one place.

`risk_synthesize` (routes/risk.py) still has its own copy of this loop, without
the run deadline: Risk does not run in the background yet (#504), and was set
aside on 2026-09-27. Moving it here is that service's change to make.
"""

from __future__ import annotations

import contextvars
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.engine import get_job, run_job
from app.ai.failures import ai_call_boundary
from app.ai.llm import LLMClient
from app.ai.runs import RUN_DEADLINE_EXCEEDED, RunFailed
from app.logging import get_logger
from app.models._common import utcnow

_log = get_logger(__name__)


@dataclass(frozen=True)
class Batched:
    """What came back. `answers` holds each SUCCESSFUL batch's parsed response,
    in batch order (not completion order), so a caller merging them reads the
    same sequence every run."""

    answers: list[dict[str, Any]]
    # The inputs each answer was given, index for index with `answers`, so a
    # caller can tell an answer about what it was asked from one that strays.
    inputs: list[dict[str, Any]]
    total: int
    failed: int


def run_batches(
    db: Session,
    llm: LLMClient,
    job_name: str,
    batch_inputs: list[dict[str, Any]],
    *,
    requested_by: uuid.UUID,
    service_id: uuid.UUID,
    client_id: uuid.UUID,
    client_org_name: str | None,
    name_hints: Any,
    deadline_at: datetime,
    max_workers: int,
    deadline_message: str,
) -> Batched:
    """Run `job_name` once per entry of `batch_inputs`, concurrently.

    Each batch is a real `run_job` call and therefore writes its own `llm_calls`
    row -- N rows per run instead of one. That is the honest accounting: N
    provider calls were made and each is separately billable.

    Each worker gets its OWN Session. A SQLAlchemy Session is not thread-safe,
    and the caller's `db` belongs to the caller; sharing it across threads
    corrupts state. Each worker commits its own `llm_calls` row so evidence of a
    call survives independently of whether its siblings succeed.

    A partial failure does NOT discard the run. Losing 1 batch of 26 should cost
    the consultant that batch's rows, not all of them and the money already
    spent on them; the caller discloses `failed` of `total`. Only a total
    failure raises, and it raises through `ai_call_boundary` so the error stays
    typed and carries `charged_likely`.
    """
    if not batch_inputs:
        # A caller with nothing to split still makes one call (an empty batch);
        # it says so by passing one. An empty list here is a caller's bug.
        raise ValueError(f"{job_name}: no batches to run")
    batches = batch_inputs

    def _one(inputs: dict[str, Any]) -> dict:
        # Bind to the CALLER's engine, not the module-level SessionLocal:
        # reaching for SessionLocal opens a connection outside whatever the
        # caller is bound to, which silently bypassed the test suite's
        # dependency-injected engine and broke isolation across test files.
        session = Session(bind=db.get_bind())
        try:
            out = run_job(
                session,
                llm,
                job_name,
                inputs=inputs,
                requested_by=requested_by,
                service_id=service_id,
                client_id=client_id,
                client_org_name=client_org_name,
                name_hints=name_hints,
            )
            session.commit()
            # Guaranteed a dict by `parse_json_object`; a wrong shape raises
            # and is counted as a failed batch rather than a silent empty one.
            return out.data
        except Exception:
            # Mirror ai_call_boundary: commit so the FAILED row survives the
            # exception, then let it propagate to be counted.
            session.commit()
            raise
        finally:
            session.close()

    # Warm the job registry on THIS thread before any worker touches it. Lazy
    # registration behind a module flag is not something a worker should be the
    # first to trigger.
    get_job(job_name)

    answers: dict[int, dict[str, Any]] = {}
    failed = 0
    first_error: Exception | None = None

    pool = ThreadPoolExecutor(max_workers=max_workers)
    # #645: the job's overall deadline. All batches are submitted up front, so
    # there is no natural boundary to check it at; it is checked between
    # results, and `as_completed` is given the time remaining so one hung
    # provider stream cannot hold the run past it.
    remaining = (deadline_at - utcnow()).total_seconds()
    try:
        # Each worker runs inside a COPY of the caller's context. A pool thread
        # starts with an empty one, so `correlation_id_var` read None there and
        # every `llm_calls` row a batch wrote lost the request's correlation id
        # -- measured 2026-09-23, 0 of 52 live mitre_map rows carried one. A
        # fresh copy per submit, because one Context cannot be entered by two
        # threads at once. The copy carries the run id too (#645), so each
        # batch's row names its run.
        futures = {
            pool.submit(contextvars.copy_context().run, _one, b): i for i, b in enumerate(batches)
        }
        for fut in as_completed(futures, timeout=max(remaining, 0)):
            if utcnow() > deadline_at:
                raise TimeoutError("past the run deadline")
            try:
                answers[futures[fut]] = fut.result()
            except Exception as exc:  # noqa: BLE001 - counted, not swallowed
                failed += 1
                first_error = first_error or exc
                _log.error(
                    f"{job_name}_batch_failed",
                    service_id=str(service_id),
                    error=f"{type(exc).__name__}: {exc}",
                )
    except TimeoutError as exc:
        # Batches not yet started are cancelled; one already inside a provider
        # call cannot be, and is left to finish into its own `llm_calls` row.
        pool.shutdown(wait=False, cancel_futures=True)
        _log.error(f"{job_name}_deadline_exceeded", service_id=str(service_id))
        raise RunFailed(RUN_DEADLINE_EXCEEDED, deadline_message) from exc
    pool.shutdown(wait=True)

    if failed == len(batches) and first_error is not None:
        # Nothing usable came back. Re-raise inside the boundary so the caller
        # gets the same typed failure + charged_likely it always did.
        with ai_call_boundary(db, llm, purpose=job_name):
            raise first_error

    _log.info(
        f"{job_name}_batched",
        service_id=str(service_id),
        batches_total=len(batches),
        batches_failed=failed,
    )
    done = sorted(answers)
    return Batched(
        answers=[answers[i] for i in done],
        inputs=[batches[i] for i in done],
        total=len(batches),
        failed=failed,
    )
