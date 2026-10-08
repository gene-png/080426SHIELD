"""The CSF catalog is corrected toward NIST CSWP 29, not yet source-pinned (#852): data only.

Revision ID: 0064
Revises: 0063
Create Date: 2026-10-08

#852 corrected two rows of the CSF catalog toward NIST CSWP 29 (CSF 2.0), per
the issue's comparison with the PDF: CSF 2.0 has no `ID.AM-09`, which the
catalog held, and has `RC.CO-04`, which it lacked. No test yet pins the code set
to the PDF; #852 stays open until one does. Per non-discarded CSF assessment
(draft, submitted, approved, released):

* **Inserted:** an empty `RC.CO-04` answer where the assessment does not have
  one, and an empty `RC.CO-04` Working Profile row for each tier the assessment
  had already seeded, with the seed's own defaults. Without the answer row the
  questionnaire cannot show the subcategory at all (it renders a catalog code
  only when a row exists), and without the Working Profile row a seeded profile
  could never get one (seeding is offered only while nothing is seeded). An
  existing row is never duplicated or overwritten.
* **Retired:** rows on `ID.AM-09`, in `csf_answers`, `csf_dimension_scores` and
  `csf_gap_actions`, are KEPT, untouched (the approved plan, #736 comment
  6054419744, the pattern 0063 used for retired CISA rows, and #925 uses for
  DoD). The scoring and gap engines iterate the catalog, and every reader of
  stored rows filters to it (`app.csf.retired.catalog_rows`), so they are not
  scored; the workspace, the self-assessment, the deliverable, the client dashboard, the
  Working Profile and the playbook files disclose how many hold an answer.
  Nothing is deleted.
* `risk_entries` are NOT touched: CSF 2.0 has no successor for `ID.AM-09`, so
  there is nothing to re-key to. A register generated after this draws no
  finding from it (`routes/risk.py`).

Released assessments ARE migrated (D-107): no real client is onboarded yet.
The codes are written here, not imported from `app.csf.catalog`: a migration
records what it did at the time. Statuses are the enum member NAMES, which is
what the column stores. SQLite-safe: no schema change.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | Sequence[str] | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = "RC.CO-04"
_DISCARDED = "DISCARDED"  # SAEnum stores the member NAME (native_enum=False)

_assessments = sa.table(
    "csf_assessments",
    sa.column("id", sa.Uuid()),
    sa.column("client_id", sa.Uuid()),
    sa.column("status", sa.String()),
)
_answers = sa.table(
    "csf_answers",
    sa.column("id", sa.Uuid()),
    sa.column("assessment_id", sa.Uuid()),
    sa.column("client_id", sa.Uuid()),
    sa.column("subcategory_code", sa.String()),
    sa.column("maturity_tier", sa.SmallInteger()),
    sa.column("notes", sa.Text()),
    sa.column("evidence_artifact_id", sa.Uuid()),
    sa.column("locked", sa.Boolean()),
    sa.column("answered_by", sa.Uuid()),
    sa.column("answered_at", sa.DateTime(timezone=True)),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)
_scores = sa.table(
    "csf_dimension_scores",
    sa.column("id", sa.Uuid()),
    sa.column("assessment_id", sa.Uuid()),
    sa.column("client_id", sa.Uuid()),
    sa.column("tier", sa.String()),
    sa.column("subcategory_code", sa.String()),
    sa.column("governance", sa.SmallInteger()),
    sa.column("policy", sa.SmallInteger()),
    sa.column("implementation", sa.SmallInteger()),
    sa.column("monitoring", sa.SmallInteger()),
    sa.column("improvement", sa.SmallInteger()),
    sa.column("in_scope", sa.Boolean()),
    sa.column("rationale", sa.Text()),
    sa.column("what_we_found", sa.Text()),
    sa.column("evidence_artifact_id", sa.Uuid()),
    sa.column("has_evidence", sa.Boolean()),
    sa.column("target_level", sa.SmallInteger()),
    sa.column("locked", sa.Boolean()),
    sa.column("answer_source", sa.String()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)

_DIMENSIONS = ("governance", "policy", "implementation", "monitoring", "improvement")

#: What seeding writes on a Working Profile row (`routes/csf.py::seed_profiles`
#: relies on the model defaults; `sa.table` applies none, so they are explicit).
_SEED_DEFAULTS = {
    "governance": 0,
    "policy": 0,
    "implementation": 0,
    "monitoring": 0,
    "improvement": 0,
    "in_scope": True,
    "has_evidence": False,
    "locked": False,
}


def _csf_assessments(conn) -> list:
    return conn.execute(
        sa.select(_assessments.c.id, _assessments.c.client_id).where(
            _assessments.c.status != _DISCARDED
        )
    ).all()


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(UTC)
    answers = scores = 0
    for aid, cid in _csf_assessments(conn):
        has_answer = conn.execute(
            sa.select(_answers.c.id).where(
                _answers.c.assessment_id == aid, _answers.c.subcategory_code == NEW
            )
        ).first()
        if has_answer is None:
            conn.execute(
                _answers.insert().values(
                    id=uuid.uuid4(),
                    assessment_id=aid,
                    client_id=cid,
                    subcategory_code=NEW,
                    locked=False,
                    created_at=now,
                    updated_at=now,
                )
            )
            answers += 1
        seeded = set(
            conn.execute(
                sa.select(_scores.c.tier).where(_scores.c.assessment_id == aid).distinct()
            ).scalars()
        )
        present = set(
            conn.execute(
                sa.select(_scores.c.tier).where(
                    _scores.c.assessment_id == aid, _scores.c.subcategory_code == NEW
                )
            ).scalars()
        )
        for tier in sorted(seeded - present):
            conn.execute(
                _scores.insert().values(
                    id=uuid.uuid4(),
                    assessment_id=aid,
                    client_id=cid,
                    tier=tier,
                    subcategory_code=NEW,
                    created_at=now,
                    updated_at=now,
                    **_SEED_DEFAULTS,
                )
            )
            scores += 1
    print(
        f"[0064] inserted {answers} empty RC.CO-04 answer row(s) and {scores} empty RC.CO-04 "
        "Working Profile row(s). ID.AM-09 rows are kept, not deleted; risk entries untouched."
    )


def downgrade() -> None:
    """Delete only the `RC.CO-04` rows that still carry nothing. A row someone
    has since answered or scored is kept: downgrading never deletes an answer.
    `ID.AM-09` rows were never touched and are not touched here."""
    conn = op.get_bind()
    blank = lambda col: sa.or_(col.is_(None), sa.func.trim(col) == "")  # noqa: E731
    ids = [aid for aid, _cid in _csf_assessments(conn)]
    if not ids:
        return
    conn.execute(
        _answers.delete().where(
            _answers.c.assessment_id.in_(ids),
            _answers.c.subcategory_code == NEW,
            _answers.c.maturity_tier.is_(None),
            blank(_answers.c.notes),
            _answers.c.evidence_artifact_id.is_(None),
            _answers.c.answered_by.is_(None),
            # A locked row is kept, empty or not, as the Working Profile half
            # below keeps one: locking is a consultant's "never touch this".
            _answers.c.locked.is_(False),
        )
    )
    conn.execute(
        _scores.delete().where(
            _scores.c.assessment_id.in_(ids),
            _scores.c.subcategory_code == NEW,
            _scores.c.answer_source.is_(None),
            *(getattr(_scores.c, f) == 0 for f in _DIMENSIONS),
            _scores.c.in_scope.is_(True),
            _scores.c.has_evidence.is_(False),
            _scores.c.locked.is_(False),
            _scores.c.target_level.is_(None),
            _scores.c.evidence_artifact_id.is_(None),
            blank(_scores.c.rationale),
            blank(_scores.c.what_we_found),
        )
    )
