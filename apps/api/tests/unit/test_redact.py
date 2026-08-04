"""Adversarial PII redaction tests.

Master Spec §12: "The redactor MUST have automated test coverage on every
PII pattern (emails, phones, addresses, names, identifiers, signature
blocks) with realistic adversarial test cases." The redactor is the v1
egress security boundary; over-redaction is preferable to under-redaction.
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai, redact_payload

# ---------------------------------------------------------------------------
# Emails
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_strips_plain_email() -> None:
    cleaned, counts = redact_for_ai("Contact alice@example.gov for access.")
    assert "alice@example.gov" not in cleaned
    assert "[EMAIL]" in cleaned
    assert counts["email"] == 1


@pytest.mark.unit
def test_redact_strips_email_with_subaddress_and_plus_tag() -> None:
    cleaned, counts = redact_for_ai("Reply to atlas.poc+intake@example-defense.gov today.")
    assert "atlas.poc+intake@example-defense.gov" not in cleaned
    assert counts["email"] == 1


@pytest.mark.unit
def test_redact_counts_multiple_emails() -> None:
    _, counts = redact_for_ai("a@x.gov b@y.mil c@z.com")
    assert counts["email"] == 3


# ---------------------------------------------------------------------------
# Phone numbers (US + international)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "555-867-5309",
        "(555) 867-5309",
        "555.867.5309",
        "+1 555 867 5309",
        "+1-555-867-5309",
    ],
)
def test_redact_strips_us_phone_formats(raw: str) -> None:
    cleaned, counts = redact_for_ai(f"Call us at {raw} today.")
    assert raw not in cleaned
    assert counts.get("phone", 0) >= 1


@pytest.mark.unit
def test_redact_strips_intl_phone() -> None:
    cleaned, _ = redact_for_ai("Reach out: +44 20 7946 0958.")
    assert "+44" not in cleaned
    assert "0958" not in cleaned


# ---------------------------------------------------------------------------
# SSN / EIN / CAGE / contract numbers
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_strips_ssn() -> None:
    cleaned, counts = redact_for_ai("SSN: 123-45-6789.")
    assert "123-45-6789" not in cleaned
    assert counts["ssn"] == 1


@pytest.mark.unit
def test_redact_strips_ein() -> None:
    cleaned, counts = redact_for_ai("Tax ID 12-3456789 on file.")
    assert "12-3456789" not in cleaned
    assert counts["ein"] == 1


@pytest.mark.unit
def test_redact_strips_cage_with_introducer() -> None:
    cleaned, counts = redact_for_ai("CAGE 1A2B3 listed in SAM.")
    assert "1A2B3" not in cleaned
    assert counts["cage"] == 1


@pytest.mark.unit
def test_redact_strips_contract_number() -> None:
    cleaned, counts = redact_for_ai("Award: W91QUZ-23-C-0001 (modification 5).")
    assert "W91QUZ-23-C-0001" not in cleaned
    assert counts["contract"] == 1


# ---------------------------------------------------------------------------
# Addresses (strict only)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_strips_street_address_strict_mode() -> None:
    text = "Our HQ is at 1600 Pennsylvania Avenue, Washington DC."
    cleaned, counts = redact_for_ai(text, mode="strict")
    assert "1600 Pennsylvania Avenue" not in cleaned
    assert counts.get("address", 0) >= 1


@pytest.mark.unit
def test_redact_strips_suite_and_po_box_strict_mode() -> None:
    text = "Mail: Suite 400. Also PO Box 12345."
    cleaned, counts = redact_for_ai(text, mode="strict")
    assert "Suite 400" not in cleaned
    assert "PO Box 12345" not in cleaned
    assert counts.get("address", 0) >= 1


@pytest.mark.unit
def test_redact_keeps_address_in_standard_mode() -> None:
    text = "Our HQ is at 1600 Pennsylvania Avenue."
    cleaned, counts = redact_for_ai(text, mode="standard")
    assert "1600 Pennsylvania Avenue" in cleaned
    assert "address" not in counts


# ---------------------------------------------------------------------------
# Org name (strict only)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_replaces_client_org_name_strict() -> None:
    text = "Atlas Defense Solutions ran the assessment. Atlas Defense Solutions also reviewed."
    cleaned, counts = redact_for_ai(text, mode="strict", client_org_name="Atlas Defense Solutions")
    assert "Atlas Defense Solutions" not in cleaned
    assert cleaned.count("[CLIENT]") == 2
    assert counts["client_org"] == 2


@pytest.mark.unit
def test_redact_keeps_org_name_in_standard_mode() -> None:
    text = "Atlas Defense Solutions ran the assessment."
    cleaned, _ = redact_for_ai(text, mode="standard", client_org_name="Atlas Defense Solutions")
    assert "Atlas Defense Solutions" in cleaned


# ---------------------------------------------------------------------------
# Names via hints
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_replaces_name_hints() -> None:
    cleaned, counts = redact_for_ai(
        "Eugene Powell approved; Jane Doe is the alternate.",
        name_hints=["Eugene Powell", "Jane Doe"],
    )
    assert "Eugene Powell" not in cleaned
    assert "Jane Doe" not in cleaned
    assert counts["name"] == 2


# ---------------------------------------------------------------------------
# Signature blocks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_strips_signature_block() -> None:
    text = (
        "Please find the system inventory attached.\n"
        "\n"
        "Sincerely,\n"
        "Eugene Powell\n"
        "CISO, Atlas Defense Solutions\n"
        "eugene@atlas-defense.gov\n"
        "+1 555 867 5309\n"
    )
    cleaned, counts = redact_for_ai(text)
    assert "Sincerely," not in cleaned
    assert "Eugene Powell" not in cleaned
    assert "eugene@atlas-defense.gov" not in cleaned
    assert "555 867 5309" not in cleaned
    assert "[SIGNATURE_BLOCK]" in cleaned
    assert counts["signature_block"] == 1


# ---------------------------------------------------------------------------
# Mode = off (pass-through)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_off_mode_returns_text_unchanged() -> None:
    text = "alice@example.gov 123-45-6789"
    cleaned, counts = redact_for_ai(text, mode="off")
    assert cleaned == text
    assert counts == {}


# ---------------------------------------------------------------------------
# Payload (nested dict / list)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_redact_payload_walks_nested_structures() -> None:
    obj = {
        "title": "Inventory",
        "items": [
            {"vendor": "Wiz", "contact": "alice@example.gov"},
            {"vendor": "Crowdstrike", "contact": "bob@example.gov"},
        ],
        "notes": "SSN on file: 123-45-6789.",
    }
    cleaned, counts = redact_payload(obj)
    assert cleaned["title"] == "Inventory"
    assert cleaned["items"][0]["vendor"] == "Wiz"
    assert "alice@example.gov" not in cleaned["items"][0]["contact"]
    assert "bob@example.gov" not in cleaned["items"][1]["contact"]
    assert "123-45-6789" not in cleaned["notes"]
    assert counts["email"] == 2
    assert counts["ssn"] == 1
    # Dict keys themselves are preserved as-is.
    assert set(cleaned.keys()) == {"title", "items", "notes"}


@pytest.mark.unit
def test_redact_payload_preserves_non_string_scalars() -> None:
    cleaned, _ = redact_payload({"count": 42, "active": True, "score": None})
    assert cleaned == {"count": 42, "active": True, "score": None}
