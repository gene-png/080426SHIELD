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

Predicate 2 also picks the intake column by `services.kind`. `submit_intake`
writes both columns for every item whatever its type, so choosing by COALESCE
freezes a CSF tier onto a ZT deliverable -- measured, and the reason
`_TARGET_COLUMN_BY_KIND` exists. Kinds with no engagement target of this shape
are excluded outright.

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

`seed_demo.py` stamps the pair for CSF and ZT in the same commit as this
migration, so CI and a fresh dev database exercise the FROZEN read path rather
than only the backfill.

**NOT "zero rows in the NULL branch", which is what this said and is false.**
`seed_demo.py` deliberately leaves `frozen_target_source` NULL on ATT&CK and
Tech Debt deliverables, because those kinds have no engagement target of this
shape. So a seeded database DOES carry NULL-source rows, and someone querying
dev Postgres would have read them as a seed failure. The argument the sentence
was making survives; the absolute claim does not. That is the
argument for landing the migration and the seed change together rather than in
sequence: split them and every CI run exercises only the backfill path, which is
the path that will almost never run in production.

## A RESIDUAL NOTHING ASSERTS: `finalized_at` IS NULLABLE

`_frozen_or_live_target` branches on `frozen_target_source is not None` and
then returns `deliv.finalized_at` as the disclosure stamp. Those are two
different columns, and the second is nullable -- so a row with a non-null
source and a NULL `finalized_at` would return FROZEN figures under a NULL
stamp, and the screen would print "These figures use your target as it stands
today ... the two can differ" over figures that cannot.

