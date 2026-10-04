"""#802: the chat box's AI reading (`attack_scenario_intent`), the checks.

The plan is #802 comment 5981734020; the advisor approved it at 16:40Z
(comment 5982109105) with two conditions. Every expected value comes from the
plan's section 3 table and those conditions, not from the code:

| AI output        | check                                          | if it fails                     |
| each `remove`    | names exactly ONE cited tool (stored or shown) | unknown_tool / ambiguous_tool / duplicate |
| each `add`       | `validate_added`, the cap included             | already_clients / indistinct / duplicate / too_many / unrecognised |
| an `add` holding a redaction placeholder | refused first              | redacted_name                   |
| each `unclear`   | a case-insensitive substring of the description SENT (condition 1) | the whole answer is refused |
| the shape        | exactly remove / add / unclear, lists of strings | the whole answer is refused   |

The AI's answers below are written as the prompt asks for them.
"""

from __future__ import annotations

import pytest

from app.attack import scenario_intent

pytestmark = pytest.mark.unit

CITED = ("EDR Tool", "SIEM Tool", "Acme Portal")


def _read(data, *, sent="retire the edr thing", cited=CITED, client=CITED, org="Acme"):
    return scenario_intent.read(
        data,
        sent=sent,
        cited=cited,
        client_tools=client,
        client_org_name=org,
        redaction_mode="strict",
    )


def _answer(remove=(), add=(), unclear=()):
    return {"remove": list(remove), "add": list(add), "unclear": list(unclear)}


def _reasons(parsed):
    return [(n.text, n.reason) for n in parsed.not_understood]


# --- removals ---------------------------------------------------------------------


def test_a_removal_naming_a_cited_tool_is_proposed() -> None:
    parsed = _read(_answer(remove=["EDR Tool"]))
    assert (parsed.removed, parsed.added, parsed.not_understood) == (["EDR Tool"], [], [])


def test_a_removal_in_its_shown_form_is_the_stored_tool() -> None:
    """The AI sees "[CLIENT] Portal" for "Acme Portal" and copies it."""
    parsed = _read(_answer(remove=["[CLIENT] Portal"]))
    assert parsed.removed == ["Acme Portal"]


@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("EDR", "unknown_tool"),  # an inference is never a match
        ("Firewall Tool", "unknown_tool"),  # not cited
    ],
)
def test_a_removal_naming_no_cited_tool_is_not_understood(name, reason) -> None:
    parsed = _read(_answer(remove=[name]))
    assert parsed.removed == []
    assert _reasons(parsed) == [(name, reason)]


def test_a_removal_naming_two_cited_tools_is_not_a_guess() -> None:
    cited = ("EDR Tool", "edr  tool")
    parsed = _read(_answer(remove=["EDR Tool"]), cited=cited, client=cited)
    assert parsed.removed == []
    assert _reasons(parsed) == [("EDR Tool", "ambiguous_tool")]


def test_a_removal_listed_twice_is_proposed_once() -> None:
    parsed = _read(_answer(remove=["EDR Tool", "edr tool"]))
    assert parsed.removed == ["EDR Tool"]
    assert _reasons(parsed) == [("edr tool", "duplicate")]


# --- additions --------------------------------------------------------------------


def test_an_addition_that_passes_validation_is_proposed() -> None:
    parsed = _read(_answer(add=["XDR Suite"]))
    assert (parsed.removed, parsed.added, parsed.not_understood) == ([], ["XDR Suite"], [])


def test_an_addition_of_a_client_tool_names_it() -> None:
    parsed = _read(_answer(add=["SIEM Tool"]))
    assert parsed.added == []
    assert [(n.reason, n.name) for n in parsed.not_understood] == [("already_clients", "SIEM Tool")]


@pytest.mark.parametrize("name", ["[CLIENT] Gateway", "XDR for [NAME]", "[client] gateway"])
def test_an_addition_holding_a_redaction_placeholder_is_not_proposed(name) -> None:
    """A placeholder in a NEW name cannot be reversed: the AI never saw the
    name it stands for."""
    parsed = _read(_answer(add=[name]))
    assert parsed.added == []
    assert _reasons(parsed) == [(name, "redacted_name")]


def test_more_additions_than_a_what_if_takes_are_not_proposed() -> None:
    names = [f"Tool {chr(65 + i)}" for i in range(11)]
    parsed = _read(_answer(add=names))
    assert parsed.added == names[:10]
    assert _reasons(parsed) == [("Tool K", "too_many")]


# --- unclear: condition 1 (verbatim) and condition 2 (placeholders) ----------------


def test_an_unclear_phrase_is_quoted_back_as_the_description_has_it() -> None:
    """Case-insensitive, and rendered from the description SENT, so the screen
    shows the admin's own casing and never words the admin did not write."""
    parsed = _read(_answer(unclear=["THE EDR THING"]), sent="please retire the edr thing")
    assert _reasons(parsed) == [("the edr thing", "ai_unclear")]


def test_an_unclear_phrase_holding_a_placeholder_is_shown_as_sent() -> None:
    """Condition 2, the residual: the redactor returns no span mapping, so a
    phrase carrying "[CLIENT]" is shown with the placeholder, as sent."""
    parsed = _read(_answer(unclear=["[CLIENT] gateway"]), sent="drop the [CLIENT] gateway")
    assert _reasons(parsed) == [("[CLIENT] gateway", "ai_unclear")]


# --- shape: the whole answer is refused ---------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param(["EDR Tool"], id="not-an-object"),
        pytest.param({"remove": [], "add": []}, id="a-key-missing"),
        pytest.param({**_answer(), "notes": []}, id="an-extra-key"),
        pytest.param({**_answer(), "remove": "EDR Tool"}, id="a-string-not-a-list"),
        pytest.param({**_answer(), "add": [7]}, id="a-non-string-entry"),
        pytest.param(
            _answer(unclear=["something the admin never wrote"]), id="unclear-not-verbatim"
        ),
        pytest.param(_answer(unclear=["  "]), id="unclear-blank"),
    ],
)
def test_an_answer_out_of_shape_is_refused_whole(data) -> None:
    with pytest.raises(scenario_intent.IntentShapeError):
        _read(data)


def test_one_bad_quote_refuses_the_names_beside_it_too() -> None:
    """Condition 1: "the whole AI answer is refused", not the one entry."""
    with pytest.raises(scenario_intent.IntentShapeError):
        _read(_answer(remove=["EDR Tool"], unclear=["never typed"]))


# --- what the AI is sent ------------------------------------------------------------


def test_the_payload_is_the_description_and_the_cited_tools_only() -> None:
    assert scenario_intent.payload("retire EDR Tool", ["EDR Tool", "SIEM Tool"]) == {
        "description": "retire EDR Tool",
        "tools": ["EDR Tool", "SIEM Tool"],
    }


def test_the_description_sent_is_the_redacted_one() -> None:
    sent = scenario_intent.sent_description(
        "drop the Acme Portal",
        CITED,
        redaction_mode="strict",
        client_org_name="Acme",
    )
    assert "Acme" not in sent
    assert "[CLIENT]" in sent
