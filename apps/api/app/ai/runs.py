"""Run-AI in the background (#645): start, execute, finish, reap.

A Run-AI used to be one HTTP request, and ATT&CK's ~26 batched provider calls
outlast the request timeout: the browser gave up while the server carried on.
Now a POST validates, inserts an `ai_runs` row and answers 202; a background
job does the work and finishes the row; the workspace polls the row.

THE RULES, each one a thing that would otherwise go wrong silently:

* One RUNNING run per service and purpose, enforced by the partial unique
  index `uq_ai_runs_one_running` (migration 0057), not by a read. Two first
  POSTs racing both read "nothing running"; the index refuses the second
  insert and the POST re-reads and joins.
* A second POST JOINS a run only when it acknowledged the same mode. A
  consultant who acknowledged offline is never handed a live run (#504).
* The job finishes with a COMPARE-AND-SWAP on `status = 'RUNNING'`, in the
  same transaction as the apply. A run the reaper already ended matches zero
  rows, and the apply is rolled back: a reaped run never applies late.
* Every failure is a terminal FAILED state with a typed reason. Nothing raises
  into a background thread where nobody would see it.
* The job opens its own Session bound to the REQUEST's engine
  (`db.get_bind()`), never `SessionLocal`, and runs inside a copy of the
  request's context, so the correlation id reaches every `llm_calls` row.

THE ONE-PROCESS PRECONDITION. The reaper below decides a RUNNING run has no job
behind it by asking THIS process: a run started by another boot, or absent
from this process's live set, is orphaned. That is only true while the api is
ONE process. It is today: compose runs `uvicorn --reload` and the Dockerfile
sets no `--workers`. A multi-worker deploy would have every worker reaping its
siblings' live runs, so it needs a shared liveness signal (a heartbeat column)
before it can ship.
"""

from __future__ import annotations

import contextvars
import functools
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks, HTTPException, status
from sqlalchemy import exists, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.failures import friendly_reason
from app.ai.llm import LLMClient
from app.ai.run_context import ai_run_id_var
from app.logging import correlation_id_var, get_logger
from app.models._common import utcnow
from app.models.ai_run import AiRun, AiRunStatus
from app.models.llm_call import LLMCall, LLMCallMode
from app.schemas.ai_runs import AiRunResponse, AiRunStarted, Serves

_log = get_logger(__name__)

#: This api process. A RUNNING run carrying any other value was started by a
#: process that no longer exists (see the module docstring's precondition).
BOOT_ID = str(uuid.uuid4())

#: How long a run may hold its service's edit lock. Sized above the longest
#: measured run: ATT&CK's 26 batches at 5 workers, ~30s of generation each
#: (`routes/attack.py`, `_MITRE_BATCH_SIZE`), is ~3 minutes when healthy, and a
#: rate-limited provider has been seen to stretch a single batch to minutes.
RUN_DEADLINE = timedelta(minutes=45)

#: How far past its deadline a run THIS process is still executing may go
#: before a status read ends it. The ATT&CK job checks its own deadline between
#: batches; this margin is for a job blocked inside one provider call, which
#: cannot check anything until the call returns.
REAP_MARGIN = timedelta(minutes=5)

RUN_ORPHANED = "run_orphaned"
RUN_DEADLINE_EXCEEDED = "run_deadline_exceeded"
RUN_CRASHED = "run_crashed"

# The runs THIS process is executing. Added by the POST before it answers 202,
# so a poll arriving before the background task starts does not reap the run;
# removed by the job in a `finally`.
_live: set[uuid.UUID] = set()
_live_lock = threading.Lock()


def _mark_live(run_id: uuid.UUID) -> None:
    with _live_lock:
        _live.add(run_id)


def _mark_done(run_id: uuid.UUID) -> None:
    with _live_lock:
        _live.discard(run_id)


def is_live(run_id: uuid.UUID) -> bool:
    with _live_lock:
        return run_id in _live


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def provider_serves(llm: LLMClient) -> Serves:
    """What a call through this client does: the provider decides, never the
    environment variable (D-037 promotes a stored key to live in fixture
    mode). The same test `LLMClient.invoke` uses to stamp `llm_calls.mode`."""
    return "offline" if llm.provider.name == "fixture" else "live"


