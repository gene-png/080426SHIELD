"""Which ATT&CK techniques "cannot be prevented" equals MITRE's published STIX (#554 R3).

The advisor's decision (Q2, 2026-10-02): a technique cannot be prevented when
MITRE ATT&CK lists no preventive control for it, which is either of

* **pre-compromise** -- MITRE maps M1056 "Pre-compromise" to it, the mitigation
  whose text reads "cannot be easily mitigated with preventive controls";
* **no mitigation** -- MITRE maps no mitigation to it at all.

WHERE THE EXPECTED VALUES COME FROM. The committed subset under
`app/attack/stix/` holds MITRE's own `mitigates` relationships and
`course-of-action` objects. This module parses them with ITS OWN code, never
the generator's, so a set that disagrees with MITRE cannot agree with this test
by construction. The literal pins at the bottom are facts about ATT&CK 19.2,
measured on MITRE's published file on 2026-10-02.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.attack import catalog

pytestmark = pytest.mark.unit

STIX_DIR = Path(__file__).resolve().parents[2] / "app" / "attack" / "stix"


def _objects() -> list[dict]:
    path = STIX_DIR / catalog.SOURCE["subset"]
    return json.loads(gzip.decompress(path.read_bytes()))["objects"]


def _ext_id(obj: dict) -> str:
    (ref,) = [r for r in obj["external_references"] if r.get("source_name") == "mitre-attack"]
    return ref["external_id"]


def _live(obj: dict) -> bool:
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def _mitre_not_preventable() -> dict[str, str]:
    """{technique id: basis}, read from MITRE's relationships."""
    objs = _objects()
    techniques = {o["id"]: _ext_id(o) for o in objs if o["type"] == "attack-pattern" and _live(o)}
    mitigations = {
        o["id"]: _ext_id(o) for o in objs if o["type"] == "course-of-action" and _live(o)
    }
    mapped: dict[str, set[str]] = {code: set() for code in techniques.values()}
    for o in objs:
        if (
            o["type"] == "relationship"
            and o["relationship_type"] == "mitigates"
            and _live(o)
            and o["source_ref"] in mitigations
            and o["target_ref"] in techniques
        ):
            mapped[techniques[o["target_ref"]]].add(mitigations[o["source_ref"]])
    out: dict[str, str] = {}
    for code, ms in mapped.items():
        if "M1056" in ms:
            out[code] = catalog.NOT_PREVENTABLE_PRE_COMPROMISE
        elif not ms:
            out[code] = catalog.NOT_PREVENTABLE_NO_MITIGATION
    return out


def test_the_subset_carries_mitres_mitigations() -> None:
    types = {o["type"] for o in _objects()}
    assert {"relationship", "course-of-action"} <= types
    (m1056,) = [o for o in _objects() if o["type"] == "course-of-action" and _ext_id(o) == "M1056"]
    assert m1056["name"] == "Pre-compromise"


def test_the_set_is_mitres_exactly() -> None:
    expected = _mitre_not_preventable()
    ours = {code: catalog.not_preventable_basis(code) for code in catalog.NOT_PREVENTABLE}
    assert ours == expected


def test_every_other_catalogue_technique_is_preventable() -> None:
    expected = _mitre_not_preventable()
    for code in catalog.all_codes() - set(expected):
        assert catalog.not_preventable_basis(code) is None, code
        assert code not in catalog.NOT_PREVENTABLE


def test_a_code_outside_the_catalogue_raises() -> None:
    with pytest.raises(KeyError):
        catalog.not_preventable_basis("T9999")


def test_the_data_module_is_what_the_generator_writes() -> None:
    import scripts.generate_attack_catalog as gen

    from app.attack import _catalog_data as data

    bundle = {"objects": _objects()}
    assert tuple(gen.not_preventable(bundle)) == data.NOT_PREVENTABLE_DATA


# --- ATT&CK 19.2, measured on MITRE's file 2026-10-02 -------------------------


def test_the_counts_are_19_2s() -> None:
    bases = [catalog.not_preventable_basis(c) for c in catalog.NOT_PREVENTABLE]
    assert bases.count("pre_compromise") == 88
    assert bases.count("no_mitigation") == 111
    assert len(catalog.NOT_PREVENTABLE) == 199


@pytest.mark.parametrize(
    ("code", "basis"),
    [
        ("T1082", "no_mitigation"),  # System Information Discovery
        ("T1057", "no_mitigation"),  # Process Discovery
        ("T1583", "pre_compromise"),  # Acquire Infrastructure
        ("T1583.001", "pre_compromise"),
        ("T1059", None),  # Command and Scripting Interpreter has mitigations
        ("T1003.001", None),  # LSASS Memory has mitigations
    ],
)
def test_pinned_techniques(code: str, basis: str | None) -> None:
    assert catalog.not_preventable_basis(code) == basis
