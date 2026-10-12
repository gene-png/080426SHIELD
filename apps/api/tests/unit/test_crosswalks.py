"""Crosswalks X1 and C1, and the ATT&CK 19.2 revocations they translate through
(N10, for #1063; track D design note rev 5 §12, rulings #736 6126886407 and
6127667643).

Expected values are TYPED here from the sources' own published facts or from a
hand trace of the vendored inputs, never read through the loader (CLAUDE.md,
#72). The determinism test is the one place the derivation runs, and it
compares bytes, so a hand edit to a data file cannot drift from its sources.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from app.attack._catalog_data import SOURCE
from app.integration import crosswalk
from app.integration.crosswalk import (
    C1Result,
    CrosswalkIntegrityError,
    c1_techniques_for,
    load_crosswalk,
)

pytestmark = pytest.mark.unit

API = Path(__file__).resolve().parents[2]
DATA = API / "app" / "integration" / "data"
SUBSET = API / "app" / "attack" / "stix" / "enterprise-attack-19.2.subset.json.gz"


def _revocations() -> dict:
    return json.loads((DATA / "attack_revocations_19.2.json").read_text(encoding="utf-8"))


# --- The revocations file -----------------------------------------------------------


def test_revocations_come_from_the_pinned_19_2_bundle() -> None:
    header = _revocations()["header"]
    assert header["source_sha256"] == SOURCE["sha256"]
    assert header["source_url"] == SOURCE["url"]
    assert header["attack_version"] == "19.2"
    assert len(header["attack_stix_data_commit"]) == 40


def test_every_revoked_technique_in_the_vendored_subset_has_a_pair() -> None:
    with gzip.open(SUBSET) as handle:
        subset = json.loads(handle.read())["objects"]
    revoked = set()
    for obj in subset:
        if obj.get("type") == "attack-pattern" and obj.get("revoked"):
            refs = [r for r in obj["external_references"] if r["source_name"] == "mitre-attack"]
            revoked.add(refs[0]["external_id"])
    paired = {p["old"] for p in _revocations()["revoked_by"]}
    missing = sorted(revoked - paired)
    # Counted, never dropped: a revoked technique with no replacement would be
    # named here. MITRE's 19.2 bundle pairs every one.
    assert missing == []
    assert len(revoked) == 149


@pytest.mark.parametrize(
    "old,new",
    [
        # MITRE's published revocations (attack.mitre.org, each old ID's page).
        ("T1086", "T1059.001"),  # PowerShell
        ("T1088", "T1548.002"),  # Bypass User Account Control
        ("T1050", "T1543.003"),  # New Service -> Windows Service
        ("T1060", "T1547.001"),  # Registry Run Keys / Startup Folder
        ("T1085", "T1218.011"),  # Rundll32
    ],
)
def test_known_revocation_pairs(old: str, new: str) -> None:
    assert {"old": old, "new": new} in _revocations()["revoked_by"]


def test_scripting_is_deprecated_not_revoked() -> None:
    # T1064 Scripting was deprecated in ATT&CK v7, with no replacement.
    data = _revocations()
    assert "T1064" in data["deprecated"]
    assert all(p["old"] != "T1064" for p in data["revoked_by"])


def test_revocations_are_sorted_for_reviewable_diffs() -> None:
    data = _revocations()
    pairs = [(p["old"], p["new"]) for p in data["revoked_by"]]
    assert pairs == sorted(pairs)
    assert data["deprecated"] == sorted(data["deprecated"])


# --- X1 and C1 headers (typed from the sources) ------------------------------------


def test_x1_header_names_its_source_and_versions() -> None:
    header = load_crosswalk("x1").header
    assert header["source_commit"] == "a85e55af3c9fa55359a98621745b9b039a088bec"
    assert header["source_sha256"] == (
        "355ae97d309c00eb2428e5af07754ff4ca16cfe63928194081d0e883aed929c8"
    )
    assert header["licence"] == "Apache-2.0"
    assert header["attack_version_source"] == "16.1"
    assert header["attack_version_target"] == "19.2"
    # The CTID file's own counts: 5,410 mapping objects, 96 non-mappable.
    assert header["mapping_objects_total"] == 5410
    assert header["skipped_non_mappable"] == 96


def test_x1_discloses_every_untranslated_id_with_a_reason() -> None:
    header = load_crosswalk("x1").header
    for entry in header["untranslated"]:
        assert entry["reason"] in ("absent_from_19.2", "deprecated_in_19.2", "revocation_cycle")
    # T1521.003 (a mobile technique in CTID's enterprise file) is not in 19.2.
    assert {"id": "T1521.003", "reason": "absent_from_19.2"} in header["untranslated"]


def test_x1_translates_a_revoked_16_1_id() -> None:
    # T1086 PowerShell (16.1-era ID in some CTID rows) must never survive as a
    # target; every target is an active 19.2 technique.
    from app.attack.catalog import all_codes

    rows = load_crosswalk("x1").rows
    assert all(r["technique"] in all_codes() for r in rows)
    assert any(r["technique"] != r["attack_16_1"] for r in rows)


def test_c1_header_records_the_revision_and_its_difference() -> None:
    header = load_crosswalk("c1").header
    assert header["sp_800_53_revision"] == "5.1.1"
    assert header["x2_sha256"] == (
        "d83fbc04ea146e3ed4cacd3594351beab2359ae835669d607228528b43bb31a7"
    )
    assert header["revision_difference"] == {
        "only_in_5.2.0": ["RA-04", "SA-15(13)", "SA-24", "SI-02(07)"],
        "x1_maps_any_of_them": False,
    }
    # The README: 106 subcategories carry SP 800-53 references.
    assert header["subcategories_with_sp_800_53"] == 106
    assert header["third_party_lines_ignored"] > 0


def test_c1_contains_only_sp_800_53_controls() -> None:
    import re

    for row in load_crosswalk("c1").rows:
        assert re.fullmatch(r"[A-Z]{2}-\d{2}(\(\d{2}\))?", row["control"]), row


# --- C1 lookups -----------------------------------------------------------------------


def test_a_hand_traced_c1_path() -> None:
    # Hand trace: X2 lists "SP 800-53 Rev 5.1.1: AC-02" under PR.AA-01, and
    # CTID's X1 maps AC-02 "mitigates" T1078 Valid Accounts.
    result = c1_techniques_for("PR.AA-01")
    assert result.status == "mapped"
    assert any(r.control == "AC-02" and r.technique == "T1078" for r in result.rows)


def test_a_subcategory_with_no_mapping_is_its_own_state() -> None:
    # GV.OC-01's SP 800-53 controls (program-level) have no CTID mapping.
    result = c1_techniques_for("GV.OC-01")
    assert result == C1Result(status="no_mapping", rows=())


def test_an_unknown_subcategory_raises() -> None:
    with pytest.raises(KeyError):
        c1_techniques_for("ZZ.ZZ-99")


# --- Integrity and determinism ------------------------------------------------------


def test_a_data_file_that_does_not_match_its_pin_raises(tmp_path: Path, monkeypatch) -> None:
    bad = tmp_path / "x1_80053_attack.json"
    bad.write_bytes((DATA / "x1_80053_attack.json").read_bytes() + b" ")
    monkeypatch.setattr(crosswalk, "DATA", tmp_path)
    crosswalk.load_crosswalk.cache_clear()
    try:
        with pytest.raises(CrosswalkIntegrityError):
            load_crosswalk("x1")
    finally:
        crosswalk.load_crosswalk.cache_clear()


def test_an_unknown_crosswalk_name_raises() -> None:
    with pytest.raises(KeyError):
        load_crosswalk("x9")


def test_the_committed_files_equal_a_fresh_derivation() -> None:
    import sys

    sys.path.insert(0, str(API / "scripts"))
    try:
        import derive_crosswalks
    finally:
        sys.path.remove(str(API / "scripts"))
    outputs = derive_crosswalks.derive(derive_crosswalks.nist_dir())
    for name, data in outputs.items():
        committed = (DATA / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == hashlib.sha256(committed).hexdigest(), name
