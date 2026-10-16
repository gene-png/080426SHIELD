"""What a session's open transaction has done, for the AI call sites (#1025,
holder 2; advisor, #736 6216024281, 3e).

A caller that reaches a provider holding an open transaction keeps a pooled
connection checked out for the whole call; measured on #1025, eight concurrent
runs exhausted the production pool for every tenant. The ruling: never commit
a caller's transaction inside `invoke`; each run-work function and request
route ends its READ transaction explicitly before its AI call
(`end_read_transaction`), and a provider call inside a transaction that took a
`FOR UPDATE` lock is refused loudly (`holds_for_update`, read by `invoke`).

Both need to know what the transaction did, which SQLAlchemy does not record,
so the listeners below mark it in `session.info` and clear the marks when the
outermost transaction ends (commit, rollback or close):

* `_WROTE`: a flush with a net change to write (#1362), or an ORM-enabled
  INSERT / UPDATE / DELETE statement;
* `_FOR_UPDATE`: an ORM SELECT carrying `with_for_update()`.

RESIDUAL: the flush mark is taken in `before_flush`, so an object that a
`before_flush` listener registered AFTER this one adds or changes is not seen
(#1362 review); today the only other one, `_block_audit_mutations`, only
raises. And a raw `text("... FOR UPDATE")` or a Core statement run on the
connection is not seen. No AI caller does either today (the #1025 lock sweep,
#736 6210729795); the marks are a floor, not a census.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from app.logging import get_logger

_log = get_logger(__name__)

_WROTE = "shield_ai_txn_wrote"
_FOR_UPDATE = "shield_ai_txn_for_update"


@event.listens_for(Session, "before_flush")
def _mark_flush(session: Session, _flush_context, _instances) -> None:
    # #1362: only a flush with something to write. An attribute set to the
    # value it already holds leaves its object in `dirty` and runs a flush
    # that emits nothing; `is_modified` compares against the loaded value.
    if session.new or session.deleted or any(session.is_modified(o) for o in session.dirty):
        session.info[_WROTE] = True


@event.listens_for(Session, "do_orm_execute")
def _mark_statement(state) -> None:
    if state.is_insert or state.is_update or state.is_delete:
        state.session.info[_WROTE] = True
    elif state.is_select and getattr(state.statement, "_for_update_arg", None) is not None:
        state.session.info[_FOR_UPDATE] = True


@event.listens_for(Session, "after_transaction_end")
def _clear(session: Session, transaction: SessionTransaction) -> None:
    if transaction.parent is None:
        session.info.pop(_WROTE, None)
        session.info.pop(_FOR_UPDATE, None)


def holds_for_update(db: Session) -> bool:
    """Whether `db`'s open transaction took a `FOR UPDATE` lock."""
    return db.in_transaction() and bool(db.info.get(_FOR_UPDATE))


def end_read_transaction(db: Session, *, where: str) -> None:
    """End `db`'s READ transaction before an AI call, so the caller holds no
    pooled connection while the provider answers.

    Refuses, loudly and naming `where`, a transaction that has written --
    pending objects, a flush with a net change, or a DML statement -- because committing it here
    would make a run's partial writes durable before the run knows it
    succeeded, and rolling it back would lose them. A caller that must write
    first has to be reshaped, not passed through.

    Loaded objects stay loaded (`expire_on_commit` is suspended for this one
    commit), so reading their attributes for the call does not open a new
    transaction behind it."""
    pending = (
        len(db.new),
        sum(1 for o in db.dirty if db.is_modified(o)),
        len(db.deleted),
    )
    if any(pending) or db.info.get(_WROTE):
        raise RuntimeError(
            f"{where}: the session has written in this transaction "
            f"(new, dirty, deleted = {pending}; flushed = {bool(db.info.get(_WROTE))}), "
            "so its read transaction cannot be ended before the AI call (#1025)"
        )
    if not db.in_transaction():
        _log.info("ai.read_transaction_already_ended", where=where)
        return
    keep = db.expire_on_commit
    db.expire_on_commit = False
    try:
        db.commit()
    finally:
        db.expire_on_commit = keep
    _log.info("ai.read_transaction_ended", where=where)
