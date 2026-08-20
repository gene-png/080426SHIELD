"""#77: `tech_debt_extract` was the last AI parser with no top-level shape guard.

It carried both halves of the defect family `AIResponseShapeError` exists for:

    raw_items = decoded.get("items", []) if isinstance(decoded, dict) else []
    return [_coerce_item(i) for i in raw_items if isinstance(i, dict)]

- the `else []` fallback — a bare list top level (the likeliest drift: the model
  returns the array it was asked to nest) was discarded whole, reporting zero
  extracted items, which is indistinguishable from an inventory the model found
  nothing in;
- the iterate-keys hole — a non-list `items` that happens to be a dict yields
  its KEYS, each of which the `isinstance` filter then drops one by one.

It is partly self-reporting: `reconcile_rows` marks every uploaded row excluded
when extraction returns nothing, so a silent empty run surfaces as "we excluded
all 240 of your rows". That is why it was not swept into #78 with the other
four. It still matters, because this path feeds the ATT&CK allow-list, where an
empty capability list once produced 607 fabricated `gap` rows — a report
asserting the client has no coverage, from an extraction that returned nothing.
The reconciliation makes that visible IF SOMEONE READS IT; it does not refuse.

**The prose-tolerance tests below are not padding.** `_parse_response` retries
by slicing the JSON out of surrounding prose, which `parse_json` does NOT do —
so swapping in `parse_json_object_with_list` wholesale would have silently
removed that tolerance and turned working providers into hard failures. They pin
the behaviour a naive fix destroys.

That retry originally considered `{...}` only, which had its own hole: a bare
list wrapped in prose sliced down to the first ITEM's braces and decoded as one
object with no `items` key, so the guard never saw a list and the run reported
zero capabilities. It now considers `[...]` too, first-decoding-candidate wins.
"""

from __future__ import annotations

import json

import pytest

from app.ai.engine import AIResponseShapeError
from app.tech_debt.extract import _parse_response

_ITEM = {"name": "Splunk", "vendor": "Splunk", "source_row_index": 0}


# --- the guard --------------------------------------------------------------


@pytest.mark.unit
def test_a_bare_list_top_level_raises_instead_of_extracting_nothing() -> None:
    """The likeliest drift: the model returns the array it was told to nest."""
    with pytest.raises(AIResponseShapeError) as exc:
        _parse_response(json.dumps([_ITEM]))
    assert "list" in str(exc.value)


@pytest.mark.unit
def test_a_dict_under_items_raises_rather_than_iterating_its_keys() -> None:
    """The iterate-keys hole: `for item in {"a": 1}` yields "a", not the value."""
    with pytest.raises(AIResponseShapeError):
        _parse_response(json.dumps({"items": {"Splunk": _ITEM}}))


@pytest.mark.unit
def test_a_string_under_items_raises() -> None:
    """A string iterates one CHARACTER at a time — the worst silent shape."""
    with pytest.raises(AIResponseShapeError):
        _parse_response(json.dumps({"items": "Splunk, CrowdStrike"}))


@pytest.mark.unit
def test_a_scalar_top_level_raises() -> None:
    with pytest.raises(AIResponseShapeError):
        _parse_response("42")


# --- what must NOT change ---------------------------------------------------


@pytest.mark.unit
def test_a_missing_items_key_still_yields_no_items() -> None:
    """Deliberately unchanged — that is #46, filed and explicitly out of scope.

    Guarding the CONTAINER is this issue; guarding the KEY NAME is a different
    one, and conflating them here would quietly widen the change.
    """
    assert _parse_response(json.dumps({"capabilities": [_ITEM]})) == []


@pytest.mark.unit
def test_an_empty_items_list_is_a_valid_answer() -> None:
    """An inventory with nothing recognisable is a real outcome, not an error."""
    assert _parse_response(json.dumps({"items": []})) == []


@pytest.mark.unit
def test_prose_wrapped_json_is_still_tolerated() -> None:
    """`_parse_response` slices between the outermost braces; `parse_json` does not.

    This is the tolerance a wholesale swap to `parse_json_object_with_list`
    would have removed without any test noticing.
    """
    content = (
        f"Here is the inventory you asked for:\n{json.dumps({'items': [_ITEM]})}\nHope that helps!"
    )
    items = _parse_response(content)
    assert [i.name for i in items] == ["Splunk"]


@pytest.mark.unit
def test_fenced_json_is_still_tolerated() -> None:
    content = f"```json\n{json.dumps({'items': [_ITEM]})}\n```"
    assert [i.name for i in _parse_response(content)] == ["Splunk"]


@pytest.mark.unit
def test_prose_wrapped_bare_list_still_raises_the_shape_error() -> None:
    """The prose retry must not become a way around the guard.

    Slicing between the outermost braces on `[{...}]` finds the ITEM's braces
    and yields a single object — so a lenient implementation would silently
    turn a bare list into one item. It must reach the shape error instead.
    """
    with pytest.raises((AIResponseShapeError, ValueError)):
        _parse_response(f"Sure:\n{json.dumps([_ITEM])}")


@pytest.mark.unit
def test_unparseable_content_still_raises_valueerror() -> None:
    with pytest.raises(ValueError):
        _parse_response("not json at all")


@pytest.mark.unit
def test_valid_items_are_still_coerced() -> None:
    items = _parse_response(json.dumps({"items": [_ITEM, {"name": "CrowdStrike"}]}))
    assert [i.name for i in items] == ["Splunk", "CrowdStrike"]


@pytest.mark.unit
def test_prose_containing_an_unrelated_bracket_still_finds_the_object() -> None:
    """Widening the retry to brackets must not break brace recovery.

    "see [1] for details {...}" slices from the citation bracket to the last
    `]`, which is not valid JSON. The first candidate that DECODES wins, so the
    object is still recovered rather than raising.
    """
    payload = json.dumps({"items": [_ITEM]})
    items = _parse_response(f"See [1] for details {payload}")
    assert [i.name for i in items] == ["Splunk"]


@pytest.mark.unit
def test_a_prose_wrapped_dict_under_items_still_raises() -> None:
    """The iterate-keys hole must not be reachable through the prose path."""
    with pytest.raises(AIResponseShapeError):
        _parse_response(f"Result:\n{json.dumps({'items': {'Splunk': _ITEM}})}")
