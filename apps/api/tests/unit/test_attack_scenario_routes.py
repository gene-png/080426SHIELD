"""#802 slice A: the ATT&CK what-if, through the routes an admin reaches.

The world is built the way a consultant builds it: tools typed into the
matrix, the assessment approved under R3, the deliverable finalized and
released. The AI is a fixture provider answering the PROMPT's contract
(`{"rows": [{technique_code, tool, detection, prevention, response,
rationale}]}`), and the job is a placeholder registered here.

TODO(#806): the placeholder below stands in for the prompt text #806 holds.
When that text lands in `app/ai/jobs.py`, delete `_PLACEHOLDER_PROMPT` and
`analysis_job`, and let these tests use the registered job.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.ai import engine as ai_engine
from app.ai.engine import AIJob
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.attack.catalog import NOT_PREVENTABLE
from app.models.ai_run import AiRun
from app.models.attack_assessment import AttackCoverage
from app.models.attack_scenario import AttackScenario, AttackScenarioState
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.llm_call import LLMCall
from app.models.service import Service, ServiceKind, ServiceStatus
from tests._ai_runs import DeferringRunner, defer_runs
from tests._attack_rows import standalone_rows
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

PURPOSE = "attack_scenario_delta"
_PLACEHOLDER_PROMPT = "TODO(#806): placeholder; the real text is held by #806."

EDR, SIEM, SOAR = "EDR Tool", "SIEM Tool", "SOAR Tool"


@pytest.fixture()
def analysis_job() -> Iterator[None]:
    """Register the placeholder job for one test, and remove it after, so the
    unregistered state the other tests rely on is restored."""
    ai_engine.register_job(AIJob(name=PURPOSE, prompt=_PLACEHOLDER_PROMPT, top_level_key="rows"))
    try:
        yield
    finally:
        ai_engine._REGISTRY.pop(PURPOSE, None)


@dataclass
class World:
    c: TestClient
    app: Any
    sessions: sessionmaker
    h: dict
    cid: str
    svc_id: str
    assessment_id: str
    deliverable_id: str
    #: covered (EDR, EDR, SOAR); partial (SIEM); gap (EDR, an uncleared inference)
    a: str
    b: str
    cc: str

    def answer(self, rows_by_code: dict[str, list[dict]]) -> None:
        """The AI's answer, per batch, from the batch's own technique codes."""
        provider = FixtureProvider()

        def respond(payload: dict) -> LLMResponse:
            sent = payload.get("technique_codes") or []
            rows = [r for code in sent for r in rows_by_code.get(code, [])]
            return LLMResponse(json.dumps({"rows": rows}))

        provider.register(PURPOSE, respond)
        # mitre_map answers with nothing, for the tests that hold one running.
        provider.register("mitre_map", lambda _p: LLMResponse('{"techniques": []}'))
        from app.routes.attack import _llm_dep

        self.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)

    def create(self, removed: list[str] | None) -> Any:
        body = {} if removed is None else {"removed": removed}
        return self.c.post(f"/attack/services/{self.svc_id}/scenarios", headers=self.h, json=body)

    def run(self, scenario_id: str) -> Any:
        return self.c.post(
            f"/attack/scenarios/{scenario_id}/run", headers=self.h, json={"serves": "offline"}
        )

    def get(self, scenario_id: str) -> dict:
        r = self.c.get(f"/attack/scenarios/{scenario_id}", headers=self.h)
        assert r.status_code == 200, r.text
        return r.json()

    def coverage_snapshot(self) -> list[tuple]:
        with self.sessions() as s:
            rows = s.execute(
                select(AttackCoverage)
                .where(AttackCoverage.assessment_id == uuid.UUID(self.assessment_id))
                .order_by(AttackCoverage.technique_code)
            ).scalars()
            return [
                tuple(getattr(r, col.name) for col in AttackCoverage.__table__.columns)
                for r in rows
            ]


def _flags(code: str, tool: str, d=False, p=False, r=False) -> dict:
    return {
        "technique_code": code,
        "tool": tool,
        "detection": d,
        "prevention": p,
        "response": r,
        "rationale": "From the tool's classification.",
    }


def _patch(c: TestClient, h: dict, row_id: str, **body) -> None:
    r = c.patch(f"/attack/coverage/{row_id}", headers=h, json=body)
    assert r.status_code == 200, r.text


def _world(parts, *, release: bool = True) -> World:
    c, app, sessions = parts
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
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    with sessions() as db:
        td = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=uuid.UUID(cid),
            opened_by=uuid.UUID(me["id"]),
        )
        db.add(td)
        db.flush()
        cl = CapabilityList(service_id=td.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        for name in (EDR, SIEM, SOAR):
            db.add(CapabilityItem(capability_list_id=cl.id, name=name))
        db.commit()
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    assessment = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()
    preventable = [r for r in assessment["coverage"] if r["technique_code"] not in NOT_PREVENTABLE]
    a, b, cc = standalone_rows(preventable, 3)
    _patch(
        c,
        h,
        a["id"],
        status="covered",
        detection_tools=[EDR],
        prevention_tools=[EDR],
        response_tools=[SOAR],
    )
    _patch(c, h, b["id"], status="partial", detection_tools=[SIEM])
    _patch(c, h, cc["id"], status="gap", detection_tools=[EDR])
    # C's Detect tool is an INFERRED citation nobody has cleared: the state a
    # mitre_map run writes when it resolves a cited word to EDR Tool (#102),
    # here suggesting Gap. R3 computes Detect as awaiting review, so C is Gap
    # and agrees with its suggestion: no review queue, a confirmed base.
    with sessions() as db:
        db.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(cc["id"]))
            .values(
                unconfirmed_citations=[
                    {"tool": EDR, "cited": "EDR", "reason": "substring", "cleared_at": None}
                ]
            )
        )
        db.commit()
    r = c.post(f"/attack/assessments/{assessment['id']}/approve", headers=h)
    assert r.status_code == 200, r.text
    deliv = c.post(f"/attack/services/{svc_id}/deliverables/finalize", headers=h)
    assert deliv.status_code in (200, 201), deliv.text
    if release:
        rel = c.post(f"/attack/deliverables/{deliv.json()['id']}/release", headers=h)
        assert rel.status_code == 200, rel.text
    return World(
        c=c,
        app=app,
        sessions=sessions,
        h=h,
        cid=cid,
        svc_id=svc_id,
        assessment_id=assessment["id"],
        deliverable_id=deliv.json()["id"],
        a=a["technique_code"],
        b=b["technique_code"],
        cc=cc["technique_code"],
    )


def _error(r) -> dict:
    """The typed refusal's reason and message (the D-016 envelope)."""
    err = r.json()["error"]
    return {"reason": err["reason"], "message": err["message"]}


