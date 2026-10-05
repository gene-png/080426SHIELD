"""#845: a security tool the extraction marks "not in use" gets its own sign-off.

Tech Debt v3.2 (issue 806, comment 5983838515, approved by Gene) returns a
security tool that the row describes as planned, not yet deployed, inactive or no
longer used as `security_related: false` with empty functions, and tells the
model to "Begin `notes` with exactly `Security tool not in use:`". The sign-off
queue tells those rows apart by that one prefix (`signoff_kind`). Confirming one
is recorded as a removal from ATT&CK scope. A row carrying the prefix while it
also lists security functions contradicts itself; the parser keeps it in scope,
and the list counts it.

The prefix and the example note are copied from v3.2's text, never imported
from the code. Every assertion goes through the routes the workspace uses.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.audit_entry import AuditEntry
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

#: From v3.2 section 7, verbatim.
PREFIX = "Security tool not in use:"
EXAMPLE_NOTE = "Security tool not in use: planned, not yet deployed."


def _item(name: str, i: int, *, related: bool, functions: list[str], notes: str | None) -> dict:
    return {
        "name": name,
        "vendor": "Vendor",
        "category": None,
        "function": None,
        "annual_cost_usd": 1000,
        "license_count": None,
        "notes": notes,
        "security_related": related,
        "security_functions": functions,
        "confidence_pct": 60,
        "source_row_index": i,
    }


def _extract(app_client, items: list[dict]) -> tuple:  # noqa: F811
    c, Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": items})))
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    rows = "".join(f"{it['name']}\n" for it in items)
    art = _upload_csv(c, bearer, "x.csv", ("name\n" + rows).encode())
    body = tech_debt_extract(c, svc, h, art)
    return c, Sess, h, svc, body


def _by_name(body: dict) -> dict:
    return {i["name"]: i for i in body["items"]}


def test_signoff_kind_is_the_exact_prefix_only(app_client) -> None:  # noqa: F811
    items = [
        _item("Planned EDR", 0, related=False, functions=[], notes=EXAMPLE_NOTE),
        _item("Payroll", 1, related=False, functions=[], notes="Planned, not yet deployed."),
        _item("Lowercase", 2, related=False, functions=[], notes="security tool not in use: x"),
        _item("Mid", 3, related=False, functions=[], notes=f"Note. {EXAMPLE_NOTE}"),
        _item("Leading space", 4, related=False, functions=[], notes=f"  {EXAMPLE_NOTE}"),
        _item("Active EDR", 5, related=True, functions=["detect"], notes=None),
    ]
    _c, _S, _h, _svc, body = _extract(app_client, items)
    kinds = {n: i["signoff_kind"] for n, i in _by_name(body).items()}
    assert kinds == {
        "Planned EDR": "not_in_use",
        "Payroll": "not_security",
        "Lowercase": "not_security",
        "Mid": "not_security",
        "Leading space": "not_in_use",
        "Active EDR": None,
    }


def test_confirming_a_not_in_use_row_is_recorded_as_removal_from_attack(
    app_client,  # noqa: F811
) -> None:
    items = [
        _item("Planned EDR", 0, related=False, functions=[], notes=EXAMPLE_NOTE),
        _item("Payroll", 1, related=False, functions=[], notes=None),
    ]
    c, Sess, h, _svc, body = _extract(app_client, items)
    by = _by_name(body)
    for name in ("Planned EDR", "Payroll"):
        r = c.post(
            f"/tech-debt/capability-items/{by[name]['id']}/security-classification/confirm",
            headers=h,
        )
        assert r.status_code == 200, r.text
    with Sess() as s:
        rows = {
            (e.action, e.target_id): e.details
            for e in s.execute(
                select(AuditEntry).where(AuditEntry.action.like("capability_item.%"))
            ).scalars()
        }
    planned = uuid.UUID(by["Planned EDR"]["id"])
    payroll = uuid.UUID(by["Payroll"]["id"])
    assert rows[("capability_item.removed_from_attack_scope", planned)] == {
        "name": "Planned EDR",
        "notes": EXAMPLE_NOTE,
    }
    assert ("capability_item.security_classification_confirmed", planned) not in rows
    assert rows[("capability_item.security_classification_confirmed", payroll)] == {
        "name": "Payroll"
    }


def test_the_contradiction_is_counted_and_kept_in_scope(app_client) -> None:  # noqa: F811
    """The prefix with functions: the parser keeps it security-related (the safe
    direction), the list counts it, and the extraction's audit row records it."""
    items = [
        _item("Odd EDR", 0, related=False, functions=["detect"], notes=EXAMPLE_NOTE),
        _item("Planned EDR", 1, related=False, functions=[], notes=EXAMPLE_NOTE),
    ]
    _c, Sess, _h, _svc, body = _extract(app_client, items)
    assert body["not_in_use_contradictions"] == 1
    odd = _by_name(body)["Odd EDR"]
    assert (odd["security_related"], odd["signoff_kind"]) == (True, None)
    with Sess() as s:
        details = (
            s.execute(
                select(AuditEntry.details).where(AuditEntry.action == "capability_list.extracted")
            )
            .scalars()
            .one()
        )
    assert details["not_in_use_contradictions"] == 1


