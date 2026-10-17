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
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from app.attack._catalog_data import SOURCE
from app.integration import crosswalk
from app.integration.crosswalk import (
    CrosswalkIntegrityError,
    c1_techniques_for,
    load_crosswalk,
)

pytestmark = pytest.mark.unit

API = Path(__file__).resolve().parents[2]
DATA = API / "app" / "integration" / "data"
SUBSET = API / "app" / "attack" / "stix" / "enterprise-attack-19.2.subset.json.gz"


def _script(name: str) -> ModuleType:
    """Load `scripts/<name>.py` by path (the scripts directory is not a package
    on the test path)."""
    spec = importlib.util.spec_from_file_location(name, API / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    # Hand counts of the CTID file (it carries no counts of its own): 5,410
    # mapping objects, 96 of them non-mappable.
    assert header["mapping_objects_total"] == 5410
    assert header["skipped_non_mappable"] == 96


def test_x1_accounts_for_every_mapping_object() -> None:
    # Hand count of the CTID file: 5,314 `mitigates` objects, of which 5,264
    # distinct (control, technique) pairs; the 50 others repeat an earlier
    # object in EVERY field (e.g. IA-09 / T1036 Masquerading, twice). One
    # object (T1521.003) has no 19.2 technique. 5,410 = 96 + 1 + 50 + 5,263.
    # The identity below cannot go red by construction (derive_x1 sends every
    # object to exactly one counter); its force is the TYPED 1, 50 and 5,263.
    header = load_crosswalk("x1").header
    assert header["untranslated_rows"] == 1
    assert header["duplicate_rows"] == 50
    assert header["rows"] == 5263
    assert header["mapping_objects_total"] == (
        header["skipped_non_mappable"]
        + header["untranslated_rows"]
        + header["duplicate_rows"]
        + header["rows"]
    )
    assert len(load_crosswalk("x1").rows) == header["rows"]


def test_x1_rows_are_triples_so_two_16_1_ids_can_reach_one_technique() -> None:
    # MITRE 19.2 revokes both T1562 Impair Defenses and T1562.001 Disable or
    # Modify Tools into T1685; CTID maps SI-04 to both, so SI-04 -> T1685 is
    # two rows, one per 16.1 source, never collapsed.
    rows = load_crosswalk("x1").rows
    sources = {
        r["attack_16_1"] for r in rows if (r["control"], r["technique"]) == ("SI-04", "T1685")
    }
    assert {"T1562", "T1562.001"} <= sources
    header = load_crosswalk("x1").header
    # 5,236 distinct (control, 19.2 technique) pairs, counted by the
    # coordinator from the committed rows on #1105 round 2, independently of
    # derive_x1: 27 fewer than the 5,263 triples.
    assert header["control_technique_pairs"] == 5236


def test_x1_discloses_every_untranslated_id_with_a_reason() -> None:
    header = load_crosswalk("x1").header
    for entry in header["untranslated"]:
        assert entry["reason"] in ("absent_from_19.2", "deprecated_in_19.2", "revocation_cycle")
    # T1521.003 (a mobile technique in CTID's enterprise file) is not in 19.2.
    assert {"id": "T1521.003", "reason": "absent_from_19.2"} in header["untranslated"]


def test_x1_translates_a_revoked_16_1_id() -> None:
    # Hand trace: CTID maps SI-02 "mitigates" T1574.002 DLL Side-Loading, and
    # MITRE revoked T1574.002 into T1574.001 (Hijack Execution Flow: DLL).
    rows = load_crosswalk("x1").rows
    pair = {"control": "SI-02", "technique": "T1574.001", "attack_16_1": "T1574.002"}
    assert pair in rows
    assert all(r["attack_16_1"] != "T1574.002" or r["technique"] == "T1574.001" for r in rows)


def test_every_x1_target_is_an_active_19_2_technique() -> None:
    from app.attack.catalog import all_codes

    assert all(r["technique"] in all_codes() for r in load_crosswalk("x1").rows)


def test_c1_header_records_the_revision_and_its_difference() -> None:
    header = load_crosswalk("c1").header
    assert header["sp_800_53_revision"] == "5.1.1"
    assert header["x2_sha256"] == (
        "d83fbc04ea146e3ed4cacd3594351beab2359ae835669d607228528b43bb31a7"
    )
    # Hand trace: the family and category lines read the same in both
    # revisions, and no subcategory is referenced only under 5.2.0.
    assert header["revision_difference"] == {
        "only_in_5.2.0": ["RA-04", "SA-15(13)", "SA-24", "SI-02(07)"],
        "x1_maps_any_of_them": False,
        "families_only_in_5.2.0": {},
        "category_references_only_in_5.2.0": {},
        "subcategories_only_in_5.2.0": [],
    }
    # Every one of the CSF 2.0 catalog's 106 subcategories carries an SP 800-53
    # Rev 5.1.1 line in X2 (the catalog's own count, and a read of the export).
    from app.csf.catalog import all_codes as csf_codes

    assert header["subcategories_with_sp_800_53"] == 106 == len(csf_codes())
    # Non-SP 800-53 lines, counted straight from the export with openpyxl, per
    # row kind: subcategory, category and function rows all carry them.
    assert header["third_party_lines_ignored"] == {
        "subcategory": 4594,
        "category": 480,
        "function": 54,
    }


def test_c1_discloses_the_sp_800_53_lines_it_does_not_compose() -> None:
    # Hand trace of the X2 export. Two subcategories name a whole control
    # FAMILY ("SP 800-53 Rev 5.1.1: PT"), and two CATEGORY rows carry
    # references of their own. Neither is composed into rows (expanding a
    # family, or pushing a category's controls onto its subcategories, is an
    # inference); both are disclosed, never counted as third-party.
    header = load_crosswalk("c1").header
    assert header["family_references_not_expanded"] == {
        "GV.OC-03": ["PT"],
        "PR.IR-03": ["CP", "IR"],
    }
    assert header["category_references_not_composed"] == {
        "RC.RP": ["CP-04", "CP-10"],
        "RS.MA": ["IR-04", "IR-07", "IR-08", "IR-09"],
    }


def test_c1_explains_every_x2_row_without_a_subcategory() -> None:
    # Hand count of the export's 48 such rows: the title and the column header,
    # 12 function rows (a heading and a closing row for each of six functions),
    # and 34 category rows (22 CSF 2.0 categories and 12 withdrawn 1.1 ones).
    header = load_crosswalk("c1").header
    assert header["x2_rows_without_a_subcategory"] == {"other": 2, "function": 12, "category": 34}


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
    assert result.status == "no_mapping"
    assert result.rows == ()
    assert result.controls_without_techniques  # it HAS references; none reach


def test_a_partly_mapped_subcategory_names_the_controls_that_reach_nothing() -> None:
    # Hand trace: X2 lists AU-06 and IR-04 under DE.AE-02; CTID maps neither.
    # SI-04, also listed, does reach techniques.
    result = c1_techniques_for("DE.AE-02")
    assert result.status == "mapped"
    assert any(r.control == "SI-04" for r in result.rows)
    assert result.controls_without_techniques == ("AU-06", "IR-04")
    assert all(r.control not in ("AU-06", "IR-04") for r in result.rows)


def test_a_category_reference_reaches_the_lookup() -> None:
    # Hand trace: X2's RC.RP category row names CP-04 and CP-10 (X1 maps
    # CP-10 to techniques); RC.RP-04 itself reaches nothing. The category's
    # controls are disclosed with the result, never composed into its rows.
    result = c1_techniques_for("RC.RP-04")
    assert result.status == "no_mapping"
    assert result.category_references_not_composed == ("CP-04", "CP-10")
    # RC.RP-03 is mapped through its own CP-02 and CP-09 and names neither
    # category control, so the category's are disclosed beside its rows.
    mapped = c1_techniques_for("RC.RP-03")
    assert mapped.status == "mapped"
    assert mapped.category_references_not_composed == ("CP-04", "CP-10")
    assert all(r.control not in ("CP-04", "CP-10") for r in mapped.rows)
    # RC.RP-01 names CP-10 on its OWN row in X2, so CP-10 is composed there
    # from that line, not from the category's.
    assert any(r.control == "CP-10" for r in c1_techniques_for("RC.RP-01").rows)
    assert c1_techniques_for("PR.AA-01").category_references_not_composed == ()


def test_a_family_reference_reaches_the_lookup() -> None:
    assert c1_techniques_for("PR.IR-03").families_not_expanded == ("CP", "IR")
    assert c1_techniques_for("PR.AA-01").families_not_expanded == ()


def test_a_subcategory_with_no_sp_800_53_reference_raises(monkeypatch) -> None:
    # Unreachable with the committed X2 (all 106 carry one); a future export
    # with such a subcategory must not read as "no_mapping".
    real = load_crosswalk("c1")
    header = dict(real.header)
    header["subcategories_without_a_mapping"] = [
        c for c in header["subcategories_without_a_mapping"] if c != "GV.OC-01"
    ]
    fake = crosswalk.Crosswalk("c1", header, real.rows)
    monkeypatch.setattr(crosswalk, "load_crosswalk", lambda name: fake)
    with pytest.raises(CrosswalkIntegrityError, match="no SP 800-53 reference"):
        c1_techniques_for("GV.OC-01")
    # Referenced ONLY under the other revision is a different cause, named.
    header["revision_difference"] = {
        **header["revision_difference"],
        "subcategories_only_in_5.2.0": ["GV.OC-01"],
    }
    with pytest.raises(CrosswalkIntegrityError, match="only under SP 800-53 Rev 5.2.0"):
        c1_techniques_for("GV.OC-01")


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


# --- The derivation scripts, offline and synthetic ------------------------------------


def test_revocations_derive_refuses_a_bundle_off_its_pin() -> None:
    script = _script("derive_attack_revocations")
    with pytest.raises(script.Refused, match="does not equal the pinned"):
        script.derive(b'{"objects": []}', commit="0" * 40, generated="2026-10-12")


def _bundle(*objects: dict) -> bytes:
    return json.dumps({"objects": list(objects)}).encode()


def _technique(stix_id: str, attack_id: str, **extra) -> dict:
    refs = [{"source_name": "mitre-attack", "external_id": attack_id}]
    return {"type": "attack-pattern", "id": stix_id, "external_references": refs, **extra}


def _revoked_by(rel_id: str, old: str, new: str) -> dict:
    return {
        "type": "relationship",
        "id": rel_id,
        "relationship_type": "revoked-by",
        "source_ref": old,
        "target_ref": new,
    }


def _pin(monkeypatch, script: ModuleType, bundle: bytes) -> None:
    digest = hashlib.sha256(bundle).hexdigest()
    monkeypatch.setattr(script, "SOURCE", {"sha256": digest, "url": "u", "version": "v"})


def test_revocations_derive_pairs_and_deprecations(monkeypatch) -> None:
    script = _script("derive_attack_revocations")
    bundle = _bundle(
        _technique("ap--a", "T9001", revoked=True),
        _technique("ap--b", "T9002"),
        _technique("ap--c", "T9003", x_mitre_deprecated=True),
        _revoked_by("rel--1", "ap--a", "ap--b"),
        _revoked_by("rel--2", "mitigation--x", "ap--b"),  # not a technique: skipped
    )
    _pin(monkeypatch, script, bundle)
    out = script.derive(bundle, commit="0" * 40, generated="2026-10-12")
    assert out["revoked_by"] == [{"old": "T9001", "new": "T9002"}]
    assert out["deprecated"] == ["T9003"]


def test_revocations_derive_refuses_one_old_id_revoked_into_two(monkeypatch) -> None:
    script = _script("derive_attack_revocations")
    bundle = _bundle(
        _technique("ap--a", "T9001", revoked=True),
        _technique("ap--b", "T9002"),
        _technique("ap--c", "T9003"),
        _revoked_by("rel--1", "ap--a", "ap--b"),
        _revoked_by("rel--2", "ap--a", "ap--c"),
    )
    _pin(monkeypatch, script, bundle)
    with pytest.raises(script.Refused, match="T9001"):
        script.derive(bundle, commit="0" * 40, generated="2026-10-12")


def test_read_pinned_refuses_a_mismatch_and_a_missing_file(tmp_path: Path) -> None:
    script = _script("derive_crosswalks")
    path = tmp_path / "input.json"
    path.write_bytes(b"abc")
    assert script._read_pinned(path, hashlib.sha256(b"abc").hexdigest()) == b"abc"
    with pytest.raises(script.Refused, match="does not equal the pinned"):
        script._read_pinned(path, hashlib.sha256(b"abd").hexdigest())
    with pytest.raises(script.Refused, match="input missing"):
        script._read_pinned(tmp_path / "absent.json", "0" * 64)


@pytest.mark.parametrize(
    "code,expected",
    [
        ("T1", ("T1", None)),  # active: unchanged
        ("T2", ("T1", None)),  # revoked into an active technique
        ("T3", ("T1", None)),  # a chain: T3 -> T2 -> T1
        ("T4", (None, "revocation_cycle")),  # T4 -> T5 -> T4
        ("T6", (None, "deprecated_in_19.2")),
        ("T7", (None, "absent_from_19.2")),
        ("T8", (None, "deprecated_in_19.2")),  # revoked into a deprecated one
    ],
)
def test_translator_branches(code: str, expected: tuple) -> None:
    script = _script("derive_crosswalks")
    revocations = {
        "revoked_by": [
            {"old": "T2", "new": "T1"},
            {"old": "T3", "new": "T2"},
            {"old": "T4", "new": "T5"},
            {"old": "T5", "new": "T4"},
            {"old": "T8", "new": "T6"},
        ],
        "deprecated": ["T6"],
    }
    translate = script._translator(revocations, frozenset({"T1"}))
    assert translate(code) == expected


def test_translator_refuses_one_old_id_with_two_replacements() -> None:
    script = _script("derive_crosswalks")
    revocations = {
        "revoked_by": [{"old": "T2", "new": "T1"}, {"old": "T2", "new": "T3"}],
        "deprecated": [],
    }
    with pytest.raises(script.Refused, match="T2"):
        script._translator(revocations, frozenset({"T1", "T3"}))


def _x1(*objects: dict) -> bytes:
    return json.dumps(
        {"metadata": {"attack_version": "16.1"}, "mapping_objects": list(objects)}
    ).encode()


def _mitigates(control: str, technique: str, **extra) -> dict:
    return {
        "capability_id": control,
        "attack_object_id": technique,
        "mapping_type": "mitigates",
        **extra,
    }


def test_x1_counts_identical_duplicates_and_refuses_ones_that_differ() -> None:
    script = _script("derive_crosswalks")
    revocations = {"revoked_by": [], "deprecated": []}
    same = _x1(_mitigates("AC-02", "T1078"), _mitigates("AC-02", "T1078"))
    header = script.derive_x1(same, revocations)["header"]
    assert (header["rows"], header["duplicate_rows"]) == (1, 1)
    differ = _x1(_mitigates("AC-02", "T1078", status="complete"), _mitigates("AC-02", "T1078"))
    with pytest.raises(script.Refused, match="AC-02"):
        script.derive_x1(differ, revocations)


def _x2(tmp_path: Path, *rows: tuple) -> Path:
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "CSF 2.0"
    for row in rows:
        sheet.append(list(row))
    path = tmp_path / "x2.xlsx"
    book.save(path)
    return path


def test_x2_classifies_family_and_category_lines(tmp_path: Path) -> None:
    script = _script("derive_crosswalks")
    path = _x2(
        tmp_path,
        ("GOVERN (GV): text", None, None, None, None),
        (None, "Organizational Context (GV.OC): text", None, None, "SP 800-53 Rev 5.1.1: PM-01"),
        (
            None,
            None,
            "GV.OC-01: text",
            None,
            "SP 800-53 Rev 5.1.1: PM-11\nSP 800-53 Rev 5.1.1: PT\nISO: x",
        ),
    )
    parsed = script._x2_references(path)
    assert parsed.refs == {"GV.OC-01": {"5.1.1": {"PM-11"}}}
    assert parsed.families == {"GV.OC-01": {"5.1.1": {"PT"}}}
    assert parsed.categories == {"GV.OC": {"5.1.1": {"PM-01"}}}
    assert parsed.third_party == {"subcategory": 1, "category": 0, "function": 0}
    assert parsed.unplaced == {"other": 0, "function": 1, "category": 1}


def test_x2_counts_third_party_lines_on_every_row_kind(tmp_path: Path) -> None:
    script = _script("derive_crosswalks")
    path = _x2(
        tmp_path,
        ("Function", "Category", "Subcategory", None, "Informative References"),
        ("GOVERN (GV): text", None, None, None, "CRI: GV"),
        (None, "Organizational Context (GV.OC): text", None, None, "CRI: GV.OC\nISO: y"),
        (None, None, "GV.OC-01: text", None, "ISO: x"),
    )
    assert script._x2_references(path).third_party == {
        "subcategory": 1,
        "category": 2,
        "function": 1,
    }


def test_derive_c1_refuses_a_family_or_category_line_under_an_unknown_code(
    tmp_path: Path, monkeypatch
) -> None:
    script = _script("derive_crosswalks")
    x1 = {"rows": []}
    family = _x2(tmp_path, (None, None, "ZZ.ZZ-01: text", None, "SP 800-53 Rev 5.1.1: PT"))
    with pytest.raises(script.Refused, match="ZZ.ZZ-01"):
        script.derive_c1(family, x1)
    category = _x2(
        tmp_path, (None, "Unknown (ZZ.ZZ): text", None, None, "SP 800-53 Rev 5.1.1: PM-01")
    )
    with pytest.raises(script.Refused, match="ZZ.ZZ"):
        script.derive_c1(category, x1)


@pytest.mark.parametrize(
    "row",
    [
        (None, None, "GV.OC-01: text", None, "SP 800-53 Rev 5.1.1: AC 2"),  # unreadable
        ("GOVERN (GV): text", None, None, None, "SP 800-53 Rev 5.1.1: PM-01"),  # on a function
        (None, None, None, None, "SP 800-53 Rev 5.1.1: PM-01"),  # on no row SHIELD can place
        (None, "Organizational Context (GV.OC): text", None, None, "SP 800-53 Rev 5.1.1: PT"),
    ],
)
def test_x2_refuses_an_sp_800_53_line_it_cannot_place(tmp_path: Path, row: tuple) -> None:
    script = _script("derive_crosswalks")
    with pytest.raises(script.Refused, match="SP 800-53"):
        script._x2_references(_x2(tmp_path, row))
