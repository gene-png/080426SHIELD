"""Run one AI job N times on the same input and report how far the runs agree.

#806 step 1: the before-and-after measure every later prompt change is judged
by. Usage, inside a container that can reach no shared service:

    python -m scripts.measure_ai_consistency --job zt_score --framework cisa \
        --runs 2 --out /tmp/zt.json

WHAT IT REFUSES (exit 2), before any model call:
  * a DATABASE_URL that is not SQLite. A run writes `llm_calls` rows, and the
    compose file hardcodes the shared Postgres -- `docker compose run --no-deps`
    from ANY worktree joins that network -- so the only safe database is a
    throwaway file;
  * SHIELD_LLM_MODE other than `live`. Fixture mode echoes canned responses, so
    it would report perfect agreement about nothing;
  * SHIELD_REDACTION_MODE other than `strict`.

WHAT IT DOES: builds the payload with the route's own builder
(`routes/zt.py::_zt_ai_request_for`, `routes/csf.py::_csf_ai_request_for`) and
calls the model the way the route does -- `engine.run_job` inside
`ai_call_boundary` for zt_score, `run_batches` over `_csf_batch_inputs` for
csf_score -- so redaction, mode, batching and output caps are production's. It
parses with the job's registered parser.
It APPLIES NOTHING: no answer row is written. The one state change it can make
is `--reopen-released`, which sets a released assessment back to DRAFT so the
route's builder will accept it -- the demo seed releases every ZT assessment --
and which the report records as `input_setup`.

WHAT IT REPORTS, per pair of successful runs: the row set (in both / only in
one / unreadable / duplicated keys), and per field over rows present in both,
how many were compared and how many agreed. Every share carries its
denominator. It also reports the number the client would see, computed by the
engines rather than here: zt_score's gap count (`zt.scoring.analyze_gaps`) and
csf_score's per-row maturity level (`csf.playbook.score_tier`), with
agreement on the level per pair. For zt_score it reports how often the model
repeated the `current` stage it was sent (`echo`). Counts and codes only: no
model text reaches the output or the logs.

`--max-output-tokens N` starts no further run once N output tokens are spent.

EXIT: 0 every run succeeded; 1 a run failed, or fewer than two succeeded (the
report is still written, and names each failure); 2 refused.

`zt_score` and `csf_score` are implemented. `tech_debt_extract` needs an input
builder of its own (#806 step 5); asking for it now is refused rather than
approximated.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)

#: Jobs with an input builder here. `_job_shape` names each one's row list, key
#: and compared fields.
_IMPLEMENTED_JOBS = ("zt_score", "csf_score")


class Refused(Exception):
    """The environment is not one a measurement may run in."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class RunRecord:
    ok: bool
    data: dict | None
    failure: str | None
    input_tokens: int | None
    output_tokens: int | None
    # B3: a failed run's typed reason is often a constant (`ai_call_failed`),
    # so the underlying exception's TYPE name is kept too -- never its message,
    # which can quote the model -- with the boundary's `charged_likely`.
    cause: str | None = None
    charged_likely: bool | None = None


#: More runs than this is refused: every run is billed, and five pairs already
#: show an observed set rather than one value.
MAX_RUNS = 5


def preflight(*, database_url: str, llm_mode: str, redaction_mode: str) -> None:
    """Refuse unless this is a throwaway SQLite database, live mode and strict
    redaction. Each refusal names its own cause."""
    if not database_url.startswith("sqlite"):
        raise Refused(
            "database_not_sqlite",
            "DATABASE_URL must be a SQLite file: a measurement writes llm_calls rows "
            "and must never reach a shared database.",
        )
    if llm_mode != "live":
        raise Refused(
            "llm_mode_not_live",
            f"SHIELD_LLM_MODE is {llm_mode!r}; a measurement needs live mode "
            "(fixture responses agree with themselves by construction).",
        )
    if redaction_mode != "strict":
        raise Refused(
            "redaction_not_strict",
            f"SHIELD_REDACTION_MODE is {redaction_mode!r}; a measurement runs only "
            "with strict redaction.",
        )


