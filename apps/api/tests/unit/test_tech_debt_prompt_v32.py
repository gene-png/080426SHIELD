"""#806: the Tech Debt extraction prompt is v3.2, and what v3.2 closes is counted.

The approved text is issue 806, comment 5983838515 (Gene, 2026-10-04). The plan
is issue 806, comment 5984600764, approved on issue 736 (comment 5986057990,
item 4). Its tests, in the plan's order:

1. The prompt is v3.2 verbatim, and `llm_calls.prompt_version` says "v3.2".
2. What a model can still send against v3.2's rules is kept as sent and counted:
   a missing name (`name_missing`), a confidence off v3.2's scale
   (`confidence_off_scale`), a category off v3.2's closed list
   (`category_off_list`), and two items naming one source row
   (`source_row_duplicated`). The first three are read live from the stored
   rows, so a consultant's correction clears them; the fourth cannot be (the
   row index is not stored on an item), so it is recorded at extraction.
3. The closed category list held in code equals the one in the prompt.
4. The offline fixture does what v3.2 says (`test_the_fixture_*`).

Every expected value below is copied from v3.2's text, never read from the code.
Everything goes through the extraction route and the latest-list GET.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.models.audit_entry import AuditEntry
from app.models.llm_call import LLMCall
from tests._ai_runs import get_run
from tests.unit.test_tech_debt_routes import (  # noqa: F401  (fixture)
    _register,
    _upload_csv,
    app_client,
)

pytestmark = pytest.mark.unit

#: sha256 of the fenced "Full text:" block of issue 806 comment 5983838515,
#: taken from the comment body on 2026-10-08 (11,536 characters, no trailing
#: newline). Any edit to the prompt, however small, goes red here.
V32_SHA256 = "61bf3e991807440a9d7588aaeb5129f08a9a61425af4bab67aca203f90d4302e"

#: v3.2's section headings, as the comment writes them.
V32_HEADINGS = (
    "## 1. Scope",
    "## 2. Redacted values",
    "## 3. Permitted inference",
    "## 4. One item per row",
    "## 5. Duplicate handling",
    "## 6. Field rules",
    "## 7. Security classification",
    "## 8. Confidence scoring",
    "## 9. Source indexes and output order",
    "## 10. Output requirements",
)

#: v3.2 section 7, the sentence that changed from v3.1 (for #845).
V32_PREFIX_SENTENCE = (
    "Begin `notes` with exactly `Security tool not in use:` followed by the status "
    'as the row states it (for example "Security tool not in use: planned, not yet '
    'deployed.").'
)
PREFIX = "Security tool not in use:"

#: v3.2 section 6, `category`, copied from the comment.
V32_CATEGORIES = (
    "AI/ML",
    "Analytics/BI",
    "Application Security",
    "Backup/Recovery",
    "Cloud Infrastructure",
    "CNAPP",
    "Collaboration/Communication",
    "CRM/Sales",
    "Data/Database",
    "DevOps/Engineering",
    "EDR/XDR",
    "ERP",
    "Finance/Accounting",
    "GRC/Compliance",
    "HCM/HR",
    "IAM/PAM",
    "Incident Response",
    "IT Asset Management",
    "IT Operations/ITSM",
    "Legal",
    "Marketing",
    "Network Infrastructure",
    "Network Security",
    "Productivity/Content",
    "Project/Work Management",
    "Security Awareness",
    "SIEM/SOAR",
    "Storage",
    "Vulnerability Management",
)

#: v3.2 section 8.
V32_CONFIDENCE = {100, 90, 60}


# --- 1. the prompt ------------------------------------------------------------


def test_the_prompt_is_v32_verbatim() -> None:
    from app.tech_debt.extract import PROMPT, PROMPT_VERSION

    assert PROMPT_VERSION == "v3.2"
    for heading in V32_HEADINGS:
        assert heading in PROMPT, heading
    assert V32_PREFIX_SENTENCE in PROMPT
    # No .format() placeholders were introduced: the text is placed, not built.
    assert hashlib.sha256(PROMPT.encode("utf-8")).hexdigest() == V32_SHA256


def test_the_category_list_in_code_is_the_one_in_the_prompt() -> None:
    from app.tech_debt.extract import CATEGORIES, PROMPT

    # Parsed out of the prompt: the backticked values on the line after
    # "Exactly one value from this list, or `null`:".
    after = PROMPT.split("Exactly one value from this list, or `null`:", 1)[1]
    line = next(ln for ln in after.splitlines() if ln.strip())
    in_prompt = tuple(re.findall(r"`([^`]+)`", line))
    assert in_prompt == V32_CATEGORIES
    assert tuple(CATEGORIES) == V32_CATEGORIES


# --- 2. the counters, through the extraction route ----------------------------


def _example(i: int, **fields) -> dict:
    """v3.2 section 10's JSON example, with a name, a row and `fields` over it."""
    base = {
        "name": f"Capability {i}",
        "vendor": None,
        "category": None,
        "function": None,
        "annual_cost_usd": None,
        "license_count": None,
        "notes": None,
        "security_related": False,
        "security_functions": [],
        "confidence_pct": 90,
        "source_row_index": i,
    }
    return {**base, **fields}


