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

ADVISOR RULINGS (#736 comment 6116519635), applied here:
  - ZT option (a): the rule applies only to assessments NOT YET RELEASED. A
    RELEASED assessment is scored at its stored stage, so the headline counts
    released ZT as not moving. A separate, labelled line
    (`zt_released_without_freeze_*`) shows what it WOULD have moved.
  - Out-of-ladder stages stay unchanged (`proposed_launch_stage`).
  - "Capped" counts only when the number changes: `stage_moves`.
  - CSF totals are reported as well as levels: `rows_total_moves`.
  - CSF is not frozen by option (a); it is reported per status as before.

`app.routes.clients` and `app.routes.csf` are imported INSIDE the functions
that call their helpers, not at module level: importing either builds the app's
own (writable) engine from
DATABASE_URL, so a module-level import would fail on a malformed URL before
`main` could report it as exit 2, and would do so before this script opened its
read-only engine. The app engine is never connected by this script.

HOW IT AVOIDS REIMPLEMENTING SCORING. Every number comes from the product's own
engines, CALLED on the stored rows with the launch rule applied in memory:

  - CSF tier rows: `app.csf.playbook.score_tier`, twice per row.
  - CSF Enterprise: `app.csf.enterprise.enterprise_subcategories`, twice per
    assessment. The launch call runs with the module's `score_tier` replaced by
    a wrapper that calls the REAL `score_tier` with launch evidence. The wrapper
    counts its calls and the count must equal the tier scores the roll-up
    produced, or the rule was not applied and the run exits 2.
  - ZT: `app.zt.scoring.compute` and `analyze_gaps`, today's stored stages and
    the launch stages. A capability's counted stage is read from `compute`
    over that one answer.

WHICH VERSIONS, AND WHICH TARGET. Every figure is reported twice. The HEADLINE
(`surfaced`) is chosen PER SERVICE, because the two services' readers differ:
  - CSF: the version the Playbook and its exports read. `csf_dashboard` reads
    `CsfAnswer.maturity_tier`, which no rule touches. The Playbook and its
    exports (`export_playbook` and its client artifacts, through
    `enterprise_subcategories`) take `routes.csf._latest_assessment`, the latest
    NON-DISCARDED version, released or not. Called, not re-derived. NOT every
    reader of these rows does: `routes/risk.py`'s finalized CSF input reads a
    different version, and the Risk Register is not measured here.
  - ZT: the version the client dashboard renders, resolved by the dashboard's
    own helpers (`_latest_released_deliverable`, then `_deliverable_parent`).
    Its gaps are against the target that deliverable was FROZEN with, through
    the dashboard's `_frozen_or_live_target` (#209), never the live intake read.
  - secondary (`all_versions`): every stored version, drafts and superseded
    versions included. A version no client surface reads takes the live intake
    target (`client_target_stage` + `resolve_target_stage`, as finalize does).
  The one thing written here is the PROPOSED ZT rule, `proposed_launch_stage`,
  because it does not exist in the product yet: it is what is being measured.

TWO PATHS FOR CSF TIER ROWS. Section 10.6's SQL is run as an independent second
path (with `a.client_id` added to its SELECT and GROUP BY so per-client counts
are cross-checked too, and `lvl()` inlined as 10.6 allows). Both paths read the
same population, every `csf_dimension_scores` row joined to its assessment (ALL
versions), and must agree per (status, client). Only `rows_level_moves` is an
independent cross-check of the scoring; `rows_in_scope` and `rows_ticked_today`
are shared-population counts (both paths count the same column of the same
rows), and are labelled so. A disagreement prints PATHS DISAGREE and exits 1.

RETIRED CSF CODES. A kept row on a code the catalog no longer has (#852) is in
both paths' population, so it is counted, and disclosed apart:
`rows_on_retired_code` and `rows_level_moves_on_retired_code`. No surface rolls
it up (`catalog_rows`).

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
Exit 1: the two CSF paths disagree, and nothing else. Exit 2: the input could
not be read (DATABASE_URL unset or malformed, no such file, no connection, no
tables), the launch rule could not be applied, or anything else failed before
figures were printed; the reason is on stderr and no figures are printed.
NOTHING TO MEASURE is reported PER SERVICE (CSF, Zero Trust), and so is a
service with rows but no surfaced version.

It never writes. SQLite is opened with `mode=ro`; Postgres with
`default_transaction_read_only=on`; every session is rolled back.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
import uuid
from collections import Counter
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, event, select, text  # noqa: E402
from sqlalchemy.engine import Connection, Engine, make_url  # noqa: E402
from sqlalchemy.exc import MultipleResultsFound, NoResultFound, SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.csf import enterprise, playbook  # noqa: E402
from app.csf.retired import catalog_rows  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus  # noqa: E402
from app.models.csf_profile import CsfDimensionScore  # noqa: E402
from app.models.deliverable import Deliverable  # noqa: E402
from app.models.zt_assessment import (  # noqa: E402
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)
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

TIER_METRICS = (
    "rows_read",
    "rows_in_scope",
    "rows_level_moves",
    "rows_ticked_today",
    "rows_total_moves",
    "rows_on_retired_code",
    "rows_level_moves_on_retired_code",
)
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


class Views:
    """Every count twice. `surfaced` (the HEADLINE): only the version the
    service's readers read, one per service at most (CSF: the Playbook's
    `_latest_assessment`; ZT: the client dashboard's released parent). `all_versions`: every
    stored version, drafts and superseded versions included, which is what the
    10.6 SQL reads and what the two-path cross-check compares."""

    def __init__(self, metrics: tuple[str, ...]) -> None:
        self.metrics = metrics
        self.all = Tally(metrics)
        self.surfaced = Tally(metrics)

    def add(self, surfaced: bool, cid: str, status: str, metric: str, n: int = 1) -> None:
        self.all.add(cid, status, metric, n)
        if surfaced:
            self.surfaced.add(cid, status, metric, n)

    def reason(self, surfaced: bool, cid: str, status: str, why: str) -> None:
        self.all.reason(cid, status, why)
        if surfaced:
            self.surfaced.reason(cid, status, why)

    def report(self, names: Mapping[str, str | None], with_reasons: bool = False) -> dict:
        return {
            "surfaced": self.surfaced.report(names, with_reasons),
            "all_versions": self.all.report(names, with_reasons),
        }


# ---------------------------------------------------------------- surfaced versions


def surfaced_parents(
    db: Session, model: Any, statuses: tuple[Any, ...]
) -> tuple[dict[uuid.UUID, Deliverable], list[dict[str, str]]]:
    """{assessment id: the deliverable a client dashboard renders it for}, plus
    the services whose released deliverable names no resolvable parent.

    The resolution is the client dashboards', CALLED: the service's latest
    RELEASED deliverable (`_latest_released_deliverable`), then the assessment it
    was built from (`_deliverable_parent`, with the statuses `zt_dashboard`
    passes). An unresolved parent is refused by the dashboard
    (`_unresolved_parent`), so it surfaces no version and is listed instead.
    The admin's unreleased preview is not a client surface and is not here."""
    from app.routes.clients import _deliverable_parent, _latest_released_deliverable

    surfaced: dict[uuid.UUID, Deliverable] = {}
    unresolved: list[dict[str, str]] = []
    for sid in sorted(set(db.execute(select(model.service_id)).scalars()), key=str):
        deliv = _latest_released_deliverable(db, sid)
        if deliv is None:
            continue
        parent = _deliverable_parent(db, model, deliv, statuses)
        if parent is None:
            unresolved.append(
                {
                    "service_id": str(sid),
                    "deliverable_id": str(deliv.id),
                    "reason": "dashboard_version_unresolved: parent_version is NULL or names "
                    "no APPROVED/RELEASED assessment, so the dashboard refuses",
                }
            )
            continue
        surfaced[parent.id] = deliv
    return surfaced, unresolved


def csf_surfaced(db: Session) -> set[uuid.UUID]:
    """Per CSF service, the version the Playbook and its exports read:
    `routes.csf._latest_assessment` (the latest non-discarded version), CALLED.
    A service whose every version is discarded surfaces nothing."""
    from app.routes.csf import _latest_assessment

    out: set[uuid.UUID] = set()
    for sid in set(db.execute(select(CsfAssessment.service_id)).scalars()):
        a = _latest_assessment(db, sid)
        if a is not None:
            out.add(a.id)
    return out


# ---------------------------------------------------------------- CSF


def csf_tier_rows_python(db: Session, parents: Collection[uuid.UUID]) -> Views:
    """Path 1: `score_tier` per stored row, today's tick against launch."""
    views = Views(TIER_METRICS)
    for a in db.execute(select(CsfAssessment)).scalars().all():
        cid, st, surfaced = _cid(a.client_id), _status(a.status), a.id in parents
        rows = (
            db.execute(select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id))
            .scalars()
            .all()
        )
        on_catalog = {r.id for r in catalog_rows(rows)}
        for row in rows:
            views.add(surfaced, cid, st, "rows_read")
            if not row.in_scope:
                continue
            retired = row.id not in on_catalog
            ds = enterprise.dimensions_of(row)
            today_r = playbook.score_tier(ds, has_evidence=row.has_evidence)
            launch_r = playbook.score_tier(ds, has_evidence=LAUNCH_HAS_CURRENT_IMPLEMENTATION)
            today, launch = today_r.level, launch_r.level
            views.add(surfaced, cid, st, "rows_in_scope")
            if retired:
                views.add(surfaced, cid, st, "rows_on_retired_code")
            if row.has_evidence:
                views.add(surfaced, cid, st, "rows_ticked_today")
            # Totals as well as levels (advisor ruling): a ticked row whose
            # implementation drops 2 -> 1 can lose a point and keep its level.
            if today_r.total != launch_r.total:
                views.add(surfaced, cid, st, "rows_total_moves")
            if today != launch:
                views.add(surfaced, cid, st, "rows_level_moves")
                if retired:
                    views.add(surfaced, cid, st, "rows_level_moves_on_retired_code")
    return views


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
    """Path 2: section 10.6's SQL, keyed (client id, status), over ALL versions."""
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


def csf_enterprise(
    db: Session, parents: Collection[uuid.UUID]
) -> tuple[Views, list[dict[str, str]]]:
    views = Views(
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
        cid, st, surfaced = _cid(a.client_id), _status(a.status), a.id in parents
        try:
            today, _ = enterprise.enterprise_subcategories(db, a)
            calls = [0]
            with _launch_score_tier(calls):
                launch, _ = enterprise.enterprise_subcategories(db, a)
        except (ValueError, KeyError) as exc:
            not_evaluable.append(
                {
                    "assessment_id": str(a.id),
                    "status": st,
                    "surfaced": str(surfaced),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        expected = sum(len(s.tier_levels) for s in today)
        if calls[0] != expected:
            raise RuleNotApplied(
                f"the launch rule was not applied to CSF assessment {a.id}: the roll-up "
                f"scored {expected} tier rows and the launch score_tier saw {calls[0]}"
            )
        views.add(surfaced, cid, st, "assessments_evaluated")
        by_code = {s.subcategory_code: s for s in launch}
        for t in today:
            n = by_code[t.subcategory_code]
            views.add(surfaced, cid, st, "subcategories")
            if t.enterprise_level != n.enterprise_level:
                views.add(surfaced, cid, st, "subcategory_level_moves")
            if t.gap:
                views.add(surfaced, cid, st, "gaps_today")
            if n.gap:
                views.add(surfaced, cid, st, "gaps_launch")
            if n.gap and not t.gap:
                views.add(surfaced, cid, st, "gaps_opened")
            if t.gap and not n.gap:
                views.add(surfaced, cid, st, "gaps_closed")
            if t.priority != n.priority:
                views.add(surfaced, cid, st, "priority_changes")
    return views, not_evaluable


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


def _zt_target(db: Session, a: ZtAssessment, deliv: Deliverable | None) -> tuple[object, bool]:
    """(the client's CHOSEN target, whether it was frozen). A surfaced version
    takes the target its deliverable was rendered with, through the dashboard's
    own `_frozen_or_live_target` (#209); any other version takes the live
    intake read, as finalize would."""
    from app.routes.clients import _frozen_or_live_target

    live = client_target_stage(db, a.service_id)
    if deliv is None:
        return live, False
    chosen, frozen_at = _frozen_or_live_target(deliv, live)
    return chosen, frozen_at is not None


ZT_ANSWER_METRICS = ("answers_read", "answers_evaluated", "stage_moves", "unchanged")
ZT_ASSESSMENT_METRICS = (
    "assessments_evaluated",
    "targets_frozen",
    "targets_live",
    "overall_label_moves",
    "average_stage_moves",
    "pillar_average_moves",
    "gaps_today",
    "gaps_launch",
    "assessments_gap_count_moves",
)

LaunchStage = Callable[[ZtFrameworkCode, "int | None"], "int | None"]


def _stored_stage(_framework: ZtFrameworkCode, stage: int | None) -> int | None:
    """A RELEASED assessment is scored at its stored stage (advisor ruling,
    option (a), #736 comment 6116519635): the rule does not reach it."""
    return stage


def zt_rule_applies(status: str) -> bool:
    """Option (a): the ZT rule applies only to assessments not yet released.

    The ASSESSMENT's status stands in for "released". That holds because
    releasing a deliverable flips the assessment it was built from to RELEASED
    (`deliverable_release._release_parent`, keyed on the `parent_version`
    stamped at finalize), so a released report's assessment is RELEASED. A
    deliverable finalized before migration 0041 has no `parent_version`, its
    parent is never flipped, and that assessment stays APPROVED here: the rule
    then applies to it, which errs toward reporting a move, not hiding one."""
    return status != ZtAssessmentStatus.RELEASED.value


def _zt_one(
    answers: Views,
    assessments: Views,
    a: ZtAssessment,
    rows: list[ZtAnswer],
    surfaced: bool,
    launch_stage: LaunchStage,
    target: tuple[object, bool],
) -> str | None:
    """Count one assessment into `answers` and `assessments`, with
    `launch_stage` as the launch rule. Returns the reason the deliverable figures
    could not be evaluated, or None."""
    cid, st = _cid(a.client_id), _status(a.status)
    fw = _catalog_framework(a.framework)
    for r in rows:
        answers.add(surfaced, cid, st, "answers_read")
        why = _why_not_evaluable(fw, r.capability_code, r.maturity_stage)
        if why is not None:
            answers.reason(surfaced, cid, st, why)
            continue
        answers.add(surfaced, cid, st, "answers_evaluated")
        stage = int(r.maturity_stage)  # type: ignore[arg-type]
        launch = launch_stage(fw, stage)
        assert launch is not None
        # "Capped" counts only when the number changes (advisor ruling): a
        # stage already at lowest + 1 is unchanged, never a move.
        if _counted_stage(fw, r.capability_code, stage) != _counted_stage(
            fw, r.capability_code, launch
        ):
            answers.add(surfaced, cid, st, "stage_moves")
        else:
            answers.add(surfaced, cid, st, "unchanged")

    # The deliverable's inputs, as the finalize route builds them.
    valid = all_codes(fw)
    today_map = {r.capability_code: r.maturity_stage for r in rows if r.capability_code in valid}
    launch_map = {c: launch_stage(fw, s) for c, s in today_map.items()}
    targets = {r.capability_code: r.target_stage for r in rows if r.capability_code in valid}
    chosen, frozen = target
    try:
        target_stage, _source = resolve_target_stage(fw, chosen)
        every = len(capabilities(fw))  # no DEFAULT_TOP_N truncation
        s_today, s_launch = compute(fw, today_map), compute(fw, launch_map)
        g_today = analyze_gaps(
            fw, today_map, targets=targets, target_stage=target_stage, top_n=every
        )
        g_launch = analyze_gaps(
            fw, launch_map, targets=targets, target_stage=target_stage, top_n=every
        )
    except (ValueError, KeyError) as exc:
        return f"{type(exc).__name__}: {exc}"
    assessments.add(surfaced, cid, st, "assessments_evaluated")
    assessments.add(surfaced, cid, st, "targets_frozen" if frozen else "targets_live")
    if s_today.overall_stage_label != s_launch.overall_stage_label:
        assessments.add(surfaced, cid, st, "overall_label_moves")
    if s_today.average_stage != s_launch.average_stage:
        assessments.add(surfaced, cid, st, "average_stage_moves")
    for p_today, p_launch in zip(s_today.by_pillar, s_launch.by_pillar, strict=True):
        if p_today.average_stage != p_launch.average_stage:
            assessments.add(surfaced, cid, st, "pillar_average_moves")
    assessments.add(surfaced, cid, st, "gaps_today", g_today.total_gap_count)
    assessments.add(surfaced, cid, st, "gaps_launch", g_launch.total_gap_count)
    if g_today.total_gap_count != g_launch.total_gap_count:
        assessments.add(surfaced, cid, st, "assessments_gap_count_moves")
    return None


def zt(db: Session, parents: Mapping[uuid.UUID, Deliverable]) -> dict[str, Any]:
    """Every ZT assessment under option (a): RELEASED at its stored stage, the
    rest under the proposed rule. RELEASED assessments are counted a second
    time, under the rule, into `released_without_freeze`: what WOULD have moved
    had the freeze not been ruled. That line is never part of the headline."""
    out: dict[str, Any] = {
        "answers": Views(ZT_ANSWER_METRICS),
        "assessments": Views(ZT_ASSESSMENT_METRICS),
        "released_without_freeze_answers": Views(ZT_ANSWER_METRICS),
        "released_without_freeze_assessments": Views(ZT_ASSESSMENT_METRICS),
        "not_evaluable": [],
    }
    for a in db.execute(select(ZtAssessment)).scalars().all():
        st, surfaced = _status(a.status), a.id in parents
        rows = list(
            db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == a.id)).scalars().all()
        )
        target = _zt_target(db, a, parents.get(a.id))
        applies = zt_rule_applies(st)
        launch_stage: LaunchStage = proposed_launch_stage if applies else _stored_stage
        why = _zt_one(out["answers"], out["assessments"], a, rows, surfaced, launch_stage, target)
        if why is not None:
            out["not_evaluable"].append(
                {
                    "assessment_id": str(a.id),
                    "status": st,
                    "surfaced": str(surfaced),
                    "reason": why,
                }
            )
            continue
        if not applies:
            _zt_one(
                out["released_without_freeze_answers"],
                out["released_without_freeze_assessments"],
                a,
                rows,
                surfaced,
                proposed_launch_stage,
                target,
            )
    return out


# ---------------------------------------------------------------- measure


def measure(url: str) -> dict[str, Any]:
    try:
        engine = open_readonly(url)
    except SQLAlchemyError as exc:
        # `make_url` refuses a malformed URL with ArgumentError. Still "could
        # not look", never exit 1 ("the paths disagree").
        raise CouldNotRead(f"could not parse DATABASE_URL: {exc!r}") from exc
    try:
        with Session(engine) as db:
            try:
                names = {_cid(c.id): c.legal_name for c in db.execute(select(Client)).scalars()}
                csf_parents = csf_surfaced(db)
                zt_parents, zt_unresolved = surfaced_parents(
                    db, ZtAssessment, (ZtAssessmentStatus.APPROVED, ZtAssessmentStatus.RELEASED)
                )
                tiers = csf_tier_rows_python(db, csf_parents)
                sql = csf_tier_rows_sql(db.connection())
                ent, ent_bad = csf_enterprise(db, csf_parents)
                zt_out = zt(db, zt_parents)
            finally:
                db.rollback()
    except (MultipleResultsFound, NoResultFound) as exc:
        # `_deliverable_parent` resolves with `scalar_one_or_none`, which raises
        # on a second parent row: a data fault, not an unreadable database.
        raise CouldNotRead(f"the deliverable chain is inconsistent: {exc!r}") from exc
    except SQLAlchemyError as exc:
        raise CouldNotRead(f"could not read the database: {exc!r}") from exc
    finally:
        engine.dispose()

    disagreements = compare_paths(tiers.all, sql)
    return {
        "scope": {
            "launch": "no CONFIRMED links (the backfill writes SUGGESTED); doc_status NULL "
            "reads as not_sure (design note rev 4, 10.6)",
            "surfaced": {
                "csf": "HEADLINE: per CSF service, the version the Playbook and its exports "
                "read (routes.csf._latest_assessment: latest non-discarded); the CSF client "
                "dashboard reads CsfAnswer.maturity_tier, which no rule touches",
                "zt": "HEADLINE: per ZT service, the version the client dashboard renders "
                "(latest released deliverable's parent), gaps against that deliverable's "
                "frozen target; RELEASED held at the stored stage (option (a))",
            },
            "released_without_freeze": "NOT the headline: zt_released_without_freeze_* "
            "count RELEASED ZT a second time under the rule, to show what WOULD have moved "
            "without the freeze; its `surfaced` view is the subset a client dashboard renders",
            "all_versions": "every stored assessment version; versions no client surface "
            "reads take the live intake target",
            "zt_statuses_held_at_stored_stage": ["released"],
        },
        "csf_tier_rows": tiers.report(names),
        "csf_tier_rows_sql": _sql_report(sql, names),
        "csf_tier_rows_cross_check": {
            "independently_cross_checked": ["rows_level_moves"],
            "shared_population": ["rows_in_scope", "rows_ticked_today"],
            "python_only": [
                "rows_read",
                "rows_total_moves",
                "rows_on_retired_code",
                "rows_level_moves_on_retired_code",
            ],
            "population": "all_versions",
        },
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
        "surfaced_versions": {"csf": len(csf_parents), "zt": len(zt_parents)},
        "csf_enterprise": {**ent.report(names), "not_evaluable": ent_bad},
        "csf_deliverable": {
            "rows_moved": 0,
            "basis": "by construction, not measured: the CSF deliverable reads "
            "CsfAnswer.maturity_tier, which no proposed rule reads",
        },
        "zt_rule": {
            "applies_to": "assessments not yet released (advisor ruling, option (a), "
            "#736 comment 6116519635)",
            "released": "scored at the stored stage: the headline counts released ZT as "
            "not moving",
            "released_without_freeze": "a separate line: what released ZT WOULD have "
            "moved under the rule; never part of the headline",
            "out_of_ladder": "left unchanged (ruling)",
            "capped": "counted only when the number changes (ruling): stage_moves",
        },
        "zt_answers": zt_out["answers"].report(names, with_reasons=True),
        "zt_released_without_freeze_answers": zt_out["released_without_freeze_answers"].report(
            names, with_reasons=True
        ),
        "zt_released_without_freeze_assessments": zt_out[
            "released_without_freeze_assessments"
        ].report(names),
        "zt_assessments": {
            **zt_out["assessments"].report(names),
            "not_evaluable": zt_out["not_evaluable"],
            "parents_unresolved": zt_unresolved,
        },
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


_CSF_HEADLINE = "HEADLINE, the version the Playbook and its exports read"
_ZT_HEADLINE = "HEADLINE, the version the client dashboard renders"
_ALL = "secondary, ALL assessment versions"


def _both(
    title: str, headline: str, section: Mapping[str, Any], secondary: str = _ALL
) -> list[str]:
    return _table(f"{title} [{headline}]", section["surfaced"]) + _table(
        f"{title} [{secondary}]", section["all_versions"]
    )


#: The would-have-moved tables are never the headline, in either view.
_NOT_HEADLINE_SURFACED = "NOT the headline: released, IF NOT FROZEN; surfaced versions"
_NOT_HEADLINE_ALL = "NOT the headline: released, IF NOT FROZEN; all versions"


def _read(section: Mapping[str, Any], metric: str, view: str = "all_versions") -> int:
    return sum(c[metric] for c in section[view]["by_status"].values())


def _nothing_to_measure(report: Mapping[str, Any]) -> list[str]:
    """Per SERVICE: one service's rows never make another's zeros read clean."""
    out = []
    for service, key, section, metric, why in (
        (
            "CSF",
            "csf",
            report["csf_tier_rows"],
            "rows_read",
            "every version is discarded, so _latest_assessment returns none",
        ),
        (
            "Zero Trust",
            "zt",
            report["zt_answers"],
            "answers_read",
            "no released deliverable resolves to a parent",
        ),
    ):
        if _read(section, metric) == 0:
            out.append(
                f"{PREFIX}: NOTHING TO MEASURE ({service}): no rows were read, so its zeros "
                "below are not a clean result"
            )
        elif report["surfaced_versions"][key] == 0:
            out.append(
                f"{PREFIX}: NO SURFACED VERSION ({service}): rows exist but {why}, so its "
                "HEADLINE zeros are not a clean result"
            )
        elif _read(section, metric, "surfaced") == 0:
            out.append(
                f"{PREFIX}: SURFACED VERSION HAS NO ROWS ({service}): the version its "
                "readers read holds none, so its HEADLINE zeros are not a clean result"
            )
    return out


def render(report: Mapping[str, Any]) -> str:
    out = [f"{PREFIX}: evidence rules at launch, design note rev 4 10.4/10.6 (read-only)"]
    out.append(
        f"{PREFIX} read (all versions): CSF tier rows "
        f"{_read(report['csf_tier_rows'], 'rows_read')}, ZT answer rows "
        f"{_read(report['zt_answers'], 'answers_read')}"
    )
    out += _nothing_to_measure(report)
    if report["paths_agree"]:
        out.append(
            f"{PREFIX}: CSF tier rows, all versions: the score_tier path and the 10.6 SQL "
            "path AGREE"
        )
    else:
        out.append(f"{PREFIX}: PATHS DISAGREE on CSF tier rows: {report['disagreements']}")
    check = report["csf_tier_rows_cross_check"]
    out.append(
        f"  independently cross-checked: {', '.join(check['independently_cross_checked'])}; "
        f"shared-population counts (both paths count the same column of the same rows): "
        f"{', '.join(check['shared_population'])}; score_tier path only: "
        f"{', '.join(check['python_only'])}"
    )
    out += _both("CSF tier rows (score_tier path)", _CSF_HEADLINE, report["csf_tier_rows"])
    out += _table(f"CSF tier rows (10.6 SQL path) [{_ALL}]", report["csf_tier_rows_sql"])
    out += _both(
        "CSF Enterprise (enterprise_subcategories)", _CSF_HEADLINE, report["csf_enterprise"]
    )
    if report["csf_enterprise"]["not_evaluable"]:
        out.append(f"  CSF not_evaluable: {report['csf_enterprise']['not_evaluable']}")
    out.append(f"\nCSF R2: {report['csf_rules']['R2']['basis']}")
    out.append(f"CSF R3: {report['csf_rules']['R3']['basis']}")
    out.append(f"CSF deliverable: {report['csf_deliverable']['basis']}")
    out += _both("ZT answers (counted stage, compute)", _ZT_HEADLINE, report["zt_answers"])
    out += _both(
        "ZT assessments (deliverable: compute + analyze_gaps)",
        _ZT_HEADLINE,
        report["zt_assessments"],
    )
    for key in ("not_evaluable", "parents_unresolved"):
        if report["zt_assessments"][key]:
            out.append(f"  ZT {key}: {report['zt_assessments'][key]}")
    out.append(
        f"\nZT RELEASED WITHOUT THE FREEZE: {report['zt_rule']['released_without_freeze']}. "
        "Released ZT is scored at the stored stage above (option (a))."
    )
    out += _both(
        "ZT answers, released, IF NOT FROZEN",
        _NOT_HEADLINE_SURFACED,
        report["zt_released_without_freeze_answers"],
        _NOT_HEADLINE_ALL,
    )
    out += _both(
        "ZT assessments, released, IF NOT FROZEN",
        _NOT_HEADLINE_SURFACED,
        report["zt_released_without_freeze_assessments"],
        _NOT_HEADLINE_ALL,
    )
    return "\n".join(out)


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(f"{PREFIX}: DATABASE_URL is not set; nothing was read.", file=sys.stderr)
        return EXIT_UNREADABLE
    try:
        report = measure(url)
        table = render(report)
        payload = json.dumps(report, indent=2, sort_keys=True)
    except (CouldNotRead, RuleNotApplied) as exc:
        print(f"{PREFIX}: {exc}", file=sys.stderr)
        return EXIT_UNREADABLE
    except Exception as exc:  # noqa: BLE001 -- any failure before figures is "could not look"
        # Exit 1 means "the two paths disagree"; an unexpected failure must not
        # borrow it. The traceback goes to stderr, and no figures are printed.
        traceback.print_exc()
        print(f"{PREFIX}: could not measure, nothing is reported: {exc!r}", file=sys.stderr)
        return EXIT_UNREADABLE
    print(table)
    print(JSON_MARKER)
    print(payload)
    if not report["paths_agree"]:
        print(
            f"{PREFIX}: PATHS DISAGREE: the CSF counts above are not trustworthy", file=sys.stderr
        )
        return EXIT_PATHS_DISAGREE
    return EXIT_MEASURED


if __name__ == "__main__":
    sys.exit(main())
