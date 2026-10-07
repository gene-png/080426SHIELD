"""A Tech Debt tool marked `cut` is a PLANNED RETIREMENT on every ATT&CK surface (#686).

Gene's decision (2026-09-26, D-105): the tool still counts toward coverage --
it is still deployed -- and every surface that counts it says "planned
retirement". The coordinator's verdicts on the join: "the consolidation
plan" is each Tech Debt service's LATEST approved or released list, and only it
votes (#787 review, F1); a cited name on no service's latest plan -- a draft
only, an older version only, or nowhere -- is "retirement status unknown"; and
a client with no plan at all gets no marks and no counts.

ONE WORLD carries every state, so the per-surface assertions cannot pass on a
world that lacks the case:

    Splunk Enterprise   approved list, cut       -> planned retirement
    Legacy AV           approved list, cut       -> planned retirement
    CrowdStrike Falcon  approved list, keep      -> not retiring
    Okta                approved list, undecided -> not retiring
    Tenable             DRAFT list only, cut     -> unknown (on no latest plan)
    Homegrown Script    on no list (free text)   -> unknown

Expected strings are the coordinator-approved copy on #686, written out here,
never imported from `app/attack/retirement.py`.
"""

from __future__ import annotations

import io
import uuid

import pytest
from sqlalchemy import update

from app.models.capability import (
    CapabilityDisposition,
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
)
from app.models.service import Service, ServiceKind
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit

CUT = CapabilityDisposition.CUT
KEEP = CapabilityDisposition.KEEP

#: (status, detection tools) per scored row, in order.
ROWS = [
    ("covered", ["Splunk Enterprise", "CrowdStrike Falcon"]),  # cites a retiring tool
    ("covered", ["Legacy AV"]),  # relies on one alone
    ("partial", ["Okta"]),
    ("covered", ["Tenable"]),
    ("covered", ["Homegrown Script"]),
]

PLANNED_SENTENCE = (
    "2 of the 5 covered or partial techniques cite a tool marked for planned "
    "retirement; 1 relies on such tools alone."
)
UNKNOWN_SENTENCE = "Retirement status could not be determined for 2 cited tools."


def _tech_debt_list(
    Sess,
    client_id: str,
    opened_by: str,
    *,
    status: CapabilityListStatus,
    items: list[tuple[str, CapabilityDisposition | None]],
) -> dict[str, uuid.UUID]:
    """A Tech Debt service and list, written straight to the database: the
    world, not the step under test. An approved list carries the membership
    snapshot its approve route would have written."""
    with Sess() as s:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            title="Tech Debt",
            client_id=uuid.UUID(client_id),
            opened_by=uuid.UUID(opened_by),
        )
        s.add(svc)
        s.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=status)
        s.add(cl)
        s.flush()
        ids: dict[str, uuid.UUID] = {}
        for name, disposition in items:
            it = CapabilityItem(
                capability_list_id=cl.id,
                name=name,
                security_related=True,
                disposition=disposition,
            )
            s.add(it)
            s.flush()
            ids[name] = it.id
        if status in (CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED):
            cl.approved_membership = [
                {"item_id": str(i), "name": n, "vendor": None} for n, i in ids.items()
            ]
        s.commit()
        return ids


def _all_three(tools: list[str]) -> dict:
    """#554 R3: the same tools in Detect, Prevent and Respond, so a covered row
    computes to Covered. The tool NAMES, which this file's marks and counts read,
    are unchanged."""
    return {"detection_tools": tools, "prevention_tools": tools, "response_tools": tools}


