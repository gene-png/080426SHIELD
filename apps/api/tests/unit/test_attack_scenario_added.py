"""#802 slice B: a what-if that ADDS tools the client doesn't have.

The pure half: what an admin may add, which techniques an added tool could
change and which of their functions it may be asked about, what the AI may
credit there, and how a rise is attributed. Approved plan: #802, comment
5969854402; the advisor at 14:58Z.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.redact import redact_for_ai
from app.attack import scenario
from app.attack.catalog import NOT_PREVENTABLE
from tests._attack_rows import _standalone_codes

pytestmark = pytest.mark.unit

# Codes from the CATALOG's own parent links (`tests/_attack_rows`), not from
# the code under test: a standalone technique that can be prevented, one that
# cannot, and a parent with sub-techniques.
_STANDALONE = sorted(_standalone_codes())
PREVENTABLE = next(c for c in _STANDALONE if c not in NOT_PREVENTABLE)
UNPREVENTABLE = next(c for c in _STANDALONE if c in NOT_PREVENTABLE)
PARENT = "T1003"  # OS Credential Dumping: it has sub-techniques
OTHER = next(c for c in _STANDALONE if c not in NOT_PREVENTABLE and c != PREVENTABLE)


def _row(code, *, d=(), p=(), r=(), status="partial", citations=()):
    return SimpleNamespace(
        technique_code=code,
        status=status,
        reason_code=None,
        detection_tools=list(d),
        prevention_tools=list(p),
        response_tools=list(r),
        unconfirmed_citations=list(citations),
    )


def _tool(name="XDR Tool", functions=("detect",), vendor=None, category=None):
    return {
        "name": name,
        "vendor": vendor,
        "category": category,
        "security_functions": list(functions),
    }


def _validate(raw, *, client=("EDR Tool", "SIEM Tool"), org="Acme"):
    return scenario.validate_added(
        raw, client_tools=client, client_org_name=org, redaction_mode="strict"
    )


# --- what an admin may add ------------------------------------------------------


def test_a_well_formed_tool_is_accepted_trimmed_with_its_functions() -> None:
    (tool,) = _validate([_tool("  XDR Tool ", ("respond", "detect"), vendor=" V ")])
    assert tool.name == "XDR Tool"
    assert tool.vendor == "V"
    assert tool.functions == ("detect", "respond")  # D/P/R order


@pytest.mark.parametrize("name", ["EDR Tool", "edr tool", "  SIEM tool  "])
def test_a_tool_the_client_already_has_is_refused_by_name(name) -> None:
    with pytest.raises(scenario.AlreadyClients) as exc:
        _validate([_tool(name)])
    assert exc.value.name == name.strip()


def test_the_placeholder_twin_of_a_client_tool_is_the_client_tool() -> None:
    """Slice A's cross-tier rule: the client's `Acme SOC Platform` is shown as
    `[CLIENT] SOC Platform`, so that spelling is the client's tool too. The
    shown form comes from the egress redactor."""
    shown, counts = redact_for_ai("Acme SOC Platform", mode="strict", client_org_name="Acme")
    assert counts and shown != "Acme SOC Platform"
    with pytest.raises(scenario.AlreadyClients):
        _validate([_tool(shown)], client=("Acme SOC Platform",))


def test_a_name_shown_as_a_client_tool_is_refused_as_indistinct() -> None:
    """Two distinct names the address rule shows as one placeholder."""
    a, _ = redact_for_ai("Suite 100 Scanner", mode="strict")
    b, _ = redact_for_ai("Suite 200 Scanner", mode="strict")
    assert a == b and a != "Suite 100 Scanner"  # the world
    with pytest.raises(scenario.Indistinct) as exc:
        _validate([_tool("Suite 200 Scanner")], client=("Suite 100 Scanner",))
    assert exc.value.name == "Suite 200 Scanner"


def test_two_added_tools_shown_as_one_name_are_refused_as_indistinct() -> None:
    with pytest.raises(scenario.Indistinct):
        _validate([_tool("Suite 100 Scanner"), _tool("Suite 200 Scanner")])


def test_a_tool_with_no_function_is_refused_by_name() -> None:
    with pytest.raises(scenario.NoFunctions) as exc:
        _validate([_tool("XDR Tool", ())])
    assert exc.value.name == "XDR Tool"


def test_a_function_that_is_not_detect_prevent_or_respond_is_refused() -> None:
    with pytest.raises(scenario.BadFunction) as exc:
        _validate([_tool("XDR Tool", ("detect", "recover"))])
    assert exc.value.value == "recover"


def test_more_than_ten_tools_are_refused() -> None:
    ten = [_tool(f"Tool {chr(65 + i)}") for i in range(10)]
    assert len(_validate(ten)) == 10
    with pytest.raises(scenario.TooMany) as exc:
        _validate([*ten, _tool("Tool Z")])
    assert exc.value.limit == 10


@pytest.mark.parametrize("name", ["", "   ", None, 5])
def test_a_tool_with_no_name_is_refused(name) -> None:
    with pytest.raises(scenario.BlankName):
        _validate([{**_tool(), "name": name}])


def test_a_tool_listed_twice_is_refused() -> None:
    with pytest.raises(scenario.Duplicate) as exc:
        _validate([_tool("XDR Tool"), _tool("xdr tool")])
    assert exc.value.name == "xdr tool"


def test_an_overlong_name_or_vendor_is_refused() -> None:
    with pytest.raises(scenario.TooLong):
        _validate([_tool("X" * 201)])
    with pytest.raises(scenario.TooLong):
        _validate([_tool("XDR Tool", vendor="V" * 201)])


def test_a_change_needs_a_removal_or_an_addition() -> None:
    with pytest.raises(scenario.EmptyChangeList):
        scenario.require_change([], [])
    scenario.require_change(["EDR Tool"], [])
    scenario.require_change([], [scenario.AddedTool("XDR Tool", None, None, ("detect",))])


# --- which techniques, and which functions --------------------------------------


def _added(*functions: str) -> list[scenario.AddedTool]:
    return [scenario.AddedTool("XDR Tool", None, None, tuple(functions))]


def test_open_functions_are_the_declared_functions_not_in_place() -> None:
    rows = [_row(PREVENTABLE, d=["SIEM Tool"])]
    opened = scenario.open_functions(rows, _added("detect", "prevent", "respond"))
    assert opened == {PREVENTABLE: ["prevention", "response"]}


def test_a_function_no_added_tool_declares_is_not_open() -> None:
    rows = [_row(PREVENTABLE, d=["SIEM Tool"])]
    assert scenario.open_functions(rows, _added("respond")) == {PREVENTABLE: ["response"]}


def test_prevention_is_never_open_where_the_technique_cannot_be_prevented() -> None:
    rows = [_row(UNPREVENTABLE)]
    assert scenario.open_functions(rows, _added("prevent", "detect")) == {
        UNPREVENTABLE: ["detection"]
    }


def test_a_tool_awaiting_review_is_not_in_place_so_its_function_is_open() -> None:
    """R3's own rule: an uncleared inferred citation is scored as not in place."""
    rows = [
        _row(
            PREVENTABLE,
            d=["SIEM Tool"],
            citations=[
                {"tool": "SIEM Tool", "cited": "SIEM", "reason": "substring", "cleared_at": None}
            ],
        )
    ]
    assert scenario.open_functions(rows, _added("detect")) == {PREVENTABLE: ["detection"]}


