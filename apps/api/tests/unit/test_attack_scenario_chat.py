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


def test_a_bare_clause_after_an_addition_makes_the_span_not_understood() -> None:
    """An addition never shares its verb, and "add X and Y" may be ONE name
    cut at "and" (#824 review, B1): the whole span is quoted back, and
    neither part is proposed."""
    parsed = _parse("add XDR Suite and Patch Tool")
    assert parsed.added == []
    assert _reasons(parsed) == [("add XDR Suite and Patch Tool", "split_name")]


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


def test_a_bare_clause_after_a_swap_makes_the_span_not_understood() -> None:
    """ "swap X for Y and Z": Y may be cut from "Y and Z"; nothing proposed."""
    parsed = _parse("swap EDR Tool for XDR Suite and SIEM Tool")
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [("swap EDR Tool for XDR Suite and SIEM Tool", "split_name")]


def test_a_duplicate_is_not_understood_and_the_first_stands() -> None:
    parsed = _parse("remove EDR Tool and edr tool, add XDR Suite, add xdr suite")
    assert (parsed.removed, parsed.added) == (["EDR Tool"], ["XDR Suite"])
    assert _reasons(parsed) == [("edr tool", "duplicate"), ("add xdr suite", "duplicate")]


def test_matched_and_not_understood_clauses_are_kept_apart() -> None:
    parsed = _parse("retire EDR Tool; add SIEM Tool; remove Firewall Tool")
    assert parsed.removed == ["EDR Tool"]
    assert [n.reason for n in parsed.not_understood] == ["already_clients", "unknown_tool"]


# --- never a fragment of a name (#824 review, B1, B4, B7) ----------------------------


def test_a_cited_name_containing_and_is_held_whole() -> None:
    cited = ("Identity and Access Manager", "SIEM Tool")
    parsed = _parse("retire identity and access manager and SIEM Tool", cited=cited, client=cited)
    assert parsed.removed == ["Identity and Access Manager", "SIEM Tool"]
    assert parsed.not_understood == []


def test_a_cited_name_containing_a_comma_and_a_full_stop_is_held_whole() -> None:
    cited = ("Acme, Inc. EDR", "SIEM Tool")
    parsed = _parse("remove Acme, Inc. EDR, SIEM Tool", cited=cited, client=cited)
    assert parsed.removed == ["Acme, Inc. EDR", "SIEM Tool"]


def test_an_added_name_cut_at_a_full_stop_is_not_proposed() -> None:
    parsed = _parse("add Example Inc. Scanner")
    assert parsed.added == []
    assert _reasons(parsed) == [("add Example Inc. Scanner", "split_name")]


def test_an_added_name_cut_at_and_is_not_proposed() -> None:
    parsed = _parse("add Endpoint Detection and Response Suite")
    assert parsed.added == []
    assert [n.reason for n in parsed.not_understood] == ["split_name"]


