"""Migration 0064 (#839): stored DoD answers survive the catalog change.

The world is built through the ORM at revision 0063 (0064 changes no schema, so
the models fit both), then upgraded. What the migration must do comes from the
approved plan (#838 comment 6022742677, amended in 6023694715), not from the
migration: DoD numbers Data Loss Prevention 4.6 and Data Access Control 4.7, so
the stored `DOD.DAT.06` and `DOD.DAT.07` answers swap; `DOD.USR.09` (1.9) is
inserted; the six retired rows are KEPT; risk links swap the same way; CISA
and discarded assessments are untouched; a downgrade never deletes an answer.
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

RETIRED = ("DOD.APP.06", "DOD.APP.07", "DOD.NET.05", "DOD.NET.06", "DOD.NET.07", "DOD.VIS.07")


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

    url = f"sqlite:///{tmp_path / 'm0064.db'}"
    os.environ["DATABASE_URL"] = url
    cfg = _cfg(url)
    command.upgrade(cfg, "0063")
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

        dod_svc = service(ServiceKind.ZERO_TRUST_DOD)
        live = assessment(dod_svc, ZtFramework.DOD_ZTRA, ZtAssessmentStatus.RELEASED)
        answer(live, "DOD.USR.01", 2, "kept as it is")
        answer(live, "DOD.DAT.06", 1, "access control")  # old 06 = Data Access Control
        answer(live, "DOD.DAT.07", 3, "loss prevention")  # old 07 = Data Loss Prevention
        for code in RETIRED:
            answer(live, code, 2, f"retired {code}")
        gone = assessment(dod_svc, ZtFramework.DOD_ZTRA, ZtAssessmentStatus.DISCARDED, 2)
        answer(gone, "DOD.DAT.06", 1, "discarded")
        cisa = assessment(
            service(ServiceKind.ZERO_TRUST_CISA),
            ZtFramework.CISA_ZTMM_2_0,
            ZtAssessmentStatus.DRAFT,
        )
        answer(cisa, "CISA.ID.01", 2)
        register = RiskRegister(client_id=client.id)
        db.add(register)
        db.flush()
        db.add(
            RiskEntry(
                register_id=register.id,
                client_id=client.id,
                title="t",
                source="questionnaire_response",
                source_id="DOD.DAT.06",
                linked_controls=["DOD.DAT.07", "DOD.USR.01", "DOD.NET.05"],
            )
        )
        db.commit()
        ids.update(live=live.id, gone=gone.id, cisa=cisa.id)
    yield cfg, engine, ids


def _codes(engine, assessment_id) -> dict[str, tuple]:
    from app.models.zt_assessment import ZtAnswer

    with Session(engine) as db:
        rows = db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == assessment_id)).scalars()
        return {r.capability_code: (r.maturity_stage, r.notes) for r in rows}


def _risk(engine) -> list[tuple]:
    from app.models.risk_register import RiskEntry

    with Session(engine) as db:
        return [(r.source_id, r.linked_controls) for r in db.execute(select(RiskEntry)).scalars()]


def test_upgrade_swaps_inserts_and_keeps_everything(world) -> None:
    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    live = _codes(engine, ids["live"])
    # DoD 4.6 is Data Loss Prevention and 4.7 Data Access Control: each answer
    # follows its capability, notes and all. A released assessment too (D-107).
    assert live["DOD.DAT.06"] == (3, "loss prevention")
    assert live["DOD.DAT.07"] == (1, "access control")
    assert live["DOD.USR.01"] == (2, "kept as it is")
    # 1.9 Integrated ICAM Platform is new, and empty.
    assert live["DOD.USR.09"] == (None, None)
    # Retired rows are kept, untouched.
    for code in RETIRED:
        assert live[code] == (2, f"retired {code}"), code
    # A discarded assessment and a CISA one are not touched.
    assert _codes(engine, ids["gone"]) == {"DOD.DAT.06": (1, "discarded")}
    assert _codes(engine, ids["cisa"]) == {"CISA.ID.01": (2, None)}
    # Risk links swap the same way; a retired code is left as it is.
    assert _risk(engine) == [("DOD.DAT.07", ["DOD.DAT.06", "DOD.USR.01", "DOD.NET.05"])]


def test_downgrade_swaps_back_and_deletes_only_an_empty_inserted_row(world) -> None:
    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    command.downgrade(cfg, "0063")
    live = _codes(engine, ids["live"])
    assert live["DOD.DAT.06"] == (1, "access control")
    assert live["DOD.DAT.07"] == (3, "loss prevention")
    assert "DOD.USR.09" not in live  # inserted and still empty: removed
    assert _risk(engine) == [("DOD.DAT.06", ["DOD.DAT.07", "DOD.USR.01", "DOD.NET.05"])]


def test_downgrade_never_deletes_an_answered_inserted_row(world) -> None:
    from app.models.zt_assessment import ZtAnswer

    cfg, engine, ids = world
    command.upgrade(cfg, "0064")
    with Session(engine) as db:  # someone answers the new row
        row = db.execute(
            select(ZtAnswer).where(
                ZtAnswer.assessment_id == ids["live"], ZtAnswer.capability_code == "DOD.USR.09"
            )
        ).scalar_one()
        row.notes = "ICAM platform in place"
        db.commit()
    command.downgrade(cfg, "0063")
    assert _codes(engine, ids["live"])["DOD.USR.09"] == (None, "ICAM platform in place")