def _extract(app_client, items: list[dict], rows: int):  # noqa: F811
    """Extract `items` as the model's answer over `rows` uploaded rows. Returns
    the client, session factory, headers, the run and the latest list."""
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
    return c, Sess, h, run, latest.json()


ZERO = {
    "name_missing": 0,
    "confidence_off_scale": 0,
    "category_off_list": 0,
    "source_row_duplicated": 0,
}


def test_a_compliant_answer_has_every_flag_at_zero(app_client) -> None:  # noqa: F811
    items = [
        _example(0, name="Okta", vendor="Okta", category="IAM/PAM", confidence_pct=100),
        _example(1, name="Workday", category="HCM/HR", confidence_pct=60, notes="Edition."),
        _example(2, name="Jira", category=None, notes="Category: ticketing."),
    ]
    _, _, _, run, body = _extract(app_client, items, rows=3)
    assert body["extraction_flags"] == ZERO
    assert run["result"]["source_row_duplicated"] == 0


def test_a_missing_name_is_kept_and_counted(app_client) -> None:  # noqa: F811
    items = [_example(0, name="Okta"), _example(1, name="  ")]
    _, _, _, _, body = _extract(app_client, items, rows=2)
    assert body["extraction_flags"] == {**ZERO, "name_missing": 1}
    assert sorted(i["name"] for i in body["items"]) == ["Okta", "Unknown capability"]


def test_a_confidence_off_the_scale_is_kept_and_counted(app_client) -> None:  # noqa: F811
    items = [_example(0, confidence_pct=70), _example(1, confidence_pct=60, notes="Why.")]
    _, _, _, _, body = _extract(app_client, items, rows=2)
    assert body["extraction_flags"] == {**ZERO, "confidence_off_scale": 1}
    assert sorted(i["confidence_pct"] for i in body["items"]) == [60, 70]


def test_a_category_off_the_list_is_kept_and_counted(app_client) -> None:  # noqa: F811
    items = [_example(0, category="EDR"), _example(1, category="EDR/XDR")]
    _, _, _, _, body = _extract(app_client, items, rows=2)
    assert body["extraction_flags"] == {**ZERO, "category_off_list": 1}
    assert sorted(i["category"] for i in body["items"]) == ["EDR", "EDR/XDR"]


def test_a_duplicated_source_row_keeps_both_items_and_is_disclosed(
    app_client,  # noqa: F811
) -> None:
    items = [
        _example(0, name="Okta"),
        _example(1, name="Microsoft 365"),
        _example(1, name="Teams"),
        _example(2, name="Jira"),
    ]
    _, Sess, _, run, body = _extract(app_client, items, rows=3)

    # Both kept: the included count is per item, as before.
    assert sorted(i["name"] for i in body["items"]) == ["Jira", "Microsoft 365", "Okta", "Teams"]
    assert body["extraction_flags"] == {**ZERO, "source_row_duplicated": 1}
    # Recorded on the list, so it survives a reload; the later item is named.
    assert body["extraction_findings"] == [
        {
            "source_row_index": 1,
            "item_name": "Teams",
            "field": "source_row_index",
            "reason": "duplicated",
            "value": "1",
        }
    ]
    # In the run's result and the extraction's audit.
    assert run["result"]["source_row_duplicated"] == 1
    with Sess() as s:
        details = (
            s.execute(select(AuditEntry).where(AuditEntry.action == "capability_list.extracted"))
            .scalars()
            .one()
            .details
        )
    assert details["findings_by_reason"] == {"duplicated": 1}
    assert details["extraction_flags"] == {**ZERO, "source_row_duplicated": 1}


