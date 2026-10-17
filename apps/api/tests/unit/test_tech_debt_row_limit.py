"""#1425: an inventory over the row limit is REFUSED, not read short.

`parse_inventory` used to keep the first `MAX_ROWS` rows and append a sentinel
row, which reconcile then counted as an uploaded row: a 600-row file stored 501
received and "1 excluded", and every deliverable printed those counts. Now the
parser refuses, the route answers 422 with a typed `{reason, message}`, and no
AI call is made and no list is created.

The worlds are built by the real upload route and the real parser.
"""

from __future__ import annotations

import io

import pytest

from app.ai.llm import LLMResponse
from app.models.capability import CapabilityList
from app.tech_debt.parsers import MAX_ROWS, InventoryOverRowLimit, parse_inventory
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

CSV = "text/csv"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _csv(rows: int) -> bytes:
    lines = ["Tool,Cost"] + [f"Tool{i},{i}" for i in range(rows)]
    return ("\n".join(lines) + "\n").encode()


def _xlsx(rows: int) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Tool", "Cost"])
    for i in range(rows):
        ws.append([f"Tool{i}", i])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_the_limit_itself_is_read_whole_in_both_formats() -> None:
    assert len(parse_inventory(_csv(MAX_ROWS), CSV)) == MAX_ROWS
    assert len(parse_inventory(_xlsx(MAX_ROWS), XLSX)) == MAX_ROWS


@pytest.mark.parametrize(("make", "mime"), [(_csv, CSV), (_xlsx, XLSX)])
def test_one_row_over_the_limit_is_refused_with_the_real_count(make, mime) -> None:
    with pytest.raises(InventoryOverRowLimit) as caught:
        parse_inventory(make(MAX_ROWS + 1), mime)
    assert caught.value.rows == MAX_ROWS + 1
    assert str(MAX_ROWS + 1) in caught.value.message
    assert str(MAX_ROWS) in caught.value.message


def _extract(c, bearer: str, svc_id: str, artifact_id: str):
    return c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id, "serves": "offline"},
    )


def _world(app_client, rows: int):  # noqa: F811
    c, TestSession, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    calls = {"n": 0}

    def fake(_p):
        calls["n"] += 1
        return LLMResponse('{"items": []}')

    provider.register("extract.capabilities", fake)
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"title": "x"},
    )
    svc_id = sr.json()["id"]
    up = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer}"},
        files={"file": ("inv.csv", io.BytesIO(_csv(rows)), CSV)},
    )
    assert up.status_code == 201, up.text
    return c, TestSession, bearer, svc_id, up.json()["id"], calls


def test_the_route_refuses_an_over_limit_file_with_a_typed_422(app_client) -> None:  # noqa: F811
    c, TestSession, bearer, svc_id, artifact_id, calls = _world(app_client, MAX_ROWS + 100)

    r = _extract(c, bearer, svc_id, artifact_id)

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["reason"] == "inventory_over_row_limit"
    assert str(MAX_ROWS + 100) in error["message"]
    assert calls["n"] == 0
    with TestSession() as db:
        assert db.query(CapabilityList).count() == 0


def test_the_route_still_reads_a_file_at_the_limit(app_client) -> None:  # noqa: F811
    c, _TestSession, bearer, svc_id, artifact_id, _calls = _world(app_client, MAX_ROWS)

    r = _extract(c, bearer, svc_id, artifact_id)

    assert r.status_code == 202, r.text
