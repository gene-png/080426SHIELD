"""#833 + #834: the extraction validates what the model returns before storing it,
and records what it could not store as given (`capability_lists.extraction_findings`).

The approved plan (issue 833, comments 5984037981 and 5995416506):
  * a number is judged as a number: range first, then wholeness; a whole number
    written differently ("2", 2.0, "1,000") is accepted; a bool is refused; a
    cost may carry a leading "$" and "," separators (v3.2: "Accept a dollar sign
    as USD"), and nothing else;
  * a refused value is stored as NULL and recorded, never truncated in silence
    (`int(2.9)` is not 2);
  * a string longer than its column is cut to the column width and recorded,
    never left to crash the insert on Postgres after the call is paid;
  * NULL means "not recorded" (a list from before the column); [] means checked
    and nothing to record.

Every expected value is written out here from the plan's table, never read from
the parser. Everything goes through the extraction route and the latest-list GET.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit


def _item(name: str, i: int, **fields) -> dict:
    base = {
        "name": name,
        "vendor": None,
        "category": None,
        "function": None,
        "annual_cost_usd": None,
        "license_count": None,
        "notes": None,
        "security_related": True,
        "security_functions": ["detect"],
        "confidence_pct": 90,
        "source_row_index": i,
    }
    return {**base, **fields}


def _extract(app_client, items: list[dict], rows: int | None = None):  # noqa: F811
    return _extract_with_headers(app_client, items, rows)[0]


def _extract_with_headers(app_client, items, rows=None):  # noqa: F811
    c, Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": items})))
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    n = len(items) if rows is None else rows
    csv = "name\n" + "".join(f"row{k}\n" for k in range(n))
    art = _upload_csv(c, bearer, "x.csv", csv.encode())
    return tech_debt_extract(c, svc, h, art), h


#: (raw value, stored value, finding reason or None)
COST = [
    (1200, 1200.0, None),
    ("1200", 1200.0, None),
    ("$1,200", 1200.0, None),
    ("1,200.50", 1200.5, None),
    (0, 0.0, None),
    (True, None, "unparseable"),
    ("€1,200", None, "unparseable"),
    ("1200/month", None, "unparseable"),
    (-5, None, "out_of_range"),
    (10**12, None, "out_of_range"),
]
LICENSES = [
    (2, 2, None),
    (2.0, 2, None),
    ("2", 2, None),
    ("1,000", 1000, None),
    (2.9, None, "not_whole"),
    (True, None, "unparseable"),
    ("enterprise", None, "unparseable"),
    (-1, None, "out_of_range"),
    (2**31, None, "out_of_range"),
]
CONFIDENCE = [
    (60, 60, None),
    ("90", 90, None),
    (2.5, None, "not_whole"),
    (101, None, "out_of_range"),
    (True, None, "unparseable"),
]


@pytest.mark.parametrize(("raw", "stored", "reason"), COST)
def test_annual_cost(app_client, raw, stored, reason) -> None:  # noqa: F811
    body = _extract(app_client, [_item("Tool", 0, annual_cost_usd=raw)])
    (item,) = body["items"]
    assert item["annual_cost_usd"] == stored
    expected = (
        []
        if reason is None
        else [
            {
                "source_row_index": 0,
                "item_name": "Tool",
                "field": "annual_cost_usd",
                "reason": reason,
                "value": raw if isinstance(raw, str) else repr(raw),
            }
        ]
    )
    assert body["extraction_findings"] == expected


@pytest.mark.parametrize(("raw", "stored", "reason"), LICENSES)
def test_license_count(app_client, raw, stored, reason) -> None:  # noqa: F811
    body = _extract(app_client, [_item("Tool", 0, license_count=raw)])
    (item,) = body["items"]
    assert item["license_count"] == stored
    reasons = [(f["field"], f["reason"]) for f in body["extraction_findings"]]
    assert reasons == ([] if reason is None else [("license_count", reason)])


@pytest.mark.parametrize(("raw", "stored", "reason"), CONFIDENCE)
def test_confidence(app_client, raw, stored, reason) -> None:  # noqa: F811
    body = _extract(app_client, [_item("Tool", 0, confidence_pct=raw)])
    (item,) = body["items"]
    assert item["confidence_pct"] == stored
    reasons = [(f["field"], f["reason"]) for f in body["extraction_findings"]]
    assert reasons == ([] if reason is None else [("confidence_pct", reason)])


@pytest.mark.parametrize(
    ("raw", "reason"),
    [(2.9, "not_whole"), (5, "out_of_range"), (True, "unparseable")],
)
def test_a_bad_source_row_index_is_left_unattributed(app_client, raw, reason) -> None:  # noqa: F811
    """`2.9` used to be stored as row 2, attributing the item to the wrong row."""
    body = _extract(app_client, [_item("Tool", raw)], rows=2)
    reasons = [(f["field"], f["reason"]) for f in body["extraction_findings"]]
    assert reasons == [("source_row_index", reason)]
    # Unattributed: the reconciliation cannot list exclusions it cannot see.
    assert body["attribution_complete"] is False


def test_an_over_long_string_is_cut_to_its_column_and_recorded(app_client) -> None:  # noqa: F811
    long_name = "N" * 300
    long_category = "C" * 200
    body = _extract(app_client, [_item(long_name, 0, category=long_category)])
    (item,) = body["items"]
    assert (len(item["name"]), len(item["category"])) == (255, 128)
    found = {(f["field"], f["reason"], f["width"]) for f in body["extraction_findings"]}
    assert found == {("name", "truncated", 255), ("category", "truncated", 128)}


def test_a_clean_extraction_records_an_empty_list(app_client) -> None:  # noqa: F811
    body = _extract(app_client, [_item("Tool", 0, annual_cost_usd=100, license_count=3)])
    assert body["extraction_findings"] == []


def test_a_list_from_before_the_column_reads_as_not_recorded(app_client) -> None:  # noqa: F811
    """A pre-0062 list was never checked: NULL, never an empty "nothing found"."""
    import uuid

    from sqlalchemy import update

    from app.models.capability import CapabilityList

    body, h = _extract_with_headers(app_client, [_item("Tool", 0, license_count=2.9)])
    assert body["extraction_findings"]  # APPEAR: this list was checked
    c, Sess, _provider = app_client
    with Sess() as s:
        s.execute(
            update(CapabilityList)
            .where(CapabilityList.id == uuid.UUID(body["id"]))
            .values(extraction_findings=None)
        )
        s.commit()
    latest = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert latest["extraction_findings"] is None
