"""Auth compensating-controls tests (Sprint 3 T2).

Covers the honest versions of the controls README/BUILD_REPORT claimed:
  (a) the forced re-auth ceiling (12 h by default, D-085) honored at /auth/refresh (typed 401
      reason=reauth_required past shield_forced_reauth_seconds);
  (b) refresh-token rotation — a reused (already-rotated) refresh token is
      rejected;
  (c) dead feature flags fail loudly at startup rather than silently doing
      nothing (the MFA / email-verify flows don't exist yet).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-reauth.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c


def _register(client: TestClient, email: str = "first@example.com") -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": "Test User",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# -----------------------------------------------------------------------------
# (a) Forced re-auth ceiling
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_refresh_past_forced_reauth_returns_typed_401(app_client: TestClient) -> None:
    from app.config import get_settings
    from app.security.jwt import issue_token

    body = _register(app_client)
    user_id = body["user"]["id"]
    settings = get_settings()

    # Mint a refresh token whose original auth time is older than the forced
    # re-auth ceiling. The ceiling is checked before rotation, so the jti need
    # not match the stored one.
    stale_auth_time = datetime.now(UTC) - timedelta(
        seconds=settings.shield_forced_reauth_seconds + 3600
    )
    import uuid as _uuid

    stale_token, _ = issue_token(
        subject=_uuid.UUID(user_id),
        role="admin",
        typ="refresh",
        auth_time=stale_auth_time,
    )

    r = app_client.post("/auth/refresh", json={"refresh_token": stale_token})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == "reauth_required"


@pytest.mark.unit
def test_refresh_within_window_carries_auth_time_forward(app_client: TestClient) -> None:
    from app.security.jwt import verify_token

    body = _register(app_client)
    original = verify_token(body["tokens"]["refresh_token"], expected_type="refresh")

    r = app_client.post("/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert r.status_code == 200, r.text
    rotated = verify_token(r.json()["refresh_token"], expected_type="refresh")

    # The original auth-time claim rides forward unchanged so the forced-reauth
    # ceiling is anchored to the original login, not reset on every refresh.
    assert rotated.auth_time is not None
    assert original.auth_time is not None
    assert rotated.auth_time == original.auth_time


@pytest.mark.unit
def test_every_pair_states_its_reauth_deadline_and_a_refresh_does_not_move_it(
    app_client: TestClient,
) -> None:
    """#498. The web counts down to the session's END, which is the EARLIER of
    the refresh token's expiry and the forced re-auth ceiling. The refresh
    expiry rolls forward on every rotation; the ceiling does not. Without the
    deadline on the wire the web could only see the rolling one, and a user
    active all day would be signed out at the ceiling with no warning.

    Expected value derived from the rule (login time + ceiling), not read off
    the response: the login's `auth_time` claim is the anchor the refresh
    endpoint itself enforces."""
    from app.config import get_settings
    from app.security.jwt import verify_token

    ceiling = timedelta(seconds=get_settings().shield_forced_reauth_seconds)
    body = _register(app_client)
    login = verify_token(body["tokens"]["refresh_token"], expected_type="refresh")
    assert login.auth_time is not None
    expected = login.auth_time + ceiling

    stated = datetime.fromisoformat(body["tokens"]["reauth_at"])
    assert abs((stated - expected).total_seconds()) < 1, (stated, expected)

    # The refresh half needs a login that is NOT "just now": refreshed
    # milliseconds after registering, a ceiling re-anchored on the refresh
    # time lands within a second of the right one and passes (round 9 on
    # #499). So refresh a token -- the ACTIVE jti, so rotation accepts it --
    # whose login was an hour ago; a refresh-anchored ceiling is then off by
    # an hour.
    import uuid as _uuid

    from app.security.jwt import issue_token

    an_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    older, _ = issue_token(
        subject=_uuid.UUID(body["user"]["id"]),
        role=body["user"]["role"],
        typ="refresh",
        auth_time=an_hour_ago,
        jti=login.jti,
    )
    r = app_client.post("/auth/refresh", json={"refresh_token": older})
    assert r.status_code == 200, r.text
    after_refresh = datetime.fromisoformat(r.json()["reauth_at"])
    anchored = an_hour_ago + ceiling
    assert abs((after_refresh - anchored).total_seconds()) < 1, (
        "a refresh moved the ceiling off the login time",
        after_refresh,
        anchored,
    )


@pytest.mark.unit
def test_login_states_the_reauth_deadline_too(app_client: TestClient) -> None:
    _register(app_client, email="login@example.com")
    r = app_client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["reauth_at"] is not None


# -----------------------------------------------------------------------------
# (b) Refresh-token rotation
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_reused_old_refresh_token_rejected(app_client: TestClient, monkeypatch) -> None:
    """Strict single-use, with the rotation grace disabled.

    NOTE: this test's contract CHANGED on 2026-08-08. It used to assert that a
    replayed token is rejected immediately. It now pins that behaviour with
    `jwt_refresh_grace_seconds = 0`, because with the grace enabled (the
    default) an immediate replay is deliberately ACCEPTED — see
    `test_concurrent_refresh_with_the_same_token_does_not_log_the_user_out`.
    The change is intentional and narrow, not a weakening to reach green: a
    token two generations old, or replayed after the window, is still rejected,
    and this test proves the strict path still exists and still works.
    """
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JWT_REFRESH_GRACE_SECONDS", "0")
    get_settings.cache_clear()

    body = _register(app_client)
    original_refresh = body["tokens"]["refresh_token"]

    first = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert first.status_code == 200, first.text
    new_refresh = first.json()["refresh_token"]

    # Reusing the now-rotated-out original refresh token is rejected loudly.
    reused = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert reused.status_code == 401, reused.text
    assert reused.json()["error"]["reason"] == "refresh_reused"

    # The freshly rotated token still works.
    ok = app_client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert ok.status_code == 200, ok.text

    get_settings.cache_clear()


@pytest.mark.unit
def test_concurrent_refresh_with_the_same_token_does_not_log_the_user_out(
    app_client: TestClient,
) -> None:
    """The defect this grace window exists for.

    A browser fires several requests at once when the access token expires, and
    every one presents the SAME refresh token. Observed in the API log as pairs
    of `auth.refresh_reused` 286 MICROSECONDS apart, each ending in a hard
    sign-out mid-task. Both callers must come away with a working session.
    """
    body = _register(app_client)
    original_refresh = body["tokens"]["refresh_token"]

    winner = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert winner.status_code == 200, winner.text

    # The racer presents the same (now rotated-out) token a moment later.
    loser = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert loser.status_code == 200, loser.text

    # Both hold usable tokens, and they converge on ONE identity rather than
    # each rotating the other out — otherwise the race just moves.
    from app.security.jwt import verify_token

    winner_jti = verify_token(winner.json()["refresh_token"], expected_type="refresh").jti
    loser_jti = verify_token(loser.json()["refresh_token"], expected_type="refresh").jti
    assert winner_jti == loser_jti, "concurrent refreshers must not fight over rotation"

    # And the converged token still refreshes normally afterwards.
    again = app_client.post("/auth/refresh", json={"refresh_token": loser.json()["refresh_token"]})
    assert again.status_code == 200, again.text


@pytest.mark.unit
def test_grace_does_not_survive_the_window(app_client: TestClient) -> None:
    """Time-boxed, not permanent: a replay after the window is still replay."""
    from app.config import get_settings
    from app.models.user import User

    body = _register(app_client)
    original_refresh = body["tokens"]["refresh_token"]
    assert (
        app_client.post("/auth/refresh", json={"refresh_token": original_refresh}).status_code
        == 200
    )

    # Backdate the rotation past the grace window.
    settings = get_settings()
    from app.db.session import get_db
    from app.main import create_app  # noqa: F401 - app already built by the fixture

    db_gen = app_client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        user = db.query(User).filter(User.email == "first@example.com").one()
        user.refresh_rotated_at = datetime.now(UTC) - timedelta(
            seconds=settings.jwt_refresh_grace_seconds + 5
        )
        db.commit()
    finally:
        db.close()

    stale = app_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert stale.status_code == 401, stale.text
    assert stale.json()["error"]["reason"] == "refresh_reused"


@pytest.mark.unit
def test_a_token_two_generations_old_is_rejected_even_within_the_window(
    app_client: TestClient,
) -> None:
    """Only the IMMEDIATELY previous jti is honoured — the grace is not a history."""
    body = _register(app_client)
    gen1 = body["tokens"]["refresh_token"]

    r2 = app_client.post("/auth/refresh", json={"refresh_token": gen1})
    assert r2.status_code == 200
    gen2 = r2.json()["refresh_token"]
    r3 = app_client.post("/auth/refresh", json={"refresh_token": gen2})
    assert r3.status_code == 200

    # gen1 is now two rotations back, still well inside the time window.
    stale = app_client.post("/auth/refresh", json={"refresh_token": gen1})
    assert stale.status_code == 401, stale.text
    assert stale.json()["error"]["reason"] == "refresh_reused"


# -----------------------------------------------------------------------------
# (b2) A TRUE race: two refreshes that both read the same active jti (#505)
#
# The tests above run one request after another, so each sees the other's
# commit. A real race does not: both requests load the user BEFORE either
# rotates, both pass the "presented == active" check, and the second write
# overwrites the first -- the winner's new jti is then neither active nor
# previous, and its next refresh reads as `refresh_reused`. SQLite serialises
# writes, so this can only be forced deterministically: the route's first
# `utcnow()` after loading the user is the ceiling check, which runs before
# rotation, and a one-shot hook there commits the concurrent WINNER's rotation
# through a separate session. The hook records what it saw, so a test cannot
# pass because the interleaving silently did not happen.
# -----------------------------------------------------------------------------


def _race_the_rotation(app_client: TestClient, monkeypatch, presented_refresh: str) -> dict:
    """Arrange for a concurrent winner to rotate `presented_refresh`'s jti while
    the request under test is between its user load and its rotation."""
    import uuid

    from app.db.session import get_db
    from app.models._common import utcnow as real_utcnow
    from app.models.user import User
    from app.routes import auth as auth_mod
    from app.security.jwt import verify_token

    presented = str(verify_token(presented_refresh, expected_type="refresh").jti)
    seen: dict = {"fired": False, "winner_jti": str(uuid.uuid4())}

    def hook():
        if not seen["fired"]:
            seen["fired"] = True
            db = next(app_client.app.dependency_overrides[get_db]())
            try:
                user = db.query(User).filter(User.email == "first@example.com").one()
                seen["active_before_winner"] = user.active_refresh_jti
                user.previous_refresh_jti = user.active_refresh_jti
                user.active_refresh_jti = seen["winner_jti"]
                user.refresh_rotated_at = real_utcnow()
                db.commit()
            finally:
                db.close()
        return real_utcnow()

    monkeypatch.setattr(auth_mod, "utcnow", hook)
    seen["presented"] = presented
    return seen


def _stored_jtis(app_client: TestClient) -> tuple[str, str]:
    from app.db.session import get_db
    from app.models.user import User

    db = next(app_client.app.dependency_overrides[get_db]())
    try:
        user = db.query(User).filter(User.email == "first@example.com").one()
        return user.active_refresh_jti, user.previous_refresh_jti
    finally:
        db.close()


@pytest.mark.unit
def test_a_refresh_that_loses_the_race_serves_the_winners_identity(
    app_client: TestClient, monkeypatch
) -> None:
    """The losing request must not rotate over the winner. It re-reads the
    winner's state, finds its own jti is now the IMMEDIATELY previous one, and
    is served the winner's identity through the grace path -- a benign
    two-tab race is not read as a stolen token."""
    body = _register(app_client)
    original = body["tokens"]["refresh_token"]
    seen = _race_the_rotation(app_client, monkeypatch, original)

    loser = app_client.post("/auth/refresh", json={"refresh_token": original})

    assert seen["fired"] and seen["active_before_winner"] == seen["presented"], seen
    assert loser.status_code == 200, loser.text
    from app.security.jwt import verify_token

    served = str(verify_token(loser.json()["refresh_token"], expected_type="refresh").jti)
    assert served == seen["winner_jti"], "the loser must converge on the winner's jti"
    assert _stored_jtis(app_client) == (seen["winner_jti"], seen["presented"]), (
        "the winner's rotation was overwritten -- its jti is now neither active nor "
        "previous, so its next refresh reads as refresh_reused (#505)"
    )


@pytest.mark.unit
def test_with_no_grace_the_race_loser_gets_a_typed_401_not_a_rotation(
    app_client: TestClient, monkeypatch
) -> None:
    """Strict single-use (`jwt_refresh_grace_seconds = 0`): the loser presented
    a jti that is no longer active, which is exactly a replay under that
    setting -- a TYPED 401 `refresh_reused`, deliberately, and never a 500. The
    winner's state is untouched either way."""
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("JWT_REFRESH_GRACE_SECONDS", "0")
    get_settings.cache_clear()
    try:
        body = _register(app_client)
        original = body["tokens"]["refresh_token"]
        seen = _race_the_rotation(app_client, monkeypatch, original)

        loser = app_client.post("/auth/refresh", json={"refresh_token": original})

        assert seen["fired"] and seen["active_before_winner"] == seen["presented"], seen
        assert loser.status_code == 401, loser.text
        assert loser.json()["error"]["reason"] == "refresh_reused"
        assert _stored_jtis(app_client) == (seen["winner_jti"], seen["presented"])
    finally:
        get_settings.cache_clear()