def _ai_runs(w: World) -> list[AiRun]:
    with w.sessions() as s:
        return list(s.execute(select(AiRun)).scalars())


# --- creating a scenario ----------------------------------------------------


def test_without_a_confirmed_assessment_a_what_if_is_refused_with_the_remedy(
    app_parts,  # noqa: F811
) -> None:
    c, app, sessions = app_parts
    w = _world(app_parts, release=False)
    # A second, draft version is not a base either; the approved one is. So
    # mint a service whose only assessment is a draft.
    svc = c.post(
        "/attack/services", headers=w.h, json={"kind": "attack_coverage", "title": "Draft only"}
    ).json()["id"]
    assert c.post(f"/attack/services/{svc}/assessments", headers=w.h).status_code == 201
    r = c.post(f"/attack/services/{svc}/scenarios", headers=w.h, json={"removed": [EDR]})
    assert r.status_code == 409, r.text
    assert _error(r) == {
        "reason": "scenario_needs_confirmed_assessment",
        "message": (
            "There is no confirmed assessment to compare with yet. Approve the ATT&CK "
            "assessment and review every technique in its review queue, then try again."
        ),
    }
    listed = c.get(f"/attack/services/{svc}/scenarios", headers=w.h)
    assert listed.status_code == 200, listed.text
    assert listed.json() == {"base": None, "scenarios": []}


def test_a_tool_the_assessment_does_not_cite_is_refused_by_name(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    r = w.create(["Firewall Tool"])
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_unknown_tool",
        "message": "Firewall Tool is not a tool this assessment cites. Pick it from the list.",
    }


@pytest.mark.parametrize("removed", [None, []])
def test_an_empty_change_list_is_refused(app_parts, removed) -> None:  # noqa: F811
    w = _world(app_parts)
    r = w.create(removed)
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_empty_change",
        "message": "Choose at least one tool to remove.",
    }


