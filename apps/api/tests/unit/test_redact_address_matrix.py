"""The address-designator truth table (#130).

WHY THIS FILE EXISTS, AND WHY IT IS A TABLE.

`suite_pat` was rewritten three times in one sitting while fixing #130, and every
draft was correct for the corpus that prompted it and wrong for the next one: the
first lost `Ste-400`, the second lost `Suite Twelve`, the third lost every
zero-separator form (`PO Box99`, `Suite400`, `Apt3B`). CLAUDE.md's rule fires on
exactly that tell -- "a rule you have rewritten three times is a design problem,
not a bug list. Enumerate the state space instead of patching the case in front
of you... Do the matrix FIRST, then change the logic."

So this table was written BEFORE the new pattern, and every expected value below
is derived from what the redactor SHOULD do -- never from what any pattern does.
Deriving them from the implementation is the #72 shape (a test that supplies its
own expected value from the thing under test) and would make the table agree with
the code by construction.

THREE VERDICTS, and the third one is the point:

  REDACT   - a real PII designator. Must be removed. A miss here is a LEAK.
  LEAVE    - ordinary prose or a product name. Must survive byte-for-byte.
             A hit here corrupts every AI input on the platform (#130).
  RESIDUAL - known-wrong and deliberately accepted, with the reason recorded.
             An unstated exemption reads as an oversight to whoever finds it
             next, so each one carries its rationale inline.

`redact_for_ai` is the single LLM egress path (core principle 1), so every row
here applies to all five services and every AI purpose.
"""

from __future__ import annotations

import time

import pytest

from app.ai.redact import redact_for_ai

ADDR = "[ADDRESS]"


def _clean(text: str) -> str:
    cleaned, _ = redact_for_ai(text, mode="strict")
    return cleaned


# ---------------------------------------------------------------------------
# Axis 1 - suffix shape, keyword first, separator present
# ---------------------------------------------------------------------------

SUFFIX_SHAPE = [
    ("bare digits", "Suite 400", ADDR),
    ("digit+letter", "Apt 3B", ADDR),
    ("letter+digit", "Suite B3", ADDR),
    ("hyphenated digits", "Suite 400-B", ADDR),
    ("spelled out", "Suite Twelve", ADDR),
    ("spelled out, multi-token", "Suite One Hundred Twenty", ADDR),
    ("spelled out, hyphenated", "Apt Twenty-One", ADDR),
    ("roman, uppercase", "Apt IV", ADDR),
    ("single letter", "Suite A", ADDR),
    ("ordinal suffix", "Suite 1st", ADDR),
]

