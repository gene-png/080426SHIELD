"""Build the synthetic Tech Debt XLSX for the #806 consistency measure.

    python -m scripts.build_measure_corpus

`scripts/measure_corpus/tech_debt_inventory.json` is the reviewed source; this
writes `tech_debt_inventory.xlsx` beside it: one sheet, the JSON's `header` as
row 1 and its `rows` below, every cell as the text it holds in the JSON. The
JSON's `classes` map is NOT written: it names which row stands for which
section 2 class (#806 comment 5983938383), and a column saying so would tell
the model the answer. A test reads the committed XLSX back through the
upload's own parser and requires it to equal the JSON, so an edit to one
without the other goes red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.logging import get_logger

_log = get_logger(__name__)

CORPUS_DIR = Path(__file__).resolve().parent / "measure_corpus"


def write_inventory_xlsx(source: Path, target: Path) -> int:
    """Write `source`'s header and rows to `target` as an XLSX. Returns the
    number of data rows written. Raises on a row whose width is not the
    header's, rather than writing a sheet the parser would read differently."""
    from openpyxl import Workbook

    doc = json.loads(Path(source).read_text(encoding="utf-8"))
    header, rows = doc["header"], doc["rows"]
    for i, row in enumerate(rows):
        if len(row) != len(header):
            raise ValueError(f"row {i} has {len(row)} cells; the header has {len(header)}")
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventory"
    ws.append(header)
    for row in rows:
        ws.append(row)
    wb.save(target)
    _log.info("build_measure_corpus.written", target=str(target), rows=len(rows))
    return len(rows)


def main() -> int:
    n = write_inventory_xlsx(
        CORPUS_DIR / "tech_debt_inventory.json", CORPUS_DIR / "tech_debt_inventory.xlsx"
    )
    print(f"wrote {n} rows to {CORPUS_DIR / 'tech_debt_inventory.xlsx'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
