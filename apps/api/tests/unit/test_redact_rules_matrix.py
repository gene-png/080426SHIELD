"""Truth tables for the four NON-ADDRESS redaction rules (#135, #136, #137, #140).

WHY THIS FILE EXISTS. `test_redact_address_matrix.py` did this for the address
rule after #130, and D-058 records the method: enumerate the state space, decide
each cell from what the redactor SHOULD do, and only then change the pattern. The
other four rules never got one. Every one of them then turned out to be wrong in
BOTH directions at once, which is exactly what an unenumerated rule looks like:

  * `_RE_PHONE` redacts a pair of IP addresses and a numeric bullet list, and
    records a phone removal over text containing no phone number (#140).
  * `_RE_CAGE` misses `CAGE Code 1ABC2` (its own primary phrasing), matches an
    empty separator so `CAGEFIGHT` becomes `[CAGE]`, and rewrites the ordinary
    phrase "CAGE codes" (#137).
  * `_RE_CONTRACT` has no `IGNORECASE`, so a lowercased contract number egresses
    whole (#136).
  * `_redact_signature_blocks` cuts everything from a line reading `Best` to end
    of input and records it as a successful redaction (#135).

THREE VERDICTS, as in the address table:

  REDACT   - real PII. Must be removed. A miss here is a LEAK.
  LEAVE    - ordinary content. Must survive byte-for-byte. A hit here corrupts
             every AI input on the platform, silently.
  RESIDUAL - known-wrong and deliberately accepted, with the reason inline.

The LEAVE rows are the point. Each rule already had tests proving it redacts what
it should; none had a single test proving it leaves anything alone, which is how
four rules shipped over-matching. Real signal that must survive is drawn from
what this platform actually processes: IP addresses and CIDR blocks (Zero Trust
segmentation), technique IDs (ATT&CK), CVE identifiers, version strings, currency
columns (Tech Debt), and dates.
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai

PHONE = "[PHONE]"
CAGE = "[CAGE]"
CONTRACT = "[CONTRACT]"
SIG = "[SIGNATURE_BLOCK]"


def _clean(text: str) -> str:
    cleaned, _ = redact_for_ai(text, mode="strict")
    return cleaned


def _counts(text: str) -> dict:
    _, counts = redact_for_ai(text, mode="strict")
    return counts


# ---------------------------------------------------------------------------
# Phone - REDACT
# ---------------------------------------------------------------------------

PHONE_REDACT = [
    ("us with country code", "+1 (555) 123-4567", PHONE),
    ("us dashed", "555-123-4567", PHONE),
    ("us dotted", "555.123.4567", PHONE),
    ("us spaced", "555 123 4567", PHONE),
    # The opening paren was OUTSIDE the match, so this produced "([PHONE]" -- a
    # partial redaction that reads as a complete one. Found while building this
    # table; not in any filed issue.
    ("us parenthesised area code", "(202) 555-0173", PHONE),
    ("international", "+44 20 7946 0958", PHONE),
    # Every row below LEAKED under the first rewrite of this rule, and the
    # table could not see it: PHONE_REDACT was seven rows all of one grouping.
    # Tightening a rule that over-matched is exactly where under-match leaks
    # get introduced, so the REDACT half needs the same class enumeration the
    # LEAVE half got.
    ("trunk prefix, dashed", "Call 1-800-555-0199 now", "Call [PHONE] now"),
    ("trunk prefix, dotted", "1.555.867.5309", PHONE),
    ("uk national, no country code", "Tel 020 7946 0958", "Tel [PHONE]"),
    ("uk freephone 4-3-4", "0800 123 4567", PHONE),
    ("country code with trunk zero", "+44 (0)20 7946 0958", PHONE),
    # Non-ASCII separators. `_HSPACE` exists in this file because an enumerated
    # whitespace class dropped sixteen characters and leaked (D-058); the first
    # phone rewrite re-made that mistake 190 lines above the fix.
    ("non-breaking space separators", "Call 555\xa0123\xa04567 today.", "Call [PHONE] today."),
    ("thin space separators", "Call 555\u2009123\u20094567 today.", "Call [PHONE] today."),
    ("narrow no-break separators", "555\u202f123\u202f4567", PHONE),
    (
        "in a sentence",
        "Call the SOC on 555-123-4567 if it recurs.",
        "Call the SOC on [PHONE] if it recurs.",
    ),
    # MACHINE FORMATS -- no separators at all. Both leaked after the rewrite
    # and both were caught by the rule it replaced. Found by running the OLD
    # pattern (quoted in redact.py's own comment) and the new one over one
    # corpus and diffing the match sets -- the only method that finds what the
    # PREVIOUS author thought of and this one did not.
    #
    # The separator requirement is what excludes them, and it is load-bearing
    # for `build 20240115`, so the rule cannot simply drop it. A bare run is a
    # phone at EXACTLY 10 digits, or 11 led by a 1. Eight digits is a build id.
    ("machine format, bare NANP", "5551234567", PHONE),
    ("machine format, +1 and no separators", "+15551234567", PHONE),
    ("machine format, E.164 international", "+442079460958", PHONE),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"), PHONE_REDACT, ids=[c[0] for c in PHONE_REDACT]
)
def test_phone_numbers_are_redacted(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"{shape}: a real phone number leaked"


# ---------------------------------------------------------------------------
# Phone - LEAVE. This is #140, and it is the class the rule never had.
# ---------------------------------------------------------------------------

PHONE_LEAVE = [
    # Zero Trust's entire subject matter is network segmentation.
    ("ip pair with a conjunction", "Segments 10.20.30.40 and 10.20.30.41 are isolated."),
    ("ip pair, space separated", "10.20.30.40 10.20.30.41"),
    ("single ip", "Host 192.168.1.100 is unmanaged."),
    ("cidr block", "The 10.20.0.0/16 range is flat."),
    ("ip in a list", "Scope: 10.0.0.1, 10.0.0.2, 10.0.0.3"),
    # A numeric bullet list collapsed to one token, and the audit row claimed a
    # phone number had been removed.
    ("numeric bullet list", "- 12\n- 34\n- 56\n- 78"),
    ("numbered findings", "1. 4 controls missing\n2. 9 controls partial"),
    # Things every service emits.
    ("attack technique ids", "Techniques T1078, T1110 and T1566 apply."),
    # B10. SUB-technique codes, which is how ATT&CK names most concrete
    # behaviours. `1003.001` is seven digits in two groups with one of
    # exactly three, so it passes both phone validators, and the parent
    # `T1003` does not -- which is why every row above passed while this
    # whole class was being destroyed. Caught by `test_risk_register`
    # going red on a set comparison, never by this table.
    ("attack sub-technique", "T1003.001"),
    ("attack sub-technique in prose", "T1547.001 persists via run keys."),
    ("attack sub-technique, list", "T1055.012 and T1027.002 both apply."),
    # The same shape without the ATT&CK prefix: any identifier glued to a
    # letter. A phone number is never preceded by one.
    ("build identifier", "Build v1234.567 shipped."),
    ("rule identifier", "Sigma rule R2001.004 fired."),
    ("cve identifiers", "CVE-2024-3400 and CVE-2023-4966 are unpatched."),
    ("version string", "Splunk Enterprise 9.1.2 build 20240115"),
    # B2 -- #140 REINTRODUCED. The rewrite that stopped the rule eating IP
    # pairs still eats any 3-5 short numbers totalling 7-15 digits on one
    # line. A port list is the most common numeric run in a Zero Trust or
    # ATT&CK finding, and the audit row records `phone: 1` over text with no
    # phone number in it -- the accounting lie #140 was filed for.
    ("port list", "Ports 22 80 443 3389 8080 are open."),
    ("port list, two entries", "Ports 8080 8443 are exposed."),
    # A US-format date is three dash-separated groups. The ISO guard covers
    # 2026-08-25; nothing covered this ordering.
    ("us date, dashed", "08-25-2026"),
    ("us date, slashed", "08/25/2026"),
    ("year sequence", "2024 2025 2026"),
    ("currency column", "Annual spend 120000 vs 95000"),
    ("iso date", "Assessed 2026-08-25, reassess 2027-02-01"),
    ("port range", "Ports 30000 40000 are open to the internet."),
    ("percentages and counts", "106 of 106 subcategories scored, 37 gaps at S4"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), PHONE_LEAVE, ids=[c[0] for c in PHONE_LEAVE])
def test_the_phone_rule_leaves_ordinary_numbers_alone(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: #140 corruption -- the phone rule ate real content"


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), PHONE_LEAVE, ids=[c[0] for c in PHONE_LEAVE])
def test_the_phone_rule_records_no_removal_it_did_not_make(shape: str, text: str) -> None:
    """The audit half of #140.

    `artifact_redactions.removed_items` and the `llm_calls` ledger both carry
    these counts. A `phone: 1` over text containing no phone number is a record
    asserting something the input never held -- CLAUDE.md's "a success record
    must be written where the success is", failing in the other direction.
    """
    assert "phone" not in _counts(text), f"{shape}: recorded a phone removal that did not happen"


# ---------------------------------------------------------------------------
# CAGE - REDACT, including the primary phrasing the rule missed
# ---------------------------------------------------------------------------

CAGE_REDACT = [
    ("bare keyword", "CAGE 1ABC2", CAGE),
    ("colon separator", "CAGE: 7XYZ9", CAGE),
    ("hash separator", "CAGE #1ABC2", CAGE),
    # #137's headline: the phrasing everybody actually writes.
    ("code, spaced", "CAGE Code 1ABC2", CAGE),
    ("code, colon", "CAGE Code: 1ABC2", CAGE),
    ("code, lowercase", "cage code 1abc2", CAGE),
    ("number word", "CAGE Number 1ABC2", CAGE),
    # All three LEAKED after the first CAGE rewrite. `CAGE1ABC2` regressed on
    # the `\b` that fix added -- the zero-separator form `_suite_branches`
    # branch 1 exists to catch, for the same OCR/spreadsheet reason.
    ("glued to the value", "CAGE1ABC2", CAGE),
    ("no. with a dot", "CAGE No. 1ABC2", CAGE),
    ("no without a dot", "CAGE No 1ABC2", CAGE),
    # The PLURAL connector: `code\b` fails against `codes`, so two real codes
    # egressed while three CAGE_LEAVE rows asserted that shape was fine.
    ("plural connector", "CAGE codes are 1ABC2", CAGE),
    ("in a sentence", "Our CAGE code is 1ABC2 for this contract.", "Our [CAGE] for this contract."),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"), CAGE_REDACT, ids=[c[0] for c in CAGE_REDACT]
)
def test_cage_codes_are_redacted(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"{shape}: a CAGE code leaked"


CAGE_LEAVE = [
    # The over-match half of #137: five letters after the keyword is an ordinary
    # word as often as it is a code, and "CAGE codes" is the phrase in the
    # issue's own title.
    ("plural noun", "CAGE codes are missing for 3 vendors."),
    ("plural noun mid-sentence", "The CAGE codes list is stale."),
    # The empty-separator half: #130's disease, still live in this rule.
    ("keyword glued to a word", "CAGEFIGHT"),
    ("keyword glued, longer", "CAGEBRIDGE"),
    ("prose about the concept", "Every vendor needs a CAGE code before award."),
    # B7 -- `and` is a connector and `T1078` is five alphanumerics containing
    # a digit, so the value test passes and an ATT&CK technique id is eaten.
    # ATT&CK ids sit beside vendor identifiers constantly. This is #130's
    # disease again, on the CAGE connector branch.
    ("cage beside an attack technique id", "CAGE and T1078"),
    ("cage beside a technique id in prose", "CAGE and T1078 both apply."),
    ("cage connector across a newline", "CAGE and\nT1078 applies."),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), CAGE_LEAVE, ids=[c[0] for c in CAGE_LEAVE])
def test_the_cage_rule_leaves_ordinary_prose_alone(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: #137 over-match -- the CAGE rule ate prose"


@pytest.mark.unit
def test_accepted_residual_only_the_first_code_in_a_list_is_caught() -> None:
    """A KNOWN leak, pinned rather than discovered.

    The rule anchors on the CAGE keyword, so a second code later in the same
    sentence has no keyword in front of it and survives. Accepted for now
    because the first code is the one that identifies the entity and the
    alternative -- matching bare five-character alphanumerics after a keyword
    has been seen -- would re-open the over-match this rule was just fixed for.
    """
    cleaned = _clean("CAGE codes are 1ABC2 and 3XYZ4")
    assert CAGE in cleaned
    assert "3XYZ4" in cleaned, "residual changed -- update the note and D-058"


# ---------------------------------------------------------------------------
# Contract numbers - REDACT regardless of case (#136)
# ---------------------------------------------------------------------------

CONTRACT_REDACT = [
    ("uppercase", "W91QUZ-23-C-0001", CONTRACT),
    ("lowercase", "w91quz-23-c-0001", CONTRACT),
    ("mixed case", "Fa8732-21-F-1234", CONTRACT),
    ("numeric prefix", "HQ0034-22-D-0007", CONTRACT),
    ("trailing letter", "FA8732-21-F-1234A", CONTRACT),
    (
        "in a sentence",
        "Awarded under w91quz-23-c-0001 last year.",
        "Awarded under [CONTRACT] last year.",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("shape", "text", "expected"), CONTRACT_REDACT, ids=[c[0] for c in CONTRACT_REDACT]
)
def test_contract_numbers_are_redacted_in_any_case(shape: str, text: str, expected: str) -> None:
    assert _clean(text) == expected, f"{shape}: #136 leak -- a contract number egressed whole"


CONTRACT_LEAVE = [
    ("cve", "CVE-2024-3400"),
    ("iso date range", "2026-08-25"),
    ("version", "9.1.2-rc-0001"),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), CONTRACT_LEAVE, ids=[c[0] for c in CONTRACT_LEAVE])
def test_the_contract_rule_leaves_similar_shapes_alone(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: contract rule over-matched"


# ---------------------------------------------------------------------------
# Signature blocks - REDACT (#135). The hardest of the four, because the cut is
# unbounded: everything from the opener to end of input disappears.
# ---------------------------------------------------------------------------

SIGNATURE_REDACT = [
    # B6 -- opener and signatory on ONE line. Every other cell in this table
    # puts the name on the NEXT line, so the rule was only ever built for
    # that shape and the table could not see the gap: the axis was written
    # from the rule's structure rather than from how sign-offs are typed.
    # Inline sign-offs are how short emails and ticket comments end, and
    # Tech Debt ingests both.
    ("inline thanks and name", "Findings follow.\nThanks, Dana Whitfield"),
    ("inline regards and name", "Findings follow.\nRegards, Dana Whitfield"),
    (
        "inline best, name and title",
        "Findings follow.\nBest, Dana Whitfield, CISO",
    ),
    ("regards with comma", "Findings follow.\nRegards,\nDana Whitfield\nCISO"),
    ("sincerely", "Findings follow.\nSincerely,\nDana Whitfield"),
    ("best regards", "Findings follow.\nBest regards,\nDana Whitfield"),
    ("kind regards", "Findings follow.\nKind regards\nDana Whitfield"),
    ("v/r", "Findings follow.\nV/R,\nDana Whitfield"),
    ("respectfully", "Findings follow.\nRespectfully,\nDana Whitfield"),
    ("thanks with comma", "Findings follow.\nThanks,\nDana Whitfield"),
    ("best with comma", "Findings follow.\nBest,\nDana Whitfield"),
    # NO COMMA. An earlier draft required one, which let all of these survive.
    # Measured, that is not "some sign-offs are missed": what survives is a named
    # individual, their job title, the city-state-ZIP line no other rule matches,
    # and -- for a tenant with no org name registered, which the resolver calls
    # the normal pending-intake state -- the organisation too.
    ("bare regards, no comma", "Findings follow.\nRegards\nDana Whitfield"),
    ("bare best, no comma", "Findings follow.\nBest\nDana Whitfield"),
    ("bare thanks, no comma", "Findings follow.\nThanks\nDana Whitfield"),
    ("blank line before signatory", "Findings follow.\nRegards,\n\nDana Whitfield\nCISO"),
    ("title on the next line", "Findings follow.\nRegards\nDirector of Information Security"),
    # REAL LAYOUTS. Every one of these leaked under the next-line-name test: the
    # first line of a signature block is very often contact detail rather than a
    # name, the name test rejected it, and the block survived -- leaking the name,
    # the title, the org (for a tenant with none registered) and the ZIP line.
    # Exactly the list the comma mechanism was rejected for leaking, re-leaked by
    # its replacement on a one-line reordering.
    (
        "phone first",
        "Findings follow.\nRegards,\n+1 555 867 5309\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
    (
        "email first",
        "Findings follow.\nRegards,\ndana.whitfield@atlas.gov\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
    (
        "rfc3676 delimiter",
        "Findings follow.\nRegards,\n--\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
    (
        "labelled phone",
        "Findings follow.\nRegards,\nTel: 555-123-4567\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
    (
        "rank and initials",
        "Findings follow.\nRegards,\nLt. Col. Dana M. Whitfield\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
    (
        "name with suffix",
        "Findings follow.\nRegards,\nJohn Smith Jr.\nDana Whitfield\nCISO, Atlas Defense Solutions\n1600 Wilson Blvd\nArlington VA 22209",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), SIGNATURE_REDACT, ids=[c[0] for c in SIGNATURE_REDACT])
def test_signature_blocks_are_cut(shape: str, text: str) -> None:
    cleaned = _clean(text)
    assert SIG in cleaned, f"{shape}: a signature block survived"
    assert "Dana Whitfield" not in cleaned, f"{shape}: the signatory's name leaked"


# ---------------------------------------------------------------------------
# Signature blocks - LEAVE. This is #135, and it is data LOSS rather than a leak:
# the model receives a truncated document and the run reports success.
# ---------------------------------------------------------------------------

SIGNATURE_LEAVE = [
    # The realistic trigger. PDF and DOCX extraction emits a hard line break at
    # the wrap point, so "Best / practice" arrives as a line reading exactly
    # "Best" -- and Tech Debt's whole pipeline is uploaded documents.
    ("wrapped best practice", "MFA on all admin accounts.\nBest\npractice per CISA ZTMM."),
    # B1 -- #135 REINTRODUCED, and the rows above could not see it. The rule
    # now cuts when ANY of the next five lines is contact-shaped, and the
    # contact hint fires on any IP address, any date, or any run of 7+
    # digits. Zero Trust findings are made of IP addresses; Tech Debt notes
    # are made of dates and dollar figures. So a wrapped `Best` or `Thanks`
    # anywhere within five lines of ordinary technical content deletes the
    # rest of the input, and the audit row records a successful redaction.
    #
    # Every cell above sits in text containing nothing contact-shaped, which
    # is why they pass and why the oracle reports them as pinning nothing.
    (
        "wrapped best, ip later in the finding",
        "Flat segmentation."
        + "\nBest"
        + "\npractice per CISA ZTMM."
        + "\nHost 10.20.30.40 bridges both.",
    ),
    (
        "wrapped thanks, date later",
        "Control review complete."
        + "\nThanks"
        + "\nto the SOC for the logs."
        + "\nNext review 2026-11-01.",
    ),
    (
        "wrapped best, spend figure later",
        "Licence consolidation is viable."
        + "\nBest"
        + "\ncase saves 18 percent."
        + "\nAnnual spend is 1250000 today.",
    ),
    (
        "wrapped regards, ip on the very next line",
        "Segment review." + "\nRegards" + "\n10.20.30.40 remains reachable.",
    ),
    ("wrapped thanks", "The SOC owes us logs.\nThanks\nare due to the IR team."),
    ("wrapped regards", "Controls were reviewed.\nRegards\nthis finding, see section 4."),
    ("bare best, more findings after", "Finding 1.\nBest\nFinding 2 is critical."),
    ("bare cheers mid-document", "Rollout went well.\nCheers\nNext steps below."),
    # Title Case on the following line is NOT sufficient -- a sentence ends in a
    # full stop and a signatory does not. This cell is what stops the next-line
    # axis from re-creating the over-match it replaced.
    ("title case sentence follows", "Finding 1.\nBest\nFinding 2 is critical."),
    ("long sentence follows", "Reviewed.\nRegards\nAll of the controls in scope were tested"),
    # Wrapped HEADINGS. Title Case, short, no terminal full stop -- they pass
    # every other part of the signatory test, and a name never contains a colon.
    # Four of these five were cut before the colon exclusion; only the longest
    # survived, on the word cap, which is luck rather than a rule.
    ("wrapped heading with colon", "Guidance follows.\nBest\nPractice: Enable MFA"),
    ("wrapped heading, finding", "Guidance follows.\nBest\nFinding: MFA missing"),
    ("wrapped heading, section", "Guidance follows.\nRegards\nSection 4: Scope"),
    ("wrapped heading, note", "Guidance follows.\nBest\nNote: see 4.2"),
    (
        "wrapped heading, long",
        "Guidance follows.\nBest\nPractice: Enable MFA before the next assessment",
    ),
    # Already safe today, kept so a widening cannot break them.
    ("thanks in a sentence", "Thanks to the SOC team for the logs.\nFinding 2 follows."),
    ("best in a sentence", "Best practice is MFA everywhere.\nFinding 3 follows."),
]


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), SIGNATURE_LEAVE, ids=[c[0] for c in SIGNATURE_LEAVE])
def test_the_signature_rule_does_not_truncate_ordinary_prose(shape: str, text: str) -> None:
    assert _clean(text) == text, f"{shape}: #135 data loss -- the rest of the input was deleted"


@pytest.mark.unit
@pytest.mark.parametrize(("shape", "text"), SIGNATURE_LEAVE, ids=[c[0] for c in SIGNATURE_LEAVE])
def test_no_signature_removal_is_recorded_for_ordinary_prose(shape: str, text: str) -> None:
    assert "signature_block" not in _counts(text), f"{shape}: recorded a cut that did not happen"


@pytest.mark.unit
def test_accepted_residual_title_case_fragment_is_cut() -> None:
    """A KNOWN over-cut, accepted and pinned.

    A wrapped prose fragment that is short, Title Case and carries no terminal
    punctuation is indistinguishable from a signatory by this axis. Accepted
    because it errs toward removing rather than leaking, and because the
    alternative -- requiring a comma -- was measured to leak a name, a title, a
    ZIP line and an unregistered org name.
    """
    assert SIG in _clean("Guidance follows.\nBest\nPractice Guide")


@pytest.mark.unit
def test_every_value_in_removed_counts_is_a_count_of_removals() -> None:
    """The unit invariant, pinned.

    The web sums this dict to render "N spans redacted" on the pre-egress
    preview. A value in any other unit makes that aggregate nonsense two layers
    away from where it was added, silently. `signature_block_chars` was added and
    then removed for exactly this reason.

    THE ANTI-#72 CONSTRUCTION, built in rather than bolted on. The expected
    total is derived from the OUTPUT -- how many placeholders appear in the
    redacted text -- not restated from the dict under test. A test that read
    `counts["email"] == 2` would agree with the implementation by construction
    and could never fail; this one compares two independent artefacts of the same
    run, so a rule that miscounts breaks it even though nothing here names a
    number. That is the general technique: derive the expected value from a
    DIFFERENT product of the system than the one you are asserting about.
    """
    text = (
        "Contact ops@example.com or fallback@example.com.\n"
        "Call 555-123-4567.\n"
        "CAGE 1ABC2, contract W91QUZ-23-C-0001.\n"
        "Office at 1234 Main Street, Suite 200.\n"
        "Findings follow.\nRegards,\nDana Whitfield\nCISO"
    )
    cleaned, counts = redact_for_ai(text, mode="strict")

    placeholders = sum(
        cleaned.count(p)
        for p in ("[EMAIL]", "[PHONE]", "[CAGE]", "[CONTRACT]", "[ADDRESS]", "[SIGNATURE_BLOCK]")
    )
    assert placeholders > 0, "the fixture stopped exercising the rules"
    assert sum(counts.values()) == placeholders, (
        "a value in removed_counts is not a count of removals -- the pre-egress "
        f"preview would render the wrong total. counts={counts}, "
        f"placeholders in output={placeholders}"
    )
    assert all(
        isinstance(v, int) and 0 < v <= 50 for v in counts.values()
    ), f"a value is not a plausible removal count: {counts}"
