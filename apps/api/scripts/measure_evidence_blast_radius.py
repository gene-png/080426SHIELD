"""Measure what the evidence scoring rules would move at launch. READ-ONLY.

Design note rev 4, section 10.6 (for #1071, EV-1). The rules are section 10.4's:
R1 to R3 for CSF, and for Zero Trust `evidenced_stage` with Q10 ruled "lowest
stage plus one" (#736 comment 6115899208). Neither rule is in the product yet;
this measures them before anyone codes them.

    cd apps/api
    DATABASE_URL=postgresql+psycopg://... python scripts/measure_evidence_blast_radius.py
    # or, from the repo root, against the running stack:
    docker compose exec -T api python scripts/measure_evidence_blast_radius.py

WHAT "LAUNCH" MEANS (10.6). The backfill turns every `evidence_artifact_id` into
a SUGGESTED link, never a CONFIRMED one, and files keep `doc_status` NULL, which
reads as Not sure. So at launch no target has a confirmed Current file, and:

  - R1 ("no Current file supports implementation") holds for EVERY CSF row. Its
    arithmetic is today's evidence cap (10.4's table), so R1 at launch is
    `score_tier(ds, has_evidence=False)` for every row.
  - R2 needs a CONFIRMED Draft link. None exists at launch, so R2 moves nothing.
    That is stated in the output, not computed.
  - R3 has no score effect by definition.
  - ZT: no capability has a Current file supporting `implemented`, so every
    stage above the framework's lowest counts as the lowest plus one.

HOW IT AVOIDS REIMPLEMENTING SCORING. Every number comes from the product's own
engines, CALLED on the stored rows with the launch rule applied in memory:

  - CSF tier rows: `app.csf.playbook.score_tier`, twice per row.
  - CSF Enterprise: `app.csf.enterprise.enterprise_subcategories`, twice per
    assessment. The launch call runs with the module's `score_tier` replaced by
    a wrapper that calls the REAL `score_tier` with launch evidence. The wrapper
    counts its calls and the count must equal the tier scores the roll-up
    produced, or the rule was not applied and the run exits 2.
  - ZT: `app.zt.scoring.compute` and `analyze_gaps`, today's stored stages and
    the launch stages, with the client's target resolved by the same
    `client_target_stage` + `resolve_target_stage` the finalize route calls.
    A capability's counted stage is read from `compute` over that one answer.
  The one thing written here is the PROPOSED ZT rule, `proposed_launch_stage`,
  because it does not exist in the product yet: it is what is being measured.

TWO PATHS FOR CSF TIER ROWS. Section 10.6's SQL is run as an independent second
path (with `a.client_id` added to its SELECT and GROUP BY so per-client counts
are cross-checked too, and `lvl()` inlined as 10.6 allows). Both paths read the
same population, every `csf_dimension_scores` row joined to its assessment, and
must agree per (status, client) on rows in scope, rows whose level moves and rows
ticked today. A disagreement prints PATHS DISAGREE and exits 1.

WHAT IS NOT EVALUATED, AND IS NEVER COUNTED AS UNCHANGED:
  - ZT answers: `unscored` (stage NULL), `out_of_ladder` (a stored stage the
    framework does not have; the engine treats it as unscored), `retired_code`
    (a capability the catalog no longer has; not scored).
  - A CSF or ZT assessment the engine refuses: listed with the exception text.

NOT MEASURED HERE: the Risk Register's CSF and ZT inputs, and the Q9 grace
proposal (APPROVED and RELEASED keep their ticks), which is a proposal; read the
per-status rows for it. The CSF deliverable is not measured because it cannot
move: it reads `CsfAnswer.maturity_tier`, which no proposed rule reads.

Output: a table, then a line `--- JSON ---`, then the same figures as JSON.
Exit 0: measured (including a database with nothing to measure, which says so).
Exit 1: the two CSF paths disagree. Exit 2: the input could not be read
(DATABASE_URL unset, no such file, no connection, no tables) or the launch rule
could not be applied; the reason is on stderr and no figures are printed.

It never writes. SQLite is opened with `mode=ro`; Postgres with
`default_transaction_read_only=on`; every session is rolled back.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, select, text  # noqa: E402
from sqlalchemy.engine import Connection, Engine, make_url  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.csf import enterprise, playbook  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus  # noqa: E402
from app.models.csf_profile import CsfDimensionScore  # noqa: E402
from app.models.zt_assessment import ZtAnswer, ZtAssessment, ZtFramework  # noqa: E402
from app.services.engagement_targets import client_target_stage  # noqa: E402
from app.zt.catalog import all_codes, capabilities  # noqa: E402
from app.zt.maturity import ZtFrameworkCode, level_count, stage_definitions  # noqa: E402
from app.zt.scoring import analyze_gaps, compute, resolve_target_stage  # noqa: E402

PREFIX = "measure-evidence-blast-radius"
JSON_MARKER = "--- JSON ---"
EXIT_MEASURED = 0
EXIT_PATHS_DISAGREE = 1
EXIT_UNREADABLE = 2

#: R1's trigger at launch: no CONFIRMED Current link supports `implementation`
#: anywhere, because the backfill writes SUGGESTED links only (10.6).
LAUNCH_HAS_CURRENT_IMPLEMENTATION = False

STATUSES = tuple(s.value for s in CsfAssessmentStatus)

TIER_METRICS = ("rows_read", "rows_in_scope", "rows_level_moves", "rows_ticked_today")
SQL_METRICS = ("rows_in_scope", "rows_level_moves", "rows_ticked_today")


class CouldNotRead(Exception):
    """The input could not be read: exit 2, never a zero."""


class RuleNotApplied(Exception):
    """The launch rule did not reach the engine: exit 2, never "unchanged"."""


# ---------------------------------------------------------------- opening


def _register_sql_functions(dbapi_conn: Any, _record: Any) -> None:
    """10.6's SQL is Postgres; SQLite has no LEAST/GREATEST. Registered, not
    rewritten, so the SQL text is the same on both."""
    dbapi_conn.create_function("LEAST", -1, lambda *a: min(a), deterministic=True)
    dbapi_conn.create_function("GREATEST", -1, lambda *a: max(a), deterministic=True)


def open_readonly(url: str) -> Engine:
    u = make_url(url)
    backend = u.get_backend_name()
    if backend == "sqlite":
        if not u.database or u.database == ":memory:":
            raise CouldNotRead("an in-memory SQLite database has nothing to read")
        path = Path(u.database)
        if not path.is_file():
            # Checked first: without `mode=ro` SQLite would CREATE the file.
            raise CouldNotRead(f"no SQLite file at {path}")
        engine = create_engine(f"sqlite:///file:{path.resolve()}?mode=ro&uri=true", future=True)
        event.listen(engine, "connect", _register_sql_functions)
        return engine
    if backend == "postgresql":
        return create_engine(
            url, future=True, connect_args={"options": "-c default_transaction_read_only=on"}
        )
    raise CouldNotRead(f"unsupported database backend {backend!r}")


def _status(raw: object) -> str:
    """An assessment status as its lower-case value, from an enum or raw SQL
    (which may hold the enum NAME)."""
    value = getattr(raw, "value", raw)
    s = str(value)
    if s in CsfAssessmentStatus.__members__:
        return CsfAssessmentStatus[s].value
    return s.lower()


def _cid(raw: object) -> str:
    return str(uuid.UUID(str(raw)))


# ---------------------------------------------------------------- tallies


class Tally:
    """Counters keyed by (client id, status), rolled up by status and by client."""

    def __init__(self, metrics: tuple[str, ...]) -> None:
        self.metrics = metrics
        self.cells: dict[tuple[str, str], Counter] = {}
        self.reasons: dict[tuple[str, str], Counter] = {}

    def add(self, cid: str, status: str, metric: str, n: int = 1) -> None:
        assert metric in self.metrics, metric
        self.cells.setdefault((cid, status), Counter())[metric] += n

    def reason(self, cid: str, status: str, why: str) -> None:
        self.reasons.setdefault((cid, status), Counter())[why] += 1

    def _cell(self, keys: list[tuple[str, str]], with_reasons: bool) -> dict:
        total: Counter = Counter()
        why: Counter = Counter()
        for k in keys:
            total.update(self.cells.get(k, Counter()))
            why.update(self.reasons.get(k, Counter()))
        out: dict[str, Any] = {m: total[m] for m in self.metrics}
        if with_reasons:
            out["not_evaluable"] = dict(sorted(why.items()))
        return out

    def report(self, names: Mapping[str, str | None], with_reasons: bool = False) -> dict:
        keys = set(self.cells) | set(self.reasons)
        statuses = list(STATUSES) + sorted({s for _, s in keys} - set(STATUSES))
        by_status = {s: self._cell([k for k in keys if k[1] == s], with_reasons) for s in statuses}
        by_client = {
            cid: {
                "name": names.get(cid),
                "by_status": {
                    s: self._cell([(cid, s)], with_reasons) for s in statuses if (cid, s) in keys
                },
            }
            for cid in sorted({c for c, _ in keys})
        }
        return {"by_status": by_status, "by_client": by_client}


# ---------------------------------------------------------------- CSF


def csf_tier_rows_python(db: Session) -> Tally:
    """Path 1: `score_tier` per stored row, today's tick against launch."""
    tally = Tally(TIER_METRICS)
    rows = db.execute(
        select(CsfDimensionScore, CsfAssessment.status).join(
            CsfAssessment, CsfAssessment.id == CsfDimensionScore.assessment_id
        )
    ).all()
    for row, raw_status in rows:
        cid, st = _cid(row.client_id), _status(raw_status)
        tally.add(cid, st, "rows_read")
        if not row.in_scope:
            continue
        ds = enterprise.dimensions_of(row)
        today = playbook.score_tier(ds, has_evidence=row.has_evidence).level
        launch = playbook.score_tier(ds, has_evidence=LAUNCH_HAS_CURRENT_IMPLEMENTATION).level
        tally.add(cid, st, "rows_in_scope")
        if row.has_evidence:
            tally.add(cid, st, "rows_ticked_today")
        if today != launch:
            tally.add(cid, st, "rows_level_moves")
    return tally


