"""Shared helpers for the #646 AI-source tests.

`seed_run` writes the row the Run-AI framework writes for a run that finished
(#645), straight into the test's database, so a test can state which mode
drafted an assessment without driving a Run-AI for each case.
`seed_unattributed_call` writes the `llm_calls` row a pre-#756 run left: a
completed call with no `ai_run_id`.

The text readers return what a person opening the file would read.
"""

from __future__ import annotations

import io
import uuid
from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from app.models._common import utcnow
from app.models.ai_run import AiRun, AiRunStatus
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus

LIVE = "AI suggestions in this assessment came from a live AI model."
FIXTURE = (
    "OFFLINE TEST DATA: every AI suggestion in this assessment came from built-in test "
    "data, not a live AI model. Treat AI-drafted values as placeholders, not analysis."
)
NONE = "No AI suggestions were used in this assessment."
UNKNOWN = (
    "It is not recorded whether the AI suggestions in this assessment came from a live "
    "AI model or from offline test data."
)


def mixed(fixture_runs: int, total: int, subject: str = "assessment") -> str:
    return (
        f"OFFLINE TEST DATA: {fixture_runs} of the {total} AI runs on this {subject} used "
        "built-in test data, not a live AI model. Values they drafted are placeholders, "
        "not analysis."
    )


def env_sessions() -> sessionmaker:
    """Sessions on the test's own database, for fixtures that yield only a
    client (each points `DATABASE_URL` at its SQLite file)."""
    import os

    from sqlalchemy import create_engine

    return sessionmaker(bind=create_engine(os.environ["DATABASE_URL"], future=True))


def seed_run(
    Sess: sessionmaker,
    *,
    service_id: str,
    subject_id: str,
    purpose: str,
    mode: LLMCallMode,
    status: AiRunStatus = AiRunStatus.COMPLETED,
    result: dict | None = None,
) -> None:
    from app.models.service import Service
    from app.models.user import User

    with Sess() as s:
        svc = s.get(Service, uuid.UUID(service_id))
        user = s.query(User).first()
        now = utcnow()
        s.add(
            AiRun(
                client_id=svc.client_id,
                service_id=svc.id,
                purpose=purpose,
                subject_id=uuid.UUID(subject_id),
                status=status,
                mode=mode,
                boot_id="test-boot",
                requested_by=user.id,
                started_at=now,
                deadline_at=now + timedelta(minutes=45),
                finished_at=now,
                result=result,
            )
        )
        s.commit()


def seed_unattributed_call(Sess: sessionmaker, *, service_id: str, purpose: str) -> None:
    from app.models.service import Service
    from app.models.user import User

    with Sess() as s:
        svc = s.get(Service, uuid.UUID(service_id))
        user = s.query(User).first()
        s.add(
            LLMCall(
                purpose=purpose,
                prompt_version="v1",
                provider="anthropic",
                model="m",
                mode=LLMCallMode.LIVE,
                status=LLMCallStatus.COMPLETED,
                requested_by=user.id,
                service_id=svc.id,
                client_id=svc.client_id,
                ai_run_id=None,
            )
        )
        s.commit()


def pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return " ".join(" ".join((p.extract_text() or "") for p in reader.pages).split())


def docx_text(raw: bytes) -> str:
    from docx import Document

    return " ".join(" ".join(p.text for p in Document(io.BytesIO(raw)).paragraphs).split())


def xlsx_ai_sheet(raw: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(raw))
    assert wb.sheetnames[-1] == "AI source", wb.sheetnames
    return [list(r) for r in wb["AI source"].iter_rows(values_only=True)]
