"""The ATT&CK catalog equals MITRE's published STIX for the version it claims (#556).

WHERE THE EXPECTED VALUES COME FROM. The committed subset under
`app/attack/stix/` holds MITRE's own objects, selected by type and otherwise
untouched. This module parses it with ITS OWN code -- not the generator's, not
the catalog's -- so a catalog that disagrees with MITRE cannot agree with this
test by construction (CLAUDE.md: a test that reads its expected value from the
thing under test cannot fail). The old test asserted only `len(TECHNIQUES) >=
600`, which the hand-encoded catalog passed while missing 17 real techniques
and swapping two names.

The literal pins at the bottom are the #556 defects themselves, stated as
facts about ATT&CK, so they fail if either defect returns.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.attack import catalog

pytestmark = pytest.mark.unit

STIX_DIR = Path(__file__).resolve().parents[2] / "app" / "attack" / "stix"


def _bundle() -> dict:
    path = STIX_DIR / catalog.SOURCE["subset"]
    assert path.is_file(), f"the STIX subset the catalog names is missing: {path}"
    return json.loads(gzip.decompress(path.read_bytes()))


def _ext_id(obj: dict) -> str:
    (ref,) = [r for r in obj["external_references"] if r.get("source_name") == "mitre-attack"]
    return ref["external_id"]


def _live(obj: dict) -> bool:
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def _mitre() -> tuple[list[tuple[str, str, str, str]], dict[str, tuple[str, frozenset[str], bool]]]:
    """(tactics in matrix order, {technique id: (name, tactic shortnames, is_sub)})."""
    objs = _bundle()["objects"]
    (matrix,) = [o for o in objs if o["type"] == "x-mitre-matrix" and _live(o)]
    tactic_objs = {o["id"]: o for o in objs if o["type"] == "x-mitre-tactic"}
    tactics = [
        (
            _ext_id(tactic_objs[ref]),
            tactic_objs[ref]["x_mitre_shortname"],
            tactic_objs[ref]["name"],
            tactic_objs[ref]["description"],
        )
        for ref in matrix["tactic_refs"]
    ]
    techniques = {}
    for o in objs:
        if o["type"] != "attack-pattern" or not _live(o):
            continue
        phases = frozenset(
            p["phase_name"]
            for p in o["kill_chain_phases"]
            if p["kill_chain_name"] == "mitre-attack"
        )
        techniques[_ext_id(o)] = (o["name"], phases, bool(o.get("x_mitre_is_subtechnique")))
    return tactics, techniques


def test_the_subset_is_the_version_the_catalog_claims() -> None:
    (coll,) = [o for o in _bundle()["objects"] if o["type"] == "x-mitre-collection"]
    assert coll["x_mitre_version"] == catalog.SOURCE_VERSION
    assert catalog.SOURCE["subset"] == f"enterprise-attack-{catalog.SOURCE_VERSION}.subset.json.gz"


def test_tactics_are_mitres_in_matrix_order() -> None:
    tactics, _ = _mitre()
    assert [(t.id, t.shortname, t.name) for t in catalog.TACTICS] == [
        (tid, short, name) for tid, short, name, _ in tactics
    ]
    for ours, (_, _, _, desc) in zip(catalog.TACTICS, tactics, strict=True):
        assert " ".join(desc.split()).startswith(ours.description), ours.id


def test_every_active_technique_and_only_those() -> None:
    _, techniques = _mitre()
    ours = catalog.all_codes()
    assert not (set(techniques) - ours), f"missing from catalog: {sorted(set(techniques) - ours)}"
    assert not (ours - set(techniques)), f"not active in ATT&CK: {sorted(ours - set(techniques))}"


def test_every_name_is_mitres_exactly() -> None:
    _, techniques = _mitre()
    wrong = {
        t.id: (t.name, techniques[t.id][0])
        for t in catalog.TECHNIQUES
        if t.name != techniques[t.id][0]
    }
    assert not wrong, wrong


def test_every_technique_maps_to_mitres_tactics() -> None:
    tactics, techniques = _mitre()
    short_of = {tid: short for tid, short, _, _ in tactics}
    wrong = {
        t.id: sorted(short_of[x] for x in t.tactics)
        for t in catalog.TECHNIQUES
        if frozenset(short_of[x] for x in t.tactics) != techniques[t.id][1]
    }
    assert not wrong, wrong


def test_sub_technique_flag_and_parent_match_mitre() -> None:
    _, techniques = _mitre()
    for t in catalog.TECHNIQUES:
        assert t.is_sub_technique == techniques[t.id][2], t.id
        assert t.parent_id == (t.id.split(".")[0] if t.is_sub_technique else None), t.id


def test_the_data_module_is_what_the_generator_writes() -> None:
    """A hand edit to `_catalog_data.py` fails here.

    This one DOES run the generator's own `build` -- over the committed subset
    -- so it proves "not edited by hand", and nothing about MITRE; the tests
    above cover that independently.
    """
    import scripts.generate_attack_catalog as gen

    from app.attack import _catalog_data as data

    tactics, techniques = gen.build(_bundle(), catalog.SOURCE_VERSION)
    assert tuple(tactics) == data.TACTICS_DATA
    assert tuple(techniques) == data.TECHNIQUES_DATA


# --- #556, pinned as facts about ATT&CK --------------------------------------


def test_t1558_is_kerberos_and_t1649_is_certificates() -> None:
    assert catalog.technique_by_id("T1558").name == "Steal or Forge Kerberos Tickets"
    assert catalog.technique_by_id("T1649").name == "Steal or Forge Authentication Certificates"


def test_the_kerberos_sub_techniques_live_under_t1558() -> None:
    assert {s.id for s in catalog.sub_techniques("T1558")} >= {
        "T1558.001",
        "T1558.002",
        "T1558.003",
        "T1558.004",
    }
    assert catalog.sub_techniques("T1649") == ()
    assert not {"T1649.001", "T1649.002", "T1649.003", "T1649.004"} & catalog.all_codes()


def test_subvert_trust_controls_is_present() -> None:
    assert "T1553" in catalog.all_codes()


def test_no_editorial_suffix_reaches_a_name() -> None:
    marked = [t.id for t in catalog.TECHNIQUES if "(also" in t.name or "alias listed" in t.name]
    assert not marked, marked