# -----------------------------------------------------------------------------
# (b3) Ending every session means ending the grace path too (#636)
#
# A reset and a deactivation cleared only `active_refresh_jti`. The grace path
# honours `previous_refresh_jti` inside the window, and with active None it
# issued through `_issue_pair(keep_jti=None)` -- a FULL rotation -- so the
# previous token minted a new session after the control meant to end them all.
#
# Two fixes, and they are REDUNDANT at the refresh endpoint: while active is
# None the grace refusal (b) blocks, and active only becomes non-None again
# through a login, whose rotation overwrites `previous`. So one end-to-end test
# cannot tell them apart. Each is pinned on its own: (a) by driving reset and
# deactivation through their endpoints and asserting the three stored fields
# are cleared; (b) at the refresh endpoint, on a stored state with active None
# and a live previous inside the window.
# -----------------------------------------------------------------------------

_PASSWORD = "correct horse battery staple!"


def _rotation_state(app_client: TestClient, email: str) -> tuple:
    from app.db.session import get_db
    from app.models.user import User

    db = next(app_client.app.dependency_overrides[get_db]())
    try:
        u = db.query(User).filter(User.email == email).one()
        return u.active_refresh_jti, u.previous_refresh_jti, u.refresh_rotated_at
    finally:
        db.close()