def _world(env, *, with_plan: bool = True):  # noqa: F811
    """Admin + client, the Tech Debt plan, and an ATT&CK assessment whose
    scored rows cite the tools above. Returns everything a surface test needs."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    ids: dict[str, uuid.UUID] = {}
    if with_plan:
        ids = _tech_debt_list(
            Sess,
            client_id,
            admin["user"]["id"],
            status=CapabilityListStatus.APPROVED,
            items=[
                ("Splunk Enterprise", CUT),
                ("Legacy AV", CUT),
                ("CrowdStrike Falcon", KEEP),
                ("Okta", None),
            ],
        )
        _tech_debt_list(
            Sess,
            client_id,
            admin["user"]["id"],
            status=CapabilityListStatus.DRAFT,
            # #851: "Homegrown Script" sits on the DRAFT list too. A DRAFT list
            # feeds the citable subset (`_client_capability_membership`), so
            # approve accepts the row; a draft does not vote on retirement, so the
            # tool stays UNKNOWN, which is what this file tests.
            items=[("Tenable", CUT), ("Homegrown Script", None)],
        )
    svc, a = _service_and_assessment(c, bearer)
    rows = standalone_rows(a["coverage"], len(ROWS))
    for row, (st, tools) in zip(rows, ROWS, strict=True):
        # #554 R3: a covered row names its tools in all three lists, so its
        # computed status is the one this world sets (class B).
        body: dict = {
            "status": st,
            **(_all_three(tools) if st == "covered" else {"detection_tools": tools}),
        }
        if st == "partial":
            # Approve refuses a Partial with no reason (#554).
            body["reason_code"] = "reach_limited"
        r = c.patch(f"/attack/coverage/{row['id']}", headers=_auth(bearer), json=body)
        assert r.status_code == 200, r.text
    return c, Sess, bearer, client, client_id, svc, a, ids


def _approve_finalize(c, bearer: str, svc: str, a: dict) -> dict:
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    return fin.json()


def _download(c, bearer: str, artifact_id: str) -> bytes:
    r = c.get(f"/artifacts/{artifact_id}/download", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    return r.content


def _xlsx_tool_cells(raw: bytes) -> set[str]:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(raw))["Coverage"]
    col = [c.value for c in ws[1]].index("Detection tools") + 1
    return {
        str(ws.cell(row=r, column=col).value)
        for r in range(2, ws.max_row + 1)
        if ws.cell(row=r, column=col).value
    }


def _xlsx_summary_labels(raw: bytes) -> dict:
    from openpyxl import load_workbook

    ws = load_workbook(io.BytesIO(raw))["Heatmap Summary"]
    return {r[0].value: r[1].value for r in ws.iter_rows(max_row=20) if r and r[0].value}


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    return " ".join(
        " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages).split()
    )


def _docx_text(raw: bytes) -> str:
    from docx import Document

    return " ".join(" ".join(p.text for p in Document(io.BytesIO(raw)).paragraphs).split())


# --- the deliverable ----------------------------------------------------------


def test_the_xlsx_marks_each_tool_by_its_state(env) -> None:  # noqa: F811
    c, _Sess, bearer, *_rest, svc, a, _ids = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert {
        "Splunk Enterprise (planned retirement); CrowdStrike Falcon",
        "Legacy AV (planned retirement)",
        "Okta",
        "Tenable (retirement status unknown)",
        "Homegrown Script (retirement status unknown)",
    } <= cells, cells


def test_the_xlsx_legend_explains_both_marks(env) -> None:  # noqa: F811
    c, _Sess, bearer, *_rest, svc, a, _ids = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    labels = _xlsx_summary_labels(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert labels.get("Tools marked (planned retirement)") == (
        "Marked Cut, or Cut, covered by another tool, in the Tech Debt "
        "consolidation plan. Still deployed, so still counted toward coverage; "
        "this coverage drops when the tool is retired."
    ), labels
    assert labels.get("Tools marked (retirement status unknown)") == (
        "Could not be matched to one Tech Debt capability, so whether it is planned "
        "for retirement is not known."
    ), labels


def test_the_pdf_docx_and_summary_state_the_counts(env) -> None:  # noqa: F811
    c, _Sess, bearer, *_rest, svc, a, _ids = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    pdf = _pdf_text(_download(c, bearer, fin["pdf_artifact_id"]))
    docx = _docx_text(_download(c, bearer, fin["docx_artifact_id"]))
    for name, text in (("pdf", pdf), ("docx", docx), ("summary", fin["summary"])):
        assert PLANNED_SENTENCE in text, f"{name}: {text[:2000]!r}"
        assert UNKNOWN_SENTENCE in text, f"{name}: {text[:2000]!r}"


def test_the_deliverable_keeps_the_disposition_it_was_finalized_with(env) -> None:  # noqa: F811
    """Q2: the document is rendered at finalize. A disposition changed after
    that must not change the stored document."""
    c, Sess, bearer, *_rest, svc, a, ids = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    with Sess() as s:
        s.execute(
            update(CapabilityItem)
            .where(CapabilityItem.id == ids["Legacy AV"])
            .values(disposition=KEEP)
        )
        s.commit()
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert "Legacy AV (planned retirement)" in cells, cells


def test_a_client_with_no_consolidation_plan_gets_no_marks_and_no_counts(env) -> None:  # noqa: F811
    """No approved or released Tech Debt list: nothing CAN be cut, so nothing
    is marked and "could not be determined" is not printed either."""
    c, _Sess, bearer, *_rest, svc, a, _ids = _world(env, with_plan=False)
    fin = _approve_finalize(c, bearer, svc, a)
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert "Homegrown Script" in cells, cells
    assert not any("retirement" in x for x in cells), cells
    pdf = _pdf_text(_download(c, bearer, fin["pdf_artifact_id"]))
    for text in (pdf, fin["summary"]):
        assert "retirement" not in text.lower(), text[:2000]


def test_a_cut_on_a_draft_list_alone_is_not_a_plan(env) -> None:  # noqa: F811
    """Q1: a client whose only Tech Debt list is a DRAFT has no plan, even with
    a tool cut on it."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    _tech_debt_list(
        Sess,
        client["user"]["client_id"],
        admin["user"]["id"],
        status=CapabilityListStatus.DRAFT,
        items=[("Tenable", CUT)],
    )
    svc, a = _service_and_assessment(c, bearer)
    row = standalone_rows(a["coverage"], 1)[0]
    c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Tenable"])},
    )
    fin = _approve_finalize(c, bearer, svc, a)
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    assert "Tenable" in cells, cells
    assert "retirement" not in fin["summary"].lower(), fin["summary"]


