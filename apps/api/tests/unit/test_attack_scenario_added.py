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
    with pytest.raises(scenario.TooLong) as exc:
        _validate([_tool("X" * 201)])
    assert exc.value.field == "Name"
    with pytest.raises(scenario.TooLong) as exc:
        _validate([_tool("XDR Tool", vendor="V" * 201)])
    assert exc.value.field == "Vendor (optional)"
    with pytest.raises(scenario.TooLong) as exc:
        _validate([_tool("XDR Tool", category="C" * 201)])
    assert exc.value.field == "Category (optional)"


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
        added=[scenario.AddedTool("XDR Tool", None, None, ("detect", "prevent", "respond"))],
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


def _parse_declared(rows, functions, *, lost=None, opened=None):
    return scenario.parse_delta(
        {"rows": rows},
        asked=[PREVENTABLE],
        available=["SIEM Tool", "XDR Tool"],
        lost=lost or {},
        opened=opened or {},
        added=[scenario.AddedTool("XDR Tool", None, None, tuple(functions))],
    )


def test_an_added_tool_credited_for_a_lost_function_it_was_not_declared_for_is_dropped() -> None:
    """The advisor, 16:00Z (#818 F6): the admin's choice is the only evidence."""
    parsed = _parse_declared(
        [_flags(PREVENTABLE, "XDR Tool", d=True)], ("prevent",), lost={PREVENTABLE: ["detection"]}
    )
    assert parsed.dropped == {"function_not_declared": 1}
    assert parsed.lists[PREVENTABLE]["detection_tools"] == []


def test_an_added_tool_credited_for_an_open_function_it_was_not_declared_for_is_dropped() -> None:
    parsed = _parse_declared(
        [_flags(PREVENTABLE, "XDR Tool", p=True, r=True)],
        ("prevent",),
        opened={PREVENTABLE: ["prevention", "response"]},
    )
    assert parsed.dropped == {"function_not_declared": 1}


def test_an_added_tool_credited_for_what_it_was_declared_for_is_kept() -> None:
    parsed = _parse_declared(
        [_flags(PREVENTABLE, "XDR Tool", d=True)], ("detect",), lost={PREVENTABLE: ["detection"]}
    )
    assert parsed.dropped == {}
    assert parsed.lists[PREVENTABLE]["detection_tools"] == ["XDR Tool"]


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


_ASSESSMENT = SimpleNamespace(id="a", status_rules=2, parent_rules=2)


def _lists(d=(), p=(), r=()):
    return {"detection_tools": list(d), "prevention_tools": list(p), "response_tools": list(r)}


def _split(base, lists):
    after = scenario.scenario_rows(base, lists)
    comparison = scenario.compare(_ASSESSMENT, base, after)
    return scenario.split_higher(
        _ASSESSMENT, base, lists, comparison, sorted(lists), added_names=["XDR Tool"]
    )


def test_a_rise_only_an_added_tool_explains_is_b11s() -> None:
    base = [_row(PREVENTABLE, status="gap")]
    remaining, from_added = _split(base, {PREVENTABLE: _lists(p=["XDR Tool"])})
    assert (remaining, from_added) == ([], [PREVENTABLE])


def test_a_rise_a_remaining_tool_explains_alone_is_copy_18s_even_beside_an_added_credit() -> None:
    """#818 review, F3: SIEM (remaining) re-credits Detect AND XDR (added)
    credits Prevent. Without XDR the technique still rises, so the warning
    stands; attributing it to the added tool would hide it."""
    base = [_row(PREVENTABLE, status="gap")]
    remaining, from_added = _split(base, {PREVENTABLE: _lists(d=["SIEM Tool"], p=["XDR Tool"])})
    assert (remaining, from_added) == ([PREVENTABLE], [])


def test_a_rise_the_remaining_tool_starts_and_an_added_tool_lifts_counts_in_both() -> None:
    """The advisor's option (b), 16:47Z: SIEM (remaining) alone takes Gap to
    Partial -- copy 18; XDR (added) then lifts it to Covered -- B11 as well."""
    base = [_row(PREVENTABLE, status="gap")]
    remaining, from_added = _split(
        base, {PREVENTABLE: _lists(d=["SIEM Tool"], p=["XDR Tool"], r=["XDR Tool"])}
    )
    assert (remaining, from_added) == ([PREVENTABLE], [PREVENTABLE])


def test_an_added_tool_named_with_no_function_explains_no_rise() -> None:
    """A row naming XDR with every function false put nothing in the lists."""
    base = [_row(PREVENTABLE, status="gap")]
    remaining, from_added = _split(base, {PREVENTABLE: _lists(d=["SIEM Tool"])})
    assert (remaining, from_added) == ([PREVENTABLE], [])


