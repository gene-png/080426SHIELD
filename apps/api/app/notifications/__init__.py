"""Notification helpers.

The blessed way to write a notification row is `notify(...)` - mirrors the
pattern used by `app.audit.spine.audit()`. Routes never construct
Notification rows directly.
"""

from app.notifications.spine import notify, notify_role

__all__ = ["notify", "notify_role"]
