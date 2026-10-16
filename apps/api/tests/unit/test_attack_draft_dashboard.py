"""#1178: an admin-only draft dashboard after the ATT&CK AI run, kept for
comparison after review.

`GET /attack/services/{id}/draft-dashboard` renders the client dashboard's
body from the last COMPLETED mitre_map run on the service's current
assessment, as that run left the rows (its stored `result.coverage`), never
from the rows as they are now. So a consultant's later edit does not move the
draft, and a re-run replaces it.

Every test drives the endpoints. The provider answers in the mitre_map
prompt's own keys for the codes a test chooses; expected values come from what
the test answered and edited, never from the module under test.
"""

from __future__ import annotations

import json

import pytest

from app.ai.llm import LLMResponse
from tests._ai_runs import get_run, start_run
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _admin,
    _seed_tech_debt_tools,
    app_client,
)

pytestmark = pytest.mark.unit


def _answer_only(provider, statuses: dict[str, str]) -> None:
    """The provider names only the codes in `statuses`, citing nothing."""

    def _answer(payload: dict) -> LLMResponse:
        asked = payload.get("technique_codes") or []
        entries = [
            {
                "technique_code": code,
                "status": statuses[code],
                "detection_tools": [],
                "prevention_tools": [],
                "response_tools": [],
                "rationale": "From the run.",
            }
            for code in asked
            if code in statuses
        ]
        return LLMResponse(json.dumps({"techniques": entries}))

    provider.register("mitre_map", _answer)


