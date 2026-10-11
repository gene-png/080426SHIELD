"""Count stored DoD ZT stages above their capability's maximum (#839, F1). READ-ONLY.

The write paths now refuse a maturity stage above `capability_max_stage`
(`app.zt.target_caps.max_stage_for`). Rows stored before that guard may hold
one. This measures how many, before anyone decides what a figure built on
them says (#736 comment 6048561596: "measure the blast radius on dev data
first"). It changes nothing: the transaction is read-only on Postgres and is
rolled back on every engine.

    cd apps/api
    DATABASE_URL=postgresql+psycopg://... python scripts/count_zt_stages_above_cap.py

Prints first what it READ: the number of DoD assessments and DoD answer rows,
in total and per status, so an empty or DoD-less database can never read as a
clean one. When it read no DoD answer rows it says NOTHING TO MEASURE above the
zeros. Then, per assessment status (draft, submitted, approved, released,
discarded), the number of DoD answers whose current (maturity) stage is above
the maximum and the number whose per-capability target is, then each one as
`<field> <assessment id> <code> = <stored stage>`.

A row the DoD catalog no longer has (retired, kept by 0064) is held to the DoD
ladder (1-3), as the write paths hold it. A stored 4 on a DoD row is above both.

Exit 0 after printing, including when every count is zero. Exit 2 when
DATABASE_URL is unset or the database cannot be read (no connection, no ZT
tables), so "could not look" never prints a zero.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

STATUSES = ("draft", "submitted", "approved", "released", "discarded")

#: One stage above its capability's maximum: (field, assessment id, code, stage).
Over = tuple[str, str, str, int]

#: What was read for one status: (DoD assessments, DoD answer rows).
Read = tuple[int, int]


def measure(url: str) -> tuple[dict[str, Read], dict[str, list[Over]]]:
    """({status: (assessments, rows) read}, {status: [over, ...]}) for every
    DoD answer above its capability's max. Assessments are counted from the
    assessment table, so a DoD assessment with no answer rows still counts."""
    from sqlalchemy import create_engine, select, text
    from sqlalchemy.orm import Session

    from app.models.zt_assessment import ZtAnswer, ZtAssessment, ZtFramework
    from app.zt.maturity import ZtFrameworkCode
    from app.zt.target_caps import max_stage_for

    engine = create_engine(url, future=True)
    try:
        with Session(engine) as db:
            if engine.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
            rows = db.execute(
                select(
                    ZtAssessment.status,
                    ZtAnswer.assessment_id,
                    ZtAnswer.capability_code,
                    ZtAnswer.maturity_stage,
                    ZtAnswer.target_stage,
                )
                .join(ZtAssessment, ZtAssessment.id == ZtAnswer.assessment_id)
                .where(ZtAssessment.framework == ZtFramework.DOD_ZTRA)
            ).all()
            assessments = db.execute(
                select(ZtAssessment.status, ZtAssessment.id).where(
                    ZtAssessment.framework == ZtFramework.DOD_ZTRA
                )
            ).all()
            db.rollback()
    finally:
        engine.dispose()

    def _key(status: object) -> str:
        return getattr(status, "value", str(status))

    read: dict[str, list[int]] = {s: [0, 0] for s in STATUSES}
    for status, _aid in assessments:
        read.setdefault(_key(status), [0, 0])[0] += 1
    out: dict[str, list[Over]] = {s: [] for s in STATUSES}
    for status, assessment_id, code, current, target in rows:
        key = _key(status)
        read.setdefault(key, [0, 0])[1] += 1
        cap = max_stage_for(ZtFrameworkCode.DOD_ZTRA, code)
        for field, stage in (("current", current), ("target", target)):
            if stage is not None and stage > cap:
                out.setdefault(key, []).append((field, str(assessment_id), code, stage))
    return {k: (v[0], v[1]) for k, v in read.items()}, out


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print(
            "count-zt-stages-above-cap: DATABASE_URL is not set; nothing was read.", file=sys.stderr
        )
        return 2
    try:
        read, result = measure(url)
    except Exception as exc:  # noqa: BLE001 -- every failure to read is exit 2, named
        print(f"count-zt-stages-above-cap: could not read the database: {exc!r}", file=sys.stderr)
        return 2
    print("count-zt-stages-above-cap: DoD ZT answers above their capability's maximum (read-only)")
    total_assessments = sum(a for a, _ in read.values())
    total_rows = sum(r for _, r in read.values())
    print(
        f"count-zt-stages-above-cap read: DoD assessments {total_assessments}, "
        f"DoD answer rows {total_rows}"
    )
    for status, (assessments, rows) in read.items():
        print(f"  {status} read: assessments {assessments}, answer rows {rows}")
    if total_rows == 0:
        # A zero over nothing read is not a clean result, and must not look like one.
        print(
            "count-zt-stages-above-cap: NOTHING TO MEASURE: no DoD answer rows were read, "
            "so the zeros below are not a clean result"
        )
    for status, overs in result.items():
        current = sum(1 for o in overs if o[0] == "current")
        target = sum(1 for o in overs if o[0] == "target")
        print(f"  {status}: current stage over {current}, target over {target}")
        for field, assessment_id, code, stage in sorted(overs):
            print(f"    {field} {assessment_id} {code} = {stage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
