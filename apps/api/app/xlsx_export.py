"""Rows for openpyxl workbooks whose strings are free text (#972).

Shared by every service's `render_xlsx`; ATT&CK's `_safe_text_row` was the
pattern and now calls this.

A deliverable workbook carries client input (a legal name, a service title,
notes) and model output (rationale, findings). Two things go wrong with a bare
`ws.append`:

* openpyxl stores a string starting with "=" as a FORMULA, so a legal name of
  `=HYPERLINK(...)` becomes a live formula in a Kentro-branded workbook. A
  leading "+", "-", "@", tab or carriage return is the same attack in a
  spreadsheet tool that reads the cell as input;
* openpyxl raises on a control character, so one stray byte fails the whole
  finalize.

`safe_text_row` drops the characters openpyxl cannot store, and marks a string
starting with any of those six as TEXT: data type "s" and Excel's quote prefix.
Inside the .xlsx, Excel and LibreOffice then show the cell as typed and do not
evaluate it. The value itself is not changed, so the cell reads back exactly as
typed. That protection is the .xlsx file's only: the quote prefix is a style
flag, so a CSV saved from the sheet carries the raw value, leading "=" and all
(#992).

Every strip logs ONE warning per cell, `xlsx_export.control_characters_removed`,
naming the sheet, the column LETTER, the row and how many characters went.
NEVER the value, and no cell's text at all: a column is not named by the text
above it, because row 1 of the CSF, Zero Trust and ATT&CK summary sheets is
the client's legal name, and other sheets open with a banner or a caption.
"""

from __future__ import annotations

from typing import Any

from app.logging import get_logger

_log = get_logger(__name__)

#: A leading character that makes a cell a formula, or one a spreadsheet tool
#: can evaluate when it reads the text as input (OWASP, "CSV injection"). Marking
#: the cell as text guards the .xlsx only; a CSV saved from it does not keep the
#: mark (#992).
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def safe_text_row(ws: Any, values: list) -> None:
    """Append `values` to `ws` with every string stored as text, as typed."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    removed = [len(ILLEGAL_CHARACTERS_RE.findall(v)) if isinstance(v, str) else 0 for v in values]
    ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values])
    row = ws.max_row
    for column, count in enumerate(removed, start=1):  # append starts at column A
        if count:
            cell = ws.cell(row=row, column=column)
            _log.warning(
                "xlsx_export.control_characters_removed",
                sheet=ws.title,
                column=cell.column_letter,  # never the text above it
                row=cell.row,
                removed=count,
            )
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str) and cell.value.startswith(FORMULA_TRIGGERS):
            cell.data_type = "s"
            cell.quotePrefix = True
