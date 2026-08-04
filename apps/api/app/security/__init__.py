"""Security primitives: password hashing, JWT signing, lockout tracking.

Nothing user-facing in here - these are the building blocks that the auth
routes (Phase 1 stage 3b) and the role-based route guards (Phase 1 stage 7)
compose with. Each module is intentionally small + boring so it can be
audited line-by-line in an OWASP review.
"""