def _lvl(t: str) -> str:
    """`maturity_level`'s bands, inlined as 10.6 allows."""
    return (
        f"(CASE WHEN ({t})<=2 THEN 1 WHEN ({t})<=5 THEN 2 WHEN ({t})<=7 THEN 3 "
        f"WHEN ({t})<=9 THEN 4 ELSE 5 END)"
    )


#: Section 10.6's SQL. Two changes: `a.client_id` is selected and grouped by,
#: and `lvl()` is inlined.
CSF_TIER_SQL = f"""
WITH r AS (
  SELECT s.assessment_id, a.status AS assessment_status, a.client_id AS client_id,
         s.in_scope, s.has_evidence AS ticked,
         LEAST(GREATEST(s.implementation,0),2) AS impl, LEAST(GREATEST(s.policy,0),2) AS pol,
         LEAST(GREATEST(s.governance,0),2)+LEAST(GREATEST(s.monitoring,0),2)
          +LEAST(GREATEST(s.improvement,0),2) AS other3
  FROM csf_dimension_scores s JOIN csf_assessments a ON a.id = s.assessment_id
), lv AS (
  SELECT *,
    CASE WHEN ticked THEN {_lvl("other3+pol+impl")}
         ELSE LEAST(2, {_lvl("other3+pol+LEAST(impl,1)")}) END AS lvl_today,
    LEAST(2, {_lvl("other3+pol+LEAST(impl,1)")}) AS lvl_launch
  FROM r
)
SELECT assessment_status, client_id,
       count(*) FILTER (WHERE in_scope)                            AS rows_in_scope,
       count(*) FILTER (WHERE in_scope AND lvl_today <> lvl_launch) AS rows_level_moves,
       count(*) FILTER (WHERE in_scope AND ticked)                  AS rows_ticked_today
FROM lv GROUP BY assessment_status, client_id ORDER BY assessment_status, client_id
"""


