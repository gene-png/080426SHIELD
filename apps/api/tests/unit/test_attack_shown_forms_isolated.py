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
