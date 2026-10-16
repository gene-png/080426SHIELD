"""#1080 and #1124 (the D-111 residual): the ATT&CK tool-name redactions that
build a `CitationResolver` or a what-if's removal spellings run in the
redaction child when the build carries name hints, once per build, and a
refused child refuses the request typed. Without hints they stay in-process
(option (b), advisor, #736 6221187740), so the client dashboard never waits on
Run-AI's redaction capacity.

Expected shown forms are the scenario's literals ("[NAME] Scanner",
"[CLIENT] SOC Platform"); the parity test calls `redact_for_ai`, the egress's
own per-string redactor, because "the same forms as the egress" is the claim.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.ai import isolation
from app.ai.redact import redact_for_ai
from app.attack import shown_forms as shown_module
from app.attack.citations import Candidate, CitationResolver
from app.models.attack_scenario import AttackScenario
from tests.unit.test_ai_runs_attack import app_parts  # noqa: F401  (fixture)
from tests.unit.test_attack_name_hints import DANA, DANA_TOOL, DANA_TOOL_SHOWN, _tenant_user
from tests.unit.test_attack_scenario_routes import _error, _world

pytestmark = pytest.mark.unit

HINTS = (DANA,)


@pytest.fixture
def child_calls(monkeypatch) -> list[list[str]]:
    """Every payload the module sends to the redaction child, while still
    sending it (the real call), and a refusal of any in-process redaction made
    WITH hints: that is exactly the GIL-holding work #1080 moves."""
    calls: list[list[str]] = []
    real = isolation.redact_payload_isolated

    def spy(payload, **kwargs):
        calls.append(list(payload))
        return real(payload, **kwargs)

    def no_in_process_with_hints(text, **kwargs):
        assert not kwargs.get("name_hints"), f"in-process redaction with hints: {text!r}"
        return redact_for_ai(text, **kwargs)

    monkeypatch.setattr(shown_module, "redact_payload_isolated", spy)
    monkeypatch.setattr(shown_module, "redact_for_ai", no_in_process_with_hints)
    return calls


def test_shown_forms_through_the_child_equal_the_egress_redactor() -> None:
    names = ["Acme SOC Platform", DANA_TOOL, "Unit 42", "Plain Tool", "Acme SOC Platform"]
    got = shown_module.shown_forms(names, mode="strict", client_org_name="Acme", name_hints=HINTS)
    # Positive first: the two forms the scenario names.
    assert got["Acme SOC Platform"] == "[CLIENT] SOC Platform"
    assert got[DANA_TOOL] == DANA_TOOL_SHOWN
    assert got["Plain Tool"] == "Plain Tool"
    for name in names:
        expected, _counts = redact_for_ai(
            name, mode="strict", client_org_name="Acme", name_hints=HINTS
        )
        assert got[name] == expected, name


def test_a_resolver_with_hints_asks_the_child_once_for_every_name_and_vendor(
    child_calls,
) -> None:
    resolver = CitationResolver(
        [
            Candidate(name=DANA_TOOL, vendor="Acme"),
            Candidate(name="Plain Tool", vendor="Vendor Co"),
            Candidate(name="Other Tool"),
        ],
        client_org_name="Acme",
        redaction_mode="strict",
        name_hints=HINTS,
    )
    assert child_calls == [[DANA_TOOL, "Plain Tool", "Other Tool", "Acme", "Vendor Co"]]
    # The alias still resolves: the form the model is shown confirms the tool.
    assert resolver.named_by(DANA_TOOL_SHOWN) == frozenset({DANA_TOOL})


def test_a_resolver_without_hints_never_asks_the_child(monkeypatch) -> None:
    """Option (b): the subset check's builds carry no hints and stay here."""

    def refuse(*_a, **_k):
        raise AssertionError("a no-hint build asked the redaction child")

    monkeypatch.setattr(shown_module, "redact_payload_isolated", refuse)
    resolver = CitationResolver(
        [Candidate(name="Acme SOC Platform")], client_org_name="Acme", redaction_mode="strict"
    )
    assert resolver.named_by("[CLIENT] SOC Platform") == frozenset({"Acme SOC Platform"})


def _create(w, added):
    return w.c.post(f"/attack/services/{w.svc_id}/scenarios", headers=w.h, json={"added": added})


def _scenarios(w) -> int:
    with w.sessions() as db:
        return db.execute(select(func.count()).select_from(AttackScenario)).scalar_one()


