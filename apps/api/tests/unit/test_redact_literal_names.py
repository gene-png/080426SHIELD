"""The org-name and name-hint rules against the separators and edges the DATA brings.

#535 and #536, both measured live on `main` at `5783fae`, both tier-1. The
client's legal name reached the LLM provider verbatim with `counts == {}`, so
the `llm_calls` egress record said nothing was removed:

  * #535 -- `re.escape` turns the name's space into a literal U+0020, so a
    no-break space, a narrow no-break space or two spaces between the words
    never matched.
  * #536 -- the pattern was anchored `\\b...\\b`. A `\\b` after a final "." needs
    a word character next, so "Acme Holdings, Inc." -- most incorporated names --
    could never be redacted anywhere.

WHERE THE PARAMETERS COME FROM. The separator set is computed HERE, from the
language (`\\s` minus what `str.splitlines()` breaks on), and never imported from
`redact.py`. A sweep parametrised by `_HSPACE` would agree with `_HSPACE` by
construction (CLAUDE.md's rule on tests that supply their own expected value).

WHY EVERY ROW ASSERTS BOTH HALVES. The defect's signature was "name intact AND
count zero" -- an egress record that reads as success. A row that checked only
the text could pass over a count of zero, and one that checked only the count
could pass over a partial miss (#535's "X and X-with-NBSP" row: count 1, one
occurrence leaked).
"""

from __future__ import annotations

import re
import sys

import pytest

from app.ai.redact import redact_for_ai

# CI runs `pytest -m unit`. Without this mark every test in this file was
# DESELECTED there -- found by review of 4f042f3, after local runs that named
# the file directly had passed.
pytestmark = pytest.mark.unit

# Every character `\s` matches that is NOT a line break by `str.splitlines()`.
HORIZONTAL = [
    ch
    for ch in map(chr, range(sys.maxunicode + 1))
    if re.match(r"\s", ch) and len(("a" + ch + "b").splitlines()) == 1
]
SEPARATORS = [*HORIZONTAL, "  "]


def _ids(seps: list[str]) -> list[str]:
    return ["+".join(f"U+{ord(c):04X}" for c in s) for s in seps]


def test_the_separator_set_is_the_horizontal_half_of_backslash_s() -> None:
    # Pins the derivation, so a Python change that grows `\s` shows up here
    # rather than silently widening or narrowing every sweep below.
    assert len(HORIZONTAL) == 19  # test-integrity: pinned count of the language's own set
    assert " " in HORIZONTAL and "\u00a0" in HORIZONTAL and "\u202f" in HORIZONTAL
    assert "\n" not in HORIZONTAL and "\u2028" not in HORIZONTAL


# --- #535: the separator between the words of a stored name ----------------


@pytest.mark.parametrize("sep", SEPARATORS, ids=_ids(SEPARATORS))
def test_org_name_is_redacted_whatever_horizontal_space_separates_its_words(sep: str) -> None:
    out, counts = redact_for_ai(
        f"Report for Atlas{sep}Defense on Tuesday.",
        mode="strict",
        client_org_name="Atlas Defense",
    )
    assert "Atlas" not in out and "Defense" not in out, out
    assert counts.get("client_org") == 1, counts


@pytest.mark.parametrize("sep", SEPARATORS, ids=_ids(SEPARATORS))
def test_name_hint_is_redacted_whatever_horizontal_space_separates_its_words(sep: str) -> None:
    out, counts = redact_for_ai(
        f"Signed by Dana{sep}Whitfield today.",
        mode="strict",
        name_hints=["Dana Whitfield"],
    )
    assert "Whitfield" not in out, out
    assert counts.get("name") == 1, counts


def test_a_partial_miss_cannot_hide_behind_a_nonzero_count() -> None:
    out, counts = redact_for_ai(
        "Atlas Defense and Atlas\u00a0Defense", mode="strict", client_org_name="Atlas Defense"
    )
    assert "Atlas" not in out, out
    assert counts.get("client_org") == 2, counts


# --- #536: a name that starts or ends with a non-word character ------------

EDGE_CASES = [
    # (stored legal_name, text as it arrives)
    ("Acme Holdings, Inc.", "Acme Holdings, Inc. operates the SOC."),
    ("Acme Holdings, Inc.", "Prepared for Acme Holdings, Inc."),
    ("Acme Holdings, Inc.", "Acme Holdings, Inc., a defense contractor, runs Splunk."),
    ("Acme Corp.", "Signed for Acme Corp.; see attached."),
    ("(ACME) Labs", "Report: (ACME) Labs holds the contract."),
    # Both defects in one name: a trailing "." AND a no-break space.
    ("Acme Holdings, Inc.", "Acme\u00a0Holdings, Inc. operates the SOC."),
]