def _reset_password(app_client: TestClient, monkeypatch, email: str) -> None:
    sent: list[str] = []
    monkeypatch.setattr(
        "app.routes.auth.send_password_reset_email",
        lambda *, to, token: sent.append(token),
    )
    app_client.post("/auth/forgot-password", json={"email": email})
    assert sent, "the reset email was not sent -- nothing to reset with"
    r = app_client.post(
        "/auth/reset-password", json={"token": sent[-1], "password": "another horse battery 9!"}
    )
    assert r.status_code == 200, r.text


@pytest.mark.unit
def test_a_password_reset_ends_the_grace_path_too(app_client: TestClient, monkeypatch) -> None:
    """End to end (#636): rotate once so the original token is the live
    `previous`, reset the password, and present that previous token inside the
    window. It must be a typed 401, not a new session."""
    body = _register(app_client)
    original = body["tokens"]["refresh_token"]
    assert (
        app_client.post("/auth/refresh", json={"refresh_token": original}).status_code == 200
    ), "setup: the first rotation must succeed so `original` becomes the previous jti"

    _reset_password(app_client, monkeypatch, "first@example.com")

    after = app_client.post("/auth/refresh", json={"refresh_token": original})
    assert after.status_code == 401, after.text
    assert after.json()["error"]["reason"] == "refresh_reused"


