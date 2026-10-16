"""#1006, CSF half: a tenant user's name typed into a CSF answer's notes
reaches the provider redacted, through the run AND `/ai/preview`.

The tenant's user names are the redactor's name dictionary
(`name_hints_for_tenant`), as #863 and #865 use them for ATT&CK and T2's #1235
for ZT. `csf_score` sent `answers[*].notes` with no dictionary at all. The
shared builder (`_csf_ai_request_for`) now carries it, so the preview, the run
and the measure script cannot differ.

Every expected value is the scenario's literal (the user's name and email
local part, the placeholder "[NAME]"), never a call to the redactor. The
harness is T2's ZT test's (`test_zt_name_hints.py` on #1235).
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai.llm import LLMResponse
from app.csf.catalog import SUBCATEGORIES
from app.models.user import User, UserRole
from tests._ai_runs import csf_run_ai
from tests.unit.test_csf_run_ai import _bootstrap, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

#: A tenant user, named in notes by display name and by email local part.
NAME = "Dana Whitfield"
# The local part has a separator: a bare lowercase word (`dwhitfield`) is not
# a hint by design (`_looks_like_an_account_name`, B13), a documented residual
# that is not this fix's subject.
LOCAL = "d.whitfield"
NOTE = f"Access reviews are approved by {NAME}; escalations go to {LOCAL}."
CODE = SUBCATEGORIES[0].code


def _world(c) -> tuple[dict, str]:
    h, svc_id = _bootstrap(c)
    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=engine, future=True)() as db:
        db.add(
            User(
                email=f"{LOCAL}@acme.example",
                password_hash="x" * 64,
                role=UserRole.CLIENT,
                display_name=NAME,
                client_id=uuid.UUID(c.headers["X-Client-Id"]),
            )
        )
        db.commit()
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    answer_id = next(a["id"] for a in latest["answers"] if a["subcategory_code"] == CODE)
    r = c.patch(f"/csf/answers/{answer_id}", headers=h, json={"notes": NOTE})
    assert r.status_code == 200, r.text
    return h, svc_id


def _no_person_in(text: str) -> None:
    for part in ("Dana", "Whitfield", "whitfield"):
        assert part not in text, text


def test_a_tenant_users_name_in_csf_notes_reaches_the_provider_redacted(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    h, svc_id = _world(c)
    sent: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"scores": []}')

    provider.register("csf_score", _spy)
    csf_run_ai(c, svc_id, h)

    assert sent, "no csf_score payload reached the provider"
    notes = [p["answers"][CODE]["notes"] for p in sent if CODE in p.get("answers", {})]
    assert notes, sent
    for note in notes:
        # The positive state first: the note was sent, with the person replaced.
        assert "Access reviews are approved by" in note, note
        assert "[NAME]" in note, note
    _no_person_in(json.dumps(sent))


def test_the_preview_shows_the_same_redacted_note(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    h, svc_id = _world(c)

    r = c.post("/ai/preview", headers=h, json={"service_id": svc_id})

    assert r.status_code == 200, r.text
    note = r.json()["payload"]["answers"][CODE]["notes"]
    assert "Access reviews are approved by" in note, note
    assert "[NAME]" in note, note
    _no_person_in(json.dumps(r.json()["payload"]))
