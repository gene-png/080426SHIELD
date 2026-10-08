"""Extract the Zero Trust catalogs' source of record from the source PDFs (#838).

The ZT catalogs are corrected to their primary documents, and the test that the
catalog is right must read a spec that is NOT the catalog's own constants. This
script produces that spec: a JSON extraction of each PDF, committed beside the
PDF, carrying the PDF's title, version, date, URL, size and sha256.

    # pdfplumber is not in the api image; run it in a throwaway container:
    docker run --rm -v "<repo>:/repo" python:3.12-slim sh -c \
      "pip install -q pdfplumber==0.11.10 && \
       python /repo/apps/api/scripts/extract_zt_sources.py cisa --write"

`cisa` reads `reference-docs/cisa/zero_trust_maturity_model_v2_508.pdf` and
writes `reference-docs/cisa/cisa_ztmm_v2_rows.json`. Without `--write` it
re-extracts and COMPARES with the committed file: that is how a reviewer
re-derives the committed extraction from the PDF.

Exit 1 when the re-extraction DIFFERS from the committed file, or when there
is NO COMMITTED EXTRACTION to compare with. Exit 2 when there is NO CHECKOUT
(no `reference-docs/` at or above the script), when the PDF is missing, is not
the pinned one (wrong sha256) or cannot be read, and when the committed
extraction cannot be read: each is "could not look", never the exit 1 of a
real difference. Outside that contract: a permission failure on a stat call
(`is_file`/`is_dir` under a parent that cannot be searched) surfaces as a
traceback. That case is contrived for a manual tool, and is left unwrapped.

How a CISA row is read. The tables (Tables 2-6, one per pillar) are drawn as
cell rectangles. A ROW is the outermost rectangle in the first ("Function")
column; its text in each column is the words whose top falls inside that row
and whose x lies in that column, the columns being taken from each page's own
header words. A row whose first cell is empty at the top of a page continues
the previous row across the page break. Superscript footnote markers (smaller
type) are dropped. A line that ends in "-" is joined to the next without a
space (CISA's own hyphenated words broken across lines), except before "or" or
"and", where the hyphen is suspended and a space follows ("at- or
near-real-time"); every other line break is a space. CISA's change markers, "(New Function)" and "(Formerly ...)", are
recorded as `annotation` and are not part of the name.

DoD (#839) is added when its PDFs are committed (`reference-docs/dod/`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


class SourceUnreadable(Exception):
    """The PDF could not be read as expected: a page or heading this script
    relies on was not found. `main` reports it as exit 2, never as the exit 1
    of a real difference, so a wrong pdfplumber version cannot read as "your
    extraction is wrong"."""


CISA_PDF_NAME = "zero_trust_maturity_model_v2_508.pdf"
CISA_JSON_NAME = "cisa_ztmm_v2_rows.json"


def find_checkout(start: Path) -> Path | None:
    """The nearest directory at or above `start` holding `reference-docs/`, or
    None. Walked up, not counted: a fixed `parents[3]` raises IndexError where
    the script sits shallower, as it does in the api container at
    /app/scripts (the #314 shape)."""
    for d in (start, *start.parents):
        if (d / "reference-docs").is_dir():
            return d
    return None


CISA_SOURCE = {
    "title": "Zero Trust Maturity Model",
    "publisher": "Cybersecurity and Infrastructure Security Agency (CISA)",
    "version": "2.0",
    "date": "April 2023",
    "url": "https://www.cisa.gov/sites/default/files/2023-04/zero_trust_maturity_model_v2_508.pdf",
    "bytes": 1466397,
    "sha256": "4a95fdff55a64e2468b69af075b7f208176b88c751af92aefc3b7dacad26fdb4",
}

