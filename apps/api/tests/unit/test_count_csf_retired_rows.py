"""The #852 blast-radius count reads before it reports, and says when it could not.

`scripts/count_csf_retired_rows.py` is read-only and non-blocking. What is
pinned: "could not look" is exit 2 and never a zero, and a database holding a
kept `ID.AM-09` row reports it under its assessment's status.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from scripts.count_csf_retired_rows import main as count_main
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

pytestmark = pytest.mark.unit


def test_no_database_url_is_exit_2(monkeypatch, capsys) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert count_main() == 2
    assert "nothing was read" in capsys.readouterr().err


def test_an_unreadable_database_is_exit_2(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'empty.db'}")
    assert count_main() == 2
    assert "could not read the database" in capsys.readouterr().err


def test_a_kept_row_is_counted_under_its_status(monkeypatch, tmp_path, capsys) -> None:
    from app.models.client import Client
    from app.models.csf_assessment import CsfAnswer, CsfAssessment, CsfAssessmentStatus
    from app.models.service import Service, ServiceKind
    from app.models.user import User, UserRole

    url = f"sqlite:///{tmp_path / 'count.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    with Session(create_engine(url, future=True)) as db:
        user = User(email="a@example.com", password_hash="x", role=UserRole.ADMIN, display_name="A")
        client = Client(legal_name="Acme")
        db.add_all([user, client])
        db.flush()
        svc = Service(client_id=client.id, kind=ServiceKind.NIST_CSF, title="t", opened_by=user.id)
        db.add(svc)
        db.flush()
        a = CsfAssessment(
            service_id=svc.id, client_id=client.id, version=1, status=CsfAssessmentStatus.RELEASED
        )
        db.add(a)
        db.flush()
        db.add(
            CsfAnswer(
                assessment_id=a.id,
                client_id=client.id,
                subcategory_code="ID.AM-09",
                maturity_tier=2,
            )
        )
        db.commit()

    assert count_main() == 0
    out = capsys.readouterr().out
    assert "CSF assessments 1, CSF answer rows 1" in out
    assert "NOTHING TO MEASURE" not in out
    released = next(line for line in out.splitlines() if line.startswith("  released:"))
    assert "retired answers 1, retired answers recorded 1" in released
    assert "assessments missing RC.CO-04 answer 1" in released