def test_a_row_named_three_times_is_one_source_row(app_client) -> None:  # noqa: F811
    """The copy counts SOURCE ROWS turned into more than one capability."""
    items = [_example(0, name="A"), _example(0, name="B"), _example(0, name="C")]
    _, _, _, run, body = _extract(app_client, items, rows=1)
    assert body["extraction_flags"]["source_row_duplicated"] == 1
    assert run["result"]["source_row_duplicated"] == 1
    assert [f["item_name"] for f in body["extraction_findings"]] == ["B", "C"]


def test_a_consultant_correction_clears_its_flag(app_client) -> None:  # noqa: F811
    items = [_example(0, category="EDR"), _example(1, name="", confidence_pct=75)]
    c, _, h, _, body = _extract(app_client, items, rows=2)
    assert body["extraction_flags"] == {
        **ZERO,
        "name_missing": 1,
        "confidence_off_scale": 1,
        "category_off_list": 1,
    }
    by_name = {i["name"]: i for i in body["items"]}
    r = c.patch(
        f"/tech-debt/capability-items/{by_name['Capability 0']['id']}",
        headers=h,
        json={"category": "EDR/XDR"},
    )
    assert r.status_code == 200, r.text
    r = c.patch(
        f"/tech-debt/capability-items/{by_name['Unknown capability']['id']}",
        headers=h,
        json={"name": "Okta"},
    )
    assert r.status_code == 200, r.text
    after = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert after["extraction_flags"] == ZERO


def test_the_prompt_version_is_recorded_and_an_earlier_one_is_not_measured(
    app_client,  # noqa: F811
) -> None:
    """A list an earlier prompt drafted followed that prompt's rules (v2 asked for
    any confidence 0-100 and gave "EDR" as a category), so it is not judged by
    v3.2's: its flags are null, "not measured", never a count."""
    items = [_example(0, category="EDR", confidence_pct=70)]
    c, Sess, h, _, body = _extract(app_client, items, rows=1)
    with Sess() as s:
        call = s.execute(
            select(LLMCall).where(LLMCall.purpose == "extract.capabilities")
        ).scalar_one()
        assert call.prompt_version == "v3.2"
        call.prompt_version = "v2"
        s.commit()
    assert body["extraction_flags"]["category_off_list"] == 1
    after = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert after["extraction_flags"] is None