def csf_tier_rows_sql(conn: Connection) -> dict[tuple[str, str], dict[str, int]]:
    """Path 2: section 10.6's SQL, keyed (client id, status)."""
    out: dict[tuple[str, str], dict[str, int]] = {}
    for status, cid, in_scope, moves, ticked in conn.execute(text(CSF_TIER_SQL)).all():
        key = (_cid(cid), _status(status))
        prior = out.get(key, dict.fromkeys(SQL_METRICS, 0))
        # Two raw spellings of one status (name and value) fold into one key.
        out[key] = {
            "rows_in_scope": prior["rows_in_scope"] + int(in_scope),
            "rows_level_moves": prior["rows_level_moves"] + int(moves),
            "rows_ticked_today": prior["rows_ticked_today"] + int(ticked),
        }
    return out


def compare_paths(
    python: Tally, sql: dict[tuple[str, str], dict[str, int]]
) -> list[dict[str, Any]]:
    """Every (client, status, metric) where the two paths differ."""
    out = []
    for key in sorted(set(python.cells) | set(sql)):
        cell = python.cells.get(key, Counter())
        other = sql.get(key, dict.fromkeys(SQL_METRICS, 0))
        for metric in SQL_METRICS:
            if cell[metric] != other[metric]:
                out.append(
                    {
                        "client_id": key[0],
                        "status": key[1],
                        "metric": metric,
                        "python": cell[metric],
                        "sql": other[metric],
                    }
                )
    return out