# --- the client dashboard -------------------------------------------------------


def test_the_client_dashboard_carries_the_marks_and_the_counts(env) -> None:  # noqa: F811
    c, Sess, bearer, client, client_id, svc, a, ids = _world(env)
    fin = _approve_finalize(c, bearer, svc, a)
    rel = c.post(f"/attack/deliverables/{fin['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    body = dash.json()
    assert body["tool_retirement"] == {
        "Splunk Enterprise": "planned_retirement",
        "Legacy AV": "planned_retirement",
        "Tenable": "unknown",
        "Homegrown Script": "unknown",
    }, body.get("tool_retirement")
    assert body["retirement_notes"] == [PLANNED_SENTENCE, UNKNOWN_SENTENCE], body.get(
        "retirement_notes"
    )

    # Q2: the dashboard reads the CURRENT plan, and says so on the web side.
    with Sess() as s:
        s.execute(
            update(CapabilityItem)
            .where(CapabilityItem.id == ids["Legacy AV"])
            .values(disposition=KEEP)
        )
        s.commit()
    after = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()
    assert "Legacy AV" not in after["tool_retirement"], after["tool_retirement"]


def test_the_dashboard_omits_both_keys_with_no_plan(env) -> None:  # noqa: F811
    """Additive keys, OMITTED rather than null or empty when there is no plan,
    so a response for a client without Tech Debt is what it was before #686."""
    c, _Sess, bearer, client, client_id, svc, a, _ids = _world(env, with_plan=False)
    fin = _approve_finalize(c, bearer, svc, a)
    assert (
        c.post(f"/attack/deliverables/{fin['id']}/release", headers=_auth(bearer)).status_code
        == 200
    )
    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()
    assert "techniques" in body, body
    assert "tool_retirement" not in body and "retirement_notes" not in body, sorted(body)


# --- the admin workspace ----------------------------------------------------------


def test_the_admin_assessment_carries_the_marks(env) -> None:  # noqa: F811
    c, _Sess, bearer, *_rest, svc, _a, _ids = _world(env)
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer))
    assert latest.status_code == 200, latest.text
    assert latest.json()["tool_retirement"] == {
        "Splunk Enterprise": "planned_retirement",
        "Legacy AV": "planned_retirement",
        "Tenable": "unknown",
        "Homegrown Script": "unknown",
    }


# --- the join's other unknowns, through the same index the surfaces use --------