def _setup(app_client):  # noqa: F811
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], ["Tool A"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    coverage = c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"]
    return c, provider, h, svc_id, standalone_rows(coverage, 2)


def _run(c, h, svc_id) -> dict:
    url = f"/attack/services/{svc_id}/run-ai"
    run = get_run(c, start_run(c, url, h)["run_id"], h)
    assert run["status"] == "completed", run
    return run


def _draft(c, h, svc_id):
    return c.get(f"/attack/services/{svc_id}/draft-dashboard", headers=h)


def _statuses(body: dict) -> dict[str, str]:
    return {t["code"]: t["status"] for t in body["techniques"]}


def test_the_draft_shows_the_assessment_as_the_run_left_it(app_client) -> None:  # noqa: F811
    c, provider, h, svc_id, rows = _setup(app_client)
    a, b = rows[0]["technique_code"], rows[1]["technique_code"]
    _answer_only(provider, {a: "gap", b: "gap"})
    run = _run(c, h, svc_id)

    r = _draft(c, h, svc_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["run_id"] == run["id"]
    assert body["run_finished_at"] is not None
    assert _statuses(body) == {a: "gap", b: "gap"}
    assert body["rollup"]["gap"] == 2
    # No release record stands behind a draft, so it claims none.
    assert "released_at" not in body
    assert "deliverable_version" not in body


def test_an_edit_after_the_run_does_not_move_the_draft(app_client) -> None:  # noqa: F811
    """Kept for comparison: the draft is the run's output, not today's rows.

    The edit is to the rationale, which the dashboard shows as stored. A status
    edit would prove nothing here: these rows' statuses are computed from their
    tool lists, which are empty, so any stored status reads as a gap."""
    c, provider, h, svc_id, rows = _setup(app_client)
    a, b = rows[0]["technique_code"], rows[1]["technique_code"]
    _answer_only(provider, {a: "gap", b: "gap"})
    _run(c, h, svc_id)

    edit = c.patch(
        f"/attack/coverage/{rows[0]['id']}", headers=h, json={"rationale": "Edited after."}
    )
    assert edit.status_code == 200, edit.text
    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    (now,) = [t for t in latest["coverage"] if t["technique_code"] == a]
    assert now["rationale"] == "Edited after.", "setup: the edit must have landed"

    body = _draft(c, h, svc_id).json()
    assert {t["code"]: t["rationale"] for t in body["techniques"]} == {
        a: "From the run.",
        b: "From the run.",
    }


def test_a_rerun_replaces_the_draft(app_client) -> None:  # noqa: F811
    c, provider, h, svc_id, rows = _setup(app_client)
    a, b = rows[0]["technique_code"], rows[1]["technique_code"]
    _answer_only(provider, {a: "gap"})
    first = _run(c, h, svc_id)
    assert _draft(c, h, svc_id).json()["run_id"] == first["id"]

    _answer_only(provider, {b: "gap"})
    second = _run(c, h, svc_id)
    body = _draft(c, h, svc_id).json()
    assert body["run_id"] == second["id"]
    # The second run left `a` as the first run wrote it, and wrote `b`.
    assert _statuses(body) == {a: "gap", b: "gap"}


def test_no_completed_run_is_a_typed_404(app_client) -> None:  # noqa: F811
    c, provider, h, svc_id, rows = _setup(app_client)
    r = _draft(c, h, svc_id)
    assert r.status_code == 404, r.text
    assert r.json()["error"]["reason"] == "attack_no_draft"
    # D-1, approved verbatim (#736 6216024281).
    assert r.json()["error"]["message"] == "No completed AI run yet, so there is no draft to show."


def test_a_client_user_cannot_read_the_draft(app_client) -> None:  # noqa: F811
    """Admin-only, enforced by the server, not by hiding a link."""
    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    _run(c, h, svc_id)
    assert _draft(c, h, svc_id).status_code == 200, "setup: the admin can read it"

    client = c.post(
        "/auth/register",
        json={
            "email": "client@example.com",
            "password": "correct horse battery staple!",
            "display_name": "client",
        },
    )
    assert client.status_code == 201, client.text
    body = client.json()
    assert body["user"]["role"] == "client", "setup: the second user must be a client"
    ch = {
        "Authorization": f"Bearer {body['tokens']['access_token']}",
        "X-Client-Id": body["user"]["client_id"],
    }
    r = c.get(f"/attack/services/{svc_id}/draft-dashboard", headers=ch)
    assert r.status_code == 403, r.text


def test_a_draft_on_another_catalog_is_refused_as_the_heatmap_is(app_client) -> None:  # noqa: F811
    """#556: never compute coverage over rows keyed to another ATT&CK catalog;
    the twin routes (heatmap, the client dashboard) refuse it the same way."""
    import uuid

    from sqlalchemy import update

    from app.models.attack_assessment import AttackAssessment

    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    _run(c, h, svc_id)
    assert _draft(c, h, svc_id).status_code == 200, "setup: the draft reads before the change"

    TestSession = app_client[1]
    with TestSession() as db:
        db.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(rows[0]["assessment_id"]))
            .values(catalog_version=None)
        )
        db.commit()
    r = _draft(c, h, svc_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "attack_catalog_mismatch"


def test_a_stored_result_this_build_cannot_read_is_a_typed_refusal(
    app_client,  # noqa: F811
) -> None:
    """A run stored in a shape the current schema refuses (for example one older
    than a field it now requires) is refused with a reason, never a 500."""
    import uuid

    from sqlalchemy import update

    from app.models.ai_run import AiRun

    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    run = _run(c, h, svc_id)

    TestSession = app_client[1]
    with TestSession() as db:
        db.execute(
            update(AiRun)
            .where(AiRun.id == uuid.UUID(run["id"]))
            .values(result={"tools_available": 1, "changed": []})
        )
        db.commit()
    r = _draft(c, h, svc_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "attack_draft_unreadable"
    # D-4, approved verbatim (#736 6216024281).
    assert r.json()["error"]["message"] == (
        "The last AI run was stored in an older format, so its draft cannot be shown. "
        "Run the AI again to see a draft."
    )


def test_a_client_user_of_the_same_tenant_cannot_read_the_draft(app_client) -> None:  # noqa: F811
    """The real exposure: a user of the client whose service this is. The
    tenant check passes for them, so only the role check stops them."""
    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    _run(c, h, svc_id)
    cid = h["X-Client-Id"]
    admin_only = {"Authorization": h["Authorization"]}
    r = c.post(f"/admin/clients/{cid}/domains", headers=admin_only, json={"domain": "acme.example"})
    assert r.status_code in (200, 201), r.text
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    assert user.status_code == 201, user.text
    body = user.json()
    assert (body["user"]["role"], body["user"]["client_id"]) == (
        "client",
        cid,
    ), "setup: the user must be a client of the SAME tenant"
    ch = {"Authorization": f"Bearer {body['tokens']['access_token']}", "X-Client-Id": cid}
    # The positive control: this user passes the tenant check. The client
    # dashboard answers "not released" (its tenant gate says "Client not found").
    dash = c.get(f"/clients/{cid}/attack/{svc_id}/dashboard", headers=ch)
    assert dash.status_code == 404, dash.text
    assert dash.json()["error"]["reason"] == "dashboard_not_released", dash.text
    r = c.get(f"/attack/services/{svc_id}/draft-dashboard", headers=ch)
    assert r.status_code == 403, r.text


def test_a_stale_assessment_with_no_run_names_the_catalog_not_the_missing_run(
    app_client,  # noqa: F811
) -> None:
    """A re-run cannot fix a stale catalog (Run AI refuses it too), so the
    refusal names the catalog, not "no completed AI run yet"."""
    import uuid

    from sqlalchemy import update

    from app.models.attack_assessment import AttackAssessment

    c, provider, h, svc_id, rows = _setup(app_client)
    TestSession = app_client[1]
    with TestSession() as db:
        db.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(rows[0]["assessment_id"]))
            .values(catalog_version=None)
        )
        db.commit()
    r = _draft(c, h, svc_id)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "attack_catalog_mismatch"


