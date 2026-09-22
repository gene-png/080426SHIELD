"""`legal_name` is NULL until a human names the organisation (#254, D-080)

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-22 00:00:00

`"(pending intake)"` was this codebase's marker for "this client has not named
itself yet". It was READ in 13 live conditionals across six route modules and
the Tech Debt extractor, and WRITTEN in ZERO production paths -- the only
assignments anywhere were four unit-test fixtures. Every one of those guards
was therefore dead, and what actually reached the organisation line of a client
deliverable was whatever `routes/auth.py` had derived from the registrant's
email address:

    routes/auth.py  unknown company domain  -> legal_name = "acme.example"
    routes/auth.py  generic provider        -> legal_name = A PERSON'S NAME

## Why NULL rather than writing the sentinel

Writing `"(pending intake)"` at provisioning would have made the 13 guards
start working, and it was the smaller change. It was refused because the
sentinel is a SECOND REPRESENTATION of a fact this table can state directly:
"nobody has named this organisation". Two representations can disagree, and
this pair already did -- for as long as the sentinel went unwritten, the column
said "named: acme.example" while the product's own guards said "unnamed", and
nothing could see the contradiction.

NULL cannot disagree with itself. `legal_name IS NULL` is the condition, so the
guards collapse from a string comparison to a plain read of the column.

## Why NOT `intake_completed_at IS NULL`

That was the other obvious reading of "test the real condition", and it is
wrong. `routes/admin.py` creates tenants with a name an admin typed, and those
tenants never complete intake. Keying the guards on intake would blank a real
client's deliverables and refuse its engagements -- a regression strictly worse
than the defect being fixed. The property is "has anyone named this org", which
is exactly what the name column records once it is allowed to be absent.

## Blast radius, measured before choosing

The column is widened, never narrowed, so no existing row can fail to load and
no read path gains a value it could not already receive (`legal_name` was
always a `str`; it can now also be `None`, which every consumer was already
written to handle because the sentinel produced the same `None` downstream).

The backfill below is the part with a blast radius, and it is deliberately
narrow. It NULLs only rows that satisfy all of:

  * `intake_completed_at IS NULL` -- nobody has submitted an intake for it, so
    no human has confirmed the name through the wizard; AND
  * the stored name is EXACTLY what one of the two self-serve paths would have
    written -- either a domain mapped to this same client, or the display name
    of this client's own primary contact.

Those two predicates reconstruct what `_provision_self_serve_client` wrote,
rather than guessing at it. A row an admin named is untouched unless the admin
typed a name identical to the tenant's own mapped domain or to its primary
contact's display name.

MEASURED against the dev Postgres, 2026-09-22, before this revision was applied
(`docker compose exec -T db psql -U shield -d shield`, the two predicates below
run verbatim as `SELECT count(*)`):

    total client rows                        -> 4
    matching the domain predicate            -> 1
    matching the display-name predicate      -> 0
    rows already holding "(pending intake)"  -> 0

The one match is a live instance of the defect rather than a hypothetical:

    legal_name                | intake? | mapped domain             | primary contact
    newco-1789834953739.com   | none    | newco-1789834953739.com   | Self Serve

The other three are untouched, each for a different reason, which is what makes
the predicate discriminating rather than merely narrow: `Atlas Defense
Solutions` has a mapped domain (`atlas.example`) that is NOT its name; an
engagement-demo tenant has a completed intake; and a rehearsal tenant has
neither a domain nor a primary contact.

Four rows is a statement about dev and about nothing else, which is why the
migration logs its own row counts rather than asserting an expected number:
whoever runs this against a populated database reads the real figure out of the
upgrade log instead of a number this file guessed. The first draft of this
paragraph DID guess -- it claimed 8 rows and 0 matches, and both were wrong.

## The round trip was RUN, not reasoned about

`upgrade -> downgrade -> upgrade` against the dev Postgres, 2026-09-22, reading
the stored column back at each step:

    upgrade      newco-1789834953739.com  ->  NULL   (domain predicate, 1 row)
    downgrade    NULL                     ->  "(pending intake)"       (1 row)
    upgrade      "(pending intake)"       ->  NULL   (sentinel predicate, 1 row)

The third `_BACKFILL` entry exists BECAUSE of that middle step. After a
downgrade the stored name is no longer the domain or the display name, so
neither of the first two predicates can see it, and without the sentinel
statement a re-upgrade would strand the row holding a marker no code reads any
more. The log naming a DIFFERENT predicate on each upgrade is what shows the
three are not redundant.

ERROR DIRECTION, stated so it is examined rather than assumed: a false positive
(an admin-named row wrongly NULLed) shows up immediately as "(pending intake)"
on an admin screen and is cleared by retyping the name. A false negative (a
self-serve row left named) leaves the pre-existing defect in place for that one
tenant and is not made worse by this migration. Only the second is silent, and
it is the status quo rather than something introduced here.

## Downgrade

Re-narrowing the column needs every NULL to become a string again, and there is
no string to put back -- the whole point is that none was ever offered. The
downgrade therefore fills NULLs with the literal `(pending intake)`, which is
the marker the pre-0049 code already knew how to read, so a rollback lands on
code whose guards behave exactly as they were written to.
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# The two self-serve derivations, reconstructed. Each names the path in
# `routes/auth.py` it undoes, because a bare predicate here reads as a guess.
_BACKFILL = (
    (
        "unknown-company-domain path (_provision_self_serve_client(legal_name=domain))",
        """
        UPDATE client SET legal_name = NULL
         WHERE intake_completed_at IS NULL
           AND legal_name IS NOT NULL
           AND legal_name IN (
                 SELECT cd.domain FROM client_domain cd WHERE cd.client_id = client.id
               )
        """,
    ),
    (
        "generic-provider path (_provision_self_serve_client(legal_name=display_name))",
        """
        UPDATE client SET legal_name = NULL
         WHERE intake_completed_at IS NULL
           AND legal_name IS NOT NULL
           AND primary_poc_user_id IS NOT NULL
           AND legal_name = (
                 SELECT u.display_name FROM users u WHERE u.id = client.primary_poc_user_id
               )
        """,
    ),
    (
        # The sentinel itself, translated rather than left sitting in the column.
        #
        # No production path ever wrote it, so on a database that only ever ran
        # this application it matches nothing -- and it is here anyway for the
        # case that DOES produce it: `downgrade()` writes this exact string, so
        # without this statement an upgrade -> downgrade -> upgrade round trip
        # would strand the row holding a sentinel that no code reads any more.
        # Neither of the predicates above can catch it, because after the
        # downgrade the stored name is no longer the domain or the display name.
        #
        # Unconditional on `intake_completed_at` on purpose: "(pending intake)"
        # is not a name a client would submit, so a row holding it has not been
        # named whatever its intake timestamp says.
        "the sentinel itself (pre-0049 fixtures, and any downgrade/upgrade round trip)",
        """
        UPDATE client SET legal_name = NULL
         WHERE legal_name = '(pending intake)'
        """,
    ),
)


def upgrade() -> None:
    with op.batch_alter_table("client") as batch_op:
        batch_op.alter_column(
            "legal_name",
            existing_type=sa.String(255),
            nullable=True,
            comment=(
                "The organisation's legal name. NULL means nobody has named it "
                "yet -- self-serve provisioning writes no name (D-080, #254)."
            ),
        )

    conn = op.get_bind()
    for label, stmt in _BACKFILL:
        # The count is logged AFTER the statement that makes it true, from the
        # driver's own rowcount, rather than from a SELECT run beforehand that
        # a concurrent write could invalidate.
        result = conn.execute(sa.text(stmt))
        log.info("0049 backfill: %s NULLed %s row(s)", label, result.rowcount)


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("UPDATE client SET legal_name = '(pending intake)' WHERE legal_name IS NULL")
    )
    log.info("0049 downgrade: restored the sentinel on %s row(s)", result.rowcount)

    with op.batch_alter_table("client") as batch_op:
        batch_op.alter_column(
            "legal_name",
            existing_type=sa.String(255),
            nullable=False,
            comment=None,
        )