@pytest.mark.unit
def test_a_password_reset_clears_every_rotation_field(app_client: TestClient, monkeypatch) -> None:
    """Fix (a) on its own, through the reset endpoint: the previous jti and the
    rotation time go with the active one."""
    body = _register(app_client)
    app_client.post("/auth/refresh", json={"refresh_token": body["tokens"]["refresh_token"]})
    assert _rotation_state(app_client, "first@example.com")[1] is not None, "setup: no previous"

    _reset_password(app_client, monkeypatch, "first@example.com")

    assert _rotation_state(app_client, "first@example.com") == (None, None, None)


@pytest.mark.unit
def test_a_deactivation_clears_every_rotation_field(app_client: TestClient) -> None:
    """Fix (a) on its own, through the admin endpoint. `refresh()` refuses an
    inactive user outright, so the leftover `previous` mattered only after a
    reactivation -- it is cleared at deactivation regardless."""
    admin = app_client.post(
        "/auth/register",
        json={"email": "admin@kentro.example", "password": _PASSWORD, "display_name": "Admin"},
    )
    assert admin.status_code == 201, admin.text
    bearer = admin.json()["tokens"]["access_token"]
    victim = app_client.post(
        "/auth/register",
        json={"email": "victim@atlas.example", "password": _PASSWORD, "display_name": "Victim"},
    )
    assert victim.status_code == 201, victim.text
    app_client.post(
        "/auth/refresh", json={"refresh_token": victim.json()["tokens"]["refresh_token"]}
    )
    assert _rotation_state(app_client, "victim@atlas.example")[1] is not None, "setup: no previous"

    r = app_client.patch(
        f"/admin/users/{victim.json()['user']['id']}",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"is_active": False},
    )
    assert r.status_code == 200, r.text
    assert _rotation_state(app_client, "victim@atlas.example") == (None, None, None)


