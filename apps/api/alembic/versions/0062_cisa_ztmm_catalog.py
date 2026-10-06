"""The CISA ZT catalog becomes CISA ZTMM 2.0's 37 rows (#838): data only.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-04

#838 replaced 8 pillars (with 13 rows CISA does not have) by CISA's 5 pillars,
each holding its functions and its own three cross-cutting rows. The 22 function
codes are unchanged. What moves, per non-discarded CISA assessment:

* **Mapped (2):** `CISA.ID.05` -> `CISA.ID.VA` and `CISA.DV.05` -> `CISA.DV.VA`,
  the same rows under Kentro's old names (#838 decision 3). A target that already
  exists is never overwritten: the old row then stays where it is, as a retired
  row, and is disclosed like the others.
* **Inserted:** an empty row for every one of the 15 cross-cutting codes the
  assessment does not have, so a new row reads "unscored", never "missing".
* **Retired (13, plus any unmapped):** `CISA.VA.*`, `CISA.AO.*`, `CISA.GV.*`
  rows are KEPT, untouched (decision 4, option B). The ZT scoring and gap
  engines iterate the catalog, and Risk synthesis filters to its codes
  (`routes/risk.py`), so they are not scored; the workspace, the client's
  self-assessment and the exports disclose how many hold a recorded answer.
  Nothing is deleted. A reader that reads stored rows without either is a
  defect this note does not cover.
* `risk_entries.source_id` and `risk_entries.linked_controls` holding a mapped
  code are re-keyed the same way.

The codes are written here, not imported from `app.zt.catalog`: a migration
records what it did at the time, and must not change when the catalog does.
SQLite-safe: no schema change.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0062"
down_revision: str | Sequence[str] | None = "0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAPPED = {"CISA.ID.05": "CISA.ID.VA", "CISA.DV.05": "CISA.DV.VA"}
NEW = tuple(f"CISA.{p}.{s}" for p in ("ID", "DV", "NW", "AW", "DT") for s in ("VA", "AO", "GV"))
_CISA = "CISA_ZTMM_2_0"  # SAEnum stores the member NAME (native_enum=False)
_DISCARDED = "DISCARDED"

_assessments = sa.table(
    "zt_assessments",
    sa.column("id", sa.Uuid()),
    sa.column("client_id", sa.Uuid()),
    sa.column("framework", sa.String()),
    sa.column("status", sa.String()),
)
_answers = sa.table(
    "zt_answers",
    sa.column("id", sa.Uuid()),
    sa.column("assessment_id", sa.Uuid()),
    sa.column("client_id", sa.Uuid()),
    sa.column("capability_code", sa.String()),
    sa.column("maturity_stage", sa.SmallInteger()),
    sa.column("target_stage", sa.SmallInteger()),
    sa.column("notes", sa.Text()),
    sa.column("answer_source", sa.String()),
    sa.column("evidence_artifact_id", sa.Uuid()),
    sa.column("locked", sa.Boolean()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
_risk = sa.table(
    "risk_entries",
    sa.column("id", sa.Uuid()),
    sa.column("source_id", sa.String()),
    sa.column("linked_controls", _JSON),
)


def _rekey_linked_controls(conn, mapping: dict[str, str]) -> int:
    """Re-key every risk entry's `linked_controls` (the codes the exported
    register prints) by `mapping`, in place and in order. Returns how many
    entries changed."""
    changed = 0
    rows = conn.execute(
        sa.select(_risk.c.id, _risk.c.linked_controls).where(_risk.c.linked_controls.is_not(None))
    ).all()
    for rid, controls in rows:
        if not isinstance(controls, list):
            continue  # not a list of codes: nothing this mapping can name
        rekeyed = [mapping.get(c, c) for c in controls]
        if rekeyed != controls:
            conn.execute(_risk.update().where(_risk.c.id == rid).values(linked_controls=rekeyed))
            changed += 1
    return changed


def _cisa_assessments(conn) -> list:
    return conn.execute(
        sa.select(_assessments.c.id, _assessments.c.client_id).where(
            _assessments.c.framework == _CISA, _assessments.c.status != _DISCARDED
        )
    ).all()


def _codes(conn, assessment_id) -> set[str]:
    return set(
        conn.execute(
            sa.select(_answers.c.capability_code).where(_answers.c.assessment_id == assessment_id)
        ).scalars()
    )


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    mapped = kept_old = inserted = 0
    for aid, cid in _cisa_assessments(conn):
        codes = _codes(conn, aid)
        for old, new in MAPPED.items():
            if old not in codes:
                continue
            if new in codes:
                kept_old += 1  # never overwrite: the old row stays, retired and disclosed
                continue
            conn.execute(
                _answers.update()
                .where(_answers.c.assessment_id == aid, _answers.c.capability_code == old)
                .values(capability_code=new)
            )
            codes.discard(old)
            codes.add(new)
            mapped += 1
        for code in NEW:
            if code in codes:
                continue
            conn.execute(
                _answers.insert().values(
                    id=uuid.uuid4(),
                    assessment_id=aid,
                    client_id=cid,
                    capability_code=code,
                    locked=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1
    risk = 0
    for old, new in MAPPED.items():
        risk += conn.execute(
            _risk.update().where(_risk.c.source_id == old).values(source_id=new)
        ).rowcount
    linked = _rekey_linked_controls(conn, MAPPED)
    print(
        f"[0062] mapped {mapped} row(s); kept {kept_old} old row(s) whose target "
        f"existed; inserted {inserted} empty cross-cutting row(s); re-keyed {risk} "
        f"risk source(s) and the linked controls of {linked} risk entr(ies). Retired rows are "
        "kept, not deleted."
    )


def downgrade() -> None:
    """Reverse the mapping where it can be reversed, and delete only the rows
    this upgrade inserted that still carry nothing. A cross-cutting row someone
    has since answered is kept: downgrading never deletes an answer."""
    conn = op.get_bind()
    empty = sa.and_(
        _answers.c.maturity_stage.is_(None),
        _answers.c.target_stage.is_(None),
        sa.or_(_answers.c.notes.is_(None), _answers.c.notes == ""),
        _answers.c.answer_source.is_(None),
        _answers.c.evidence_artifact_id.is_(None),
    )
    for aid, _cid in _cisa_assessments(conn):
        codes = _codes(conn, aid)
        for old, new in MAPPED.items():
            if new in codes and old not in codes:
                conn.execute(
                    _answers.update()
                    .where(_answers.c.assessment_id == aid, _answers.c.capability_code == new)
                    .values(capability_code=old)
                )
        conn.execute(
            _answers.delete().where(
                _answers.c.assessment_id == aid,
                _answers.c.capability_code.in_(NEW),
                empty,
            )
        )
    for old, new in MAPPED.items():
        conn.execute(_risk.update().where(_risk.c.source_id == new).values(source_id=old))
    _rekey_linked_controls(conn, {new: old for old, new in MAPPED.items()})