# The same shapes where the trailing token is an ordinary English word. These
# are the #130 corruptions: security prose, not addresses.
SUFFIX_SHAPE_PROSE = [
    ("lowercase word", "Suite of tools covers detection only."),
    ("plural noun", "Unit owners are unclear for 14 systems."),
    ("noun phrase", "Apt configuration drift across the estate."),
    ("hyphenated word", "Floor-level access controls were not tested."),
    # Roman-numeral letters spell ordinary words. `Unit did` and `Unit ill` are
    # both `Unit` + a token drawn entirely from [ivxlcdm], so a case-BLIND roman
    # branch redacts them. This pair is why that branch must be case-scoped.
    ("roman letters as a word", "Unit did not respond during the test."),
    ("roman letters as a word (2)", "Unit ill defined in the inventory."),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"), SUFFIX_SHAPE, ids=[c[0] for c in SUFFIX_SHAPE]
)
def test_designator_suffix_shapes_are_redacted(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"{shape}: a real designator leaked"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text"), SUFFIX_SHAPE_PROSE, ids=[c[0] for c in SUFFIX_SHAPE_PROSE]
)
def test_designator_keywords_in_ordinary_prose_survive(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: #130 corruption of security prose"


# ---------------------------------------------------------------------------
# Axis 2 - separator shape
# ---------------------------------------------------------------------------

SEPARATORS_REDACT = [
    # The zero-separator forms are the class a hand-written corpus never
    # contains: nobody TYPES `Suite400`, but OCR'd letterhead and exported
    # spreadsheet cells arrive that way, and those reach this boundary through
    # Tech Debt extraction. A `\b` after the keyword silently drops all of them.
    ("none (digit follows)", "Suite400", ADDR),
    ("none, PO Box", "PO Box99", ADDR),
    ("none, Ste", "Ste200", ADDR),
    ("none, Apt", "Apt3B", ADDR),
    ("none, Unit", "Unit12", ADDR),
    ("none, Floor", "Floor3", ADDR),
    ("space", "Suite 400", ADDR),
    ("tab", "Suite\t400", ADDR),
    ("non-breaking space", "Suite\xa0400", ADDR),
    ("period", "Ste. 200", ADDR),
    ("hash", "Apt #3B", ADDR),
    ("hyphen", "Ste-400", ADDR),
    ("PO Box, spaced", "PO Box 12345", ADDR),
    ("P.O. Box, dotted", "P.O. Box 99", ADDR),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"),
    SEPARATORS_REDACT,
    ids=[c[0] for c in SEPARATORS_REDACT],
)
def test_separator_shapes_are_redacted(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"separator {shape}: a real designator leaked"


# ---------------------------------------------------------------------------
# Axis 3 - value position. The pattern only ever looked keyword-first.
# ---------------------------------------------------------------------------

# `2nd Floor` is NEW coverage, not preserved coverage. On main it produced
# `2nd [ADDRESS]` -- the `\bFl`-eats-`oor` bug firing and leaving the number
# behind -- and `3rd Fl` matched nothing at all.
POSITION = [
    ("ordinal before Floor", "2nd Floor", ADDR),
    ("ordinal before Fl", "3rd Fl", ADDR),
    ("bare number before Floor", "3 Floor", ADDR),
    ("keyword first still works", "Floor 2", ADDR),
]

# The pre-keyword shape has exactly one member (Floor/Fl). Nobody writes these,
# so matching them would be pure over-redaction.
POSITION_LEAVE = [
    ("no such form", "200 Suite"),
    ("no such form (2)", "4B Apt"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text", "expected"), POSITION, ids=[c[0] for c in POSITION])
def test_value_before_keyword_is_redacted(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"{shape}: a real designator leaked"


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), POSITION_LEAVE, ids=[c[0] for c in POSITION_LEAVE])
def test_non_designator_word_order_survives(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: over-redacted a non-designator"


# ---------------------------------------------------------------------------
# Axis 4 - the trigger word as part of a product name. This is #130 itself.
# ---------------------------------------------------------------------------

PRODUCT_NAMES = [
    "Stellar Cyber",
    "Steampipe",
    "Sterling Commerce",
    "Steadfast",
    "Aptible",
    "Unity",
    "Unitrends",
    "United Airlines Portal",
    "Flowmon",
    "Fleet",
    "Flashpoint",
    "Fluency",
    "Suitecrm",
    "Floorplan Manager",
    "Apt Cache Proxy",
    "Adobe Creative Suite Enterprise",
    "Sophos Security Suite Enterprise",
    "CrowdStrike Falcon",
    "Splunk Enterprise",
    "Tenable Nessus",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", PRODUCT_NAMES)
def test_real_security_product_names_survive_redaction(name: str) -> None:
    """The corpus that could not have existed in seed data.

    Of 73 name-shaped quoted strings in `scripts/seed_demo.py` and
    `app/ai/fixtures.py`, ZERO trip the address rule -- so an address assertion
    built on seed data passes forever, and #130 lived for months underneath one.
    These names are written here deliberately, from real security products, for
    exactly that reason.
    """
    assert _clean(name) == name, "#130: product name corrupted on the way to the model"


SECURITY_PROSE = [
    "Flat network segmentation is the core finding.",
    "Flag any unencrypted volumes.",
    "The fleet of 200 laptops is unmanaged.",
    "There are flaws in the flow control logic.",
]


@pytest.mark.unit
@pytest.mark.parametrize("text", SECURITY_PROSE)
def test_security_prose_survives_redaction(text: str) -> None:
    """Security vocabulary is unusually dense in "fl": flat, flag, flaw, flow."""
    assert _clean(text) == text, "#130: security prose corrupted on the way to the model"


# ---------------------------------------------------------------------------
# Axis 5 - surrounding context
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_street_and_suite_are_both_redacted_in_one_line() -> None:
    assert _clean("1234 Main Street, Suite 200") == f"{ADDR}, {ADDR}"


@pytest.mark.unit
def test_a_bulleted_list_is_not_joined_across_lines() -> None:
    """A separator class containing `\\s` reaches across a newline into the next
    bullet's text and merges two list items into one corrupted line. Client notes
    are full of bullet lists; addresses that wrap mid-designator are rare, so the
    separator class stops at the newline and the wrapped form is a listed
    residual below.
    """
    text = "- Business Unit\n- 3rd party risk tooling"
    assert _clean(text) == text


# ---------------------------------------------------------------------------
# Accepted residuals. Each is WRONG and deliberately tolerated, with a reason.
# ---------------------------------------------------------------------------

# A designator keyword followed by a number is indistinguishable from a product
# version or a threat-group designation. No suffix-shape rule can separate them;
# only surrounding-context logic could, and that is a different design.
RESIDUAL_OVER_REDACTED = [
    ("version number", "Burp Suite 2024.1", "Burp [ADDRESS].1"),
    ("version, v-prefixed", "Burp Suite v2", "Burp [ADDRESS]"),
    ("version, bare", "Adobe Creative Suite 6", "Adobe Creative [ADDRESS]"),
    ("package version", "apt 1.2.3", "[ADDRESS].2.3"),
    ("threat group", "APT 28", ADDR),
    ("threat intel unit", "Unit 42", ADDR),
    ("threat intel unit (2)", "Unit 8200", ADDR),
    # NSA Suite A / Suite B cryptography, caught by the single-letter branch,
    # which exists so `Suite A` (a real lettered suite) is not lost.
    ("crypto suite", "Suite B Cryptography", "[ADDRESS] Cryptography"),
]

RESIDUAL_LEAKED = [
    # Letter-only designators. Accepted because once `street_pat` has fired, a
    # letter-only designator carries no identifying content on its own:
    # `1234 Main Street, Suite AB` -> `[ADDRESS], Suite AB`.
    #
    # The alternative -- an uppercase-only branch `(?-i:[A-Z]{1,3})` -- was
    # rejected: it corrupts `Adobe Creative Suite CC` and `Sophos Security Suite
    # XG`, which is #130 reintroduced on a different branch.
    #
    # CAVEAT, stated rather than glossed: `street_pat` does NOT reliably catch
    # the identifying half. Spelled-out and alphanumeric house numbers pass it
    # (`One Federal Plaza`, `221B Baker Street`); filed separately.
    ("two letters", "Suite AB"),
    ("two letters (2)", "Ste BB"),
    # A colon or comma between keyword and value is not in the separator class.
    # Pre-existing; unchanged by #130's fix.
    ("colon separator", "Suite: 400"),
    ("comma separator", "Suite, 400"),
    # Full-width numerals. `[A-Za-z0-9]` is ASCII-only.
    ("full-width digits", "Suite ４００"),
    # A designator wrapped onto the next line, excluded deliberately so that
    # bulleted lists survive -- see the bullet test above.
    ("wrapped line", "Suite\n400"),
    # Non-US designators were never covered. `Flat` is caught on main only by
    # the `\bFl`-eats-`at` bug: accidental coverage, not intended coverage.
    ("UK flat", "Flat 3"),
    ("non-US level", "Level 2"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"),
    RESIDUAL_OVER_REDACTED,
    ids=[c[0] for c in RESIDUAL_OVER_REDACTED],
)
def test_accepted_residual_over_redaction(shape: str, text: str, expected: str) -> None:
    """Pins a KNOWN DEFECT so narrowing it later is a deliberate act, not a surprise."""
    assert _clean(text) == expected, f"{shape}: accepted residual changed -- update D-058"


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), RESIDUAL_LEAKED, ids=[c[0] for c in RESIDUAL_LEAKED])
def test_accepted_residual_leak(shape: str, text: str) -> None:
    """Pins a KNOWN LEAK. These are the cells to revisit first if the rule is widened."""
    assert _clean(text) == text, f"{shape}: accepted residual changed -- update D-058"


# ---------------------------------------------------------------------------
# The rule runs on client-supplied text, so it must not be a DoS vector.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_address_rule_does_not_backtrack_catastrophically() -> None:
    probes = [
        "Suite " + "a-" * 2000 + "!",
        "Fl" + "o" * 5000,
        "Unit " + "1-" * 3000 + "x",
        "Suite 4 " * 3000,
    ]
    start = time.monotonic()
    for probe in probes:
        redact_for_ai(probe, mode="strict")
    elapsed = time.monotonic() - start
    assert elapsed < 5.0, f"address rule took {elapsed:.1f}s on pathological input"
