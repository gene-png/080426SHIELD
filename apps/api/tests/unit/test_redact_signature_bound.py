"""The signature rule's cost is bounded, and a DOCUMENT's cut is bounded too.

#1108. For every sign-off opener that did not lead to a cut, the rule copied and
stripped EVERY remaining line to find the next five non-blank ones: O(openers x
lines). A document of "Best" / sentence pairs, the shape a long letter or a
meeting log takes, made that quadratic in the text's length, on the AI path.

And the cut ran from the sign-off to the END of the input. In a chat message the
sign-off is the end; in a document one "Sincerely," near the top removed
everything after it (#736 6128016421). The advisor's ruling (6128447366 item 2):
bound the cut for documents to its lookahead window. So `redact_for_ai` takes
`signature_scope`: "to_end" (the default, every existing caller, unchanged) and
"block" (documents), which replaces each sign-off and its lookahead window and
keeps the text past the window.

The expected values come from the inputs written here, not from the module.
"""

from __future__ import annotations

import sys

import pytest

from app.ai.redact import PLACEHOLDER_SIGNATURE, redact_for_ai

pytestmark = pytest.mark.unit

# Not a sign-off: an opener followed by a sentence, which the rule walks past.
_PAIR = "Best\nThe control is in place and tested.\n"
# A sign-off that IS cut, then prose, then blank lines: what a long document of
# letters looks like, and what exercises the block loop's repeated cuts and its
# walks past blank lines.
_LETTER = "Regards,\nDana Whitfield\n\n\n\nThe control is in place and tested.\n\n\n"

# Five lines of ordinary prose: some fall inside a window, the rest must survive.
_AFTER = "".join(f"Appendix line {n} lists every host that was scanned.\n" for n in range(5))


def _c_calls(text: str, **kwargs) -> int:
    """How many C-level calls run while `text` is redacted.

    Counted with the profiler's C-call events, so the measure is the work the
    pipeline does -- whatever builtins the scan uses, `strip` or `isspace` or a
    regex -- not a wall clock that a loaded runner can stretch.
    """
    calls = 0

    def profile(_frame, event, _arg) -> None:
        nonlocal calls
        if event == "c_call":
            calls += 1

    sys.setprofile(profile)
    try:
        redact_for_ai(text, mode="strict", **kwargs)
    finally:
        sys.setprofile(None)
    return calls


@pytest.mark.parametrize(
    ("scope", "unit"),
    [(None, _PAIR), ("block", _PAIR), ("block", _LETTER)],
    ids=["default-no-cut", "block-no-cut", "block-cutting-every-unit"],
)
def test_the_signature_scan_is_linear(scope: str | None, unit: str) -> None:
    # The default is called with NO keyword, exactly as every existing caller
    # does, so that case measures the existing path. (The default cuts once, so
    # only the block scope can be given an input that cuts every unit.)
    kwargs = {} if scope is None else {"signature_scope": scope}
    small = _c_calls(unit * 200, **kwargs)
    large = _c_calls(unit * 2000, **kwargs)
    # Ten times the input must cost about ten times the work. Quadratic work
    # costs a hundred times; the bound allows for the rest of the pipeline.
    assert small > 0, "the profiler saw no C call, so this measured nothing"
    assert large <= 15 * small, f"{small} C calls at 200 units, {large} at 2000"


def test_the_block_case_really_cuts_every_letter() -> None:
    # Or the linearity case above would measure a scan that never cuts.
    _, counts = redact_for_ai(_LETTER * 3, mode="strict", signature_scope="block")
    assert counts["signature_block"] == 3


def test_by_default_the_cut_still_runs_to_the_end() -> None:
    text = "Findings follow.\nRegards,\nDana Whitfield\nCISO\n\n" + _AFTER
    cleaned, counts = redact_for_ai(text, mode="strict")
    assert cleaned == f"Findings follow.\n{PLACEHOLDER_SIGNATURE}\n"
    assert counts["signature_block"] == 1


def test_a_document_keeps_what_follows_the_window() -> None:
    # The window is the opener plus five non-blank lines: Dana, CISO and the
    # first three appendix lines. The last two appendix lines are past it.
    text = "Findings follow.\nSincerely,\nDana Whitfield\nCISO\n\n" + _AFTER
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == (
        f"Findings follow.\n{PLACEHOLDER_SIGNATURE}\n"
        "Appendix line 3 lists every host that was scanned.\n"
        "Appendix line 4 lists every host that was scanned.\n"
    )
    assert counts["signature_block"] == 1


