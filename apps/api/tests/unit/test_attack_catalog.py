"""ATT&CK catalog integrity + migration smoke (Phase 5 stage 5)."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.attack.catalog import (
    TACTICS,
    TECHNIQUES,
    all_codes,
    parent_techniques,
    sub_techniques,
    tactic_by_id,
    technique_by_id,
    techniques_for_tactic,
)
from app.attack.coverage import (
    COVERAGE_DEFINITIONS,
    CoverageStatus,
    coverage_label,
)

TACTIC_ID_PATTERN = re.compile(r"^TA\d{4}$")
TECHNIQUE_ID_PATTERN = re.compile(r"^T\d{4}(\.\d{3})?$")


@pytest.mark.unit
def test_fourteen_tactics() -> None:
    assert len(TACTICS) == 14
    for t in TACTICS:
        assert TACTIC_ID_PATTERN.fullmatch(t.id), t.id


@pytest.mark.unit
def test_tactics_unique() -> None:
    ids = [t.id for t in TACTICS]
    names = [t.name for t in TACTICS]
    assert len(set(ids)) == len(ids)
    assert len(set(names)) == len(names)


@pytest.mark.unit
def test_at_least_600_total_entries() -> None:
    # D-007: full Enterprise matrix (target floor 600).
    assert len(TECHNIQUES) >= 600


@pytest.mark.unit
def test_technique_codes_unique_and_well_formed() -> None:
    codes = [t.id for t in TECHNIQUES]
    assert len(set(codes)) == len(codes)
    for t in TECHNIQUES:
        assert TECHNIQUE_ID_PATTERN.fullmatch(t.id), t.id


@pytest.mark.unit
def test_parent_and_sub_counts_make_sense() -> None:
    parents = parent_techniques()
    subs = [t for t in TECHNIQUES if t.is_sub_technique]
    # Parents in the 150-250 band; subs 350-500 band - matches Enterprise
    # matrix sizing without locking us to an exact NIST/MITRE revision.
    assert 150 <= len(parents) <= 250
    assert 350 <= len(subs) <= 500


@pytest.mark.unit
def test_every_sub_technique_has_a_real_parent() -> None:
    parent_ids = {p.id for p in parent_techniques()}
    for t in TECHNIQUES:
        if t.is_sub_technique:
            assert t.parent_id in parent_ids, f"{t.id} -> {t.parent_id}"


@pytest.mark.unit
def test_sub_technique_id_prefix_matches_parent() -> None:
    for t in TECHNIQUES:
        if t.is_sub_technique:
            assert t.id.startswith(t.parent_id + ".")


@pytest.mark.unit
def test_sub_techniques_inherit_parent_tactics() -> None:
    by_id = {t.id: t for t in TECHNIQUES}
    for t in TECHNIQUES:
        if t.is_sub_technique:
            parent = by_id[t.parent_id]
            assert t.tactics == parent.tactics


@pytest.mark.unit
def test_every_technique_maps_to_at_least_one_real_tactic() -> None:
    tactic_ids = {t.id for t in TACTICS}
    for t in TECHNIQUES:
        assert t.tactics
        for tid in t.tactics:
            assert tid in tactic_ids, f"{t.id} -> {tid}"


@pytest.mark.unit
def test_techniques_for_tactic_returns_subset() -> None:
    for ta in TACTICS:
        techs = techniques_for_tactic(ta.id)
        for t in techs:
            assert ta.id in t.tactics


@pytest.mark.unit
def test_lookup_round_trip() -> None:
    sample_tactic = TACTICS[0]
    assert tactic_by_id(sample_tactic.id) is sample_tactic
    sample_tech = TECHNIQUES[0]
    assert technique_by_id(sample_tech.id) is sample_tech
    with pytest.raises(KeyError):
        tactic_by_id("TA9999")
    with pytest.raises(KeyError):
        technique_by_id("T9999.999")


@pytest.mark.unit
def test_all_codes_helper_matches_iteration() -> None:
    assert all_codes() == frozenset(t.id for t in TECHNIQUES)


@pytest.mark.unit
def test_sub_techniques_helper() -> None:
    # T1003 (OS Credential Dumping) has well-known subs; the catalog
    # should include at least a few.
    subs = sub_techniques("T1003")
    assert len(subs) >= 4
    sample_codes = {"T1003.001", "T1003.002", "T1003.003"}
    assert sample_codes.issubset({s.id for s in subs})


# ---------------------------------------------------------------------------
# Coverage status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_four_coverage_definitions() -> None:
    assert len(COVERAGE_DEFINITIONS) == 4
    statuses = {d.status for d in COVERAGE_DEFINITIONS}
    assert statuses == {
        CoverageStatus.COVERED,
        CoverageStatus.PARTIAL,
        CoverageStatus.GAP,
        CoverageStatus.NOT_APPLICABLE,
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "value,expected",
    [
        (CoverageStatus.COVERED, "Covered"),
        (CoverageStatus.PARTIAL, "Partial"),
        (CoverageStatus.GAP, "Gap"),
        (CoverageStatus.NOT_APPLICABLE, "N/A"),
        ("covered", "Covered"),
        (None, "Unscored"),
    ],
)
def test_coverage_label(value, expected: str) -> None:
    assert coverage_label(value) == expected


# ---------------------------------------------------------------------------
# Migration smoke
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_db(tmp_path) -> Iterator[str]:
    db_path = tmp_path / "shield-attack.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    yield url


@pytest.mark.unit
def test_migration_creates_attack_tables(fresh_db) -> None:
    engine = create_engine(fresh_db, future=True)
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    assert "attack_assessments" in table_names
    assert "attack_coverage" in table_names

    cols_a = {c["name"] for c in insp.get_columns("attack_assessments")}
    assert {
        "id",
        "service_id",
        "client_id",
        "version",
        "status",
        "approved_at",
        "approved_by",
    } <= cols_a

    cols_c = {c["name"] for c in insp.get_columns("attack_coverage")}
    assert {
        "id",
        "assessment_id",
        "client_id",
        "technique_code",
        "status",
        "notes",
        "evidence_artifact_id",
    } <= cols_c

    uq_a = {u["name"] for u in insp.get_unique_constraints("attack_assessments")}
    assert "uq_attack_assessments_service_version" in uq_a
    uq_c = {u["name"] for u in insp.get_unique_constraints("attack_coverage")}
    assert "uq_attack_coverage_assessment_technique" in uq_c
