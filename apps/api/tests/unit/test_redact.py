"""Adversarial PII redaction tests.

Master Spec §12: "The redactor MUST have automated test coverage on every
PII pattern (emails, phones, addresses, names, identifiers, signature
blocks) with realistic adversarial test cases." The redactor is the v1
egress security boundary; over-redaction is preferable to under-redaction.
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai, redact_org_name, redact_payload

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


@pytest.mark.unit
def test_redact_payload_forwards_mode_and_org_name_to_every_string() -> None:
    """`redact_payload` must pass its arguments DOWN, not just accept them.

    Answering a surviving mutant from `scripts/mutation_sweep.py`: dropping
    `mode=`, `client_org_name=` or `name_hints=` from the `redact_for_ai` call
    inside `_walk` left the whole suite green. Each is a silent security-boundary
    change -- dropping `mode=` makes every caller strict (over-redacts, and
    `standard` mode exists precisely because some prompts need the org context),
    and dropping the other two stops the org name and the name hints being
    removed at all, which is a LEAK.

    Pre-existing gap, unrelated to #130; closed here because the sweep asked.
    """
    payload = {"note": "Northwind HQ is at 1600 Pennsylvania Avenue. Ask Alice."}

    strict, strict_counts = redact_payload(
        payload, mode="strict", client_org_name="Northwind", name_hints=["Alice"]
    )
    assert "Northwind" not in strict["note"], "client_org_name was not forwarded"
    assert "Alice" not in strict["note"], "name_hints was not forwarded"
    assert "1600 Pennsylvania Avenue" not in strict["note"]
    assert strict_counts["client_org"] == 1
    assert strict_counts["name"] == 1

    # `standard` keeps addresses and the org name. If `mode=` is not forwarded,
    # this call silently behaves like the strict one above.
    standard, standard_counts = redact_payload(
        payload, mode="standard", client_org_name="Northwind", name_hints=["Alice"]
    )
    assert "Northwind" in standard["note"], "mode was not forwarded (org name removed)"
    assert (
        "1600 Pennsylvania Avenue" in standard["note"]
    ), "mode was not forwarded (address removed)"
    assert "client_org" not in standard_counts
    assert "address" not in standard_counts
    assert standard_counts["name"] == 1, "name hints apply in every mode"


@pytest.mark.unit
def test_redact_org_name_directly() -> None:
    """`redact_org_name` is public, and its docstring says it is tested directly.

    That claim was false until this test: every other exercise of the org rule
    goes through `redact_for_ai(..., client_org_name=...)`, which cannot tell the
    function apart from the strict-mode gate wrapped around it. A public API kept
    public on the strength of a fact that is not true is the same shape as the
    `_redacted_form` parity docstring (CLAUDE.md).
    """
    cleaned, count = redact_org_name("Northwind Traders uses Northwind SSO.", "Northwind")
    assert cleaned == "[CLIENT] Traders uses [CLIENT] SSO."
    assert count == 2

    # Whole-token, case-insensitive, and a no-op returns the input untouched.
    assert redact_org_name("northwind wins", "Northwind") == ("[CLIENT] wins", 1)
    assert redact_org_name("Northwinds are strong", "Northwind") == ("Northwinds are strong", 0)
    assert redact_org_name("nothing here", "Northwind") == ("nothing here", 0)
    # An empty or whitespace org name must not compile into a match-everything
    # pattern; it returns the text unchanged and counts nothing.
    assert redact_org_name("Northwind", "   ") == ("Northwind", 0)
