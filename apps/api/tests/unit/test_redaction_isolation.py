"""Egress redaction runs in a child process with a budget (for #552).

Measured on 3933a85c (#552, 2026-10-10): one tenant's crafted display names held
the GIL for ~0.3 s per inventory cell, and another tenant's GET /auth/me took up
to 3.7 s. Moving the matcher into a child process removed it. These tests pin
the properties that fix depends on, each through the surface a consultant
reaches (the Tech Debt extract route) wherever a route can reach it:

* the redaction that feeds the provider is NOT computed in the api process;
* a redaction over its budget is stopped, typed, before anything is sent, and
  the child that was doing it no longer exists;
* a child that dies fails closed, typed;
* the redactor's own typed refusals cross the process boundary still typed;
* the child carries no provider key;
* the concurrency cap refuses, typed, rather than queueing without bound.

Budget, parity and the copy split are in `test_redaction_budget.py`; the
per-run places, whole-run refusal and every release path in
`test_redaction_places.py`.

NO WALL-CLOCK ASSERTION ANYWHERE. Every outcome here is decided by state: which
reason the run ended with, whether the provider was called, whether a PID
exists. The one timeout (`post_within`) is a hang guard with a 60 s limit over
work stopped at 0.5 s, so it fails only when the budget is gone.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import pytest
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.llm_call import LLMCall
from tests import _isolation_targets as targets
from tests import _redaction_world as rw
from tests._redaction_world import _world  # noqa: F401 - the `world` fixture

# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extract_redacts_in_a_child_process_not_the_api(world, monkeypatch) -> None:
    """The in-process redactor is made to explode. The extraction still
    completes and still sends `[NAME]`, so the redaction that fed the provider
    was computed somewhere else -- the child, which imports the module fresh
    and never sees this patch. Red if the call site goes back in-process.

    Patched under BOTH names: `catalog_fields` no longer imports it, so the
    second patch creates the name (`raising=False`), and a revert that imports
    it again at the call site gets the exploding one rather than the original
    it bound at import."""
    import app.ai.catalog_fields as catalog_fields
    import app.ai.redact as redact

    def _in_process(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("redaction ran in the api process (#552)")

    monkeypatch.setattr(redact, "redact_payload", _in_process)
    monkeypatch.setattr(catalog_fields, "redact_payload", _in_process, raising=False)

    rw.add_tenant_user(world, "dana.whitfield@example.com", "Dana Whitfield")
    svc_id, artifact_id = rw.service_and_artifact(
        world, "Application,Owner\nPayroll VPN,Dana Whitfield\n"
    )
    run = rw.extract(world, svc_id, artifact_id)

    assert run["status"] == "completed", run
    assert len(world["sent"]) == 1, f"provider called {len(world['sent'])} times"
    sent = json.dumps(world["sent"][0])
    assert "[NAME]" in sent, sent
    assert "Dana Whitfield" not in sent, sent
    with world["Session"]() as db:
        row = db.execute(select(LLMCall)).scalar_one()
    assert (row.redacted_counts or {}).get("name", 0) >= 1, row.redacted_counts


# ---------------------------------------------------------------------------
# The child is stopped, and is gone
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_over_budget_is_killed_and_its_pid_is_gone(world, monkeypatch) -> None:
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)
    pid_file = world["tmp"] / "child.pid"
    svc_id, artifact_id = rw.service_and_artifact(
        world, f"Application,__pid_file__\nPayroll,{pid_file}\n"
    )
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_budget_exceeded", run
    assert pid_file.is_file(), "the stand-in child never ran, so this proves nothing"
    rw.assert_gone(int(pid_file.read_text()))
    assert world["sent"] == [], "the provider was called after the budget ran out"
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0


# ---------------------------------------------------------------------------
# Crash and exception transport
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_crash_fails_closed_typed(world, monkeypatch) -> None:
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.crash)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_failed", run
    assert "nothing was sent" in (run["error_message"] or ""), run
    assert run["charged_likely"] is False, run
    assert world["sent"] == []
    assert rw.llm_rows(world) == 0
    assert rw.lists_for(world, svc_id) == 0


@pytest.mark.unit
def test_redactor_typed_refusal_crosses_the_process_boundary_typed(world, monkeypatch) -> None:
    """`BlankRedactionLiteralError` raised IN THE CHILD reaches the run with its
    own reason. A transport that flattened it to `redaction_failed` or
    `run_crashed` would lose the sentence that says what was wrong."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_TARGET", targets.raise_blank_literal)
    svc_id, artifact_id = rw.service_and_artifact(world, "Application\nPayroll\n")
    run = rw.post_within(rw.HANG_GUARD_S, lambda: rw.extract(world, svc_id, artifact_id))

    assert run["status"] == "failed", run
    assert run["error_reason"] == "redaction_blank_literal", run
    assert "nothing was sent" in (run["error_message"] or ""), run
    assert world["sent"] == []


