"""Audit log - blessed write surface.

Every state-changing route writes an audit row by calling `audit(...)`.
Direct construction of `AuditEntry` is allowed only inside this package.
"""

from app.audit.spine import audit

__all__ = ["audit"]
