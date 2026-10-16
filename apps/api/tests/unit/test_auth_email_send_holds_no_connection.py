"""#1366 item 1: the auth routes that email a link -- register, resend
verification, forgot password -- send with no transaction open, so no pooled
connection is held across the SMTP call (`smtplib.SMTP(..., timeout=10)`).
They used to read `user.email` after the commit, which reloads the row and
holds a connection until the request ends.

The sender is stubbed, and each send is checked for WHAT goes out as well as
how: the recipient is the address the test registered, and the token is the
one the route issued, proven by redeeming it at the route that consumes it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import event
from sqlalchemy.pool import Pool

from tests.unit.test_email_verification import (  # noqa: F401  (fixtures)
    _NEW_PASSWORD,
    _register,
    app_client,
    db_url,
    sessionmaker_for,
)

pytestmark = pytest.mark.unit

EMAIL = "first@example.com"


@contextmanager
def pool_count() -> Iterator[list[int]]:
    """Connections checked out of any pool since entry and not yet returned,
    live, as `[n]`. The same counter #1365 adds as `tests/_pool_count.py`,
    kept here so this fix does not wait on that PR. Tracked per connection,
    so a connection checked out BEFORE entry and returned during the block is
    not counted at all: a plain counter went negative in a full run (CI on
    #1365, `[-2, -2, ...]`)."""
    held = [0]
    out: set[int] = set()
    lock = threading.Lock()

    def _out(_dbapi_conn, record, _proxy) -> None:
        with lock:
            out.add(id(record))
            held[0] = len(out)

    def _in(_dbapi_conn, record) -> None:
        with lock:
            out.discard(id(record))
            held[0] = len(out)

    event.listen(Pool, "checkout", _out)
    event.listen(Pool, "checkin", _in)
    try:
        yield held
    finally:
        event.remove(Pool, "checkout", _out)
        event.remove(Pool, "checkin", _in)


@pytest.fixture
def sends(monkeypatch) -> Iterator[list[dict]]:
    """Every send, with the pool count at the moment it is made."""
    box: list[dict] = []
    with pool_count() as held:

        def _verify(*, to: str, token: str) -> None:
            box.append({"kind": "verify", "to": to, "token": token, "held": held[0]})

        def _reset(*, to: str, token: str) -> None:
            box.append({"kind": "reset", "to": to, "token": token, "held": held[0]})

        monkeypatch.setattr("app.routes.auth.send_verification_email", _verify)
        monkeypatch.setattr("app.routes.auth.send_password_reset_email", _reset)
        yield box


def test_register_sends_with_no_connection_held(app_client, sends) -> None:  # noqa: F811
    _register(app_client, EMAIL)
    (sent,) = sends
    assert (sent["kind"], sent["to"], sent["held"]) == ("verify", EMAIL, 0), sent
    r = app_client.post("/auth/verify-email", json={"token": sent["token"]})
    assert r.status_code == 200, r.text


def test_resend_verification_sends_with_no_connection_held(app_client, sends) -> None:  # noqa: F811
    _register(app_client, EMAIL)
    r = app_client.post("/auth/resend-verification", json={"email": EMAIL})
    assert r.status_code == 200, r.text
    first, again = sends
    assert (again["kind"], again["to"], again["held"]) == ("verify", EMAIL, 0), again
    assert again["token"] != first["token"], "setup: a fresh token was issued"
    r = app_client.post("/auth/verify-email", json={"token": again["token"]})
    assert r.status_code == 200, r.text


def test_forgot_password_sends_with_no_connection_held(app_client, sends) -> None:  # noqa: F811
    _register(app_client, EMAIL)
    r = app_client.post("/auth/forgot-password", json={"email": EMAIL})
    assert r.status_code == 200, r.text
    reset = sends[-1]
    assert (reset["kind"], reset["to"], reset["held"]) == ("reset", EMAIL, 0), reset
    r = app_client.post(
        "/auth/reset-password", json={"token": reset["token"], "password": _NEW_PASSWORD}
    )
    assert r.status_code == 200, r.text