@pytest.mark.parametrize(
    ("shape", "block"),
    [
        # A blank line between the name and the title (review of 3c82777d).
        (
            "blank line after the name",
            "Regards,\nDana Whitfield\n\nCISO\nAtlas Defense Solutions\n",
        ),
        ("inline, then a blank line", "Thanks, Dana Whitfield\n\nCISO, Atlas Defense Solutions\n"),
        # A title ending in an abbreviation, which reads as a sentence.
        (
            "title ending in an abbreviation",
            "Regards,\nDana Whitfield\n"
            "Chief Information Security Officer, Atlas Defense Solutions Inc.\n"
            "Building 4\n",
        ),
    ],
)
def test_nothing_of_a_signature_inside_the_window_survives(shape: str, block: str) -> None:
    cleaned, counts = redact_for_ai(block + "\n" + _AFTER, mode="strict", signature_scope="block")
    assert counts["signature_block"] == 1, shape
    for leaked in ("Dana", "Whitfield", "CISO", "Atlas", "Officer", "Building"):
        assert leaked not in cleaned, f"{shape}: {leaked!r} survived"


def test_a_document_with_two_letters_cuts_both_blocks() -> None:
    letter = "Regards,\nDana Whitfield\nCISO\n\n" + _AFTER
    cleaned, counts = redact_for_ai(letter * 2, mode="strict", signature_scope="block")
    one = (
        f"{PLACEHOLDER_SIGNATURE}\n"
        "Appendix line 3 lists every host that was scanned.\n"
        "Appendix line 4 lists every host that was scanned.\n"
    )
    assert cleaned == one * 2
    assert counts["signature_block"] == 2
    assert "Dana" not in cleaned and "CISO" not in cleaned


def test_an_inline_sign_off_in_a_document_cuts_its_line_and_its_window() -> None:
    text = "Thanks, Dana Whitfield\nCISO\n\n" + _AFTER
    cleaned, _ = redact_for_ai(text, mode="strict", signature_scope="block")
    assert (
        cleaned == f"{PLACEHOLDER_SIGNATURE}\nAppendix line 4 lists every host that was scanned.\n"
    )


def test_a_second_sign_off_starts_its_own_block() -> None:
    # Two sign-offs back to back are two blocks, each counted: a window stops at
    # the next opener rather than swallowing it.
    text = "Regards,\nDana Whitfield\nThanks,\nAlex Morgan\n\n" + _AFTER
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == (
        f"{PLACEHOLDER_SIGNATURE}\n{PLACEHOLDER_SIGNATURE}\n"
        "Appendix line 4 lists every host that was scanned.\n"
    )
    assert counts["signature_block"] == 2


def test_an_unknown_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="signature_scope"):
        redact_for_ai("Regards,\nDana", mode="strict", signature_scope="most")


def test_an_unknown_scope_is_refused_even_with_redaction_off() -> None:
    with pytest.raises(ValueError, match="signature_scope"):
        redact_for_ai("Regards,\nDana", mode="off", signature_scope="most")


# --- parity on chat-sized inputs (D-100) -------------------------------------
#
# The bound may change only what a DOCUMENT keeps after a sign-off. On every
# input the signature tables were written for -- a sign-off that ends the field,
# and prose that must not be cut -- the block scope gives byte-identical output
# to the default. The rows come from the tables' own file, which predates this
# change; nothing here is derived from the code under test. Every REDACT row's
# block fits its window and ends the field, so this pins the window on the
# shapes chat fields have; it cannot see a block longer than the window, which
# the tests above cover.
from tests.unit.test_redact_rules_matrix import (  # noqa: E402
    _SIGNATURE_LEAKS,
    SIGNATURE_LEAVE,
    SIGNATURE_REDACT,
)

_CHAT_ROWS = [(f"redact: {s}", t) for s, t in SIGNATURE_REDACT]
_CHAT_ROWS += [(f"leave: {s}", t) for s, t in SIGNATURE_LEAVE]
# As the matrix's own leak test builds them: the tail after a bare "Best,".
_CHAT_ROWS += [(f"leak: {s}", "Findings follow.\nBest,\n" + t) for s, t in _SIGNATURE_LEAKS]


