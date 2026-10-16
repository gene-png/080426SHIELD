"""TD-5 (for #1060): "Let AI estimate", through the route a consultant clicks.

The world is `test_capability_list_revision.py`'s: a real extraction run, two
capabilities. Each test empties one cost through the item PATCH (the state
"no cost recorded"), then drives the estimate route to completion with the
production runner (`tests/_ai_runs.py`).

Also the proof `test_capability_list_revision.py`'s RUN_EDITS names for this
route: an estimate that writes a cost makes an approval stale, and a run that
writes none does not.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.fixtures import _fixture_tech_debt_cost_estimate
from app.ai.llm import LLMResponse
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityItem
from tests._ai_runs import get_run
from tests.unit.test_capability_list_revision import (  # noqa: F401  (fixture)
    World,
    _approve,
    _decide_all,
    _latest,
    _revision,
    _world,
    app_client,
)

pytestmark = pytest.mark.unit

PURPOSE = "tech_debt.cost_estimate"


def _uncost(w: World, item_id: str) -> None:
    r = w.c.patch(
        f"/tech-debt/capability-items/{item_id}", headers=w.h, json={"annual_cost_usd": None}
    )
    assert r.status_code == 200, r.text
    assert r.json()["annual_cost_usd"] is None


def _estimate(w: World) -> dict:
    """POST the estimate and return the run, whatever its status."""
    r = w.c.post(
        f"/tech-debt/capability-lists/{w.list_id}/cost-estimate",
        headers=w.h,
        json={"serves": "offline"},
    )
    assert r.status_code == 202, r.text
    return get_run(w.c, r.json()["run_id"], w.h)


def _row(w: World, item_id: str) -> dict:
    return next(i for i in _latest(w)["items"] if i["id"] == item_id)


def _world_with_estimate_fixture(app_client, answer=None) -> World:  # noqa: F811
    _c, _sessions, provider = app_client
    w = _world(app_client)
    provider.register(PURPOSE, answer or _fixture_tech_debt_cost_estimate)
    return w


def test_an_estimate_fills_only_the_uncosted_row_and_labels_it(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    _uncost(w, w.other_id)
    costed_before = _row(w, w.security_id)["annual_cost_usd"]
    run = _estimate(w)
    assert run["status"] == "completed", run
    assert run["purpose"] == PURPOSE
    assert run["result"]["asked"] == 1
    assert run["result"]["estimated"] == 1
    assert run["result"]["declined"] == 0
    assert run["result"]["refused"] == {}
    estimated = _row(w, w.other_id)
    assert estimated["annual_cost_usd"] == 12000
    assert estimated["cost_source"] == "ai_estimate"
    assert estimated["cost_estimate_basis"]
    # The costed row was not asked and is untouched.
    untouched = _row(w, w.security_id)
    assert untouched["annual_cost_usd"] == costed_before
    assert untouched["cost_source"] is None
    with w.sessions() as s:
        entries = (
            s.execute(
                select(AuditEntry).where(AuditEntry.action == "capability_items.cost_estimated")
            )
            .scalars()
            .all()
        )
    assert len(entries) == 1
    assert entries[0].details["estimated"] == 1


def test_editing_an_estimated_cost_is_the_override(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    _uncost(w, w.other_id)
    assert _estimate(w)["status"] == "completed"
    r = w.c.patch(
        f"/tech-debt/capability-items/{w.other_id}", headers=w.h, json={"annual_cost_usd": 9000}
    )
    assert r.status_code == 200, r.text
    assert r.json()["cost_source"] == "consultant"
    assert r.json()["cost_estimate_basis"] is None


def test_clearing_a_cost_clears_its_source(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    _uncost(w, w.other_id)
    assert _estimate(w)["status"] == "completed"
    _uncost(w, w.other_id)
    row = _row(w, w.other_id)
    assert row["cost_source"] is None
    assert row["cost_estimate_basis"] is None


def test_nothing_to_estimate_is_a_typed_refusal_and_no_run(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    r = w.c.post(
        f"/tech-debt/capability-lists/{w.list_id}/cost-estimate",
        headers=w.h,
        json={"serves": "offline"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "no_costs_to_estimate"


def test_a_locked_uncosted_row_is_not_asked(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    _uncost(w, w.other_id)
    r = w.c.patch(f"/tech-debt/capability-items/{w.other_id}", headers=w.h, json={"locked": True})
    assert r.status_code == 200, r.text
    r = w.c.post(
        f"/tech-debt/capability-lists/{w.list_id}/cost-estimate",
        headers=w.h,
        json={"serves": "offline"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "no_costs_to_estimate"


def test_a_declined_estimate_leaves_the_row_uncosted(app_client) -> None:  # noqa: F811
    def decline(payload: dict) -> LLMResponse:
        return LLMResponse(
            json.dumps(
                {
                    "estimates": [
                        {"ref": t["ref"], "annual_cost_usd": None, "basis": "Unknown product."}
                        for t in payload["tools"]
                    ]
                }
            )
        )

    w = _world_with_estimate_fixture(app_client, decline)
    _uncost(w, w.other_id)
    run = _estimate(w)
    assert run["status"] == "completed", run
    assert run["result"]["declined"] == 1
    assert run["result"]["estimated"] == 0
    row = _row(w, w.other_id)
    assert row["annual_cost_usd"] is None
    assert row["cost_source"] is None


def test_strays_and_omissions_are_counted_and_never_applied(app_client) -> None:  # noqa: F811
    def stray(payload: dict) -> LLMResponse:
        return LLMResponse(
            json.dumps(
                {"estimates": [{"ref": "T99", "annual_cost_usd": 5000, "basis": "never asked"}]}
            )
        )

    w = _world_with_estimate_fixture(app_client, stray)
    _uncost(w, w.other_id)
    run = _estimate(w)
    assert run["status"] == "completed", run
    assert run["result"]["stray_entries"] == 1
    assert run["result"]["refused"] == {"omitted": 1}
    assert run["result"]["estimated"] == 0
    assert _row(w, w.other_id)["annual_cost_usd"] is None


def test_a_row_costed_during_the_run_is_not_overwritten(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """A consultant's edit that lands after the provider answered and before
    the run writes: the run's conditional UPDATE finds the row costed and
    counts it `changed_meanwhile`. The edit is made where the run reads the
    answers (`parse_estimates`), the last moment before the write, in its own
    session, as a concurrent PATCH would be."""
    import app.routes.tech_debt as td

    holder: dict = {}
    real_parse = td.parse_estimates

    def parse_then_cost_the_row(entries, asked):
        w = holder["w"]
        with w.sessions() as s:
            row = s.get(CapabilityItem, uuid.UUID(w.other_id))
            row.annual_cost_usd = 777
            s.commit()
        return real_parse(entries, asked)

    monkeypatch.setattr(td, "parse_estimates", parse_then_cost_the_row)
    w = _world_with_estimate_fixture(app_client)
    holder["w"] = w
    _uncost(w, w.other_id)
    run = _estimate(w)
    assert run["status"] == "completed", run
    assert run["result"]["refused"] == {"changed_meanwhile": 1}
    assert run["result"]["estimated"] == 0
    row = _row(w, w.other_id)
    assert row["annual_cost_usd"] == 777
    assert row["cost_source"] is None


# ---------------------------------------------------------------------------
# The RUN_EDITS proof for `test_capability_list_revision.py`
# ---------------------------------------------------------------------------


def test_an_estimate_after_approval_makes_the_approval_stale(app_client) -> None:  # noqa: F811
    w = _world_with_estimate_fixture(app_client)
    _uncost(w, w.other_id)
    _decide_all(w)
    assert _approve(w).status_code == 200
    assert _latest(w)["approval_current"] is True
    before = _revision(w)
    assert _estimate(w)["result"]["estimated"] == 1
    assert _revision(w) == before + 1
    assert _latest(w)["approval_current"] is False


def test_a_run_that_estimates_nothing_leaves_the_approval_current(app_client) -> None:  # noqa: F811
    def decline(payload: dict) -> LLMResponse:
        return LLMResponse(
            json.dumps(
                {
                    "estimates": [
                        {"ref": t["ref"], "annual_cost_usd": None, "basis": "b"}
                        for t in payload["tools"]
                    ]
                }
            )
        )

    w = _world_with_estimate_fixture(app_client, decline)
    _uncost(w, w.other_id)
    _decide_all(w)
    assert _approve(w).status_code == 200
    before = _revision(w)
    assert _estimate(w)["result"]["estimated"] == 0
    assert _revision(w) == before
    assert _latest(w)["approval_current"] is True