def _mode_for(serves: Serves) -> LLMCallMode:
    return LLMCallMode.FIXTURE if serves == "offline" else LLMCallMode.LIVE


def serves_of(run: AiRun) -> Serves:
    return "offline" if run.mode == LLMCallMode.FIXTURE else "live"


def require_serves(value: str | None) -> Serves:
    """The acknowledged mode, or a typed 422. Required so the #504 guard cannot
    be skipped by leaving the field out."""
    if value in ("live", "offline"):
        return value  # type: ignore[return-value]
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "reason": "serves_required",
            "message": (
                "Run AI needs to know whether you expected it to run live or offline. "
                "Reload the page and run it again."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def _aware(dt: datetime) -> datetime:
    """SQLite hands back naive datetimes for timezone-aware columns; every
    value written here is UTC, so a naive one is UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _deadline_text(run: AiRun) -> str:
    return _aware(run.deadline_at).strftime("%H:%M UTC")


# ---------------------------------------------------------------------------
# Reaper
# ---------------------------------------------------------------------------


def _charged_likely(db: Session, run_id: uuid.UUID) -> bool:
    """Whether this run made a LIVE provider call, read from the egress
    record itself rather than from what the job thought it was doing: every
    call of the run stamps `ai_run_id` and its own `mode`."""
    return bool(
        db.execute(
            select(exists().where(LLMCall.ai_run_id == run_id, LLMCall.mode == LLMCallMode.LIVE))
        ).scalar()
    )


def _fail_if_running(
    db: Session, run_id: uuid.UUID, *, reason: str, message: str, charged_likely: bool | None
) -> bool:
    """End a run FAILED, only if it is still RUNNING. Returns whether it did."""
    res = db.execute(
        update(AiRun)
        .where(AiRun.id == run_id, AiRun.status == AiRunStatus.RUNNING)
        .values(
            status=AiRunStatus.FAILED,
            error_reason=reason,
            error_message=message,
            charged_likely=charged_likely,
            finished_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    return res.rowcount == 1


def _orphan_cause(run: AiRun, now: datetime) -> tuple[str, str] | None:
    """Why a RUNNING run has no job that will finish it, or None if one will.

    PRECONDITION: one api process (see the module docstring)."""
    if run.boot_id != BOOT_ID:
        return (
            RUN_ORPHANED,
            "The api restarted while this run was in progress, so it was stopped "
            "before it finished. Nothing from it was applied; run it again.",
        )
    if not is_live(run.id):
        return (
            RUN_ORPHANED,
            "This run stopped without recording an outcome. Nothing from it was "
            "applied; run it again.",
        )
    if now > _aware(run.deadline_at) + REAP_MARGIN:
        return (
            RUN_DEADLINE_EXCEEDED,
            "This run did not finish within its time limit, so it was stopped. "
            "Nothing from it was applied; run it again.",
        )
    return None


def reap(db: Session, *, service_id: uuid.UUID, purpose: str | None = None) -> None:
    """End every RUNNING run on this service that no job will finish.

    Takes the CALLER's session, never `SessionLocal` or the import-time engine:
    tests override `get_db` and point `DATABASE_URL` elsewhere after import, so
    anything bound to the module engine reaps the wrong database. Commits only
    when it ended something, before the caller has written anything.

    Called wherever a run is read -- the POST, the edit lock, the status read --
    rather than once at boot, so nothing can be locked by a run with no job
    behind it and the reaper needs no engine of its own.
    """
    q = select(AiRun).where(AiRun.service_id == service_id, AiRun.status == AiRunStatus.RUNNING)
    if purpose is not None:
        q = q.where(AiRun.purpose == purpose)
    now = utcnow()
    reaped = 0
    for run in db.execute(q).scalars().all():
        cause = _orphan_cause(run, now)
        if cause is None:
            continue
        reason, message = cause
        if _fail_if_running(
            db,
            run.id,
            reason=reason,
            message=message,
            charged_likely=_charged_likely(db, run.id),
        ):
            reaped += 1
            _log.warning(
                "ai_runs.reaped",
                run_id=str(run.id),
                service_id=str(service_id),
                purpose=run.purpose,
                reason=reason,
                run_boot_id=run.boot_id,
                boot_id=BOOT_ID,
            )
    if reaped:
        db.commit()


def running_run(db: Session, *, service_id: uuid.UUID, purpose: str | None = None) -> AiRun | None:
    """The run holding this service's lock, after reaping any that cannot."""
    reap(db, service_id=service_id, purpose=purpose)
    q = select(AiRun).where(AiRun.service_id == service_id, AiRun.status == AiRunStatus.RUNNING)
    if purpose is not None:
        q = q.where(AiRun.purpose == purpose)
    return db.execute(q.order_by(AiRun.started_at.desc())).scalars().first()


def refuse_while_running(db: Session, service_id: uuid.UUID) -> None:
    """The edit lock: a typed 409 while a run is in progress on this service.

    Approve and finalize are locked too: approving mid-run would approve rows
    about to change. DISCARD IS NOT -- D-031's contract is that a discard
    racing a run wins, and the job's re-read then ends the run FAILED
    `assessment_not_editable`. There is no manual unlock; a hung run is ended
    by its deadline, which the message states.
    """
    run = running_run(db, service_id=service_id)
    if run is None:
        return
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": "ai_run_in_progress",
            "message": (
                "An AI run is in progress on this assessment, so editing is locked until "
                f"it finishes, or until {_deadline_text(run)} at the latest."
            ),
            "run_id": str(run.id),
            "deadline_at": _aware(run.deadline_at).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

#: Takes the job and arranges for it to run. Production hands it to FastAPI's
#: `BackgroundTasks`; tests inject one that DEFERS, because Starlette's
#: TestClient runs background tasks before `post()` returns, and a guard test
#: that never sees RUNNING proves nothing about the guard.
Runner = Callable[[Callable[[], None]], None]


def get_ai_run_runner(background_tasks: BackgroundTasks) -> Runner:
    """FastAPI dependency: run the job after the response is sent."""

    def run(job: Callable[[], None]) -> None:
        background_tasks.add_task(job)

    return run


# ---------------------------------------------------------------------------
# The job
# ---------------------------------------------------------------------------


class RunFailed(Exception):
    """A typed terminal failure raised from inside a job."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(f"{reason}: {message}")
        self.reason = reason
        self.message = message


@dataclass
class RunOutcome:
    """What a job's work hands back for the completion compare-and-swap."""

    result: dict[str, Any]
    applied_count: int
    batches_total: int = 1
    batches_failed: int = 0


@dataclass(frozen=True)
class RunContext:
    """Plain values a job needs. Never request-bound ORM objects: the request
    session is closed by the time the job runs."""

    run_id: uuid.UUID
    service_id: uuid.UUID
    client_id: uuid.UUID
    requested_by: uuid.UUID
    started_at: datetime
    deadline_at: datetime
    llm: LLMClient
    extra: dict[str, Any] = field(default_factory=dict)

    def edited_since_start(self, updated_at: datetime | None) -> bool:
        """Whether a row's PRE-WRITE `updated_at` says a consultant edited it at
        or after this run started. At-or-after, so a same-tick edit is kept.

        Read the value BEFORE the job writes the row: `onupdate=utcnow` stamps
        every row the job touches, so a value read after the job's own flush
        would skip everything."""
        return updated_at is not None and _aware(updated_at) >= _aware(self.started_at)

    def past_deadline(self) -> bool:
        return utcnow() > _aware(self.deadline_at)


#: A service's job body. Runs in the job's own session; loads by id; calls the
#: AI inside `ai_call_boundary` and COMMITS straight after, so the `llm_calls`
#: rows survive a later rollback of the apply; applies with `flush()` only. The
#: framework commits the apply together with the completion swap.
Work = Callable[[Session, RunContext], RunOutcome]


def _failure_of(exc: BaseException) -> tuple[str, str]:
    """A typed (reason, message) for anything a job raised."""
    if isinstance(exc, RunFailed):
        return exc.reason, exc.message
    if isinstance(exc, HTTPException):
        # The synchronous run paths raise typed HTTP errors -- the D-031
        # re-read's 409 `assessment_not_editable`, `ai_call_boundary`'s 502
        # `ai_call_failed`. In a job they become the run's terminal state with
        # the SAME reason, so a consultant reads what they always read.
        detail = exc.detail
        if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
            return detail["reason"], str(detail.get("message") or detail["reason"])
        return f"http_{exc.status_code}", str(detail)
    return RUN_CRASHED, friendly_reason(exc)


def _execute(bind: Engine | Connection, ctx: RunContext, work: Work) -> None:
    """The background job. Never raises: every outcome is written to the run."""
    ai_run_id_var.set(ctx.run_id)
    session = Session(bind=bind)
    try:
        outcome = work(session, ctx)
        res = session.execute(
            update(AiRun)
            .where(AiRun.id == ctx.run_id, AiRun.status == AiRunStatus.RUNNING)
            .values(
                status=AiRunStatus.COMPLETED,
                result=outcome.result,
                applied_count=outcome.applied_count,
                batches_total=outcome.batches_total,
                batches_failed=outcome.batches_failed,
                charged_likely=_charged_likely(session, ctx.run_id),
                finished_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        if res.rowcount != 1:
            # Reaped while it worked. Its results must not land under a run the
            # workspace has already been told failed.
            session.rollback()
            _log.warning("ai_runs.completion_refused_reaped", run_id=str(ctx.run_id))
            return
        session.commit()
        _log.info(
            "ai_runs.completed",
            run_id=str(ctx.run_id),
            applied=outcome.applied_count,
            batches_total=outcome.batches_total,
            batches_failed=outcome.batches_failed,
        )
    except BaseException as exc:  # noqa: BLE001 - written to the run, never swallowed
        session.rollback()
        reason, message = _failure_of(exc)
        ended = _fail_if_running(
            session,
            ctx.run_id,
            reason=reason,
            message=message,
            charged_likely=_charged_likely(session, ctx.run_id),
        )
        session.commit()
        _log.error(
            "ai_runs.failed",
            run_id=str(ctx.run_id),
            reason=reason,
            recorded=ended,
            error=f"{type(exc).__name__}: {exc}",
        )
        if not isinstance(exc, Exception):
            raise  # KeyboardInterrupt / SystemExit are the process's, not the run's
    finally:
        session.close()
        _mark_done(ctx.run_id)


# ---------------------------------------------------------------------------
# Start
# ---------------------------------------------------------------------------

#: Called between the "is a run in progress" read and the insert. Exists so a
#: test can commit a competing run in that window and drive the savepoint
#: branch, which SQLite's serialised writers would otherwise never reach.
_between_read_and_insert: Callable[[], None] = lambda: None  # noqa: E731


def _started(run: AiRun, *, joined: bool) -> AiRunStarted:
    return AiRunStarted(
        run_id=run.id,
        status="running",
        serves=serves_of(run),
        deadline_at=_aware(run.deadline_at),
        joined=joined,
    )


def _join_or_refuse(run: AiRun, serves: Serves, subject_id: uuid.UUID) -> AiRunStarted:
    if run.subject_id != subject_id:
        # The run in progress is working on something else -- another document
        # for a Tech Debt extract. Handing back its id would tell this
        # consultant their document is being read when it is not (#644's
        # shape, one layer down).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "ai_run_in_progress_other_input",
                "message": (
                    "An AI run is already in progress here on a different input. Wait for "
                    f"it to finish, or until {_deadline_text(run)} at the latest, then "
                    "run it again."
                ),
                "run_id": str(run.id),
            },
        )
    if serves_of(run) == serves:
        _log.info("ai_runs.joined", run_id=str(run.id), serves=serves)
        return _started(run, joined=True)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "reason": "ai_run_in_progress_other_mode",
            "message": (
                f"An AI run is already in progress here, running {serves_of(run)}, not "
                f"{serves} as you expected. Wait for it to finish, or until "
                f"{_deadline_text(run)} at the latest, then run it again."
            ),
            "run_id": str(run.id),
        },
    )


