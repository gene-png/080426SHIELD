"""#860 review B4: the demo seed publishes its Risk Register, so the register
must be one the real publish gate would have let through (#737).

The seed sets `finalized_at` itself rather than calling the route. Before this,
it generated the register AFTER seeding CSF v2 APPROVED, so the provenance
recorded an unreleased input under a published register -- the #130 shape,
seed data in a state the product refuses. Runs the whole `main()` against
SQLite, so the ORDER `main` seeds in is what is under test, not a copy of it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.csf_assessment import CsfAssessment
from app.models.risk_register import RiskRegister
from app.storage.local import LocalFilesystemStorage

pytestmark = pytest.mark.unit


def test_the_seeded_register_was_publishable_when_published(tmp_path, monkeypatch) -> None:
    from scripts import seed_demo

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        seed_demo, "get_storage", lambda: LocalFilesystemStorage(tmp_path / "storage")
    )
    seed_demo.main()

    with Session(create_engine(url, future=True)) as db:
        reg = db.execute(select(RiskRegister)).scalar_one()
        assert reg.finalized_at is not None
        recorded = reg.provenance["current_inputs"]
        assert sorted(r["kind"] for r in recorded) == ["attack", "csf", "tech_debt", "zt", "zt"]
        assert {r["status"] for r in recorded} == {"released"}, recorded
        csf = {r["kind"]: r for r in recorded}["csf"]
        assert csf["version"] == 1, csf
        # v2 APPROVED still exists: the #114 demo state is seeded, after the
        # register, as the ordinary "published, then an input moved on".
        versions = db.execute(
            select(CsfAssessment.version, CsfAssessment.status).order_by(CsfAssessment.version)
        ).all()
        assert [(v, str(getattr(s, "value", s))) for v, s in versions] == [
            (1, "released"),
            (2, "approved"),
        ]