@pytest.mark.parametrize("status", ["not_applicable", None])
def test_a_technique_not_assessed_or_not_applicable_is_never_opened(status) -> None:
    rows = [_row(PREVENTABLE, status=status)]
    assert scenario.open_functions(rows, _added("detect")) == {}


def test_a_computed_parent_is_never_opened() -> None:
    assert scenario.open_functions([_row(PARENT)], _added("detect")) == {}


def test_a_technique_with_every_declared_function_in_place_is_not_opened() -> None:
    rows = [_row(PREVENTABLE, d=["SIEM Tool"], status="covered")]
    assert scenario.open_functions(rows, _added("detect")) == {}


def test_open_functions_are_judged_after_the_removal() -> None:
    """A technique whose Detect tool is being removed has Detect open too."""
    rows = [_row(PREVENTABLE, d=["EDR Tool"])]
    gone = scenario.removed_spellings(["EDR Tool"], client_org_name=None, redaction_mode="off")
    assert scenario.open_functions(rows, _added("detect"), removed=gone) == {
        PREVENTABLE: ["detection"]
    }


# --- what the AI may credit --------------------------------------------------------


def _flags(code, tool, d=False, p=False, r=False):
    return {"technique_code": code, "tool": tool, "detection": d, "prevention": p, "response": r}


