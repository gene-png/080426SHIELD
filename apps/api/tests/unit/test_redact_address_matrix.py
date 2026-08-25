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

TWO STATED EXCEPTIONS to that absolute, because an absolute with unlisted
exceptions is exactly the shape this file exists to catch:

  - Axis 6 (idempotence) asserts a FIXED POINT, so pass 2's expected value is
    whatever pass 1 produced. A property is not an expected value; the axis is
    guarded by its own test that the cells are not all pass-1 no-ops.
  - The horizontal/vertical whitespace sweeps derive their parameter sets from
    `str.splitlines()` and `re`, not from the redactor. That is a different
    module deciding what a line break is, which is the point -- the enumerated
    class this replaced agreed with itself and dropped sixteen characters.

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

import re
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
    # letter-HYPHEN-digit. The axis had digit+letter and digit-hyphen-letter but
    # not this, and the pattern broke at exactly the missing cell: `Suite B-201`
    # matched only `Suite B` and produced `[ADDRESS]-201` -- the unit number
    # surviving under an output that LOOKS redacted. A partial match that reads
    # as a success is the silent-failure shape this module exists to prevent, so
    # the assertion is exact-equality and would catch it.
    ("letter-hyphen-digit", "Suite B-201", ADDR),
    ("letter-hyphen-digit (2)", "Apt A-12", ADDR),
    ("letter-dot-digit", "Suite B.201", ADDR),
    ("abbreviated, letter-hyphen-digit", "Ste. D-3", ADDR),
    ("two letters-hyphen-digit", "Suite AB-201", ADDR),
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
    # A keyword ENDING A SENTENCE. This is the most common context the rule meets
    # in consultant prose, and it is why the separator class allows a period only
    # after an ABBREVIATION: ". " is both an abbreviating separator and a
    # sentence break, so a period after a spelled-out word let the rule swallow
    # the start of the next sentence. "Ste." is an abbreviation; "unit." is a
    # word followed by a full stop.
    ("keyword ends a sentence", "Only one control covers this unit. 3 findings remain."),
    ("keyword ends a sentence (2)", "Cameras on each floor. 2 were offline."),
    ("keyword ends a sentence (3)", "Reviewed each business unit. A follow-up is due."),
    # `ill` is drawn entirely from the roman class [IVXL], so a case-BLIND roman
    # branch redacts it. This is THE case that pins the `(?-i:` scoping: revert
    # that alone and this row goes red.
    ("roman letters as a word", "Unit ill defined in the inventory."),
    # `did` is not at risk (d is not in [IVXL]) and is here only as an ordinary
    # prose row. Recorded explicitly because an earlier draft cited it as the
    # evidence for the case-scoping, and it cannot be: it stays green either way.
    ("prose after the keyword", "Unit did not respond during the test."),
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
    # The rest of Unicode's HORIZONTAL whitespace. `\s` covers 19 such characters
    # and an enumerated class covered three, so narrowing the separator to stop
    # at newlines silently dropped sixteen of them -- a LEAK, not a residual, and
    # one nobody listed because the newline decision was framed as being about
    # newlines. These are not exotic: PDF and Word text extraction emits thin and
    # narrow-no-break spaces routinely, and that is exactly how client letterhead
    # reaches this boundary.
    ("thin space", "Suite\u2009400", ADDR),
    ("narrow no-break space", "Suite\u202f400", ADDR),
    ("en space", "Suite\u2002400", ADDR),
    ("em space", "Suite\u2003400", ADDR),
    ("ideographic space", "Suite\u3000400", ADDR),
    ("medium mathematical space", "Suite\u205f400", ADDR),
    ("ogham space mark", "Suite\u1680400", ADDR),
    ("street rule, thin space", "1234\u2009Main\u2009Street", ADDR),
    ("street rule, narrow no-break", "1600\u202fPennsylvania\u202fAvenue", ADDR),
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
    ("keyword first still works", "Floor 2", ADDR),
]

