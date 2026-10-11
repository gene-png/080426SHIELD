"""Run places, the FIFO slot wait, whole-run refusal and release (for #552).

The design approved in R8 (#736 6096174390): two child slots, and N run PLACES.
A run takes ONE place at its first redaction, keyed by `ai_run_id_var`, and
keeps it until the run ends; each of its calls waits FIFO for a slot. A call
outside any run is a one-call run. A run arriving with every place taken is
refused, typed, before egress. A slot-wait timeout mid-run fails the WHOLE run.
The place is released on every exit path.

Every outcome is decided by state -- the run's reason and message, what the
provider received, how many places are in use -- never by a clock. Where a
test needs a child to be slower than something else, the margin is stated at
the test.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select, update

from app.ai.llm import LLMResponse
from app.models._common import utcnow
from app.models.ai_run import AiRun
from tests import _isolation_targets as targets
from tests import _redaction_world as rw
from tests._ai_runs import defer_runs, get_run
from tests._redaction_world import _world  # noqa: F401 - the `world` fixture

#: Approved copy (#736 6094362713, approved in 6094620397), quoted, not built.
_BUSY_COPY = (
    "The check for people's names is busy with other AI work, so this was "
    "stopped and nothing was sent to the AI provider. Try again in a minute."
)

#: The PART-WAY sentences: a run that had already sent a payload when it was
#: refused cannot say "nothing was sent". Drafted for #552, held for a ruling.
_BUSY_PART_WAY = (
    "The check for people's names is busy with other AI work, so this run was "
    "stopped part-way. Nothing from it was applied."
)
_BUDGET_PART_WAY = (
    "Checking a payload in this run for people's names took longer than the "
    "0.5-second limit, so the run was stopped part-way. Nothing from it was applied."
)


def _settings(monkeypatch, **values: str) -> None:
    from app.config import get_settings

    for name, value in values.items():
        monkeypatch.setenv(f"SHIELD_REDACTION_{name}", value)
    get_settings.cache_clear()


def _hold_a_place(
    world: dict, isolation: Any, name: str
) -> tuple[threading.Thread, Any, dict[str, BaseException]]:
    """A one-call run whose child spins until its budget stops it, started in
    a thread. Returns once the child has written its PID, so the place and a
    slot are held by state, not by a sleep. The holder's own ending is kept for
    the test to assert: it must be the budget, nothing else."""
    pid_file = world["tmp"] / f"{name}.pid"
    ended: dict[str, BaseException] = {}

    def _hold() -> None:
        try:
            isolation.redact_payload_isolated(
                {"__pid_file__": str(pid_file)},
                mode="strict",
                client_org_name=None,
                name_hints=(),
            )
        except BaseException as exc:  # noqa: BLE001 - kept, and asserted by the test
            ended["e"] = exc

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    rw.wait_for_file(pid_file)
    return holder, pid_file, ended


# ---------------------------------------------------------------------------
# One place per run
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_batched_run_takes_one_place_however_many_calls_it_makes(world, monkeypatch) -> None:
    """With ONE place, a CSF Run-AI fanning out five calls at a time completes
    every batch. Counted per call, its own second call would find the place
    taken and be refused."""
    import app.ai.isolation as isolation

    _settings(monkeypatch, MAX_RUNS="1")
    svc_id = rw.csf_service(world)

    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.csf_run(world, svc_id))

    assert run["status"] == "completed", run
    assert run["batches_total"] >= 5, f"too few batches to fan out: {run['batches_total']}"
    assert run["batches_failed"] == 0, run
    assert len(world["sent"]) == run["batches_total"], (len(world["sent"]), run)
    assert isolation.places_in_use() == 0


# ---------------------------------------------------------------------------
# Refused at arrival: typed, before egress, not charged
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_run_arriving_with_every_place_taken_is_refused_and_not_charged(
    world, monkeypatch
) -> None:
    """A LIVE extraction arriving while the only place is held is refused with
    the busy sentence, sends nothing, writes no list and no `llm_calls` row,
    and records `charged_likely` False: "not charged", never "may have made a
    live AI call" beside "nothing was sent"."""
    import app.ai.isolation as isolation

    _settings(monkeypatch, MAX_RUNS="1", BUDGET_SECONDS="5")
    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    holder, pid_file, holder_ended = _hold_a_place(world, isolation, "holder")
    assert isolation.places_in_use() == 1

    rw.use_live_provider(world)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.extract(world, svc_id, artifact_id, serves="live")

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_capacity_busy", run
    assert run["error_message"] == _BUSY_COPY, run["error_message"]
    assert run["charged_likely"] is False, run
    assert world["sent"] == []
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0

    holder.join(rw.HANG_GUARD_S)
    assert not holder.is_alive()
    assert (
        getattr(holder_ended.get("e"), "reason", None) == "redaction_budget_exceeded"
    ), holder_ended
    rw.assert_gone(int(pid_file.read_text()))