@pytest.mark.parametrize(("legal_name", "text"), EDGE_CASES)
def test_org_name_with_a_non_word_edge_is_redacted(legal_name: str, text: str) -> None:
    out, counts = redact_for_ai(text, mode="strict", client_org_name=legal_name)
    for token in re.findall(r"[A-Za-z]+", legal_name):
        # test-integrity: needles are every word of the STORED input name, not of the output
        assert token not in out, (token, out)
    assert counts.get("client_org") == 1, counts


def test_name_hint_with_a_non_word_edge_is_redacted() -> None:
    out, counts = redact_for_ai(
        "Signed, J. Smith Jr. today", mode="strict", name_hints=["J. Smith Jr."]
    )
    assert "Smith" not in out, out
    assert counts.get("name") == 1, counts


# --- what must NOT change -----------------------------------------------------


@pytest.mark.parametrize(
    ("legal_name", "text"),
    [("Acme Holdings", "Acme Holdings operates the SOC."), ("Widgets LLC", "Widgets LLC ships.")],
)
def test_a_plain_name_still_redacts(legal_name: str, text: str) -> None:
    out, counts = redact_for_ai(text, mode="strict", client_org_name=legal_name)
    assert legal_name not in out, out
    assert counts.get("client_org") == 1, counts


@pytest.mark.parametrize("text", ["Acmex is a product.", "xAcme is a product.", "Acme_ops ran it."])
def test_a_word_edged_name_still_needs_a_word_boundary(text: str) -> None:
    # The anchors became conditional, not absent: a name that begins and ends
    # with a word character must still not match inside a longer word.
    out, counts = redact_for_ai(text, mode="strict", client_org_name="Acme")
    assert out == text
    assert "client_org" not in counts, counts


# --- line breaks: literal names use `\s`, not `_HSPACE` (owner decision, D-088) -

LINE_BREAKS = [
    ch
    for ch in map(chr, range(sys.maxunicode + 1))
    if re.match(r"\s", ch) and len(("a" + ch + "b").splitlines()) == 2
]


def test_the_line_break_set_is_the_other_half_of_backslash_s() -> None:
    assert len(LINE_BREAKS) == 10  # test-integrity: pinned count of the language's own set
    assert "\n" in LINE_BREAKS and "\u2028" in LINE_BREAKS


@pytest.mark.parametrize("brk", LINE_BREAKS, ids=_ids(LINE_BREAKS))
def test_a_name_wrapped_across_a_line_is_redacted(brk: str) -> None:
    # A known literal from the tenant's own rows, so crossing a line cannot
    # join tokens that were never one name -- unlike the shape rules `_HSPACE`
    # guards. This was an xfail(strict) residual until the owner decided it.
    out, counts = redact_for_ai(
        f"Report for Atlas{brk}Defense on Tuesday.", mode="strict", client_org_name="Atlas Defense"
    )
    assert "Atlas" not in out and "Defense" not in out, out
    assert counts.get("client_org") == 1, counts


def test_a_hint_wrapped_across_a_line_is_redacted() -> None:
    out, counts = redact_for_ai(
        "Signed by Dana\r\nWhitfield today.", mode="strict", name_hints=["Dana Whitfield"]
    )
    assert "Whitfield" not in out, out
    assert counts.get("name") == 1, counts


# --- review of ab80a13: two partial-match regressions the fix introduced ------
#
# Both publish a SURNAME under an output that reads as a completed redaction,
# which is worse than no match. Main got both right; the new token-joined,
# conditionally-anchored patterns got both wrong until the name rule stopped
# depending on alternation order.


def test_a_padded_short_hint_cannot_publish_the_surname() -> None:
    # "Dana" + 12 spaces is 16 characters, LONGER than "Dana Whitfield" (14)
    # as stored, so a sort on stored length put it first DETERMINISTICALLY, and
    # its pattern (whitespace dropped) matched "Dana" alone. (With 10 spaces the
    # lengths tie and `set()` order decides, which varies by hash seed, so the
    # test passed or failed by process.)
    out, counts = redact_for_ai(
        "Signed by Dana Whitfield.",
        mode="strict",
        name_hints=["Dana" + " " * 12, "Dana Whitfield"],
    )
    assert "Whitfield" not in out and "Dana" not in out, out
    assert counts.get("name") == 1, counts


def test_a_punctuation_led_hint_cannot_split_a_longer_name() -> None:
    # "(Dana" has no leading anchor, so it matches at position 0, LEFT of where
    # "Dana Whitfield" can start. Python's alternation takes the leftmost match
    # before the longest, so longest-first ordering could not prevent it.
    out, counts = redact_for_ai(
        "(Dana Whitfield) signed.",
        mode="strict",
        name_hints=["Dana Whitfield", "(Dana"],
    )
    assert "Whitfield" not in out and "Dana" not in out, out
    assert counts.get("name") == 1, counts