def test_a_swap_with_two_possible_divisions_is_not_a_guess() -> None:
    """ "Defender Suite" and "Defender Suite for Endpoint" are both cited: the
    swap divides two ways, both passing, so nothing is proposed."""
    cited = ("Defender Suite", "Defender Suite for Endpoint")
    parsed = _parse("swap Defender Suite for Endpoint for XDR Suite", cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [
        ("swap Defender Suite for Endpoint for XDR Suite", "ambiguous_split")
    ]


def test_a_swap_with_one_passing_division_is_proposed() -> None:
    cited = ("Defender Suite for Endpoint",)
    parsed = _parse("swap Defender Suite for Endpoint for XDR Suite", cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == (["Defender Suite for Endpoint"], ["XDR Suite"])


def test_a_replace_whose_name_contains_with_divides_where_it_passes() -> None:
    cited = ("Tool with Extras",)
    parsed = _parse("replace Tool with Extras with XDR Suite", cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == (["Tool with Extras"], ["XDR Suite"])


def test_more_additions_than_a_what_if_takes_are_not_proposed() -> None:
    """B4: the chat never proposes an 11th added tool (the cap is 10)."""
    text = "; ".join(f"add Tool {chr(65 + i)}" for i in range(11))
    parsed = _parse(text)
    assert len(parsed.added) == 10
    assert _reasons(parsed) == [("add Tool K", "too_many")]


def test_a_failed_removal_shares_nothing() -> None:
    """B7: "retire Identity and Access Manager" with only "Access Manager"
    cited: "Identity" fails, and "Access Manager" is NOT read as a removal."""
    cited = ("Access Manager",)
    parsed = _parse("retire Identity and Access Manager", cited=cited, client=cited)
    assert parsed.removed == []
    assert _reasons(parsed) == [
        ("retire Identity", "unknown_tool"),
        ("Access Manager", "unrecognised"),
    ]


@pytest.mark.parametrize("text", ["", "   ", " , ; . ", "?"])
def test_text_with_no_clause_parses_to_nothing(text) -> None:
    parsed = _parse(text)
    assert (parsed.removed, parsed.added, parsed.not_understood) == ([], [], [])


# --- #824 narrow review: B1's remaining shapes ---------------------------------------


def test_a_swap_is_never_divided_where_another_division_failed() -> None:
    """Both "Defender Suite" and "Defender Suite for Endpoint" are cited, so
    the swap divides two ways. Only one division's ADDED half passes, but
    that is not evidence it is the division meant: nothing is proposed."""
    cited = ("Defender Suite", "Defender Suite for Endpoint", "SIEM Tool")
    parsed = _parse("swap Defender Suite for Endpoint for SIEM Tool", cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [
        ("swap Defender Suite for Endpoint for SIEM Tool", "ambiguous_split")
    ]


def test_a_swap_with_one_plausible_division_reports_that_divisions_own_failure() -> None:
    """Only "Defender Suite for Endpoint" is cited, so the swap divides one way,
    and the admin is told why THAT division fails (SIEM Tool is the client's)."""
    cited = ("Defender Suite for Endpoint", "SIEM Tool")
    parsed = _parse("swap Defender Suite for Endpoint for SIEM Tool", cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == ([], [])
    assert [(n.reason, n.name) for n in parsed.not_understood] == [("already_clients", "SIEM Tool")]


def test_a_swap_is_not_divided_where_the_other_division_is_a_duplicate() -> None:
    """The reviewer's second row: division 2's removal repeats the one before
    it, which is no reason to take division 1."""
    cited = ("Defender Suite", "Defender Suite for Endpoint")
    parsed = _parse(
        "retire Defender Suite for Endpoint; swap Defender Suite for Endpoint for XDR Suite",
        cited=cited,
        client=cited,
    )
    assert (parsed.removed, parsed.added) == (["Defender Suite for Endpoint"], [])
    assert _reasons(parsed) == [
        ("swap Defender Suite for Endpoint for XDR Suite", "ambiguous_split")
    ]


def test_a_swap_that_divides_one_way_names_why_its_removal_fails() -> None:
    """One "for", so one division: its removal names no cited tool, and the
    admin is told that, rather than that the form was not recognised."""
    parsed = _parse("swap Firewall Tool for XDR Suite")
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [("swap Firewall Tool for XDR Suite", "unknown_tool")]


def test_overlapping_cited_names_are_not_chosen_between() -> None:
    """ "Identity and Access" and "Identity and Access Manager" both claim the
    words: neither the longer nor the earlier is preferred."""
    cited = ("Identity and Access", "Identity and Access Manager", "SIEM Tool")
    parsed = _parse(
        "retire Identity and Access Manager; remove SIEM Tool", cited=cited, client=cited
    )
    assert parsed.removed == ["SIEM Tool"]
    assert _reasons(parsed) == [("retire Identity and Access Manager", "ambiguous_tool")]


def test_a_removal_list_never_prefers_the_longer_held_name() -> None:
    """The reviewer's row: "Access Manager and Audit Log" is cited, and so are
    "Access Manager" and "Audit Log". The list is not read as the one tool."""
    cited = ("EDR Tool", "Access Manager", "Audit Log", "Access Manager and Audit Log")
    parsed = _parse("retire EDR Tool and Access Manager and Audit Log", cited=cited, client=cited)
    assert parsed.removed == ["EDR Tool"]
    assert _reasons(parsed) == [("Access Manager and Audit Log", "ambiguous_tool")]


def test_words_naming_one_cited_tool_and_several_are_not_a_guess() -> None:
    """ "Identity and Access Manager" is one cited tool, and also "Identity"
    and "Access Manager", two more: nothing is proposed."""
    cited = ("Identity and Access Manager", "Identity", "Access Manager")
    parsed = _parse("retire Identity and Access Manager", cited=cited, client=cited)
    assert parsed.removed == []
    assert _reasons(parsed) == [("retire Identity and Access Manager", "ambiguous_tool")]


@pytest.mark.parametrize(
    "text",
    [
        "remove " + chr(0) + "0" + chr(0),
        "retire Identity and Access Manager " + chr(0) + "1" + chr(0),
    ],
)
def test_a_typed_nul_is_text_like_any_other(text) -> None:
    cited = ("Identity and Access Manager", "SIEM Tool")
    parsed = _parse(text, cited=cited, client=cited)
    assert parsed.removed == []
    assert len(parsed.not_understood) == 1


# --- #824 narrow review at 02993287 -------------------------------------------------


def test_a_verb_matched_through_case_folding_still_divides() -> None:
    """F1: a long s matches "swap" case-insensitively, and the division must
    follow the verb that MATCHED, not a lowercased copy of the typed text."""
    parsed = _parse(chr(0x17F) + "wap EDR Tool for XDR Suite")
    assert (parsed.removed, parsed.added) == (["EDR Tool"], ["XDR Suite"])


def test_a_held_name_never_matches_inside_another_word() -> None:
    """F4: cited "R and D" is not held inside "HR and Dev Portal"."""
    cited = ("HR", "Dev Portal", "R and D")
    parsed = _parse("retire HR and Dev Portal", cited=cited, client=cited)
    assert parsed.removed == ["HR", "Dev Portal"]
    assert parsed.not_understood == []


@pytest.mark.parametrize(
    ("cited", "text"),
    [
        (("R and D",), "add HR and Dev Portal"),
        (("Detection and Response",), "add Extended Detection and Response Suite"),
    ],
)
def test_an_added_name_with_a_break_is_never_proposed_whatever_is_held(cited, text) -> None:
    """F4: whether an addition may carry a break is not decided by what the
    removal side holds. A cited name inside it leaves it a new name cut at a
    break, as it would be with nothing cited."""
    parsed = _parse(text, cited=cited, client=cited)
    assert parsed.added == []
    assert _reasons(parsed) == [(text, "split_name")]


def test_a_swap_whose_added_half_carries_a_break_is_not_proposed() -> None:
    cited = ("EDR Tool", "Detection and Response")
    parsed = _parse(
        "swap EDR Tool for Extended Detection and Response Suite", cited=cited, client=cited
    )
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [
        ("swap EDR Tool for Extended Detection and Response Suite", "split_name")
    ]


def test_the_shown_form_of_a_cited_name_is_held_too() -> None:
    """F3: the client's own name is shown as [CLIENT], and an admin can type
    that form; it is held like the stored one, so the list is not split into
    two other cited tools in silence."""
    cited = ("Acme SIEM and SOAR", "Acme SIEM", "SOAR")
    parsed = _parse("retire [CLIENT] SIEM and SOAR", cited=cited, client=cited)
    assert parsed.removed == []
    assert _reasons(parsed) == [("retire [CLIENT] SIEM and SOAR", "ambiguous_tool")]


def test_a_swap_with_several_cuts_and_none_plausible_is_unrecognised() -> None:
    parsed = _parse("swap Foo Tool for Bar Tool for Baz Tool")
    assert (parsed.removed, parsed.added) == ([], [])
    assert _reasons(parsed) == [("swap Foo Tool for Bar Tool for Baz Tool", "unrecognised")]


# --- #824 narrow review at 91118faa -------------------------------------------------


@pytest.mark.parametrize(
    ("cited", "text", "name"),
    [
        (
            ("Identity and Access Manager",),
            "add Identity and Access Manager",
            "Identity and Access Manager",
        ),
        (("Acme SIEM and SOAR",), "add [CLIENT] SIEM and SOAR", "[CLIENT] SIEM and SOAR"),
    ],
)
def test_adding_a_client_tool_whose_name_has_a_break_still_names_it(cited, text, name) -> None:
    """T1: the client's own tool is refused as theirs (B4) before a break in
    the name is reported, typed as stored or as shown. B4 names the spelling
    the admin typed, as the create route's refusal does."""
    parsed = _parse(text, cited=cited, client=cited)
    assert parsed.added == []
    assert [(n.reason, n.name) for n in parsed.not_understood] == [("already_clients", name)]


@pytest.mark.parametrize(
    ("cited", "text", "clause"),
    [
        (("Splunk", "Add Manager"), "retire Splunk and Add Manager", "Add Manager"),
        (("Splunk", "Cut Shield", "Shield"), "retire Splunk and Cut Shield", "Cut Shield"),
    ],
)
def test_a_cited_name_starting_with_a_verb_in_a_shared_list_is_not_a_guess(
    cited, text, clause
) -> None:
    """T2: after a removal, "Add Manager" is a cited tool AND an addition of
    "Manager"; "Cut Shield" is a cited tool AND a removal of "Shield". Neither
    reading is chosen."""
    parsed = _parse(text, cited=cited, client=cited)
    assert (parsed.removed, parsed.added) == (["Splunk"], [])
    assert _reasons(parsed) == [(clause, "ambiguous_tool")]