def _job_shape(job: str) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """(list key, key fields, compared fields) for `job`. zt_score's are the
    route's own constants, imported rather than restated, so the measure
    compares exactly the fields the apply path reads."""
    if job == "zt_score":
        from app.routes.zt import _ROW_KEY_FIELDS, _ZT_ROW_FIELDS

        return "capabilities", _ROW_KEY_FIELDS, _ZT_ROW_FIELDS
    if job == "csf_score":
        # `what_we_found` is the route's sixth run field and is not compared:
        # free text differs in wording on every run.
        from app.routes.csf import _DIM_FIELDS
        from app.routes.csf import _ROW_KEY_FIELDS as _CSF_KEY_FIELDS

        return "scores", _CSF_KEY_FIELDS, _DIM_FIELDS
    raise Refused("job_not_implemented", f"{job!r} has no measure yet; see the module docstring.")


def _is_whole(v: Any) -> bool:
    """A JSON integer. `True` is an int in Python and is not one here."""
    return type(v) is int


def _same(a: Any, b: Any) -> bool:
    """Equal AND of the same JSON type, so `true` never matches `1`."""
    return type(a) is type(b) and a == b


def _index(rows: Sequence[Any], key_fields: tuple[str, ...]) -> tuple[dict, int, int]:
    """Rows by key. A non-object row is unreadable; a key seen twice is ambiguous
    and indexes neither copy. Returns (index, unreadable, extra copies of a
    repeated key)."""
    seen: dict[tuple, Any] = {}
    dupes: set[tuple] = set()
    unreadable = extra_copies = 0
    for row in rows:
        if not isinstance(row, dict):
            unreadable += 1
            continue
        key = tuple(json.dumps(row.get(f), sort_keys=True) for f in key_fields)
        if key in seen or key in dupes:
            dupes.add(key)
            extra_copies += 1
        seen[key] = row
    for key in dupes:
        seen.pop(key, None)
    return seen, unreadable, extra_copies


def compare_pair(job: str, a: Mapping[str, Any], b: Mapping[str, Any]) -> dict:
    """Agreement between two parsed responses: row set, then per field over the
    rows present in both. Every count is a denominator or a numerator of one."""
    list_key, key_fields, fields = _job_shape(job)
    ia, unread_a, dup_a = _index(a.get(list_key) or [], key_fields)
    ib, unread_b, dup_b = _index(b.get(list_key) or [], key_fields)
    both = sorted(set(ia) & set(ib))
    out_fields: dict[str, dict] = {}
    for f in fields:
        compared = equal = within_one = missing_a = missing_b = 0
        diffs: list[int] = []
        for k in both:
            ra, rb = ia[k], ib[k]
            if f not in ra:
                missing_a += 1
            if f not in rb:
                missing_b += 1
            if f not in ra or f not in rb:
                continue
            compared += 1
            va, vb = ra[f], rb[f]
            if _same(va, vb):
                equal += 1
            if _is_whole(va) and _is_whole(vb):
                diffs.append(abs(va - vb))
                if abs(va - vb) <= 1:
                    within_one += 1
        out_fields[f] = {
            "compared": compared,
            "equal": equal,
            "within_one": within_one,
            "mean_abs_diff": (sum(diffs) / len(diffs)) if diffs else None,
            "missing_in_a": missing_a,
            "missing_in_b": missing_b,
        }
    return {
        "rows": {
            "in_both": len(both),
            "only_in_a": len(set(ia) - set(ib)),
            "only_in_b": len(set(ib) - set(ia)),
            "unreadable_a": unread_a,
            "unreadable_b": unread_b,
            "duplicate_keys_a": dup_a,
            "duplicate_keys_b": dup_b,
        },
        "fields": out_fields,
    }


def _zt_sent_current(inputs: Mapping[str, Any], code: Any) -> Any:
    answer = (inputs.get("answers") or {}).get(code) if isinstance(code, str) else None
    return answer.get("current") if isinstance(answer, dict) else None


#: Per job, the compared fields whose value the payload already SENDS, and how
#: to read the sent value for a row. Agreement on such a field can be the model
#: repeating its input on both runs rather than judging twice; `echo_share`
#: says how much. zt_score sends each capability's stored `current` and no
#: target (`routes/zt.py::_zt_ai_request_for`).
_ECHO_FIELDS: dict[str, dict[str, Any]] = {
    "zt_score": {"current": _zt_sent_current},
}


