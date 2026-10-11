"""#802 slice A: the ATT&CK what-if, through the routes an admin reaches.

The world is built the way a consultant builds it: tools typed into the
matrix, the assessment approved under R3, the deliverable finalized and
released. The AI is a fixture provider answering the PROMPT's contract
(`{"rows": [{technique_code, tool, detection, prevention, response,
rationale}]}`), and the job is the one `app/ai/jobs.py` registers with
Gene's approved prompt (#802).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

from app.ai import engine as ai_engine
from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.attack.catalog import NOT_PREVENTABLE
from app.models.ai_run import AiRun
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.models.attack_scenario import AttackScenario, AttackScenarioRow, AttackScenarioState
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.deliverable import Deliverable
from app.models.llm_call import LLMCall
from app.models.service import Service, ServiceKind, ServiceStatus
from app.routes.tech_debt import SECURITY_CLASSIFICATION_OVERRIDDEN
from app.storage.local import LocalFilesystemStorage
from tests._ai_runs import DeferringRunner, defer_runs
from tests._attack_rows import standalone_rows
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

PURPOSE = "attack_scenario_delta"

EDR, SIEM, SOAR = "EDR Tool", "SIEM Tool", "SOAR Tool"


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
        self.use(provider)

    def use(self, provider: FixtureProvider) -> None:
        """Serve `provider` to mitre_map's route and to the what-if's, which
        builds its client only after its refusals (F4)."""
        from app.routes.attack import _llm_dep
        from app.routes.attack_scenarios import _llm_builder

        self.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
        self.app.dependency_overrides[_llm_builder] = lambda: (lambda: LLMClient(provider))

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
            out: list[tuple] = [
                tuple(getattr(r, col.name) for col in AttackCoverage.__table__.columns)
                for r in rows
            ]
            # The assessment row itself and every deliverable of the service:
            # a what-if may write none of them (#815 review, F9).
            a = s.get(AttackAssessment, uuid.UUID(self.assessment_id))
            out.append(tuple(getattr(a, col.name) for col in AttackAssessment.__table__.columns))
            for d in s.execute(
                select(Deliverable)
                .where(Deliverable.service_id == uuid.UUID(self.svc_id))
                .order_by(Deliverable.id)
            ).scalars():
                out.append(tuple(getattr(d, col.name) for col in Deliverable.__table__.columns))
            return out


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


#: A tool named after the client ("Acme"), and the spelling a later
#: extraction stores for the same tool once the tenant has a legal name
#: (`citations.py`, the alias tier): both can sit on one capability list.
SOC_NAMED = "Acme SOC Platform"
SOC_PLACEHOLDER = "[CLIENT] SOC Platform"


#: Two DISTINCT tools the egress shows as one placeholder (the address rule).
UNIT_42 = "Unit 42"
UNIT_7 = "Unit 7"


def _world(
    parts,
    *,
    release: bool = True,
    soc_twins: bool = False,
    unit_pair: bool = False,
    list_status: CapabilityListStatus = CapabilityListStatus.APPROVED,
) -> World:
    """`list_status` APPROVED (the default) makes a list approved with no
    `approved_membership`: the shape of a list approved before migration 0043,
    whose drift since the base cannot be checked. DRAFT reads live rows."""
    c, app, sessions = parts
    # Storage on local disk, never the real backend: finalizing the base's
    # deliverable uploads its PDF, and the real dependency is MinIO, which CI
    # does not run and a dev container would share (#815 CI). As
    # `test_attack_acceptance` and `test_ai_runs_csf` do, it lives under
    # pytest's `tmp_path`: the `app_parts` fixture's, the directory holding its
    # SQLite database, so pytest cleans it up with the test.
    from app.routes.artifacts import _storage_dep

    tmp_path = Path(sessions.kw["bind"].url.database).parent
    storage = LocalFilesystemStorage(tmp_path / "storage")
    app.dependency_overrides[_storage_dep] = lambda: storage
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
        cl = CapabilityList(service_id=td.id, version=1, status=list_status)
        db.add(cl)
        db.flush()
        extra = (SOC_NAMED, SOC_PLACEHOLDER) if soc_twins else ()
        extra += (UNIT_42, UNIT_7) if unit_pair else ()
        for name in (EDR, SIEM, SOAR, *extra):
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
    if soc_twins:
        # B cites the client-named spelling; A also cites its placeholder twin.
        _patch(c, h, b["id"], status="partial", detection_tools=[SIEM], response_tools=[SOC_NAMED])
        _patch(
            c,
            h,
            a["id"],
            status="covered",
            detection_tools=[EDR],
            prevention_tools=[EDR],
            response_tools=[SOAR, SOC_PLACEHOLDER],
        )
    elif unit_pair:
        _patch(c, h, b["id"], status="partial", detection_tools=[SIEM], response_tools=[UNIT_42])
    else:
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


@pytest.mark.parametrize(
    "body",
    [{}, {"removed": []}, {"removed": [], "added": []}],
    ids=["missing", "empty", "both-empty"],
)
def test_an_empty_change_list_is_refused(app_parts, body) -> None:  # noqa: F811
    """Slice B: B8 (14:58Z) replaces copy 17, because a what-if may only add;
    the refusal is kept, and reached through the route (approved edit)."""
    w = _world(app_parts)
    r = w.c.post(f"/attack/services/{w.svc_id}/scenarios", headers=w.h, json=body)
    assert r.status_code == 422, r.text
    assert _error(r) == {
        "reason": "scenario_empty_change",
        "message": "Choose at least one tool to remove or add.",
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


def _remove_the_job(m: pytest.MonkeyPatch) -> None:
    """The kept 503 guard (copy 16) is a RATCHET: with the job registered it
    should never fire. Its tests remove the registration inside a
    `monkeypatch.context()` only, so the real job is back when the block ends,
    and each asserts that it is."""
    ai_engine.registered_jobs()  # registers the defaults before one is removed
    m.delitem(ai_engine._REGISTRY, PURPOSE)


def test_if_the_job_is_ever_unregistered_a_run_is_a_typed_503_and_spends_nothing(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    w = _world(app_parts)
    sid = w.create([EDR]).json()["id"]
    with monkeypatch.context() as m:
        _remove_the_job(m)
        r = w.run(sid)
        assert r.status_code == 503, r.text
        assert _error(r) == {
            "reason": "scenario_analysis_unavailable",
            "message": "AI analysis for what-ifs is not available yet.",
        }
        assert _ai_runs(w) == []
        assert w.get(sid)["analysis_available"] is False
    assert PURPOSE in ai_engine.registered_jobs()  # restored, not deleted


def _run_to_completion(w: World, sid: str) -> dict:
    r = w.run(sid)
    assert r.status_code == 202, r.text
    return w.get(sid)


def test_a_run_reassesses_only_the_affected_techniques_and_compares(
    app_parts,  # noqa: F811
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
    # Q4 (R3): C's Detect rested on a tool awaiting review in the base; after
    # the change it rests on SIEM, which is confirmed. The sentence is the
    # approved Q4 text, written out here from the approval, not imported.
    assert body["today"]["awaiting_review"] == 1
    assert body["today"]["awaiting_review_text"] == (
        "1 technique lists tools awaiting review; it is scored as if those tools were "
        "not in place."
    )
    assert body["after"]["awaiting_review"] == 0
    assert body["after"]["awaiting_review_text"] is None
    # Approved under #620's rules, so the outside counts are stated on both.
    for side in ("today", "after"):
        assert body[side]["unable_to_determine"] == 0, body[side]
        assert body[side]["outside_control_surface"] == 0, body[side]
    assert body["dropped"] == {}
    assert body["not_reassessed"] == []


def test_a_technique_that_would_score_higher_is_counted_and_marked(app_parts) -> None:  # noqa: F811
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


def test_the_base_credits_stand_when_the_ai_names_nothing(app_parts) -> None:  # noqa: F811
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
    app_parts,  # noqa: F811
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


def test_nothing_scoring_higher_counts_zero_not_none(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    w.answer({})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["scored_higher"] == 0
    assert all(d["scored_higher"] is False for d in body["differences"])


def test_a_removed_tool_the_ai_names_anyway_is_dropped_and_counted(app_parts) -> None:  # noqa: F811
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, EDR, d=True, p=True, r=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["dropped"] == {"tool_outside_change": 1}
    assert body["scored_higher"] == 0
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert EDR not in lists[w.cc]["detection_tools"]


def test_a_batch_that_fails_leaves_its_techniques_not_reassessed(
    app_parts, monkeypatch  # noqa: F811
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
    w.use(provider)
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


def test_a_run_writes_nothing_the_assessment_or_the_client_reads(app_parts) -> None:  # noqa: F811
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


def test_a_discarded_what_if_cannot_be_run(app_parts) -> None:  # noqa: F811
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


def test_a_discard_racing_the_run_wins(app_parts) -> None:  # noqa: F811
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
    app_parts,  # noqa: F811
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
    app_parts, monkeypatch  # noqa: F811
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
    assert body["run_error"] == {
        "reason": "scenario_discarded",
        "message": "This what-if was set aside before the run finished.",
    }
    assert body["state"] == "discarded"
    assert body["run_status"] == "failed"
    assert body["techniques"] == []
    assert body["scored_higher"] is None


def test_a_discard_landing_as_the_run_starts_is_not_undone(app_parts) -> None:  # noqa: F811
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


def test_a_failed_run_says_why_and_can_be_run_again(app_parts) -> None:  # noqa: F811
    """A run whose every batch fails ends FAILED, the scenario says why, and
    the same what-if can be run again: nothing was written for it."""
    w = _world(app_parts)
    provider = FixtureProvider()
    provider.register(PURPOSE, lambda _p: LLMResponse('{"rows": "nothing"}'))
    w.use(provider)
    sid = w.create([EDR]).json()["id"]
    assert w.run(sid).status_code == 202
    body = w.get(sid)
    assert body["run_status"] == "failed"
    assert body["run_error"]["reason"], body["run_error"]
    assert body["run_error"]["message"], body["run_error"]
    assert body["techniques"] == []

    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    assert w.run(sid).status_code == 202
    again = w.get(sid)
    assert again["run_status"] == "completed"
    assert again["run_error"] is None


def test_a_row_whose_technique_is_not_a_string_is_dropped_and_the_run_completes(
    app_parts,  # noqa: F811
) -> None:
    """F1: a list where a code belongs is unhashable. It is set aside and
    counted; it never takes the batch's other answers, or the run, with it."""
    w = _world(app_parts)
    w.answer(
        {
            w.cc: [
                {**_flags(w.cc, SIEM, d=True), "technique_code": [w.cc]},
                _flags(w.cc, SIEM, d=True),
            ]
        }
    )
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["run_status"] == "completed", body["run_error"]
    assert body["dropped"] == {"technique_outside_slice": 1}
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["detection_tools"] == [SIEM]