# ---------------------------------------------------------------------------
# The child's environment
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_child_environment_carries_no_provider_key(world, monkeypatch) -> None:
    """The child gets the payload and the hints, and nothing it does not need.
    Keys are set in the PARENT here, so a child that inherited the parent's
    environment would carry them."""
    import app.ai.isolation as isolation

    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(name, "sk-test-not-a-real-key")
    monkeypatch.setattr(isolation, "_TARGET", targets.report_environment)

    cleaned, _counts = isolation.redact_payload_isolated(
        {"env": "x"}, mode="strict", client_org_name=None, name_hints=()
    )
    names = cleaned["env"]
    assert isinstance(names, list) and names, f"child reported no environment: {cleaned!r}"
    leaked = [n for n in names if n.upper().endswith("_API_KEY")]
    assert leaked == [], f"the redaction child inherited provider keys: {leaked}"
    assert not [n for n in names if n.upper().startswith("SHIELD_")], names
    assert "DATABASE_URL" not in names, names


# ---------------------------------------------------------------------------
# The concurrency cap: typed refusal, never an unbounded queue
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_every_place_taken_refuses_typed(world, monkeypatch) -> None:
    """One place. While a one-call run holds it (its child is running), a
    second one-call run is refused with `redaction_capacity_busy` -- it neither
    queues nor runs. "Holds" is established by the child's own PID file, not by
    a sleep."""
    import app.ai.isolation as isolation
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_MAX_RUNS", "1")
    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", "5")
    get_settings.cache_clear()
    monkeypatch.setattr(isolation, "_TARGET", targets.write_pid_then_spin)

    pid_file = world["tmp"] / "holder.pid"
    holder_error: dict[str, BaseException] = {}

    def _hold() -> None:
        try:
            isolation.redact_payload_isolated(
                {"__pid_file__": str(pid_file)},
                mode="strict",
                client_org_name=None,
                name_hints=(),
            )
        except BaseException as exc:  # noqa: BLE001 - inspected below
            holder_error["e"] = exc

    holder = threading.Thread(target=_hold, daemon=True)
    holder.start()
    rw.wait_for_file(pid_file)

    with pytest.raises(StarletteHTTPException) as refused:
        isolation.redact_payload_isolated(
            {"x": "y"}, mode="strict", client_org_name=None, name_hints=()
        )
    assert refused.value.detail["reason"] == "redaction_capacity_busy", refused.value.detail
    assert "nothing was sent" in refused.value.detail["message"]

    holder.join(rw.HANG_GUARD_S)
    assert not holder.is_alive()
    assert isinstance(holder_error.get("e"), StarletteHTTPException), holder_error
    assert holder_error["e"].detail["reason"] == "redaction_budget_exceeded"
    rw.assert_gone(int(pid_file.read_text()))


@pytest.mark.unit
def test_a_child_running_a_different_redactor_file_is_refused(world, monkeypatch) -> None:
    """The child must run the SAME redactor file as the api. Python 3.12's
    forkserver ignores the parent's sys.path, so a forkserver started from
    another directory, or beside an installed copy of `app`, can load another
    tree's `app.ai.redact`: older rules, silently. Measured on the #552 build
    harness (a `python -I` uvicorn beside an editable install of another
    worktree). The parent names its own file; a child that loaded a different
    one refuses, typed, and nothing is sent."""
    import app.ai.isolation as isolation

    monkeypatch.setattr(isolation, "_redactor_file", lambda: "/not/the/api/app/ai/redact.py")
    with pytest.raises(StarletteHTTPException) as refused:
        isolation.redact_payload_isolated(
            {"x": "Dana Whitfield"}, mode="strict", client_org_name=None, name_hints=()
        )
    assert refused.value.detail["reason"] == "redaction_failed", refused.value.detail
    assert isolation.places_in_use() == 0