@pytest.mark.unit
def test_the_grace_path_refuses_when_no_session_is_active(app_client: TestClient) -> None:
    """Fix (b) on its own, at the refresh endpoint: a stored state with active
    None and a live previous inside the window -- what every reset left before
    #636 -- is a typed 401. The grace path must never rotate."""
    from app.db.session import get_db
    from app.models._common import utcnow
    from app.models.user import User
    from app.security.jwt import verify_token

    body = _register(app_client)
    original = body["tokens"]["refresh_token"]
    presented = str(verify_token(original, expected_type="refresh").jti)
    db = next(app_client.app.dependency_overrides[get_db]())
    try:
        u = db.query(User).filter(User.email == "first@example.com").one()
        u.active_refresh_jti = None
        u.previous_refresh_jti = presented
        u.refresh_rotated_at = utcnow()
        db.commit()
    finally:
        db.close()

    r = app_client.post("/auth/refresh", json={"refresh_token": original})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == "refresh_reused"
    assert _rotation_state(app_client, "first@example.com")[0] is None, "a session was minted"


# -----------------------------------------------------------------------------
# (c) Dead feature flags fail loudly at startup
# -----------------------------------------------------------------------------


@pytest.mark.unit
def test_startup_no_longer_refuses_when_require_mfa_true() -> None:
    # Sprint 6 T4 / D-027: the TOTP enroll/verify/login-challenge flow now
    # exists, so SHIELD_AUTH_REQUIRE_MFA GATES enforcement in routes/auth.py
    # rather than refusing to boot. Booting with the flag on must NOT raise.
    from app.config import Settings

    settings = Settings(shield_auth_require_mfa=True)
    settings.assert_safe_for_runtime()  # does not raise


@pytest.mark.unit
def test_startup_no_longer_refuses_when_require_email_verify_true() -> None:
    # Sprint 6 T5 / D-028: the email-verification flow now exists, so
    # SHIELD_AUTH_REQUIRE_EMAIL_VERIFY GATES login enforcement in routes/auth.py
    # rather than refusing to boot. Booting with the flag on must NOT raise.
    from app.config import Settings

    settings = Settings(shield_auth_require_email_verify=True)
    settings.assert_safe_for_runtime()  # does not raise