def test_two_services_whose_plans_disagree_are_unknown_not_a_guess(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    # TWO Tech Debt SERVICES (`_tech_debt_list` opens a service per call), each
    # with its own latest plan. The union rule applies across services; two
    # VERSIONS of one service are the next tests, where the latest wins.
    for disposition in (CUT, KEEP):
        _tech_debt_list(
            Sess,
            client["user"]["client_id"],
            admin["user"]["id"],
            status=CapabilityListStatus.APPROVED,
            items=[("Splunk Enterprise", disposition)],
        )
    svc, _a = _service_and_assessment(c, bearer)
    a = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    row = standalone_rows(a["coverage"], 1)[0]
    c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Splunk Enterprise"])},
    )
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    assert latest["tool_retirement"] == {"Splunk Enterprise": "unknown"}


def test_a_snapshot_entry_whose_item_is_gone_is_unknown(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    ids = _tech_debt_list(
        Sess,
        client["user"]["client_id"],
        admin["user"]["id"],
        status=CapabilityListStatus.APPROVED,
        items=[("Splunk Enterprise", CUT)],
    )
    with Sess() as s:
        s.delete(s.get(CapabilityItem, ids["Splunk Enterprise"]))
        s.commit()
    svc, a = _service_and_assessment(c, bearer)
    row = standalone_rows(a["coverage"], 1)[0]
    c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Splunk Enterprise"])},
    )
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    assert latest["tool_retirement"] == {"Splunk Enterprise": "unknown"}