# ---------------------------------------------------------------------------
# A slot-wait timeout mid-run fails the WHOLE run
# ---------------------------------------------------------------------------


def _score_first_asked_row(payload: dict) -> LLMResponse:
    """A csf_score answer for the first row the batch asked about, so a batch
    that got through WOULD apply something if the run were allowed to land."""
    entry = {
        "tier": payload["tiers"][0],
        "subcategory_code": payload["subcategories"][0],
        "governance": 1,
        "policy": 1,
        "implementation": 1,
        "monitoring": 1,
        "improvement": 1,
        "what_we_found": "Applied from the batch that got through.",
    }
    return LLMResponse(json.dumps({"scores": [entry]}), input_tokens=1, output_tokens=1)


@pytest.mark.unit
def test_a_slot_wait_timeout_mid_run_fails_the_whole_run(world, monkeypatch) -> None:
    """One slot. The run's first call is redacted and SENT; its second holds
    the slot; every other call waits past the slot-wait limit. The run fails
    whole with the busy reason and the part-way sentence, and the batch that
    did come back is not applied.

    THE MARGIN: the first call must finish before the 2 s slot wait expires;
    it is one ordinary redaction (about 39 ms measured on #736), so about 50x."""
    import app.ai.isolation as isolation

    _settings(monkeypatch, MAX_CHILDREN="1", SLOT_WAIT_SECONDS="2", BUDGET_SECONDS="6")
    ctl = rw.control_dir(world)
    monkeypatch.setattr(isolation, "_TARGET", targets.first_real_then_hold)
    sent: list[dict] = []

    def _answer(payload: dict) -> LLMResponse:
        sent.append(payload)
        return _score_first_asked_row(payload)

    world["provider"].register("csf_score", _answer)
    svc_id = rw.csf_service(world)

    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.csf_run(world, svc_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_capacity_busy", run
    assert run["error_message"] == _BUSY_PART_WAY, run["error_message"]
    assert len(sent) == 1, f"{len(sent)} batches reached the provider; only the first may"
    assert run["result"] is None, run
    assert rw.csf_scored_rows(world, svc_id) == 0, "a partial result was applied"
    assert isolation.places_in_use() == 0

    rw.wait_until_idle()
    rw.assert_gone(int((ctl / "holder.pid").read_text()))


# ---------------------------------------------------------------------------
# The place is released on every exit path
# ---------------------------------------------------------------------------


def _record_places(world: dict, answer: str) -> list[int]:
    """Answer extractions with `answer`, recording how many places were in use
    WHILE the provider was being called: 1 proves the run held its place."""
    from app.ai import isolation

    seen: list[int] = []

    def _answer(_payload: dict) -> LLMResponse:
        seen.append(isolation.places_in_use())
        return LLMResponse(answer, input_tokens=1, output_tokens=1)

    world["provider"].register("extract.capabilities", _answer)
    return seen


@pytest.mark.unit
def test_the_place_is_released_when_the_run_succeeds(world) -> None:
    import app.ai.isolation as isolation

    seen = _record_places(world, '{"items": []}')
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.extract(world, svc_id, artifact_id)

    assert run["status"] == "completed", run
    assert seen == [1], seen
    assert isolation.places_in_use() == 0


@pytest.mark.unit
def test_the_place_is_released_when_the_run_fails_typed(world) -> None:
    import app.ai.isolation as isolation

    seen = _record_places(world, "this is not JSON")
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.extract(world, svc_id, artifact_id)

    assert run["status"] == "failed", run
    # Typed upstream, by `ai_call_boundary`, before the route's own parse.
    assert run["error_reason"] == "ai_call_failed", run
    assert seen == [1], seen
    assert isolation.places_in_use() == 0


@pytest.mark.unit
def test_the_place_is_released_when_the_run_raises_unexpectedly(world, monkeypatch) -> None:
    import app.ai.isolation as isolation
    import app.routes.tech_debt as tech_debt

    def _explode(*_a: Any, **_k: Any) -> int:
        raise RuntimeError("an unexpected failure after the AI call")

    monkeypatch.setattr(tech_debt, "_max_list_version", _explode)
    seen = _record_places(world, '{"items": []}')
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.extract(world, svc_id, artifact_id)

    assert run["status"] == "failed", run
    assert run["error_reason"] == "run_crashed", run
    assert seen == [1], seen
    assert isolation.places_in_use() == 0


@pytest.mark.unit
def test_the_place_is_released_when_the_run_is_reaped(world, monkeypatch) -> None:
    """The job is stuck inside a redaction (its child spins). A status read
    past the run's lock reaps it, and the place comes back AT THE REAP, while
    the job is still stuck: otherwise one stuck run holds a place for as long
    as its child lives."""
    import app.ai.isolation as isolation

    _settings(monkeypatch, BUDGET_SECONDS="5")
    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    runner = defer_runs(world["app"])
    pid_file = world["tmp"] / "stuck.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run_id = rw.start_extract(world, svc_id, artifact_id)
    job = threading.Thread(target=runner.run_all, daemon=True)
    job.start()
    rw.wait_for_file(pid_file)
    assert isolation.places_in_use() == 1, "the run never took its place"

    with world["Session"]() as db:
        db.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(run_id))
            .values(deadline_at=utcnow() - timedelta(hours=1))
        )
        db.commit()
    run = get_run(world["c"], run_id, world["h"])

    assert (run["status"], run["error_reason"]) == ("failed", "run_deadline_exceeded"), run
    assert job.is_alive(), "the job ended before the reap, so this proves nothing about it"
    assert isolation.places_in_use() == 0, "the reap did not give the place back"

    job.join(rw.HANG_GUARD_S)
    assert not job.is_alive()
    assert isolation.places_in_use() == 0
    rw.assert_gone(int(pid_file.read_text()))