@pytest.mark.unit
def test_startup_raises_when_email_delivery_enabled_without_host() -> None:
    # D-028: enabling delivery without an SMTP host would silently drop every
    # verification / reset email — refuse to boot rather than swallow it.
    from app.config import Settings

    settings = Settings(shield_email_delivery_enabled=True, smtp_host="")
    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        settings.assert_safe_for_runtime()


@pytest.mark.unit
def test_the_default_forced_reauth_ceiling_is_twelve_hours(monkeypatch) -> None:
    """D-085, the owner's decision on #516: the ceiling is a session-AGE bound,
    lowered from 24 h to 12 h -- a working day with overrun, and half the
    overnight window. The expected value is the decision, not the constant: an
    edit to the default has to change this test and the decision record
    together. It is NOT an idle timeout; see D-085 and #516."""
    from app.config import Settings

    monkeypatch.delenv("SHIELD_FORCED_REAUTH_SECONDS", raising=False)
    assert Settings(_env_file=None).shield_forced_reauth_seconds == 12 * 3600


@pytest.mark.unit
def test_the_reauth_refusal_does_not_name_a_period(app_client: TestClient) -> None:
    """The ceiling is configurable, so the refusal must not say "daily": at the
    12 h default that was false. It says what happened, not how long it was."""
    from app.config import get_settings
    from app.security.jwt import issue_token

    body = _register(app_client)
    stale_auth_time = datetime.now(UTC) - timedelta(
        seconds=get_settings().shield_forced_reauth_seconds + 60
    )
    import uuid as _uuid

    stale, _ = issue_token(
        subject=_uuid.UUID(body["user"]["id"]),
        role="admin",
        typ="refresh",
        auth_time=stale_auth_time,
    )
    r = app_client.post("/auth/refresh", json={"refresh_token": stale})
    assert r.status_code == 401, r.text
    # THIS refusal, not another: a "session superseded" 401 would also pass the
    # checks below, and would if a refactor ran rotation before the ceiling.
    assert r.json()["error"]["reason"] == "reauth_required", r.text
    message = r.json()["error"]["message"]
    # No period in any spelling: not "daily", and not "12-hour" or "24 h"
    # either -- the value is configurable, so any figure here goes stale.
    lowered = message.lower()
    for word in ("daily", "hour", "day"):
        assert word not in lowered, (word, message)
    assert not any(ch.isdigit() for ch in message), message
    assert "sign in again" in message.lower(), message


# -----------------------------------------------------------------------------
# #658: an ACCESS token issued before a password reset is refused.
#
# The owner's rule, 2026-09-25: store `credentials_changed_at` truncated to
# whole seconds, and accept a token iff its `iat` >= that cutoff. `iat` is whole
# seconds too, so a login in the reset's own second is accepted -- which also
# accepts a token minted EARLIER in that same second. That sub-second residual
# is the rule's, stated here and pinned below rather than discovered later.
#
# Time is pinned through the two clocks involved: `app.security.jwt._now` sets
# a token's `iat`, and `app.routes.auth.utcnow` sets the reset's cutoff.
# -----------------------------------------------------------------------------

_CUTOFF_REASON = "credentials_changed"


def _second(offset_s: float = 0.0) -> datetime:
    """A whole second half a minute AGO, plus `offset_s`. In the past because a
    token's `nbf` equals its `iat`, and a future `nbf` makes the token invalid
    before any cutoff is consulted -- the first draft of these tests pinned a
    future second and every "refused" was that, not the rule. Recent enough
    that every token TTL and reset-link expiry still holds."""
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=30)
    return base + timedelta(seconds=offset_s)


def _me(app_client: TestClient, access: str):
    return app_client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})


