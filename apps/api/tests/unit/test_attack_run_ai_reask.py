"""#1047: an ATT&CK Run-AI asks the model a second time for the techniques a
successful batch left out, and reports how many are still missing after that.

A live run left about 228 techniques unscored. #853 made the run NAME the
techniques a successful batch left out; this re-asks for exactly those, once,
in the same run. What is still missing afterwards is what `omitted_count` and
`omitted_techniques` report.

Every test drives `POST /attack/services/{id}/run-ai`. The provider answers in
the prompt's own keys for the codes the PAYLOAD asked about. It tells a re-ask
from a first ask by whether it has been asked for a code before: first-pass
batches are disjoint. Expected values come from what the test left out and
what the payloads asked, never from a constant of the module under test.
Fixture mode cannot reach any of this: its mitre_map fixture answers every code.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.ai.isolation import RedactionRefused
from app.ai.llm import FixtureProvider, LLMResponse
from app.ai.runs import RunContext
from tests._ai_runs import attack_run_ai, run_ai_expecting_failure
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _admin,
    _seed_tech_debt_tools,
    app_client,
)

pytestmark = pytest.mark.unit


def _entry(code: str, rationale: str = "First answer.", status: str = "gap") -> dict:
    """One answer in the prompt's keys, citing nothing."""
    return {
        "technique_code": code,
        "status": status,
        "detection_tools": [],
        "prevention_tools": [],
        "response_tools": [],
        "rationale": rationale,
    }


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str
    rows: list[dict]
    # Each call's `technique_codes`, in the order the provider received them.
    sent: list[list[str]] = field(default_factory=list)

    def code(self, i: int) -> str:
        return self.rows[i]["technique_code"]

    def respond(
        self,
        *,
        omit_first: frozenset[str] = frozenset(),
        omit_always: frozenset[str] = frozenset(),
        fail_first_with: str | None = None,
        fail_reask: bool = False,
        refuse_reask: bool = False,
        reask_stray: str | None = None,
        reask_status: str = "gap",
    ) -> None:
        """Answer every code asked, except:

        `omit_first`: left out the first time asked, answered on a re-ask.
        `omit_always`: left out every time.
        `fail_first_with`: the FIRST batch asking for that code raises.
        `fail_reask`: every re-ask call raises.
        `refuse_reask`: every re-ask call is refused by the redaction gate.
        `reask_stray`: a re-ask also answers for this code, which it was not
        asked about, with the rationale "Stray answer.".
        `reask_status`: the status every re-ask entry gives.
        """
        asked_before: Counter[str] = Counter()

        def _answer(payload: dict) -> LLMResponse:
            asked = list(payload.get("technique_codes") or [])
            self.sent.append(asked)
            reask = any(asked_before[c] for c in asked)
            asked_before.update(asked)
            if reask and fail_reask:
                raise RuntimeError("provider closed the connection")
            if reask and refuse_reask:
                raise RedactionRefused(
                    "redaction_unavailable",
                    "Redaction refused this payload.",
                    status_code=503,
                    sent_before=True,
                )
            if not reask and fail_first_with in asked:
                raise RuntimeError("provider closed the connection")
            left_out = omit_always | (frozenset() if reask else omit_first)
            entries = [
                (_entry(c, "Second answer.", reask_status) if reask else _entry(c, "First answer."))
                for c in asked
                if c not in left_out
            ]
            if reask and reask_stray is not None:
                entries.append(_entry(reask_stray, "Stray answer."))
            return LLMResponse(json.dumps({"techniques": entries}))

        self.provider.register("mitre_map", _answer)

    def run(self) -> dict:
        return attack_run_ai(self.c, self.svc_id, self.h)

    def patch_status(self, i: int, status: str) -> None:
        r = self.c.patch(
            f"/attack/coverage/{self.rows[i]['id']}", headers=self.h, json={"status": status}
        )
        assert r.status_code == 200, r.text

    def reasks(self) -> list[list[str]]:
        """The calls that asked for a code an earlier call had asked for."""
        seen: set[str] = set()
        out = []
        for batch in self.sent:
            if seen & set(batch):
                out.append(batch)
            seen.update(batch)
        return out

    def audit(self) -> dict:
        from app.models.audit_entry import AuditEntry

        with self.sessions() as db:
            rows = (
                db.execute(select(AuditEntry.details).where(AuditEntry.action == "attack.run_ai"))
                .scalars()
                .all()
            )
        assert len(rows) == 1, rows
        return rows[0]


