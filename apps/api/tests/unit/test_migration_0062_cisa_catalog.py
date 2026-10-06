"""Migration 0062 (#838): stored CISA answers survive the catalog change.

The world is built through the ORM at revision 0061 (0062 changes no schema,
so the models fit both), then upgraded. What the migration must do comes from
the approved plan (#838 comment 5982917066), not from the migration: the two
mapped rows move, the 15 cross-cutting rows exist, retired rows are KEPT, an
existing target is never overwritten, other frameworks and discarded
assessments are untouched, and a downgrade never deletes an answer.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

pytestmark = pytest.mark.unit

_CROSS = [f"CISA.{p}.{s}" for p in ("ID", "DV", "NW", "AW", "DT") for s in ("VA", "AO", "GV")]


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture()
def world(tmp_path):
    from app.models.client import Client
    from app.models.risk_register import RiskEntry, RiskRegister
    from app.models.service import Service, ServiceKind
    from app.models.user import User, UserRole
    from app.models.zt_assessment import (
        ZtAnswer,
        ZtAssessment,
        ZtAssessmentStatus,
        ZtFramework,
    )

    url = f"sqlite:///{tmp_path / 'm0062.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0061")
    engine = create_engine(url, future=True)
    ids: dict[str, object] = {}
    with Session(engine) as db:
        user = User(email="a@example.com", password_hash="x", role=UserRole.ADMIN, display_name="A")
        client = Client(legal_name="Acme")
        db.add_all([user, client])
        db.flush()

        def service(kind: ServiceKind) -> Service:
            s = Service(client_id=client.id, kind=kind, title="t", opened_by=user.id)
            db.add(s)
            db.flush()
            return s

        def assessment(svc: Service, fw: ZtFramework, status: ZtAssessmentStatus, version=1):
            a = ZtAssessment(
                service_id=svc.id, client_id=client.id, framework=fw, version=version, status=status
            )
            db.add(a)
            db.flush()
            return a

        def answer(a, code: str, stage: int | None, notes: str | None = None) -> None:
            db.add(
                ZtAnswer(
                    assessment_id=a.id,
                    client_id=client.id,
                    capability_code=code,
                    maturity_stage=stage,
                    notes=notes,
                )
            )

        cisa = service(ServiceKind.ZERO_TRUST_CISA)
        live = assessment(cisa, ZtFramework.CISA_ZTMM_2_0, ZtAssessmentStatus.DRAFT)
        answer(live, "CISA.ID.01", 2, "kept as it is")
        answer(live, "CISA.ID.05", 2, "visibility for identity")  # maps to ID.VA
        answer(live, "CISA.DV.05", 1, "old devices visibility")  # target exists: stays
        answer(live, "CISA.DV.VA", 3, "already answered")
        answer(live, "CISA.VA.01", 3, "log storage")  # retired, kept
        gone = assessment(cisa, ZtFramework.CISA_ZTMM_2_0, ZtAssessmentStatus.DISCARDED, 2)
        answer(gone, "CISA.ID.05", 2)
        dod = assessment(
            service(ServiceKind.ZERO_TRUST_DOD),
            ZtFramework.DOD_ZTRA,
            ZtAssessmentStatus.DRAFT,
        )
        answer(dod, "DOD.USR.01", 2)
        register = RiskRegister(client_id=client.id)
        db.add(register)
        db.flush()
        db.add(
            RiskEntry(
                register_id=register.id,
                client_id=client.id,
                title="t",
                source="questionnaire_response",
                source_id="CISA.ID.05",
            )
        )
        db.commit()
        ids.update(live=live.id, gone=gone.id, dod=dod.id)
    yield cfg, engine, ids


def _codes(engine, assessment_id) -> dict[str, tuple]:
    from app.models.zt_assessment import ZtAnswer

    with Session(engine) as db:
        rows = db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == assessment_id)).scalars()
        return {r.capability_code: (r.maturity_stage, r.notes) for r in rows}


def _risk_ids(engine) -> list[str]:
    from app.models.risk_register import RiskEntry

    with Session(engine) as db:
        return list(db.execute(select(RiskEntry.source_id)).scalars())


def test_upgrade_maps_inserts_and_keeps_everything(world) -> None:
    cfg, engine, ids = world
    command.upgrade(cfg, "0062")
    live = _codes(engine, ids["live"])
    # Mapped, answer and notes carried with it.
    assert "CISA.ID.05" not in live
    assert live["CISA.ID.VA"] == (2, "visibility for identity")
    # Target existed: neither overwritten nor lost.
    assert live["CISA.DV.VA"] == (3, "already answered")
    assert live["CISA.DV.05"] == (1, "old devices visibility")
    # Retired rows are kept, untouched.
    assert live["CISA.VA.01"] == (3, "log storage")
    assert live["CISA.ID.01"] == (2, "kept as it is")
    # Every cross-cutting row exists; the new ones are empty.
    assert set(_CROSS) <= set(live)
    assert live["CISA.NW.GV"] == (None, None)
    # A discarded assessment and a DoD one are not touched.
    assert _codes(engine, ids["gone"]) == {"CISA.ID.05": (2, None)}
    assert _codes(engine, ids["dod"]) == {"DOD.USR.01": (2, None)}
    # The risk link follows the mapped row.
    assert _risk_ids(engine) == ["CISA.ID.VA"]


def test_downgrade_reverses_the_mapping_and_deletes_only_empty_inserted_rows(world) -> None:
    from app.models.zt_assessment import ZtAnswer

    cfg, engine, ids = world
    command.upgrade(cfg, "0062")
    with Session(engine) as db:  # someone answers a new cross-cutting row
        row = db.execute(
            select(ZtAnswer).where(
                ZtAnswer.assessment_id == ids["live"], ZtAnswer.capability_code == "CISA.NW.GV"
            )
        ).scalar_one()
        row.maturity_stage = 2
        db.commit()
    command.downgrade(cfg, "0061")
    live = _codes(engine, ids["live"])
    assert live["CISA.ID.05"] == (2, "visibility for identity")
    assert "CISA.ID.VA" not in live
    assert live["CISA.NW.GV"] == (2, None)  # answered: never deleted
    assert "CISA.AW.AO" not in live  # inserted and empty: removed
    assert live["CISA.DV.VA"] == (3, "already answered")  # pre-existing: kept
    assert _risk_ids(engine) == ["CISA.ID.05"]
