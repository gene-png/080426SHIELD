"""Phase 5 stage 1: Zero Trust catalog integrity + migration smoke."""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.zt.catalog import (
    CISA_CAPABILITIES,
    CISA_PILLARS,
    DOD_CAPABILITIES,
    DOD_PILLARS,
    all_codes,
    capabilities,
    capability_by_code,
    pillar_by_code,
    pillars,
)
from app.zt.maturity import (
    CISA_STAGES,
    DOD_STAGES,
    ZtFrameworkCode,
    level_count,
    stage_label,
)

CISA_CODE_PATTERN = re.compile(r"^CISA\.[A-Z]{2}\.\d{2}$")
DOD_CODE_PATTERN = re.compile(r"^DOD\.[A-Z]{3}\.\d{2}$")


# ---------------------------------------------------------------------------
# CISA ZTMM 2.0
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_cisa_pillar_count_is_eight() -> None:
    assert len(CISA_PILLARS) == 8


@pytest.mark.unit
def test_cisa_capability_count_is_thirtyseven() -> None:
    assert len(CISA_CAPABILITIES) == 37


@pytest.mark.unit
def test_cisa_capability_codes_unique_and_well_formed() -> None:
    codes = [c.code for c in CISA_CAPABILITIES]
    assert len(set(codes)) == len(codes)
    for c in CISA_CAPABILITIES:
        assert CISA_CODE_PATTERN.fullmatch(c.code), c.code
        # Pillar prefix matches.
        assert c.code.split(".", 2)[1] == c.pillar_code


@pytest.mark.unit
def test_every_cisa_capability_has_a_real_pillar() -> None:
    pillar_codes = {p.code for p in CISA_PILLARS}
    for c in CISA_CAPABILITIES:
        assert c.pillar_code in pillar_codes


# ---------------------------------------------------------------------------
# DoD ZTRA
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dod_pillar_count_is_seven() -> None:
    assert len(DOD_PILLARS) == 7


@pytest.mark.unit
def test_dod_capability_count_is_fifty() -> None:
    # v1 baseline; expand to the full 152 in a future patch.
    assert len(DOD_CAPABILITIES) == 50


@pytest.mark.unit
def test_dod_capability_codes_unique_and_well_formed() -> None:
    codes = [c.code for c in DOD_CAPABILITIES]
    assert len(set(codes)) == len(codes)
    for c in DOD_CAPABILITIES:
        assert DOD_CODE_PATTERN.fullmatch(c.code), c.code
        assert c.code.split(".", 2)[1] == c.pillar_code


@pytest.mark.unit
def test_every_dod_capability_has_a_real_pillar() -> None:
    pillar_codes = {p.code for p in DOD_PILLARS}
    for c in DOD_CAPABILITIES:
        assert c.pillar_code in pillar_codes


# ---------------------------------------------------------------------------
# Shared accessors
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_capability_namespaces_dont_collide() -> None:
    cisa = {c.code for c in CISA_CAPABILITIES}
    dod = {c.code for c in DOD_CAPABILITIES}
    assert cisa.isdisjoint(dod)


@pytest.mark.unit
def test_capabilities_helper_returns_per_framework() -> None:
    assert capabilities(ZtFrameworkCode.CISA_ZTMM_2_0) is CISA_CAPABILITIES
    assert capabilities(ZtFrameworkCode.DOD_ZTRA) is DOD_CAPABILITIES


@pytest.mark.unit
def test_pillars_helper_returns_per_framework() -> None:
    assert pillars(ZtFrameworkCode.CISA_ZTMM_2_0) is CISA_PILLARS
    assert pillars(ZtFrameworkCode.DOD_ZTRA) is DOD_PILLARS


@pytest.mark.unit
def test_all_codes_round_trips_against_iteration() -> None:
    cisa_codes = all_codes(ZtFrameworkCode.CISA_ZTMM_2_0)
    assert cisa_codes == frozenset(c.code for c in CISA_CAPABILITIES)
    dod_codes = all_codes(ZtFrameworkCode.DOD_ZTRA)
    assert dod_codes == frozenset(c.code for c in DOD_CAPABILITIES)


