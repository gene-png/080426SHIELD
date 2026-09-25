"""Record the ATT&CK catalog version each assessment was scored against (#556, D-091).

The catalog is now generated from MITRE's STIX (v19.2). The hand-encoded list it
replaces matched no released version. An assessment's coverage rows are keyed by
technique code and pre-seeded from whatever catalog existed when the assessment
was created, so an assessment scored against the old list holds codes the new
catalog does not have (all of T1562, four non-existent T1649.00x) and lacks rows
for techniques it never saw (all of T1553).

The readers that compute coverage used to DROP any row whose code was not in the
catalog, silently. After a catalog change that would have turned every existing
assessment into a percentage over an undisclosed, mixed set. This column lets
them refuse instead: an assessment is computed only when its `catalog_version`
equals the catalog's `SOURCE_VERSION`.

## Existing rows stay NULL, deliberately

NULL means "scored against an unrecorded catalog". That is the true state of
every row that predates this migration: the old catalog carried a version label
it did not satisfy. Backfilling "15" or "19.2" would write a claim nobody can
support. Missing data defaults to unconfirmed, never to confirmed (CLAUDE.md).

## Blast radius, measured before choosing

Measured 2026-09-24: 0 real client ATT&CK assessments in any environment this
repo defines. The dev database holds 4, all test data: the seeded demo, an
e2e-minted client, and the synthetic client of #555. On the dev stack they are
rescored by resetting it: the workspace has no control that starts a new version
after approval (#558). That rests on one condition nobody here can check: no
real engagement ran on a stack this session could not see.

## Chain order: 0051 -> 0053 -> 0052

Written as the next revision after 0051, while #569's 0053 was also open and also
chained from 0051. #569 merged first, so this revision now follows 0053 to keep
a single head. The id stays `0052`: alembic orders by the chain, not by the
number, and renaming would change every reference to it for no behaviour.

SQLite-safe via `batch_alter_table` (core principle 6); additive and nullable,
so older code reading a newer database is unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052"
down_revision: str | Sequence[str] | None = "0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("attack_assessments") as batch:
        batch.add_column(sa.Column("catalog_version", sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("attack_assessments") as batch:
        batch.drop_column("catalog_version")
