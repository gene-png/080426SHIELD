"""Whose details an engagement uses — the primary-contact override (0039).

Intake takes the contact from the signed-in user's own record, which is right
when they are the point of contact and wrong whenever they are not: an
assistant or procurement lead completing the wizard on someone else's behalf had
no way to say so, and email is deliberately read-only, so the engagement
recorded the wrong person and a consultant would contact them (UX finding 9).

The resolution rules below are the whole feature. Getting them wrong means mail
goes to someone who explicitly said they are not the contact.
"""

from __future__ import annotations

import pytest

from app.models.client import Client
from app.models.user import User, UserRole
from app.routes.intake import _effective_contact


def _user() -> User:
    return User(
        email="assistant@example.com",
        password_hash="x",
        display_name="Alex Assistant",
        role=UserRole.CLIENT,
        title="Executive Assistant",
        phone="555-0100",
        timezone="America/New_York",
    )


def _client(**kw) -> Client:
    return Client(legal_name="Northwind Logistics", **kw)


@pytest.mark.unit
def test_no_override_uses_the_submitting_user() -> None:
    """Every pre-0039 client, and everyone who IS the contact."""
    contact = _effective_contact(_client(), _user())
    assert contact.display_name == "Alex Assistant"
    assert contact.email == "assistant@example.com"
    assert contact.is_override is False


@pytest.mark.unit
def test_missing_client_falls_back_to_the_user() -> None:
    """Intake can be opened before a client row exists."""
    contact = _effective_contact(None, _user())
    assert contact.email == "assistant@example.com"
    assert contact.is_override is False


@pytest.mark.unit
def test_override_redirects_name_and_email() -> None:
    contact = _effective_contact(
        _client(
            primary_contact_name="Dana Director",
            primary_contact_email="dana@example.com",
            primary_contact_title="CISO",
            primary_contact_phone="555-0199",
        ),
        _user(),
    )
    assert contact.display_name == "Dana Director"
    assert contact.email == "dana@example.com"
    assert contact.title == "CISO"
    assert contact.phone == "555-0199"
    # Flagged, so Review & submit can say whose details are being sent rather
    # than showing a name the submitter may not recognise as their own.
    assert contact.is_override is True


@pytest.mark.unit
def test_a_title_or_phone_alone_does_not_redirect_anything() -> None:
    """An override has to name someone. Stray optional fields — a half-filled
    form, or values left behind by an earlier edit — must not silently take
    over the contact."""
    contact = _effective_contact(
        _client(primary_contact_title="CISO", primary_contact_phone="555-0199"),
        _user(),
    )
    assert contact.display_name == "Alex Assistant"
    assert contact.email == "assistant@example.com"
    assert contact.is_override is False


@pytest.mark.unit
def test_a_named_contact_without_an_email_keeps_the_account_address() -> None:
    """Naming someone without an address is common — the submitter knows who
    but not their email. The account address is the only one we can be sure
    reaches a human, so it stands in rather than leaving the engagement with no
    contactable address at all."""
    contact = _effective_contact(
        _client(primary_contact_name="Dana Director"),
        _user(),
    )
    assert contact.display_name == "Dana Director"
    assert contact.email == "assistant@example.com"
    assert contact.is_override is True


@pytest.mark.unit
def test_partial_override_falls_back_field_by_field() -> None:
    """A name-only override still keeps a usable phone number, rather than
    blanking every field the override did not mention."""
    contact = _effective_contact(
        _client(primary_contact_name="Dana Director"),
        _user(),
    )
    assert contact.title == "Executive Assistant"
    assert contact.phone == "555-0100"
    # Timezone is never overridden: it is the submitting user's display
    # preference, not a property of the contact.
    assert contact.timezone == "America/New_York"


@pytest.mark.unit
def test_an_email_only_override_is_enough_to_redirect() -> None:
    contact = _effective_contact(
        _client(primary_contact_email="dana@example.com"),
        _user(),
    )
    assert contact.email == "dana@example.com"
    assert contact.display_name == "Alex Assistant"
    assert contact.is_override is True