def _sql_report(
    sql: dict[tuple[str, str], dict[str, int]], names: Mapping[str, str | None]
) -> dict[str, Any]:
    tally = Tally(SQL_METRICS)
    for (cid, st), cell in sql.items():
        for metric, n in cell.items():
            tally.add(cid, st, metric, n)
    return tally.report(names)


@contextmanager
def _launch_score_tier(calls: list[int]) -> Iterator[None]:
    """The Enterprise roll-up with R1 at launch: the REAL `score_tier`, called
    with launch evidence in place of the row's tick."""
    real = enterprise.score_tier
    if real is not playbook.score_tier:
        raise RuleNotApplied(
            "the launch rule was not applied: app.csf.enterprise.score_tier is not "
            "app.csf.playbook.score_tier, so this script no longer knows what it is replacing"
        )

    def launch(ds: playbook.DimensionScores, *, has_evidence: bool) -> playbook.TierResult:
        calls[0] += 1
        return real(ds, has_evidence=LAUNCH_HAS_CURRENT_IMPLEMENTATION)

    enterprise.score_tier = launch  # type: ignore[assignment]
    try:
        yield
    finally:
        enterprise.score_tier = real


def csf_enterprise(db: Session) -> tuple[Tally, list[dict[str, str]]]:
    tally = Tally(
        (
            "assessments_evaluated",
            "subcategories",
            "subcategory_level_moves",
            "gaps_today",
            "gaps_launch",
            "gaps_opened",
            "gaps_closed",
            "priority_changes",
        )
    )
    not_evaluable: list[dict[str, str]] = []
    for a in db.execute(select(CsfAssessment)).scalars().all():
        cid, st = _cid(a.client_id), _status(a.status)
        try:
            today, _ = enterprise.enterprise_subcategories(db, a)
            calls = [0]
            with _launch_score_tier(calls):
                launch, _ = enterprise.enterprise_subcategories(db, a)
        except (ValueError, KeyError) as exc:
            not_evaluable.append(
                {"assessment_id": str(a.id), "status": st, "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        expected = sum(len(s.tier_levels) for s in today)
        if calls[0] != expected:
            raise RuleNotApplied(
                f"the launch rule was not applied to CSF assessment {a.id}: the roll-up "
                f"scored {expected} tier rows and the launch score_tier saw {calls[0]}"
            )
        tally.add(cid, st, "assessments_evaluated")
        by_code = {s.subcategory_code: s for s in launch}
        for t in today:
            n = by_code[t.subcategory_code]
            tally.add(cid, st, "subcategories")
            if t.enterprise_level != n.enterprise_level:
                tally.add(cid, st, "subcategory_level_moves")
            if t.gap:
                tally.add(cid, st, "gaps_today")
            if n.gap:
                tally.add(cid, st, "gaps_launch")
            if n.gap and not t.gap:
                tally.add(cid, st, "gaps_opened")
            if t.gap and not n.gap:
                tally.add(cid, st, "gaps_closed")
            if t.priority != n.priority:
                tally.add(cid, st, "priority_changes")
    return tally, not_evaluable


# ---------------------------------------------------------------- ZT


def _catalog_framework(fw: ZtFramework) -> ZtFrameworkCode:
    return ZtFrameworkCode(fw.value)


def proposed_launch_stage(framework: ZtFrameworkCode, stage: int | None) -> int | None:
    """The PROPOSED rule (10.4, Q10) at launch, where no capability has a Current
    file supporting `implemented`: a stage above the framework's lowest counts
    as the lowest plus one. A stage outside the ladder is left as stored, so
    the engine still treats it as unscored; capping it would score junk."""
    if stage is None or not 1 <= stage <= level_count(framework):
        return stage
    lowest = min(d.stage for d in stage_definitions(framework))
    return min(stage, lowest + 1)


def _counted_stage(framework: ZtFrameworkCode, code: str, stage: int) -> int | None:
    """The stage the engine COUNTS for one capability: `compute` over that one
    answer, whose average is that answer's validated, capability-capped stage."""
    avg = compute(framework, {code: stage}).average_stage
    return None if avg is None else int(avg)


def _why_not_evaluable(framework: ZtFrameworkCode, code: str, stage: int | None) -> str | None:
    if code not in all_codes(framework):
        return "retired_code"
    if stage is None:
        return "unscored"
    if not 1 <= stage <= level_count(framework):
        return "out_of_ladder"
    return None


def zt(db: Session) -> tuple[Tally, Tally, list[dict[str, str]]]:
    answers_tally = Tally(("answers_read", "answers_evaluated", "stage_moves", "unchanged"))
    assessments_tally = Tally(
        (
            "assessments_evaluated",
            "overall_label_moves",
            "average_stage_moves",
            "pillar_average_moves",
            "gaps_today",
            "gaps_launch",
            "assessments_gap_count_moves",
        )
    )
    not_evaluable: list[dict[str, str]] = []
    for a in db.execute(select(ZtAssessment)).scalars().all():
        cid, st = _cid(a.client_id), _status(a.status)
        fw = _catalog_framework(a.framework)
        rows = db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == a.id)).scalars().all()
        for r in rows:
            answers_tally.add(cid, st, "answers_read")
            why = _why_not_evaluable(fw, r.capability_code, r.maturity_stage)
            if why is not None:
                answers_tally.reason(cid, st, why)
                continue
            answers_tally.add(cid, st, "answers_evaluated")
            stage = int(r.maturity_stage)  # type: ignore[arg-type]
            launch = proposed_launch_stage(fw, stage)
            assert launch is not None
            if _counted_stage(fw, r.capability_code, stage) != _counted_stage(
                fw, r.capability_code, launch
            ):
                answers_tally.add(cid, st, "stage_moves")
            else:
                answers_tally.add(cid, st, "unchanged")

        # The deliverable's inputs, as the finalize route builds them.
        valid = all_codes(fw)
        today_map = {
            r.capability_code: r.maturity_stage for r in rows if r.capability_code in valid
        }
        launch_map = {c: proposed_launch_stage(fw, s) for c, s in today_map.items()}
        targets = {r.capability_code: r.target_stage for r in rows if r.capability_code in valid}
        try:
            target_stage, _source = resolve_target_stage(fw, client_target_stage(db, a.service_id))
            every = len(capabilities(fw))  # no DEFAULT_TOP_N truncation
            s_today, s_launch = compute(fw, today_map), compute(fw, launch_map)
            g_today = analyze_gaps(
                fw, today_map, targets=targets, target_stage=target_stage, top_n=every
            )
            g_launch = analyze_gaps(
                fw, launch_map, targets=targets, target_stage=target_stage, top_n=every
            )
        except (ValueError, KeyError) as exc:
            not_evaluable.append(
                {"assessment_id": str(a.id), "status": st, "reason": f"{type(exc).__name__}: {exc}"}
            )
            continue
        assessments_tally.add(cid, st, "assessments_evaluated")
        if s_today.overall_stage_label != s_launch.overall_stage_label:
            assessments_tally.add(cid, st, "overall_label_moves")
        if s_today.average_stage != s_launch.average_stage:
            assessments_tally.add(cid, st, "average_stage_moves")
        for p_today, p_launch in zip(s_today.by_pillar, s_launch.by_pillar, strict=True):
            if p_today.average_stage != p_launch.average_stage:
                assessments_tally.add(cid, st, "pillar_average_moves")
        assessments_tally.add(cid, st, "gaps_today", g_today.total_gap_count)
        assessments_tally.add(cid, st, "gaps_launch", g_launch.total_gap_count)
        if g_today.total_gap_count != g_launch.total_gap_count:
            assessments_tally.add(cid, st, "assessments_gap_count_moves")
    return answers_tally, assessments_tally, not_evaluable