def test_each_list_reads_its_own_extractions_prompt_version(app_client) -> None:  # noqa: F811
    """Review finding F5 on PR #955: the version is the one the LIST's own
    extraction ran, never the latest call. A later v3.2 extraction on another
    service leaves an earlier list's v2 call where it was."""
    items = [_example(0, category="EDR", confidence_pct=70)]
    c, Sess, h, _, first = _extract(app_client, items, rows=1)
    with Sess() as s:
        call = s.execute(
            select(LLMCall).where(LLMCall.purpose == "extract.capabilities")
        ).scalar_one()
        call.prompt_version = "v2"
        s.commit()

    # A second, later extraction on a different service and list, under v3.2.
    bearer = h["Authorization"].split()[1]
    svc2 = c.post("/tech-debt/services", headers=h, json={"title": "y"}).json()["id"]
    art2 = _upload_csv(c, bearer, "y.csv", b"name\nrow0\n")
    r = c.post(
        f"/tech-debt/services/{svc2}/capability-lists/extract",
        headers=h,
        json={"artifact_id": art2, "serves": "offline"},
    )
    assert r.status_code == 202, r.text
    assert get_run(c, r.json()["run_id"], h)["status"] == "completed"
    with Sess() as s:
        versions = sorted(
            v
            for (v,) in s.execute(
                select(LLMCall.prompt_version).where(LLMCall.purpose == "extract.capabilities")
            )
        )
    assert versions == ["v2", "v3.2"]

    second = c.get(f"/tech-debt/services/{svc2}/capability-lists/latest", headers=h).json()
    assert second["extraction_flags"]["category_off_list"] == 1
    again = c.get(
        f"/tech-debt/services/{first['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert again["extraction_flags"] is None


def test_a_bundle_part_a_consultant_adds_is_not_counted_as_the_ais(
    app_client,  # noqa: F811
) -> None:
    """Review finding F1 on PR #955: the components route copies the bundle's
    `source_artifact_id` onto each part, with a category the consultant typed.
    A part is the consultant's row, not one the AI returned, so it is not
    counted."""
    items = [_example(0, name="Microsoft 365 E5", category="Productivity/Content")]
    c, _, h, _, body = _extract(app_client, items, rows=1)
    assert body["extraction_flags"] == ZERO  # APPEAR: measured, and clean
    (bundle,) = body["items"]
    r = c.post(
        f"/tech-debt/capability-items/{bundle['id']}/components",
        headers=h,
        json={"components": [{"name": "Defender for Endpoint", "category": "EDR"}]},
    )
    assert r.status_code in (200, 201), r.text
    after = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    part = next(i for i in after["items"] if i["name"] == "Defender for Endpoint")
    assert part["category"] == "EDR"
    assert part["source_artifact_id"] == bundle["source_artifact_id"]
    assert after["extraction_flags"] == ZERO


def test_a_human_included_row_is_not_counted_as_the_ais(app_client) -> None:  # noqa: F811
    """The copy says the row "came back" from the AI; a consultant's own row
    did not, so its free-typed category is not counted."""
    items = [_example(0, name="Okta", category="IAM/PAM")]
    c, _, h, _, body = _extract(app_client, items, rows=2)
    assert len(body["excluded_rows"]) == 1
    r = c.post(
        f"/tech-debt/capability-lists/{body['id']}/excluded-rows/1/include",
        headers=h,
        json={"name": "Legacy tool", "category": "Mainframe"},
    )
    assert r.status_code in (200, 201), r.text
    after = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert any(i["category"] == "Mainframe" for i in after["items"])
    assert after["extraction_flags"] == ZERO


def test_a_list_whose_source_link_is_gone_is_not_measured(app_client) -> None:  # noqa: F811
    """Advisor ruling (issue 736, comment 6068587667, item 3b): the counts read
    only the AI's rows, which are the rows linked to the source document. When
    that link is null, the AI's rows can no longer be told apart, so the list
    reports `extraction_flags` null ("not measured"), never a smaller count.
    No current writer produces that state (no route deletes an Artifact; the
    link is cleared only by ON DELETE SET NULL), so the setup writes it
    directly. The guard is a ratchet against an artifact delete route."""
    from app.models.capability import CapabilityItem

    items = [_example(0, category="EDR", confidence_pct=70), _example(1, name="")]
    c, Sess, h, _, body = _extract(app_client, items, rows=2)
    # APPEAR first: linked, the counts are there.
    assert body["extraction_flags"] == {
        **ZERO,
        "name_missing": 1,
        "confidence_off_scale": 1,
        "category_off_list": 1,
    }
    with Sess() as s:
        for it in s.execute(select(CapabilityItem)).scalars():
            it.source_artifact_id = None
        s.commit()
    after = c.get(
        f"/tech-debt/services/{body['service_id']}/capability-lists/latest", headers=h
    ).json()
    assert len(after["items"]) == 2
    assert after["extraction_flags"] is None


# --- 4. the offline fixture follows v3.2 ---------------------------------------

#: s4's inventory, plus a total line, a retired row with no cost, a planned
#: security row, and a retired row that still carries a cost at an index the
#: fixture's cycle calls non-security (every fourth row). Columns are what a
#: client sends.
FIXTURE_CSV = (
    "name,vendor,category,annual_cost_usd,license_count,status\n"
    "CrowdStrike Falcon,CrowdStrike,EDR,120000,500,active\n"  # 0
    "Splunk Enterprise,Splunk,SIEM,200000,100,active\n"  # 1
    "Okta,Okta,IAM,60000,500,active\n"  # 2
    "Tenable Nessus,Tenable,VulnScan,40000,50,active\n"  # 3
    "Total,,,420000,,\n"  # 4: a total line
    "Symantec Endpoint,Broadcom,EDR,,,retired 2025\n"  # 5: retired, no cost
    "Falcon Identity,CrowdStrike,ITDR,40000,0,planned FY27\n"  # 6: planned, security
    "McAfee ePO,Trellix,EDR,15000,,decommissioned\n"  # 7: retired, still a cost
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
    return c.get(f"/tech-debt/services/{svc}/capability-lists/latest", headers=h).json()


def test_the_fixture_uses_only_v32_values(app_client) -> None:  # noqa: F811
    body = _fixture_extract(app_client)
    items = body["items"]
    assert items, "the fixture returned nothing"
    assert {i["confidence_pct"] for i in items} <= V32_CONFIDENCE
    assert {i["category"] for i in items} <= set(V32_CATEGORIES) | {None}
    for i in items:
        if i["confidence_pct"] == 60:
            assert i["notes"], f"{i['name']}: a 60 with no note saying why"
        # Notes are plain facts about the row, never an instruction to a reviewer.
        assert not re.search(r"confirm|review|approv", i["notes"] or "", re.I), i
    # A known category that is not on the list is null, with the real one noted.
    nessus = next(i for i in items if i["name"] == "Tenable Nessus")
    assert nessus["category"] is None
    assert "VulnScan" in nessus["notes"]
    # On the list: the client's own word, as the list writes it.
    by_name = {i["name"]: i for i in items}
    assert by_name["CrowdStrike Falcon"]["category"] == "EDR/XDR"
    assert by_name["Splunk Enterprise"]["category"] == "SIEM/SOAR"
    assert by_name["Okta"]["category"] == "IAM/PAM"
    assert body["extraction_flags"] == ZERO
    # s4 depends on exactly one of its four rows reading "AI 60%".
    assert [by_name[n]["confidence_pct"] for n in ("CrowdStrike Falcon",)] == [60]
    assert (
        sum(
            1
            for n in ("CrowdStrike Falcon", "Splunk Enterprise", "Okta", "Tenable Nessus")
            if by_name[n]["confidence_pct"] == 60
        )
        == 1
    )


def test_the_fixture_skips_a_total_line_and_a_retired_row_with_no_cost(
    app_client,  # noqa: F811
) -> None:
    body = _fixture_extract(app_client)
    names = {i["name"] for i in body["items"]}
    assert "Total" not in names
    assert "Symantec Endpoint" not in names
    assert sorted(e["index"] for e in body["excluded_rows"]) == [4, 5]
    # Retired but still carrying a cost: kept, its status noted, confidence 60.
    mcafee = next(i for i in body["items"] if i["name"] == "McAfee ePO")
    assert mcafee["confidence_pct"] == 60
    assert mcafee["notes"].startswith("Status: decommissioned.")


def test_the_fixture_marks_a_planned_security_tool_as_v32_says(app_client) -> None:  # noqa: F811
    body = _fixture_extract(app_client)
    planned = next(i for i in body["items"] if i["name"] == "Falcon Identity")
    assert planned["security_related"] is False
    assert planned["security_functions"] == []
    # v3.2: "Begin `notes` with exactly `Security tool not in use:` followed by
    # the status as the row states it".
    assert planned["notes"].startswith(f"{PREFIX} planned FY27.")
    assert planned["confidence_pct"] == 60
    # The sign-off queue reads it as a not-in-use tool (#845).
    assert planned["signoff_kind"] == "not_in_use"


def test_the_fixture_demo_items_follow_v32(app_client) -> None:  # noqa: F811
    """The items the fixture returns for a payload with no rows."""
    from app.ai.fixtures import build_runtime_provider

    out = build_runtime_provider().complete("", {"__purpose__": "extract.capabilities"})
    items = json.loads(out.content)["items"]
    assert [i["category"] for i in items] == ["EDR/XDR", "SIEM/SOAR", "IAM/PAM"]
    assert {i["confidence_pct"] for i in items} <= V32_CONFIDENCE
    for i in items:
        assert not re.search(r"confirm|review|approv|fixture", i["notes"] or "", re.I), i
