#!/usr/bin/env python
"""Fail when DELIVERY_PLAN.md's stated total does not equal the sum of its parts.

WHY THIS IS A CHECK. A schedule whose parts do not sum to its total is the same
defect as a status line that is wrong: it is a number someone will act on that
nothing produced. It has now happened twice in this repo, both times by someone
who had just written the rule against it -- once as "10.5-13.5" over parts
summing to 10-14.5, and once as "12-18.5" over parts summing to 11.5-17.5, in a
section literally headed "and the parts sum to it". The second was caught by an
adversarial review, not by the sentence one paragraph above it.

Two instances by authors who knew the shape is D-051's argument exactly, so this
follows the same route as the control-character gate: a deterministic,
stdlib-only, sub-second check rather than a third paragraph of prose.

## What it checks

The estimate table under the "Total remaining" heading in DELIVERY_PLAN.md. Rows
look like:

    | 10 - redaction boundary (#135-#140) | 1.5-2.5 |
    | **Total** | **11.5-17.5** |

It sums every non-total row's range and compares to the stated total. Ranges may
be a single number ("1") or lo-hi ("1.5-2.5"), with either a hyphen or an en
dash. The heading is also checked, because the total is written twice and drift
between the two is its own defect.

## What it does NOT do

It does not check the per-item Estimate column of the MVP path table against
this one. Those are deliberately allowed to differ: the path table carries prose
and re-size notes, this table carries the arithmetic. Cross-checking them would
demand a parser for the prose column and would fail on wording, not on numbers.

**It does not check PROSE restatements of the total, and that is where the last
instance actually lived.** The corrected table shipped twenty lines above a
paragraph still opening "12-18.5 is a 54%-wide range" -- a live wrong total, in
the PR that added this gate. A scan for it was written, measured, and
**rejected**: the paragraph contains no "sessions" to key on, so the rule has to
be "any range in this discussion that is not the total", and over the real
document that fires on dates (`2026-08-22`), hour ranges (`4-8 hours`,
`46-140 hours`), ratios (`2-4x`), and the per-item sizings the same paragraphs
legitimately quote (`from 3-4 to 4-6`) -- twelve false positives against one true
one -- 1 real finding in 13, a signal of **7.7%**.

That is not merely consistent with an existing decision here, it falls below a
threshold this repo has already judged unshippable. `check_test_integrity.py`'s
TI001 was narrowed after measuring "41 findings of which 36 are override handles;
restricting to constant-style names gives 5" -- 5 in 41, **12.2%** -- under the
stated reasoning that "a rule whose signal is 12% of its output gets muted, and a
muted rule is worth nothing". 7.7% < 12.2%, so this rule is refused a fortiori by
the precedent rather than by a fresh judgement call. A gate that fails for reasons unrelated to the defect gets switched
off, which is worse than not having it.

So this half stays human: **when the total changes, grep the section for the old
number.** The gate covers the arithmetic, which is mechanical; it does not cover
the retelling, which is not.

EXIT CODES, per this repo's fail-closed convention (D-051):
  0 - the parts sum to the stated total
  1 - they do not
  2 - the table could not be found or parsed (an unreadable input is NOT a pass)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_DASH = "–"  # en dash, which prettier leaves in place

# Column headers, skipped by name rather than by "it did not parse" -- so that
# branch is free to mean only "I could not read this".
_HEADER_LABELS = {"item", "work", "step", ""}


def _norm(text: str) -> str:
    return text.replace(_DASH, "-").replace("**", "").strip()


def _parse_range(cell: str) -> tuple[float, float] | None:
    """'1.5-2.5' -> (1.5, 2.5); '1' -> (1.0, 1.0); anything else -> None."""
    cell = _norm(cell)
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", cell)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)", cell)
    if m:
        return float(m.group(1)), float(m.group(1))
    return None


def check(plan_text: str) -> tuple[int, list[str]]:
    lines = plan_text.split("\n")

    start = next(
        (i for i, line in enumerate(lines) if _norm(line).startswith("### Total remaining")),
        None,
    )
    if start is None:
        return 2, ["no '### Total remaining' heading in DELIVERY_PLAN.md"]

    heading = _norm(lines[start])
    heading_range = None
    m = re.search(r"(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?)", heading)
    if m:
        heading_range = _parse_range(m.group(1))

    parts: list[tuple[str, tuple[float, float]]] = []
    skipped: list[str] = []
    stated: tuple[float, float] | None = None
    for line in lines[start + 1 :]:
        if _norm(line).startswith("###"):
            break
        if not line.strip().startswith("|"):
            continue
        cells = line.strip().strip("|").split("|")
        if len(cells) < 2:
            continue
        label, value = _norm(cells[0]), cells[-1]
        if set(label) <= {"-", " "}:  # the |---|---| separator row
            continue
        if label.lower() in _HEADER_LABELS:  # the | Item | Estimate | header
            continue
        parsed = _parse_range(value)
        if parsed is None:
            # NOT `continue`. A row whose estimate does not parse is a row this
            # check COULD NOT READ, and dropping it silently is the defect the
            # whole file exists to prevent: the sum would be over fewer items
            # than the table displays, and the cheapest way to green would be to
            # change the Total to match the short sum -- the gate steering the
            # author into writing a total that omits an item.
            #
            # The house style one table up in DELIVERY_PLAN.md already annotates
            # estimates ("**4-6 sessions** (re-sized 2026-08-25 ...)"), so this
            # is a formatting choice away, not hypothetical.
            skipped.append(f"{label} -> {_norm(value)!r}")
            continue
        if label.lower() == "total":
            stated = parsed
        else:
            parts.append((label, parsed))

    if skipped:
        return 2, [
            "these rows have an estimate this check cannot parse, so the sum",
            "would silently be over fewer items than the table shows:",
            "",
            *[f"  {row}" for row in skipped],
            "",
            "Use a bare range in the Estimate cell (`1.5-2.5`) and put any note",
            "in the item label, or in prose under the table.",
        ]
    if not parts:
        return 2, ["found the heading but no parseable item rows under it"]
    if stated is None:
        return 2, ["found item rows but no '| **Total** |' row"]

    lo = round(sum(p[1][0] for p in parts), 4)
    hi = round(sum(p[1][1] for p in parts), 4)
    problems: list[str] = []

    if (lo, hi) != (round(stated[0], 4), round(stated[1], 4)):
        problems.append(
            f"table total says {stated[0]:g}-{stated[1]:g}, "
            f"but the {len(parts)} item rows sum to {lo:g}-{hi:g}"
        )
    if heading_range is None:
        problems.append("the '### Total remaining' heading states no range")
    elif heading_range != (round(stated[0], 4), round(stated[1], 4)):
        problems.append(
            f"heading says {heading_range[0]:g}-{heading_range[1]:g} "
            f"but the table's Total row says {stated[0]:g}-{stated[1]:g}"
        )

    if problems:
        problems.append("")
        problems.append("Rows counted:")
        for label, (a, b) in parts:
            problems.append(f"  {a:>5g}-{b:<5g}  {label}")
        return 1, problems

    return 0, [f"plan totals: {lo:g}-{hi:g} across {len(parts)} items, heading and table agree"]


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("DELIVERY_PLAN.md")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"check-plan-totals: cannot read {path}: {type(exc).__name__}")
        return 2

    code, messages = check(text)
    prefix = "check-plan-totals"
    if code == 0:
        print(f"{prefix}: {messages[0]}")
    else:
        print(f"{prefix}: FAILED" if code == 1 else f"{prefix}: could not parse")
        for line in messages:
            safe = line.encode("ascii", "replace").decode()
            print(f"  {safe}" if line else "")
    return code


if __name__ == "__main__":
    # A crash must NOT share an exit code with "violations found". Python exits
    # 1 on an unhandled exception, which is this gate's "found something" code,
    # so an uncaught error would read as a verdict it never reached.
    #
    # `BaseException` with both propagating cases NAMED, rather than the
    # equivalent `except Exception`: a handler that says out loud what it
    # declines to swallow does not rely on the reader knowing the inheritance
    # tree. `SystemExit` is somebody's deliberate exit code. `KeyboardInterrupt`
    # is an operator who knows exactly what happened and is owed 130, not
    # "could not look".
    #
    # Duplicated verbatim in all eight gates rather than shared -- an import is
    # one more thing that can fail BEFORE the handler is installed, which is the
    # defect this block exists to close. Drift is caught instead by
    # tests/unit/test_gate_crash_exit_code.py, which runs every one of them.
    try:
        raise SystemExit(main(sys.argv))
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException as exc:  # noqa: BLE001 - deliberate: crash != verdict
        nl = chr(10)
        sys.stderr.write(f"check-plan-totals: CRASHED: {type(exc).__name__}: {exc}{nl}")
        sys.stderr.write(f"A crash is not a clean report and not a violation (D-051).{nl}")
        raise SystemExit(2) from exc
