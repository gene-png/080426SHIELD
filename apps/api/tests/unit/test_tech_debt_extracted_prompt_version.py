"""TD-2 part A, F1 (for #1058): `capability_items.extracted_prompt_version`.

A NULL `is_suite` alone cannot say which of two things happened: the row was
extracted before TD-2 (nobody asked), or a v3.3 extraction asked and the model
did not answer. Part B treats the first as "not checked" and the second as a
finding. The advisor's ruling (#736 6160171214, F1 option (a)) records, on the
row the extraction inserts, the prompt version that ran -- the SAME value the
call records in `llm_calls.prompt_version`, passed through rather than derived
again. Every row a consultant adds (an included excluded row, a component) was
never asked, and keeps NULL.

Expected values are typed here ("v3.3", the version the prompt this PR ships
carries) and checked against the `llm_calls` row, never read from the code under
test. Everything goes through the routes; stored values are read back from the
database.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.capability import CapabilityItem
from app.models.llm_call import LLMCall
from tests._ai_runs import tech_debt_extract
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

#: The version the in-tree prompt carries since TD-2 part A, typed here.
V33 = "v3.3"


def _answer(name: str, row: int, **fields) -> dict:
    """One item in the shape section 10's example gives; `...` removes a key."""
    base = {
        "name": name,
        "vendor": None,
        "category": None,
        "function": None,
        "annual_cost_usd": None,
        "license_count": None,
        "notes": None,
        "security_related": False,
        "security_functions": [],
        "is_suite": False,
        "recognized": True,
        "confidence_pct": 90,
        "source_row_index": row,
    }
    base.update(fields)
    return {k: v for k, v in base.items() if v is not ...}


def _world(app_client, items: list[dict], rows: int):  # noqa: F811
    c, Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": items})))
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    csv = "name\n" + "".join(f"row{k}\n" for k in range(rows))
    art = _upload_csv(c, bearer, "x.csv", csv.encode())
    body = tech_debt_extract(c, svc, h, art)
    return c, Sess, h, body


def _stored(Sess) -> dict[str, tuple[object, object]]:
    """name -> (is_suite, extracted_prompt_version), as the database holds them."""
    with Sess() as s:
        rows = s.execute(
            select(
                CapabilityItem.name,
                CapabilityItem.is_suite,
                CapabilityItem.extracted_prompt_version,
            )
        ).all()
    return {name: (suite, version) for name, suite, version in rows}


def _recorded_versions(Sess) -> list[str]:
    with Sess() as s:
        return list(
            s.execute(
                select(LLMCall.prompt_version).where(LLMCall.purpose == "extract.capabilities")
            ).scalars()
        )


def test_an_unanswered_is_suite_from_a_v33_run_reads_as_asked_not_as_pre_td2(
    app_client,  # noqa: F811
) -> None:
    items = [
        _answer("Okta", 0),  # positive first: an answered flag
        _answer("Adobe Creative Cloud All Apps", 1, is_suite=...),
    ]
    _c, Sess, _h, _body = _world(app_client, items, rows=2)
    stored = _stored(Sess)
    assert stored["Okta"] == (False, V33)
    suite, version = stored["Adobe Creative Cloud All Apps"]
    assert suite is None  # unanswered, never False
    # ... and NOT NULL here: this is what tells "asked, unanswered" from a row
    # extracted before TD-2, which holds NULL in both.
    assert version == V33
    # The same value the call recorded, not one worked out again.
    assert _recorded_versions(Sess) == [V33]


def test_a_row_the_consultant_includes_carries_no_prompt_version(app_client) -> None:  # noqa: F811
    c, Sess, h, body = _world(app_client, [_answer("Okta", 0)], rows=2)
    assert len(body["excluded_rows"]) == 1  # APPEAR: there is a row to include
    r = c.post(
        f"/tech-debt/capability-lists/{body['id']}/excluded-rows/1/include",
        headers=h,
        json={"name": "Included by hand"},
    )
    assert r.status_code == 201, r.text
    stored = _stored(Sess)
    assert stored["Okta"] == (False, V33)  # positive control: the extracted row
    assert stored["Included by hand"] == (None, None)


def test_a_component_the_consultant_names_carries_no_prompt_version(
    app_client,  # noqa: F811
) -> None:
    c, Sess, h, body = _world(app_client, [_answer("Microsoft 365 G5", 0, is_suite=True)], rows=1)
    bundle = body["items"][0]["id"]
    r = c.post(
        f"/tech-debt/capability-items/{bundle}/components",
        headers=h,
        json={"components": [{"name": "Defender for Endpoint"}]},
    )
    assert r.status_code == 201, r.text
    stored = _stored(Sess)
    assert stored["Microsoft 365 G5"] == (True, V33)  # positive control
    assert stored["Defender for Endpoint"] == (None, None)