def test_reading_the_draft_writes_nothing(app_client) -> None:  # noqa: F811
    """The rows the draft rebuilds are in memory only. The writer scan
    (`test_approved_record_writers.py`) sees the model constructed and is told
    this; this pins it: the stored rows are byte-for-byte what they were."""
    c, provider, h, svc_id, rows = _setup(app_client)
    a = rows[0]["technique_code"]
    _answer_only(provider, {a: "gap"})
    _run(c, h, svc_id)
    c.patch(f"/attack/coverage/{rows[0]['id']}", headers=h, json={"rationale": "Edited after."})
    before = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    assert _draft(c, h, svc_id).status_code == 200
    after = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    assert after["coverage"] == before["coverage"]


def test_a_draft_from_a_partial_run_carries_the_runs_own_disclosures(
    app_client,  # noqa: F811
) -> None:
    """A draft from a run that lost a batch, and left techniques out, must not
    read as complete (#736 6216024281, 3b): it carries the run's failed-batch,
    omitted and re-asked counts, as the run reported them."""
    c, provider, h, svc_id, rows = _setup(app_client)
    lost, answered = rows[0]["technique_code"], rows[1]["technique_code"]

    def _answer(payload: dict) -> LLMResponse:
        asked = payload.get("technique_codes") or []
        if lost in asked:
            raise RuntimeError("provider closed the connection")
        entries = (
            [
                {
                    "technique_code": answered,
                    "status": "gap",
                    "detection_tools": [],
                    "prevention_tools": [],
                    "response_tools": [],
                    "rationale": "From the run.",
                }
            ]
            if answered in asked
            else []
        )
        return LLMResponse(json.dumps({"techniques": entries}))

    provider.register("mitre_map", _answer)
    run = _run(c, h, svc_id)
    reported = run["result"]
    assert reported["batches_failed"] >= 1, "setup: a batch failed"
    assert reported["omitted_count"] > 0, "setup: a successful batch left techniques out"
    assert reported["reasked_count"] > 0, "setup: the run asked again"

    body = _draft(c, h, svc_id).json()
    assert (body["batches_failed"], body["omitted_count"], body["reasked_count"]) == (
        reported["batches_failed"],
        reported["omitted_count"],
        reported["reasked_count"],
    )