def echo_share(job: str, inputs: Mapping[str, Any], data: Mapping[str, Any]) -> dict:
    """For one run: of the rows where something was sent AND the model answered
    the field, how many answers equal (same JSON type) what was sent. Rows sent
    nothing are counted apart, since there was nothing to repeat."""
    list_key, key_fields, _ = _job_shape(job)
    out: dict[str, dict[str, int]] = {}
    for field, sent_value in _ECHO_FIELDS.get(job, {}).items():
        answered = echoed = nothing_sent = 0
        for row in data.get(list_key) or []:
            if not isinstance(row, dict) or field not in row:
                continue
            sent = sent_value(inputs, row.get(key_fields[0]))
            if sent is None:
                nothing_sent += 1
                continue
            answered += 1
            if _same(sent, row[field]):
                echoed += 1
        out[field] = {"sent_and_answered": answered, "echoed": echoed, "nothing_sent": nothing_sent}
    return out


def zt_downstream(framework: Any, *, engagement_stage: int, data: Mapping[str, Any]) -> dict:
    """The gaps a client would see if every value in `data` were applied,
    counted by the engine (`analyze_gaps`) with no truncation.

    Only whole-number stages are passed on; anything else is counted in
    `non_integer_values` and treated as absent, because the engine's own
    validator calls `int()`, which would read `true` as 1 and `"2"` as 2.
    A whole number outside the framework's stages is passed on (the engine
    treats it as unscored, or an unusable target) and ALSO counted in
    `out_of_range_values`, so a run of stage 9s cannot read as a run that
    simply left rows blank. `unusable_target_codes` is the engine's own list.
    Rows the real apply path would skip (locked, protected, edited) are not
    modelled: this is what the model ASKED for, not what a run would write.
    """
    from app.zt.catalog import capabilities
    from app.zt.maturity import level_count
    from app.zt.scoring import analyze_gaps

    max_stage = level_count(framework)
    out_of_range = 0

    answers: dict[str, int] = {}
    targets: dict[str, int] = {}
    non_integer = 0
    for row in data.get("capabilities") or []:
        if not isinstance(row, dict) or not isinstance(row.get("code"), str):
            continue
        for field, dest in (("current", answers), ("target", targets)):
            if field not in row or row[field] is None:
                continue
            if _is_whole(row[field]):
                dest[row["code"]] = row[field]
                if not 1 <= row[field] <= max_stage:
                    out_of_range += 1
            else:
                non_integer += 1
    gaps = analyze_gaps(
        framework,
        answers,
        targets=targets,
        target_stage=engagement_stage,
        top_n=len(capabilities(framework)),
    )
    return {
        "gap_codes": sorted(g.code for g in gaps.gaps),
        "total_gap_count": gaps.total_gap_count,
        "unscored_count": len(gaps.unscored_codes),
        "non_integer_values": non_integer,
        "out_of_range_values": out_of_range,
        "unusable_target_codes": sorted(gaps.unusable_target_codes),
    }


def csf_levels(data: Mapping[str, Any], *, has_evidence: Mapping[str, bool]) -> dict:
    """Each row's maturity level, by `csf.playbook.score_tier` -- the number a
    client sees per (tier, subcategory) -- keyed "tier|subcategory_code" as the
    route keys its rows.

    Only a row whose five dimensions are all whole numbers 0-2 is scored. The
    engine's `clamped()` calls `int()` and clamps, so it would read 3 as 2,
    `true` as 1 and "2" as 2; such a row is counted in `not_scoreable` instead.
    `has_evidence` is the stored row's flag, as the route passes it."""
    from app.csf.playbook import DimensionScores, score_tier
    from app.routes.csf import _DIM_FIELDS

    levels: dict[str, int] = {}
    not_scoreable = 0
    for row in data.get("scores") or []:
        if not isinstance(row, dict):
            continue
        key = f"{row.get('tier')}|{row.get('subcategory_code')}"
        dims = [row.get(f) for f in _DIM_FIELDS]
        if key not in has_evidence or not all(_is_whole(d) and 0 <= d <= 2 for d in dims):
            not_scoreable += 1
            continue
        result = score_tier(
            DimensionScores(**dict(zip(_DIM_FIELDS, dims, strict=True))),
            has_evidence=has_evidence[key],
        )
        levels[key] = result.level
    return {"levels": levels, "not_scoreable": not_scoreable}


