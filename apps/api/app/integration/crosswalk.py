"""Load the crosswalks X1 and C1 (N10, for #1063; design note rev 5 §12).

X1  SP 800-53 rev5 control -> ATT&CK 19.2 technique (MITRE CTID, Apache-2.0).
C1  CSF 2.0 subcategory -> SP 800-53 Rev 5.1.1 control -> ATT&CK technique.

Both files are DERIVED offline by `scripts/derive_crosswalks.py` and committed;
`test_crosswalks.py` re-derives them byte for byte. Each file's sha256 is
pinned below, and a mismatch raises: a hand-edited or truncated file is never
read as a crosswalk, and nothing is ever returned empty in its place.

Three states for a subcategory, never two: `mapped` (rows), `no_mapping` (the
subcategory has SP 800-53 references but none reaches an ATT&CK technique),
and an unknown code, which raises KeyError. C1 being absent is a fourth case
the caller sees as an exception, never as "no conflict".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Literal

from app.csf.catalog import all_codes as csf_codes
from app.logging import get_logger

_log = get_logger(__name__)

DATA = Path(__file__).resolve().parent / "data"

#: Pinned by sha256; regenerate with `scripts/derive_crosswalks.py`, then update
#: these two values in the same commit as the data files.
CROSSWALK_FILES: dict[str, tuple[str, str]] = {
    "x1": (
        "x1_80053_attack.json",
        "115fbacfcd6cdcff1f1a56189409c1cf1bdfaf135d4bdcd738b2cea473ae3281",
    ),
    "c1": (
        "c1_csf_attack.json",
        "b6c0131dd86d72b8394a7655f8ffa87cae6fa7364f6f62f6b72507ebe6faaf82",
    ),
}


class CrosswalkIntegrityError(ValueError):
    """A crosswalk file is missing or does not match its pinned sha256."""


@dataclass(frozen=True)
class Crosswalk:
    name: str
    header: dict[str, Any]
    rows: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class C1Row:
    subcategory: str
    control: str
    technique: str


@dataclass(frozen=True)
class C1Result:
    status: Literal["mapped", "no_mapping"]
    rows: tuple[C1Row, ...]


@cache
def load_crosswalk(name: str) -> Crosswalk:
    """The named crosswalk ("x1" or "c1"). Unknown name: KeyError. Missing or
    altered file: CrosswalkIntegrityError."""
    filename, pinned = CROSSWALK_FILES[name]
    path = DATA / filename
    if not path.is_file():
        raise CrosswalkIntegrityError(f"crosswalk {name}: {path} is missing")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != pinned:
        raise CrosswalkIntegrityError(
            f"crosswalk {name}: sha256 {digest} does not equal the pinned {pinned}"
        )
    parsed = json.loads(data)
    crosswalk = Crosswalk(name, parsed["header"], tuple(parsed["rows"]))
    _log.info("crosswalk.loaded", name=name, rows=len(crosswalk.rows), sha256=digest)
    return crosswalk


def c1_techniques_for(subcategory: str) -> C1Result:
    """C1's rows for one CSF 2.0 subcategory, each with its control path."""
    if subcategory not in csf_codes():
        raise KeyError(f"crosswalk c1: unknown CSF subcategory {subcategory!r}")
    rows = tuple(
        C1Row(r["subcategory"], r["control"], r["technique"])
        for r in load_crosswalk("c1").rows
        if r["subcategory"] == subcategory
    )
    return C1Result(status="mapped" if rows else "no_mapping", rows=rows)


__all__ = [
    "C1Result",
    "C1Row",
    "Crosswalk",
    "CrosswalkIntegrityError",
    "c1_techniques_for",
    "load_crosswalk",
]
