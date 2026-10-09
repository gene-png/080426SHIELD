"""Rows for openpyxl workbooks whose strings are free text (#972).

Shared by every service's `render_xlsx`; ATT&CK's `_safe_text_row` was the
pattern and now calls this.

A deliverable workbook carries client input (a legal name, a service title,
notes) and model output (rationale, findings). Two things go wrong with a bare
`ws.append`:

* openpyxl stores a string starting with "=" as a FORMULA, so a legal name of
  `=HYPERLINK(...)` becomes a live formula in a Kentro-branded workbook. A
  leading "+", "-", "@", tab or carriage return is the same attack in any tool
  that re-reads the cell (CSV export, copy and paste);
* openpyxl raises on a control character, so one stray byte fails the whole
  finalize.

`safe_text_row` drops the characters openpyxl cannot store, and marks a string
starting with any of those six as TEXT: data type "s" and Excel's quote prefix,
which shows the cell exactly as typed and never evaluates it. The value itself
is not changed, so the cell reads back exactly as typed.
"""

from __future__ import annotations

from typing import Any

#: A leading character that makes a cell a formula, or one a spreadsheet tool
#: can evaluate when the text is re-read (OWASP, CSV injection).
FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def safe_text_row(ws: Any, values: list) -> None:
    """Append `values` to `ws` with every string stored as text, as typed."""
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

    ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values])
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str) and cell.value.startswith(FORMULA_TRIGGERS):
            cell.data_type = "s"
            cell.quotePrefix = True
