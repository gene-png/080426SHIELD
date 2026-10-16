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
"block" (documents), which replaces each sign-off block alone and keeps going.

The expected values come from the inputs written here, not from the module.
"""

from __future__ import annotations

import sys

import pytest

from app.ai.redact import PLACEHOLDER_SIGNATURE, redact_for_ai

pytestmark = pytest.mark.unit

# Not a sign-off: an opener followed by a sentence, which the rule walks past.
_PAIR = "Best\nThe control is in place and tested.\n"


def _strip_calls(text: str, **kwargs) -> int:
    """How many times `str.strip` runs while `text` is redacted.

    Counted with the profiler's C-call events, so the measure is the work the
    rule does, not a wall clock that a loaded runner can stretch.
    """
    calls = 0

    def profile(_frame, event, arg) -> None:
        nonlocal calls
        if event == "c_call" and getattr(arg, "__name__", "") == "strip":
            calls += 1

    sys.setprofile(profile)
    try:
        redact_for_ai(text, mode="strict", **kwargs)
    finally:
        sys.setprofile(None)
    return calls


@pytest.mark.parametrize("scope", [None, "block"], ids=["default", "block"])
def test_the_signature_scan_is_linear_in_the_openers(scope: str | None) -> None:
    # The default is called with NO keyword, exactly as every existing caller
    # does, so this case measures the existing path.
    kwargs = {} if scope is None else {"signature_scope": scope}
    small = _strip_calls(_PAIR * 200, **kwargs)
    large = _strip_calls(_PAIR * 2000, **kwargs)
    # Ten times the input must cost about ten times the work. Quadratic work
    # costs a hundred times; the bound allows for the rest of the pipeline.
    assert small > 0, "the profiler saw no strip() call, so this measured nothing"
    assert large <= 15 * small, f"{small} strip() calls at 200 pairs, {large} at 2000"


def test_by_default_the_cut_still_runs_to_the_end() -> None:
    text = "Findings follow.\nRegards,\nDana Whitfield\nCISO\n\nAppendix A lists every host.\n"
    cleaned, counts = redact_for_ai(text, mode="strict")
    assert cleaned == f"Findings follow.\n{PLACEHOLDER_SIGNATURE}\n"
    assert counts["signature_block"] == 1


def test_a_document_keeps_what_follows_a_sign_off() -> None:
    text = (
        "Findings follow.\n"
        "Sincerely,\n"
        "Dana Whitfield\n"
        "CISO\n"
        "\n"
        "Appendix A lists every host that was scanned.\n"
    )
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == (
        f"Findings follow.\n{PLACEHOLDER_SIGNATURE}\n\nAppendix A lists every host that was scanned.\n"
    )
    assert counts["signature_block"] == 1


def test_a_document_with_two_letters_cuts_both_blocks() -> None:
    letter = "The scan is complete.\nRegards,\nDana Whitfield\nCISO\n\n"
    cleaned, counts = redact_for_ai(letter * 2, mode="strict", signature_scope="block")
    one = f"The scan is complete.\n{PLACEHOLDER_SIGNATURE}\n\n"
    assert cleaned == one * 2
    assert counts["signature_block"] == 2
    assert "Dana" not in cleaned and "CISO" not in cleaned


def test_a_block_ends_at_the_first_sentence() -> None:
    # The window stops at prose, so a sentence after the block survives even
    # inside the five-line lookahead.
    text = "Regards,\nDana Whitfield\nThe next section covers the firewall rules.\n"
    cleaned, _ = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == f"{PLACEHOLDER_SIGNATURE}\nThe next section covers the firewall rules.\n"


def test_an_inline_sign_off_in_a_document_cuts_its_line_and_its_block() -> None:
    text = "Thanks, Dana Whitfield\nCISO\n\nThe scan covered every host.\n"
    cleaned, _ = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == f"{PLACEHOLDER_SIGNATURE}\n\nThe scan covered every host.\n"


def test_an_unknown_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="signature_scope"):
        redact_for_ai("Regards,\nDana", mode="strict", signature_scope="most")


# --- parity on chat-sized inputs (D-100) -------------------------------------
#
# The bound may change only what a DOCUMENT keeps after a sign-off. On every
# input the signature tables were written for -- a sign-off that ends the field,
# and prose that must not be cut -- the block scope gives byte-identical output
# to the default. The rows come from the tables' own file, which predates this
# change; nothing here is derived from the code under test.
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


def test_a_second_sign_off_starts_its_own_block() -> None:
    # Two sign-offs back to back are two blocks, each counted: a block stops at
    # the next opener rather than swallowing it.
    text = "Regards,\nDana Whitfield\nThanks,\nAlex Morgan\n\nThe scan covered every host.\n"
    cleaned, counts = redact_for_ai(text, mode="strict", signature_scope="block")
    assert cleaned == (
        f"{PLACEHOLDER_SIGNATURE}\n{PLACEHOLDER_SIGNATURE}\n\nThe scan covered every host.\n"
    )
    assert counts["signature_block"] == 2


def test_an_unknown_scope_is_refused_even_with_redaction_off() -> None:
    with pytest.raises(ValueError, match="signature_scope"):
        redact_for_ai("Regards,\nDana", mode="off", signature_scope="most")
