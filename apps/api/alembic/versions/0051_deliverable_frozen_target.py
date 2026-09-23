"""Freeze the engagement target a deliverable was rendered against (#209).

A client dashboard resolved the engagement target LIVE on every request while the
released document held the number it was rendered with. Change the intake target
after release and the two disagree: the PDF says "37 gaps at target S4" and the
dashboard beside it says something else, computed from the same approved answers.
Both are internally consistent, and one is a number the client never contracted
for.

Two nullable columns on `deliverables`, structurally twinned with
`parent_version` (0041): same table, same nullable shape, same "NULL = predates
this migration" contract, stamped at the same moment.

## ONE PAIR, NOT TWO PER LADDER

`Service.kind` discriminates, so a CSF deliverable's `frozen_target` is a tier
and a ZT one's is a stage. Two pairs would force every reader to know which was
populated, and the kind already answers that.

## Why the source column and not just the number

`target_stage_source` already drives client copy through `targetNote`. Freeze the
number alone and a client who clears their target after release gets a frozen `4`
captioned by a LIVE source of `default` -- "Default target" printed over the stage
they contracted for. The number and its provenance have to freeze together or the
caption lies about the figure beside it.

## WHAT IS FROZEN: THE CLIENT'S CHOSEN VALUE, NOT THE RESOLVED ONE

`frozen_target` holds what the client stored at intake -- `csf_target_tier` or
`zt_target_stage`, a `SmallInteger | None`. The dashboard then runs the SAME
resolver it runs today (`zt_resolve_target_stage` / `csf_resolve_target_tier`)
over that frozen input.

That is a DERIVATION rather than a SYNCHRONIZATION, which is the standing
preference: freeze the resolver's OUTPUT and the number and its caption become
two stored values that have to be kept in agreement with a pure function by
hand. Freeze its INPUT and they cannot disagree, because the same deterministic
call produces both.

## `frozen_target_source` IS THE DISCRIMINATOR, NOT A COPY OF THE RESOLVER'S SOURCE

The name is a trap and is spelled out for that reason. `target_stage_source` --
the field this one sits beside in every response -- is the RESOLVER's verdict
(`client`, `default`, `client_out_of_range`, `client_unparseable`). This column
is nothing of the kind. It records HOW THE FREEZE WAS ESTABLISHED:

  * `finalize`   -- stamped by the finalize route. Exact.
  * `audit`      -- backfilled from the finalize audit row. Exact.
  * `updated_at` -- backfilled by inference; see the predicate below.
  * NULL         -- never frozen. COMPUTE LIVE AND SAY SO.

It exists because **`frozen_target IS NULL` carries two facts otherwise.** A
client who chose no target has a legitimately NULL choice, frozen exactly; a
deliverable predating this migration has no freeze at all. Same bytes, opposite
meanings, and the second must fall back to live computation while the first must
NOT. The source column is what tells them apart, so every read path branches on
`frozen_target_source IS NULL` and never on `frozen_target IS NULL`.

## BACKFILL: two sources, never a guess

1. **The finalize audit row**, where one exists -- exact. It records the
   RESOLVED pair, so it is read backwards to recover the input:
   `target_stage_source == "client"` means the stored choice was usable and
   equal to `target_stage`, so freeze that integer; `"default"` means the
   resolver was handed NULL, so freeze NULL. Dialect-aware, because `details`
   is a dict on psycopg and a JSON string on SQLite.

   `client_out_of_range` and `client_unparseable` are DECLINED BY THIS ARM
   rather than guessed. The audit row holds only the RESOLVED number -- the
   framework default in both cases -- so freezing it would relabel the client's
   own broken choice as "no choice made", turning a disclosure into a silent
   correction.

   **DECLINED BY THIS ARM IS NOT THE SAME AS UNFROZEN, and an earlier version of
   this paragraph said it was.** Predicate 2 reads the RAW column, so where the
   intake row has not been written since, it recovers the out-of-range value
   VERBATIM and freezes it -- which is correct and strictly better: the resolver
   is deterministic, so the stored 9 reproduces both the rendered default and
   the `client_out_of_range` source exactly as the released report had them. The
   row ends unfrozen only when BOTH arms decline. The test that found this
   asserted the old claim and failed.
2. **`updated_at <= finalized_at`** on the source `service_requests` row as the
   fallback: the row has not been written since the deliverable froze, so the
   stored target IS the frozen one.
3. **NULL otherwise.** Missing data defaults to UNCONFIRMED, never to confirmed.

### Three residuals, stated rather than discovered later

`updated_at` moves on ANY write to `service_requests`, so predicate 2
UNDER-backfills -- the safe direction: a row that was touched for an unrelated
reason gets NULL and the dashboard computes live and says so.

`onupdate` is SQLAlchemy-level, not a database trigger, so a raw-SQL write to
`service_requests` would leave `updated_at` stale and freeze a drifted value as
though it were original. No product code does that -- `submit_self_assessment`
writes through the ORM -- but it is a fail-OPEN and it is written down here
because nothing else would say so.

Predicate 2 requires the stored target to be NON-NULL, so it can never
establish the "the client chose nothing" freeze -- only source 1 can. That is
under-backfilling again, in the same safe direction, and it is the reason the
two sources are not interchangeable.

## Blast radius, measured before choosing

Dev Postgres, per 0047's precedent:

    SELECT count(*) FROM deliverables WHERE released_at IS NOT NULL;                 -> 6
    SELECT count(*) FROM deliverables WHERE released_at IS NOT NULL
      AND finalized_at IS NOT NULL;                                                  -> 6
    SELECT count(*) FROM deliverables;                                               -> 6

<!-- counted: docker compose exec -T db psql -U shield -d shield -At, the three
     SELECT count(*) statements above, 2026-09-22 -->

Every deliverable on dev is released AND finalized, so the backfill has six rows
to consider and no unfinalized ones to skip.

**THESE NUMBERS WERE WRITTEN BEFORE THE QUERY WAS RUN, AND THEY WERE WRONG.**
The first version of this block said 2 / 2 / 3. That is the mistake 0049 already
records -- writing a `MEASURED` block from expectation and then running the query
-- and it is recorded here rather than silently corrected because the whole point
of a blast-radius block is that a reader can trust the figure without re-running
it. A corrected number with no note reads exactly like one that was right.

`seed_demo.py` stamps both columns in the same commit as this migration, so CI
and a fresh dev database start with zero rows in the NULL branch. That is the
argument for landing the migration and the seed change together rather than in
sequence: split them and every CI run exercises only the backfill path, which is
the path that will almost never run in production.

## THE POSTGRES BRANCH IS RUN BY NO TEST, SO IT WAS RUN BY HAND

Every pytest fixture points `DATABASE_URL` at its own SQLite file, and CI's E2E
job seeds through `seed_demo.py`, which stamps at finalize -- so the backfill has
nothing to do there. **Nothing in this repository executes the
`UPDATE ... FROM` branch below.** A syntax error in it would take the whole
upgrade down in production with every gate green.

Measured 2026-09-22 against a throwaway `postgres:16-alpine`: the full chain
upgraded to 0051, then `downgrade 0050` / `upgrade 0051` over three hand-seeded
rows.

    A v1     finalized, intake row untouched since  -> frozen_target=4, source=updated_at
    B v1     finalized, intake row written AFTER    -> unfrozen
    A draft  not finalized                          -> unfrozen

Log line: `0 row(s) from the finalize audit and 1 from updated_at; declined 0;
2 row(s) remain unfrozen`. That is the same behaviour
`tests/unit/test_migration_0051_backfill.py` asserts on SQLite, on the dialect
arm those tests cannot reach.

Two things went wrong getting there and both looked like success: `psql -f` with
no `-v ON_ERROR_STOP=1` returned 0 over nine aborted statements, and a
`docker cp` under `MSYS_NO_PATHCONV=1` had its SOURCE path rewritten to a
Windows path that does not exist, so it failed. Each produced a "0 row(s)"
report over an empty table, which is indistinguishable from a clean run. The
row-level readback is what caught both -- an instance of the standing rule that
when a command's status cannot be trusted, check the artifact it was supposed to
produce.

## SQLite-safe

`batch_alter_table` for both directions (core principle 6). Tests run SQLite and
production runs Postgres, and `ALTER TABLE ... DROP COLUMN` is what SQLite could
not do before 3.35 -- the batch form rebuilds the table instead.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0051"
down_revision: str | Sequence[str] | None = "0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

#: `(value, source)` key pairs in the finalize audit payload, per service kind.
#: The audit row is written by the four finalize routes and is the only EXACT
#: record of what the deliverable was rendered against.
_AUDIT_KEYS = (("target_stage", "target_stage_source"), ("target_tier", "target_tier_source"))

#: The one resolver source meaning "the client's stored choice was usable".
#: `zt.scoring.resolve_target_stage` and `csf.gap.resolve_target_tier` both
#: return it, and `routes/clients.py::CLIENT_CHOSE_IT` is the same constant --
#: not imported, because a migration must not depend on today's application code
#: (0044 records why), and stated here so the duplication is deliberate.
_SOURCE_CLIENT = "client"

#: The resolver source meaning "the resolver was handed NULL", which is
#: recoverable as a freeze of NULL. Everything else -- `client_out_of_range`,
#: `client_unparseable` -- is declined; see the docstring.
_SOURCE_NO_CHOICE = "default"


def _details_dict(raw: object) -> dict:
    """`audit_log.details` as a dict, on either backend.

    psycopg hands back a dict for a JSONB column; SQLite hands back the JSON
    TEXT. A migration that assumed one would silently backfill nothing on the
    other -- and "nothing backfilled" is indistinguishable from "no rows
    matched", which is the report this repo keeps mistaking for success.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (str, bytes)):
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def upgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.add_column(sa.Column("frozen_target", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("frozen_target_source", sa.String(length=16), nullable=True))

    conn = op.get_bind()

    # SOURCE 1: the finalize audit row. Exact, and preferred wherever it exists.
    #
    # Read in PYTHON rather than as one SQL statement, for the reason 0050
    # records: the JSON shape differs per backend, and a `json_extract` / `->>`
    # split would be two predicates that have to be kept in agreement by hand.
    # One reader, one definition.
    #
    # THE FIRST VERSION OF THIS QUERY NAMED `audit_log` ORDERED BY `created_at`,
    # and both were wrong -- it died with `no such table: audit_log` on the first
    # SQLite run. Recorded because the failure was LOUD and the near-miss was
    # not: a migration whose backfill query cannot execute takes the whole
    # upgrade down in production, and nothing about READING the file said so.
    # The table is `audit_entries` and its timestamp column is `at`.
    #
    # The four finalize actions are `zt.`, `csf.`, `attack.` and a bare
    # `deliverable.finalized` from tech_debt, so the pattern is a SUFFIX match
    # rather than an enumeration of the prefixes -- a fifth service would
    # otherwise be silently unbackfilled.
    audit_rows = conn.execute(
        sa.text(
            "SELECT a.target_id, a.details FROM audit_entries a"
            " WHERE a.action LIKE '%deliverable.finalized'"
            "   AND a.target_type = 'deliverable'"
            " ORDER BY a.at"
        )
    ).fetchall()

    # deliverable id -> the CHOSEN value to freeze, which may legitimately be
    # None. A declined row is absent from this dict entirely; `None` as a VALUE
    # means "frozen, and the client had chosen nothing", so the dict must be
    # read by MEMBERSHIP downstream and never by `.get(id) is None`.
    from_audit: dict[str, int | None] = {}
    declined = 0
    for target_id, raw in audit_rows:
        details = _details_dict(raw)
        for value_key, source_key in _AUDIT_KEYS:
            if value_key not in details:
                continue
            source = details.get(source_key)
            if source == _SOURCE_CLIENT:
                value = details.get(value_key)
                if isinstance(value, int) and not isinstance(value, bool):
                    from_audit[str(target_id)] = value
                else:
                    # The audit row says the client's choice was usable and then
                    # does not carry an integer. Declining is the only honest
                    # branch: this is the could-not-look case, not a clean one.
                    declined += 1
            elif source == _SOURCE_NO_CHOICE:
                from_audit[str(target_id)] = None
            else:
                declined += 1
            break

    stamped_from_audit = 0
    for deliverable_id, chosen in from_audit.items():
        # GUARDED ON THE SOURCE COLUMN, NOT THE VALUE. `frozen_target IS NULL`
        # is true of a row this loop has already stamped with a legitimate NULL
        # choice, so guarding on the value would let source 2 overwrite an EXACT
        # freeze with an INFERRED one. The source column is the discriminator
        # everywhere in this migration, for the reason the docstring gives.
        result = conn.execute(
            sa.text(
                "UPDATE deliverables SET frozen_target = :v, frozen_target_source = 'audit'"
                " WHERE id = :id AND frozen_target_source IS NULL"
            ),
            {"v": chosen, "id": deliverable_id},
        )
        stamped_from_audit += result.rowcount or 0

    # SOURCE 2: the source request has not been written since the deliverable
    # froze, so its stored target IS the frozen one. UNDER-backfills by design --
    # see the docstring's residuals.
    #
    # THE JOIN IS `s.source_request_id`, not `s.request_id`, and the first
    # version had the latter -- `no such column: s.request_id` on the first
    # SQLite run. `_zt_client_target_stage` in `routes/clients.py` is the
    # production resolver and it reaches the row through `svc.source_request_id`;
    # this backfill has to use the same link or it is answering a different
    # question about a different row.
    #
    # `csf_target_tier` and `zt_target_stage` are the two columns on
    # `service_requests`; COALESCE picks whichever the service kind populated,
    # and one pair of columns on `deliverables` receives it.
    from_updated_at = conn.execute(
        sa.text(
            "UPDATE deliverables SET frozen_target = sub.target,"
            "   frozen_target_source = 'updated_at'"
            " FROM ("
            "   SELECT d.id AS did,"
            "          COALESCE(sr.csf_target_tier, sr.zt_target_stage) AS target"
            "     FROM deliverables d"
            "     JOIN services s ON s.id = d.service_id"
            "     JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE d.frozen_target_source IS NULL"
            "      AND d.finalized_at IS NOT NULL"
            "      AND sr.updated_at <= d.finalized_at"
            "      AND COALESCE(sr.csf_target_tier, sr.zt_target_stage) IS NOT NULL"
            " ) AS sub"
            " WHERE deliverables.id = sub.did"
        )
        if conn.dialect.name == "postgresql"
        else sa.text(
            # SQLite has no UPDATE ... FROM before 3.33 and no guarantee of it in
            # the wheels this repo installs, so the correlated-subquery form is
            # used there. Two statements, one meaning, and the dialect split is
            # stated rather than left for a reader to infer from a crash.
            "UPDATE deliverables SET frozen_target = ("
            "   SELECT COALESCE(sr.csf_target_tier, sr.zt_target_stage)"
            "     FROM services s JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE s.id = deliverables.service_id"
            "      AND sr.updated_at <= deliverables.finalized_at"
            " ), frozen_target_source = 'updated_at'"
            " WHERE frozen_target_source IS NULL AND finalized_at IS NOT NULL AND ("
            "   SELECT COALESCE(sr.csf_target_tier, sr.zt_target_stage)"
            "     FROM services s JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE s.id = deliverables.service_id"
            "      AND sr.updated_at <= deliverables.finalized_at"
            " ) IS NOT NULL"
        )
    ).rowcount

    remaining = conn.execute(
        sa.text("SELECT count(*) FROM deliverables WHERE frozen_target_source IS NULL")
    ).scalar()

    # COUNTED, never asserted. FOUR numbers rather than one, because "0 stamped"
    # and "0 rows to stamp" are different facts that a single total cannot tell
    # apart -- the distinction 0050's log line exists for -- and because
    # `declined` is the one number nothing else in the system will ever report:
    # a declined row looks exactly like a row that predates this migration.
    log.info(
        "0051: froze the engagement target on %s row(s) from the finalize audit"
        " and %s from updated_at; declined %s audit row(s) whose recorded source"
        " was neither a usable client choice nor an absent one; %s row(s) remain"
        " unfrozen and will compute live and say so",
        stamped_from_audit,
        from_updated_at or 0,
        declined,
        remaining,
    )


def downgrade() -> None:
    with op.batch_alter_table("deliverables") as batch:
        batch.drop_column("frozen_target_source")
        batch.drop_column("frozen_target")
