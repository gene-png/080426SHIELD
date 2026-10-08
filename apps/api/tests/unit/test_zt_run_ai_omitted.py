"""#840: a ZT capability the model returns no result for is counted and shown.

`_zt_run_work` asks the model about every capability and applies only the
entries that come back. Before #840 a capability with no entry kept whatever
stage it held and the run recorded nothing. The run now reports
`omitted_capabilities = (asked & rows) - answered - locked`, with `notes_blank` and
`kept_stage` per capability, and the audit row carries counts only.

Every test drives the run through `POST /zt/services/{id}/run-ai`. The provider
answers in the prompt's own keys (`code`, `current`, `target`, from
`_ZT_SCORE_PROMPT`'s example JSON) for the codes the PAYLOAD asked about, minus
the ones a test leaves out. Every expected value is derived from which codes
the test left out and what its setup wrote, never from a constant of the module
under test. Fixture mode cannot reach any of this: `_fixture_zt_score` answers
every code it is sent.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.zt_assessment import ZtAnswer
from tests._ai_runs import zt_run_ai


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str
    answers: list[dict]

    def code(self, i: int) -> str:
        return self.answers[i]["capability_code"]

    def patch(self, i: int, **fields: Any) -> None:
        r = self.c.patch(f"/zt/answers/{self.answers[i]['id']}", headers=self.h, json=fields)
        assert r.status_code == 200, r.text

    def answer_all_but(
        self,
        omit: set[str],
        *,
        override: dict[str, dict] | None = None,
    ) -> None:
        """A provider answering every code the payload ASKED about except
        `omit`, in the prompt's keys. `override` replaces one code's entry."""
        override = override or {}

        def respond(payload: dict[str, Any]) -> LLMResponse:
            caps = [
                override.get(code, {"code": code, "current": 1, "target": 3})
                for code in payload["capabilities"]
                if code not in omit
            ]
            return LLMResponse(json.dumps({"capabilities": caps}))

        self.provider.register("zt_score", respond)

    def run(self) -> dict:
        return zt_run_ai(self.c, self.svc_id, self.h)

    def row(self, code: str) -> ZtAnswer:
        with self.sessions() as s:
            return s.execute(select(ZtAnswer).where(ZtAnswer.capability_code == code)).scalar_one()


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-zt-omitted.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.zt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@kentro.example",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        cid = c.post(
            "/admin/clients",
            headers={"Authorization": f"Bearer {bearer}"},
            json={"legal_name": "Acme"},
        ).json()["id"]
        h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
        svc_id = c.post(
            "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Acme ZT"}
        ).json()["id"]
        a = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        answers = a.json()["answers"]
        assert len(answers) >= 6, answers
        yield World(c, sessions, provider, h, svc_id, answers)


def _identity_holds(result: dict) -> None:
    """Omitted must not touch the values identity: it counts what was SENT."""
    assert result["suggestions_received"] == result["suggestions_applied"] + sum(
        d["values"] for d in result["dropped"]
    ), result


@pytest.mark.unit
def test_capabilities_left_out_are_listed_with_their_notes_and_kept_stage(world) -> None:
    """Truth-table rows 5 and 6: asked, not answered, with and without a prior.

    Red-on-revert: drop `- answered` and every capability is listed.
    """
    blank, noted = world.code(0), world.code(1)
    # `blank`: no notes, no stage (row 5). `noted`: notes and a stage set by
    # hand (row 6), the harm the issue names.
    world.patch(1, notes="Okta covers the workforce only", maturity_stage=2)
    world.answer_all_but({blank, noted})

    result = world.run()

    assert result["omitted_capabilities"] == sorted(
        [
            {"capability_code": blank, "notes_blank": True, "kept_stage": None},
            {"capability_code": noted, "notes_blank": False, "kept_stage": 2},
        ],
        key=lambda n: n["capability_code"],
    ), result["omitted_capabilities"]
    assert result["omitted_count"] == 2
    # Both rows are as the setup left them.
    assert (world.row(blank).maturity_stage, world.row(blank).notes) == (None, None)
    assert (world.row(noted).maturity_stage, world.row(noted).notes) == (
        2,
        "Okta covers the workforce only",
    )
    # And a capability that WAS answered is not listed: the run applied it.
    answered = world.code(2)
    assert answered not in {n["capability_code"] for n in result["omitted_capabilities"]}
    assert world.row(answered).maturity_stage == 1
    _identity_holds(result)


@pytest.mark.unit
def test_an_entry_that_names_a_capability_and_is_refused_is_not_omitted(world) -> None:
    """Truth-table row 7: an entry names the capability, and nothing applies.

    Its loss is itemized under its own reason, so counting it again here would
    report one capability twice. Two shapes: a value out of range, and an entry
    that names the code and suggests nothing.

    Red-on-revert: count only APPLIED codes as answered, and both are listed.
    """
    out_of_range, empty_entry = world.code(0), world.code(1)
    world.answer_all_but(
        set(),
        override={
            out_of_range: {"code": out_of_range, "current": 9},
            empty_entry: {"code": empty_entry},
        },
    )

    result = world.run()

    reasons = {(d["key"], d["reason"]) for d in result["dropped"]}
    assert (out_of_range, "out_of_range") in reasons, result["dropped"]
    assert (empty_entry, "entry_shape") in reasons, result["dropped"]
    assert result["omitted_capabilities"] == [], result["omitted_capabilities"]
    assert result["omitted_count"] == 0
    _identity_holds(result)


@pytest.mark.unit
def test_a_locked_capability_left_out_is_not_omitted(world) -> None:
    """A locked row is untouched by design, so a missing answer for it is not
    news. An unlocked one left out in the same run IS listed, so the empty
    result for the locked one is not a run that lists nothing at all.

    Red-on-revert: drop `- locked_keys` and the locked code is listed.
    """
    locked, unlocked = world.code(0), world.code(1)
    world.patch(0, locked=True, notes="Locked by the consultant")
    world.answer_all_but({locked, unlocked})

    result = world.run()

    listed = [n["capability_code"] for n in result["omitted_capabilities"]]
    assert listed == [unlocked], listed
    assert result["omitted_count"] == 1


@pytest.mark.unit
def test_whitespace_notes_are_blank_and_na_is_a_note(world) -> None:
    """Whitespace only is blank. "N/A" is a note: code cannot tell a deliberate
    "N/A" from one a model should have scored, so it does not try."""
    spaces, na = world.code(0), world.code(1)
    world.patch(0, notes="  \n\t ")
    world.patch(1, notes="N/A")
    world.answer_all_but({spaces, na})

    result = world.run()

    blank_by_code = {n["capability_code"]: n["notes_blank"] for n in result["omitted_capabilities"]}
    assert blank_by_code == {spaces: True, na: False}, result["omitted_capabilities"]


@pytest.mark.unit
def test_kept_stage_is_read_after_the_apply(world, monkeypatch) -> None:
    """A capability edited while the model answered, and left out of the
    answer, is counted (the sentence "got no stage from the AI this run" stays
    true of it) and reports the stage the edit wrote, which is what the row
    holds when the run ends.

    The edit is made in the job's own session, right after the provider call
    returns: SQLite allows one writer, and the job holds the write lock while
    the provider answers, so a second connection cannot land an edit there.
    The job commits it before reading the rows, as it would a real edit.

    Red-on-revert: read `kept_stage` from the rows as loaded before the provider
    call, and it reports the stage the edit replaced.
    """
    import app.routes.zt as zt_routes
    from app.models._common import utcnow

    edited = world.code(0)
    world.patch(0, notes="Before the run", maturity_stage=1)
    real_run_job = zt_routes.run_job
    calls: list[int] = []

    def run_job_then_edit(db: Session, *args: Any, **kwargs: Any) -> Any:
        result = real_run_job(db, *args, **kwargs)
        db.execute(
            update(ZtAnswer)
            .where(ZtAnswer.id == uuid.UUID(world.answers[0]["id"]))
            .values(maturity_stage=3, notes="Edited mid-run", updated_at=utcnow())
        )
        calls.append(1)
        return result

    monkeypatch.setattr(zt_routes, "run_job", run_job_then_edit)
    world.answer_all_but({edited})

    result = world.run()

    assert calls == [1], "the edit never ran, so this test proves nothing"
    assert result["omitted_capabilities"] == [
        {"capability_code": edited, "notes_blank": False, "kept_stage": 3}
    ], result["omitted_capabilities"]
    assert world.row(edited).maturity_stage == 3


@pytest.mark.unit
def test_an_empty_response_lists_every_unlocked_capability(world) -> None:
    """`{"capabilities": []}` received nothing, so every capability asked for is
    without a result. The panel renders this inside its received-0 branch."""
    locked = world.code(0)
    world.patch(0, locked=True)
    world.provider.register_static("zt_score", LLMResponse('{"capabilities": []}'))

    result = world.run()

    expected = sorted(a["capability_code"] for a in world.answers if a["capability_code"] != locked)
    assert result["suggestions_received"] == 0
    assert [n["capability_code"] for n in result["omitted_capabilities"]] == expected
    assert result["omitted_count"] == len(expected)


@pytest.mark.unit
def test_the_audit_row_carries_omitted_counts_and_no_codes(world) -> None:
    """#44 constraint 1: counts only. Each count derived from the setup."""
    from app.models.audit_entry import AuditEntry

    # blank notes, no stage / blank notes, a stage / notes, a stage / "N/A", none
    setups: list[tuple[int, dict]] = [
        (0, {}),
        (1, {"maturity_stage": 2}),
        (2, {"notes": "Partial rollout", "maturity_stage": 3}),
        (3, {"notes": "N/A"}),
    ]
    for i, fields in setups:
        if fields:
            world.patch(i, **fields)
    omitted = {world.code(i) for i, _ in setups}
    world.answer_all_but(omitted)

    world.run()

    with world.sessions() as s:
        row = s.execute(select(AuditEntry).where(AuditEntry.action == "zt.run_ai")).scalar_one()
    details = row.details
    blank = sum(1 for _, f in setups if not f.get("notes"))
    kept = sum(1 for _, f in setups if f.get("maturity_stage") is not None)
    assert details["omitted_blank_notes"] == blank, details
    assert details["omitted_with_notes"] == len(setups) - blank, details
    assert details["omitted_kept_stage"] == kept, details
    blob = json.dumps(details)
    for code in omitted:
        assert code not in blob, blob