# ---------------------------------------------------------------------------
# Risk generate: one place for the whole fan-out, and whole-generate refusal
# ---------------------------------------------------------------------------


def _risk_client(world: dict, legal_name: str) -> str:
    """A client of its own, seeded with approved ATT&CK, CSF and ZT findings
    (six in all), the same seed the code-lists test uses."""
    from tests.unit.test_risk_code_lists_redaction import _seed

    r = world["c"].post("/admin/clients", headers=world["h"], json={"legal_name": legal_name})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    _seed(world["c"], world["bearer"], cid)
    return cid


def _risk_registers(world: dict, cid: str) -> int:
    from app.models.risk_register import RiskRegister

    with world["Session"]() as db:
        return db.execute(
            select(func.count())
            .select_from(RiskRegister)
            .where(RiskRegister.client_id == uuid.UUID(cid))
        ).scalar_one()


def _generate(world: dict, cid: str):
    return rw.post_within(
        rw.HANG_GUARD_S,
        lambda: world["c"].post(f"/risk/clients/{cid}/register/generate", headers=world["h"]),
    )


@pytest.mark.unit
def test_risk_generate_takes_one_place_for_its_whole_fan_out(world, monkeypatch) -> None:
    """Risk is not a Run-AI, so its calls carry no run id. With ONE place and a
    batch per finding, its five-way fan-out completes every batch: the generate
    is one redaction scope. Counted as one-call runs, its own concurrent
    batches would refuse each other."""
    import app.ai.isolation as isolation
    import app.routes.risk as risk

    _settings(monkeypatch, MAX_RUNS="1")
    monkeypatch.setattr(risk, "_RISK_BATCH_SIZE", 1)
    cid = _risk_client(world, "Risk Scope Client")

    r = _generate(world, cid)

    assert r.status_code == 201, r.text
    risk_sent = [p for p in world["sent"] if "findings" in p]
    assert len(risk_sent) >= 5, f"too few batches to fan out: {len(risk_sent)}"
    assert _risk_registers(world, cid) == 1
    assert isolation.places_in_use() == 0


