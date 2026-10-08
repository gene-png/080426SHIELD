"""Count stored CSF rows on ID.AM-09 and missing RC.CO-04 rows (#852). READ-ONLY.

#852 corrected the CSF catalog toward NIST CSWP 29 (not yet source-pinned):
CSF 2.0 has no `ID.AM-09` and has `RC.CO-04`. Migration 0064 keeps every `ID.AM-09` row and inserts empty
`RC.CO-04` rows. This measures, before or after it runs, how many rows the
change reaches, so the disclosure's reach on released work is a number rather
than a guess. It changes nothing: the transaction is read-only on Postgres and
is rolled back on every engine.

    cd apps/api
    DATABASE_URL=postgresql+psycopg://... python scripts/count_csf_retired_rows.py

Prints first what it READ: CSF assessments and answer rows, in total and per
status, so an empty or CSF-less database can never read as a clean one. When it
read no CSF answer rows it says NOTHING TO MEASURE above the zeros. Then, per
assessment status (draft, submitted, approved, released, discarded):

  * `ID.AM-09` answers, all and recorded (`app.csf.retired.has_recorded_answer`);
  * `ID.AM-09` Working Profile rows, all and recorded (`has_recorded_score`);
  * `ID.AM-09` action plans, recorded (`has_recorded_action`);
  * assessments with no `RC.CO-04` answer row;
  * seeded tiers with no `RC.CO-04` Working Profile row;

and the risk entries whose `source_id` is `ID.AM-09` or whose
`linked_controls` hold it.

Exit 0 after printing, including when every count is zero. Exit 2 when
DATABASE_URL is unset or the database cannot be read (no connection, no CSF
tables), so "could not look" never prints a zero.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATUSES = ("draft", "submitted", "approved", "released", "discarded")
RETIRED = "ID.AM-09"
NEW = "RC.CO-04"

FIELDS = (
    "retired answers",
    "retired answers recorded",
    "retired profile rows",
    "retired profile rows recorded",
    "retired action plans recorded",
    "assessments missing RC.CO-04 answer",
    "seeded tiers missing RC.CO-04 profile row",
)


def _key(status: object) -> str:
    return getattr(status, "value", str(status))


def measure(url: str) -> tuple[dict[str, list[int]], dict[str, dict[str, int]], dict[str, int]]:
    """({status: [assessments, answer rows] read}, {status: {field: count}},
    {risk field: count})."""
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session

    from app.csf.retired import has_recorded_action, has_recorded_answer, has_recorded_score
    from app.models.csf_assessment import CsfAnswer, CsfAssessment
    from app.models.csf_profile import CsfDimensionScore, CsfGapAction
    from app.models.risk_register import RiskEntry

    engine = create_engine(url, future=True)
    try:
        with Session(engine) as db:
            if engine.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            assessments = db.execute(select(CsfAssessment.id, CsfAssessment.status)).all()
            status_of = {aid: _key(st) for aid, st in assessments}
            answers = db.execute(select(CsfAnswer)).scalars().all()
            scores = db.execute(select(CsfDimensionScore)).scalars().all()
            actions = db.execute(select(CsfGapAction)).scalars().all()
            risk = db.execute(select(RiskEntry.source_id, RiskEntry.linked_controls)).all()
            # Detach what was read before rolling back: a rollback EXPIRES the
            # objects still in the session, and reading one afterwards fails.
            db.expunge_all()
            db.rollback()
    finally:
        engine.dispose()

    read: dict[str, list[int]] = {s: [0, 0] for s in STATUSES}
    out: dict[str, dict[str, int]] = {s: dict.fromkeys(FIELDS, 0) for s in STATUSES}
    for st in status_of.values():
        read.setdefault(st, [0, 0])[0] += 1
        out.setdefault(st, dict.fromkeys(FIELDS, 0))
    has_new: set = set()
    for a in answers:
        st = status_of.get(a.assessment_id, "unknown")
        read.setdefault(st, [0, 0])[1] += 1
        out.setdefault(st, dict.fromkeys(FIELDS, 0))
        if a.subcategory_code == NEW:
            has_new.add(a.assessment_id)
        if a.subcategory_code == RETIRED:
            out[st]["retired answers"] += 1
            out[st]["retired answers recorded"] += int(has_recorded_answer(a))
    for aid, st in status_of.items():
        if aid not in has_new:
            out[st]["assessments missing RC.CO-04 answer"] += 1
    tiers: dict = {}
    new_tiers: set = set()
    for r in scores:
        st = status_of.get(r.assessment_id, "unknown")
        out.setdefault(st, dict.fromkeys(FIELDS, 0))
        tiers.setdefault(r.assessment_id, set()).add(r.tier)
        if r.subcategory_code == NEW:
            new_tiers.add((r.assessment_id, r.tier))
        if r.subcategory_code == RETIRED:
            out[st]["retired profile rows"] += 1
            out[st]["retired profile rows recorded"] += int(has_recorded_score(r))
    for aid, ts in tiers.items():
        st = status_of.get(aid, "unknown")
        out[st]["seeded tiers missing RC.CO-04 profile row"] += sum(
            1 for t in ts if (aid, t) not in new_tiers
        )
    for g in actions:
        if g.subcategory_code == RETIRED and has_recorded_action(g):
            st = status_of.get(g.assessment_id, "unknown")
            out.setdefault(st, dict.fromkeys(FIELDS, 0))
            out[st]["retired action plans recorded"] += 1
    risk_out = {
        "risk entries with source_id ID.AM-09": sum(1 for sid, _ in risk if sid == RETIRED),
        "risk entries linking ID.AM-09": sum(
            1 for _, linked in risk if isinstance(linked, list) and RETIRED in linked
        ),
    }
    return read, out, risk_out


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("count-csf-retired-rows: DATABASE_URL is not set; nothing was read.", file=sys.stderr)
        return 2
    try:
        read, result, risk = measure(url)
    except Exception as exc:  # noqa: BLE001 -- every failure to read is exit 2, named
        print(f"count-csf-retired-rows: could not read the database: {exc!r}", file=sys.stderr)
        return 2
    print("count-csf-retired-rows: CSF rows on ID.AM-09 and missing RC.CO-04 rows (read-only)")
    total_assessments = sum(a for a, _ in read.values())
    total_rows = sum(r for _, r in read.values())
    print(
        f"count-csf-retired-rows read: CSF assessments {total_assessments}, "
        f"CSF answer rows {total_rows}"
    )
    for status, (assessments, rows) in read.items():
        print(f"  {status} read: assessments {assessments}, answer rows {rows}")
    if total_rows == 0:
        # A zero over nothing read is not a clean result, and must not look like one.
        print(
            "count-csf-retired-rows: NOTHING TO MEASURE: no CSF answer rows were read, "
            "so the zeros below are not a clean result"
        )
    for status, counts in result.items():
        print(f"  {status}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    for k, v in risk.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