# ---------------------------------------------------------------- measure


def measure(url: str) -> dict[str, Any]:
    engine = open_readonly(url)
    try:
        with Session(engine) as db:
            try:
                names = {_cid(c.id): c.legal_name for c in db.execute(select(Client)).scalars()}
                tiers = csf_tier_rows_python(db)
                sql = csf_tier_rows_sql(db.connection())
                ent, ent_bad = csf_enterprise(db)
                zt_answers, zt_assessments, zt_bad = zt(db)
            finally:
                db.rollback()
    except SQLAlchemyError as exc:
        raise CouldNotRead(f"could not read the database: {exc!r}") from exc
    finally:
        engine.dispose()

    disagreements = compare_paths(tiers, sql)
    return {
        "scope": {
            "launch": "no CONFIRMED links (the backfill writes SUGGESTED); doc_status NULL "
            "reads as not_sure (design note rev 4, 10.6)",
            "statuses_frozen_by_q9_grace_proposal": ["approved", "released"],
        },
        "csf_tier_rows": tiers.report(names),
        "csf_tier_rows_sql": _sql_report(sql, names),
        "paths_agree": not disagreements,
        "disagreements": disagreements,
        "csf_rules": {
            "R1": "applied: score_tier(has_evidence=False) for every row at launch",
            "R2": {
                "rows_affected": 0,
                "basis": "by construction: R2 needs a CONFIRMED Draft link; none exists at launch",
            },
            "R3": {"rows_affected": 0, "basis": "by definition: R3 has no score effect"},
        },
        "csf_enterprise": {**ent.report(names), "not_evaluable": ent_bad},
        "csf_deliverable": {
            "rows_moved": 0,
            "basis": "by construction, not measured: the CSF deliverable reads "
            "CsfAnswer.maturity_tier, which no proposed rule reads",
        },
        "zt_answers": zt_answers.report(names, with_reasons=True),
        "zt_assessments": {**zt_assessments.report(names), "not_evaluable": zt_bad},
    }


