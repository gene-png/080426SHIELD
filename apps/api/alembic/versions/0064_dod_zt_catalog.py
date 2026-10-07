"""The DoD ZT catalog becomes the 2025 DoD CIO roadmap's 45 capabilities (#839): data only.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-06

#839 corrects the DoD catalog to the DoD Zero Trust Execution Roadmap (DoD CIO,
2025, 25-T-1465). Per non-discarded DoD assessment:

* **Swapped (2):** `DOD.DAT.06` <-> `DOD.DAT.07`. Kentro had Data Access Control
  at 06 and Data Loss Prevention at 07; DoD numbers them 4.7 and 4.6. The swap
  goes through a temporary code because (assessment, code) is unique.
* **Inserted:** an empty `DOD.USR.09` (Integrated ICAM Platform, 1.9) where the
  assessment does not have it.
* **Retired (6):** `DOD.APP.06`, `DOD.APP.07`, `DOD.NET.05`, `DOD.NET.06`,
  `DOD.NET.07`, `DOD.VIS.07` are KEPT, untouched (decision 4, option B), and
  disclosed by `zt/retired.py`. Nothing is deleted.
* `risk_entries.source_id` and `risk_entries.linked_controls` holding a swapped
  code are swapped the same way.

Released assessments ARE migrated (D-107). The codes are written here, not
imported from `app.zt.catalog`: a migration records what it did at the time.
SQLite-safe: no schema change.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0064"
down_revision: str | Sequence[str] | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SWAP = {"DOD.DAT.06": "DOD.DAT.07", "DOD.DAT.07": "DOD.DAT.06"}
_TEMP = "DOD.DAT.SWAP"
NEW = ("DOD.USR.09",)
_DOD = "DOD_ZTRA"  # SAEnum stores the member NAME (native_enum=False)
_DISCARDED = "DISCARDED"

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
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
_risk = sa.table(
    "risk_entries",
    sa.column("id", sa.Uuid()),
    sa.column("source_id", sa.String()),
    sa.column("linked_controls", _JSON),
)


def _dod_assessments(conn) -> list:
    return conn.execute(
        sa.select(_assessments.c.id, _assessments.c.client_id).where(
            _assessments.c.framework == _DOD, _assessments.c.status != _DISCARDED
        )
    ).all()


def _swap_answers(conn, aid) -> None:
    """DAT.06 <-> DAT.07 for one assessment, through a temporary code."""
    rows = _answers.c
    conn.execute(
        _answers.update()
        .where(rows.assessment_id == aid, rows.capability_code == "DOD.DAT.06")
        .values(capability_code=_TEMP)
    )
    conn.execute(
        _answers.update()
        .where(rows.assessment_id == aid, rows.capability_code == "DOD.DAT.07")
        .values(capability_code="DOD.DAT.06")
    )
    conn.execute(
        _answers.update()
        .where(rows.assessment_id == aid, rows.capability_code == _TEMP)
        .values(capability_code="DOD.DAT.07")
    )


def _swap_risk(conn) -> tuple[int, int]:
    """The same swap on every risk entry's `source_id` and `linked_controls`.
    Every register's, not only one drawn from a migrated assessment: the codes
    are DoD's, so no CISA link can match, and a link to DAT.06 meant the
    capability, which is now numbered DAT.07."""
    sources = 0
    for rid, sid in conn.execute(
        sa.select(_risk.c.id, _risk.c.source_id).where(_risk.c.source_id.in_(list(SWAP)))
    ).all():
        conn.execute(_risk.update().where(_risk.c.id == rid).values(source_id=SWAP[sid]))
        sources += 1
    linked = 0
    for rid, controls in conn.execute(
        sa.select(_risk.c.id, _risk.c.linked_controls).where(_risk.c.linked_controls.is_not(None))
    ).all():
        if not isinstance(controls, list):
            continue
        swapped = [SWAP.get(c, c) for c in controls]
        if swapped != controls:
            conn.execute(_risk.update().where(_risk.c.id == rid).values(linked_controls=swapped))
            linked += 1
    return sources, linked


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    swapped = inserted = 0
    for aid, cid in _dod_assessments(conn):
        _swap_answers(conn, aid)
        swapped += 1
        have = set(
            conn.execute(
                sa.select(_answers.c.capability_code).where(_answers.c.assessment_id == aid)
            ).scalars()
        )
        for code in NEW:
            if code in have:
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
    sources, linked = _swap_risk(conn)
    print(
        f"[0064] swapped DAT.06/07 in {swapped} assessment(s); inserted {inserted} "
        f"empty USR.09 row(s); swapped {sources} risk source(s) and the linked "
        f"controls of {linked} risk entr(ies). Retired rows are kept, not deleted."
    )


def downgrade() -> None:
    """The swap is its own inverse. Delete only inserted rows that still hold
    nothing, by the same test as `zt/retired.has_recorded_answer`, so a
    downgrade never deletes an answer."""
    conn = op.get_bind()
    empty = sa.and_(
        _answers.c.maturity_stage.is_(None),
        _answers.c.target_stage.is_(None),
        sa.or_(_answers.c.notes.is_(None), sa.func.trim(_answers.c.notes) == ""),
        _answers.c.evidence_artifact_id.is_(None),
    )
    for aid, _cid in _dod_assessments(conn):
        _swap_answers(conn, aid)
        conn.execute(
            _answers.delete().where(
                _answers.c.assessment_id == aid,
                _answers.c.capability_code.in_(NEW),
                empty,
            )
        )
    _swap_risk(conn)