@pytest.mark.unit
def test_a_refusal_inside_risk_generate_fails_the_whole_generate(world, monkeypatch) -> None:
    """One slot. Risk's first batch is redacted and SENT; its second runs over
    the budget. Generate answers the typed refusal with the part-way sentence
    and writes NO register: before this, the batches that got through became a
    register. (The client's legal name carries the control directory, because
    Risk passes the redactor no name hints.)"""
    import app.ai.isolation as isolation
    import app.routes.risk as risk

    _settings(monkeypatch, MAX_CHILDREN="1")
    monkeypatch.setattr(risk, "_RISK_BATCH_SIZE", 1)
    ctl = world["tmp"] / "ctl"
    ctl.mkdir()
    cid = _risk_client(world, f"__ctl__:{ctl}")
    monkeypatch.setattr(isolation, "_TARGET", targets.first_real_then_hold)

    r = _generate(world, cid)

    assert r.status_code == 503, r.text
    error = r.json()["error"]
    assert error["reason"] == "redaction_budget_exceeded", error
    assert error["message"] == _BUDGET_PART_WAY, error
    risk_sent = [p for p in world["sent"] if "findings" in p]
    assert len(risk_sent) == 1, f"{len(risk_sent)} batches reached the provider"
    assert _risk_registers(world, cid) == 0, "a register was written from a refused generate"
    assert isolation.places_in_use() == 0
    rw.assert_gone(int((ctl / "holder.pid").read_text()))


@pytest.mark.unit
def test_run_batches_outside_any_run_takes_one_place(world, monkeypatch) -> None:
    """`run_batches` called outside a Run-AI (the CLI measure script does) is
    one redaction scope: with ONE place, six batches at five workers all come
    back. As one-call runs, its concurrent batches refused each other (found by
    the measure-script suite on the first build)."""
    import app.ai.isolation as isolation
    from app.ai.batching import run_batches
    from app.ai.llm import LLMClient
    from app.models.user import User

    _settings(monkeypatch, MAX_RUNS="1")
    # Risk E (#1036): `findings` is keyed by source_id, so it is an object;
    # the keyed guard refuses a list before egress.
    batches = [{"findings": {}, "valid_techniques": [], "valid_controls": []} for _ in range(6)]
    with world["Session"]() as db:
        admin = db.execute(
            select(User).where(User.email == "admin@kentro-consulting.com")
        ).scalar_one()
        out = rw.post_within(
            rw.HANG_GUARD_S,
            lambda: run_batches(
                db,
                LLMClient(world["provider"]),
                "risk_synthesize",
                batches,
                requested_by=admin.id,
                service_id=None,
                client_id=world["tenant_id"],
                client_org_name=None,
                name_hints=(),
                deadline_at=utcnow() + timedelta(hours=1),
                max_workers=5,
                deadline_message="past the deadline",
            ),
        )

    assert (out.total, out.failed) == (6, 0), out
    assert len([p for p in world["sent"] if "findings" in p]) == 6
    assert isolation.places_in_use() == 0