def _parse(rows, *, lost=None, opened=None):
    return scenario.parse_delta(
        {"rows": rows},
        asked=[PREVENTABLE],
        available=["SIEM Tool", "XDR Tool"],
        lost=lost or {},
        opened=opened or {},
        added_names=["XDR Tool"],
    )


def test_an_open_function_may_be_credited_to_an_added_tool() -> None:
    parsed = _parse([_flags(PREVENTABLE, "XDR Tool", p=True)], opened={PREVENTABLE: ["prevention"]})
    assert parsed.dropped == {}
    assert parsed.lists[PREVENTABLE]["prevention_tools"] == ["XDR Tool"]


def test_an_open_function_credited_to_a_client_tool_is_dropped_as_not_added() -> None:
    parsed = _parse(
        [_flags(PREVENTABLE, "SIEM Tool", p=True)], opened={PREVENTABLE: ["prevention"]}
    )
    assert parsed.dropped == {"tool_not_added": 1}
    assert parsed.lists[PREVENTABLE]["prevention_tools"] == []


def test_a_lost_function_may_be_credited_to_a_client_or_an_added_tool() -> None:
    parsed = _parse(
        [_flags(PREVENTABLE, "SIEM Tool", d=True), _flags(PREVENTABLE, "XDR Tool", d=True)],
        lost={PREVENTABLE: ["detection"]},
    )
    assert parsed.dropped == {}
    assert parsed.lists[PREVENTABLE]["detection_tools"] == ["SIEM Tool", "XDR Tool"]


def test_a_function_neither_lost_nor_open_is_still_dropped_whole() -> None:
    parsed = _parse(
        [_flags(PREVENTABLE, "XDR Tool", p=True, r=True)], opened={PREVENTABLE: ["prevention"]}
    )
    assert parsed.dropped == {"function_not_lost": 1}


# --- batches carry the change -----------------------------------------------------


def test_each_batch_carries_the_added_tools_and_the_open_functions() -> None:
    rows = [_row(PREVENTABLE, d=["SIEM Tool"]), _row(OTHER, d=["EDR Tool"])]
    gone = scenario.removed_spellings(["EDR Tool"], client_org_name=None, redaction_mode="off")
    added = _added("detect", "prevent")
    caps = [
        {"name": "SIEM Tool", "vendor": None, "category": None, "security_functions": ["detect"]}
    ]
    (batch,) = scenario.batch_inputs(rows, sorted([PREVENTABLE, OTHER]), gone, caps, added=added)
    assert batch["added_tools"] == [
        {
            "name": "XDR Tool",
            "vendor": None,
            "category": None,
            "security_functions": ["detect", "prevent"],
        }
    ]
    assert [t["name"] for t in batch["available_tools"]] == ["SIEM Tool", "XDR Tool"]
    assert batch["open_functions"] == {
        PREVENTABLE: ["prevention"],
        OTHER: ["detection", "prevention"],
    }
    assert batch["lost_functions"] == {PREVENTABLE: [], OTHER: ["detection"]}


# --- a rise, attributed -----------------------------------------------------------


def test_a_rise_credited_to_an_added_tool_is_a_result_not_the_warning() -> None:
    comparison = scenario.Comparison(
        today=None,
        after=None,
        changed=[(PREVENTABLE, "partial", "covered"), (OTHER, "gap", "partial")],
    )
    accepted = [
        {
            "technique_code": PREVENTABLE,
            "tool": "XDR Tool",
            "detection": False,
            "prevention": True,
            "response": False,
        },
        {
            "technique_code": OTHER,
            "tool": "SIEM Tool",
            "detection": True,
            "prevention": False,
            "response": False,
        },
    ]
    remaining, from_added = scenario.split_higher(
        comparison, [PREVENTABLE, OTHER], accepted, added_names=["XDR Tool"]
    )
    assert remaining == [OTHER]
    assert from_added == [PREVENTABLE]


def test_an_added_tool_named_with_no_function_explains_no_rise() -> None:
    comparison = scenario.Comparison(
        today=None, after=None, changed=[(PREVENTABLE, "gap", "partial")]
    )
    accepted = [
        {
            "technique_code": PREVENTABLE,
            "tool": "XDR Tool",
            "detection": False,
            "prevention": False,
            "response": False,
        }
    ]
    remaining, from_added = scenario.split_higher(
        comparison, [PREVENTABLE], accepted, added_names=["XDR Tool"]
    )
    assert remaining == [PREVENTABLE]
    assert from_added == []
