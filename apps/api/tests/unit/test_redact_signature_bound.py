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
# The REDACT row is in test_redact_rules_matrix.py's _SIGNATURE_LEAKS. These pin
# what the fix must NOT start cutting: only an all-capitalised line has its
# ranks and suffixes left out of the word count.


@pytest.mark.parametrize(
    ("shape", "text"),
    [
        # A sentence ends the lookahead (B1), so the name line after it must
        # not be reached: the sentence has to stay a sentence.
        (
            "a sentence with an honorific",
            "Findings follow.\nBest\nDr. Smith approved the change.\nDana Whitfield\n",
        ),
        (
            "a capitalised sentence of five words",
            "Findings follow.\nBest\nThe Quarterly Board Review Concluded.\n",
        ),
    ],
)
@pytest.mark.parametrize("scope", ["to_end", "block"])
def test_prose_after_an_opener_is_still_not_cut(shape: str, text: str, scope: str) -> None:
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope=scope)
    assert "signature_block" not in counts, shape
    assert cleaned.endswith(text.splitlines()[-1] + "\n"), shape
