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
(`routes/zt.py::_zt_ai_request_for`), calls `engine.run_job` inside the route's
own `ai_call_boundary` -- the one path to the model, so redaction, mode and
output caps are production's -- and parses with the job's registered parser.
It APPLIES NOTHING: no answer row is written. The one state change it can make
is `--reopen-released`, which sets a released assessment back to DRAFT so the
route's builder will accept it -- the demo seed releases every ZT assessment --
and which the report records as `input_setup`.

WHAT IT REPORTS, per pair of successful runs: the row set (in both / only in
one / unreadable / duplicated keys), and per field over rows present in both,
how many were compared and how many agreed. Every share carries its
denominator. It also reports the gap count the client would see if each run's
values were applied, computed by `zt.scoring.analyze_gaps` rather than here.
Counts and capability codes only: no model text reaches the output or the logs.

EXIT: 0 every run succeeded; 1 a run failed, or fewer than two succeeded (the
report is still written, and names each failure); 2 refused.

Only `zt_score` is implemented. `csf_score` and `tech_debt_extract` arrive with
the steps that change those prompts (#806 steps 3 and 5), each with its own
input builder; asking for them now is refused rather than approximated.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)

#: Jobs with an input builder here. `_job_shape` names each one's row list, key
#: and compared fields.
_IMPLEMENTED_JOBS = ("zt_score",)


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
    Rows the real apply path would skip (locked, protected, edited) are not
    modelled: this is what the model ASKED for, not what a run would write.
    """
    from app.zt.catalog import capabilities
    from app.zt.scoring import analyze_gaps

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
    }


def summarize(job: str, runs: Sequence[RunRecord]) -> dict:
    """Every pair of successful runs, plus the failed runs by number (1-based).
    Fewer than two successes is a failure: there is nothing to compare."""
    ok = [(i + 1, r) for i, r in enumerate(runs) if r.ok]
    pairs = [
        {"pair": [i, j], **compare_pair(job, ra.data or {}, rb.data or {})}
        for (i, ra), (j, rb) in itertools.combinations(ok, 2)
    ]
    failed = [{"run": i + 1, "failure": r.failure} for i, r in enumerate(runs) if not r.ok]
    return {
        "job": job,
        "runs_requested": len(runs),
        "runs_ok": len(ok),
        "failed_runs": failed,
        "pairs": pairs,
        "tokens": {
            "input": sum(r.input_tokens or 0 for r in runs),
            "output": sum(r.output_tokens or 0 for r in runs),
        },
        "exit_code": 0 if not failed and len(ok) >= 2 else 1,
    }


def _framework_enum(name: str) -> Any:
    from app.models.zt_assessment import ZtFramework

    return {"cisa": ZtFramework.CISA_ZTMM_2_0, "dod": ZtFramework.DOD_ZTRA}[name]


def _latest_zt(db: Any, framework: str, statuses: Sequence[Any]) -> Any:
    from sqlalchemy import select

    from app.models.zt_assessment import ZtAssessment

    return (
        db.execute(
            select(ZtAssessment)
            .where(
                ZtAssessment.framework == _framework_enum(framework),
                ZtAssessment.status.in_(list(statuses)),
            )
            .order_by(ZtAssessment.created_at.desc())
        )
        .scalars()
        .first()
    )


def measure_zt(
    db: Any, llm: Any, *, framework: str, runs: int, reopen_released: bool = False
) -> dict:
    """Run zt_score `runs` times on the latest editable assessment for
    `framework` and summarize. Writes only what `run_job` itself writes.

    `reopen_released`: the demo seed releases every ZT assessment, and the
    route's builder refuses a locked one. With this set, and only when there is
    no editable assessment, the latest released (or approved) one is set back to
    DRAFT first -- a state every assessment passed through before release -- so
    the measure runs on the seed's real answers instead of an empty new version.
    It is recorded in the report as `input_setup`. Never needed outside the
    throwaway database `preflight` insists on."""
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.ai.engine import run_job
    from app.ai.failures import ai_call_boundary
    from app.models.client import Client
    from app.models.service import Service
    from app.models.user import User, UserRole
    from app.models.zt_assessment import ZtAssessmentStatus
    from app.routes.zt import _to_catalog_framework, _zt_ai_request_for
    from app.services.engagement_targets import client_target_stage
    from app.zt.scoring import resolve_target_stage

    a = _latest_zt(db, framework, [ZtAssessmentStatus.DRAFT, ZtAssessmentStatus.SUBMITTED])
    reopened_from = None
    if a is None and reopen_released:
        a = _latest_zt(db, framework, [ZtAssessmentStatus.RELEASED, ZtAssessmentStatus.APPROVED])
        if a is not None:
            reopened_from = a.status.value
            a.status = ZtAssessmentStatus.DRAFT
            db.commit()
            _log.info(
                "measure_ai_consistency.reopened",
                assessment_id=str(a.id),
                reopened_from=reopened_from,
            )
    if a is None:
        raise Refused(
            "no_editable_assessment",
            f"No draft or submitted {framework} assessment"
            + ("" if reopen_released else " (--reopen-released was not given)")
            + ".",
        )
    svc = db.get(Service, a.service_id)
    client = db.get(Client, svc.client_id)
    admin = (
        db.execute(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at))
        .scalars()
        .first()
    )
    if admin is None:
        raise Refused("no_admin_user", "No admin user to record as the requester.")
    req = _zt_ai_request_for(db, a, client)
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

    records: list[RunRecord] = []
    for n in range(1, runs + 1):
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
            # Typed by the boundary; the reason, never the message, which can
            # quote the model's output.
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            failure = str(detail.get("reason") or f"http_{exc.status_code}")
            _log.error("measure_ai_consistency.run_failed", run=n, failure=failure)
            records.append(RunRecord(False, None, failure, None, None))
            continue
        db.commit()
        call = result.llm_call
        _log.info(
            "measure_ai_consistency.run_ok",
            run=n,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            duration_ms=call.duration_ms,
        )
        records.append(RunRecord(True, result.data, None, call.input_tokens, call.output_tokens))

    report = summarize("zt_score", records)
    report["assessment_capabilities"] = len(req.rows)
    report["engagement_stage"] = {"stage": stage, "source": stage_source}
    report["input_setup"] = {"reopened_from": reopened_from}
    report["provider"] = {"name": llm.provider.name, "model": llm.provider.model}
    report["echo"] = [
        {"run": i + 1, **echo_share("zt_score", req.preview.inputs, r.data)}
        for i, r in enumerate(records)
        if r.ok and r.data is not None
    ]
    report["downstream"] = [
        {"run": i + 1, **zt_downstream(fw, engagement_stage=stage, data=r.data)}
        for i, r in enumerate(records)
        if r.ok and r.data is not None
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
    for d in report.get("downstream", []):
        print(
            f"run {d['run']}: client-visible gaps {d['total_gap_count']}, "
            f"unscored {d['unscored_count']}, non-integer values {d['non_integer_values']}"
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
    args = p.parse_args(argv)
    if args.runs < 2:
        print("REFUSED (runs_below_two): agreement needs at least two runs.", file=sys.stderr)
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
            report = measure_zt(
                db,
                llm,
                framework=args.framework,
                runs=args.runs,
                reopen_released=args.reopen_released,
            )
        except Refused as exc:
            print(f"REFUSED ({exc.reason}): {exc}", file=sys.stderr)
            return 2
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    _print_table(report)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