# ---------------------------------------------------------------- render


def _table(title: str, section: Mapping[str, Any]) -> list[str]:
    rows = section["by_status"]
    metrics = [k for k in next(iter(rows.values())) if k != "not_evaluable"]
    lines = [
        f"\n{title}",
        "  " + "status".ljust(11) + "".join(m.rjust(len(m) + 2) for m in metrics),
    ]
    for st, cell in rows.items():
        line = "  " + st.ljust(11) + "".join(str(cell[m]).rjust(len(m) + 2) for m in metrics)
        if cell.get("not_evaluable"):
            line += f"   not evaluable: {cell['not_evaluable']}"
        lines.append(line)
    for cid, client in section["by_client"].items():
        lines.append(f"  client {cid} ({client['name'] or 'unnamed'})")
        for st, cell in client["by_status"].items():
            line = "    " + st.ljust(9) + "".join(str(cell[m]).rjust(len(m) + 2) for m in metrics)
            if cell.get("not_evaluable"):
                line += f"   not evaluable: {cell['not_evaluable']}"
            lines.append(line)
    return lines


def render(report: Mapping[str, Any]) -> str:
    out = [f"{PREFIX}: evidence rules at launch, design note rev 4 10.4/10.6 (read-only)"]
    read = sum(c["rows_read"] for c in report["csf_tier_rows"]["by_status"].values())
    zt_read = sum(c["answers_read"] for c in report["zt_answers"]["by_status"].values())
    out.append(f"{PREFIX} read: CSF tier rows {read}, ZT answer rows {zt_read}")
    if read == 0 and zt_read == 0:
        out.append(
            f"{PREFIX}: NOTHING TO MEASURE: no CSF tier rows and no ZT answers were read, "
            "so the zeros below are not a clean result"
        )
    if report["paths_agree"]:
        out.append(f"{PREFIX}: CSF tier rows: the score_tier path and the 10.6 SQL path AGREE")
    else:
        out.append(f"{PREFIX}: PATHS DISAGREE on CSF tier rows: {report['disagreements']}")
    out += _table("CSF tier rows (score_tier path)", report["csf_tier_rows"])
    out += _table("CSF tier rows (10.6 SQL path)", report["csf_tier_rows_sql"])
    out += _table("CSF Enterprise (enterprise_subcategories)", report["csf_enterprise"])
    if report["csf_enterprise"]["not_evaluable"]:
        out.append(f"  not evaluable: {report['csf_enterprise']['not_evaluable']}")
    out.append(f"\nCSF R2: {report['csf_rules']['R2']['basis']}")
    out.append(f"CSF R3: {report['csf_rules']['R3']['basis']}")
    out.append(f"CSF deliverable: {report['csf_deliverable']['basis']}")
    out += _table("ZT answers (counted stage, compute)", report["zt_answers"])
    out += _table("ZT assessments (deliverable: compute + analyze_gaps)", report["zt_assessments"])
    if report["zt_assessments"]["not_evaluable"]:
        out.append(f"  not evaluable: {report['zt_assessments']['not_evaluable']}")
    return "\n".join(out)


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(f"{PREFIX}: DATABASE_URL is not set; nothing was read.", file=sys.stderr)
        return EXIT_UNREADABLE
    try:
        report = measure(url)
    except (CouldNotRead, RuleNotApplied) as exc:
        print(f"{PREFIX}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    print(render(report))
    print(JSON_MARKER)
    print(json.dumps(report, indent=2, sort_keys=True))
    if not report["paths_agree"]:
        print(
            f"{PREFIX}: PATHS DISAGREE: the CSF counts above are not trustworthy", file=sys.stderr
        )
        return EXIT_PATHS_DISAGREE
    return EXIT_MEASURED


if __name__ == "__main__":
    sys.exit(main())
