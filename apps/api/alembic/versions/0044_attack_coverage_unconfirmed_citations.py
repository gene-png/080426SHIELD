"""attack_coverage.unconfirmed_citations — which evidence a human has not vouched for

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-20 00:00:00

Closes the storage half of #101 and is the prerequisite for #102.

W2's resolver decides whether a cited tool name matched exactly (CONFIRMED) or
had to be inferred (NEEDS_REVIEW — a punctuation rescue, a substring, a vendor
match, or a vendor match made against a list with missing vendors). That
distinction existed only in the transient `run_ai` response: reload the page and
the record that a citation was inferred was gone. `citations.py` called it
"queued for a human" and the panel said "check them before release"; neither was
true, because there was no queue and nothing to check against.

This is the same lesson migration 0036 records for the Tech Debt reconciliation —
"persisted because the workspace re-fetches the list on every load, and a
disclosure that vanishes on refresh is no disclosure."

Shape: `[{"tool": ..., "reason": ..., "field": ..., "cleared_at": ...}]`.
`reason` is a `ReviewReason` value, `field` is which of detection/prevention/
response the citation supported, and `cleared_at` is NULL until a human vouches
for it. Keeping the cleared ones rather than deleting them is deliberate: #102
scores on whether support is confirmed, and "a human looked at this and accepted
it" is a different state from "nobody ever cited it", which matters to anyone
auditing why a technique counts.

JSON rather than a table: it is a small per-row list, always read whole with its
row, and never joined or filtered on.

THREE values, and the distinction is the whole point:

* ``NULL``  — citations were never resolved; this row predates the resolver.
* ``[]``    — resolved, and nothing needed inferring.
* ``[...]`` — resolved, and these citations were inferred.

**NULL scores as PENDING, not as confirmed.** An earlier draft of this docstring
said #102 should "leave such a technique scoring exactly as it does today". That
is the fail-open reading: an assessment whose citations were never checked would
have read as fully confirmed because nothing on record contradicted it — the
same shape D-054 rejected on the nullable-vendor default, one layer down. Absence
of evidence is not evidence of confirmation.

Fail-closed is affordable here and was checked rather than assumed: **zero**
RELEASED ATT&CK assessments exist, and there is no production deployment, so no
client-facing number is retroactively changed. What it costs is one Run-AI on
each of the existing drafts to resolve their citations — which is exactly the
work that was never done for them.

`seed_demo.py` writes ``[]`` explicitly for the rows it creates. That is a
deliberate, single-place assertion that seeded demo data is confirmed, rather
than every pre-migration row being grandfathered in by a default nobody chose.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0044"
down_revision: str | None = "0043"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # batch_alter_table: tests run SQLite, prod runs Postgres.
    with op.batch_alter_table("attack_coverage") as batch:
        batch.add_column(sa.Column("unconfirmed_citations", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attack_coverage") as batch:
        batch.drop_column("unconfirmed_citations")