@pytest.mark.unit
def test_pillar_by_code_round_trip() -> None:
    p = pillar_by_code(ZtFrameworkCode.CISA_ZTMM_2_0, "ID")
    assert p.name == "Identity"
    with pytest.raises(KeyError):
        pillar_by_code(ZtFrameworkCode.CISA_ZTMM_2_0, "XX")


@pytest.mark.unit
def test_capability_by_code_finds_across_frameworks() -> None:
    sample_cisa = CISA_CAPABILITIES[0]
    sample_dod = DOD_CAPABILITIES[0]
    assert capability_by_code(sample_cisa.code) is sample_cisa
    assert capability_by_code(sample_dod.code) is sample_dod
    with pytest.raises(KeyError):
        capability_by_code("BOGUS.XX.99")


# ---------------------------------------------------------------------------
# Maturity
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_framework_level_counts() -> None:
    # CISA has 4 levels (Traditional..Optimal); DoD has 3 (Not Started..Advanced).
    assert level_count(ZtFrameworkCode.CISA_ZTMM_2_0) == 4
    assert level_count(ZtFrameworkCode.DOD_ZTRA) == 3
    assert [d.stage for d in CISA_STAGES] == [1, 2, 3, 4]
    assert [d.stage for d in DOD_STAGES] == [1, 2, 3]


@pytest.mark.unit
@pytest.mark.parametrize(
    "stage,fw,expected",
    [
        (1, ZtFrameworkCode.CISA_ZTMM_2_0, "Traditional"),
        (1, ZtFrameworkCode.DOD_ZTRA, "Not Started"),
        (2, ZtFrameworkCode.CISA_ZTMM_2_0, "Initial"),
        (2, ZtFrameworkCode.DOD_ZTRA, "Target"),
        (3, ZtFrameworkCode.CISA_ZTMM_2_0, "Advanced"),
        (3, ZtFrameworkCode.DOD_ZTRA, "Advanced"),
        (4, ZtFrameworkCode.CISA_ZTMM_2_0, "Optimal"),
        # DoD has no stage 4 — it falls outside the ladder.
        (4, ZtFrameworkCode.DOD_ZTRA, "Unknown"),
        (None, ZtFrameworkCode.CISA_ZTMM_2_0, "Unscored"),
        (99, ZtFrameworkCode.CISA_ZTMM_2_0, "Unknown"),
    ],
)
def test_stage_label(stage, fw, expected: str) -> None:
    assert stage_label(stage, fw) == expected


# ---------------------------------------------------------------------------
# Migration smoke
# ---------------------------------------------------------------------------


@pytest.fixture()
def fresh_db(tmp_path) -> Iterator[str]:
    db_path = tmp_path / "shield-zt.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    yield url


@pytest.mark.unit
def test_migration_creates_zt_tables(fresh_db) -> None:
    engine = create_engine(fresh_db, future=True)
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    assert "zt_assessments" in table_names
    assert "zt_answers" in table_names

    cols_a = {c["name"] for c in insp.get_columns("zt_assessments")}
    assert {
        "id",
        "service_id",
        "client_id",
        "framework",
        "version",
        "status",
        "approved_at",
        "approved_by",
        "created_at",
        "updated_at",
    } <= cols_a

    cols_b = {c["name"] for c in insp.get_columns("zt_answers")}
    assert {
        "id",
        "assessment_id",
        "client_id",
        "capability_code",
        "maturity_stage",
        "notes",
        "evidence_artifact_id",
        "answered_by",
        "answered_at",
    } <= cols_b

    uq_assessments = {u["name"] for u in insp.get_unique_constraints("zt_assessments")}
    assert "uq_zt_assessments_service_version" in uq_assessments

    uq_answers = {u["name"] for u in insp.get_unique_constraints("zt_answers")}
    assert "uq_zt_answers_assessment_capability" in uq_answers
