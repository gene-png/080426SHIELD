"""#1006, ZT half: a tenant user's name typed into a ZT capability's notes
reaches the provider redacted, through the run AND `/ai/preview`.

The tenant's user names are the redactor's name dictionary
(`name_hints_for_tenant`), as #863 and #865 use them for ATT&CK. `zt_score`
sent `answers[*].notes` with no dictionary at all. The shared builder now
carries it, so the preview and the run cannot differ.

Every expected value is the scenario's literal (the user's name and email
local part, the placeholder "[NAME]"), never a call to the redactor.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.llm import LLMResponse
from app.models.user import User, UserRole
from tests._ai_runs import zt_run_ai
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

#: A tenant user, named in notes by display name and by email local part.
NAME = "Dana Whitfield"
LOCAL = "dwhitfield"
NOTE = f"MFA exceptions are approved by {NAME}; escalations go to {LOCAL}."


def _world(c):
    h, svc_id, cid = _admin_service(c, "zero_trust_cisa")
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as db:
        db.add(
            User(
                email=f"{LOCAL}@acme.example",
                password_hash="x" * 64,
                role=UserRole.CLIENT,
                display_name=NAME,
                client_id=uuid.UUID(cid),
            )
        )
        db.commit()
    answers = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()["answers"]
    r = c.patch(f"/zt/answers/{answers[0]['id']}", headers=h, json={"notes": NOTE})
    assert r.status_code == 200, r.text
    return h, svc_id, answers[0]["capability_code"]


def _no_person_in(text: str) -> None:
    for part in ("Dana", "Whitfield", LOCAL):
        assert part not in text, text


def test_a_tenant_users_name_in_zt_notes_reaches_the_provider_redacted(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    h, svc_id, code = _world(c)
    sent: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"capabilities": []}')

    provider.register("zt_score", _spy)
    zt_run_ai(c, svc_id, h)

    assert len(sent) == 1, sent
    note = sent[0]["answers"][code]["notes"]
    # The positive state first: the note was sent, with the person replaced.
    assert "MFA exceptions are approved by" in note, note
    assert "[NAME]" in note, note
    _no_person_in(json.dumps(sent[0]))


def test_the_preview_shows_the_same_redacted_note(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    h, svc_id, code = _world(c)

    r = c.post("/ai/preview", headers=h, json={"service_id": svc_id})

    assert r.status_code == 200, r.text
    note = r.json()["payload"]["answers"][code]["notes"]
    assert "MFA exceptions are approved by" in note, note
    assert "[NAME]" in note, note
    _no_person_in(json.dumps(r.json()["payload"]))
