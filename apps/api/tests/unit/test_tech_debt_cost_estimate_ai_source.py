"""TD-5 (for #1060): the deliverable's AI-source stamp (#646) counts the estimate.

A list whose rows a LIVE extraction drafted, but whose costs a FIXTURE-mode
estimate wrote, is not "live": some AI-drafted values in it are canned test
data. Before TD-5's change to `mode_stamp`, the Tech Debt stamp counted
extraction runs only, so this list was stamped live -- a flattering stamp on a
client deliverable. Asserted through the files the client receives, not the
helper.

A test provider cannot serve live, so the extraction run's recorded mode is set
to live by SQL. That is a REACHABLE state, not a fixture-only one: its writer is
`app/ai/runs.py` `start_run`, which stores `mode=_mode_for(actual)`, and
`_mode_for` returns `LLMCallMode.LIVE` whenever the provider serves live, as
every live extraction does. The stamp reads exactly that column.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update

from app.ai.fixtures import _fixture_tech_debt_cost_estimate
from app.models.ai_run import AiRun
from app.models.llm_call import LLMCallMode
from tests._ai_mode import docx_text, pdf_text, xlsx_ai_sheet
from tests.unit.test_capability_list_revision import (  # noqa: F401  (fixture)
    World,
    _approve,
    _decide_all,
    _latest,
    _world,
    app_client,
)
from tests.unit.test_tech_debt_cost_estimate_routes import PURPOSE, _estimate, _uncost

pytestmark = pytest.mark.unit


def _record_extraction_live(w: World) -> None:
    with w.sessions() as s:
        n = s.execute(
            update(AiRun)
            .where(AiRun.service_id == uuid.UUID(w.svc_id), AiRun.purpose == "tech_debt_extract")
            .values(mode=LLMCallMode.LIVE)
        ).rowcount
        s.commit()
    assert n == 1, f"expected one extraction run, updated {n}"


def _files(w: World, body: dict) -> tuple[str, str, list[list[object]]]:
    def _bytes(key: str) -> bytes:
        dl = w.c.get(f"/artifacts/{body[key]}/download", headers=w.h)
        assert dl.status_code == 200, dl.text
        return dl.content

    return (
        pdf_text(_bytes("pdf_artifact_id")),
        docx_text(_bytes("docx_artifact_id")),
        xlsx_ai_sheet(_bytes("xlsx_artifact_id")),
    )


def _finalize(w: World) -> dict:
    _decide_all(w)
    assert _approve(w).status_code == 200
    fin = w.c.post(f"/tech-debt/services/{w.svc_id}/deliverables/finalize", headers=w.h)
    assert fin.status_code == 201, fin.text
    return fin.json()


def test_a_live_extraction_alone_is_stamped_live(app_client) -> None:  # noqa: F811
    """POSITIVE CONTROL: the SQL above does produce a live stamp, so the test
    below is red for the reason it names and not because nothing reads live."""
    w = _world(app_client)
    _record_extraction_live(w)
    assert _latest(w)["ai_source"]["state"] == "live"
    _pdf, _docx, sheet = _files(w, _finalize(w))
    assert sheet[0][:2] == ["AI source", "live"]


def test_a_fixture_estimate_under_a_live_extraction_is_not_stamped_live(
    app_client,  # noqa: F811
) -> None:
    c, _sessions, provider = app_client
    w = _world(app_client)
    provider.register(PURPOSE, _fixture_tech_debt_cost_estimate)
    _record_extraction_live(w)
    _uncost(w, w.other_id)
    assert _estimate(w)["result"]["estimated"] == 1
    assert _latest(w)["ai_source"]["state"] == "mixed"
    pdf, docx, sheet = _files(w, _finalize(w))
    assert sheet[0][:2] == ["AI source", "mixed"]
    sentence = _latest(w)["ai_source"]["sentence"]
    assert sentence in pdf
    assert sentence in docx
