"""SMTP email sender, gated behind SHIELD_EMAIL_DELIVERY_ENABLED (Sprint 6 T5, D-028).

Dev uses MailHog (``docker-compose.yml`` service ``mailhog`` on :1025 / UI :8025).
Delivery is off by default: with the flag off we skip the network send and log
that we did — a deployment that has not configured SMTP never silently believes
it sent mail. With the flag on but no host configured we FAIL LOUDLY rather than
swallow the misconfiguration (Master Spec / CLAUDE.md principle 2).

The two ``send_*`` helpers compose the message and hand it to the low-level
``send_email``; routes call the helpers so the raw token never has to be threaded
through a subject/body string in the caller.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import get_settings
from app.logging import get_logger

log = get_logger("app.email.sender")


def send_email(*, to: str, subject: str, body: str) -> None:
    """Deliver one plaintext email via SMTP, gated by the delivery flag.

    Fails loudly if delivery is enabled but SMTP is unconfigured; otherwise a
    real send failure propagates (no silent swallow).
    """
    settings = get_settings()
    if not settings.shield_email_delivery_enabled:
        # Never log the body (it carries a token/link). Subject + recipient only.
        log.info("email.delivery_disabled", to=to, subject=subject)
        return

    if not settings.smtp_host:
        raise RuntimeError(
            "SHIELD_EMAIL_DELIVERY_ENABLED=true but SMTP_HOST is not configured. "
            "Set SMTP_HOST (MailHog in dev) or disable delivery."
        )

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.send_message(message)
    log.info("email.sent", to=to, subject=subject)


def _verify_link(token: str) -> str:
    base = get_settings().web_base_url.rstrip("/")
    return f"{base}/verify-email?token={token}"


def _reset_link(token: str) -> str:
    base = get_settings().web_base_url.rstrip("/")
    return f"{base}/reset-password?token={token}"


def send_verification_email(*, to: str, token: str) -> None:
    """Send an email-address verification link to a freshly registered user."""
    link = _verify_link(token)
    body = (
        "Welcome to SHIELD.\n\n"
        "Please confirm your email address by opening the link below:\n\n"
        f"{link}\n\n"
        "This link expires in 24 hours. If you did not create a SHIELD account, "
        "you can ignore this message."
    )
    send_email(to=to, subject="Confirm your SHIELD email address", body=body)


def send_password_reset_email(*, to: str, token: str) -> None:
    """Send a password-reset link. Sent only when an account actually exists."""
    link = _reset_link(token)
    body = (
        "We received a request to reset your SHIELD password.\n\n"
        "Open the link below to choose a new password:\n\n"
        f"{link}\n\n"
        "This link expires in 1 hour. If you did not request a reset, you can "
        "ignore this message — your password will not change."
    )
    send_email(to=to, subject="Reset your SHIELD password", body=body)


def send_release_notification(*, to: str, service_label: str, title: str, version: int) -> None:
    """Notify one client user that a finalized deliverable was released to them
    (Sprint 7 T2, D-030).

    Best-effort: gated by the same delivery flag as every other send — with
    delivery off this is a logged no-op inside ``send_email``. Carries the
    service, the deliverable title/version, and a link to the client's documents
    surface so the recipient can review and download it.
    """
    base = get_settings().web_base_url.rstrip("/")
    documents_url = f"{base}/documents"
    subject = f"Your {service_label} deliverable is ready"
    body = (
        f"A new {service_label} deliverable has been released to your team on "
        "SHIELD.\n\n"
        f"  {title} (v{version})\n\n"
        "Open your documents to review and download it:\n\n"
        f"{documents_url}\n\n"
        "You are receiving this because you have a SHIELD client account for "
        "this engagement."
    )
    send_email(to=to, subject=subject, body=body)