def run_loop(
    runs: int,
    one_run: Callable[[int], RunRecord],
    *,
    max_output_tokens: int | None,
    stop_on_failure: bool = False,
) -> list[RunRecord]:
    """Call `one_run(n)` for n = 1..runs. Once the output tokens spent exceed
    `max_output_tokens`, no further run STARTS; each one not started is recorded
    as failed (`stopped_output_budget`). A run already under way is never cut
    off, so the overrun is bounded by one run's output. With `stop_on_failure`,
    no run starts after a failed one (`stopped_after_failure`): a rate-limited
    provider is not retried into."""
    records: list[RunRecord] = []
    spent = 0
    for n in range(1, runs + 1):
        if stop_on_failure and any(not r.ok for r in records):
            records.append(RunRecord(False, None, "stopped_after_failure", 0, 0))
            continue
        if max_output_tokens is not None and spent > max_output_tokens:
            _log.warning("measure_ai_consistency.budget_stop", run=n, output_tokens=spent)
            records.append(RunRecord(False, None, "stopped_output_budget", 0, 0))
            continue
        record = one_run(n)
        spent += record.output_tokens or 0
        records.append(record)
    return records


def summarize(job: str, runs: Sequence[RunRecord]) -> dict:
    """Every pair of successful runs, plus the failed runs by number (1-based).
    Fewer than two successes is a failure: there is nothing to compare."""
    ok = [(i + 1, r) for i, r in enumerate(runs) if r.ok]
    pairs = [
        {"pair": [i, j], **compare_pair(job, ra.data or {}, rb.data or {})}
        for (i, ra), (j, rb) in itertools.combinations(ok, 2)
    ]
    failed = [
        {
            "run": i + 1,
            "failure": r.failure,
            "cause": r.cause,
            "charged_likely": r.charged_likely,
        }
        for i, r in enumerate(runs)
        if not r.ok
    ]
    # A run that called the provider and has no output count is spend nobody
    # can see. A budget-stopped run made no call, so it does not count.
    called = [
        r for r in runs if r.failure not in ("stopped_output_budget", "stopped_after_failure")
    ]
    return {
        "job": job,
        "runs_requested": len(runs),
        "runs_ok": len(ok),
        "failed_runs": failed,
        "pairs": pairs,
        "tokens": {
            "input": sum(r.input_tokens or 0 for r in runs),
            "output": sum(r.output_tokens or 0 for r in runs),
            "complete": all(r.output_tokens is not None for r in called),
        },
        "exit_code": 0 if not failed and len(ok) >= 2 else 1,
    }


def _framework_enum(name: str) -> Any:
    from app.models.zt_assessment import ZtFramework

    return {"cisa": ZtFramework.CISA_ZTMM_2_0, "dod": ZtFramework.DOD_ZTRA}[name]


def _pick_assessment(
    db: Any, model: Any, status: Any, *, label: str, reopen_released: bool, **where: Any
) -> tuple[Any, str | None]:
    """The latest DRAFT/SUBMITTED `model` row matching `where`, or -- with
    `reopen_released`, and only when none is editable -- the latest RELEASED or
    APPROVED one set back to DRAFT. Returns (assessment, reopened_from).

    Why reopening exists: the demo seed releases its assessments, and every
    route builder refuses a locked one; a new version starts with empty answers.
    DRAFT is a state every assessment passed through before release. Never
    needed outside the throwaway database `preflight` insists on."""
    from sqlalchemy import select

    def latest(statuses: list[Any]) -> Any:
        q = select(model).where(model.status.in_(statuses))
        for column, value in where.items():
            q = q.where(getattr(model, column) == value)
        return db.execute(q.order_by(model.created_at.desc())).scalars().first()

    a = latest([status.DRAFT, status.SUBMITTED])
    reopened_from = None
    if a is None and reopen_released:
        a = latest([status.RELEASED, status.APPROVED])
        if a is not None:
            _require_sqlite_bind(db, "reopening a released assessment")
            reopened_from = a.status.value
            a.status = status.DRAFT
            db.commit()
            _log.info(
                "measure_ai_consistency.reopened",
                assessment_id=str(a.id),
                reopened_from=reopened_from,
            )
    if a is None:
        raise Refused(
            "no_editable_assessment",
            f"No draft or submitted {label} assessment"
            + ("" if reopen_released else " (--reopen-released was not given)")
            + ".",
        )
    return a, reopened_from