def _world(app_client: tuple, n: int) -> World:  # noqa: F811
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    coverage = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"]
    return World(c, TestSession, provider, h, svc_id, standalone_rows(coverage, n))


def _row(result: dict, code: str) -> dict:
    (row,) = [t for t in result["coverage"] if t["technique_code"] == code]
    return row


def test_a_run_that_answers_everything_asks_nothing_again(app_client) -> None:  # noqa: F811
    w = _world(app_client, 1)
    w.respond()
    result = w.run()
    assert w.reasks() == []
    assert (result["reasked_count"], result["reask_batches_total"]) == (0, 0)
    assert result["reask_batches_failed"] == 0
    assert w.audit()["reasked_count"] == 0


def test_a_technique_left_out_once_is_asked_again_and_gets_its_status(
    app_client,  # noqa: F811
) -> None:
    w = _world(app_client, 2)
    left_out = frozenset({w.code(0), w.code(1)})
    w.respond(omit_first=left_out)
    result = w.run()

    # One more call, asking for exactly the techniques left out.
    assert [sorted(b) for b in w.reasks()] == [sorted(left_out)]
    for code in left_out:
        row = _row(result, code)
        assert (row["status"], row["rationale"]) == ("gap", "Second answer.")
    assert (result["omitted_count"], result["omitted_techniques"]) == (0, [])
    assert (result["reasked_count"], result["reask_batches_total"]) == (2, 1)
    assert result["reask_batches_failed"] == 0
    audit = w.audit()
    assert (audit["reasked_count"], audit["omitted_count"]) == (2, 0)


def test_a_technique_left_out_twice_is_reported_still_missing(app_client) -> None:  # noqa: F811
    """Ask 3: the count still missing after the second pass."""
    w = _world(app_client, 2)
    recovered, missing = w.code(0), w.code(1)
    w.respond(omit_first=frozenset({recovered}), omit_always=frozenset({missing}))
    result = w.run()

    assert [sorted(b) for b in w.reasks()] == [sorted([recovered, missing])]
    assert _row(result, recovered)["status"] == "gap"
    assert _row(result, missing)["status"] is None
    assert result["omitted_techniques"] == [{"technique_code": missing, "kept_status": None}]
    assert (result["omitted_count"], result["reasked_count"]) == (1, 2)
    audit = w.audit()
    assert (audit["omitted_count"], audit["reasked_count"]) == (1, 2)


def test_a_locked_technique_left_out_is_not_asked_again(app_client) -> None:  # noqa: F811
    w = _world(app_client, 2)
    locked, open_ = w.code(0), w.code(1)
    r = w.c.patch(f"/attack/coverage/{w.rows[0]['id']}", headers=w.h, json={"locked": True})
    assert r.status_code == 200, r.text
    w.respond(omit_first=frozenset({locked, open_}))
    result = w.run()
    assert w.reasks() == [[open_]]
    assert result["reasked_count"] == 1


def test_a_failed_batch_is_not_asked_again(app_client) -> None:  # noqa: F811
    """A failed batch's techniques stay `batches_failed`'s and its alert's
    ("Re-run before relying on this draft"); the re-ask covers only what a
    SUCCESSFUL batch left out."""
    # 26 distinct asked codes cannot share one 25-code batch, so the first and
    # last of these, in sorted order, sit in different batches.
    w = _world(app_client, 26)
    codes = sorted(r["technique_code"] for r in w.rows)
    in_failed, left_out = codes[0], codes[-1]
    w.respond(fail_first_with=in_failed, omit_first=frozenset({left_out}))
    result = w.run()
    (failed_batch,) = [b for b in w.sent if in_failed in b]
    assert left_out not in failed_batch, "setup: the two codes share a batch"
    assert w.reasks() == [[left_out]]
    assert result["batches_failed"] == 1
    assert result["reasked_count"] == 1
    assert _row(result, left_out)["status"] == "gap"