def _login(app_client: TestClient, email: str = "first@example.com") -> str:
    r = app_client.post(
        "/auth/login", json={"email": email, "password": "another horse battery 9!"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _stored_cutoff(email: str = "first@example.com") -> datetime | None:
    from app.models.user import User

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        user = s.query(User).filter_by(email=email).one()
        return user.credentials_changed_at


@pytest.mark.unit
def test_an_access_token_from_before_a_reset_is_refused(
    app_client: TestClient, monkeypatch
) -> None:
    """The open half of #636: the token outlived the reset until its own TTL."""
    s = _second()
    monkeypatch.setattr("app.security.jwt._now", lambda: s - timedelta(seconds=5))
    old_access = _register(app_client)["tokens"]["access_token"]
    assert _me(app_client, old_access).status_code == 200, "setup: the token must work first"

    monkeypatch.setattr("app.routes.auth.utcnow", lambda: s + timedelta(microseconds=250_000))
    _reset_password(app_client, monkeypatch, "first@example.com")

    r = _me(app_client, old_access)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == _CUTOFF_REASON, r.text
    assert "sign in again" in r.json()["error"]["message"].lower(), r.text


@pytest.mark.unit
def test_a_login_in_the_same_second_as_the_reset_is_accepted(
    app_client: TestClient, monkeypatch
) -> None:
    """The owner's required case: the session a user starts right after a reset
    must not be refused by the reset it follows."""
    s = _second()
    monkeypatch.setattr("app.security.jwt._now", lambda: s - timedelta(seconds=5))
    _register(app_client)

    monkeypatch.setattr("app.routes.auth.utcnow", lambda: s + timedelta(microseconds=800_000))
    _reset_password(app_client, monkeypatch, "first@example.com")
    monkeypatch.setattr("app.security.jwt._now", lambda: s + timedelta(microseconds=900_000))
    new_access = _login(app_client)

    r = _me(app_client, new_access)
    assert r.status_code == 200, r.text


@pytest.mark.unit
def test_a_token_from_the_second_before_the_reset_is_refused(
    app_client: TestClient, monkeypatch
) -> None:
    """The boundary from below: one whole second earlier than the cutoff."""
    s = _second()
    monkeypatch.setattr("app.security.jwt._now", lambda: s - timedelta(microseconds=1))
    old_access = _register(app_client)["tokens"]["access_token"]

    monkeypatch.setattr("app.routes.auth.utcnow", lambda: s)
    _reset_password(app_client, monkeypatch, "first@example.com")

    r = _me(app_client, old_access)
    assert r.status_code == 401, r.text
    assert r.json()["error"]["reason"] == _CUTOFF_REASON, r.text


@pytest.mark.unit
def test_a_token_from_earlier_in_the_resets_own_second_is_accepted(
    app_client: TestClient, monkeypatch
) -> None:
    """THE RULE'S STATED RESIDUAL, pinned so it is a decision and not a surprise:
    `iat >= cutoff` in whole seconds accepts a token minted up to one second
    before the reset. Refusing it would refuse the same-second login above."""
    s = _second()
    monkeypatch.setattr("app.security.jwt._now", lambda: s + timedelta(microseconds=100_000))
    earlier = _register(app_client)["tokens"]["access_token"]

    monkeypatch.setattr("app.routes.auth.utcnow", lambda: s + timedelta(microseconds=900_000))
    _reset_password(app_client, monkeypatch, "first@example.com")

    assert _me(app_client, earlier).status_code == 200


@pytest.mark.unit
def test_the_reset_stores_its_cutoff_in_whole_seconds(app_client: TestClient, monkeypatch) -> None:
    s = _second()
    _register(app_client)
    assert _stored_cutoff() is None, "a new account has no cutoff"

    monkeypatch.setattr("app.routes.auth.utcnow", lambda: s + timedelta(microseconds=654_321))
    _reset_password(app_client, monkeypatch, "first@example.com")

    stored = _stored_cutoff()
    assert stored is not None
    assert stored.replace(tzinfo=UTC) == s, stored


@pytest.mark.unit
def test_a_login_rehash_is_not_a_credentials_change(app_client: TestClient, monkeypatch) -> None:
    """Login rewrites the hash when its parameters are upgraded. The password is
    the same, so a cutoff there would sign the user out of every other session
    on a routine rehash."""
    body = _register(app_client)
    monkeypatch.setattr("app.routes.auth.verify_password", lambda *_a, **_k: (True, True))
    r = app_client.post(
        "/auth/login",
        json={"email": "first@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 200, r.text
    assert _stored_cutoff() is None
    assert _me(app_client, body["tokens"]["access_token"]).status_code == 200