def _session_dialect(db: Any) -> str:
    return db.get_bind().dialect.name


def _require_sqlite_bind(db: Any, what: str) -> None:
    """A second, local check before any state change: `preflight` reads the
    settings, this reads the session actually in hand."""
    dialect = _session_dialect(db)
    if dialect != "sqlite":
        raise Refused(
            "state_change_needs_sqlite",
            f"Refusing {what}: the session is bound to {dialect!r}, not SQLite.",
        )


def _admin_user(db: Any) -> Any:
    """The requester recorded on each call. Checked BEFORE any state change."""
    from sqlalchemy import select

    from app.models.user import User, UserRole

    admin = (
        db.execute(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at))
        .scalars()
        .first()
    )
    if admin is None:
        raise Refused("no_admin_user", "No admin user to record as the requester.")
    return admin


def _client_of(db: Any, a: Any) -> Any:
    from app.models.client import Client
    from app.models.service import Service

    return db.get(Client, db.get(Service, a.service_id).client_id)


def _builder_refusal(exc: Exception) -> Refused:
    """A route builder's typed refusal (locked, not seeded), as a Refused."""
    detail = getattr(exc, "detail", None)
    text = detail.get("message") if isinstance(detail, dict) else detail
    return Refused("builder_refused", f"The route's payload builder refused: {text}")


def _failure(exc: Exception) -> tuple[str, str | None, bool | None]:
    """(reason, cause, charged_likely) for a failed run. The reason is typed;
    the cause is the underlying exception's TYPE name. Never a message, which
    can quote the model."""
    detail = getattr(exc, "detail", None)
    detail = detail if isinstance(detail, dict) else {}
    if detail.get("reason"):
        reason = str(detail["reason"])
    elif isinstance(getattr(exc, "reason", None), str):
        reason = exc.reason  # type: ignore[attr-defined]
    else:
        reason = type(exc).__name__
    cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
    charged = detail.get("charged_likely")
    return reason, cause, charged if isinstance(charged, bool) else None


def _ok_runs(records: Sequence[RunRecord]) -> list[tuple[int, dict]]:
    return [(i + 1, r.data) for i, r in enumerate(records) if r.ok and r.data is not None]