def test_a_failed_reask_keeps_the_first_pass_and_reports_the_techniques_missing(
    app_client,  # noqa: F811
) -> None:
    """A re-ask that fails must not throw away the first pass: the run still
    completes, what the first pass answered lands, and the techniques the
    re-ask was for stay on the omitted list. The failure is counted on its own
    fields, not folded into `batches_failed` (whose alert says the techniques
    are covered by nothing below, and these are: by the omitted list)."""
    w = _world(app_client, 2)
    answered, left_out = w.code(0), w.code(1)
    w.respond(omit_first=frozenset({left_out}), fail_reask=True)
    result = w.run()
    assert w.reasks() == [[left_out]]
    assert _row(result, answered)["status"] == "gap"
    assert result["omitted_techniques"] == [{"technique_code": left_out, "kept_status": None}]
    assert (result["reask_batches_total"], result["reask_batches_failed"]) == (1, 1)
    assert result["batches_failed"] == 0
    assert w.audit()["reask_batches_failed"] == 1


def test_a_reask_answer_for_a_technique_it_was_not_asked_about_is_dropped(
    app_client,  # noqa: F811
) -> None:
    """The re-ask must not overwrite a first-pass answer. A stray entry is
    dropped and counted on the audit row."""
    w = _world(app_client, 2)
    first, left_out = w.code(0), w.code(1)
    w.respond(omit_first=frozenset({left_out}), reask_stray=first)
    result = w.run()
    assert w.reasks() == [[left_out]]
    assert _row(result, first)["rationale"] == "First answer."
    assert _row(result, left_out)["rationale"] == "Second answer."
    assert w.audit()["reask_strays_dropped"] == 1


def test_a_reask_refused_by_redaction_fails_the_whole_run(app_client) -> None:  # noqa: F811
    """Ruling (a) on #736: a redaction refusal fails a run whole. A re-ask is
    part of the run, so its refusal is not a failed re-ask that lets the first
    pass land: nothing is applied."""
    w = _world(app_client, 2)
    answered, left_out = w.code(0), w.code(1)
    w.respond(omit_first=frozenset({left_out}), refuse_reask=True)
    run = run_ai_expecting_failure(w.c, f"/attack/services/{w.svc_id}/run-ai", w.h)
    assert w.reasks() == [[left_out]]
    assert run["error_reason"] == "redaction_unavailable"
    coverage = w.c.get(f"/attack/services/{w.svc_id}/assessments/latest", headers=w.h)
    assert coverage.status_code == 200, coverage.text
    (row,) = [t for t in coverage.json()["coverage"] if t["technique_code"] == answered]
    assert row["status"] is None, "the first pass must not land when the re-ask is refused"


def test_no_reask_starts_past_the_deadline(app_client, monkeypatch) -> None:  # noqa: F811
    """The re-ask runs only while the run is inside its deadline. Past it, the
    techniques stay on the omitted list and the audit row says why nothing was
    asked again."""
    w = _world(app_client, 2)
    answered, left_out = w.code(0), w.code(1)
    w.respond(omit_first=frozenset({left_out}))
    monkeypatch.setattr(RunContext, "past_deadline", lambda self: True)
    result = w.run()
    assert w.reasks() == []
    assert _row(result, answered)["status"] == "gap"
    assert result["omitted_techniques"] == [{"technique_code": left_out, "kept_status": None}]
    assert (result["reasked_count"], result["reask_batches_total"]) == (0, 0)
    audit = w.audit()
    assert audit["reask_skipped_past_deadline"] is True
    assert audit["omitted_count"] == 1


def test_a_large_reask_is_batched_and_asks_each_technique_once(app_client) -> None:  # noqa: F811
    """The re-ask uses the same batching as the first pass: more left-out
    techniques than one batch holds are split, and none is asked twice."""
    w = _world(app_client, 40)
    left_out = frozenset(r["technique_code"] for r in w.rows)
    w.respond(omit_first=left_out)
    result = w.run()
    reasks = w.reasks()
    assert len(reasks) > 1, "setup: 40 left out must need more than one re-ask batch"
    asked_again = [c for b in reasks for c in b]
    assert sorted(asked_again) == sorted(left_out)
    assert result["reask_batches_total"] == len(reasks)
    assert (result["reasked_count"], result["omitted_count"]) == (len(left_out), 0)


