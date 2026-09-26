"""CSF full-Playbook XLSX export (Work Order D4)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.csf.catalog import SUBCATEGORIES


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'shield-csfxlsx.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain
    from app.routes.artifacts import _storage_dep
    from app.storage.local import LocalFilesystemStorage

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: LocalFilesystemStorage(tmp_path / "storage")
    _seed = TestSession()
    tenant = _Client(legal_name="Test Tenant")
    _seed.add(tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    _seed.commit()
    cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, cid


@pytest.mark.unit
def test_a_draft_playbook_export_is_named_WORKING(app_client) -> None:
    """#243, #237's twin. A client-named artifact built from unreviewed work.

    `export_playbook` resolves `_latest_assessment` -- latest non-discarded,
    DRAFTS INCLUDED -- and its only refusals were "No assessment yet." and
    "Seed the Working Profile before exporting.". No status check. It then
    built filenames through `deliverable_filename(company=org, ...)`, so the
    client's name went on a document nobody had approved.

    **Not fixed by gating the export**, and that is a deliberate departure from
    the issue's suggested resolution. The Export button is offered whenever
    profiles are seeded, which is most of an engagement -- so a 409 there would
    remove a legitimate mid-engagement feature, and the consultant needs to
    read their own working profile to decide whether to approve it.

    This is `CLAUDE.md`'s #32 shape: ask whether the guarantee needs the state
    FROZEN or only needs to SAY WHAT IT IS. The mistakability is the defect,
    not the export. `deliverable_filename` already carries `working=True` for
    exactly this -- its docstring says "for admin-only intermediates" -- and it
    prefixes `WORKING_`.
    """
    c, cid = app_client
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})

    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    names = [a["filename"] for a in ex.json()["artifacts"]]
    assert names, "export produced no artifacts"
    for n in names:
        assert n.startswith("WORKING_"), (
            f"a DRAFT assessment produced a deliverable-named artifact: {n}. "
            "The client's name is on a document nobody approved."
        )


@pytest.mark.unit
def test_an_approved_playbook_export_drops_the_WORKING_prefix(app_client) -> None:
    """The other half, so the fix cannot become a permanent label.

    Once the assessment is APPROVED the artifact is deliverable-grade and must
    be named that way -- otherwise `WORKING_` stops meaning anything and gets
    read past, which is how a warning is trained away.
    """
    c, cid = app_client
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    ap = c.post(f"/csf/assessments/{a['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text

    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    for n in [x["filename"] for x in ex.json()["artifacts"]]:
        assert not n.startswith("WORKING_"), f"approved work still labelled draft: {n}"


@pytest.mark.unit
def test_playbook_export_produces_downloadable_xlsx(app_client) -> None:
    c, cid = app_client
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)

    # Locked before seeding.
    assert c.post(f"/csf/services/{svc_id}/playbook/export", headers=h).status_code == 409

    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high", "moderate"]})
    # Give one subcategory some scores so the sheets have content.
    code = SUBCATEGORIES[0].code
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    sid = next(x["id"] for x in rows if x["subcategory_code"] == code)
    c.patch(
        f"/csf/dimension-scores/{sid}",
        headers=h,
        json={"governance": 2, "policy": 2, "has_evidence": True, "target_level": 4},
    )

    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    arts = {a["kind"]: a for a in ex.json()["artifacts"]}
    # XLSX workbook + executive briefing (PDF+Word) + full playbook (PDF+Word).
    assert set(arts) == {"xlsx", "exec_pdf", "exec_docx", "full_pdf", "full_docx"}

    dh = {**h, "X-Client-Id": cid}
    magic = {
        "xlsx": b"PK",
        "exec_pdf": b"%PDF-",
        "exec_docx": b"PK",
        "full_pdf": b"%PDF-",
        "full_docx": b"PK",
    }
    for kind, art in arts.items():
        dl = c.get(f"/artifacts/{art['artifact_id']}/download", headers=dh)
        assert dl.status_code == 200, f"{kind}: {dl.status_code}"
        assert dl.content.startswith(magic[kind]), f"{kind} wrong magic bytes"


@pytest.mark.unit
def test_all_five_playbook_files_say_when_the_ai_came_from_fixtures(app_client) -> None:
    """#646. The Playbook's Run-AI (`csf_score`) drafts the dimension scores these
    files present, so each of the five says when that came from fixtures."""
    from tests._ai_mode import (
        FIXTURE_LINE,
        docx_text,
        pdf_text,
        seed_completed_call,
        xlsx_ai_sheet,
    )

    c, cid = app_client
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    seed_completed_call(requested_by=r.json()["user"]["id"], service_id=svc_id, purpose="csf_score")

    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    arts = {a["kind"]: a for a in ex.json()["artifacts"]}
    assert set(arts) == {"xlsx", "exec_pdf", "exec_docx", "full_pdf", "full_docx"}
    dh = {**h, "X-Client-Id": cid}
    for kind, art in arts.items():
        dl = c.get(f"/artifacts/{art['artifact_id']}/download", headers=dh)
        assert dl.status_code == 200, f"{kind}: {dl.status_code}"
        if kind == "xlsx":
            assert xlsx_ai_sheet(dl.content)[0][:2] == ["AI source", "fixture"], kind
        elif kind.endswith("pdf"):
            assert FIXTURE_LINE in pdf_text(dl.content), kind
        else:
            assert FIXTURE_LINE in docx_text(dl.content), kind


@pytest.mark.unit
@pytest.mark.parametrize("stored", [None, "   "])
def test_a_blank_legal_name_prints_the_fallback_on_all_five_playbook_artifacts(
    app_client, stored
) -> None:
    """The SURFACE for the seventh reader, driven through the route.

    `routes/csf.py` resolves the organisation once and passes it to five
    renderers. A test that calls a renderer with its own resolved name cannot
    see one of those five arguments being the raw value, so this one stores the
    blank name, runs `/playbook/export`, downloads every artifact the route
    stored, and reads the organisation line out of each.

    `None` is how D-080 stores an unnamed organisation today; `"   "` is the
    legacy shape migration 0050 normalises and the readers must still survive.
    """
    import io
    import uuid as _uuid

    from docx import Document
    from openpyxl import load_workbook
    from pypdf import PdfReader
    from sqlalchemy import update

    from app.models.client import Client

    c, cid = app_client
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with Session(engine) as db:
        db.execute(update(Client).where(Client.id == _uuid.UUID(cid)).values(legal_name=stored))
        db.commit()
    engine.dispose()

    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    ex = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert ex.status_code == 200, ex.text
    arts = {a["kind"]: a for a in ex.json()["artifacts"]}
    assert set(arts) == {"xlsx", "exec_pdf", "exec_docx", "full_pdf", "full_docx"}

    def text_of(kind: str, raw: bytes) -> str:
        if kind == "xlsx":
            wb = load_workbook(io.BytesIO(raw))
            return "\n".join(
                str(cell.value)
                for ws in wb.worksheets
                for row in ws.iter_rows()
                for cell in row
                if cell.value is not None
            )
        if kind.endswith("pdf"):
            return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)
        return "\n".join(p.text for p in Document(io.BytesIO(raw)).paragraphs)

    for kind, art in arts.items():
        dl = c.get(f"/artifacts/{art['artifact_id']}/download", headers={**h, "X-Client-Id": cid})
        assert dl.status_code == 200, f"{kind}: {dl.status_code}"
        text = text_of(kind, dl.content)
        label = "Client:" if kind == "xlsx" else "Prepared for:"
        lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith(label)]
        assert lines, f"{kind}: no {label!r} line found -- the artifact shape changed"
        for ln in lines:
            assert ln == f"{label} Client", (
                f"{kind} prints {ln!r} for a stored legal_name of {stored!r}; "
                "the organisation line must fall back, not print the blank"
            )