def test_a_removed_tool_is_not_offered_or_credited_under_its_other_spelling(
    app_parts,  # noqa: F811
) -> None:
    """F2. The list holds the client-named tool AND its placeholder spelling,
    which the egress shows the model identically. Removing one removes both:
    neither is offered, and the AI naming the other spelling is not credited."""
    from app.ai.redact import redact_for_ai

    shown, counts = redact_for_ai(SOC_NAMED, mode="strict", client_org_name="Acme")
    assert counts and shown == SOC_PLACEHOLDER  # the world: one tool, two spellings
    w = _world(app_parts, soc_twins=True)
    offered: list[list[str]] = []
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        offered.append([t["name"] for t in payload.get("available_tools") or []])
        return LLMResponse(json.dumps({"rows": [_flags(w.b, SOC_PLACEHOLDER, r=True)]}))

    provider.register(PURPOSE, respond)
    w.use(provider)
    sid = w.create([SOC_NAMED]).json()["id"]
    body = _run_to_completion(w, sid)
    # Round 2, item 1: A cites only the TWIN spelling, and is affected too.
    assert body["affected_codes"] == sorted([w.a, w.b])
    assert len(offered) == 1
    assert SOC_PLACEHOLDER not in offered[0] and SOC_NAMED not in offered[0], offered
    assert body["dropped"] == {"tool_outside_change": 1}
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.b]["response_tools"] == []
    # A loses the twin's Respond credit and keeps SOAR's.
    assert lists[w.a]["response_tools"] == [SOAR]


