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

`dod` reads `reference-docs/dod/ZT-CapabilitiesActivities.pdf` (DoD CIO, 2025,
25-T-1465, the source of record per #839 comment 5983310584) and writes
`reference-docs/dod/dod_zt_2025_rows.json`: the 45 capabilities and their 152
activities. The 2022 Roadmap beside it is pinned too, for the record.

How a DoD row is read. Both tables are drawn with cell rules. The columns are
the vertical rules that cross the header row; a ROW is the band between two
horizontal rules that cross the first ("ID") column, and a band whose ID cell
is empty continues the previous row across a page break. A cell's text is
built from its CHARACTERS, keeping the PDF's own space characters: the tables'
justified text spreads letters apart, so a word-gap tolerance cannot tell a
wide letter gap from a word break. Lines join as for CISA.
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


DOD_PDF_NAME = "ZT-CapabilitiesActivities.pdf"
DOD_ROADMAP_NAME = "DoD-ZTExecutionRoadmap.pdf"
DOD_JSON_NAME = "dod_zt_2025_rows.json"

DOD_SOURCE = {
    "title": "DOD Zero Trust Execution Roadmap (COAs 1-3)",
    "publisher": "DoD Chief Information Officer",
    "marking": "25-T-1465",
    "date": "2025-08-21 (modified 2025-09-03)",
    "url": "https://dodcio.defense.gov/Portals/0/Documents/Library/ZT-CapabilitiesActivities.pdf",
    "bytes": 651809,
    "sha256": "756abc470d22dfddf399bcf3264b23c23fecedd8ac32b98b4f3461c96ed43be1",
}
DOD_ROADMAP_SOURCE = {
    "title": "DOD ZT Capability Execution Roadmap (COA 1)",
    "publisher": "Department of Defense",
    "date": "2022-11-21",
    "url": "https://dodcio.defense.gov/Portals/0/Documents/Library/DoD-ZTExecutionRoadmap.pdf",
    "bytes": 2505849,
    "sha256": "0d013fdb00740f2221e8bd227e21b05f13a57ee6a88b7d301e828d3717b9d928",
}
_DOD_CAPABILITY = re.compile(r"[1-7]\.\d{1,2}")
_DOD_ACTIVITY = re.compile(r"[1-7]\.\d{1,2}\.\d{1,2}")
_DOD_PILLAR = re.compile(r"([1-7]) - (.+)")


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


def _dod_columns(page, header_y: float) -> list[float]:
    """x of each vertical rule crossing the header row, near-duplicates merged."""
    xs = sorted(
        r["x0"] for r in page.rects if r["top"] < header_y < r["bottom"] and (r["x1"] - r["x0"]) < 2
    )
    out: list[float] = []
    for x in xs:
        if not out or x - out[-1] > 3:
            out.append(x)
    return out


def _dod_rules(page, x0: float, x1: float) -> list[float]:
    """y of each horizontal rule crossing the ID column."""
    return sorted(
        {
            round(r["top"], 1)
            for r in page.rects
            if r["x0"] <= x0 + 1 and r["x1"] >= x1 - 1 and (r["bottom"] - r["top"]) < 1.5
        }
    )


def _dod_cell(chars, x0: float, x1: float, y0: float, y1: float) -> list[str]:
    """One cell's lines, from its characters and their own spaces."""
    inside = [
        c
        for c in chars
        if x0 <= (c["x0"] + c["x1"]) / 2 < x1
        and y0 <= (c["top"] + c["bottom"]) / 2 < y1
        and c["size"] >= 4.0
    ]
    lines: list[list] = []
    for c in sorted(inside, key=lambda c: (c["top"], c["x0"])):
        for line in lines:
            if abs(line[0] - c["top"]) < 2:
                line[1].append(c)
                break
        else:
            lines.append([c["top"], [c]])
    out = []
    for _, cs in sorted(lines, key=lambda line: line[0]):
        text = re.sub(r"\s+", " ", "".join(c["text"] for c in sorted(cs, key=lambda c: c["x0"])))
        if text.strip():
            out.append(text.strip())
    return out


def _dod_table(pdf, title: str, header_y: float, columns: tuple[str, ...], row_id: re.Pattern):
    """Every row of the table on the pages titled `title`, across page breaks."""
    rows: list[dict] = []
    pages = [p for p in pdf.pages if title in (p.extract_text() or "")[:200]]
    if not pages:
        raise SourceUnreadable(f"no page titled {title!r}")
    for page in pages:
        xs = _dod_columns(page, header_y)
        if len(xs) != len(columns) + 1:
            raise SourceUnreadable(f"{title!r} p{page.page_number}: {len(xs) - 1} columns")
        rules = _dod_rules(page, xs[0], xs[1])
        if len(rules) < 3:
            raise SourceUnreadable(f"{title!r} p{page.page_number}: no rows")
        # rules[0] is the table's top edge and rules[1] the header row's bottom.
        for y0, y1 in zip(rules[1:], rules[2:], strict=False):
            cells = {
                c: _dod_cell(page.chars, xs[i], xs[i + 1], y0, y1) for i, c in enumerate(columns)
            }
            key = " ".join(cells[columns[0]])
            if row_id.fullmatch(key):
                rows.append({**cells, "id": key, "page": page.page_number})
            elif not key and rows:
                for c in columns[1:]:
                    rows[-1][c] = rows[-1][c] + cells[c]
            else:
                raise SourceUnreadable(f"{title!r} p{page.page_number}: ID cell {key!r}")
    return rows


def extract_dod(pdf_path: Path) -> dict:
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        caps = _dod_table(
            pdf,
            "DoD Zero Trust Capabilities",
            54.0,
            ("id", "name", "pillar", "description", "outcome", "impact", "activities"),
            _DOD_CAPABILITY,
        )
        acts = _dod_table(
            pdf,
            "DoD Zero Trust Activities",
            62.0,
            (
                "id",
                "name",
                "pillar",
                "responsibility",
                "type",
                "duration",
                "description",
                "outcomes",
                "end_state",
                "predecessors",
                "successors",
            ),
            _DOD_ACTIVITY,
        )
    capabilities = []
    for r in caps:
        m = _DOD_PILLAR.fullmatch(_join_lines(r["pillar"]))
        if m is None:
            raise SourceUnreadable(f"capability {r['id']}: pillar {r['pillar']!r}")
        capabilities.append(
            {
                "id": r["id"],
                "pillar_number": int(m.group(1)),
                "pillar": m.group(2),
                "name": _join_lines(r["name"]),
                "description": _join_lines(r["description"]),
                "outcome": _join_lines(r["outcome"]),
                "page": r["page"],
            }
        )
    activities = []
    for r in acts:
        kind = _join_lines(r["type"])
        if "Target" in kind:
            level = "target"
        elif "Advanced" in kind:
            level = "advanced"
        else:
            raise SourceUnreadable(f"activity {r['id']}: type {kind!r}")
        activities.append(
            {
                "id": r["id"],
                "name": _join_lines(r["name"]),
                "level": level,
                "description": _join_lines(r["description"]),
                "outcomes": _join_lines(r["outcomes"]),
                "end_state": _join_lines(r["end_state"]),
                "page": r["page"],
            }
        )
    return {
        "source": DOD_SOURCE,
        "roadmap_2022": DOD_ROADMAP_SOURCE,
        "extracted_with": "apps/api/scripts/extract_zt_sources.py (pdfplumber)",
        "capabilities": capabilities,
        "activities": activities,
    }


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
    p.add_argument("source", choices=("cisa", "dod"))
    p.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    repo = find_checkout(Path(__file__).resolve().parent)
    if repo is None:
        print("NO CHECKOUT: no reference-docs/ at or above this script", file=sys.stderr)
        return 2
    if args.source == "cisa":
        folder = repo / "reference-docs" / "cisa"
        pinned = [(folder / CISA_PDF_NAME, CISA_SOURCE["sha256"])]
        out_json, extract, unit = folder / CISA_JSON_NAME, extract_cisa, "rows"
    else:
        folder = repo / "reference-docs" / "dod"
        pinned = [
            (folder / DOD_PDF_NAME, DOD_SOURCE["sha256"]),
            (folder / DOD_ROADMAP_NAME, DOD_ROADMAP_SOURCE["sha256"]),
        ]
        out_json, extract, unit = folder / DOD_JSON_NAME, extract_dod, "activities"
    for pdf_path, sha in pinned:
        if not pdf_path.is_file():
            print(f"MISSING: {pdf_path}", file=sys.stderr)
            return 2
        try:
            got = _sha256(pdf_path)
        except OSError as exc:
            print(f"COULD NOT READ the PDF: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        if got != sha:
            print(f"NOT THE PINNED PDF: {pdf_path.name} sha256 {got}", file=sys.stderr)
            return 2
    try:
        data = extract(pinned[0][0])
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed: exit 2
        # Could-not-look is exit 2, distinct from DIFFERS (exit 1): a reader
        # that fails (a moved heading, another pdfplumber, a damaged file) says
        # nothing about whether the committed extraction is right.
        print(f"COULD NOT READ the PDF: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        out_json.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {out_json} ({len(data[unit])} {unit})")
        return 0
    if not out_json.is_file():
        print(f"NO COMMITTED EXTRACTION at {out_json}", file=sys.stderr)
        return 1
    try:
        committed = out_json.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(
            f"COULD NOT READ the committed extraction: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    if committed != text:
        print("DIFFERS from the committed extraction", file=sys.stderr)
        return 1
    print(f"matches the committed extraction ({len(data[unit])} {unit})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