# ---------------------------------------------------------------------------
# The slot wait is FIFO
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_slots_are_granted_in_arrival_order() -> None:
    """`threading.BoundedSemaphore` is not FIFO: measured on #736, later
    arrivals were served while earlier waiters timed out. Three waiters queue
    in a known order (each enqueued before the next starts, by the queue's own
    count) and are granted in that order as the one slot is released."""
    from app.ai.isolation import FifoSlots

    slots = FifoSlots(1)
    assert slots.wait(rw.HANG_GUARD_S), "the free slot was not granted at once"
    granted: list[str] = []
    lock = threading.Lock()

    def _waiter(name: str) -> None:
        assert slots.wait(rw.HANG_GUARD_S), f"{name} was never granted"
        with lock:
            granted.append(name)

    threads = []
    for i, name in enumerate(["first", "second", "third"]):
        t = threading.Thread(target=_waiter, args=(name,), daemon=True)
        t.start()
        threads.append(t)
        for _ in range(rw.HANG_GUARD_S * 20):
            if slots.waiting() == i + 1:
                break
            threading.Event().wait(0.05)
        assert slots.waiting() == i + 1, f"{name} never queued"

    for expected in range(1, 4):
        slots.release()
        for _ in range(rw.HANG_GUARD_S * 20):
            with lock:
                if len(granted) == expected:
                    break
            threading.Event().wait(0.05)
    for t in threads:
        t.join(rw.HANG_GUARD_S)
    assert granted == ["first", "second", "third"], granted
    slots.release()
    assert slots.in_use() == 0


@pytest.mark.unit
def test_a_call_from_a_run_that_has_ended_is_refused_and_takes_no_place(world) -> None:
    """A straggling call of a run that has already ended (a batch dequeued as
    the run failed, or a job still running after its reap) is refused and is
    NOT given a place: nobody would release a place taken after the end. No
    route reaches this deterministically, so it is driven at the module with
    the run id set the way the run framework sets it."""
    import app.ai.isolation as isolation
    from app.ai.run_context import ai_run_id_var

    run_id = uuid.uuid4()
    token = ai_run_id_var.set(run_id)
    try:
        isolation.release_run(run_id)
        with pytest.raises(isolation.RedactionRefused) as refused:
            isolation.redact_payload_isolated(
                {"x": "y"}, mode="strict", client_org_name=None, name_hints=()
            )
    finally:
        ai_run_id_var.reset(token)
    assert refused.value.reason == "redaction_capacity_busy", refused.value.detail
    assert isolation.places_in_use() == 0, "an ended run was given a place"


@pytest.mark.unit
def test_the_place_is_released_when_closing_out_the_run_raises(world, monkeypatch) -> None:
    """`_execute`'s `finally` closes the session and leaves the live set before
    it gives the place back. If either raises, the place must still come back:
    the reaper only covers RUNNING runs, so a leak here is for ever (#1042
    review, finding 4)."""
    import app.ai.isolation as isolation
    import app.ai.runs as runs

    real_mark_done = runs._mark_done

    def _mark_done_then_raise(run_id: uuid.UUID) -> None:
        real_mark_done(run_id)
        raise RuntimeError("closing out the run failed")

    monkeypatch.setattr(runs, "_mark_done", _mark_done_then_raise)
    seen = _record_places(world, '{"items": []}')
    runner = defer_runs(world["app"])
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    rw.start_extract(world, svc_id, artifact_id)

    with pytest.raises(RuntimeError, match="closing out the run failed"):
        runner.run_all()

    assert seen == [1], "the run never held a place, so this proves nothing"
    assert isolation.places_in_use() == 0