def measure_zt(
    db: Any,
    llm: Any,
    *,
    framework: str,
    runs: int,
    reopen_released: bool = False,
    max_output_tokens: int | None = None,
    stop_on_failure: bool = False,
) -> dict:
    """Run zt_score `runs` times on the latest editable assessment for
    `framework` and summarize. Writes only what `run_job` itself writes, plus
    the status change `reopen_released` asks for (see `_pick_assessment`)."""
    from fastapi import HTTPException

    from app.ai.engine import run_job
    from app.ai.failures import ai_call_boundary
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus
    from app.routes.zt import _to_catalog_framework, _zt_ai_request_for
    from app.services.engagement_targets import client_target_stage
    from app.zt.scoring import resolve_target_stage

    admin = _admin_user(db)
    a, reopened_from = _pick_assessment(
        db,
        ZtAssessment,
        ZtAssessmentStatus,
        label=framework,
        reopen_released=reopen_released,
        framework=_framework_enum(framework),
    )
    client = _client_of(db, a)
    try:
        req = _zt_ai_request_for(db, a, client)
    except HTTPException as exc:
        raise _builder_refusal(exc) from exc
    fw = _to_catalog_framework(a.framework)
    stage, stage_source = resolve_target_stage(fw, client_target_stage(db, a.service_id))
    _log.info(
        "measure_ai_consistency.start",
        job="zt_score",
        assessment_id=str(a.id),
        capabilities=len(req.rows),
        engagement_stage=stage,
        engagement_stage_source=stage_source,
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        try:
            with ai_call_boundary(db, llm, purpose=req.preview.job_name):
                result = run_job(
                    db,
                    llm,
                    req.preview.job_name,
                    inputs=req.preview.inputs,
                    requested_by=admin.id,
                    service_id=a.service_id,
                    client_id=client.id,
                    client_org_name=req.preview.client_org_name,
                    name_hints=req.preview.name_hints,
                )
        except HTTPException as exc:
            reason, cause, charged = _failure(exc)
            tokens_in, tokens_out = _tokens_since(db, before)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(False, None, reason, tokens_in, tokens_out, cause, charged)
        db.commit()
        tokens_in, tokens_out = _tokens_since(db, before)
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            duration_ms=result.llm_call.duration_ms,
        )
        return RunRecord(True, result.data, None, tokens_in, tokens_out)

    records = run_loop(
        runs, one_run, max_output_tokens=max_output_tokens, stop_on_failure=stop_on_failure
    )
    report = summarize("zt_score", records)
    report["assessment_id"] = str(a.id)
    report["assessment_capabilities"] = len(req.rows)
    report["engagement_stage"] = {"stage": stage, "source": stage_source}
    report["input_setup"] = {"reopened_from": reopened_from}
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["echo"] = [
        {"run": n, **echo_share("zt_score", req.preview.inputs, data)}
        for n, data in _ok_runs(records)
    ]
    report["downstream"] = [
        {"run": n, **zt_downstream(fw, engagement_stage=stage, data=data)}
        for n, data in _ok_runs(records)
    ]
    return report


def _call_ids(db: Any) -> set:
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    return set(db.execute(select(LLMCall.id)).scalars())


def _tokens_since(db: Any, before: set) -> tuple[int | None, int | None]:
    """Input and output tokens over the `llm_calls` rows written since `before`
    -- one per batch, each in its own session. None when no row reported any."""
    from sqlalchemy import select

    from app.models.llm_call import LLMCall

    db.expire_all()
    rows = [r for r in db.execute(select(LLMCall)).scalars() if r.id not in before]

    def total(attr: str) -> int | None:
        values = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return sum(values) if values else None

    return total("input_tokens"), total("output_tokens")


def _seed_profile_if_empty(db: Any, a: Any, admin: Any, client: Any, tiers: Sequence[str]) -> list:
    """Seed the Working Profile through the route's own handler when the
    assessment has no profile rows -- the demo seed creates answers and no
    profile, and the builder refuses an unseeded one. Returns the tiers seeded,
    or [] when rows already existed (nothing is changed then)."""
    from sqlalchemy import func, select

    from app.models.csf_profile import CsfDimensionScore
    from app.routes.csf import _latest_assessment, seed_profiles
    from app.schemas.csf import ProfileSeedRequest

    existing = db.execute(
        select(func.count())
        .select_from(CsfDimensionScore)
        .where(CsfDimensionScore.assessment_id == a.id)
    ).scalar_one()
    if existing or not tiers:
        return []
    _require_sqlite_bind(db, "seeding a Working Profile")
    if _latest_assessment(db, a.service_id).id != a.id:
        # The handler seeds the service's LATEST assessment, by its own rule.
        raise Refused(
            "profile_seed_target_mismatch",
            "The route would seed a different assessment than the one measured.",
        )
    seeded = seed_profiles(
        a.service_id, ProfileSeedRequest(tiers=list(tiers)), user=admin, client=client, db=db
    )
    _log.info("measure_ai_consistency.profile_seeded", assessment_id=str(a.id), tiers=seeded)
    return list(seeded)


