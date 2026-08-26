"""PII redactor - the SECURITY BOUNDARY in front of every LLM call.

Master Spec §12 + §12.1. SHIELD v1 accepts the risk of egress to a
commercial LLM provider (Anthropic Claude by default); this module is
the primary compensating control. It is intentionally pure: no I/O, no
DB, no clock. It can be reviewed line-by-line in an OWASP audit.

Functions:
  redact_for_ai(text, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_text, removed_counts)
  redact_payload(obj, *, mode, client_org_name=None, name_hints=())
      -> (cleaned_obj, removed_counts)

THE UNIT INVARIANT ON `removed_counts`, stated because breaking it is silent
and shows up two layers away. **Every value is a count of REMOVALS, and one
removal is one.** The web sums the dict to render "N spans redacted" on the
pre-egress preview -- the screen whose entire purpose is telling a human what is
about to leave -- so a value measured in any other unit makes that aggregate
nonsense. `signature_block_chars` (how many characters the signature rule
deleted) was added here and then removed for exactly this reason: it is a
magnitude, not a count, and a magnitude belongs in a column of its own. The same
question was answered the same way once before, by deleting the counter rather
than shipping one that could not state its own scope.

`removed_counts` is a dict like `{"email": 3, "phone": 1, ...}`. It is
logged on the corresponding `llm_calls` audit row (`redacted_counts`).
Master Spec §11 also describes an `artifact_redactions.removed_items`
column; that table does not exist -- no model, no migration, no writer.
This docstring asserted it for months and is where docs/security.md
picked the claim up.
Counts only - no payload contents.

Modes:
  strict   - removes everything below.
  standard - removes everything EXCEPT addresses and the client's org name.
             Useful when the prompt explicitly needs the org context.
  off      - pass-through. Refused at startup on ANY environment other than
             `development` (config.assert_safe_for_runtime). It used to key on
             `is_production()` while `Environment` has three members, so a
             STAGING deployment booted with this module disabled and every
             llm_calls row recording an empty redacted_counts -- #142, fixed.
             This module accepts `off` so unit tests can compare "redacted vs
             raw" paths.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

RedactionMode = Literal["strict", "standard", "off"]

# ---------------------------------------------------------------------------
# Replacement placeholders
# ---------------------------------------------------------------------------

PLACEHOLDER_EMAIL = "[EMAIL]"
PLACEHOLDER_PHONE = "[PHONE]"
PLACEHOLDER_SSN = "[SSN]"
PLACEHOLDER_EIN = "[EIN]"
PLACEHOLDER_CAGE = "[CAGE]"
PLACEHOLDER_CONTRACT = "[CONTRACT]"
PLACEHOLDER_ADDRESS = "[ADDRESS]"
PLACEHOLDER_NAME = "[NAME]"
PLACEHOLDER_CLIENT = "[CLIENT]"
PLACEHOLDER_SIGNATURE = "[SIGNATURE_BLOCK]"

# ---------------------------------------------------------------------------
# Regexes. Compiled once at import. Designed to favor false-positives
# (over-redact) over false-negatives (leak), because this is a security
# boundary and we'd rather lose some fidelity than leak PII.
# ---------------------------------------------------------------------------

_RE_EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

# HORIZONTAL whitespace: everything `\s` matches EXCEPT the ten characters
# `str.splitlines()` treats as a line break. Every separator in the ADDRESS rule
# is built from it, so "the rule does not cross a line" is one definition in one
# place rather than a property each pattern re-asserts.
#
# Every separator in the module is now built from it -- the address rules, the
# phone rule, and (as a superset) the CAGE class. An earlier version of this note
# said `_RE_PHONE` and `_RE_CAGE` "still contain `\s` and still cross line
# breaks", which was true when written and false as of the item 10 rewrites, and
# it told the reader to grep `\s` to find them. A note that sends someone
# hunting a defect that is gone is the same shape as one that reassures about a
# defect that is not.
#
# WHY A SUBTRACTION AND NOT A LIST. The first version of this fix enumerated
# `[ \t\xa0]`, which reads as "space, tab, non-breaking space -- surely
# that is all of them". `\s` matches 19 horizontal characters, so that list
# silently dropped SIXTEEN of them: U+2000-U+200A (en, em, thin, hair and
# friends), U+202F narrow no-break, U+205F medium mathematical, U+3000
# ideographic, U+1680 ogham, and U+001F. That is a LEAK, not a residual, and it
# was invisible because the decision was framed as being about NEWLINES and
# nobody re-derived what else was in the class being replaced. Thin and
# narrow-no-break spaces are what PDF and Word extraction emit, which is exactly
# how client letterhead reaches this boundary.
#
# `[^\S\r\n]` -- the obvious idiom, and what the adversarial review of this
# fix suggested -- is also wrong: it still crosses `\v`, `\f`, `\x1c`-`\x1e`,
# `\x85`, U+2028 and U+2029, every one of which IS a line break. Subtract the
# whole vertical set instead, and let `\S` define the horizontal one.
_HSPACE = r"[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]"

# Phones. Two rewrites, and the second exists because the first LEAKED.
#
# The original was `\+?[\d][\d\s.\-()]{8,18}\d` -- a digit-density heuristic, not a
# phone shape. It ate IP-address pairs in Zero Trust findings and numeric bullet
# lists, and recorded a phone removal over text with no phone in it (#140).
#
# Replacing it with strict NANP 3-3-4 plus `+CC` fixed the over-match and
# introduced four under-matches, every one of which the old rule had caught and
# none of which any cell in the truth table could see, because PHONE_REDACT was
# seven rows all of one shape:
#
#   1-800-555-0199        trunk prefix; the lookbehind blocked every inner group
#   1.555.867.5309        same, dotted
#   020 7946 0958         UK national, 3-4-4 -- matches no NANP grouping
#   0800 123 4567         4-3-4
#   +44 (0)20 7946 0958   a single-digit `(0)` group
#   555\xa0123\xa04567     NBSP separators -- `[ .\-]` is ASCII-space only
#
# The last is the sharpest: `_HSPACE` exists in this file precisely because an
# enumerated whitespace class dropped sixteen characters and leaked (D-058), and
# the phone rewrite then re-made that exact mistake 190 lines above the fix.
#
# So the rule now models what a telephone number IS: an optional country or
# trunk prefix, then 2-5 GROUPS of 2-4 digits, 7-15 digits in total. Group size
# is what excludes the LEAVE class -- `Ports 30000 40000` is 5-5, a version is
# 1-1-1 -- and the two shapes group size cannot exclude get an explicit
# lookahead, because a dotted quad and an ISO date are the only two things in
# this corpus that group like a phone number and are not one.
_PHONE_SEP = r"(?:" + _HSPACE + r"|[.-])"
# A group may be parenthesised, and a parenthesised group may be followed by
# more digits without a separator -- "+44 (0)20 7946 0958".
_PHONE_GROUP = r"(?:\(\d{1,4}\)\d{0,4}|\d{1,4})"
_RE_PHONE = re.compile(
    # The match must START at a digit, a `+` or an opening paren. An earlier
    # draft allowed a leading optional separator, which let a match begin on
    # the SPACE before a dotted quad -- and both negative lookaheads below were
    # then evaluated against that space, matched nothing, and so blocked
    # nothing. `Segments 10.20.30.40` came back `Segments[PHONE]`.
    r"(?<![\d.\-/])"
    # An IPv4 address is four groups of 1-3 digits and NOTHING after. Without
    # the trailing guard this also blocked `1.555.867.5309`, a real dotted
    # trunk-prefixed phone number, because its first four groups parse as a
    # quad -- the exclusion written to protect the LEAVE set eating a REDACT
    # row.
    r"(?!\d{1,3}(?:\.\d{1,3}){3}(?!\d))"
    r"(?!\d{4}-\d{2}-\d{2})"
    r"(?:\+\d{1,3}" + _PHONE_SEP + r"?)?" + _PHONE_GROUP
    # At least one SEPARATED group. A bare digit run with no separator is an
    # identifier far more often than a phone number in this corpus
    # ("20240115", "120000"), so the separator is load-bearing, not cosmetic.
    + r"(?:" + _PHONE_SEP + _PHONE_GROUP + r"){1,4}"
    r"(?![\d\-/])"
)


def _phone_digit_count_ok(match: str) -> bool:
    """A phone number carries 7-15 digits (E.164 caps at 15).

    Applied after matching rather than inside the pattern: expressing "between 7
    and 15 digits, ignoring separators" as a regex needs a lookahead that has to
    re-scan the whole candidate, and this is both readable and cheap.
    """
    return 7 <= sum(ch.isdigit() for ch in match) <= 15


_RE_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_RE_EIN = re.compile(r"\b\d{2}-\d{7}\b")

# CAGE code. Rewritten twice; the second time because the first LEAKED.
#
# The original `\bCAGE[\s:#-]*([A-Z0-9]{5})\b` was wrong three ways (#137): a
# letterless separator class missed "CAGE Code 1ABC2", `*` matched empty so
# `CAGEFIGHT` became `[CAGE]`, and under IGNORECASE any five-letter word matched,
# so "CAGE codes are missing" was rewritten AND recorded.
#
# The first fix added `\bCAGE\b`, which stops `CAGEFIGHT` -- and also stopped
# `CAGE1ABC2`, because `1` is a word character so there is no boundary. That is
# the zero-separator form `_suite_branches` branch 1 exists specifically to
# catch, for the stated reason that OCR'd letterhead and exported spreadsheet
# cells arrive that way. Two rules in one file making opposite choices about the
# same input class, one of them silently.
#
# So the boundary is not the mechanism. The VALUE is: a real CAGE code is five
# alphanumerics containing at least one digit, and an English word is not. That
# alone rejects `CAGEFIGHT` and "CAGE codes", and it lets the glued form back in.
#
# The connector loop also handles the PLURAL ("CAGE codes are 1ABC2 and 3XYZ4"),
# which the first fix missed because `code\b` fails against `codes` -- two real
# codes egressing while three table rows asserted that shape was correctly left
# alone. And `No.` needs the dot INSIDE the separator class, or "CAGE No. 1ABC2"
# leaks: `no\.?\b` cannot match "no." (no boundary between `.` and a space).
_CAGE_SEP = r"[\s:#.,-]"
_RE_CAGE = re.compile(
    r"\bCAGE" r"(?:" + _CAGE_SEP + r"*(?:codes?|numbers?|nos?|is|are|and)\b)*" + _CAGE_SEP + r"*"
    # At least one digit in the five: this is what separates a code from a word,
    # and it is the whole mechanism. Real CAGE codes are issued with digits.
    r"(?=[A-Z0-9]{0,4}\d)" r"([A-Z0-9]{5})\b",
    re.IGNORECASE,
)

# Contract numbers: common govcon shapes include W91QUZ-23-C-0001,
# HQ0034-22-D-0007, FA8732-21-F-1234. The prefix mixes letters and
# digits (e.g. W91QUZ) so it's [A-Z0-9]{4,8}, not [A-Z]{2,6}.
_RE_CONTRACT = re.compile(
    r"\b[A-Z0-9]{4,8}-\d{2}-[A-Z]-\d{4,5}[A-Z]?\b",
    # IGNORECASE was missing, so `w91quz-23-c-0001` egressed whole with an empty
    # `removed_counts` (#136). The shape is distinctive enough that case adds no
    # false positives: a date has no `-[A-Z]-` and `CVE-2024-3400` has no second
    # dash group.
    re.IGNORECASE,
)

# Signature-block openers. ONE flat list again -- the comma mechanism an earlier
# draft used is gone, replaced by looking at the NEXT LINE.
#
# Why the comma failed as a discriminator. `best`, `thanks`, `cheers` and
# `regards` are all ordinary words, and PDF/DOCX extraction emits a hard line
# break at the wrap point, so "Best / practice per CISA ZTMM" arrives as a line
# reading exactly "Best" and the rest of the finding was deleted (#135).
# Requiring a trailing comma fixed that and created the opposite defect:
# a comma-less "Regards" sign-off is common, and what survives it is
#
#     John Smith / Director of Information Security / <org> / <email> /
#     <street> / Arlington VA 22209
#
# -- a named individual, their title, the city-state-ZIP line that no other rule
# matches, and, for a tenant with no org name registered, the organisation too.
# Measured, not assumed. The false-negative cost is far higher than the
# false-positive one, and the comma discriminates neither case well because it is
# punctuation the writer may simply not have typed.
#
# The following line discriminates both:
#
#     Regards / John Smith                    -> short, Title Case, no full stop
#     This section regards / the finding 4.2  -> lowercase continuation
#     Best / practice per CISA ZTMM.          -> ends in a full stop
#     Best / Finding 2 is critical.           -> ends in a full stop
#
# It keys on what actually differs between a sign-off and a wrapped word, so one
# axis replaces the whole comma mechanism rather than tuning it.
_SIGNATURE_OPENERS = (
    "sincerely",
    "regards",
    "best regards",
    "kind regards",
    "warm regards",
    "best",
    "thanks",
    "thank you",
    "cheers",
    "respectfully",
    "v/r",
)

# A signatory line: a person's name, or their title. Short, capitalised, and not
# a sentence. Accepted residual: a Title-Case fragment of wrapped prose that
# happens to carry no terminal punctuation ("Best" / "Practice Guide") is cut.
# Rare, and it errs toward removing rather than leaking.
_MAX_SIGNATORY_WORDS = 4
_MAX_SIGNATORY_CHARS = 60


# Contact-shaped lines. A real signature block's FIRST line is very often not a
# name at all -- it is a phone, an email, a `--` delimiter or a `Tel:` label --
# and the next-line name test rejected every one of those, so the block survived
# and leaked the name, title, org and ZIP that followed. That is the same list
# the comma mechanism was rejected for leaking; the replacement leaked it on a
# one-line reordering.
_RE_CONTACT_HINT = re.compile(
    r"@" r"|^\s*--+\s*$"
    # Built from `_HSPACE`, not a literal space. Flagged by
    # `check_separator_classes.py` on its first run -- the THIRD instance of
    # this shape in this file, written minutes after fixing the second. The
    # NBSP test that was supposed to cover it passed for the wrong reason: the
    # ZIP hint below fired, not this one.
    + r"|\d(?:" + _HSPACE + r"|[\d.()-]){5,}\d" + r"|\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b",
    re.MULTILINE,
)

_SIGNATURE_LOOKAHEAD_LINES = 5


def _looks_like_a_signatory(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_SIGNATORY_CHARS:
        return False
    if stripped[-1] in ".!?":
        return False
    # A person's name never contains a colon; a wrapped HEADING routinely does,
    # and security documents are full of them. Without this, "Best" wrapped above
    # "Practice: Enable MFA" classified the heading as a signatory and deleted the
    # rest of the field. The word cap alone caught only the LONGER headings
    # ("Practice: Enable MFA before the next assessment", 7 words), which is luck
    # rather than a rule -- four of five test headings were cut.
    if ":" in stripped:
        return False
    words = stripped.split()
    if not 1 <= len(words) <= _MAX_SIGNATORY_WORDS:
        return False
    return stripped[0].isupper()


def _count_replacements(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def _redact_signature_blocks(text: str) -> tuple[str, int, int]:
    """Strip everything from a signature opener line to end of input.

    Returns ``(cleaned, count, removed_chars)``. The third value exists because
    this rule DELETES an arbitrary suffix: `signature_block: 1` said only "it
    fired", which is not the question an audit row answers for a destructive
    rule. A four-line sign-off and two thirds of a truncated document produced
    identical ledger entries (#135).

    An opener only counts when the next NON-BLANK line looks like a signatory --
    see `_looks_like_a_signatory` and the note above the opener list. Blank lines
    are skipped, because "Regards," followed by a blank line and then a name is
    the ordinary shape of a real sign-off.
    """
    lines = text.splitlines(keepends=True)
    cut: int | None = None
    for idx, raw in enumerate(lines):
        if raw.strip().lower().rstrip(",.!") not in _SIGNATURE_OPENERS:
            continue
        following = [nxt for nxt in lines[idx + 1 :] if nxt.strip()]
        if not following:
            continue
        # Either the next line names a person, OR any of the next few lines is
        # contact-shaped. The second clause catches the real layouts -- phone
        # first, email first, `--` delimiter, `Tel:` label -- which the name
        # test alone rejects, leaking everything below them.
        if _looks_like_a_signatory(following[0]) or any(
            _RE_CONTACT_HINT.search(nxt.strip()) for nxt in following[:_SIGNATURE_LOOKAHEAD_LINES]
        ):
            cut = idx
            break
    if cut is None:
        return text, 0, 0
    head = "".join(lines[:cut])
    removed = len(text) - len(head)
    return head + PLACEHOLDER_SIGNATURE + "\n", 1, removed


_STREET_WORDS = (
    "Street",
    "St",
    "Avenue",
    "Ave",
    "Road",
    "Rd",
    "Drive",
    "Dr",
    "Lane",
    "Ln",
    "Boulevard",
    "Blvd",
    "Court",
    "Ct",
    "Way",
    "Highway",
    "Hwy",
    "Parkway",
    "Pkwy",
    "Plaza",
    "Square",
)


# The street rule's failure mode is worse than the suite rule's. Its leading
# `\d{1,6}` reaches BACKWARD over a line break and takes a number that belonged
# to the previous line -- "Servers reviewed: 5\nMain Street office is unstaffed."
# became "Servers reviewed: [ADDRESS] office is unstaffed.", losing the count and
# reading as an ordinary sentence afterwards. It was also the one sub-pattern
# still using `\s` after #130's first fix, while the truth table carried a
# comment claiming the guarantee held for all three.
#
# Cost of the change, named rather than discovered: an address wrapped across a
# line break now leaks. That coverage was real (unlike `Flat`'s, which existed
# only through the `\bFl` bug) but was never clean -- the trailing directional
# falls outside the pattern, so `1600 Pennsylvania\nAvenue NW` redacted to
# `[ADDRESS] NW` either way. Pinned as an accepted residual.
_STREET_SEP = _HSPACE

# Spelled-out designators ("Suite Twelve", "Apt Twenty-One"). Without these the
# digit rule below silently drops a whole class of real addresses.
_NUMWORD = (
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|first|second|third)"
)

# House number: digits with an optional letter (`221B`), or spelled out
# (`One Federal Plaza`). Both forms passed the old `\d{1,6}` and egressed whole.
_HOUSE_NUMBER = r"(?:\d{1,6}[A-Za-z]?|" + _NUMWORD + r")"

# A trailing quadrant. Without it `1600 Pennsylvania Avenue NW` redacted to
# `[ADDRESS] NW` -- a partial match that reads as a completed redaction, the
# shape D-058 refuses to accept elsewhere in this rule.
_DIRECTIONAL = r"(?:" + _STREET_SEP + r"+(?:N|S|E|W|NE|NW|SE|SW)\b)?"

_STREET_PAT = (
    r"\b"
    + _HOUSE_NUMBER
    + _STREET_SEP
    + r"+([A-Z][A-Za-z]+"
    + _STREET_SEP
    + r"+){1,4}(?:"
    + "|".join(_STREET_WORDS)
    + r")\b"
    + _DIRECTIONAL
)

# Unit/suite designators. The suffix decides, not the keyword: every keyword
# here is also an ordinary English word or the start of a product name, so the
# rule can only be as good as its answer to "is what follows designator-shaped".
#
# Split by whether the keyword is an ABBREVIATION, because only an abbreviation
# takes a trailing period. That distinction is load-bearing rather than tidy: a
# period-plus-space separator is also how a SENTENCE ends, so allowing it after
# a spelled-out word made the rule swallow the start of the next sentence --
# "covers this unit. 3 findings remain." -> "covers this [ADDRESS] findings
# remain." That is #130's own disease surviving the fix through the separator
# class instead of the boundary. "Ste." and "Apt." are abbreviations and take a
# period; "Unit" and "Floor" are words and do not.
_SUITE_KEY_ABBREV = r"(?:Ste|Apt|Fl)"
_SUITE_KEY_WORD = r"(?:Suite|Unit|Floor|PO" + _HSPACE + r"+Box|P\.O\." + _HSPACE + r"+Box)"

# Separators. Deliberately NOT `\s`: a newline lets the rule reach into the next
# line of a bulleted list and merge two items into one corrupted line
# ("- Business Unit\n- 3rd party risk tooling"). Client notes are full of
# bullets; a designator wrapped mid-line is rare and is a listed residual.
_SUITE_SEP = r"(?:" + _HSPACE + r"|[#\-])"
# Abbreviations only: the same class plus the abbreviating period.
_SUITE_SEP_ABBREV = r"(?:" + _HSPACE + r"|[.#\-])"


def _suite_branches(sep: str) -> str:
    """The five suffix shapes, parameterised by which separator class applies.

    Identical for abbreviated and spelled-out keywords except for the period --
    written once and called twice rather than copied, because a second copy of a
    security-boundary rule drifts (CLAUDE.md's parity lesson).
    """
    return (
        r"(?:"
        # 1. NO separator, and a digit immediately: "Suite400", "PO Box99",
        #    "Apt3B". Nobody types these, but OCR'd letterhead and exported
        #    spreadsheet cells arrive this way and reach here through Tech Debt
        #    extraction. Requiring a DIGIT (rather than any character, as before
        #    #130) is what stops the keyword eating the rest of "Suitecrm",
        #    "Unitrends", "Flowmon".
        r"\d[A-Za-z0-9\-]*"
        # 2. A separator, then a number that may carry a short letter prefix and
        #    an internal separator: "Suite 400", "Ste-400", "Suite B3",
        #    "Suite B-201", "Apt A-12". The letter prefix is capped at 3 and the
        #    internal separator cannot be a space -- both deliberate. Uncapped,
        #    it swallows "Adobe Creative Suite Enterprise 2024"; with a space
        #    allowed, "the floor is 3 meters" matches. Before this branch handled
        #    the letter-hyphen-digit form, "Suite B-201" produced
        #    "[ADDRESS]-201": the unit number survived while the output LOOKED
        #    redacted, which is the silent-success shape this module exists to
        #    avoid.
        r"|" + sep + r"+[A-Za-z]{0,3}[.\-]?\d[A-Za-z0-9\-]*"
        # 3. Spelled out, possibly multi-token: "Suite One Hundred Twenty".
        r"|" + sep + r"+" + _NUMWORD + r"(?:(?:" + _HSPACE + r"|-)" + _NUMWORD + r")*"
        # 4. Roman numerals, and this branch MUST stay case-scoped even though
        #    the pattern compiles IGNORECASE: lowercase i/v/x/l spell ordinary
        #    English words, so a case-blind branch redacts "Unit ill defined" --
        #    the #130 disease again. Verified by reverting `(?-i:` alone and
        #    watching that case go red; "Unit did not respond" is NOT evidence
        #    for this and an earlier draft of this comment wrongly claimed it
        #    was, because `d` is not in the class. C/D/M are left out for the
        #    same reason: they would add "did", "dim" and "mild" as collisions to
        #    buy roman numerals above 89, which no suite number needs.
        r"|" + sep + r"+(?-i:[IVXL]{1,6})"
        # 5. A single lettered designator: "Suite A", "Apt B". Deliberately one
        #    character: widening it to [A-Z]{1,3} to catch "Suite AB" also
        #    corrupts "Adobe Creative Suite CC" and "Sophos Security Suite XG",
        #    which is #130 reintroduced on another branch. "Suite AB" is an
        #    accepted residual -- see the truth table in
        #    tests/unit/test_redact_address_matrix.py.
        #
        #    The lookahead refuses when a number follows, because matching just
        #    the letter would leave it behind: "Suite B 201" became
        #    "[ADDRESS] 201", a partial match that READS as a completed
        #    redaction. Declining outright is the honest failure -- the whole
        #    string survives, which the truth table records as a leak, rather
        #    than half of it vanishing under an output that looks finished.
        r"|" + sep + r"+[A-Za-z0-9](?!" + sep + r"*\d)"
        r")\b"
    )


_SUITE_PAT = (
    r"\b"
    + _SUITE_KEY_ABBREV
    + _suite_branches(_SUITE_SEP_ABBREV)
    + r"|\b"
    + _SUITE_KEY_WORD
    + _suite_branches(_SUITE_SEP)
)

# The value can also PRECEDE the keyword, which the pre-#130 pattern never
# modelled. The shape has exactly one member: only Floor/Fl take a number in
# front -- nobody writes "200 Suite" or "4B Apt". This is NEW coverage closing a
# live leak, not coverage preserved through the fix: before #130, "2nd Floor"
# produced "2nd [ADDRESS]" (the `\bFl`-eats-`oor` bug firing, number left
# behind) and "3rd Fl" matched nothing at all.
#
# The ordinal suffix is REQUIRED, and the separator is not `\s`. Both are there
# because this branch is the one that reaches leftward into prose: with a bare
# number allowed, "We reviewed 3 floor plans." became "We reviewed [ADDRESS]
# plans." -- floor plans, floor switches and floor wardens are ordinary facility
# and network-assessment vocabulary. With `\s` it also crossed a newline
# ("the top 3\nfloor switches"), which is precisely the merge the separator class
# above is written to prevent. "3 Floor" with no ordinal is a listed residual;
# "3 Floor Lane" is caught by the street rule instead.
_PRE_KEYWORD_PAT = r"\b\d{1,4}(?:st|nd|rd|th)" + _HSPACE + r"+(?:Floor|Fl)\b"

# City / state / ZIP, as ONE grouping. The bare five-digit ZIP is deliberately
# NOT a unit of this rule: `20190` is a plausible annual cost in Tech Debt and a
# control count in CSF, and destroying one while recording a successful
# redaction is the more expensive error. `Reston VA 20190` is unambiguous in a
# way none of its parts are -- match the grouping, not the digits, which is the
# same lesson the phone rewrite paid for.
#
# RESIDUAL, with a firing condition rather than a permanent carve-out: non-US
# postcodes are not matched. The tenancy is US govcon, so a non-US postcode is
# overwhelmingly a vendor address in a capability list (`Sophos, Abingdon
# OX14 3YP`) rather than client PII. **That justification expires the first time
# a tenant with a non-US office is onboarded**, at which point this becomes a
# defect. See #138.
_CITY_STATE_ZIP = (
    # A determiner is not a city. Without this, "The VA 22209 figure is a
    # spend total." matched -- `The` fits `[A-Z][a-z]+` exactly as `Reston` does.
    r"\b(?!(?:The|This|That|These|Those|Our|Their|Its|An?)\b)"
    # The comma form is what people actually type.
    r"(?:[A-Z][a-z]+,?" + _STREET_SEP + r"+){1,3}"
    r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|"
    r"WV|WI|WY|DC)" + _STREET_SEP + r"+\d{5}(?:-\d{4})?\b"
)

# Facility designators (#139). A SEPARATE keyword group with a DIGIT-ONLY suffix
# rule, because these words are ordinary English in a way `Suite` and `Ste` are
# not. `Building a baseline`, `Room for improvement` and `Building 2 of the 5
# controls` all sit in real findings, and the single-letter and spelled-out
# branches that serve `Suite A` would eat every one of them.
#
# `Level` is deliberately EXCLUDED and recorded as a residual: "patch level 3",
# "log level 2" and "level of effort" are core vocabulary here, and a digit
# follows in exactly the cases that matter. The suffix cannot separate them; only
# surrounding-context logic could, and that is a different design.
# Facility designators, taken from USPS Publication 28 Appendix C2 -- the
# approved list of US secondary unit designators -- rather than from recall.
# That is the same move as the phone rewrite: a published enumeration turns
# "which ones did I think of" into a lookup, and it is what lets #139 claim the
# list is complete against a STANDARD instead of complete against memory.
#
# All 24 are accounted for in tests/unit/test_redact_address_matrix.py
# (PUB28_DESIGNATORS), one row each: covered / added here / excluded with a
# reason. The nine exclusions are ordinary English or technical vocabulary that
# takes a digit -- KEY, LOT, SIDE, REAR, FRNT, SPC, PH, LOWR, UPPR -- and would
# reproduce the `Room for` problem exactly.
#
# LEVEL is NOT on Pub 28 C2, which is the real reason it is excluded. "Patch
# level 3 is inseparable from a floor designator" invites the next person to
# attempt the separation and fail identically; "not a US designator per Pub 28
# C2" is the same scope call as the non-US postcode residual, with the same
# firing condition -- a tenant with non-US offices.
_FACILITY_KEY = (
    r"(?:Building|Bldg|Room|Rm|Mail\s+Stop|Stop|MS" r"|Dept|Ofc|Lbby|Bsmt|Trlr|Pier|Hngr|Slip)"
)
_FACILITY_PAT = (
    r"\b"
    + _FACILITY_KEY
    + r"\b"
    + _SUITE_SEP
    + r"*\d[A-Za-z0-9-]*\b"
    # A real designator is TERMINAL -- end of line, a comma, or another
    # capitalised address token. A count is followed by a lowercase noun or
    # preposition: "Building 2 of the 5 controls", "Slip 2 days behind",
    # "dept 5 findings".
    #
    # An earlier draft listed the continuation words instead (of, in, on, to,
    # the...). It missed "days" and "findings" -- both caught by the prose
    # fixtures here, not by review. A stopword list is an enumeration of what
    # you thought of; "not followed by a lowercase word" is the shape.
    + r"(?!"
    + _SUITE_SEP
    + r"+[a-z])"
)

_RE_ADDRESS = re.compile(
    f"{_STREET_PAT}|{_CITY_STATE_ZIP}|{_SUITE_PAT}|{_FACILITY_PAT}|{_PRE_KEYWORD_PAT}",
    re.IGNORECASE,
)


def _redact_addresses(text: str) -> tuple[str, int]:
    """Best-effort street-address redaction.

    Matches a leading digit run + street keyword, a unit/suite designator, or a
    number preceding "Floor"/"Fl". Heuristic by nature, so the decisions are
    pinned as a truth table in `tests/unit/test_redact_address_matrix.py` --
    including the cells that are knowingly wrong and accepted (D-058).

    This rule is NOT free to make over-eager. `redact_for_ai` is the single LLM
    egress path, so a keyword that over-matches corrupts every AI input across
    all five services, silently: the model receives plausible-looking text, no
    error is raised, and nothing surfaces it. That was #130.
    """
    count = _count_replacements(_RE_ADDRESS, text)
    if count == 0:
        return text, 0
    return _RE_ADDRESS.sub(PLACEHOLDER_ADDRESS, text), count


def redact_org_name(text: str, org_name: str) -> tuple[str, int]:
    """Replace the client's legal name (case-insensitive, whole-token).

    Public since #33 finding 5, when the ATT&CK citation resolver needed to know
    what a tool name looks like after redaction. That resolver now calls
    `redact_for_ai` instead — the whole pipeline rather than this one rule —
    because this rule is only one of the ten passes `redact_for_ai` runs in
    strict mode (eight in standard, where this rule and the address rule are
    skipped) and the others also rewrite tool
    names. The address rule was the egregious case and is fixed (#130); it still
    rewrites a keyword followed by a number, so the reason stands. Kept public:
    it is a coherent unit and is tested directly.
    """
    if not org_name.strip():
        return text, 0
    pat = re.compile(rf"\b{re.escape(org_name)}\b", re.IGNORECASE)
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_CLIENT, text), count


def _redact_names(text: str, name_hints: Iterable[str]) -> tuple[str, int]:
    """Replace exact-match names from `name_hints` (case-insensitive)."""
    hints = [h for h in name_hints if h and len(h) >= 2]
    if not hints:
        return text, 0
    pat = re.compile(
        r"\b(?:" + "|".join(re.escape(h) for h in hints) + r")\b",
        re.IGNORECASE,
    )
    count = _count_replacements(pat, text)
    if count == 0:
        return text, 0
    return pat.sub(PLACEHOLDER_NAME, text), count


def redact_for_ai(
    text: str,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[str, dict[str, int]]:
    """Redact PII from `text`. Returns the cleaned text + a counts dict.

    `mode="off"` returns the original text and an empty counts dict.
    Production refuses `off` via `Settings.assert_safe_for_runtime`.
    """
    counts: dict[str, int] = {}
    if mode == "off":
        return text, counts

    # Signature blocks first: they hide tail content from being redacted
    # twice when the block contains names + phones + emails.
    cleaned, c, removed_chars = _redact_signature_blocks(text)
    if c:
        counts["signature_block"] = c
        # NOT the character count. `removed_chars` is computed and deliberately
        # NOT put here -- see the unit invariant on `redact_for_ai`. It belongs
        # in a column of its own, which is #144's shape.
        del removed_chars

    for key, pat, placeholder in (
        ("email", _RE_EMAIL, PLACEHOLDER_EMAIL),
        ("ssn", _RE_SSN, PLACEHOLDER_SSN),
        ("ein", _RE_EIN, PLACEHOLDER_EIN),
        ("contract", _RE_CONTRACT, PLACEHOLDER_CONTRACT),
    ):
        c = _count_replacements(pat, cleaned)
        if c:
            cleaned = pat.sub(placeholder, cleaned)
            counts[key] = c

    # Phone runs on its own because the digit-count bound is applied to the
    # MATCH, not inside the pattern. A candidate that groups like a phone number
    # but carries fewer than 7 or more than 15 digits is left exactly as it was
    # -- and, critically, is NOT counted. `counts["phone"]` must equal the number
    # of substitutions actually made, or the ledger asserts removals that did not
    # happen, which is the audit half of #140.
    phone_hits = 0

    def _sub_phone(match: re.Match[str]) -> str:
        nonlocal phone_hits
        if not _phone_digit_count_ok(match.group(0)):
            return match.group(0)
        phone_hits += 1
        return PLACEHOLDER_PHONE

    cleaned = _RE_PHONE.sub(_sub_phone, cleaned)
    if phone_hits:
        counts["phone"] = phone_hits

    # CAGE: keep only the placeholder, not the introducer keyword.
    cage_count = _count_replacements(_RE_CAGE, cleaned)
    if cage_count:
        cleaned = _RE_CAGE.sub(PLACEHOLDER_CAGE, cleaned)
        counts["cage"] = cage_count

    # Name hints
    cleaned, c = _redact_names(cleaned, name_hints)
    if c:
        counts["name"] = c

    if mode == "strict":
        # Addresses + org name only in strict mode.
        cleaned, c = _redact_addresses(cleaned)
        if c:
            counts["address"] = c
        if client_org_name:
            cleaned, c = redact_org_name(cleaned, client_org_name)
            if c:
                counts["client_org"] = c

    return cleaned, counts


def redact_payload(
    obj: Any,
    *,
    mode: RedactionMode = "strict",
    client_org_name: str | None = None,
    name_hints: Iterable[str] = (),
) -> tuple[Any, dict[str, int]]:
    """Recursively redact strings inside an arbitrary JSON-shaped payload.

    Returns the cleaned object + a counts dict aggregated across every
    string encountered. dict keys are not redacted (they're typically
    field names like "email", which we want preserved).
    """
    totals: dict[str, int] = {}

    def _walk(node: Any) -> Any:
        if isinstance(node, str):
            cleaned, counts = redact_for_ai(
                node,
                mode=mode,
                client_org_name=client_org_name,
                name_hints=name_hints,
            )
            for key, value in counts.items():
                totals[key] = totals.get(key, 0) + value
            return cleaned
        if isinstance(node, Mapping):
            return {k: _walk(v) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return type(node)(_walk(v) for v in node)
        return node

    return _walk(obj), totals