def test_a_renamed_item_still_joins_through_the_snapshot(env) -> None:  # noqa: F811
    """A rename after approval: the snapshot keeps the old name and the item id,
    so the cited (old) name still reaches the live disposition."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    ids = _tech_debt_list(
        Sess,
        client["user"]["client_id"],
        admin["user"]["id"],
        status=CapabilityListStatus.APPROVED,
        items=[("Splunk Enterprise", CUT)],
    )
    with Sess() as s:
        s.execute(
            update(CapabilityItem)
            .where(CapabilityItem.id == ids["Splunk Enterprise"])
            .values(name="Splunk Cloud")
        )
        s.commit()
    svc, a = _service_and_assessment(c, bearer)
    row = standalone_rows(a["coverage"], 1)[0]
    c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Splunk Enterprise"])},
    )
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    assert latest["tool_retirement"] == {"Splunk Enterprise": "planned_retirement"}


# --- the count sentence's numbers (#787 review, F3 and F4) ----------------------


def _family() -> tuple[str, list[str]]:
    """The catalog parent with the fewest sub-techniques, and those sub-techniques.

    Derived from the catalog's own parent links, NOT from `app.attack.parents`,
    so the setup does not agree with the code under test by construction.
    """
    from app.attack.catalog import TECHNIQUES

    kids: dict[str, list[str]] = {}
    for t in TECHNIQUES:
        if t.parent_id is not None:
            kids.setdefault(t.parent_id, []).append(t.id)
    parent = min(kids, key=lambda p: (len(kids[p]), p))
    return parent, sorted(kids[parent])


def _plan_with_legacy_av_cut(env):  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    _tech_debt_list(
        Sess,
        client["user"]["client_id"],
        admin["user"]["id"],
        status=CapabilityListStatus.APPROVED,
        items=[("Legacy AV", CUT)],
    )
    return c, bearer


def test_one_technique_reads_in_the_singular(env) -> None:  # noqa: F811
    """F3: "1 of the 1 covered or partial technique cites ...; 1 relies ...",
    through finalize, not only through a hand-written web string."""
    c, bearer = _plan_with_legacy_av_cut(env)
    svc, a = _service_and_assessment(c, bearer)
    row = standalone_rows(a["coverage"], 1)[0]
    r = c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Legacy AV"])},
    )
    assert r.status_code == 200, r.text
    fin = _approve_finalize(c, bearer, svc, a)
    assert (
        "1 of the 1 covered or partial technique cites a tool marked for planned "
        "retirement; 1 relies on such tools alone."
    ) in fin["summary"], fin["summary"]


def test_a_computed_parent_counts_on_both_sides_of_the_sentence(env) -> None:  # noqa: F811
    """F4: M is the rollup's covered + partial, which includes a computed parent
    (D-094). N must count over the SAME population, so a parent covered by
    children that cite a retiring tool counts in N too -- its coverage drops
    with theirs. Before, N skipped parents while M included them: a ratio over
    two populations."""
    c, bearer = _plan_with_legacy_av_cut(env)
    parent, children = _family()
    svc, a = _service_and_assessment(c, bearer)
    by_code = {row["technique_code"]: row for row in a["coverage"]}
    for code in children:
        r = c.patch(
            f"/attack/coverage/{by_code[code]['id']}",
            headers=_auth(bearer),
            json={"status": "covered", **_all_three(["Legacy AV"])},
        )
        assert r.status_code == 200, r.text
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    statuses = {row["technique_code"]: row["status"] for row in latest["coverage"]}
    assert statuses[parent] == "covered", (parent, statuses[parent])
    fin = _approve_finalize(c, bearer, svc, a)
    n = len(children) + 1  # every child, and the parent they cover
    assert (
        f"{n} of the {n} covered or partial techniques cite a tool marked for planned "
        f"retirement; {n} rely on such tools alone."
    ) in fin["summary"], fin["summary"]


# --- two VERSIONS of one Tech Debt service: the latest plan wins (#787, F1) -----


def _one_service_two_versions(
    env,  # noqa: F811
    v1: list[tuple[str, CapabilityDisposition | None]],
    v2: list[tuple[str, CapabilityDisposition | None]],
    *,
    v2_status: CapabilityListStatus = CapabilityListStatus.APPROVED,
):
    """One Tech Debt service with an APPROVED v1 and a v2 in `v2_status` (by
    default APPROVED, the state each extraction leaves behind), and an ATT&CK
    service citing Splunk."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    with Sess() as s:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            title="Tech Debt",
            client_id=uuid.UUID(client_id),
            opened_by=uuid.UUID(admin["user"]["id"]),
        )
        s.add(svc)
        s.flush()
        for version, items, status in (
            (1, v1, CapabilityListStatus.APPROVED),
            (2, v2, v2_status),
        ):
            cl = CapabilityList(service_id=svc.id, version=version, status=status)
            s.add(cl)
            s.flush()
            entries = []
            for name, disposition in items:
                it = CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    security_related=True,
                    disposition=disposition,
                )
                s.add(it)
                s.flush()
                entries.append({"item_id": str(it.id), "name": name, "vendor": None})
            if status in (CapabilityListStatus.APPROVED, CapabilityListStatus.RELEASED):
                cl.approved_membership = entries
        s.commit()
    asvc, a = _service_and_assessment(c, bearer)
    row = standalone_rows(a["coverage"], 1)[0]
    r = c.patch(
        f"/attack/coverage/{row['id']}",
        headers=_auth(bearer),
        json={"status": "covered", **_all_three(["Splunk Enterprise"])},
    )
    assert r.status_code == 200, r.text
    fin = _approve_finalize(c, bearer, asvc, a)
    assert (
        c.post(f"/attack/deliverables/{fin['id']}/release", headers=_auth(bearer)).status_code
        == 200
    )
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{asvc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    cells = _xlsx_tool_cells(_download(c, bearer, fin["xlsx_artifact_id"]))
    return fin, dash.json(), cells


def test_an_older_versions_cut_is_outvoted_by_the_latest_keep(env) -> None:  # noqa: F811
    """v1 cut, v2 keep: the current plan keeps the tool. Before F1 both versions
    voted, and the disagreement read UNKNOWN."""
    fin, dash, cells = _one_service_two_versions(
        env, v1=[("Splunk Enterprise", CUT)], v2=[("Splunk Enterprise", KEEP)]
    )
    assert "Splunk Enterprise" in cells, cells
    assert not any("retirement" in x for x in cells), cells
    assert dash["tool_retirement"] == {}, dash["tool_retirement"]
    assert dash["retirement_notes"] == [], dash["retirement_notes"]
    assert "retirement" not in fin["summary"].lower(), fin["summary"]


def test_a_tool_dropped_from_the_latest_version_is_unknown_not_retiring(env) -> None:  # noqa: F811
    """v1 cut, absent from v2: the current plan does not list it. Before F1 the
    stale cut read PLANNED beside "Retirement labels reflect the current
    consolidation plan." -- which was then false."""
    fin, dash, cells = _one_service_two_versions(
        env, v1=[("Splunk Enterprise", CUT)], v2=[("Okta", KEEP)]
    )
    assert "Splunk Enterprise (retirement status unknown)" in cells, cells
    assert dash["tool_retirement"] == {"Splunk Enterprise": "unknown"}, dash["tool_retirement"]
    assert dash["retirement_notes"] == [
        "Retirement status could not be determined for 1 cited tool."
    ], dash["retirement_notes"]
    assert "planned retirement" not in fin["summary"], fin["summary"]


@pytest.mark.parametrize("v2_status", [CapabilityListStatus.DRAFT, CapabilityListStatus.DISCARDED])
def test_a_newer_unapproved_version_does_not_unseat_the_approved_plan(  # noqa: F811
    env, v2_status  # noqa: F811
) -> None:
    """#787 round 2, N1: v1 APPROVED with Splunk cut, v2 a DRAFT or DISCARDED
    with it kept. The plan is the latest APPROVED or RELEASED version, so v1
    still decides: the status is judged BEFORE taking the highest version."""
    fin, dash, cells = _one_service_two_versions(
        env,
        v1=[("Splunk Enterprise", CUT)],
        v2=[("Splunk Enterprise", KEEP)],
        v2_status=v2_status,
    )
    assert "Splunk Enterprise (planned retirement)" in cells, cells
    assert dash["tool_retirement"] == {"Splunk Enterprise": "planned_retirement"}, dash[
        "tool_retirement"
    ]


def test_a_computed_parent_rests_only_on_the_children_that_make_its_coverage(  # noqa: F811
    env,  # noqa: F811
) -> None:
    """#787 round 2, N2: a parent's coverage is made by its covered and partial
    children. One child covered by a retiring tool and one GAP child carrying a
    kept tool make the parent PARTIAL, resting on the retiring tool alone; the
    gap child's tool is not evidence for it."""
    from app.attack.catalog import TECHNIQUES

    kids: dict[str, list[str]] = {}
    for t in TECHNIQUES:
        if t.parent_id is not None:
            kids.setdefault(t.parent_id, []).append(t.id)
    parent = min((p for p in kids if len(kids[p]) >= 2), key=lambda p: (len(kids[p]), p))
    first, *rest = sorted(kids[parent])

    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    _tech_debt_list(
        Sess,
        client["user"]["client_id"],
        admin["user"]["id"],
        status=CapabilityListStatus.APPROVED,
        items=[("Legacy AV", CUT), ("CrowdStrike Falcon", KEEP)],
    )
    svc, a = _service_and_assessment(c, bearer)
    by_code = {row["technique_code"]: row for row in a["coverage"]}
    writes = [(first, "covered", ["Legacy AV"])] + [
        (code, "gap", ["CrowdStrike Falcon"]) for code in rest
    ]
    for code, st, tools in writes:
        # A gap row CAN carry tools: the PATCH writes status and tool lists
        # independently, so this state is reachable today.
        r = c.patch(
            f"/attack/coverage/{by_code[code]['id']}",
            headers=_auth(bearer),
            json={"status": st, "detection_tools": tools},
        )
        assert r.status_code == 200, r.text
        assert r.json()["detection_tools"] == tools, r.json()
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer)).json()
    assert {row["technique_code"]: row["status"] for row in latest["coverage"]}[parent] == "partial"
    # #554 R3 (C1, ruled by the advisor 01:05Z): a GAP child carrying a tool is
    # this test's subject, and under R3 that row computes to Partial. Approve,
    # then stamp status_rules=1 -- the reachable state of an assessment approved
    # before R3 -- then finalize, so the document renders the stored statuses.
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    from app.models.attack_assessment import AttackAssessment

    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(a["id"]))
            .values(status_rules=1)
        )
        s.commit()
    r = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert r.status_code in (200, 201), r.text
    fin = r.json()
    # The covered child and the partial parent: both rest on Legacy AV alone.
    assert (
        "2 of the 2 covered or partial techniques cite a tool marked for planned "
        "retirement; 2 rely on such tools alone."
    ) in fin["summary"], fin["summary"]
