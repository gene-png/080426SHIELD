"""No surface that shows ATT&CK coverage may drop the not-verified count (#554).

The owner's decision on #554: coverage is computed over ASSESSED techniques only,
and the not-verified count (`unable_to_determine`) sits BESIDE the percentage on
every surface -- "no surface may drop it, and a test must prove it can't". The
outside-the-control-surface count travels with it.

EVERY SURFACE, ONE TEST EACH, from the same world: the three renderers (XLSX,
DOCX, PDF), the stored deliverable summary, the admin heatmap and the client
dashboard (the home value card's count is in `test_value_summary.py`). This is a
NAMED REGISTRY of the API surfaces. Its first version missed three surfaces, each
rendered on the web.
The web side is DERIVED instead
(`attack-percentages-state-the-outside-counts.test.ts`): any component reading
ATT&CK data that renders a coverage figure must state the counts. The API
renderers stay a list because they are few and live in two modules; a new one
belongs here.

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


def test_the_scored_total_does_not_shrink_as_rows_move_to_not_verified() -> None:
    """#621 round 2, finding 1. An unverified row is not "scored", but the
    catalogue total beside it must not shrink: every document states X of the
    WHOLE catalogue. Before, Y was scored + unscored, which would drop by
    NOT_VERIFIED the moment "scored" stopped counting them."""
    from openpyxl import load_workbook

    ctx = _ctx(NOT_VERIFIED, OUTSIDE)
    scored = len(TECHNIQUES) - NOT_VERIFIED  # literal arithmetic, not the rollup
    expected = f"{scored}/{len(TECHNIQUES)}"
    ws = load_workbook(io.BytesIO(render_xlsx(ctx)))["Heatmap Summary"]
    labels = {r[0].value: r[1].value for r in ws.iter_rows(max_row=14)}
    assert labels["Scored / Total"] == expected
    assert f"Scored: {expected}" in _docx_text(render_docx(ctx))
    assert f"Scored: {expected}" in _pdf_text(render_pdf(ctx))


def test_the_count_is_never_dropped_at_zero() -> None:
    """Zero is shown, so "none" and "not shown" cannot look alike."""
    ctx = _ctx(0, 0)
    assert "Not verified 0, Outside control surface 0" in _docx_text(render_docx(ctx))
    assert "Not verified 0, Outside control surface 0" in _pdf_text(render_pdf(ctx))


# --- the stored summary, the admin heatmap and the client dashboard ----------


REFUSAL_TAIL = (
    "An approved assessment cannot be edited, so this one cannot be released; a new "
    "assessment version starts every technique unscored."
)


def _released_outside_the_routes(Sess, deliverable_id: str, assessment_id: str) -> None:
    """Mark a deliverable and its assessment released straight in the database:
    the route refuses, by design (#622), to release over a Not verified row."""
    from app.models._common import utcnow
    from app.models.deliverable import Deliverable

    with Sess() as s:
        s.execute(
            update(Deliverable)
            .where(Deliverable.id == uuid.UUID(deliverable_id))
            .values(released_at=utcnow())
        )
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(assessment_id))
            .values(status=AttackAssessmentStatus.RELEASED)
        )
        s.commit()


def test_the_summary_heatmap_and_client_dashboard_carry_both_counts(env) -> None:  # noqa: F811
    """A RATCHET for the backstop case, not a live path (#732 item 3).

    No writer for `unable_to_determine` exists today (`coverage.WRITABLE` is
    unwidened), and since #622 approve and release refuse over one. So the
    rows are written straight to the database AFTER a clean approve, and the
    release is completed outside the routes. That is the state an assessment
    approved before the gate existed could hold, and these surfaces must still
    count it. With #622 only the ORDER the state is built in changed, plus the
    release: it is now asserted REFUSED, by its literal sentence, where #621
    asserted 200. Every other assertion is as #621 wrote it.
    """
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)

    rows = standalone_rows(a["coverage"], NOT_VERIFIED + OUTSIDE + 1)

    def write(statuses: list[str]) -> None:
        with Sess() as s:
            for row, status in zip(rows, statuses, strict=True):
                s.execute(
                    update(AttackCoverage)
                    .where(AttackCoverage.id == uuid.UUID(row["id"]))
                    .values(status=status, unconfirmed_citations=[])
                )
            s.commit()

    write(["covered"] * len(rows))
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    write(
        ["unable_to_determine"] * NOT_VERIFIED + ["outside_control_surface"] * OUTSIDE + ["covered"]
    )

    heat = c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).json()
    assert (heat["unable_to_determine"], heat["outside_control_surface"]) == (
        NOT_VERIFIED,
        OUTSIDE,
    )

    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    assert SENTENCE in fin.json()["summary"], fin.json()["summary"]
    rel = c.post(f"/attack/deliverables/{fin.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 409, rel.text
    codes = ", ".join(sorted(r["technique_code"] for r in rows[:NOT_VERIFIED]))
    assert rel.json()["error"]["message"] == (
        f"Nothing was released: {NOT_VERIFIED} techniques are Not verified ({codes}). "
        + REFUSAL_TAIL
    )
    _released_outside_the_routes(Sess, fin.json()["id"], a["id"])

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