@pytest.mark.parametrize(("shape", "text"), _CHAT_ROWS, ids=[r[0] for r in _CHAT_ROWS])
def test_on_chat_sized_inputs_the_block_scope_changes_nothing(shape: str, text: str) -> None:
    assert redact_for_ai(text, mode="strict", signature_scope="block") == redact_for_ai(
        text, mode="strict"
    ), shape


def test_a_bare_opener_that_starts_no_block_does_not_end_the_window() -> None:
    # "Thanks" here is followed by a title too long to be a signatory and with
    # no contact hint, so it starts no block of its own -- and must not end
    # Regards' window either, or the title survives (review of 578e42b6).
    text = (
        "Regards,\nDana Whitfield\nThanks\n"
        "Chief Information Security Officer, Atlas Defense Solutions\n\n" + _AFTER
    )
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope="block")
    assert counts["signature_block"] == 1
    for leaked in ("Chief", "Officer", "Atlas", "Defense", "Thanks"):
        assert leaked not in cleaned, f"{leaked!r} survived"
    # And no more than the window went: Dana, Thanks, the title and the first
    # two appendix lines are its five non-blank lines.
    assert "Appendix line 1 lists" not in cleaned
    for kept in ("Appendix line 2 lists", "Appendix line 3 lists", "Appendix line 4 lists"):
        assert kept in cleaned, f"{kept!r} was cut, past the window"


# --- #1256: a rank-and-name line ending in a full stop -----------------------
#
# The REDACT row for the issue's exact line is in test_redact_rules_matrix.py's
# _SIGNATURE_LEAKS. Here: the same shape with other suffixes, which must be cut
# too, and the sentences the fix must NOT start cutting -- Title-Case sentences
# whose last word is short and ends in a stop (review of 96b41f97: dropping
# every abbreviation-shaped token turned each into a "name" and cut the text
# after it).

_SUFFIXED_NAMES = [
    "Lt. Col. Dana M. Whitfield 3rd.",
    "Lt. Col. Dana M. Whitfield (Ret.).",
    # Four real words: counted the same by both tests only once `(Ret.).` is
    # an abbreviation to each of them (review of 8310931d).
    "Col. Dana Marie Whitfield, USAF (Ret.).",
]

_TITLE_CASE_SENTENCES = [
    "Phase Two Is Under Way.",
    "Section A. Overview Of Findings.",
    "U.S. Gov. Systems Are Affected.",
    "All Systems Are Now Up.",
    "Dr. Smith approved the change.",
    # Ends in a suffix WORD, but has lowercase words: a sentence (review of
    # 8310931d). Phase II, Tier III and Level IV are ordinary in findings.
    "Patching resumes in Phase II.",
    "Hosts move to Tier III next quarter.",
]


@pytest.mark.parametrize("name", _SUFFIXED_NAMES)
@pytest.mark.parametrize("scope", ["to_end", "block"])
def test_a_ranked_name_ending_in_a_suffix_is_cut(name: str, scope: str) -> None:
    cleaned, counts = redact_for_ai(
        "Findings follow.\nBest,\n" + name + "\n", mode="strict", signature_scope=scope
    )
    assert counts.get("signature_block") == 1, name
    assert "Whitfield" not in cleaned and "Dana" not in cleaned, name


@pytest.mark.parametrize("sentence", _TITLE_CASE_SENTENCES)
@pytest.mark.parametrize("scope", ["to_end", "block"])
def test_a_sentence_after_an_opener_still_ends_the_lookahead(sentence: str, scope: str) -> None:
    # The name line AFTER the sentence must not be reached (B1, #135): a
    # sentence ends the lookahead, so nothing is cut and the text survives.
    text = "Findings follow.\nBest\n" + sentence + "\nDana Whitfield\n"
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope=scope)
    assert "signature_block" not in counts, sentence
    # Other rules may rewrite words of it ("Way" reads as a street), but the
    # sign-off line and what follows it are not deleted.
    assert "\nBest\n" in cleaned and cleaned.endswith("Dana Whitfield\n"), sentence


