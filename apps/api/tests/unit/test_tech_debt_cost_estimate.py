"""TD-5 (for #1060): the pure half of the opt-in AI cost estimate.

Who is asked, what is sent, and how every answer is sorted. Expectations are
typed from the approved proposal (#736 6205600298, ruled 6206818759 item 5),
never read from the module's own constants.
"""

from __future__ import annotations

import uuid

import pytest

from app.tech_debt.cost_estimate import build_payload, estimate_targets, parse_estimates
from tests.unit.test_exporters import _item

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Who is asked
# ---------------------------------------------------------------------------


def test_only_uncosted_unlocked_source_items_are_asked() -> None:
    bundle = _item(name="Suite Bundle", annual_cost_usd=500_000)
    items = [
        _item(name="Tool A", annual_cost_usd=None),
        _item(name="Tool B", annual_cost_usd=0),  # a recorded $0 is a cost
        _item(name="Tool C", annual_cost_usd=None, locked=True),  # the consultant's lock
        _item(name="Tool D", annual_cost_usd=1_000),
        bundle,
        _item(name="Bundle Part", annual_cost_usd=None, parent_item_id=bundle.id),
        _item(name="Tool E", annual_cost_usd=None),
    ]
    assert [i.name for i in estimate_targets(items)] == ["Tool A", "Tool E"]


def test_the_payload_uses_opaque_refs_and_no_database_id() -> None:
    a = _item(name="Tool A", annual_cost_usd=None, vendor="V", license_count=40, notes="n")
    b = _item(name="Tool B", annual_cost_usd=None, vendor=None, license_count=None)
    payload, refs = build_payload([a, b])
    assert refs == {"T1": a.id, "T2": b.id}
    assert [t["ref"] for t in payload["tools"]] == ["T1", "T2"]
    # The approved field list, and nothing else: no id, no cost, no disposition.
    assert set(payload["tools"][0]) == {
        "ref",
        "name",
        "vendor",
        "category",
        "function",
        "license_count",
        "notes",
    }
    assert payload["tools"][0]["license_count"] == 40
    assert str(a.id) not in repr(payload)


# ---------------------------------------------------------------------------
# How every answer is sorted
# ---------------------------------------------------------------------------


def test_a_whole_estimate_is_kept_with_its_basis() -> None:
    out = parse_estimates(
        [{"ref": "T1", "annual_cost_usd": 12000, "basis": "Tier X at $25 per user."}], ["T1"]
    )
    assert out.estimates["T1"].cost == 12000.0
    assert out.estimates["T1"].basis == "Tier X at $25 per user."
    assert out.declined == [] and out.refused == {} and out.stray_entries == 0


@pytest.mark.parametrize("value", ["12000", 12000.0, " 12000 "], ids=["string", "float", "padded"])
def test_a_value_the_model_plainly_meant_is_accepted(value) -> None:
    out = parse_estimates([{"ref": "T1", "annual_cost_usd": value, "basis": "b"}], ["T1"])
    assert out.estimates["T1"].cost == 12000.0


def test_null_is_declined_not_refused() -> None:
    out = parse_estimates([{"ref": "T1", "annual_cost_usd": None, "basis": "unknown"}], ["T1"])
    assert out.declined == ["T1"]
    assert out.estimates == {} and out.refused == {}


def test_an_answer_with_no_cost_key_is_refused_not_declined() -> None:
    """A misnamed key is not the model saying "I cannot estimate": the prompt
    asks for `annual_cost_usd`, and an entry without it is refused, so key
    drift shows as a refusal rather than as a decline."""
    out = parse_estimates([{"ref": "T1", "cost": 12000}], ["T1"])
    assert out.declined == []
    assert out.refused == {"invalid_cost": ["T1"]}


@pytest.mark.parametrize(
    "value",
    [True, 1.5, -5, 10**12, "1,200", "$1200", "about 1200", "nan", "inf", [1200], {"v": 1}],
    ids=[
        "bool",
        "fraction",
        "negative",
        "over-column",
        "commas",
        "currency",
        "text",
        "nan",
        "inf",
        "list",
        "object",
    ],
)
def test_a_value_that_is_not_a_storable_whole_dollar_amount_is_refused(value) -> None:
    out = parse_estimates([{"ref": "T1", "annual_cost_usd": value, "basis": "b"}], ["T1"])
    assert out.refused == {"invalid_cost": ["T1"]}
    assert out.estimates == {} and out.declined == []


def test_an_asked_ref_with_no_answer_is_refused_as_omitted() -> None:
    out = parse_estimates([{"ref": "T1", "annual_cost_usd": 100, "basis": "b"}], ["T1", "T2"])
    assert out.refused == {"omitted": ["T2"]}
    assert set(out.estimates) == {"T1"}


def test_stray_entries_are_counted_and_never_applied() -> None:
    entries = [
        {"ref": "T1", "annual_cost_usd": 100, "basis": "first"},
        {"ref": "T1", "annual_cost_usd": 999, "basis": "repeat"},  # a second answer
        {"ref": "T9", "annual_cost_usd": 500, "basis": "never asked"},
        {"annual_cost_usd": 500},  # no ref
        "not an object",
    ]
    out = parse_estimates(entries, ["T1"])
    assert out.stray_entries == 4
    # The first answer stands; the repeat did not overwrite it.
    assert out.estimates["T1"].cost == 100.0
    assert out.estimates["T1"].basis == "first"


def test_a_missing_or_blank_basis_keeps_the_estimate_without_one() -> None:
    out = parse_estimates(
        [
            {"ref": "T1", "annual_cost_usd": 100},
            {"ref": "T2", "annual_cost_usd": 200, "basis": "   "},
        ],
        ["T1", "T2"],
    )
    assert out.estimates["T1"].basis is None
    assert out.estimates["T2"].basis is None


def test_every_asked_ref_lands_in_exactly_one_outcome() -> None:
    asked = ["T1", "T2", "T3", "T4"]
    out = parse_estimates(
        [
            {"ref": "T1", "annual_cost_usd": 100, "basis": "b"},
            {"ref": "T2", "annual_cost_usd": None},
            {"ref": "T3", "annual_cost_usd": "lots"},
        ],
        asked,
    )
    placed = list(out.estimates) + out.declined + [r for refs in out.refused.values() for r in refs]
    assert sorted(placed) == asked


def test_targets_keep_their_order_and_ids() -> None:
    ids = [uuid.uuid4() for _ in range(3)]
    items = [_item(id=i, name=f"Tool {n}", annual_cost_usd=None) for n, i in enumerate(ids)]
    _, refs = build_payload(estimate_targets(items))
    assert list(refs.values()) == ids
