"""#802 slice A: the what-if's code side, before any storage or route.

Removing tools from the frozen last-confirmed assessment re-assesses ONLY the
techniques those tools appear on, through a scoped AI call whose answer code
validates, and whose statuses code computes (R3's `computed.py`). These tests
pin the code side: which techniques are affected, which removals are real
tools, what of the AI's answer is accepted, and the comparison.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.attack import scenario

pytestmark = pytest.mark.unit


def _row(code: str, *, d=(), p=(), r=(), status="covered", citations=()):
    return SimpleNamespace(
        technique_code=code,
        status=status,
        reason_code=None,
        detection_tools=list(d),
        prevention_tools=list(p),
        response_tools=list(r),
        unconfirmed_citations=list(citations),
    )


BASE = [
    _row("T1003", d=["EDR Tool"], p=["EDR Tool"], r=["SOAR Tool"]),
    _row("T1059", d=["SIEM Tool"], status="partial"),
    _row("T1566", d=["Mail Gateway"], p=["Mail Gateway"], r=["EDR Tool"]),
]


# --- affected techniques ----------------------------------------------------


def test_the_affected_techniques_are_those_a_removed_tool_appears_on() -> None:
    assert scenario.affected_codes(BASE, ["EDR Tool"]) == ["T1003", "T1566"]


def test_a_removed_name_matches_case_folded_and_trimmed() -> None:
    assert scenario.affected_codes(BASE, ["  edr tool "]) == ["T1003", "T1566"]


def test_a_tool_on_no_row_affects_nothing() -> None:
    assert scenario.affected_codes(BASE, ["SIEM Tool"]) == ["T1059"]


# --- the change list --------------------------------------------------------


def test_removed_names_resolve_to_the_names_the_assessment_cites() -> None:
    assert scenario.resolve_removed(BASE, ["edr tool", "SIEM TOOL"]) == ["EDR Tool", "SIEM Tool"]


def test_a_removed_name_the_assessment_does_not_cite_is_refused_by_name() -> None:
    with pytest.raises(scenario.UnknownTool) as e:
        scenario.resolve_removed(BASE, ["EDR Tool", "Nothing Like It"])
    assert e.value.name == "Nothing Like It"


def test_an_empty_change_list_is_refused() -> None:
    with pytest.raises(scenario.EmptyChangeList):
        scenario.resolve_removed(BASE, [])


def test_a_duplicate_removal_counts_once() -> None:
    assert scenario.resolve_removed(BASE, ["EDR Tool", "edr tool"]) == ["EDR Tool"]


# --- the AI's answer: only what the change and the slice allow ---------------

AVAILABLE = ["SIEM Tool", "SOAR Tool", "Mail Gateway", "Backup Tool"]


def _ai(rows):
    return {"rows": rows}


def test_accepted_rows_become_the_affected_techniques_new_lists() -> None:
    parsed = scenario.parse_delta(
        _ai(
            [
                {
                    "technique_code": "T1003",
                    "tool": "siem tool",
                    "detection": True,
                    "prevention": False,
                    "response": False,
                    "rationale": "Logs credential access.",
                },
                {
                    "technique_code": "T1003",
                    "tool": "SOAR Tool",
                    "detection": False,
                    "prevention": False,
                    "response": True,
                    "rationale": "Runs the playbook.",
                },
            ]
        ),
        asked=["T1003", "T1566"],
        available=AVAILABLE,
    )
    assert parsed.lists["T1003"] == {
        "detection_tools": ["SIEM Tool"],
        "prevention_tools": [],
        "response_tools": ["SOAR Tool"],
    }
    # Asked about and answered with nothing: it provides nothing now.
    assert parsed.lists["T1566"] == {
        "detection_tools": [],
        "prevention_tools": [],
        "response_tools": [],
    }
    assert parsed.dropped == {}


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (
            {"technique_code": "T9999", "tool": "SIEM Tool", "detection": True},
            "technique_outside_slice",
        ),
        (
            {"technique_code": "T1003", "tool": "EDR Tool", "detection": True},
            "tool_outside_change",
        ),
        (
            {"technique_code": "T1003", "tool": "Unknown Tool", "detection": True},
            "tool_outside_change",
        ),
        (
            {"technique_code": "T1003", "tool": "SIEM Tool", "detection": "yes"},
            "not_boolean",
        ),
        (
            {"technique_code": "T1003", "tool": "SIEM Tool", "detection": 1},
            "not_boolean",
        ),
        ("not an object", "not_an_object"),
    ],
)
def test_anything_outside_the_contract_is_dropped_and_counted(row, reason) -> None:
    parsed = scenario.parse_delta(_ai([row]), asked=["T1003"], available=AVAILABLE)
    assert parsed.dropped == {reason: 1}
    assert parsed.lists["T1003"] == {
        "detection_tools": [],
        "prevention_tools": [],
        "response_tools": [],
    }


def test_a_missing_rows_list_is_a_shape_error_not_an_empty_answer() -> None:
    with pytest.raises(scenario.ScenarioShapeError):
        scenario.parse_delta({"rows": "none"}, asked=["T1003"], available=AVAILABLE)
    with pytest.raises(scenario.ScenarioShapeError):
        scenario.parse_delta({}, asked=["T1003"], available=AVAILABLE)


# --- the scenario rows and the comparison -----------------------------------


def test_only_affected_rows_change_and_the_base_is_untouched() -> None:
    lists = {
        "T1003": {"detection_tools": ["SIEM Tool"], "prevention_tools": [], "response_tools": []},
        "T1566": {
            "detection_tools": ["Mail Gateway"],
            "prevention_tools": ["Mail Gateway"],
            "response_tools": [],
        },
    }
    before = [dict(vars(r)) for r in BASE]
    rows = scenario.scenario_rows(BASE, lists)
    by = {r.technique_code: r for r in rows}
    assert by["T1003"].detection_tools == ["SIEM Tool"]
    assert by["T1003"].prevention_tools == []
    assert by["T1059"].detection_tools == ["SIEM Tool"]  # not affected
    # The base rows are never mutated.
    assert [dict(vars(r)) for r in BASE] == before
    # Citations are the base row's: a tool awaiting review there still is.
    assert by["T1003"].unconfirmed_citations == []


def test_the_comparison_computes_both_sides_and_names_what_moved() -> None:
    """Under R3 a technique is Covered only with all three in place. Removing
    the only Respond tool from a covered technique makes it Partial, by code."""
    from tests._attack_rows import _standalone_codes

    a, b = sorted(c for c in _standalone_codes() if c != "T1003")[:2]
    assessment = SimpleNamespace(id="a", status_rules=2, parent_rules=2)
    base = [
        _row(a, d=["EDR Tool"], p=["EDR Tool"], r=["SOAR Tool"]),
        _row(b, d=["SIEM Tool"], p=["SIEM Tool"], r=["SIEM Tool"]),
    ]
    after_rows = scenario.scenario_rows(
        base,
        {
            a: {
                "detection_tools": ["EDR Tool"],
                "prevention_tools": ["EDR Tool"],
                "response_tools": [],
            }
        },
    )
    result = scenario.compare(assessment, base, after_rows)
    assert result.changed == [(a, "covered", "partial")]
    assert (result.today.covered, result.today.partial) == (2, 0)
    assert (result.after.covered, result.after.partial) == (1, 1)
    assert result.after.coverage_pct < result.today.coverage_pct
