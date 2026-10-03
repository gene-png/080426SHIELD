"""#802 slice C: the chat box's deterministic matcher (no AI).

Approved plan: #802, comment 5971765890; the advisor at 18:32Z. Every
expected value comes from the plan's form table, not from the code:

| remove / retire / drop / cut X              | X into `removed`               |
| add / introduce Y                            | Y into `added`                 |
| swap X for Y; replace X with Y               | X into `removed`, Y into `added` |

A removal must hit exactly ONE tool the base cites in the resolver's name
tiers; an addition must pass the create route's name check. Everything else
is quoted back as not understood, never guessed.
"""

from __future__ import annotations

import pytest

from app.ai.redact import redact_for_ai
from app.attack import scenario

pytestmark = pytest.mark.unit

CITED = ("EDR Tool", "SIEM Tool", "SOAR Tool")


def _parse(text, *, cited=CITED, client=CITED, org="Acme"):
    return scenario.parse_change(
        text,
        cited=cited,
        client_tools=client,
        client_org_name=org,
        redaction_mode="strict",
    )


def _reasons(parsed):
    return [(n.text, n.reason) for n in parsed.not_understood]


# --- each form ----------------------------------------------------------------------


@pytest.mark.parametrize("verb", ["remove", "retire", "drop", "cut", "Remove", "RETIRE"])
def test_each_removal_verb_puts_the_cited_tool_into_removed(verb) -> None:
    parsed = _parse(f"{verb} EDR Tool")
    assert (parsed.removed, parsed.added, parsed.not_understood) == (["EDR Tool"], [], [])


@pytest.mark.parametrize("verb", ["add", "introduce", "Add"])
def test_each_addition_verb_puts_the_new_tool_into_added(verb) -> None:
    parsed = _parse(f"{verb} XDR Suite")
    assert (parsed.removed, parsed.added, parsed.not_understood) == ([], ["XDR Suite"], [])


@pytest.mark.parametrize("text", ["swap EDR Tool for XDR Suite", "replace EDR Tool with XDR Suite"])
def test_a_swap_removes_the_first_and_adds_the_second(text) -> None:
    parsed = _parse(text)
    assert (parsed.removed, parsed.added) == (["EDR Tool"], ["XDR Suite"])


def test_a_swap_is_one_unit_if_either_half_fails_neither_is_proposed() -> None:
    """SIEM Tool is the client's: the swap is not understood, and EDR Tool is
    not proposed for removal on its own."""
    parsed = _parse("swap EDR Tool for SIEM Tool")
    assert (parsed.removed, parsed.added) == ([], [])
    assert [(n.reason, n.name) for n in parsed.not_understood] == [("already_clients", "SIEM Tool")]


def test_a_list_after_a_removal_verb_shares_it() -> None:
    """The plan's own example: "retire X and Y". Sharing is safe for a removal:
    each name must still hit exactly one cited tool."""
    parsed = _parse("retire EDR Tool and SIEM Tool")
    assert parsed.removed == ["EDR Tool", "SIEM Tool"]


def test_a_bare_clause_after_an_addition_is_not_understood() -> None:
    """An addition is never shared: any words would make a "new tool", which
    is a guess. Each tool to add needs its own verb."""
    parsed = _parse("add XDR Suite and Patch Tool")
    assert parsed.added == ["XDR Suite"]
    assert _reasons(parsed) == [("Patch Tool", "unrecognised")]


def test_what_if_and_a_question_mark_are_ignored() -> None:
    parsed = _parse("What if we retire EDR Tool, SIEM Tool and add XDR Suite?")
    assert (parsed.removed, parsed.added, parsed.not_understood) == (
        ["EDR Tool", "SIEM Tool"],
        ["XDR Suite"],
        [],
    )


def test_clauses_split_on_semicolons_and_full_stops_but_not_inside_a_name() -> None:
    parsed = _parse("remove EDR Tool; add Tenable.io. drop SOAR Tool", client=(*CITED,))
    assert (parsed.removed, parsed.added) == (["EDR Tool", "SOAR Tool"], ["Tenable.io"])


# --- names: exact, or not understood ----------------------------------------------


def test_case_and_whitespace_still_name_the_cited_tool_under_its_cited_spelling() -> None:
    parsed = _parse("remove  edr   TOOL")
    assert parsed.removed == ["EDR Tool"]


def test_the_placeholder_twin_names_the_cited_tool() -> None:
    named = "Acme SOC Platform"
    shown, _ = redact_for_ai(named, mode="strict", client_org_name="Acme")
    assert shown != named  # the world
    parsed = _parse(f"remove {shown}", cited=(named,), client=(named,))
    assert parsed.removed == [named]


def test_an_inference_is_never_a_match() -> None:
    """ "EDR" is a word of "EDR Tool": an inference, not a name."""
    parsed = _parse("remove EDR")
    assert parsed.removed == []
    assert _reasons(parsed) == [("remove EDR", "unknown_tool")]


def test_two_cited_tools_one_name_is_ambiguous_not_a_guess() -> None:
    parsed = _parse("remove edr tool", cited=("EDR Tool", "EDR TOOL"))
    assert parsed.removed == []
    assert _reasons(parsed) == [("remove edr tool", "ambiguous_tool")]


def test_a_tool_the_base_does_not_cite_is_not_understood() -> None:
    parsed = _parse("remove Firewall Tool")
    assert _reasons(parsed) == [("remove Firewall Tool", "unknown_tool")]


def test_adding_a_client_tool_is_not_understood_as_the_clients() -> None:
    parsed = _parse("add SIEM Tool")
    assert parsed.added == []
    assert [(n.reason, n.name) for n in parsed.not_understood] == [("already_clients", "SIEM Tool")]


def test_adding_a_name_shown_as_a_client_tool_is_not_understood() -> None:
    parsed = _parse(
        "add Suite 200 Scanner", cited=("Suite 100 Scanner",), client=("Suite 100 Scanner",)
    )
    assert _reasons(parsed) == [("add Suite 200 Scanner", "indistinct")]


def test_a_clause_with_no_verb_and_nothing_to_share_is_not_understood() -> None:
    parsed = _parse("please make it better")
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [("please make it better", "unrecognised")]


def test_a_bare_clause_after_a_swap_is_not_understood() -> None:
    """Only a removal list shares its verb; "swap X for Y and Z" does not."""
    parsed = _parse("swap EDR Tool for XDR Suite and SIEM Tool")
    assert (parsed.removed, parsed.added) == (["EDR Tool"], ["XDR Suite"])
    assert _reasons(parsed) == [("SIEM Tool", "unrecognised")]


def test_a_duplicate_is_not_understood_and_the_first_stands() -> None:
    parsed = _parse("remove EDR Tool and edr tool, add XDR Suite, add xdr suite")
    assert (parsed.removed, parsed.added) == (["EDR Tool"], ["XDR Suite"])
    assert _reasons(parsed) == [("edr tool", "duplicate"), ("add xdr suite", "duplicate")]


def test_matched_and_not_understood_clauses_are_kept_apart() -> None:
    parsed = _parse("retire EDR Tool, add SIEM Tool, polish the dashboard")
    assert parsed.removed == ["EDR Tool"]
    assert [n.reason for n in parsed.not_understood] == ["already_clients", "unrecognised"]


@pytest.mark.parametrize("text", ["", "   ", " , ; . ", "?"])
def test_text_with_no_clause_parses_to_nothing(text) -> None:
    parsed = _parse(text)
    assert (parsed.removed, parsed.added, parsed.not_understood) == ([], [], [])