def measure_csf(
    db: Any,
    llm: Any,
    *,
    runs: int,
    reopen_released: bool = False,
    max_output_tokens: int | None = None,
    seed_profile_tiers: Sequence[str] = (),
    stop_on_failure: bool = False,
) -> dict:
    """Run csf_score `runs` times on the latest editable CSF assessment, batched
    exactly as the route batches it, and summarize.

    A run in which ANY batch failed is a failed run: its missing rows would
    otherwise read as rows the model chose to leave out. The batches' scores are
    concatenated in batch order; an entry naming a row its batch was not asked
    for therefore shows up as a duplicated key, counted and compared in neither
    run, rather than being filtered here by a copy of the route's stray rule."""
    from datetime import timedelta

    from fastapi import HTTPException

    from app.ai.batching import run_batches
    from app.ai.runs import RUN_DEADLINE, RunFailed
    from app.models._common import utcnow
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
    from app.routes.csf import _CSF_MAX_WORKERS, _csf_ai_request_for, _csf_batch_inputs

    admin = _admin_user(db)
    a, reopened_from = _pick_assessment(
        db,
        CsfAssessment,
        CsfAssessmentStatus,
        label="CSF",
        reopen_released=reopen_released,
    )
    client = _client_of(db, a)
    seeded_tiers = _seed_profile_if_empty(db, a, admin, client, seed_profile_tiers)
    try:
        req = _csf_ai_request_for(db, a, client)
    except HTTPException as exc:
        raise _builder_refusal(exc) from exc
    batches = _csf_batch_inputs(req.preview.inputs)
    has_evidence = {key: bool(row.has_evidence) for key, row in req.rows.items()}
    _log.info(
        "measure_ai_consistency.start",
        job="csf_score",
        assessment_id=str(a.id),
        rows=len(req.rows),
        batches=len(batches),
        answers_sent=len(req.preview.inputs.get("answers") or {}),
        provider=llm.provider.name,
        model=llm.provider.model,
        runs=runs,
    )

    def one_run(n: int) -> RunRecord:
        before = _call_ids(db)
        try:
            batched = run_batches(
                db,
                llm,
                req.preview.job_name,
                batches,
                requested_by=admin.id,
                service_id=a.service_id,
                client_id=client.id,
                client_org_name=req.preview.client_org_name,
                name_hints=req.preview.name_hints,
                deadline_at=utcnow() + timedelta(seconds=RUN_DEADLINE.total_seconds()),
                max_workers=_CSF_MAX_WORKERS,
                deadline_message="The measurement run did not finish within the run deadline.",
            )
        except (HTTPException, RunFailed) as exc:
            reason, cause, charged = _failure(exc)
            tokens_in, tokens_out = _tokens_since(db, before)
            _log.error(
                "measure_ai_consistency.run_failed",
                run=n,
                failure=reason,
                cause=cause,
                charged_likely=charged,
            )
            return RunRecord(False, None, reason, tokens_in, tokens_out, cause, charged)
        tokens_in, tokens_out = _tokens_since(db, before)
        if batched.failed:
            failure = f"batches_failed:{batched.failed}/{batched.total}"
            _log.error("measure_ai_consistency.run_failed", run=n, failure=failure)
            return RunRecord(False, None, failure, tokens_in, tokens_out, None, True)
        data = {"scores": [entry for answer in batched.answers for entry in answer["scores"]]}
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            batches=batched.total,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
        return RunRecord(True, data, None, tokens_in, tokens_out)

    records = run_loop(
        runs, one_run, max_output_tokens=max_output_tokens, stop_on_failure=stop_on_failure
    )
    report = summarize("csf_score", records)
    levels = {n: csf_levels(data, has_evidence=has_evidence) for n, data in _ok_runs(records)}
    for pair in report["pairs"]:
        la, lb = levels[pair["pair"][0]]["levels"], levels[pair["pair"][1]]["levels"]
        both = set(la) & set(lb)
        pair["level"] = {"compared": len(both), "equal": sum(la[k] == lb[k] for k in both)}
    report["assessment_id"] = str(a.id)
    report["rows"] = len(req.rows)
    report["batches_per_run"] = len(batches)
    report["answers_sent"] = len(req.preview.inputs.get("answers") or {})
    report["input_setup"] = {"reopened_from": reopened_from, "profile_seeded_tiers": seeded_tiers}
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["downstream"] = [
        {"run": n, "not_scoreable": lv["not_scoreable"], "scored_rows": len(lv["levels"])}
        for n, lv in levels.items()
    ]
    return report


