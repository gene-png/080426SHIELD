"""#1094: the "≥" is ON the XLSX savings value, not only beside it.

When estimated savings are a lower bound, the PDF, DOCX and plan card print
"≥" on the number. The XLSX cell was a plain number formatted "$#,##0" with the
"≥" only in the next column, so a reader who copied the number got an exact
looking figure. Ruled on #736 (6229200940): keep the cell NUMERIC (sums still
work) and give it the number format `"≥ "$#,##0` only when the savings are a
floor; an exact figure keeps `$#,##0`. The cell is read back from a workbook the
real renderer wrote, never from the format string the code holds.
"""

from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from app.models import CapabilityList
from app.tech_debt.exporters import DeliverableContext, render_xlsx
from tests.unit.test_tech_debt_bundle_part_savings import (  # noqa: F401  (fixtures)
    SAVINGS,
    _xlsx_rows,
    released,
)
from tests.unit.test_tech_debt_dashboard import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

#: The format the advisor ruled for a floor, and the one an exact figure keeps.
FLOOR_FORMAT = '"≥ "$#,##0'
EXACT_FORMAT = "$#,##0"


def _savings_cell(raw: bytes):
    ws = load_workbook(io.BytesIO(raw)).worksheets[0]
    for row in ws.iter_rows():
        if row[0].value == "Estimated annual savings":
            return row[4]
    raise AssertionError("no 'Estimated annual savings' row in the workbook")


def _render(*, savings: float, known: bool) -> bytes:
    ctx = DeliverableContext(
        client_legal_name="Example Co",
        service_title="Technical Debt Review",
        cap_list=CapabilityList(version=1),
        items=[],
        total_cost=0.0,
        estimated_savings=savings,
        savings_cost_known=known,
    )
    return render_xlsx(ctx)


def test_a_floor_savings_cell_is_numeric_and_carries_the_marker_in_its_format() -> None:
    cell = _savings_cell(_render(savings=12345.0, known=False))
    assert cell.value == 12345.0, cell.value
    # openpyxl reads 12345.0 back as an int: what matters is that it is a number.
    assert isinstance(cell.value, (int, float)), "the cell must stay a number so sums work"
    assert cell.number_format == FLOOR_FORMAT, cell.number_format


def test_an_exact_savings_cell_keeps_the_plain_format() -> None:
    cell = _savings_cell(_render(savings=12345.0, known=True))
    assert cell.value == 12345.0, cell.value
    assert cell.number_format == EXACT_FORMAT, cell.number_format
    assert "≥" not in cell.number_format


def test_a_floor_of_zero_still_carries_the_marker() -> None:
    # The redundancy card marks a floor even at $0 (#1044); so does the file.
    cell = _savings_cell(_render(savings=0.0, known=False))
    assert cell.value == 0.0
    assert cell.number_format == FLOOR_FORMAT, cell.number_format


def test_a_released_floor_deliverable_marks_the_cell_the_client_downloads(
    released,  # noqa: F811
) -> None:
    raw = released["files"]["xlsx"]
    cell = _savings_cell(raw)
    assert cell.value == SAVINGS, cell.value
    assert cell.number_format == FLOOR_FORMAT, cell.number_format
    # The note beside it is unchanged: the marker adds no new words.
    assert (
        _xlsx_rows(raw)["Estimated annual savings"][5] == "≥ (one or more cut rows missing a cost)"
    )
