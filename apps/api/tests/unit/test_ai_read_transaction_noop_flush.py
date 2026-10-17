"""#1362: a flush that changes nothing is not a write. Setting an attribute
to the value it already holds puts the object in `Session.dirty`, so a flush
runs; before #1362 that flush marked the transaction as written, and
`end_read_transaction` refused a caller that had only read. A real change,
flushed, is still refused (`test_ai_read_transaction_ended.py`)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.ai.session_marks import end_read_transaction
from tests.unit.test_ai_calls_hold_no_connection import _invoke_world
from tests.unit.test_attack_run_ai import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_a_flush_with_no_net_change_does_not_count_as_a_write(app_client) -> None:  # noqa: F811
    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        client.legal_name = client.legal_name
        assert client in db.dirty, "setup: the object is dirty"
        db.flush()
        assert db.in_transaction(), "setup: the read is still open"
        end_read_transaction(db, where="test")
        assert not db.in_transaction()


def test_a_real_change_beside_it_is_still_refused(app_client) -> None:  # noqa: F811
    """The positive control, in the same shape: a different value, flushed."""
    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with TestSession() as db:
        client = db.execute(select(Client).where(Client.id == cid)).scalar_one()
        client.legal_name = client.legal_name + " (changed)"
        db.flush()
        with pytest.raises(RuntimeError, match=r"^test: the session has written"):
            end_read_transaction(db, where="test")
        db.rollback()


@pytest.mark.parametrize("what", ["insert", "delete"])
def test_a_flushed_insert_or_delete_is_still_refused(app_client, what: str) -> None:  # noqa: F811
    """The other two branches of the flush mark (review of a6720311): after the
    flush nothing is pending, so only the mark can refuse."""
    TestSession, _provider, _llm, _uid, cid, Client = _invoke_world(app_client)
    with TestSession() as setup:
        doomed = Client(legal_name="To be deleted")
        setup.add(doomed)
        setup.commit()
        doomed_id = doomed.id
    with TestSession() as db:
        db.execute(select(Client).where(Client.id == cid)).scalar_one()
        if what == "insert":
            db.add(Client(legal_name="Added mid-read"))
        else:
            db.delete(db.get(Client, doomed_id))
        db.flush()
        assert (len(db.new), len(db.deleted)) == (0, 0), "setup: nothing is pending"
        with pytest.raises(RuntimeError, match=r"^test: the session has written"):
            end_read_transaction(db, where="test")
        db.rollback()
