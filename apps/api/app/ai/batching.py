"""Run one AI job as concurrent batches, inside a Run-AI run (#645).

Shared by `mitre_map` (routes/attack.py) and `csf_score` (routes/csf.py, #479),
which split one job too large for any provider's output cap into many calls.
Each caller decides how its job splits and what a batch's answer means; this
decides how the batches run, fail and are accounted for, in one place.

`risk_synthesize` (routes/risk.py) still has its own copy of this loop, without
the run deadline or #797's stop on a credential rejection: Risk does not run in
the background yet (#504), and was set aside on 2026-09-27. Moving it here is
that service's change to make, and brings both with it.
"""

from __future__ import annotations

import contextvars
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.engine import get_job, run_job
from app.ai.failures import AI_CALL_FAILED, ai_call_boundary, is_credential_rejection
from app.ai.llm import LLMClient
from app.ai.runs import RUN_DEADLINE_EXCEEDED, RunFailed
from app.logging import get_logger
from app.models._common import utcnow

_log = get_logger(__name__)


class _NotSent(Exception):
    """A batch its worker did not send, because a credential rejection had
    already stopped the run (#797). Never counted as an attempt or an error."""


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
    failure raises, typed through `ai_call_boundary` as it always was, as a
    `RunFailed` carrying the batch counts.

    A CREDENTIAL REJECTION is the one failure that stops the run (#797,
    `failures.is_credential_rejection`): every later call with the same key is
    refused the same way. No batch STARTS after the first rejection, so a bad
    key costs at most `max_workers` calls -- the ones already in flight --
    instead of one per batch. Any other failure -- a rate limit, a 5xx, a
    timeout, a malformed answer -- costs its batch and the run goes on.

    ANY OTHER EXCEPTION raised while the caller waits for results -- a Ctrl-C,
    a failure in the caller's own thread -- cancels every batch not yet
    started and is re-raised UNCHANGED (#806). Before, only the deadline
    cancelled them, and queued batches went on to bill after the caller had
    stopped listening.

    The single-call purposes (`zt_score`, `extract.capabilities`) do not come
    through here: one call already stops at its first failure.
    """
    if not batch_inputs:
        # A caller with nothing to split still makes one call (an empty batch);
        # it says so by passing one. An empty list here is a caller's bug.
        raise ValueError(f"{job_name}: no batches to run")
    batches = batch_inputs
    # #797: set by the first worker whose call comes back as a credential
    # rejection, and read by every worker BEFORE it calls. Set in the worker,
    # not by the collecting thread: a provider that refuses instantly lets
    # workers start many batches before the collector sees the first 401, and
    # cancelling futures from there would not bound the calls. With the flag,
    # no call starts after the first rejection lands, so a bad key costs at
    # most one call per worker.
    stop = threading.Event()

    def _one(inputs: dict[str, Any]) -> dict:
        if stop.is_set():
            raise _NotSent()
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
        except Exception as exc:
            if is_credential_rejection(exc):
                stop.set()
            # Mirror ai_call_boundary: commit so the FAILED row survives the
            # exception, then let it propagate to be counted.
            try:
                session.commit()
            except Exception as commit_exc:  # noqa: BLE001 - logged; the cause wins
                # The ORIGINAL error must reach the collector (#800 review):
                # a commit failure raised in its place turned a rejected key
                # into a DB error -- after `stop` had already silenced every
                # later batch -- and the stop was never logged. So the commit
                # failure is LOGGED, loudly, and the cause is re-raised.
                _log.error(
                    f"{job_name}_batch_commit_failed",
                    service_id=str(service_id),
                    error=f"{type(commit_exc).__name__}: {commit_exc}",
                    cause=f"{type(exc).__name__}: {exc}",
                )
            raise exc
        finally:
            session.close()

    # Warm the job registry on THIS thread before any worker touches it. Lazy
    # registration behind a module flag is not something a worker should be the
    # first to trigger.
    get_job(job_name)

    answers: dict[int, dict[str, Any]] = {}
    failed = 0
    first_error: Exception | None = None
    # #797: the credential rejection that ended the run early, if one did.
    rejected: Exception | None = None
    attempted = 0

    pool = ThreadPoolExecutor(max_workers=max_workers)

    def _submit(indexes: range) -> dict:
        # Each worker runs inside a COPY of the caller's context. A pool thread
        # starts with an empty one, so `correlation_id_var` read None there and
        # every `llm_calls` row a batch wrote lost the request's correlation id
        # -- measured 2026-09-23, 0 of 52 live mitre_map rows carried one. A
        # fresh copy per submit, because one Context cannot be entered by two
        # threads at once. The copy carries the run id too (#645), so each
        # batch's row names its run.
        return {pool.submit(contextvars.copy_context().run, _one, batches[i]): i for i in indexes}

    def _collect(futures: dict) -> None:
        # #645: the job's overall deadline. All batches are submitted up front,
        # so there is no natural boundary to check it at; it is checked between
        # results, and `as_completed` is given the time remaining so one hung
        # provider stream cannot hold the run past it.
        nonlocal failed, first_error, rejected, attempted
        remaining = (deadline_at - utcnow()).total_seconds()
        for fut in as_completed(futures, timeout=max(remaining, 0)):
            if utcnow() > deadline_at:
                raise TimeoutError("past the run deadline")
            try:
                answers[futures[fut]] = fut.result()
                attempted += 1
            except _NotSent:
                # #797: its worker saw the stop flag. No answer, no call.
                continue
            except Exception as exc:  # noqa: BLE001 - counted, not swallowed
                attempted += 1
                failed += 1
                first_error = first_error or exc
                _log.error(
                    f"{job_name}_batch_failed",
                    service_id=str(service_id),
                    error=f"{type(exc).__name__}: {exc}",
                )
                if rejected is None and is_credential_rejection(exc):
                    # #797: recorded for the log line below. The stop itself is
                    # the worker's `stop` flag: every batch not yet started
                    # returns `_NotSent` without calling, and one already inside
                    # a provider call finishes into its own `llm_calls` row.
                    rejected = exc

    try:
        # Every batch at once, as before #797. A first batch run alone would
        # bound a bad key to one call, at the price of a whole batch round
        # trip -- tens of seconds on a large model -- on EVERY successful run,
        # to save at most `max_workers - 1` calls that are refused at auth and
        # not billed. The stop flag bounds it at `max_workers` instead.
        _collect(_submit(range(len(batches))))
    except TimeoutError as exc:
        # Batches not yet started are cancelled; one already inside a provider
        # call cannot be, and is left to finish into its own `llm_calls` row.
        pool.shutdown(wait=False, cancel_futures=True)
        _log.error(f"{job_name}_deadline_exceeded", service_id=str(service_id))
        raise RunFailed(RUN_DEADLINE_EXCEEDED, deadline_message) from exc
    except BaseException as exc:
        # #806 (the advisor's option (b) on #736): ANY other exception while
        # waiting -- a Ctrl-C, a failure in the caller's thread -- cancels the
        # queued batches too. Before this only the deadline did, so they went
        # on to start, and bill, after the caller had stopped listening. The
        # stop flag also turns away a batch a worker has just dequeued; one
        # already inside a provider call cannot be cancelled and finishes into
        # its own `llm_calls` row. The ORIGINAL exception is re-raised
        # unchanged: callers type it themselves.
        stop.set()
        pool.shutdown(wait=False, cancel_futures=True)
        _log.error(
            f"{job_name}_batches_cancelled",
            service_id=str(service_id),
            error=type(exc).__name__,
        )
        raise
    pool.shutdown(wait=True)

    # A batch with no answer is a failed batch, whether it was sent and failed
    # or was never sent because the key was rejected (#797). The caller's
    # "N of M batches failed" disclosure counts every missing answer.
    failed = len(batches) - len(answers)
    if rejected is not None:
        _log.error(
            f"{job_name}_stopped_on_credential_rejection",
            service_id=str(service_id),
            attempted=attempted,
            planned=len(batches),
            answered=len(answers),
            error=f"{type(rejected).__name__}: {rejected}",
        )

    if not answers and first_error is not None:
        # Nothing usable came back. Re-raise inside the boundary so the error
        # is typed exactly as it always was -- `ai_call_failed`, the same
        # friendly message, `charged_likely` -- and then carry the batch counts
        # to the run (#797): every planned batch came back without an answer.
        # The rejection, when there is one, whatever finished first: it is the
        # error that stopped the run, and the message must say so (#797).
        cause = rejected or first_error
        try:
            with ai_call_boundary(db, llm, purpose=job_name):
                raise cause
        except HTTPException as typed:
            detail = typed.detail if isinstance(typed.detail, dict) else {}
            raise RunFailed(
                str(detail.get("reason") or AI_CALL_FAILED),
                str(detail.get("message") or typed.detail),
                batches=(len(batches), len(batches)),
            ) from cause

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
