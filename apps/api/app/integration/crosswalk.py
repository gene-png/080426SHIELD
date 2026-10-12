"""Load the crosswalks X1 and C1 (N10, for #1063; design note rev 5 §12).

X1  SP 800-53 rev5 control -> ATT&CK 19.2 technique (MITRE CTID, Apache-2.0).
C1  CSF 2.0 subcategory -> SP 800-53 Rev 5.1.1 control -> ATT&CK technique.

Both files are DERIVED offline by `scripts/derive_crosswalks.py` and committed;
`test_crosswalks.py` re-derives them byte for byte. Each file's sha256 is
pinned below, and a mismatch raises: a hand-edited or truncated file is never
read as a crosswalk, and nothing is ever returned empty in its place.

Three states for a subcategory, never two: `mapped` (rows), `no_mapping` (the
subcategory has SP 800-53 references but none reaches an ATT&CK technique),
and an unknown code, which raises KeyError. A known subcategory with NO SP
800-53 reference in X2 raises too (unreachable with the committed X2, where
all 106 carry one), so `no_mapping` always means "referenced, reaches nothing".
C1 being absent is a further case the caller sees as an exception, never as
"no conflict".

PARTLY MAPPED. A `mapped` subcategory can still list controls that reach no
technique (`controls_without_techniques`); a whole control family X2 names is
not expanded (`families_not_expanded`); and controls X2 names on the
subcategory's CATEGORY row are not composed into its rows
(`category_references_not_composed`, resolved from the code's category
prefix). All three travel with the result so a reader of the rows can say what
they do not cover.
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
        "9ad804731398e925c70fb4765f505496ecd93b33427d2c55940440c6e3e51b26",
    ),
    "c1": (
        "c1_csf_attack.json",
        "67546cb9666888acdfacf56c4c0395e6d01d9ce0ecdea1b7708c14fca7af1749",
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
    controls_without_techniques: tuple[str, ...] = ()
    families_not_expanded: tuple[str, ...] = ()
    category_references_not_composed: tuple[str, ...] = ()


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
    c1 = load_crosswalk("c1")
    rows = tuple(
        C1Row(r["subcategory"], r["control"], r["technique"])
        for r in c1.rows
        if r["subcategory"] == subcategory
    )
    header = c1.header
    if not rows and subcategory not in header["subcategories_without_a_mapping"]:
        revision = header["sp_800_53_revision"]
        other = [k for k in header["revision_difference"] if k.startswith("subcategories_only_in_")]
        for key in other:
            if subcategory in header["revision_difference"][key]:
                raise CrosswalkIntegrityError(
                    f"crosswalk c1: {subcategory} is referenced only under SP 800-53 Rev "
                    f"{key.removeprefix('subcategories_only_in_')}, not Rev {revision}"
                )
        raise CrosswalkIntegrityError(
            f"crosswalk c1: {subcategory} has no SP 800-53 reference in X2, so it is "
            "neither mapped nor unmapped"
        )
    category = subcategory.rsplit("-", 1)[0]
    return C1Result(
        status="mapped" if rows else "no_mapping",
        rows=rows,
        controls_without_techniques=tuple(
            header["controls_without_techniques_by_subcategory"].get(subcategory, ())
        ),
        families_not_expanded=tuple(header["family_references_not_expanded"].get(subcategory, ())),
        category_references_not_composed=tuple(
            header["category_references_not_composed"].get(category, ())
        ),
    )


__all__ = [
    "C1Result",
    "C1Row",
    "Crosswalk",
    "CrosswalkIntegrityError",
    "c1_techniques_for",
    "load_crosswalk",
]