def start_run(
    db: Session,
    *,
    llm: LLMClient,
    serves: Serves,
    service_id: uuid.UUID,
    client_id: uuid.UUID,
    purpose: str,
    subject_id: uuid.UUID,
    requested_by: uuid.UUID,
    runner: Runner,
    work: Work,
    extra: dict[str, Any] | None = None,
) -> AiRunStarted:
    """Start a run, or join the one in progress. The caller has already made
    every synchronous refusal its service makes (tenant, locked, catalog...).

    `llm` is the client the POST built once through the route's `_llm_dep`; the
    job is handed the SAME object, so the mode checked here is the mode called.
    """
    actual = provider_serves(llm)
    if serves == "offline" and actual == "live":
        # #504: the page loaded while AI was offline and the consultant chose to
        # continue offline; a key loaded since then would send this run, and the
        # client's data, to the provider. The reverse -- acknowledged live, now
        # offline -- serves canned output the acknowledgement already covers.
        _log.warning("ai_runs.refused_status_changed", service_id=str(service_id))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "reason": "ai_status_changed",
                "message": (
                    "AI was offline when this page loaded, and it would now run live and "
                    "send this client's data to the AI provider. Nothing was sent. Reload "
                    "the page to see the current AI status, then run it again."
                ),
            },
        )

    current = running_run(db, service_id=service_id, purpose=purpose)
    if current is not None:
        return _join_or_refuse(current, serves, subject_id)

    _between_read_and_insert()
    started_at = utcnow()
    deadline_at = started_at + RUN_DEADLINE
    run = AiRun(
        client_id=client_id,
        service_id=service_id,
        purpose=purpose,
        subject_id=subject_id,
        status=AiRunStatus.RUNNING,
        mode=_mode_for(actual),
        boot_id=BOOT_ID,
        requested_by=requested_by,
        correlation_id=correlation_id_var.get(),
        started_at=started_at,
        deadline_at=deadline_at,
    )
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        # A concurrent first POST inserted its run between our read and our
        # insert, and the unique index refused ours. Join it, or refuse it.
        _log.info("ai_runs.insert_lost_race", service_id=str(service_id), purpose=purpose)
        winner = db.execute(
            select(AiRun).where(
                AiRun.service_id == service_id,
                AiRun.purpose == purpose,
                AiRun.status == AiRunStatus.RUNNING,
            )
        ).scalar_one()
        return _join_or_refuse(winner, serves, subject_id)
    db.commit()

    ctx = RunContext(
        run_id=run.id,
        service_id=service_id,
        client_id=client_id,
        requested_by=requested_by,
        # The values written, not re-read: SQLite hands timestamps back naive.
        started_at=started_at,
        deadline_at=deadline_at,
        llm=llm,
        extra=extra or {},
    )
    # Live BEFORE the 202 leaves: a poll that beats the background task to the
    # start must not find a RUNNING run this process "is not executing".
    _mark_live(run.id)
    job_context = contextvars.copy_context()
    runner(functools.partial(job_context.run, _execute, db.get_bind(), ctx, work))
    _log.info(
        "ai_runs.started",
        run_id=str(run.id),
        service_id=str(service_id),
        purpose=purpose,
        serves=actual,
    )
    return _started(run, joined=False)


def to_response(run: AiRun) -> AiRunResponse:
    return AiRunResponse(
        id=run.id,
        service_id=run.service_id,
        purpose=run.purpose,
        status=run.status.value,  # type: ignore[arg-type]
        serves=serves_of(run),
        started_at=_aware(run.started_at),
        deadline_at=_aware(run.deadline_at),
        finished_at=_aware(run.finished_at) if run.finished_at else None,
        batches_total=run.batches_total,
        batches_failed=run.batches_failed,
        applied_count=run.applied_count,
        result=run.result,
        error_reason=run.error_reason,
        error_message=run.error_message,
        charged_likely=run.charged_likely,
    )
