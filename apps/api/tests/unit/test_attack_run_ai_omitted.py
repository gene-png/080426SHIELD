"""#853: an ATT&CK technique a Run-AI batch leaves out is counted and named.

`_attack_run_work` sends `technique_codes` in batches and applies only the
entries that come back. Before #853 a technique no entry named kept whatever it
held -- NULL on a first run, a stale status on a re-run -- and the run recorded
nothing. The run now reports `omitted_techniques = asked - answered - locked`
over the SUCCESSFUL batches, with the status each one kept, and the audit row
carries counts only. Twins: CSF #836, ZT #840.

Every test drives `POST /attack/services/{id}/run-ai`. The provider answers in
the prompt's own keys (`technique_code`, `status`, `detection_tools`, ... from
the mitre_map prompt's example JSON) for the codes the PAYLOAD asked about,
minus the ones a test leaves out. Expected values come from which codes the
test left out, what its setup wrote, and what the payloads asked -- never from
a constant of the module under test. Fixture mode cannot reach any of this:
the built-in mitre_map fixture answers every code it is sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.ai.llm import FixtureProvider, LLMResponse
from tests._ai_runs import attack_run_ai
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _admin,
    _seed_tech_debt_tools,
    app_client,
)

pytestmark = pytest.mark.unit


def _entry(code: str, status: str = "gap") -> dict:
    """One answer in the prompt's keys, citing nothing."""
    return {
        "technique_code": code,
        "status": status,
        "detection_tools": [],
        "prevention_tools": [],
        "response_tools": [],
        "rationale": "No capability addresses this technique.",
    }


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str
    rows: list[dict]
    # Each batch's `technique_codes`, as the provider received them.
    sent: list[list[str]] = field(default_factory=list)

    def code(self, i: int) -> str:
        return self.rows[i]["technique_code"]

    def patch(self, i: int, **fields: object) -> None:
        r = self.c.patch(f"/attack/coverage/{self.rows[i]['id']}", headers=self.h, json=fields)
        assert r.status_code == 200, r.text

    def respond(
        self,
        omit: set[str] = frozenset(),
        *,
        status_for: dict[str, str] | None = None,
        fail_batch_with: str | None = None,
        empty_batch_with: str | None = None,
        extra_in_batch_with: tuple[str, str] | None = None,
    ) -> None:
        """Answer every code a batch asks for except `omit`.

        `fail_batch_with`: the batch asking for that code raises (a failed
        batch). `empty_batch_with`: the batch asking for that code answers
        `{"techniques": []}`. `extra_in_batch_with=(host, stray)`: the batch
        asking for `host` also answers for `stray`, a code another batch asked.
        """
        status_for = status_for or {}

        def _answer(payload: dict) -> LLMResponse:
            import json

            asked = list(payload.get("technique_codes") or [])
            self.sent.append(asked)
            if fail_batch_with in asked:
                raise RuntimeError("provider closed the connection")
            if empty_batch_with in asked:
                return LLMResponse('{"techniques": []}')
            entries = [
                _entry(code, status_for.get(code, "gap")) for code in asked if code not in omit
            ]
            if extra_in_batch_with and extra_in_batch_with[0] in asked:
                entries.append(_entry(extra_in_batch_with[1]))
            return LLMResponse(json.dumps({"techniques": entries}))

        self.provider.register("mitre_map", _answer)

    def run(self) -> dict:
        return attack_run_ai(self.c, self.svc_id, self.h)

    def batch_of(self, code: str) -> list[str]:
        (batch,) = [b for b in self.sent if code in b]
        return batch

    def audit(self, runs: int = 1) -> dict:
        """The LAST `attack.run_ai` audit row, after asserting how many runs
        wrote one, so a discovery run's row is never read by mistake."""
        from app.models.audit_entry import AuditEntry

        with self.sessions() as db:
            rows = (
                db.execute(
                    select(AuditEntry.details)
                    .where(AuditEntry.action == "attack.run_ai")
                    .order_by(AuditEntry.at)
                )
                .scalars()
                .all()
            )
        assert len(rows) == runs, rows
        return rows[-1]


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


def _status_of(result: dict, code: str) -> str | None:
    (row,) = [t for t in result["coverage"] if t["technique_code"] == code]
    return row["status"]


def _spread(w: World) -> tuple[str, str]:
    """Two standalone codes the run puts in DIFFERENT batches, read from the
    payloads of a discovery run that answers none of `w.rows` (so none of them
    changes). Returns (code_a, code_b); the caller's run is then the second."""
    w.respond(omit={r["technique_code"] for r in w.rows})
    w.run()
    batches = list(w.sent)
    w.sent.clear()
    a = w.code(0)
    batch_a = next(b for b in batches if a in b)
    standalone = {r["technique_code"] for r in w.rows}
    b = next(
        code for batch in batches if batch is not batch_a for code in batch if code in standalone
    )
    return a, b