def test_the_first_pass_asks_each_technique_exactly_once(app_client) -> None:  # noqa: F811
    """The duplicate check `test_run_ai_never_sends_a_computed_parent_to_the_model`
    gave up for the re-ask (the advisor's condition, #736 6206422365). The
    provider answers nothing, so every technique is asked twice; the first
    `batches_total` calls are the first pass, because the re-ask starts only
    after every first-pass batch has answered."""
    from app.attack.catalog import TECHNIQUES

    w = _world(app_client, 1)
    w.respond(omit_always=frozenset(t.id for t in TECHNIQUES))
    result = w.run()
    first_pass = w.sent[: result["batches_total"]]
    asked_first = Counter(c for b in first_pass for c in b)
    assert asked_first, "no first-pass batch reached the provider"
    assert {c for c, n in asked_first.items() if n > 1} == set()
    # Derived from the catalog's parent links, as the computed-parent test is.
    has_children = {t.parent_id for t in TECHNIQUES if t.parent_id is not None}
    assert sorted(asked_first) == sorted(t.id for t in TECHNIQUES if t.id not in has_children)
    # And the re-ask, every call after those, asks each of them once more.
    asked_again = Counter(c for b in w.sent[result["batches_total"] :] for c in b)
    assert asked_again == asked_first
    assert result["reask_batches_total"] == len(w.sent) - result["batches_total"]


def test_a_technique_locked_while_the_first_pass_ran_is_not_asked_again(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    """The lock is read again after the first pass: a row a consultant locked
    while it ran is left alone, so it is not paid for a second time.

    The lock lands as the first pass returns, from its own session: written
    from inside a batch, it races the batches' own SQLite writes."""
    import uuid

    from app.models.attack_assessment import AttackCoverage
    from app.routes import attack as attack_routes

    w = _world(app_client, 2)
    locked, open_ = w.code(0), w.code(1)
    real = attack_routes._mitre_map_batches
    passes: list[int] = []

    def _first_pass_then_lock(*args, **kwargs):
        out = real(*args, **kwargs)
        if not passes:
            with w.sessions() as db:
                db.get(AttackCoverage, uuid.UUID(w.rows[0]["id"])).locked = True
                db.commit()
        passes.append(1)
        return out

    monkeypatch.setattr(attack_routes, "_mitre_map_batches", _first_pass_then_lock)
    w.respond(omit_first=frozenset({locked, open_}))
    result = w.run()
    assert len(passes) == 2, "setup: expected a first pass and one re-ask"
    assert w.reasks() == [[open_]]
    assert result["reasked_count"] == 1
    assert _row(result, locked)["locked"] is True


def test_a_reask_answer_the_run_refuses_leaves_the_technique_on_the_omitted_list(
    app_client,  # noqa: F811
) -> None:
    """A refused re-ask answer applies nothing, so the technique still got no
    status from this run and stays listed with the status it kept, where the
    consultant is told to check it. Before the re-ask existed it was listed;
    the re-ask must not move it to the audit row only (#859)."""
    w = _world(app_client, 2)
    kept, unscored = w.code(0), w.code(1)
    w.patch_status(0, "covered")
    w.respond(omit_first=frozenset({kept, unscored}), reask_status="no_such_status")
    result = w.run()
    assert [sorted(b) for b in w.reasks()] == [sorted([kept, unscored])]
    assert _row(result, kept)["status"] == "covered"
    assert result["omitted_techniques"] == sorted(
        [
            {"technique_code": kept, "kept_status": "covered"},
            {"technique_code": unscored, "kept_status": None},
        ],
        key=lambda t: t["technique_code"],
    )
    assert (result["omitted_count"], result["reasked_count"]) == (2, 2)
    audit = w.audit()
    assert {e["technique_code"] for e in audit["statuses_rejected"]} == {kept, unscored}
    assert audit["omitted_count"] == 2