def _print_table(report: dict) -> None:
    print(f"job={report['job']} runs_ok={report['runs_ok']}/{report['runs_requested']}")
    for f in report["failed_runs"]:
        print(f"  run {f['run']} FAILED: {f['failure']}")
    for p in report["pairs"]:
        r = p["rows"]
        print(
            f"pair {p['pair']}: rows in both {r['in_both']}, only A {r['only_in_a']}, "
            f"only B {r['only_in_b']}, unreadable {r['unreadable_a']}/{r['unreadable_b']}, "
            f"duplicate keys {r['duplicate_keys_a']}/{r['duplicate_keys_b']}"
        )
        for name, s in p["fields"].items():
            print(
                f"  {name}: equal {s['equal']}/{s['compared']}, within one "
                f"{s['within_one']}/{s['compared']}, mean |diff| {s['mean_abs_diff']}, "
                f"missing A/B {s['missing_in_a']}/{s['missing_in_b']}"
            )
    for e in report.get("echo", []):
        for name, c in e.items():
            if name != "run":
                print(
                    f"run {e['run']} echo {name}: {c['echoed']}/{c['sent_and_answered']} "
                    f"repeat the sent value ({c['nothing_sent']} rows were sent nothing)"
                )
    for p in report["pairs"]:
        if "level" in p:
            lv = p["level"]
            print(f"pair {p['pair']} maturity level: equal {lv['equal']}/{lv['compared']}")
    for d in report.get("downstream", []):
        if "total_gap_count" in d:
            print(
                f"run {d['run']}: client-visible gaps {d['total_gap_count']}, "
                f"unscored {d['unscored_count']}, non-integer values {d['non_integer_values']}"
            )
        else:
            print(
                f"run {d['run']}: rows scored {d['scored_rows']}, "
                f"not scoreable {d['not_scoreable']}"
            )
    print(f"tokens: input {report['tokens']['input']}, output {report['tokens']['output']}")


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--job", required=True)
    p.add_argument("--framework", choices=("cisa", "dod"), default="cisa")
    p.add_argument("--runs", type=int, default=2)
    p.add_argument("--out", required=True)
    p.add_argument(
        "--reopen-released",
        action="store_true",
        help="If no assessment is editable, set the latest released one back to DRAFT "
        "first (the demo seed releases them all). Recorded in the report.",
    )
    p.add_argument(
        "--seed-profile-tiers",
        default="",
        help="csf_score only: comma-separated tiers (high,moderate,low) to seed, through "
        "the route's own handler, when the assessment has no Working Profile rows. "
        "Recorded in the report.",
    )
    p.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="Start no further run after a failed one (a rate limit is not retried into).",
    )
    p.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Start no further run once this many output tokens are spent. A run "
        "under way is never cut off, so the overrun is at most one run.",
    )
    args = p.parse_args(argv)
    if args.runs < 2:
        print("REFUSED (runs_below_two): agreement needs at least two runs.", file=sys.stderr)
        return 2
    if args.runs > MAX_RUNS:
        print(f"REFUSED (runs_above_max): at most {MAX_RUNS} runs.", file=sys.stderr)
        return 2

    from app.config import get_settings

    s = get_settings()
    try:
        preflight(
            database_url=s.database_url,
            llm_mode=s.shield_llm_mode,
            redaction_mode=s.shield_redaction_mode,
        )
        if args.job not in _IMPLEMENTED_JOBS:
            _job_shape(args.job)
    except Refused as exc:
        print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
        return 2

    from app.ai.llm import LLMClient
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        llm = LLMClient.from_db(db, s)
        print(f"provider={llm.provider.name} model={llm.provider.model} runs={args.runs}")
        try:
            common = {
                "runs": args.runs,
                "reopen_released": args.reopen_released,
                "max_output_tokens": args.max_output_tokens,
                "stop_on_failure": args.stop_on_failure,
            }
            if args.job == "csf_score":
                tiers = [t for t in args.seed_profile_tiers.split(",") if t]
                report = measure_csf(db, llm, seed_profile_tiers=tiers, **common)
            else:
                report = measure_zt(db, llm, framework=args.framework, **common)
        except Refused as exc:
            print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
            return 2
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    _print_table(report)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
