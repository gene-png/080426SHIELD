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

Shape: `[{"tool": ..., "cited": ..., "reason": ..., "field": ..., "cleared_at": ...}]`.

`cited` is what the model actually wrote and `tool` is what the resolver turned
it into; the difference is the part a consultant acts on, because "Qradar" tells
them the list holds "Splunk Enterprise" where the resolved name tells them
nothing. `field` is which of detection/prevention/response the citation
supported. `cleared_at` is NULL until a human vouches for it. Keeping the cleared
ones rather than deleting them is deliberate: #102 scores on whether support is
confirmed, and "a human looked at this and accepted it" is a different state from
"nobody ever cited it", which matters to anyone auditing why a technique counts.

`tool` is NULL for the two outcomes that applied no capability, and `reason`
says which:

* `rejected_unknown` / `rejected_ambiguous` -- the model named a tool and the
  resolver could not place it. `cited` carries the name it used.
* `no_citation` -- the model assigned a positive status and named nothing at
  all, so `cited` and `field` are both NULL too.

Neither has a tool to record, which is precisely why both are recorded. Without
them a `covered` row whose evidence was dropped stores identically to a `covered`
row a consultant typed in by hand, and #102 has to withhold the first while
leaving the second alone. See `app/attack/pending.py`.

JSON rather than a table: it is a small per-row list, always read whole with its
row, and never joined or filtered on.

THREE values, and the distinction is the whole point:

* ``NULL``  — citations were never resolved; this row predates the resolver.
* ``[]``    — resolved, and nothing is outstanding: either every citation
  matched exactly, or a human authored the row themselves.
* ``[...]`` — resolved, and these citations were inferred, rejected, or never
  made at all.

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
It also now gives its `covered` and `partial` rows real tool names: they carried
a positive status over EMPTY tool lists, which is the very shape #102 exists to
withhold, so the demo was modelling the defect. `_seed_attack` refuses to write
rows the rule would withhold rather than leaving the demo to report a coverage
number its own data does not support.
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