def test_an_override_is_not_counted_as_a_contradiction(app_client) -> None:  # noqa: F811
    """A consultant marking a not-in-use row security-related leaves the same
    stored shape the parser's flip does. It is the consultant's ruling, not the
    model contradicting itself, so it is not counted."""
    items = [_item("Planned EDR", 0, related=False, functions=[], notes=EXAMPLE_NOTE)]
    c, _S, h, _svc, body = _extract(app_client, items)
    assert body["not_in_use_contradictions"] == 0  # APPEAR: the count is there
    item_id = _by_name(body)["Planned EDR"]["id"]
    r = c.post(
        f"/tech-debt/capability-items/{item_id}/security-classification/override",
        headers=h,
        json={"security_functions": ["detect"]},
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert _by_name(after)["Planned EDR"]["security_related"] is True
    assert after["not_in_use_contradictions"] == 0


def test_the_offline_fixture_marks_a_planned_security_tool_as_v3_2_says() -> None:
    """The offline extraction mirrors v3.2 section 7, so the not-in-use group is
    reachable in fixture mode (demo and e2e)."""
    from app.ai.fixtures import _fixture_tech_debt

    rows = [
        {"name": "Falcon Insight"},
        {"name": "Falcon Identity", "status": "Planned, not yet deployed"},
        {"name": "Okta"},
        {"name": "Workday HCM", "status": "planned"},
    ]
    items = json.loads(_fixture_tech_debt({"rows": rows}).content)["items"]
    by = {i["name"]: i for i in items}
    planned = by["Falcon Identity"]
    assert (planned["security_related"], planned["security_functions"]) == (False, [])
    assert planned["notes"] == "Security tool not in use: not yet deployed."
    assert planned["notes"].startswith(PREFIX)
    # A non-security row that says "planned" is not a security tool not in use.
    assert not (by["Workday HCM"]["notes"] or "").startswith(PREFIX)
    # Rows that say nothing about lifecycle are unchanged.
    assert by["Falcon Insight"]["security_related"] is True


def test_the_prefix_is_matched_after_leading_whitespace_in_an_edited_note(
    app_client,  # noqa: F811
) -> None:
    """The parser strips what the model sends, so leading whitespace reaches the
    store only through a consultant's notes edit, which is kept as typed."""
    items = [_item("Payroll", 0, related=False, functions=[], notes=None)]
    c, _S, h, _svc, body = _extract(app_client, items)
    item_id = _by_name(body)["Payroll"]["id"]
    assert _by_name(body)["Payroll"]["signoff_kind"] == "not_security"  # APPEAR
    r = c.patch(
        f"/tech-debt/capability-items/{item_id}", headers=h, json={"notes": f"  {EXAMPLE_NOTE}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["notes"] == f"  {EXAMPLE_NOTE}"
    assert r.json()["signoff_kind"] == "not_in_use"