# --- #1256: the line classes, as a TABLE written before the logic -----------
#
# CLAUDE.md: a predicate rewritten three times is a design problem, so the
# state space is written down first. Each row is a line that follows a bare
# opener ("Best,"), then a name line that only a scan reaching PAST it would
# find. "cut" means the signature rule fires on it (a name, removed); "keep"
# means it is a sentence: the lookahead stops there and nothing is cut.
_LINE_CLASSES = [
    # Names: rank or honorific, then a stopped last token.
    ("cut", "rank, suffix last", "Lt. Col. Dana M. Whitfield Jr."),
    ("cut", "rank, ordinal suffix last", "Lt. Col. Dana M. Whitfield 3rd."),
    ("cut", "rank, bracketed suffix and stop", "Lt. Col. Dana M. Whitfield (Ret.)."),
    ("cut", "four words, bracketed suffix and stop", "Col. Dana Marie Whitfield, USAF (Ret.)."),
    ("cut", "four words, bracketed suffix, no stop", "Col. Dana Marie Whitfield, USAF (Ret.)"),
    ("cut", "suffix before a comma, not last", "Lt. Col. Dana Whitfield Jr., USAF, CISO"),
    ("cut", "credential with inner stops last", "Dr. Dana M. Whitfield, M.D."),
    ("cut", "service abbreviation last", "Lt. Col. Dana M. Whitfield, USAF."),
    ("cut", "certification last", "Maj. Dana M. Whitfield, CISSP."),
    ("cut", "job title last", "Dr. Dana M. Whitfield, CISO."),
    # Sentences.
    ("keep", "Title-Case, short final word", "Phase Two Is Under Way."),
    ("keep", "Title-Case, abbreviation mid-line", "Section A. Overview Of Findings."),
    ("keep", "Title-Case, leading abbreviations", "U.S. Gov. Systems Are Affected."),
    ("keep", "Title-Case, two-letter final word", "All Systems Are Now Up."),
    ("keep", "honorific, sentence case", "Dr. Smith approved the change."),
    ("keep", "Roman numeral last, sentence case", "Patching resumes in Phase II."),
    ("keep", "Roman numeral mid-line, sentence case", "Hosts move to Tier III next quarter."),
    ("keep", "ordinal last, sentence case", "The patch window opens on the 3rd."),
    # Title-Case sentences ending in an acronym of three letters or fewer (or a
    # dotted one): a designation tail WITHOUT a comma before it (review of
    # db522400 -- each was cut there).
    ("keep", "Title-Case, short acronym last", "Enable MFA On Every VPN."),
    ("keep", "Title-Case, three-letter acronym last", "Escalate Findings To The SOC."),
    ("keep", "Title-Case, dotted acronym last", "Data Stays Inside The U.S."),
    ("keep", "Title-Case, abbreviations and acronym", "U.S. Gov. Systems Report To CISA."),
]
# Accepted residuals, recorded on #1256 rather than pinned either way:
#   - an all-Title-Case stopped line of four RAW words or fewer is not prose
#     ("Next Steps Below.", pre-existing);
#   - a name-shaped line with a name TAIL is counted without its
#     abbreviations, so an all-Title-Case sentence that ends in a suffix word
#     ("Hosts Move To Tier III.") or in a short designation after a comma
#     ("Report Issues To Support, IT.") reads as a name -- new with #1256, and
#     it errs toward removing;
#   - a name with a lowercase particle ("Dana van der Berg Jr.") is not
#     name-shaped, and one ending in a plain stopped surname after its ranks
#     ("Lt. Col. Dana M. Whitfield.") has no tail; both still read as sentences
#     (pre-existing);
#   - a name with a designation and NO comma before it ("Lt. Col. Dana M.
#     Whitfield USAF.", six raw words) has no tail and reads as a sentence: the
#     comma is the only thing telling it from "U.S. Gov. Systems Report To
#     CISA." (a leak, pre-existing on main; tracked on #1256).


@pytest.mark.parametrize(
    ("verdict", "shape", "line"), _LINE_CLASSES, ids=[c[1] for c in _LINE_CLASSES]
)
@pytest.mark.parametrize("scope", ["to_end", "block"])
def test_each_line_class_is_cut_or_kept(verdict: str, shape: str, line: str, scope: str) -> None:
    # A "cut" row is followed by a SENTENCE, so the cut can only come from the
    # row itself; a "keep" row by a NAME, which only a scan reaching past the
    # row would find.
    after = "The scan of every host is now complete." if verdict == "cut" else "Alex Morgan"
    text = "Findings follow.\nBest,\n" + line + "\n" + after + "\n"
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope=scope)
    if verdict == "cut":
        assert counts.get("signature_block") == 1, f"{shape}: not cut"
        assert "Whitfield" not in cleaned and "Dana" not in cleaned, f"{shape}: the name survived"
    else:
        assert "signature_block" not in counts, f"{shape}: a sentence was cut"
        assert cleaned.endswith("Alex Morgan\n"), f"{shape}: text after it was lost"
