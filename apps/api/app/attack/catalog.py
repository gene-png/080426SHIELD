"""MITRE ATT&CK Enterprise catalog, GENERATED from MITRE's published STIX (#556).

The tactics and techniques come from `_catalog_data.py`, which
`scripts/generate_attack_catalog.py` writes from one `enterprise-attack-<version>.json`
in mitre-attack/attack-stix-data. `SOURCE` records the version, URL and sha256 of
that file, so the version this catalog claims is true by construction.

It replaced a hand-encoded list labelled "v15" that matched no released
version: 17 real techniques missing, T1558 and T1649 carrying each other's
names, four sub-technique IDs that do not exist, v16 additions on a v15 base,
and editorial suffixes such as "(also DE)" in client-facing names. Do not
edit the data by hand. Regenerate it.

Per D-007 the full Enterprise matrix is encoded, not a curated subset. The
catalog is reference data; only the engagement's coverage status per technique
lands in `attack_coverage` rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.attack._catalog_data import SOURCE, TACTICS_DATA, TECHNIQUES_DATA


@dataclass(frozen=True)
class Tactic:
    id: str  # e.g. "TA0043"
    shortname: str  # e.g. "reconnaissance"
    name: str
    description: str


@dataclass(frozen=True)
class Technique:
    id: str  # e.g. "T1003" or "T1003.001"
    name: str
    tactics: tuple[str, ...]  # tactic ids the technique maps to, in matrix order
    parent_id: str | None  # set only for sub-techniques
    is_sub_technique: bool


#: The MITRE release this catalog was generated from, e.g. "19.2".
SOURCE_VERSION: str = SOURCE["version"]

TACTICS: tuple[Tactic, ...] = tuple(Tactic(*row) for row in TACTICS_DATA)

TECHNIQUES: tuple[Technique, ...] = tuple(
    Technique(
        id=code,
        name=name,
        tactics=tuple(tactic_ids),
        parent_id=parent,
        is_sub_technique=parent is not None,
    )
    for code, name, tactic_ids, parent in TECHNIQUES_DATA
)

_TACTIC_BY_ID = {t.id: t for t in TACTICS}
_TECHNIQUE_BY_ID = {t.id: t for t in TECHNIQUES}


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------


def tactic_by_id(tactic_id: str) -> Tactic:
    return _TACTIC_BY_ID[tactic_id]


def technique_by_id(code: str) -> Technique:
    return _TECHNIQUE_BY_ID[code]


def techniques_for_tactic(tactic_id: str) -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if tactic_id in t.tactics)


def parent_techniques() -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if not t.is_sub_technique)


def sub_techniques(parent_id: str) -> tuple[Technique, ...]:
    return tuple(t for t in TECHNIQUES if t.parent_id == parent_id)


def all_codes() -> frozenset[str]:
    return frozenset(t.id for t in TECHNIQUES)


__all__ = [
    "SOURCE",
    "SOURCE_VERSION",
    "TACTICS",
    "TECHNIQUES",
    "Tactic",
    "Technique",
    "all_codes",
    "parent_techniques",
    "sub_techniques",
    "tactic_by_id",
    "technique_by_id",
    "techniques_for_tactic",
]