def test_creating_a_what_if_redacts_its_names_in_the_child_in_two_calls(
    app_parts,  # noqa: F811
    child_calls,
) -> None:
    """Through the route: the added tool is checked against the client's tools
    by the form the model is SHOWN, and the removal spellings are decided,
    each in ONE child call -- never one call per name, and never in-process."""
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    r = _create(w, [{"name": DANA_TOOL, "security_functions": ["detect"]}])
    assert r.status_code == 201, r.text
    assert len(child_calls) == 2, child_calls
    added_check, removals = child_calls
    assert DANA_TOOL in added_check and len(added_check) > 1, added_check
    assert len(removals) > 1, removals


def test_a_refused_redaction_refuses_the_what_if_typed_and_stores_nothing(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    before = _scenarios(w)

    def busy(*_a, **_k):
        raise isolation.RedactionRefused(
            isolation.REDACTION_CAPACITY_BUSY,
            isolation.busy_message(sent_before=False),
            status_code=503,
            sent_before=False,
        )

    monkeypatch.setattr(isolation, "_admit", busy)
    r = _create(w, [{"name": DANA_TOOL, "security_functions": ["detect"]}])
    assert r.status_code == 503, r.text
    assert _error(r)["reason"] == "redaction_capacity_busy"
    assert _scenarios(w) == before


def test_the_client_dashboard_subset_check_never_asks_the_child(
    app_parts,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    """Through the client dashboard: its #851 subset check builds a resolver
    with no hints, even for a tenant whose users ARE the dictionary, so a busy
    redaction child can never turn this page into a 503 (option (b))."""
    from tests.unit.test_attack_subset_after_release import (
        _approve_finalize,
        _cover,
        _dashboard,
        _release,
    )
    from tests.unit.test_attack_subset_drift import EDR, LEGACY, _codes, _with_storage
    from tests.unit.test_attack_subset_drift import _world as _drift_world

    _with_storage(app_parts, tmp_path)
    w = _drift_world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    _cover(w, _codes(w)[0], [EDR, LEGACY])
    _release(w, _approve_finalize(w))
    w.confirm_not_security(LEGACY)

    def refuse(*_a, **_k):
        raise AssertionError("the client dashboard asked the redaction child")

    monkeypatch.setattr(shown_module, "redact_payload_isolated", refuse)
    body = _dashboard(w)
    # Positive: the subset check ran (and found LEGACY outside the list).
    assert body["tool_outside_subset"] == [LEGACY], body.get("tool_outside_subset")


# --- review of 8c3c85e0: nothing asks the child after a paid call ------------------


def _busy() -> isolation.RedactionRefused:
    return isolation.RedactionRefused(
        isolation.REDACTION_CAPACITY_BUSY,
        isolation.busy_message(sent_before=False),
        status_code=503,
        sent_before=False,
    )


def test_a_refused_check_after_the_paid_chat_call_is_n2_not_nothing_was_sent(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """F1: the chat call is made, and then the check of the AI's proposed
    added names is refused. The answer is the N2 fallback with the attempt
    audited, never a 503 saying nothing was sent: the call WAS sent."""
    import json

    from app.ai.llm import LLMResponse
    from app.attack import scenario_intent
    from app.models.audit_entry import AuditEntry
    from tests.unit.test_ai_runs_attack import LiveLookingProvider
    from tests.unit.test_attack_scenario_intent_routes import N2, VAGUE

    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    seen: list[dict] = []
    provider = LiveLookingProvider()

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"remove": [], "add": ["XDR Suite"], "unclear": []}))

    provider.register(scenario_intent.PURPOSE, respond)
    w.use(provider)
    real = isolation.redact_payload_isolated

    def refuse_after_the_call(payload, **kwargs):
        if seen:
            raise _busy()
        return real(payload, **kwargs)

    monkeypatch.setattr(shown_module, "redact_payload_isolated", refuse_after_the_call)
    r = w.c.post(
        f"/attack/services/{w.svc_id}/scenarios/parse",
        headers=w.h,
        json={"text": VAGUE, "serves": "live"},
    )
    assert r.status_code == 200, r.text
    assert len(seen) == 1, "setup: the paid call was made"
    assert (r.json()["source"], r.json()["note"]) == ("matcher", N2)
    with w.sessions() as db:
        entry = db.execute(
            select(AuditEntry).where(AuditEntry.action == "attack.scenario.chat_ai_parse")
        ).scalar_one()
    assert entry.details["failure"] == "redaction_capacity_busy", entry.details
    assert entry.details["fell_back"] is True


