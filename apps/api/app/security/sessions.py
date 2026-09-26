"""End every session a user holds: the one helper for reset, deactivation and
client archive (#652, D-103).

A session is two things, and ending one means ending both:

* **the refresh family.** ALL THREE rotation fields are cleared, not only the
  active jti (#636). `_grace_or_reuse` separately refuses when no session is
  active, which is the load-bearing guard: at the refresh endpoint either one
  alone refuses a leftover `previous`. Under a concurrent refresh this ORM write
  may leave `previous` set, because the flush skips a column whose loaded value
  was already None, and in that case only the guard refuses.
* **every access token already issued.** `credentials_changed_at` is the cutoff
  `current_user` checks (#658). Whole seconds, because a token's `iat` is whole
  seconds: a sign-in in the cutoff's own second has `iat == cutoff` and is
  accepted (the owner's rule).

The caller passes `at`, its own clock reading, so each route's time stays
pinnable where its tests already pin it.
"""

from __future__ import annotations

from datetime import datetime

from app.logging import get_logger
from app.models.user import User

log = get_logger(__name__)


def end_user_sessions(user: User, *, at: datetime) -> None:
    """Refuse every refresh and access token `user` holds from before `at`.

    Changes the row only; the caller commits, in the same transaction as the
    change that made the sessions end.
    """
    user.active_refresh_jti = None
    user.previous_refresh_jti = None
    user.refresh_rotated_at = None
    user.credentials_changed_at = at.replace(microsecond=0)
    log.info(
        "sessions.ended",
        user_id=str(user.id),
        cutoff=user.credentials_changed_at.isoformat(),
    )