#: Section 5.1-5.5 headings and their tables, as the PDF prints them.
CISA_PILLARS = (
    ("5.1", "Identity", "Table 2: Identity Pillar"),
    ("5.2", "Devices", "Table 3: Devices Pillar"),
    ("5.3", "Networks", "Table 4: Networks Pillar"),
    ("5.4", "Applications and Workloads", "Table 5: Applications and Workloads"),
    ("5.5", "Data", "Table 6: Data"),
)
#: The first sentence of each pillar's section, which defines the pillar.
_DEFINITION_STARTS = {
    "Identity": "An identity refers to",
    "Devices": "A device refers to",
    "Networks": "A network refers to",
    "Applications and Workloads": "Applications and workloads include",
    "Data": "Data includes all",
}
CROSS_CUTTING = (
    "Visibility and Analytics Capability",
    "Automation and Orchestration Capability",
    "Governance Capability",
)
_COLUMNS = ("Function", "Traditional", "Initial", "Advanced", "Optimal")
_ANNOTATION = re.compile(r"\s*\((New Function|Formerly [^)]*)\)\s*$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _join_lines(lines: list[str]) -> str:
    out = ""
    for line in (ln.strip() for ln in lines):
        if not line:
            continue
        if not out:
            out = line
        elif out.endswith("-") and not re.match(r"(or|and) ", line):
            out += line  # a hyphenated word broken across lines
        elif out.endswith("-"):
            out += " " + line  # a suspended hyphen: "at- or near-real-time"
        else:
            out += " " + line
    return out


def _cell_text(words: list[dict]) -> str:
    """Words of one cell, in reading order, joined line by line."""
    lines: dict[int, list[dict]] = {}
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        key = next((k for k in lines if abs(k - w["top"]) < 3), None)
        lines.setdefault(round(w["top"]) if key is None else key, []).append(w)
    return _join_lines(
        [
            " ".join(w["text"] for w in sorted(ws, key=lambda w: w["x0"]))
            for _, ws in sorted(lines.items())
        ]
    )


def _contained(a: float, b: float, boxes: list[tuple[float, float]]) -> bool:
    """True when another, taller first-column box spans (a, b): an inner cell
    or line box, not a row."""
    return any(a2 <= a + 0.5 and b2 >= b - 0.5 and (b2 - a2) > (b - a) + 1 for a2, b2 in boxes)


def _table_rows(pdf) -> list[dict]:
    """Every first-column row of Tables 2-6, with its page and its five cells."""
    rows: list[dict] = []
    for page in pdf.pages:
        words = page.extract_words(extra_attrs=["size"], x_tolerance=1.5)  # 3 merges "at-" "or"
        if not words:
            continue
        body = max(
            {round(w["size"], 1) for w in words},
            key=lambda s: sum(1 for w in words if round(w["size"], 1) == s),
        )
        words = [w for w in words if round(w["size"], 1) >= body - 1.5]  # drop superscripts
        header = {}
        for w in words:
            if w["text"] in _COLUMNS and w["text"] not in header:
                header[w["text"]] = w
        if len(header) < len(_COLUMNS):
            continue
        header_bottom = max(header[c]["bottom"] for c in _COLUMNS)
        xs = [header[c]["x0"] - 6 for c in _COLUMNS] + [page.width]
        fx = header["Function"]["x0"]
        boxes = [
            (r["top"], r["bottom"])
            for r in page.rects
            if abs(r["x0"] - (fx - 6)) < 25
            and r["top"] > header_bottom - 1
            and r["bottom"] - r["top"] > 8
        ]
        outer = sorted(
            {(round(a, 1), round(b, 1)) for a, b in boxes if not _contained(a, b, boxes)}
        )
        for a, b in outer:
            cells = []
            for i in range(len(_COLUMNS)):
                inside = [
                    w for w in words if a - 1 <= w["top"] < b - 1 and xs[i] <= w["x0"] < xs[i + 1]
                ]
                cells.append(_cell_text(inside))
            if not any(cells):
                continue
            if not cells[0] and rows:
                prev = rows[-1]["cells"]  # continues the previous row across a page break
                rows[-1]["cells"] = [_join_lines([p, c]) for p, c in zip(prev, cells, strict=True)]
                continue
            rows.append({"page": page.page_number, "cells": cells})
    return rows


def _table_pages(pdf) -> dict[int, str]:
    """Page number -> pillar, from where each of Tables 2-6 starts. Table 7
    (the enterprise-level cross-cutting capabilities) is out of scope (#838
    decision 1), so its pages map to nothing and its rows are not read."""
    starts = []
    for _, name, title in CISA_PILLARS:
        hits = [
            p.page_number
            for p in pdf.pages
            if title in (p.extract_text() or "") and p.page_number > 12
        ]
        if not hits:
            raise SourceUnreadable(f"{title!r} not found")
        starts.append((hits[0], name))
    end = next(
        (
            p.page_number
            for p in pdf.pages
            if "Table 7: Cross-Cutting Capabilities" in (p.extract_text() or "")
            and p.page_number > 12
        ),
        None,
    )
    if end is None:
        raise SourceUnreadable("'Table 7: Cross-Cutting Capabilities' not found")
    pages: dict[int, str] = {}
    for i, (start, name) in enumerate(starts):
        stop = starts[i + 1][0] if i + 1 < len(starts) else end
        for n in range(start, stop):
            pages[n] = name
    return pages


def _definitions(pdf) -> dict[str, str]:
    text = re.sub(r"\s+", " ", " ".join(p.extract_text() or "" for p in pdf.pages))
    out = {}
    for pillar, start in _DEFINITION_STARTS.items():
        i = text.find(start)
        if i < 0:
            raise SourceUnreadable(f"definition of {pillar!r} not found")
        m = re.search(r"\.(?= [A-Z])", text[i:])
        out[pillar] = text[i : i + m.end()]
    return out


def extract_cisa(pdf_path: Path) -> dict:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = _table_pages(pdf)
        table_rows = [r for r in _table_rows(pdf) if r["page"] in pages]
        definitions = _definitions(pdf)
    rows = []
    for r in table_rows:
        raw = r["cells"][0]
        m = _ANNOTATION.search(raw)
        name = raw[: m.start()] if m else raw
        rows.append(
            {
                "pillar": pages[r["page"]],
                "name": name,
                "annotation": m.group(1) if m else None,
                "kind": "cross_cutting" if name in CROSS_CUTTING else "function",
                "page": r["page"],
                "optimal": r["cells"][4],
            }
        )
    return {
        "source": CISA_SOURCE,
        "extracted_with": "apps/api/scripts/extract_zt_sources.py (pdfplumber)",
        "pillars": [
            {"section": s, "name": n, "table": t, "definition": definitions[n]}
            for s, n, t in CISA_PILLARS
        ],
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("source", choices=("cisa",))
    p.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    repo = find_checkout(Path(__file__).resolve().parent)
    if repo is None:
        print("NO CHECKOUT: no reference-docs/ at or above this script", file=sys.stderr)
        return 2
    cisa_pdf = repo / "reference-docs" / "cisa" / CISA_PDF_NAME
    cisa_json = cisa_pdf.with_name(CISA_JSON_NAME)
    if not cisa_pdf.is_file():
        print(f"MISSING: {cisa_pdf}", file=sys.stderr)
        return 2
    try:
        got = _sha256(cisa_pdf)
    except OSError as exc:
        print(f"COULD NOT READ the PDF: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if got != CISA_SOURCE["sha256"]:
        print(f"NOT THE PINNED PDF: sha256 {got}", file=sys.stderr)
        return 2
    try:
        data = extract_cisa(cisa_pdf)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed: exit 2
        # Could-not-look is exit 2, distinct from DIFFERS (exit 1): a reader
        # that fails (a moved heading, another pdfplumber, a damaged file) says
        # nothing about whether the committed extraction is right.
        print(f"COULD NOT READ the PDF: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        cisa_json.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {cisa_json} ({len(data['rows'])} rows)")
        return 0
    if not cisa_json.is_file():
        print(f"NO COMMITTED EXTRACTION at {cisa_json}", file=sys.stderr)
        return 1
    try:
        committed = cisa_json.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"COULD NOT READ the committed extraction: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    if committed != text:
        print("DIFFERS from the committed extraction", file=sys.stderr)
        return 1
    print(f"matches the committed extraction ({len(data['rows'])} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
