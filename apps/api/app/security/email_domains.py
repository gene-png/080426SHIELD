"""Email-domain helpers for tenant onboarding (Work Order B1).

`domain_of` extracts the lowercased domain from an email address.
`is_generic_provider` flags consumer mailbox providers that must never
auto-join a client (a gmail.com address tells us nothing about which
organization the person belongs to).
"""

from __future__ import annotations

from email_validator import EmailNotValidError, validate_email

# Consumer mailbox providers. A person at one of these could belong to any
# organization (or none), so we never auto-join them to a client by domain.
GENERIC_EMAIL_PROVIDERS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "ymail.com",
        "aol.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "gmx.com",
        "mail.com",
        "zoho.com",
        "yandex.com",
        "fastmail.com",
        "hey.com",
        "qq.com",
        "163.com",
        "126.com",
    }
)


def domain_of(email: str) -> str:
    """Lowercased domain part of an email, or '' if there is no '@'."""
    _, _, domain = email.partition("@")
    return domain.strip().lower()


def is_generic_provider(domain: str) -> bool:
    return domain.lower() in GENERIC_EMAIL_PROVIDERS


def is_reserved_domain(domain: str) -> bool:
    """True when `domain` is a special-use / reserved name (RFC 2606/6761 —
    e.g. `.test`, `.invalid`, `.localhost`) that the email validator refuses.

    A user can never register an address on such a domain, so approving one
    strands it as approved-but-unregistrable (the seeded `beacon.test` problem,
    Sprint 2 T9). We reuse email-validator's own reserved-name check — the very
    check pydantic's `EmailStr` applies at registration — by probing a throwaway
    address, rather than maintaining a hand-rolled TLD list that would drift as
    the RFCs evolve. `.example` is NOT reserved by the validator and returns
    False here, matching what registration accepts.
    """
    try:
        validate_email(f"probe@{domain}", check_deliverability=False)
    except EmailNotValidError:
        return True
    return False