def test_a_distinct_tool_sharing_only_a_placeholder_stays_offered_but_is_not_credited(
    app_parts,  # noqa: F811
) -> None:
    """Round 2, item 2. `Unit 7` is not `Unit 42`, but the model is shown both
    as one placeholder. It stays offered; a citation of the shared string is
    refused and counted, never credited."""
    from app.ai.redact import redact_for_ai

    shared, _ = redact_for_ai(UNIT_42, mode="strict", client_org_name="Acme")
    assert shared == redact_for_ai(UNIT_7, mode="strict", client_org_name="Acme")[0]
    w = _world(app_parts, unit_pair=True)
    offered: list[list[str]] = []
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        offered.append([t["name"] for t in payload.get("available_tools") or []])
        return LLMResponse(json.dumps({"rows": [_flags(w.b, shared, r=True)]}))

    provider.register(PURPOSE, respond)
    w.use(provider)
    sid = w.create([UNIT_42]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["affected_codes"] == [w.b]
    assert shared in offered[0], offered  # Unit 7 is still offered
    assert body["dropped"] == {"tool_unconfirmed": 1}
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.b]["response_tools"] == []


def test_a_completed_what_if_is_never_repointed_at_a_later_run(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    """Round 2, item 3. A run completing between the route's check and
    `start_run` lets a second run start; the scenario keeps the run that wrote
    its result, and the second fails on its own."""
    from app.routes import attack_scenarios

    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    first = _run_to_completion(w, sid)
    assert first["run_status"] == "completed"
    # The window: the route's check has passed, the result has landed.
    monkeypatch.setattr(attack_scenarios, "_refuse_unless_runnable", lambda _db, _s: None)
    second = w.run(sid)
    assert second.status_code == 202, second.text
    body = w.get(sid)
    assert body["ai_run_id"] == first["ai_run_id"]
    assert body["run_status"] == "completed"
    late = w.c.get(f"/ai-runs/{second.json()['run_id']}", headers=w.h).json()
    assert late["status"] == "failed" and late["error_reason"] == "scenario_already_run", late


XDR = "XDR Tool"


def _add_tool_after_approval(w: World, name: str) -> None:
    """A row added to the client's (DRAFT) list after the base was approved:
    the second change the advisor's (b2) discloses."""
    with w.sessions() as db:
        cl = db.execute(select(CapabilityList)).scalars().one()
        db.add(CapabilityItem(capability_list_id=cl.id, name=name))
        db.commit()


def test_a_tool_added_since_the_base_is_counted_and_its_credit_marked(
    app_parts,  # noqa: F811
) -> None:
    """(b2), count above zero: the tool added after approval is offered, the
    count says so, and the technique the AI credited to it is marked."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _add_tool_after_approval(w, XDR)
    w.answer({w.cc: [_flags(w.cc, XDR, d=True)], w.a: [_flags(w.a, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 1
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_added_tools"] == [XDR]
    assert lists[w.a]["credited_added_tools"] == []
    marks = {d["technique_code"]: d["credited_added_tool"] for d in body["differences"]}
    assert marks[w.cc] is True and marks[w.a] is False


def test_no_tool_added_since_the_base_counts_zero(app_parts) -> None:  # noqa: F811
    """(b2), count zero: checked, and nothing was added. 0, not None."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 0
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_a_list_approved_before_0043_cannot_be_checked_and_reads_null_never_zero(
    app_parts,  # noqa: F811
) -> None:
    """(b2), could not check: an approved list with no recorded membership.
    Missing data defaults to unconfirmed: None, never 0."""
    w = _world(app_parts)  # APPROVED, no approved_membership
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["after"] is not None
    assert body["tools_added_since_base"] is None


def test_a_row_naming_an_added_tool_with_no_function_is_not_marked(app_parts) -> None:  # noqa: F811
    """Round 3, item 1: an accepted row whose functions are all false names the
    added tool and credits it with nothing. No mark."""
    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    _add_tool_after_approval(w, XDR)
    w.answer({w.cc: [_flags(w.cc, XDR)]})  # every function false
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 1
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_added_tools"] == []
    assert all(d["credited_added_tool"] is False for d in body["differences"])


def test_a_post_0043_snapshot_judges_each_entry_by_its_item(app_parts) -> None:  # noqa: F811
    """Round 3, item 2. The list is approved WITH a D-053 snapshot, written by
    the real writer. A tool added and re-approved after the base is counted;
    the snapshot's older entries are not."""
    from app.routes.tech_debt import build_approved_membership

    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        cl = db.execute(select(CapabilityList)).scalars().one()
        db.add(CapabilityItem(capability_list_id=cl.id, name=XDR))
        db.flush()
        cl.status = CapabilityListStatus.APPROVED
        cl.approved_membership = build_approved_membership(db, cl.id)
        db.commit()
        assert {e["name"] for e in cl.approved_membership} >= {EDR, SIEM, SOAR, XDR}
    w.answer({w.cc: [_flags(w.cc, XDR, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 1
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_added_tools"] == [XDR]


def test_one_scenarios_result_never_stops_anothers_run_being_recorded(
    app_parts,  # noqa: F811
) -> None:
    """Round 3, item 5: the no-repoint guard is correlated to ITS scenario. A
    result written for one what-if does not keep another from recording its
    run."""
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    first = w.create([EDR]).json()["id"]
    assert _run_to_completion(w, first)["run_status"] == "completed"
    second = w.create([SOAR]).json()["id"]
    started = w.run(second)
    assert started.status_code == 202, started.text
    assert w.get(second)["ai_run_id"] == started.json()["run_id"]


LATE = "Late Override Tool"
EARLY = "Early Override Tool"


def test_an_old_row_brought_into_scope_after_the_base_is_counted_and_one_before_is_not(
    app_parts,  # noqa: F811
) -> None:
    """The advisor's (ii), 08:57Z. Two rows created BEFORE the base.

    - LATE is a CONFIRMED non-security row (`security_class_confirmed`), so it
      is genuinely OUT of scope and offered to nobody -- until the real
      override endpoint brings it in, AFTER the base was approved. It counts.
    - EARLY was overridden BEFORE the base was approved, so it has been in
      scope throughout, exactly as the override leaves a row. It does not.

    The scope precondition is asserted through the membership rule itself,
    not assumed. Which tool counted is asserted where the GET names it: the
    technique credited to it."""
    from app.routes.attack import _client_capability_membership

    w = _world(app_parts, list_status=CapabilityListStatus.DRAFT)
    with w.sessions() as db:
        cl = db.execute(select(CapabilityList)).scalars().one()
        a = db.get(AttackAssessment, uuid.UUID(w.assessment_id))
        base_at = a.approved_at
        late = CapabilityItem(
            capability_list_id=cl.id,
            name=LATE,
            security_related=False,
            security_class_confirmed=True,
            created_at=base_at - timedelta(days=30),
        )
        # As `override_security_classification` leaves a row.
        early = CapabilityItem(
            capability_list_id=cl.id,
            name=EARLY,
            security_related=True,
            security_functions=["detect"],
            security_class_confirmed=False,
            created_at=base_at - timedelta(days=30),
        )
        db.add_all([late, early])
        db.flush()
        # EARLY's override, recorded before the base was approved: the world,
        # written as the audit spine writes it.
        db.add(
            AuditEntry(
                action=SECURITY_CLASSIFICATION_OVERRIDDEN,
                target_type="capability_item",
                target_id=early.id,
                at=base_at - timedelta(days=1),
            )
        )
        db.commit()
        late_id = str(late.id)
        offered = {
            p.capability.name for p in _client_capability_membership(db, uuid.UUID(w.cid)).sent
        }
    assert LATE not in offered and EARLY in offered, offered  # the precondition
    r = w.c.post(
        f"/tech-debt/capability-items/{late_id}/security-classification/override",
        headers=w.h,
        json={"security_functions": ["detect"]},
    )
    assert r.status_code == 200, r.text
    # A lost Detect and Prevent; C lost Detect. The AI credits each old row.
    w.answer({w.cc: [_flags(w.cc, LATE, d=True)], w.a: [_flags(w.a, EARLY, d=True)]})
    sid = w.create([EDR]).json()["id"]
    body = _run_to_completion(w, sid)
    assert body["tools_added_since_base"] == 1
    lists = {t["technique_code"]: t for t in body["techniques"]}
    assert lists[w.cc]["credited_added_tools"] == [LATE]
    assert lists[w.a]["detection_tools"] == [EARLY]
    assert lists[w.a]["credited_added_tools"] == []


class _CountingLimiter:
    def __init__(self) -> None:
        self.charged = 0

    def enforce_ai(self, _client_id) -> None:
        self.charged += 1


def test_a_run_refused_before_any_ai_spends_no_rate_limit_token_and_builds_no_provider(
    app_parts, monkeypatch  # noqa: F811
) -> None:
    """F4: the 503 comes before the rate limit and the provider."""
    from app.routes.attack_scenarios import _llm_builder
    from app.security.rate_limit import get_rate_limiter

    w = _world(app_parts)
    limiter = _CountingLimiter()
    built: list[int] = []
    w.app.dependency_overrides[get_rate_limiter] = lambda: limiter
    w.app.dependency_overrides[_llm_builder] = lambda: (lambda: built.append(1))
    sid = w.create([EDR]).json()["id"]
    with monkeypatch.context() as m:
        _remove_the_job(m)
        assert w.run(sid).status_code == 503
    assert limiter.charged == 0
    assert built == []
    assert PURPOSE in ai_engine.registered_jobs()  # restored, not deleted


def test_a_run_that_starts_spends_one_rate_limit_token(app_parts) -> None:  # noqa: F811
    """The other half of F4's test: the counter is the one the route charges."""
    from app.security.rate_limit import get_rate_limiter

    w = _world(app_parts)
    w.answer({})
    limiter = _CountingLimiter()
    w.app.dependency_overrides[get_rate_limiter] = lambda: limiter
    sid = w.create([EDR]).json()["id"]
    assert w.run(sid).status_code == 202
    assert limiter.charged == 1


def test_a_second_run_never_replaces_a_result_already_written(app_parts) -> None:  # noqa: F811
    """F5: a run that passed the route's check but finds a result already
    written by the time it answers is refused, typed, and deletes nothing."""
    w = _world(app_parts)
    w.answer({w.cc: [_flags(w.cc, SIEM, d=True)]})
    runner = defer_runs(w.app)
    sid = w.create([EDR]).json()["id"]
    assert w.run(sid).status_code == 202
    with w.sessions() as db:
        db.add(
            AttackScenarioRow(
                scenario_id=uuid.UUID(sid),
                technique_code=w.cc,
                detection_tools=[SOAR],
                prevention_tools=[],
                response_tools=[],
                ai_rows=[],
            )
        )
        db.commit()
    assert runner.run_all() == 1
    body = w.get(sid)
    assert body["run_status"] == "failed"
    assert body["run_error"]["reason"] == "scenario_already_run"
    assert [(t["technique_code"], t["detection_tools"]) for t in body["techniques"]] == [
        (w.cc, [SOAR])
    ]


def test_an_analysed_what_if_is_not_run_twice(app_parts) -> None:  # noqa: F811
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


class _RecordingProvider(FixtureProvider):
    """A fixture provider that also records the prompt each call SENDS."""

    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        if payload.get("__purpose__") == PURPOSE:
            self.prompts.append(prompt)
        return super().complete(prompt, payload)


def test_a_run_with_the_shipped_job_is_accepted_and_sends_the_shipped_prompt(
    app_parts,  # noqa: F811
) -> None:
    """#802: the job ships registered, so a run is accepted (no 503) and every
    batch sends the approved text. The digest is the approved text's, taken from
    Gene's comments (#802 comments 5970337002 and 5982780636), not from code."""
    import hashlib

    # test-integrity: the spec is the literal digest of Gene's approved text; the constant is compared with the prompt the real run SENT, and hashed against that digest
    from app.ai.jobs import _ATTACK_SCENARIO_DELTA_PROMPT

    w = _world(app_parts)
    provider = _RecordingProvider()
    provider.register(PURPOSE, lambda _p: LLMResponse('{"rows": []}'))
    provider.register("mitre_map", lambda _p: LLMResponse('{"techniques": []}'))
    w.use(provider)
    sid = w.create([EDR]).json()["id"]
    assert w.get(sid)["analysis_available"] is True
    body = _run_to_completion(w, sid)
    assert body["run_status"] == "completed"
    assert provider.prompts, "the run sent no what-if call"
    assert set(provider.prompts) == {_ATTACK_SCENARIO_DELTA_PROMPT}
    assert (
        hashlib.sha256(provider.prompts[0].encode()).hexdigest()
        == "b678cd2453991677c3be16153f3ace5f8aa06840fc0e8e00fd0771f7be31525b"
    )
