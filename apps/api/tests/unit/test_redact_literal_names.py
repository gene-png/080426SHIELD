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
    assert "Acme" not in out and "ACME" not in out, out
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


# --- the decision this surfaces, pinned so it cannot pass silently -------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RESIDUAL BY DECISION (#535): names are joined with `_HSPACE+`, which "
        "excludes line breaks, so a legal name WRAPPED across a line still "
        "egresses. Whether literal names should use `\\s+` is the owner's call. "
        "strict=True: if this starts passing, the decision changed and this "
        "marker must go."
    ),
)
def test_a_name_wrapped_across_a_line_is_redacted() -> None:
    out, counts = redact_for_ai(
        "Report for Atlas\nDefense on Tuesday.", mode="strict", client_org_name="Atlas Defense"
    )
    assert "Atlas" not in out, out
    assert counts.get("client_org") == 1, counts
