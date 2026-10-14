"""TD-2 part A (for #1058): the extraction's `is_suite` and `recognized` flags.

Tech Debt prompt v3.3 section 9a asks for both on every item, and verify item 10
says they are "true or false on every item, never null". The design (td2, as
ruled by the advisor) says the parser stores a missing or non-boolean value as
NULL, never as False, and records it in `extraction_findings`: False is a
decision ("not a suite", "not recognized"), NULL is the absence of one, and
part B's red-row gate treats the two differently.

Expected keys and example values are copied from the prompt's TEXT (section
10's JSON example, parsed below), never from the parser. Every case goes through
the extraction route; stored values are read back from `capability_items`.
"""

from __future__ import annotations

import json
import re

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.audit_entry import AuditEntry
from app.models.capability import CapabilityItem
from tests._ai_runs import get_run
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

#: The two keys section 9a names, as the prompt writes them.
FLAGS = ("is_suite", "recognized")


def _prompt_example() -> dict:
    """Section 10's one example item, parsed out of the prompt text."""
    from app.tech_debt.extract import PROMPT

    section = PROMPT.split("## 10. Output requirements", 1)[1]
    start = section.index("{")
    example, _ = json.JSONDecoder().raw_decode(section[start:])
    (item,) = example["items"]
    return item


def test_the_prompt_example_carries_both_flags_as_booleans() -> None:
    """The precondition every other test here builds on: section 10's example
    is where the keys are copied from."""
    item = _prompt_example()
    assert item["is_suite"] is False
    assert item["recognized"] is True


def _item(i: int, **fields) -> dict:
    """The prompt's example item, with a name, a row and `fields` over it.
    A field given as `...` is removed, so the model "sent" no such key."""
    base = {**_prompt_example(), "name": f"Capability {i}", "source_row_index": i}
    base.update(fields)
    return {k: v for k, v in base.items() if v is not ...}


def _extract(app_client, items: list[dict], rows: int):  # noqa: F811
    c, Sess, provider = app_client
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": items})))
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    csv = "name\n" + "".join(f"row{k}\n" for k in range(rows))
    art = _upload_csv(c, bearer, "x.csv", csv.encode())
    r = c.post(
        f"/tech-debt/services/{svc}/capability-lists/extract",
        headers=h,
        json={"artifact_id": art, "serves": "offline"},
    )
    assert r.status_code == 202, r.text
    run = get_run(c, r.json()["run_id"], h)
    assert run["status"] == "completed", run
    latest = c.get(f"/tech-debt/services/{svc}/capability-lists/latest", headers=h)
    assert latest.status_code == 200, latest.text
    return Sess, latest.json()


def _stored(Sess) -> dict[str, tuple[object, object]]:
    """name -> (is_suite, recognized), as the database holds them."""
    with Sess() as s:
        rows = s.execute(
            select(CapabilityItem.name, CapabilityItem.is_suite, CapabilityItem.recognized)
        ).all()
    return {name: (suite, recog) for name, suite, recog in rows}


def _flag_findings(body: dict) -> list[dict]:
    return [f for f in body["extraction_findings"] if f["field"] in FLAGS]


def test_real_booleans_are_stored_as_sent_and_record_nothing(app_client) -> None:  # noqa: F811
    items = [
        _item(0, name="Microsoft 365 G5", is_suite=True, recognized=True),
        _item(1, name="Okta", is_suite=False, recognized=True),
        _item(2, name="ZQX-Internal-7", is_suite=False, recognized=False),
    ]
    Sess, body = _extract(app_client, items, rows=3)
    assert _stored(Sess) == {
        "Microsoft 365 G5": (True, True),
        "Okta": (False, True),
        "ZQX-Internal-7": (False, False),
    }
    assert _flag_findings(body) == []


def test_a_missing_flag_is_stored_as_null_not_false_and_recorded(app_client) -> None:  # noqa: F811
    items = [
        _item(0, name="Okta"),  # positive first: a compliant item records nothing
        _item(1, name="Adobe Creative Cloud All Apps", is_suite=..., recognized=...),
    ]
    Sess, body = _extract(app_client, items, rows=2)
    stored = _stored(Sess)
    assert stored["Okta"] == (False, True)
    suite, recog = stored["Adobe Creative Cloud All Apps"]
    # `is None`, not falsy: False would read as "the model said not a suite".
    assert suite is None
    assert recog is None
    assert _flag_findings(body) == [
        {
            "source_row_index": 1,
            "item_name": "Adobe Creative Cloud All Apps",
            "field": "is_suite",
            "reason": "missing",
            "value": "None",
        },
        {
            "source_row_index": 1,
            "item_name": "Adobe Creative Cloud All Apps",
            "field": "recognized",
            "reason": "missing",
            "value": "None",
        },
    ]