# The pre-keyword shape has exactly one member (Floor/Fl). Nobody writes these,
# so matching them would be pure over-redaction.
POSITION_LEAVE = [
    ("no such form", "200 Suite"),
    ("no such form (2)", "4B Apt"),
    # The ordinal is REQUIRED on the pre-keyword branch. Without it this branch
    # reaches leftward into ordinary prose: "floor plans", "floor switches" and
    # "floor wardens" are all normal facility- and network-assessment words.
    ("bare number, compound noun", "We reviewed 3 floor plans."),
    ("bare number, compound noun (2)", "Check the floor switches."),
    # ...and with `\s` as its separator it also crossed a newline, which is the
    # exact merge the suite separator class is written to prevent. The guarantee
    # has to hold for EVERY sub-pattern in the compiled rule, not just one.
    #
    # It did not, when this comment was first written. `_STREET_PAT` still used
    # `\s+` while the other two sub-patterns had dropped it, so the sentence
    # above was true of two of three and no row tested the third. Pinned now by
    # `test_the_street_rule_does_not_reach_across_a_newline`; a claim in a
    # comment is not a test, and this one had to be turned into one.
    #
    # The ordinal here is load-bearing in the TEST, not just the rule: the first
    # version of this row used a bare "3", which the ordinal requirement above
    # already rejects, so it stayed green with the newline exclusion reverted and
    # pinned nothing. Caught by red-on-revert, not by review.
    ("across a newline", "reviewed the 2nd\nfloor plans in detail"),
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
    # Negative controls -- names with no designator keyword in them at all.
    # These must stay in the corpus: they are what distinguishes "the rule is
    # off" from "the rule is correct", and the measured ratio quoted in D-058
    # (17 of 23) is only reproducible while they are here.
    "CrowdStrike Falcon",
    "Splunk Enterprise",
    "Tenable Nessus",
    "Palo Alto Cortex XDR",
    "Rapid7 InsightVM",
    "Microsoft Sentinel",
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


# The same guarantee, for the STREET sub-pattern. Split out rather than folded
# into the case above because it was the one sub-pattern the guarantee did not
# hold for: `_SUITE_SEP` and `_PRE_KEYWORD_PAT` both dropped `\s` while
# `_STREET_PAT` kept it, so the comment in POSITION_LEAVE claiming the guarantee
# holds for EVERY sub-pattern was true of two of the three.
#
# The failure is worse here than a merge, because the street rule's leading
# `\d{1,6}` reaches BACKWARD across the newline and consumes a number that
# belonged to the previous line -- a finding count, a host count, a severity --
# and the redacted text then reads as an ordinary sentence with no sign that
# anything was lost. That is #130's disease exactly: plausible output, nothing
# raised, no test able to see it.
STREET_NEWLINE_LEAVE = [
    ("count on the previous line", "Servers reviewed: 5\nMain Street office is unstaffed."),
    ("host count on the previous line", "hosts: 3\nPark Avenue tooling needs review"),
    ("bare merge", "reviewed 5\nMain Street office"),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text"), STREET_NEWLINE_LEAVE, ids=[c[0] for c in STREET_NEWLINE_LEAVE]
)
def test_the_street_rule_does_not_reach_across_a_newline(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: the street rule merged two lines"


# The separator is defined as a SUBTRACTION -- `\s` minus the vertical set -- so
# the two halves are asserted as SETS rather than sampled. Sampling is what let
# the first version of this fix ship an enumerated `[ 	 ]` that dropped
# sixteen horizontal characters: every cell anyone thought to write passed.
#
# Derived from `str.splitlines()` and `re`, not from the redactor, so it cannot
# agree with the implementation by construction (#72). The module hardcodes its
# subtraction list; this asserts that list against a different module's opinion
# of what a line break is.
_VERTICAL = [c for c in map(chr, range(0x11000)) if len(("a" + c + "b").splitlines()) > 1]
_HORIZONTAL = [c for c in map(chr, range(0x11000)) if re.match(r"\s", c) and c not in _VERTICAL]

# ...and per SEPARATOR, not just per character. The first version of this sweep
# exercised two of the six separators in the rule (`_STREET_SEP` via a street
# address and `_SUITE_SEP` via `Suite`), so reverting `_SUITE_SEP_ABBREV` to the
# leaking enumerated class left the ENTIRE table green while `Ste.<U+202F>400`
# and `Apt<U+2009>3B` egressed verbatim. Measured, not theorised: the revert was
# applied, `grep` confirmed it landed, and all 153 cells passed.
#
# That is the same defect this file exists to prevent, inside the fix for it, one
# level up -- so the guarantee is now asserted once per separator.
_SEPARATOR_SITES = [
    ("street", "1600{ch}Pennsylvania{ch}Avenue"),
    ("suite keyword", "Suite{ch}400"),
    ("abbreviated keyword", "Ste{ch}400"),
    ("abbreviated keyword (2)", "Apt{ch}3B"),
    ("PO Box keyword", "PO{ch}Box 12345"),
    ("value before keyword", "2nd{ch}Floor"),
    ("between number words", "Suite One{ch}Hundred"),
]


@pytest.mark.unit
@pytest.mark.parametrize("site,template", _SEPARATOR_SITES, ids=[s[0] for s in _SEPARATOR_SITES])
@pytest.mark.parametrize("ch", _HORIZONTAL, ids=[f"U+{ord(c):04X}" for c in _HORIZONTAL])
def test_every_horizontal_whitespace_character_separates_an_address(
    ch: str, site: str, template: str
) -> None:
    r"""A leak, not a residual: `\s` covers 19 of these and an enumerated list covered 3."""
    assert _clean(template.format(ch=ch)) == ADDR, f"{site}: U+{ord(ch):04X} stopped separating"


@pytest.mark.unit
@pytest.mark.parametrize("site,template", _SEPARATOR_SITES, ids=[s[0] for s in _SEPARATOR_SITES])
@pytest.mark.parametrize("ch", _VERTICAL, ids=[f"U+{ord(c):04X}" for c in _VERTICAL])
def test_no_rule_reaches_across_any_vertical_whitespace_character(
    ch: str, site: str, template: str
) -> None:
    """The bullet-merge guarantee, over the whole line-break set and every separator.

    Asserts the separator SURVIVES in the output rather than that the string is
    unchanged: some templates legitimately redact the part before the break
    (`Suite One` is a complete designator), and demanding no change at all would
    make those cells assert the wrong thing. A match that spanned the break would
    consume the character, so its survival is the property.
    """
    out = _clean(template.format(ch=ch))
    assert ch in out, f"{site}: a rule spanned U+{ord(ch):04X} and merged two lines"


# ---------------------------------------------------------------------------
# Axis 6 - text that has already been through the pipeline once
# ---------------------------------------------------------------------------
#
# CLAUDE.md names four classes a hand-written corpus structurally cannot
# contain, and this branch is what added that list. Three of them are covered
# above (malformed strings, name + version number, non-US variants). This is the
# fourth, and the table shipped without it -- the branch stated the rule and
# then missed one of its own four cells.
#
# It is not hypothetical here. The Tech Debt extractor redacts its own inventory
# input, so `[CLIENT] SOC Platform` is the NORMAL product of any extraction after
# intake, and those strings are then fed back through the egress path on the next
# AI call. Anything the rule does to a placeholder it does to real client data on
# the second pass.
#
# The property is idempotence: a second pass must be a no-op. That is stronger
# than a list of cells, and it is what the ATT&CK resolver depends on when it
# reverses the transformation to build an alias.

# Every cell runs the FULL pipeline with an org name and name hints. Without
# them `redact_org_name` -- pass 10, and the exact transformation the ATT&CK
# resolver's alias tier reverses -- never executes, so an axis whose stated
# motivation is `[CLIENT] SOC Platform` would not once produce a `[CLIENT]`.
# The first version of this axis made that mistake: it passed literal `[CLIENT]`
# strings through with the org rule switched off, and all nine cells would have
# stayed green if the org rule became non-idempotent tomorrow.
_ORG = "Northwind"
_HINTS = ("Dana Whitfield",)


def _clean_full(text: str) -> str:
    cleaned, _ = redact_for_ai(text, mode="strict", client_org_name=_ORG, name_hints=_HINTS)
    return cleaned


IDEMPOTENCE_CASES = [
    # Cells that actually redact on pass 1 -- these are the ones that can detect
    # a non-idempotent rule, because there is a placeholder for pass 2 to chew on.
    ("bare address placeholder", "1234 Main Street"),
    ("suite placeholder", "Suite 400"),
    ("both, one line", "1234 Main Street, Suite 200"),
    ("placeholder beside a live designator", "[ADDRESS] Suite 400"),
    ("email and address together", "reach us at ops@example.com, 1234 Main Street"),
    # The org rule, which is the whole reason this axis exists.
    ("org name alone", f"{_ORG} runs the SOC."),
    ("org name beside a designator", f"{_ORG} SOC Platform, Suite 400"),
    # Already-redacted input: a no-op by nature, which is the point -- it is the
    # literal string the Tech Debt extractor hands back. Labelled `no-op:` because
    # the guard below is right that it cannot detect non-idempotence on its own.
    ("no-op: org name already replaced", "[CLIENT] SOC Platform"),
    ("org name twice", f"{_ORG} and {_ORG} Federal"),
    # Name hints, the other pass that rewrites free text.
    ("name hint beside an address", "Dana Whitfield, 1234 Main Street"),
    # Pass-1 no-ops. Kept deliberately and labelled: they cannot detect
    # non-idempotence (nothing is replaced, so pass 2 sees the input), but they
    # do catch a widening that starts matching them on pass 2 only.
    ("no-op: designator before a placeholder", "Suite [ADDRESS]"),
    ("no-op: product names", "Flowmon and Unitrends are deployed."),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text"), IDEMPOTENCE_CASES, ids=[c[0] for c in IDEMPOTENCE_CASES]
)
def test_redaction_is_idempotent(shape: str, text: str) -> None:
    """A second pass over already-redacted text must change nothing.

    Asserts the fixed point rather than a literal expected string on purpose: the
    expected value for pass 2 is whatever pass 1 produced, so this cannot drift
    into the #72 shape of encoding the implementation's own answer. The file
    docstring's "never from what any pattern does" has this one exception, and it
    is an exception because a fixed point is a PROPERTY rather than an expected
    value -- stated here so the absolute above is not quietly false.
    """
    once = _clean_full(text)
    assert _clean_full(once) == once, f"{shape}: a second pass rewrote already-redacted text"


@pytest.mark.unit
def test_the_idempotence_cells_are_not_all_pass_one_no_ops() -> None:
    """Guards the axis against decaying into cells that cannot detect anything.

    A cell where `_clean_full(x) == x` proves nothing about idempotence: there is
    no placeholder for the second pass to act on. THREE such cells are kept on
    purpose and named `no-op:`; if a future edit makes the REST of them no-ops
    too, the axis silently stops testing its own property and this fails.

    The floor matters as much as the check. Without it the cheap way to satisfy
    this test is to relabel a cell `no-op:` rather than fix it, which is the
    guard rewarding the edit it exists to catch -- and an empty `redacting` would
    satisfy `assert not inert` vacuously.
    """
    redacting = [t for shape, t in IDEMPOTENCE_CASES if not shape.startswith("no-op:")]
    assert len(redacting) >= 9, (
        f"only {len(redacting)} cells still redact on pass 1; relabelling a cell "
        "`no-op:` is not a fix"
    )
    inert = [t for t in redacting if _clean_full(t) == t]
    assert not inert, f"cells claim to redact on pass 1 but do not: {inert}"


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
    # The pre-keyword branch redacts an ordinal + Floor wherever it appears, so
    # an ordinal-qualified compound noun goes with it. Narrower than the bare
    # number case (which is a residual LEAK above) and accepted in the safe
    # direction, but listed so the cost is visible rather than discovered.
    ("ordinal compound noun", "2nd floor plans were provided.", "[ADDRESS] plans were provided."),
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
    # (`One Federal Plaza`, `221B Baker Street`); see #138.
    ("two letters", "Suite AB"),
    ("two letters (2)", "Ste BB"),
    # A colon or comma between keyword and value is not in the separator class.
    # Pre-existing; unchanged by #130's fix.
    ("colon separator", "Suite: 400"),
    ("comma separator", "Suite, 400"),
    # Full-width numerals, and the real rule is narrower than "ASCII only" -- an
    # earlier draft of this comment said that and was wrong. Python's `\d` on a
    # str pattern IS Unicode-aware, so it matches U+FF10-FF19; the ASCII-only
    # TAIL is what fails, and then the trailing `\b` falls between two word
    # characters. So a single full-width digit redacts (`Suite ４` -> `[ADDRESS]`)
    # and so does a full-width digit followed by ASCII ones; only an all-
    # full-width run of two or more leaks.
    ("full-width digits", "Suite ４００"),
    # An intervening word between the keyword and the number. The separator class
    # holds no letters, so `No.` / `Number` defeat it. Pre-existing, and the
    # CAGE rule fails the same way for the same reason (see #137) -- the
    # shared shape is "a separator class with no letters in it".
    ("intervening No.", "Suite No. 4"),
    ("intervening Number", "Unit Number 12"),
    # An underscore is a word character, so the ASCII tail stops before it and
    # the trailing `\b` then fails. Comes from the same exported-spreadsheet
    # source class as the zero-separator forms above.
    ("underscore in the suffix", "Suite 400_B"),
    # A space between a letter designator and its number. Allowing branch 2 to
    # cross a space would match "the floor is 3 meters" -- an ordinary sentence.
    # The single-letter branch declines it too, by lookahead: matching just
    # "Suite B" left "201" behind under an output that read as redacted, and a
    # whole-string leak the table records beats half a string vanishing.
    ("letter, space, digits", "Suite B 201"),
    # No ordinal on the pre-keyword branch. Requiring it is what keeps "3 floor
    # plans" intact; the cost is this form, and `3 Floor Lane` is caught by the
    # street rule rather than this one.
    ("bare number before Floor", "3 Floor"),
    # A designator wrapped onto the next line, excluded deliberately so that
    # bulleted lists survive -- see the bullet test above.
    ("wrapped line", "Suite\n400"),
    # The STREET rule pays the same price for the same reason, and this cell is
    # the cost of the newline exclusion above rather than a pre-existing gap: on
    # main a wrapped address WAS redacted, because `\s+` crossed the line break.
    # Stated plainly because CLAUDE.md's over-match lesson applies in both
    # directions -- tightening a rule can remove coverage that was only ever
    # there by accident, and here it removes coverage that was real. The trade is
    # deliberate: a wrapped address is rare, and a merged bullet list corrupts
    # every AI input silently.
    #
    # Note it was never CLEAN coverage. `1600 Pennsylvania Avenue NW` redacts to
    # `[ADDRESS] NW` on one line too -- the trailing directional is outside the
    # pattern -- so the wrapped form produced a partial redaction that read as a
    # complete one. Tracked in #138 with the other street_pat gaps.
    ("wrapped street address", "1600 Pennsylvania\nAvenue NW"),
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