# --- the resolver decides (#818 review, F1, F2) -------------------------------


@pytest.mark.parametrize(
    "name", ["EDR  Tool", "EDR" + chr(9) + "Tool"], ids=["double-space", "tab"]
)
def test_a_client_tool_spelled_with_other_whitespace_is_refused(name) -> None:
    """The resolver collapses internal whitespace; `_key` did not. Such a name
    passed, then made BOTH it and the client's tool resolve ambiguous."""
    with pytest.raises(scenario.AlreadyClients):
        _validate([_tool(name)])


def test_a_spelling_of_client_tools_that_already_collide_is_still_theirs() -> None:
    """#818 narrow review, 1(b): the client's own two spellings make the name
    AMBIGUOUS, not confirmed. It is still the client's tool."""
    with pytest.raises(scenario.AlreadyClients):
        _validate([_tool("Edr Tool")], client=("EDR TOOL", "EDR Tool"))


def test_a_client_spelling_after_another_added_tool_is_still_the_clients() -> None:
    """#818 round 3: with an EARLIER added tool in the list, the classifier
    still names the cause from the name tiers -- B4, not B5. (The old rule,
    "ambiguous and no earlier tool", answered Indistinct here.)"""
    with pytest.raises(scenario.AlreadyClients) as exc:
        _validate([_tool("XDR Suite"), _tool("Edr Tool")], client=("EDR TOOL", "EDR Tool"))
    assert exc.value.name == "Edr Tool"


def test_a_name_shown_as_two_colliding_client_tools_is_indistinct() -> None:
    """#818 narrow review, 1(a): two client tools already share a placeholder;
    a third name shown as it is refused, not accepted on the ambiguity."""
    with pytest.raises(scenario.Indistinct):
        _validate([_tool("Suite 300 Scanner")], client=("Suite 100 Scanner", "Suite 200 Scanner"))


def test_two_added_tools_differing_only_in_whitespace_are_refused() -> None:
    with pytest.raises(scenario.Duplicate):
        _validate([_tool("Cloud Tool"), _tool("Cloud  Tool")])


@pytest.mark.parametrize("value", [["detect"], {"f": "detect"}, 1, None])
def test_a_function_that_is_not_a_string_is_refused_not_raised(value) -> None:
    with pytest.raises(scenario.BadFunction) as exc:
        _validate([_tool("XDR Tool", (value,))])
    assert exc.value.value == value


# --- #826: a character that cannot be stored or shown ------------------------------
#
# The set is Unicode's own: every control character (category Cc: C0, DEL and
# C1) and the line and paragraph separators (Zl, Zp). Rows are written out here
# from that definition, not read from the code under test. NUL is the one
# Postgres refuses to store (measured: jsonb answers "unsupported Unicode escape
# sequence"); the rest store, but a name is one line of visible text.

REFUSED = [
    pytest.param(chr(0x00), id="NUL"),
    pytest.param(chr(0x09), id="tab"),
    pytest.param(chr(0x0A), id="line-feed"),
    pytest.param(chr(0x0D), id="carriage-return"),
    pytest.param(chr(0x1B), id="escape"),
    pytest.param(chr(0x1F), id="unit-separator"),
    pytest.param(chr(0x7F), id="DEL"),
    pytest.param(chr(0x85), id="next-line-C1"),
    pytest.param(chr(0x9F), id="last-C1"),
    pytest.param(chr(0x2028), id="line-separator"),
    pytest.param(chr(0x2029), id="paragraph-separator"),
]


@pytest.mark.parametrize("ch", REFUSED)
@pytest.mark.parametrize(
    ("field", "label"),
    [("name", "Name"), ("vendor", "Vendor (optional)"), ("category", "Category (optional)")],
)
def test_a_control_character_or_line_separator_in_any_field_is_refused(ch, field, label) -> None:
    tool = _tool("XDR Tool")
    tool[field] = "X" + ch + "Y"
    with pytest.raises(scenario.Unprintable) as exc:
        _validate([tool])
    assert exc.value.field == label


@pytest.mark.parametrize(
    "name",
    [
        "Caf" + chr(0xE9) + " Suite",  # a letter outside ASCII
        "XDR " + chr(0x2014) + " Cloud",  # an em dash
        "XDR" + chr(0xA0) + "Suite",  # a no-break space: a space, not a control
        "Tool" + chr(0x200D) + "X",  # a zero-width joiner: a format character, kept
    ],
)
def test_visible_text_outside_ascii_is_not_refused(name) -> None:
    (tool,) = _validate([_tool(name)])
    assert tool.name == name
