"""Whether a deliverable's AI suggestions came from a live model or fixtures (#646).

`llm_calls.mode` records, per call, whether the live provider or the offline
fixture provider answered. Nothing surfaced it, so a deliverable built on
fixture output (canned test data, D-017) read exactly like one built on a live
model. This module turns those rows into one stamp every renderer prints.

DERIVED, never stored: the stamp is read from `llm_calls` when the document is
rendered, so there is no second record to drift from the ledger.

Only COMPLETED calls count. A failed call produced no suggestion, so it cannot
have put fixture data into the document.

Scope, stated because it is narrower than a reader may assume: the stamp covers
the AI calls made FOR THIS SERVICE (or, for the Risk Register, the client's
`risk_synthesize` calls). It does not follow inputs across services, so an
ATT&CK deliverable does not report how the Tech Debt list it cites was
extracted; that list's own deliverable carries its own stamp.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus

_log = get_logger(__name__)

RISK_PURPOSE = "risk_synthesize"


@dataclass(frozen=True)
class AiModeStamp:
    """How many completed AI calls behind a document were live, and how many fixture.

    `looked=False` is "nobody looked": a context built without a lookup. It is
    a state of its own, never read as "no AI was used".
    """

    live_calls: int
    fixture_calls: int
    looked: bool = True

    @property
    def state(self) -> str:
        if not self.looked:
            return "unknown"
        if self.fixture_calls and self.live_calls:
            return "mixed"
        if self.fixture_calls:
            return "fixture"
        if self.live_calls:
            return "live"
        return "none"

    @property
    def is_warning(self) -> bool:
        """True when a reader must not take AI-drafted values as analysis."""
        return self.state in ("fixture", "mixed", "unknown")

    def sentence(self) -> str:
        """The line every deliverable prints. Wording depends only on `state`."""
        total = self.live_calls + self.fixture_calls
        state = self.state
        if state == "fixture":
            return (
                "OFFLINE TEST DATA: every AI suggestion behind this document came "
                "from built-in fixtures, not a live AI model. Treat AI-drafted "
                "values as placeholders, not analysis."
            )
        if state == "mixed":
            return (
                f"OFFLINE TEST DATA: {self.fixture_calls} of the {total} AI calls "
                "behind this document used built-in fixtures, not a live AI model. "
                "Values they drafted are placeholders, not analysis."
            )
        if state == "live":
            return "AI suggestions behind this document came from a live AI model."
        if state == "none":
            return "No AI call is recorded for this document; no value was AI-drafted."
        return (
            "Not recorded whether the AI suggestions behind this document came "
            "from a live AI model or from offline test data."
        )


#: For a context built without a lookup, e.g. by a test. Renders as "not recorded".
UNKNOWN_AI_MODE = AiModeStamp(live_calls=0, fixture_calls=0, looked=False)


def _count(db: Session, *conditions) -> AiModeStamp:
    rows = db.execute(
        select(LLMCall.mode, func.count())
        .where(LLMCall.status == LLMCallStatus.COMPLETED, *conditions)
        .group_by(LLMCall.mode)
    ).all()
    counts = dict(rows)
    return AiModeStamp(
        live_calls=counts.get(LLMCallMode.LIVE, 0),
        fixture_calls=counts.get(LLMCallMode.FIXTURE, 0),
    )


def ai_mode_for_service(db: Session, service_id: uuid.UUID) -> AiModeStamp:
    """The stamp for a service's deliverable: its own completed AI calls."""
    stamp = _count(db, LLMCall.service_id == service_id)
    _log.info(
        "ai_mode_stamp.service",
        service_id=str(service_id),
        state=stamp.state,
        live_calls=stamp.live_calls,
        fixture_calls=stamp.fixture_calls,
    )
    return stamp


def ai_mode_for_risk_register(db: Session, client_id: uuid.UUID) -> AiModeStamp:
    """The stamp for a client's Risk Register export.

    `risk_synthesize` runs are recorded against the client, not a service
    (`routes/risk.py` passes no `service_id`), so they are selected by client
    and purpose.
    """
    stamp = _count(db, LLMCall.client_id == client_id, LLMCall.purpose == RISK_PURPOSE)
    _log.info(
        "ai_mode_stamp.risk_register",
        client_id=str(client_id),
        state=stamp.state,
        live_calls=stamp.live_calls,
        fixture_calls=stamp.fixture_calls,
    )
    return stamp


# ---------------------------------------------------------------------------
# Rendering. ONE definition per format, so every deliverable prints the same
# words in the same place: directly under the title, before any figure.
# ---------------------------------------------------------------------------

XLSX_SHEET_TITLE = "AI source"


def pdf_paragraph(stamp: AiModeStamp, style: Any) -> Any:
    """The stamp as a reportlab Paragraph, bold when it is a warning."""
    from html import escape

    from reportlab.platypus import Paragraph

    text = escape(stamp.sentence())
    return Paragraph(f"<b>{text}</b>" if stamp.is_warning else text, style)


def add_docx_paragraph(doc: Any, stamp: AiModeStamp) -> None:
    """The stamp as a DOCX paragraph, bold when it is a warning."""
    para = doc.add_paragraph()
    run = para.add_run(stamp.sentence())
    run.bold = stamp.is_warning


def add_xlsx_sheet(wb: Any, stamp: AiModeStamp) -> None:
    """The stamp as its own LAST sheet.

    Last, not first: every workbook's first sheet is what `wb.active` opens and
    what existing readers index by row, so a sheet inserted before it would
    move their data. The PDF and DOCX carry the stamp under the title.
    """
    from openpyxl.styles import Font

    ws = wb.create_sheet(XLSX_SHEET_TITLE)
    ws.append(["AI source", stamp.state])
    ws.append([stamp.sentence()])
    ws.append(["Live AI calls", stamp.live_calls if stamp.looked else "not recorded"])
    ws.append(["Offline fixture calls", stamp.fixture_calls if stamp.looked else "not recorded"])
    ws.cell(row=1, column=1).font = Font(bold=True)
    ws.cell(row=2, column=1).font = Font(bold=stamp.is_warning)
    ws.column_dimensions["A"].width = 24