def test_a_null_flag_is_missing_too(app_client) -> None:  # noqa: F811
    """Verify item 10: "never null". A null is the model not answering."""
    Sess, body = _extract(app_client, [_item(0, is_suite=None, recognized=True)], rows=1)
    assert _stored(Sess) == {"Capability 0": (None, True)}
    assert [(f["field"], f["reason"]) for f in _flag_findings(body)] == [("is_suite", "missing")]


@pytest.mark.parametrize(
    ("sent", "shown"),
    [
        ("true", "true"),
        ("false", "false"),
        ("yes", "yes"),
        (1, "1"),
        (0, "0"),
        ([], "[]"),
    ],
)
def test_a_non_boolean_flag_is_stored_as_null_and_recorded(
    app_client, sent: object, shown: str  # noqa: F811
) -> None:
    """A string or a number is not what section 10 asks for. It is not read as
    the boolean it resembles: `0` and `"false"` would otherwise store False, a
    decision the model did not make in the form asked."""
    Sess, body = _extract(app_client, [_item(0, is_suite=True, recognized=sent)], rows=1)
    assert _stored(Sess) == {"Capability 0": (True, None)}
    assert _flag_findings(body) == [
        {
            "source_row_index": 0,
            "item_name": "Capability 0",
            "field": "recognized",
            "reason": "not_boolean",
            "value": shown,
        }
    ]


def test_the_flag_findings_are_counted_in_the_extraction_audit(app_client) -> None:  # noqa: F811
    items = [
        _item(0, is_suite=...),
        _item(1, recognized="true"),
        _item(2, is_suite=1, recognized=...),
    ]
    Sess, _ = _extract(app_client, items, rows=3)
    with Sess() as s:
        details = (
            s.execute(select(AuditEntry).where(AuditEntry.action == "capability_list.extracted"))
            .scalars()
            .one()
            .details
        )
    assert details["findings_by_reason"] == {"missing": 2, "not_boolean": 2}


# --- the offline fixture ------------------------------------------------------

FIXTURE_CSV = (
    "name,vendor,category,annual_cost_usd,license_count,status\n"
    "Microsoft 365 G5,Microsoft,Productivity,300000,500,active\n"  # 0: the prompt's suite
    "Okta,Okta,IAM,60000,500,active\n"  # 1: one product
    "ZQX-7741,,,,,active\n"  # 2: an internal code
    "Adobe Creative Cloud All Apps,Adobe,Design,20000,20,active\n"  # 3: the prompt's suite
)


def _fixture_extract(app_client):  # noqa: F811
    from app.ai.fixtures import build_runtime_provider

    c, Sess, provider = app_client
    runtime = build_runtime_provider()
    provider.register(
        "extract.capabilities",
        lambda p: runtime.complete("", {**p, "__purpose__": "extract.capabilities"}),
    )
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc = c.post("/tech-debt/services", headers=h, json={"title": "x"}).json()["id"]
    art = _upload_csv(c, bearer, "inv.csv", FIXTURE_CSV.encode())
    r = c.post(
        f"/tech-debt/services/{svc}/capability-lists/extract",
        headers=h,
        json={"artifact_id": art, "serves": "offline"},
    )
    assert r.status_code == 202, r.text
    assert get_run(c, r.json()["run_id"], h)["status"] == "completed"
    body = c.get(f"/tech-debt/services/{svc}/capability-lists/latest", headers=h).json()
    return Sess, body


def test_the_fixture_item_has_exactly_the_prompt_examples_keys() -> None:
    from app.ai.fixtures import build_runtime_provider

    rows = [{"name": "Okta", "vendor": "Okta"}, {"name": "Microsoft 365 G5"}]
    out = build_runtime_provider().complete(
        "", {"rows": rows, "__purpose__": "extract.capabilities"}
    )
    items = json.loads(out.content)["items"]
    assert len(items) == 2
    for item in items:
        assert set(item) == set(_prompt_example())
        for flag in FLAGS:
            assert isinstance(item[flag], bool), (flag, item)


def test_the_fixture_marks_a_suite_and_an_unrecognized_code(app_client) -> None:  # noqa: F811
    """Both states are reachable offline, so part B's red and amber rows are
    too: an unreachable review surface is an untested one."""
    Sess, body = _fixture_extract(app_client)
    assert _stored(Sess) == {
        "Microsoft 365 G5": (True, True),
        "Okta": (False, True),
        "ZQX-7741": (False, False),
        "Adobe Creative Cloud All Apps": (True, True),
    }
    assert _flag_findings(body) == []
    # The example names are the prompt's own, not chosen to suit the fixture.
    from app.tech_debt.extract import PROMPT

    for name in ("Microsoft 365 G5", "Adobe Creative Cloud All Apps"):
        assert re.search(re.escape(f'"{name}"'), PROMPT), name
