"""#1380 (a residual of #1025 x #1080): a hinted shown-form build runs in the
redaction child for up to the redaction budget, so the caller must hold no
pooled connection while it does. Each test samples the connections checked
out WHEN the child is asked (`shown_forms`' own call), through the route or
run that makes the build; each count is 1 with that run's builds before its
`end_read_transaction` line."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

import pytest

from app.ai.llm import LLMResponse
from app.models.user import User, UserRole
from tests._pool_count import pool_count
from tests.unit.test_ai_runs_attack import (  # noqa: F401  (app_parts: fixture)
    app_parts,
)
from tests.unit.test_attack_name_hints import DANA, _create, _tenant_user, _tool
from tests.unit.test_attack_run_ai import app_client  # noqa: F401  (fixture)
from tests.unit.test_attack_scenario_routes import EDR, SIEM, _flags, _run_to_completion, _world

pytestmark = pytest.mark.unit


@pytest.fixture
def held_at_child_calls(monkeypatch) -> Iterator[list[tuple[int, bool]]]:
    """(connections out, hints present) at every shown-form child call."""
    from app.attack import shown_forms as shown_forms_module

    samples: list[tuple[int, bool]] = []
    real = shown_forms_module.redact_payload_isolated
    with pool_count() as held:

        def sampled(payload, **kwargs):
            samples.append((held[0], bool(kwargs.get("name_hints"))))
            return real(payload, **kwargs)

        monkeypatch.setattr(shown_forms_module, "redact_payload_isolated", sampled)
        yield samples


def test_the_attack_run_builds_its_hinted_resolver_holding_no_connection(
    app_client, monkeypatch, held_at_child_calls  # noqa: F811
) -> None:
    from app.routes import attack as attack_routes
    from tests._ai_runs import attack_run_ai
    from tests.unit.test_attack_run_ai import _admin, _seed_tech_debt_tools

    monkeypatch.setattr(attack_routes, "_MITRE_MAX_WORKERS", 1)
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    with TestSession() as db:
        db.add(
            User(
                email="dana.whitfield@acme.example",
                password_hash="x" * 64,
                role=UserRole.CLIENT,
                display_name=DANA,
                client_id=uuid.UUID(cid),
            )
        )
        db.commit()
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    assert c.post(f"/attack/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
    provider.register("mitre_map", lambda _p: LLMResponse(json.dumps({"techniques": []})))
    held_at_child_calls.clear()
    attack_run_ai(c, svc_id, h)
    hinted = [n for n, hints in held_at_child_calls if hints]
    assert hinted, "setup: the run asked the child with name hints"
    assert set(hinted) == {0}, held_at_child_calls


def test_the_what_if_run_builds_its_hinted_forms_holding_no_connection(
    app_parts, monkeypatch, held_at_child_calls  # noqa: F811
) -> None:
    from app.routes import attack_scenarios

    monkeypatch.setattr(attack_scenarios, "_MAX_WORKERS", 1)
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    w.answer({w.a: [_flags(w.a, SIEM, d=True)]})
    r = w.create([EDR])
    assert r.status_code == 201, r.text
    held_at_child_calls.clear()
    body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "completed", body["run_error"]
    hinted = [n for n, hints in held_at_child_calls if hints]
    assert hinted, "setup: the run asked the child with name hints"
    assert set(hinted) == {0}, held_at_child_calls


def test_the_what_if_run_checks_an_added_tool_for_collision_holding_no_connection(
    app_parts, monkeypatch, held_at_child_calls  # noqa: F811
) -> None:
    """A scenario that ADDS a tool: the run's collision check (`validate_added`,
    F4) asks the child too, besides the spellings and the shown forms. The
    removal-only test above never reaches it, because `_collision_in` returns
    when nothing was added."""
    from app.routes import attack_scenarios

    monkeypatch.setattr(attack_scenarios, "_MAX_WORKERS", 1)
    w = _world(app_parts)
    _tenant_user(w, DANA, "dana.whitfield@acme.example")
    w.answer({w.a: [_flags(w.a, SIEM, d=True)]})
    r = _create(w, [_tool("Plain Scanner")])
    assert r.status_code == 201, r.text
    held_at_child_calls.clear()
    body = _run_to_completion(w, r.json()["id"])
    assert body["run_status"] == "completed", body["run_error"]
    hinted = [n for n, hints in held_at_child_calls if hints]
    # Four asks: the run ROUTE's collision check, then the job's collision
    # check, removal spellings and shown forms. The route's first ask holds the
    # request's read (pre-existing, filed as #1437); the job's three do not.
    assert len(hinted) == 4, held_at_child_calls
    assert set(hinted[1:]) == {0}, held_at_child_calls