@pytest.mark.parametrize(
    "hints",
    [
        ["Dana", "Dana Whitfield"],
        ["Dana Whitfield", "Dana"],
        ["Whitfield", "Dana", "Dana Whitfield"],
    ],
    ids=["short-first", "long-first", "three"],
)
def test_the_full_name_wins_whatever_order_the_hints_arrive_in(hints: list[str]) -> None:
    out, counts = redact_for_ai("Signed by Dana\u00a0Whitfield.", mode="strict", name_hints=hints)
    assert out == "Signed by [NAME].", out
    assert counts.get("name") == 1, counts


def test_a_hint_that_is_one_character_after_normalising_is_dropped() -> None:
    # " J" is two characters as stored and one after `_literal_pattern` drops
    # its whitespace. The length filter must see the normalised form, or every
    # standalone "J" in the payload becomes [NAME].
    text = "Plan J ships on Tuesday."
    out, counts = redact_for_ai(text, mode="strict", name_hints=[" J"])
    assert out == text
    assert "name" not in counts, counts


def test_chained_hints_redact_the_whole_run_not_one_winner() -> None:
    # Review of 4f042f3: choosing the longest span dropped the overlapping one
    # and published "Dana [NAME]". Overlapping spans are MERGED, so the run is
    # one removal and nothing of it survives.
    out, counts = redact_for_ai(
        "Signed by Dana Whitfield Jones today.",
        mode="strict",
        name_hints=["Dana Whitfield", "Whitfield Jones"],
    )
    assert out == "Signed by [NAME] today.", out
    assert counts.get("name") == 1, counts


def test_a_shorter_hint_in_an_earlier_anchor_group_cannot_beat_a_longer_one() -> None:
    # Hints are grouped by anchor shape so anchors can be hoisted. "(Acme." has
    # non-word characters at BOTH ends; "(Acme. Labs" ends with a word
    # character, so it is in a LATER group. One alternation across groups would
    # try the earlier group first and publish "Labs". Each group is scanned on
    # its own and the spans are merged. (The obvious pair, "Acme" and "Acme
    # Corp.", cannot fail this way: there the longer hint's group comes first.)
    out, counts = redact_for_ai(
        "Signed by (Acme. Labs today.", mode="strict", name_hints=["(Acme.", "(Acme. Labs"]
    )
    assert "Acme" not in out and "Labs" not in out, out
    assert counts.get("name") == 1, counts


@pytest.mark.parametrize(
    "text",
    ["Danae signed.", "Adana signed.", "Dana_ops signed."],
    ids=["suffix", "prefix", "underscore"],
)
def test_a_word_edged_hint_still_needs_a_word_boundary(text: str) -> None:
    # The hint path's twin of the org-name boundary test above. Its anchors are
    # hoisted into `_hint_patterns`, a different constructor, and review of
    # 3bf4237 found that deleting them turned nothing red: a hint "Dana" would
    # silently rewrite "Danae" in every AI input (the #130 class).
    out, counts = redact_for_ai(text, mode="strict", name_hints=["Dana"])
    assert out == text
    assert "name" not in counts, counts


# --- a needle with nothing to match (owner review of #542) -----------------------
#
# Unreachable through today's callers: `redact_org_name` returns early on a
# blank name, and `_redact_names` normalises and drops hints shorter than two
# characters. So these call the builders DIRECTLY, and say so: there is no
# client surface that reaches them, which is the point -- the only thing that
# stood between a blank needle and `tokens[0]` was a sentence in a docstring.
# The needles are built with chr() so no invisible character is typed.
_BLANK_NEEDLES = ["", " ", chr(0xA0), chr(0x202F), "\t\n", chr(0x3000) * 3]


@pytest.mark.parametrize("needle", _BLANK_NEEDLES, ids=repr)
@pytest.mark.parametrize("anchored", [True, False], ids=["anchored", "unanchored"])
def test_a_blank_needle_is_a_typed_error_not_an_index_error(needle: str, anchored: bool) -> None:
    from starlette.exceptions import HTTPException

    from app.ai.redact import BlankRedactionLiteralError, _literal_pattern

    with pytest.raises(BlankRedactionLiteralError) as caught:
        _literal_pattern(needle, anchored=anchored)
    err = caught.value
    # Typed under D-016: an HTTPException whose detail is {reason, message},
    # which the global handler renders as the typed envelope.
    assert isinstance(err, HTTPException)
    assert err.status_code == 500
    assert err.detail["reason"] == "redaction_blank_literal"
    assert "nothing was sent" in err.detail["message"]


@pytest.mark.parametrize("needle", _BLANK_NEEDLES, ids=repr)
def test_a_blank_needle_reaching_the_edge_check_is_the_same_typed_error(needle: str) -> None:
    # `_hint_patterns` calls `_literal_edges` directly, before any pattern is
    # built, so it needs the guard as much as `_literal_pattern` does.
    from app.ai.redact import BlankRedactionLiteralError, _literal_edges

    with pytest.raises(BlankRedactionLiteralError):
        _literal_edges(needle)