def test_a_run_that_answers_everything_omits_nothing(app_client) -> None:  # noqa: F811
    w = _world(app_client, 1)
    w.respond()
    result = w.run()
    assert (result["omitted_count"], result["omitted_techniques"]) == (0, [])
    audit = w.audit()
    assert (audit["omitted_count"], audit["omitted_kept_status"]) == (0, 0)


def test_omitted_techniques_are_counted_and_named_with_the_status_they_kept(
    app_client,  # noqa: F811
) -> None:
    """The issue's two cases: NULL on a first run (reads as unscored), and a
    stale status on a re-run, which reaches coverage as if confirmed."""
    w = _world(app_client, 2)
    fresh, stale = sorted([w.code(0), w.code(1)])
    w.patch([r["technique_code"] for r in w.rows].index(stale), status="gap")
    w.respond(omit={fresh, stale})
    result = w.run()

    assert result["omitted_count"] == 2
    assert result["omitted_techniques"] == [
        {"technique_code": fresh, "kept_status": None},
        {"technique_code": stale, "kept_status": "gap"},
    ]
    # The stale status really is what the row still holds.
    assert _status_of(result, stale) == "gap"
    assert _status_of(result, fresh) is None
    audit = w.audit()
    # Counts only on the audit row, never the codes.
    assert (audit["omitted_count"], audit["omitted_kept_status"]) == (2, 1)
    assert "omitted_techniques" not in audit


def test_a_locked_technique_left_out_is_not_omitted(app_client) -> None:  # noqa: F811
    """A locked row is left alone by design, answered or not."""
    w = _world(app_client, 2)
    locked, open_ = w.code(0), w.code(1)
    w.patch(0, locked=True)
    w.respond(omit={locked, open_})
    result = w.run()
    assert result["omitted_techniques"] == [{"technique_code": open_, "kept_status": None}]
    assert result["omitted_count"] == 1
    assert w.audit()["omitted_count"] == 1


def test_an_entry_that_named_the_technique_and_was_refused_is_an_answer(
    app_client,  # noqa: F811
) -> None:
    """A refused entry is an answer, not an omission. This one is an N/A
    refusal, which the panel counts as `not_applicable_refused` (#841); most
    other refusals reach only the audit row's `details` (#859). Either way it
    is not counted again as omitted."""
    w = _world(app_client, 2)
    refused, omitted = w.code(0), w.code(1)
    w.respond(omit={omitted}, status_for={refused: "not_applicable"})
    result = w.run()
    assert result["not_applicable_refused"] == 1
    assert result["omitted_techniques"] == [{"technique_code": omitted, "kept_status": None}]
    assert result["omitted_count"] == 1


def test_a_failed_batch_is_counted_as_failed_and_not_as_omitted(app_client) -> None:  # noqa: F811
    """No double count: the failed batch's techniques are `batches_failed`'s,
    and only what a SUCCESSFUL batch left out is omitted."""
    w = _world(app_client, 40)
    in_failed, left_out = _spread(w)
    w.respond(omit={left_out}, fail_batch_with=in_failed)
    result = w.run()
    assert result["batches_failed"] == 1
    failed_batch = w.batch_of(in_failed)
    assert left_out not in failed_batch
    assert result["omitted_techniques"] == [{"technique_code": left_out, "kept_status": None}]
    assert result["omitted_count"] == 1
    assert not {t["technique_code"] for t in result["omitted_techniques"]} & set(failed_batch)
    # The ATT&CK audit row carries no batch counts (the run's own row does);
    # what it must not do is fold the failed batch's techniques into this one.
    assert w.audit(runs=2)["omitted_count"] == 1


def test_a_batch_that_returned_nothing_omits_every_technique_it_asked(
    app_client,  # noqa: F811
) -> None:
    """`{"techniques": []}` is a successful batch with no answers: every code
    it was asked for is omitted, and the run is not counted failed."""
    w = _world(app_client, 1)
    w.respond(empty_batch_with=w.code(0))
    result = w.run()
    assert result["batches_failed"] == 0
    asked = w.batch_of(w.code(0))
    assert asked, "the empty batch must have been asked for something"
    assert result["omitted_techniques"] == [
        {"technique_code": code, "kept_status": None} for code in sorted(asked)
    ]
    assert result["omitted_count"] == len(asked)
    assert w.audit()["omitted_count"] == len(asked)


def test_a_technique_answered_by_another_batch_is_not_omitted(app_client) -> None:  # noqa: F811
    """ATT&CK APPLIES an entry naming a real technique another batch was asked
    for (CSF does not), so that technique got a result this run and saying it
    got none would be false."""
    w = _world(app_client, 40)
    host, stray = _spread(w)
    w.respond(omit={stray}, extra_in_batch_with=(host, stray))
    result = w.run()
    assert _status_of(result, stray) == "gap"
    assert (result["omitted_count"], result["omitted_techniques"]) == (0, [])