Unreachable from today's writers: both finalize routes write `finalized_at` and
the pair together, and arm 2 below requires `finalized_at IS NOT NULL`. **Arm 1
does not**, so a deliverable with a finalize audit row and a NULL
`finalized_at` would produce it -- a state no route mints, and nothing asserts
the invariant. Written down rather than guarded, because the guard belongs with
the disclosure rather than in a migration, and because an unstated window is
the one nobody tests.

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
2 row(s) remain unfrozen`.

**Arm 1 was measured on Postgres separately, and it had to be.** That first run
carried no audit rows, so it certified the `UPDATE ... FROM` branch and NOT arm 1
-- and review raised a specific suspicion about arm 1 there: it keys `from_audit`
on `str(target_id)` and binds that text against `deliverables.id`, which is a
native `uuid` on Postgres and a `String(36)` on SQLite, so the tests could pass
while production matched zero rows or raised. Measured 2026-09-23 with a real
`zt.deliverable.finalized` audit row present: `1 row(s) from the finalize audit`,
`frozen_target=2 source=audit`, exit 0. The suspicion does not hold, and it is
recorded here because the earlier certificate genuinely did not cover it. That is the same behaviour
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

#: WHICH intake column holds the engagement target, per `services.kind`.
#:
#: **COALESCE IS WRONG HERE AND THAT WAS A MEASURED DEFECT, not a tidiness
#: point.** Arm 2 below read
#: `COALESCE(sr.csf_target_tier, sr.zt_target_stage)` under a comment claiming
#: "COALESCE picks whichever the service kind populated". That assumes exactly
#: one is set, and `routes/intake.py` does the opposite: `_validate_targets`'
#: own docstring records that `submit_intake` WRITES BOTH COLUMNS for every item
#: regardless of `service_type`, checking presence per type but range for every
#: value. So `{"service_type": "zero_trust_cisa", "zt_target_stage": 2,
#: "csf_target_tier": 4}` is accepted and stores both.
#:
#: Measured 2026-09-23 on postgres:16-alpine, exactly that intake row, a ZT
#: deliverable with no finalize audit row:
#:
#:     ZT v2 -> frozen_target=4  source=updated_at
#:
#: The client contracted stage 2. The dashboard would resolve stage 4 -- MORE
#: gaps than the released PDF lists -- under a non-null `target_frozen_at` whose
#: whole meaning is "these figures agree with your report". That is #209's harm
#: produced by #209's fix, in the arm no test covered.
#:
#: `seed_demo.py` already splits on `service.kind` for the same reason. The
#: migration did not, and the two now agree.
#:
#: DERIVED INTO BOTH DIALECT BRANCHES from this one dict rather than hand-written
#: twice, so a fourth kind cannot be added to one branch and missed in the other.
#: KEYED ON THE STORED SPELLING, WHICH IS THE ENUM *NAME*, and that had to be
#: measured rather than assumed. `Service.kind` is
#: `SAEnum(ServiceKind, native_enum=False, length=32)`, and SQLAlchemy's `Enum`
#: persists a Python enum by its NAME, not its value. Measured 2026-09-23 by
#: writing one row through the ORM and reading the column back:
#:
#:     STORED kind = 'ZERO_TRUST_CISA'
#:     enum .value = 'zero_trust_cisa'   .name = 'ZERO_TRUST_CISA'
#:
#: The first version of this mapping used the VALUES. It matched nothing, and the
#: hand-seeded Postgres row that appeared to confirm the fix had been inserted
#: with the value spelling -- a fixture in a state no writer can produce,
#: validating a filter against the one input it agreed with. Three SQLite tests
#: caught it immediately; the Postgres run did not, because I wrote its rows.
#:
#: BOTH SPELLINGS are listed. A false match is impossible -- name and value map to
#: the same column for every kind -- and it removes a dependency on SQLAlchemy
#: continuing to choose names, which a `values_callable` anywhere would change.
_TARGET_COLUMN_BY_KIND = {
    "NIST_CSF": "csf_target_tier",
    "nist_csf": "csf_target_tier",
    "ZERO_TRUST_CISA": "zt_target_stage",
    "zero_trust_cisa": "zt_target_stage",
    "ZERO_TRUST_DOD": "zt_target_stage",
    "zero_trust_dod": "zt_target_stage",
}


def _target_case(alias: str) -> str:
    """A SQL `CASE` picking the right intake column for the service's kind.

    Kinds absent from the mapping -- `tech_debt`, `attack_coverage` -- fall
    through to NULL, which the callers require to be non-NULL. They have no
    engagement target of this shape, so no freeze is the correct answer and the
    model comment says so.
    """
    whens = " ".join(f"WHEN '{kind}' THEN sr.{col}" for kind, col in _TARGET_COLUMN_BY_KIND.items())
    return f"CASE {alias}.kind {whens} END"


#: The kinds arm 2 will consider at all, as a SQL list literal.
_KIND_IN = ", ".join(f"'{k}'" for k in _TARGET_COLUMN_BY_KIND)


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
    # THE COLUMN IS PICKED BY `services.kind`, NOT BY COALESCE, and the
    # COALESCE version was a measured defect -- see `_TARGET_COLUMN_BY_KIND`.
    # `submit_intake` writes BOTH intake columns for every item regardless of
    # type, so a ZT service can carry a stray `csf_target_tier` and COALESCE
    # froze that tier onto a ZT deliverable.
    from_updated_at = conn.execute(
        sa.text(
            "UPDATE deliverables SET frozen_target = sub.target,"
            "   frozen_target_source = 'updated_at'"
            " FROM ("
            "   SELECT d.id AS did,"
            f"          {_target_case('s')} AS target"
            "     FROM deliverables d"
            "     JOIN services s ON s.id = d.service_id"
            "     JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE d.frozen_target_source IS NULL"
            "      AND d.finalized_at IS NOT NULL"
            "      AND sr.updated_at <= d.finalized_at"
            f"      AND s.kind IN ({_KIND_IN})"
            f"      AND {_target_case('s')} IS NOT NULL"
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
            f"   SELECT {_target_case('s')}"
            "     FROM services s JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE s.id = deliverables.service_id"
            f"      AND s.kind IN ({_KIND_IN})"
            "      AND sr.updated_at <= deliverables.finalized_at"
            " ), frozen_target_source = 'updated_at'"
            " WHERE frozen_target_source IS NULL AND finalized_at IS NOT NULL AND ("
            f"   SELECT {_target_case('s')}"
            "     FROM services s JOIN service_requests sr ON sr.id = s.source_request_id"
            "    WHERE s.id = deliverables.service_id"
            f"      AND s.kind IN ({_KIND_IN})"
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