def test_a_what_if_pins_its_base_and_names_the_techniques_it_affects(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    r = w.create(["edr tool"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["state"] == "draft"
    assert body["removed"] == [EDR]
    assert body["affected_codes"] == sorted([w.a, w.cc])
    assert body["base_assessment_id"] == w.assessment_id
    assert body["base_approved_at"] is not None
    assert body["stale"] is False
    assert body["after"] is None
    assert body["run_status"] is None
    listed = w.c.get(f"/attack/services/{w.svc_id}/scenarios", headers=w.h).json()
    assert listed["base"]["assessment_id"] == w.assessment_id
    assert listed["base"]["tools"] == [EDR, SIEM, SOAR]
    assert [s["id"] for s in listed["scenarios"]] == [body["id"]]
    assert listed["scenarios"][0]["affected_count"] == 2


def test_another_tenants_scenario_is_not_found(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    sid = w.create([EDR]).json()["id"]
    other = w.c.post(
        "/admin/clients",
        headers={"Authorization": w.h["Authorization"]},
        json={"legal_name": "Other"},
    ).json()["id"]
    r = w.c.get(f"/attack/scenarios/{sid}", headers={**w.h, "X-Client-Id": other})
    assert r.status_code == 404, r.text
    assert _error(r)["reason"] == "scenario_not_found"


# --- running it -------------------------------------------------------------


def test_until_806_releases_the_prompt_a_run_is_a_typed_503_and_spends_nothing(
    app_parts,  # noqa: F811
) -> None:
    w = _world(app_parts)
    sid = w.create([EDR]).json()["id"]
    r = w.run(sid)
    assert r.status_code == 503, r.text
    assert _error(r) == {
        "reason": "scenario_analysis_unavailable",
        "message": "AI analysis for what-ifs is not available yet.",
    }
    assert _ai_runs(w) == []
    assert w.get(sid)["analysis_available"] is False


def _run_to_completion(w: World, sid: str) -> dict:
    r = w.run(sid)
    assert r.status_code == 202, r.text
    return w.get(sid)


def test_a_run_reassesses_only_the_affected_techniques_and_compares(
    app_parts, analysis_job  # noqa: F811
) -> None:
    w = _world(app_parts)
    # A lost Detect and Prevent; SIEM re-credits Detect -> Partial (was
    # Covered). C lost Detect; SIEM, a confirmed tool, credits it where the
    # base had only an uncleared inference -> Partial (was Gap).
    w.answer(
        {
            w.a: [_flags(w.a, SIEM, d=True)],
            w.cc: [_flags(w.cc, SIEM, d=True)],
        }
    )
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["run_status"] == "completed"
    assert body["state"] == "confirmed"
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert set(lists) == {w.a, w.cc}
    assert lists[w.a]["detection_tools"] == [SIEM]
    assert lists[w.a]["prevention_tools"] == []
    # The AI named no Respond tool for A; SOAR keeps the credit the base gave
    # it (the advisor, 05:25Z: the AI may only add).
    assert lists[w.a]["response_tools"] == [SOAR]
    diffs = {d["technique_code"]: d for d in body["differences"]}
    assert diffs[w.a]["today"] == "covered" and diffs[w.a]["after"] == "partial"
    assert diffs[w.cc]["today"] == "gap" and diffs[w.cc]["after"] == "partial"
    assert w.b not in diffs
    assert (body["today"]["covered"], body["today"]["partial"], body["today"]["gap"]) == (1, 1, 1)
    assert (body["after"]["covered"], body["after"]["partial"], body["after"]["gap"]) == (0, 3, 0)
    # Approved under #620's rules, so the outside counts are stated on both.
    for side in ("today", "after"):
        assert body[side]["unable_to_determine"] == 0, body[side]
        assert body[side]["outside_control_surface"] == 0, body[side]
    assert body["dropped"] == {}
    assert body["not_reassessed"] == []


def test_a_technique_that_would_score_higher_is_counted_and_marked(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """The advisor's addition (05:05Z). With base credits kept and only lost
    functions asked about, a technique can end HIGHER only where a lost
    function is re-credited by a confirmed tool and the base's was an uncleared
    inference (C). Counted on the scenario, marked in the differences, and only
    that one."""
    w = _world(app_parts)
    w.answer(
        {
            w.a: [_flags(w.a, SIEM, d=True)],
            w.cc: [_flags(w.cc, SIEM, d=True)],
        }
    )
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["scored_higher"] == 1
    marked = {d["technique_code"]: d["scored_higher"] for d in body["differences"]}
    assert marked == {w.a: False, w.cc: True}


def test_the_base_credits_stand_when_the_ai_names_nothing(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """The AI may only add (the advisor, 05:25Z): an answer naming nothing
    leaves each affected technique with the removal alone, re-assessed."""
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.a]["response_tools"] == [SOAR]
    assert lists[w.a]["detection_tools"] == [] and lists[w.a]["prevention_tools"] == []
    diffs = {d["technique_code"]: d for d in body["differences"]}
    assert diffs[w.a]["today"] == "covered" and diffs[w.a]["after"] == "partial"
    assert body["not_reassessed"] == []


def test_a_row_crediting_a_function_the_removal_did_not_take_is_set_aside(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """A lost Detect and Prevent; its Respond was untouched. A row crediting
    Respond is dropped whole and counted, so it cannot raise anything."""
    w = _world(app_parts)
    w.answer({w.a: [_flags(w.a, SIEM, d=True, r=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["dropped"] == {"function_not_lost": 1}
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.a]["detection_tools"] == []
    assert lists[w.a]["response_tools"] == [SOAR]


def test_nothing_scoring_higher_counts_zero_not_none(app_parts, analysis_job) -> None:  # noqa: F811
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["scored_higher"] == 0
    assert all(d["scored_higher"] is False for d in body["differences"])


def test_a_removed_tool_the_ai_names_anyway_is_dropped_and_counted(
    app_parts, analysis_job  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, EDR, d=True, p=True, r=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["dropped"] == {"tool_outside_change": 1}
    assert body["scored_higher"] == 0
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert EDR not in lists[w.cc]["detection_tools"]


def test_a_batch_that_fails_leaves_its_techniques_not_reassessed(
    app_parts, analysis_job, monkeypatch  # noqa: F811
) -> None:
    """Not the frozen row passed off as re-assessed: the removal alone, and
    named. One technique per batch, so one batch can fail while the other
    answers (a run whose every batch fails is a failed run, as mitre_map's)."""
    monkeypatch.setattr("app.attack.scenario.BATCH_SIZE", 1)
    w = _world(app_parts)
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        if payload.get("technique_codes") == [w.a]:
            return LLMResponse('{"rows": "nothing"}')
        return LLMResponse(json.dumps({"rows": [_flags(w.cc, SIEM, d=True)]}))

    provider.register(PURPOSE, respond)
    from app.routes.attack import _llm_dep

    w.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["run_status"] == "completed"
    assert body["not_reassessed"] == [w.a]
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.a]["detection_tools"] == []
    assert lists[w.a]["prevention_tools"] == []
    assert lists[w.a]["response_tools"] == [SOAR]
    assert lists[w.cc]["detection_tools"] == [SIEM]
    run = w.c.get(f"/ai-runs/{body['ai_run_id']}", headers=w.h).json()
    assert (run["batches_total"], run["batches_failed"]) == (2, 1)


def test_a_run_writes_nothing_the_assessment_or_the_client_reads(
    app_parts, analysis_job  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True, p=True, r=True)]})
    rows_before = w.coverage_snapshot()
    dash_url = f"/clients/{w.cid}/attack/{w.svc_id}/dashboard"
    dash_before = w.c.get(dash_url, headers=w.h)
    assert dash_before.status_code == 200, dash_before.text
    sid = w.create([EDR]).json()["id"]
    assert _run_to_completion(w, sid)["run_status"] == "completed"
    assert w.coverage_snapshot() == rows_before
    assert w.c.get(dash_url, headers=w.h).content == dash_before.content


def test_a_discarded_what_if_cannot_be_run(app_parts, analysis_job) -> None:  # noqa: F811
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    r = w.c.post(f"/attack/scenarios/{sid}/discard", headers=w.h)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "discarded"
    r = w.run(sid)
    assert r.status_code == 409, r.text
    assert _error(r)["reason"] == "scenario_discarded"
    assert _ai_runs(w) == []


def test_a_discard_racing_the_run_wins(app_parts, analysis_job) -> None:  # noqa: F811
    """Discarded before the job starts: it ends FAILED without calling the AI,
    so nothing is spent on a what-if nobody will read."""
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True, p=True, r=True)]})
    runner: DeferringRunner = defer_runs(w.app)
    sid = w.create([EDR]).json()["id"]
    assert w.run(sid).status_code == 202
    assert w.c.post(f"/attack/scenarios/{sid}/discard", headers=w.h).status_code == 200
    assert runner.run_all() == 1
    body = w.get(sid)
    assert body["run_status"] == "failed"
    assert body["techniques"] == []
    assert body["scored_higher"] is None
    with w.sessions() as db:
        assert db.execute(select(LLMCall)).scalars().all() == []


def test_a_what_if_overtaken_by_a_newer_confirmed_assessment_is_stale_and_not_run(
    app_parts, analysis_job  # noqa: F811
) -> None:
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    v2 = w.c.post(f"/attack/services/{w.svc_id}/assessments", headers=w.h)
    assert v2.status_code == 201, v2.text
    r = w.c.post(f"/attack/assessments/{v2.json()['id']}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    assert w.get(sid)["stale"] is True
    r = w.run(sid)
    assert r.status_code == 409, r.text
    assert _error(r)["reason"] == "scenario_stale"
    assert _ai_runs(w) == []


def test_a_discard_landing_while_the_ai_answers_still_wins(
    app_parts, analysis_job, monkeypatch  # noqa: F811
) -> None:
    """The job's second check, after the AI call (D-031's re-read): a discard
    made while the batches were out is not overwritten by their answers. The
    discard lands as the batches return, from another session, as a second
    request's would."""
    from app.routes import attack_scenarios

    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    real = attack_scenarios.run_batches

    def batches_then_discard(*args, **kwargs):
        out = real(*args, **kwargs)
        with w.sessions() as s:
            s.execute(
                update(AttackScenario)
                .where(AttackScenario.id == uuid.UUID(sid))
                .values(state=AttackScenarioState.DISCARDED)
            )
            s.commit()
        return out

    monkeypatch.setattr(attack_scenarios, "run_batches", batches_then_discard)
    assert w.run(sid).status_code == 202
    body = w.get(sid)
    run = w.c.get(f"/ai-runs/{body['ai_run_id']}", headers=w.h).json()
    assert run["error_reason"] == "scenario_discarded", run
    assert body["state"] == "discarded"
    assert body["run_status"] == "failed"
    assert body["techniques"] == []
    assert body["scored_higher"] is None


def test_a_discard_landing_as_the_run_starts_is_not_undone(
    app_parts, analysis_job  # noqa: F811
) -> None:
    """Between `start_run` committing the run and the route recording it, a
    discard from another request lands. The route's own state change must not
    write CONFIRMED over it."""
    from app.ai.runs import get_ai_run_runner

    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    held: list = []

    def discard_then_hold(job) -> None:
        with w.sessions() as s:
            s.execute(
                update(AttackScenario)
                .where(AttackScenario.id == uuid.UUID(sid))
                .values(state=AttackScenarioState.DISCARDED)
            )
            s.commit()
        held.append(job)

    w.app.dependency_overrides[get_ai_run_runner] = lambda: discard_then_hold
    r = w.run(sid)
    assert r.status_code == 202, r.text
    assert len(held) == 1
    body = w.get(sid)
    assert body["state"] == "discarded"
    assert body["ai_run_id"] == r.json()["run_id"]


def test_an_analysed_what_if_is_not_run_twice(app_parts, analysis_job) -> None:  # noqa: F811
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    _run_to_completion(w, sid)
    r = w.run(sid)
    assert r.status_code == 409, r.text
    assert _error(r)["reason"] == "scenario_already_run"


def test_a_non_admin_cannot_reach_a_what_if(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    sid = w.create([EDR]).json()["id"]
    client_bearer = w.c.post(
        "/auth/register",
        json={
            "email": "someone@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "C",
        },
    ).json()["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {client_bearer}", "X-Client-Id": w.cid}
    for method, url in (
        ("get", f"/attack/scenarios/{sid}"),
        ("get", f"/attack/services/{w.svc_id}/scenarios"),
        ("post", f"/attack/services/{w.svc_id}/scenarios"),
        ("post", f"/attack/scenarios/{sid}/run"),
        ("post", f"/attack/scenarios/{sid}/discard"),
    ):
        r = getattr(w.c, method)(url, headers=h)
        assert r.status_code in (401, 403), (url, r.status_code, r.text)
