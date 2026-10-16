"""#1084: a ZT capability with blank notes is never sent to the model.

The approved prompt's A5 tells the model to return nothing for blank notes, so
sending them buys nothing and costs input tokens. Code now decides it: a
capability whose notes are null, empty or whitespace-only is left out of
`capabilities`, `capability_details` and `answers` before egress. Notes code
cannot classify ("N/A", "TBD") are still sent; A5 covers those.

Nothing silently disappears: a capability left out is still listed in
`omitted_capabilities` with `notes_blank` (the "No notes recorded" disclosure,
#840), and a stray entry naming one is not applied but dropped as `no_notes`.

Every test drives `POST /zt/services/{id}/run-ai` (or `/ai/preview`, which
shares the builder). The provider answers in the prompt's own keys (`code`,
`current`, from A9's example JSON). Expected codes come from which rows the
test gave notes, never from a constant of the module under test.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.zt_assessment import ZtAnswer
from tests._ai_runs import zt_run_ai

_NOTE = "Phishing-resistant MFA is enforced for every workforce account."


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str
    answers: list[dict]
    sent: list[dict] = field(default_factory=list)

    def code(self, i: int) -> str:
        return self.answers[i]["capability_code"]

    def patch(self, i: int, **fields: Any) -> None:
        r = self.c.patch(f"/zt/answers/{self.answers[i]['id']}", headers=self.h, json=fields)
        assert r.status_code == 200, r.text

    def respond(self, entries: list[dict] | None = None) -> None:
        """Record every payload; answer every code it ASKED about with
        `current: 2`, plus any `entries` appended verbatim."""

        def _respond(payload: dict[str, Any]) -> LLMResponse:
            self.sent.append(payload)
            caps = [{"code": c, "current": 2} for c in payload["capabilities"]]
            return LLMResponse(json.dumps({"capabilities": caps + (entries or [])}))

        self.provider.register("zt_score", _respond)

    def run(self) -> dict:
        return zt_run_ai(self.c, self.svc_id, self.h)

    def row(self, code: str) -> ZtAnswer:
        with self.sessions() as s:
            return s.execute(select(ZtAnswer).where(ZtAnswer.capability_code == code)).scalar_one()


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-zt-blank-notes.db'}"
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


def _noted(world: World) -> tuple[set[str], set[str]]:
    """Rows 0 and 1 get a real note, row 2 "N/A" (A5's, not code's, to judge),
    row 3 whitespace only. Returns (codes that must be sent, codes that must not)."""
    world.patch(0, notes=_NOTE)
    world.patch(1, notes=_NOTE)
    world.patch(2, notes="N/A")
    world.patch(3, notes="   \n\t ")
    sent = {world.code(0), world.code(1), world.code(2)}
    every = {a["capability_code"] for a in world.answers}
    return sent, every - sent


@pytest.mark.unit
def test_only_capabilities_with_notes_reach_the_model(world) -> None:
    """Red-on-revert: send every row again and the blank ones are in all three
    maps."""
    sent, blank = _noted(world)
    world.respond()

    world.run()

    assert len(world.sent) == 1, world.sent
    payload = world.sent[0]
    assert payload["capabilities"] == sorted(sent), payload["capabilities"]
    assert set(payload["capability_details"]) == sent
    assert set(payload["answers"]) == sent
    assert world.code(3) in blank, "whitespace-only notes are blank"


@pytest.mark.unit
def test_a_capability_left_out_is_still_disclosed_as_no_notes(world) -> None:
    """The #840 disclosure lists every blank row with `notes_blank`, so a
    capability that was never sent does not silently disappear.

    Red-on-revert: compute omitted from the SENT codes, and it lists none."""
    sent, blank = _noted(world)
    world.respond()

    result = world.run()

    omitted = {o["capability_code"]: o for o in result["omitted_capabilities"]}
    assert set(omitted) == blank, sorted(set(omitted) ^ blank)
    assert all(o["notes_blank"] for o in omitted.values()), omitted
    assert result["omitted_count"] == len(blank)
    # The rows that were sent were answered and applied.
    for code in sent:
        assert world.row(code).maturity_stage == 2, code


@pytest.mark.unit
def test_a_stray_entry_for_an_unsent_capability_is_dropped_not_applied(world) -> None:
    """A7 forbids an entry for a capability the payload did not ask about. One
    naming a blank-notes row is not applied and is itemized. (No stage is set by
    hand: offline, that row would be `protected` first.)

    Red-on-revert: remove the `no_notes` drop and the row takes stage 3."""
    _sent, blank = _noted(world)
    stray = sorted(blank)[0]
    world.respond(entries=[{"code": stray, "current": 3}])

    result = world.run()

    assert world.row(stray).maturity_stage is None
    drops = [d for d in result["dropped"] if d["key"] == stray]
    assert [(d["reason"], d["values"]) for d in drops] == [("no_notes", 1)], result["dropped"]
    assert result["suggestions_received"] == result["suggestions_applied"] + sum(
        d["values"] for d in result["dropped"]
    ), result


@pytest.mark.unit
def test_the_preview_shows_the_same_filtered_payload(world) -> None:
    """`/ai/preview` shares the builder, so it shows what a run sends.

    Red-on-revert: filter in `_zt_run_work` instead of the builder."""
    sent, _blank = _noted(world)

    r = world.c.post("/ai/preview", headers=world.h, json={"service_id": world.svc_id})

    assert r.status_code == 200, r.text
    assert r.json()["payload"]["capabilities"] == sorted(sent)


@pytest.mark.unit
def test_a_row_given_notes_during_the_run_is_named_by_its_edit(world, monkeypatch) -> None:
    """Blank when the job built its request, noted while the model answered,
    and named by a stray entry: the drop says `edited`, the true cause, never
    "capability has no notes" about a row that now has some.

    The edit lands in the job's own session right after the provider call
    returns (SQLite allows one writer), as in `test_zt_run_ai_omitted.py`.

    Red-on-revert: check `no_notes` before `edited`, and this row is
    dropped as `no_notes`."""
    import uuid

    from sqlalchemy import update

    import app.routes.zt as zt_routes
    from app.models._common import utcnow

    _sent, blank = _noted(world)
    late = sorted(blank)[0]
    late_id = next(a["id"] for a in world.answers if a["capability_code"] == late)
    real_run_job = zt_routes.run_job
    calls: list[int] = []

    def run_job_then_edit(db: Session, *args: Any, **kwargs: Any) -> Any:
        result = real_run_job(db, *args, **kwargs)
        db.execute(
            update(ZtAnswer)
            .where(ZtAnswer.id == uuid.UUID(late_id))
            .values(notes="Noted while the model answered", updated_at=utcnow())
        )
        calls.append(1)
        return result

    monkeypatch.setattr(zt_routes, "run_job", run_job_then_edit)
    world.respond(entries=[{"code": late, "current": 3}])

    result = world.run()

    assert calls == [1], "the edit never ran, so this test proves nothing"
    drops = [(d["reason"], d["values"]) for d in result["dropped"] if d["key"] == late]
    assert drops == [("edited", 1)], result["dropped"]
    assert world.row(late).maturity_stage is None


@pytest.mark.unit
def test_a_wholly_blank_assessment_makes_no_model_call(world) -> None:
    """Every row blank, as on a fresh assessment: nothing would be sent, so no
    call is made and no `llm_calls` row is written (CSF's P1 does the same).
    The run still lists every capability as omitted with `notes_blank`, and
    says it sent none, so the panel does not read it as a broken response.

    Red-on-revert: call the provider with the empty list again, and
    `world.sent` and `llm_calls` each hold one."""
    from app.models.llm_call import LLMCall

    world.respond()

    result = world.run()

    assert world.sent == [], "the provider was called with nothing to score"
    with world.sessions() as s:
        assert s.execute(select(LLMCall)).scalars().all() == []
    every = sorted(a["capability_code"] for a in world.answers)
    omitted = result["omitted_capabilities"]
    assert [o["capability_code"] for o in omitted] == every
    assert all(o["notes_blank"] for o in omitted), omitted
    assert result["omitted_count"] == len(every)
    assert result["capabilities_sent"] == 0
    assert (result["suggestions_received"], result["suggestions_applied"]) == (0, 0)
    assert result["dropped"] == []


@pytest.mark.unit
def test_a_run_states_how_many_capabilities_it_sent(world) -> None:
    """The positive half: a run that sends rows says how many, so the panel's
    "nothing sent" state cannot be reached by a run that sent some."""
    sent, _blank = _noted(world)
    world.respond()

    result = world.run()

    assert result["capabilities_sent"] == len(sent) == len(world.sent[0]["capabilities"])
