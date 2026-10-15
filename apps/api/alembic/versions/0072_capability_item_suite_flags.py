"""Suite, recognition and purchase-status columns on `capability_items` (TD-2 part A, for #1058).

Revision ID: 0072
Revises: 0073

The number 0072 is the advisor's (#736), assigned when the landing order was
0071 then 0072. It is NUMBERED OUT OF ORDER: 0073 (#1120, one draft per
service) landed first, so 0072 chains AFTER 0073 and `down_revision` is
main's head at the time of writing. The chain's order is not the number order
(`test_alembic_single_head` reads the chain, never filenames).

Eight nullable columns, the design of TD-2 (td2, as ruled by the advisor):

- `is_suite`, `recognized`: the two booleans Tech Debt extraction prompt v3.3
  section 9a asks for. NULL means "not answered": a row extracted before TD-2,
  or an answer whose flag was missing or not a boolean (recorded in
  `extraction_findings`). NULL is NEVER read as False.
- `extracted_prompt_version` (F1, option (a), #736 6160171214): on a row the
  extraction inserted, the prompt version that ran -- the value the call
  records in `llm_calls.prompt_version`, passed through. It is what tells a
  NULL flag from a v3.3 run ("asked, unanswered") from a NULL flag on a row
  extracted before TD-2 ("not asked"). NULL on every row a consultant adds
  (an included excluded row, a component) and on every existing row.
- `purchase_status`: on a COMPONENT row only (a CHECK holds it to rows with a
  `parent_item_id`), one of the four approved statuses -- Purchased and in use,
  Purchased, not deployed, Not purchased, Unknown -- stored as the member NAME
  (`PURCHASED_IN_USE`, `PURCHASED_NOT_DEPLOYED`, `NOT_PURCHASED`, `UNKNOWN`),
  the `native_enum=False` convention. A second CHECK holds the vocabulary.
- `client_unconfirmed_name` (the client contact, ruling Q1),
  `client_unconfirmed_reason`, `client_unconfirmed_at`, `client_unconfirmed_by`
  (the consultant who recorded it; FK to `users`, `ON DELETE SET NULL`): the
  "Client could not confirm" record on a suite row.

## Blast radius

Additive and nullable; nothing is backfilled. Every existing row keeps NULL in
all eight columns, which part B reads as "extracted before this check existed"
(ruling Q3: never red, never counted as cleared). Nothing reads the columns in
this part except the extraction write of the two flags and the prompt version.

## The downgrade refuses while any row holds a value 0072 added

Including a recorded `False`: "not a suite" is a model's answer, and a
re-upgrade restores NULL, not the answer. Dropping a purchase status or a
"Client could not confirm" record would delete a consultant's work without a
trace. On a database with real Tech Debt work the downgrade is, in practice,
one-way until someone clears the rows.

## Clearing before a downgrade

Only once someone has decided the data may go (export it first if it must be
kept). This statement clears everything the refusal counts, and is the one the
refusal prints:

    UPDATE capability_items SET is_suite = NULL, recognized = NULL, extracted_prompt_version = NULL, purchase_status = NULL, client_unconfirmed_name = NULL, client_unconfirmed_reason = NULL, client_unconfirmed_at = NULL, client_unconfirmed_by = NULL

then `alembic downgrade 0073`.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import conv

revision: str = "0072"
down_revision: str | Sequence[str] | None = "0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The approved purchase statuses, as the column stores them (member NAMEs).
_STATUSES = ("PURCHASED_IN_USE", "PURCHASED_NOT_DEPLOYED", "NOT_PURCHASED", "UNKNOWN")
_VOCABULARY = "purchase_status IS NULL OR purchase_status IN ({})".format(
    ", ".join(f"'{s}'" for s in _STATUSES)
)
_ON_COMPONENT = "purchase_status IS NULL OR parent_item_id IS NOT NULL"
_CK_VOCABULARY = "ck_capability_items_purchase_status_vocabulary"
_CK_ON_COMPONENT = "ck_capability_items_purchase_status_on_component"
_FK_BY = "fk_capability_items_client_unconfirmed_by_users"

#: Every column this migration adds, in the order the clearing statement names.
_COLUMNS = (
    "is_suite",
    "recognized",
    "extracted_prompt_version",
    "purchase_status",
    "client_unconfirmed_name",
    "client_unconfirmed_reason",
    "client_unconfirmed_at",
    "client_unconfirmed_by",
)
_HELD = "SELECT COUNT(*) FROM capability_items WHERE " + " OR ".join(  # nosec B608
    f"{c} IS NOT NULL" for c in _COLUMNS
)
_CLEAR = "UPDATE capability_items SET " + ", ".join(f"{c} = NULL" for c in _COLUMNS)  # nosec B608


def upgrade() -> None:
    with op.batch_alter_table("capability_items") as batch:
        batch.add_column(sa.Column("is_suite", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("recognized", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("extracted_prompt_version", sa.String(32), nullable=True))
        batch.add_column(sa.Column("purchase_status", sa.String(32), nullable=True))
        batch.add_column(sa.Column("client_unconfirmed_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("client_unconfirmed_reason", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("client_unconfirmed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "client_unconfirmed_by",
                postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite"),
                nullable=True,
            )
        )
        batch.create_foreign_key(
            conv(_FK_BY), "users", ["client_unconfirmed_by"], ["id"], ondelete="SET NULL"
        )
        batch.create_check_constraint(conv(_CK_VOCABULARY), _VOCABULARY)
        batch.create_check_constraint(conv(_CK_ON_COMPONENT), _ON_COMPONENT)
    print("[0072] added to capability_items, all NULL on existing rows: " + ", ".join(_COLUMNS))


def downgrade() -> None:
    held = op.get_bind().execute(sa.text(_HELD)).scalar_one()
    if held:
        noun = "capability item holds" if held == 1 else "capability items hold"
        raise RuntimeError(
            f"Refusing to downgrade 0072: {held} {noun} a value 0072 added "
            "(a suite or recognition flag, the prompt version that asked for them, a "
            "purchase status, or a 'Client could not "
            "confirm' record). Dropping them would delete a model's answers and a "
            "consultant's work without a trace, and a re-upgrade restores NULL, not "
            "the values. To clear them deliberately, once the data may go, run: "
            f"{_CLEAR}."
        )
    with op.batch_alter_table("capability_items") as batch:
        batch.drop_constraint(conv(_CK_ON_COMPONENT), type_="check")
        batch.drop_constraint(conv(_CK_VOCABULARY), type_="check")
        batch.drop_constraint(conv(_FK_BY), type_="foreignkey")
        for column in reversed(_COLUMNS):
            batch.drop_column(column)
