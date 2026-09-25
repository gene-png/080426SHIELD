"""No surface that shows ATT&CK coverage may drop the not-verified count (#554).

The owner's decision on #554: coverage is computed over ASSESSED techniques only,
and the not-verified count (`unable_to_determine`) sits BESIDE the percentage on
every surface -- "no surface may drop it, and a test must prove it can't". The
outside-the-control-surface count travels with it.

EVERY SURFACE, ONE TEST EACH, from the same world: the three renderers (XLSX,
DOCX, PDF), the stored deliverable summary, the admin heatmap and the client
dashboard. A surface added later that shows the percentage belongs here.

The rows are written straight to the database, because no writer may produce
these statuses yet (`coverage.WRITABLE`, D-092 Decision 5): the surfaces must be
able to report them BEFORE anything can store them. The counts are literals
chosen here -- 7 and 3 -- never read back from the rollup under test.
"""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import update

from app.attack.analytics import compute
from app.attack.catalog import TECHNIQUES
from app.attack.exporters import build_context, render_docx, render_pdf, render_xlsx
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit

NOT_VERIFIED, OUTSIDE = 7, 3
SENTENCE = f"Not verified {NOT_VERIFIED}, Outside control surface {OUTSIDE}"


# --- the renderers -----------------------------------------------------------


def _ctx(not_verified: int, outside: int):
    a = AttackAssessment(
        id=uuid.uuid4(), service_id=uuid.uuid4(), version=1, status=AttackAssessmentStatus.APPROVED
    )
    statuses = (
        ["unable_to_determine"] * not_verified
        + ["outside_control_surface"] * outside
        + ["covered"] * (len(TECHNIQUES) - not_verified - outside)
    )
    coverage = [
        AttackCoverage(id=uuid.uuid4(), assessment_id=a.id, technique_code=t.id, status=st)
        for t, st in zip(TECHNIQUES, statuses, strict=True)
    ]
    rollup = compute({c.technique_code: c.status for c in coverage})
    return build_context(
        client_legal_name="Test Client",
        service_title="ATT&CK Coverage",
        assessment=a,
        coverage=coverage,
        rollup=rollup,
    )


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(
        " ".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages).split()
    )


def _docx_text(raw: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(raw))
    return " ".join(" ".join(p.text for p in doc.paragraphs).split())


def test_the_xlsx_states_both_counts_beside_the_percentage() -> None:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(render_xlsx(_ctx(NOT_VERIFIED, OUTSIDE))))["Heatmap Summary"]
    labels = {r[0].value: r[1].value for r in ws.iter_rows(max_row=14)}
    assert (labels["Not verified"], labels["Outside control surface"]) == (NOT_VERIFIED, OUTSIDE)
    header_row = next(
        r for r in range(1, ws.max_row + 1) if ws.cell(row=r, column=1).value == "Tactic"
    )
    headers = [ws.cell(row=header_row, column=c).value for c in range(1, 16)]
    assert "Not verified" in headers and "Outside control surface" in headers


def test_the_docx_states_both_counts_beside_the_percentage() -> None:
    assert SENTENCE in _docx_text(render_docx(_ctx(NOT_VERIFIED, OUTSIDE)))


def test_the_pdf_states_both_counts_beside_the_percentage() -> None:
    assert SENTENCE in _pdf_text(render_pdf(_ctx(NOT_VERIFIED, OUTSIDE)))


def test_the_count_is_never_dropped_at_zero() -> None:
    """Zero is shown, so "none" and "not shown" cannot look alike."""
    ctx = _ctx(0, 0)
    assert "Not verified 0, Outside control surface 0" in _docx_text(render_docx(ctx))
    assert "Not verified 0, Outside control surface 0" in _pdf_text(render_pdf(ctx))


# --- the stored summary, the admin heatmap and the client dashboard ----------


def test_the_summary_heatmap_and_client_dashboard_carry_both_counts(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)

    rows = standalone_rows(a["coverage"], NOT_VERIFIED + OUTSIDE + 1)
    with Sess() as s:
        for i, row in enumerate(rows):
            status = (
                "unable_to_determine"
                if i < NOT_VERIFIED
                else "outside_control_surface" if i < NOT_VERIFIED + OUTSIDE else "covered"
            )
            s.execute(
                update(AttackCoverage)
                .where(AttackCoverage.id == uuid.UUID(row["id"]))
                .values(status=status, unconfirmed_citations=[])
            )
        s.commit()

    heat = c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).json()
    assert (heat["unable_to_determine"], heat["outside_control_surface"]) == (
        NOT_VERIFIED,
        OUTSIDE,
    )

    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    assert SENTENCE in fin.json()["summary"], fin.json()["summary"]
    rel = c.post(f"/attack/deliverables/{fin.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    rollup = dash.json()["rollup"]
    assert (rollup["unable_to_determine"], rollup["outside_control_surface"]) == (
        NOT_VERIFIED,
        OUTSIDE,
    )
    # And per tactic: a technique under several tactics counts in each, so the
    # sum is at least the overall count, never less.
    assert sum(t["unable_to_determine"] for t in rollup["by_tactic"]) >= NOT_VERIFIED
    assert sum(t["outside_control_surface"] for t in rollup["by_tactic"]) >= OUTSIDE