def test_a_refused_check_before_the_chat_call_is_a_typed_503_with_nothing_sent(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """F1's other half: the names known before the call are checked BEFORE
    it, so a refusal there is true when it says nothing was sent."""
    import json

    from app.ai.llm import LLMResponse
    from app.attack import scenario_intent
    from tests.unit.test_ai_runs_attack import LiveLookingProvider
    from tests.unit.test_attack_scenario_intent_routes import VAGUE

    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    seen: list[dict] = []
    provider = LiveLookingProvider()

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"remove": [], "add": [], "unclear": []}))

    provider.register(scenario_intent.PURPOSE, respond)
    w.use(provider)

    def refuse(*_a, **_k):
        raise _busy()

    monkeypatch.setattr(shown_module, "redact_payload_isolated", refuse)
    r = w.c.post(
        f"/attack/services/{w.svc_id}/scenarios/parse",
        headers=w.h,
        json={"text": VAGUE, "serves": "live"},
    )
    assert r.status_code == 503, r.text
    assert _error(r) == {
        "reason": "redaction_capacity_busy",
        "message": (
            "The check for people's names is busy with other AI work, so this was "
            "stopped and nothing was sent to the AI provider. Try again in a minute."
        ),
    }
    assert seen == []


def test_the_what_if_run_asks_the_child_nothing_after_its_answers_arrive(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """F3: the shown forms the answers are read against are asked before
    `run_batches`; reading the paid-for answers asks the child nothing, so a
    refusal after them cannot fail a run whose answers were bought."""
    import json

    from app.ai.llm import FixtureProvider, LLMResponse
    from tests.unit.test_attack_scenario_routes import (
        EDR,
        PURPOSE,
        SIEM,
        _flags,
        _run_to_completion,
    )

    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    answered: list[str] = []
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        answered.append("answer")
        sent = payload.get("technique_codes") or []
        return LLMResponse(json.dumps({"rows": [_flags(c, SIEM, d=True) for c in sent]}))

    provider.register(PURPOSE, respond)
    w.use(provider)
    real = isolation.redact_payload_isolated
    after: list[list[str]] = []

    def refuse_after_answers(payload, **kwargs):
        if answered:
            after.append(list(payload))
            raise _busy()
        return real(payload, **kwargs)

    monkeypatch.setattr(shown_module, "redact_payload_isolated", refuse_after_answers)
    r = w.create([EDR])
    assert r.status_code == 201, r.text
    body = _run_to_completion(w, r.json()["id"])
    assert answered, "setup: the batches were answered"
    assert after == [], after
    assert body["run_status"] == "completed", body["run_error"]


# --- review of 8c3c85e0, F2: an index build is not a payload sent -------------------

#: The budget refusal as it reads when NOTHING of the run was sent
#: (`isolation.budget_message`, sent_before False), written out.
_NOTHING_SENT_TAIL = "so the check was stopped and nothing was sent to the AI provider."


def test_a_call_that_does_not_say_egress_still_counts_as_cleared() -> None:
    """The default is unchanged for every existing caller: a payload redacted
    for sending counts as cleared; one marked `egress=False` does not."""
    from app.ai.run_context import ai_run_id_var

    run_id = uuid.uuid4()
    token = ai_run_id_var.set(run_id)
    try:
        isolation.redact_payload_isolated(
            ["Plain Tool"], mode="strict", client_org_name=None, name_hints=HINTS, egress=False
        )
        assert isolation._places[("run", run_id)].cleared == 0
        isolation.redact_payload_isolated(
            {"text": "Plain text"}, mode="strict", client_org_name=None, name_hints=HINTS
        )
        assert isolation._places[("run", run_id)].cleared == 1
    finally:
        ai_run_id_var.reset(token)
        isolation.release_run(run_id)


def _egress_over_budget(monkeypatch) -> None:
    """Every payload the egress sends (a dict) runs over the budget; the
    index builds (`shown_forms`, a list) are redacted for real. The place's
    own bookkeeping then decides what the refusal says."""
    real = isolation._run_child

    def run_child(target_ref, payload, *args):
        if isinstance(payload, dict):
            return "timeout", None
        return real(target_ref, payload, *args)

    monkeypatch.setattr(isolation, "_run_child", run_child)


def test_a_mitre_map_run_refused_at_its_first_batch_says_nothing_was_sent(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """The run's resolver is built with the tenant's hints, in the child,
    BEFORE any batch. The first batch is then refused: the run must say that
    nothing was sent, not "stopped part-way"."""
    from app.ai.llm import LLMResponse
    from tests._ai_runs import defer_runs, get_run, start_run
    from tests.unit.test_ai_runs_attack import _world as _mitre_world

    w = _mitre_world(app_parts)
    runner = defer_runs(w.app)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    built: list[list[str]] = []
    real = isolation.redact_payload_isolated

    def spy(payload, **kwargs):
        built.append(list(payload))
        return real(payload, **kwargs)

    monkeypatch.setattr(shown_module, "redact_payload_isolated", spy)
    w.provider.register("mitre_map", lambda _p: LLMResponse('{"techniques": []}'))
    _egress_over_budget(monkeypatch)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert built, "setup: the resolver was built in the child before the batches"
    assert (run["status"], run["error_reason"]) == ("failed", "redaction_budget_exceeded"), run
    assert run["error_message"].endswith(_NOTHING_SENT_TAIL), run["error_message"]
    assert run["charged_likely"] is False, run


def test_a_what_if_run_refused_at_its_first_batch_says_nothing_was_sent(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """The what-if job checks its added tools and decides its removal
    spellings in the child BEFORE any batch; the first batch is refused, and
    the run says nothing was sent."""
    from tests.unit.test_attack_scenario_routes import EDR, _run_to_completion

    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    r = w.create([EDR])
    assert r.status_code == 201, r.text
    _egress_over_budget(monkeypatch)
    body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "failed", body
    assert body["run_error"]["reason"] == "redaction_budget_exceeded", body["run_error"]
    assert body["run_error"]["message"].endswith(_NOTHING_SENT_TAIL), body["run_error"]


# --- re-review of 08399fa8: A1 and A3 -------------------------------------------------


def test_asking_ahead_with_resolver_names_leaves_the_resolver_nothing_to_ask(
    child_calls,
) -> None:
    """A1: the what-if job asks ahead with `resolver_names`, the resolver's
    own rule, so a resolver given that map asks the child nothing more --
    a blank name included. A RATCHET: no blank name reaches the job today
    (`_client_capability_membership` drops blank names, `validate_added`
    refuses a blank added name), but a filter copied by hand let one through
    (review of 08399fa8)."""
    from app.attack.citations import resolver_names

    candidates = [
        Candidate(name="   ", vendor="Acme"),
        Candidate(name=DANA_TOOL, vendor="   "),
        Candidate(name="Plain Tool", vendor="Vendor Co"),
    ]
    ahead = shown_module.shown_forms(
        resolver_names(candidates), mode="strict", client_org_name="Acme", name_hints=HINTS
    )
    asked_ahead = len(child_calls)
    resolver = CitationResolver(
        candidates,
        client_org_name="Acme",
        redaction_mode="strict",
        name_hints=HINTS,
        shown=ahead,
    )
    assert asked_ahead == 1, child_calls
    assert len(child_calls) == 1, child_calls
    assert resolver.named_by(DANA_TOOL_SHOWN) == frozenset({DANA_TOOL})


def test_a_mitre_map_run_whose_index_build_is_refused_sends_nothing(
    app_parts,  # noqa: F811
    monkeypatch,
) -> None:
    """A3: the refusal comes at the index build itself, inside the run and
    before any batch. The run says nothing was sent, reads not charged, and
    the provider is never called."""
    from tests._ai_runs import defer_runs, get_run, start_run
    from tests.unit.test_ai_runs_attack import _world as _mitre_world

    w = _mitre_world(app_parts)
    runner = defer_runs(w.app)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    called: list[dict] = []

    def respond(payload: dict):
        from app.ai.llm import LLMResponse

        called.append(payload)
        return LLMResponse('{"techniques": []}')

    w.provider.register("mitre_map", respond)
    real = isolation._run_child

    def run_child(target_ref, payload, *args):
        if isinstance(payload, list):
            return "timeout", None
        return real(target_ref, payload, *args)

    monkeypatch.setattr(isolation, "_run_child", run_child)
    started = start_run(w.c, w.run_url, w.h)
    assert runner.run_all() == 1
    run = get_run(w.c, started["run_id"], w.h)
    assert (run["status"], run["error_reason"]) == ("failed", "redaction_budget_exceeded"), run
    assert run["error_message"].endswith(_NOTHING_SENT_TAIL), run["error_message"]
    assert run["charged_likely"] is False, run
    assert called == []
