"""#554 R3 through the routes: computed statuses, the review queue and the gate.

The advisor's decisions on #554 (2026-10-02, 21:55Z and 22:20Z):

* an assessment approved after R3 ships computes its statuses from Detect /
  Prevent / Respond (status_rules = 2); one approved before keeps its stored
  statuses;
* a computed status that differs from the stored (AI) suggestion is reviewed
  by a consultant before RELEASE -- gated at release, not at approve; bulk
  accept is allowed; the review is recorded (who, when, how many rows); the
  typed refusal names the count still unreviewed.

Every refusal's text is COPIED from the build plan posted on #554 (A8-A13),
never imported from the code under test.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, update

from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.models.audit_entry import AuditEntry
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit

ALL_THREE = {
    "detection_tools": ["Tool D"],
    "prevention_tools": ["Tool P"],
    "response_tools": ["Tool R"],
}


def _detail(r) -> dict:
    """The typed error's own fields: `reason`, `message` and any payload, without
    the envelope's `code` and `correlation_id`."""
    body = r.json()
    body = body.get("detail", body)
    body = body.get("error", body)
    return {k: v for k, v in body.items() if k not in ("code", "correlation_id")}


def _patch(c, bearer: str, row_id: str, body: dict) -> dict:
    r = c.patch(f"/attack/coverage/{row_id}", headers=_auth(bearer), json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _approve_and_finalize(c, bearer: str, svc: str, assessment_id: str) -> str:
    r = c.post(f"/attack/assessments/{assessment_id}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    return fin.json()["id"]


def _assessment(c, bearer: str, svc: str) -> dict:
    r = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    return r.json()


def _as_shown(c, bearer: str, svc: str, codes) -> list[dict]:
    """The pairs the review panel sends: each code with the computed status it
    shows, read off the assessment as the panel reads it."""
    rows = {r["technique_code"]: r for r in _assessment(c, bearer, svc)["coverage"]}
    return [{"code": code, "computed_status": rows[code]["computed_status"]} for code in codes]


def test_a_draft_reads_its_computed_status_beside_the_suggestion(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    out = _patch(c, bearer, row["id"], {"status": "covered", "detection_tools": ["Tool D"]})

    assert out["status"] == "covered"  # the stored suggestion, untouched
    assert out["computed_status"] == "partial"
    assert out["capabilities"]["line"] == (
        "Detect: in place · Prevent: not in place · Respond: not in place"
    )
    assert out["in_review_queue"] is True

    heat = c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).json()
    assert (heat["covered"], heat["partial"]) == (0, 1), heat


def test_approve_records_r3_and_is_not_refused_by_the_queue(env) -> None:  # noqa: F811
    """Gated at release, NOT at the click: an unreviewed row does not stop approve."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    out = _patch(c, bearer, row["id"], {"status": "partial", **ALL_THREE})
    assert out["in_review_queue"] is True

    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    assert r.json()["statuses_computed"] is True
    with Sess() as s:
        stored = s.get(AttackAssessment, uuid.UUID(a["id"]))
        assert (stored.status_rules, stored.parent_rules) == (2, 2)


def test_release_is_refused_until_the_queue_is_reviewed(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    differs, agrees = standalone_rows(a["coverage"], 2)
    _patch(c, bearer, differs["id"], {"status": "partial", **ALL_THREE})
    _patch(c, bearer, agrees["id"], {"status": "covered", **ALL_THREE})
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])

    refused = c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer))
    assert refused.status_code == 409, refused.text
    detail = _detail(refused)
    code = differs["technique_code"]
    assert detail["reason"] == "attack_computed_status_unreviewed", detail
    assert detail["message"] == (
        "Nothing was released: 1 technique has a computed status that differs from the "
        f"AI's suggestion and has not been reviewed ({code}). Review it in the Computed "
        "status review panel, then release again."
    )
    assert detail["unreviewed"] == [code]

    # Bulk accept, on the APPROVED assessment.
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": _as_shown(c, bearer, svc, [code])},
    )
    assert r.status_code == 200, r.text
    reviewed = {row["technique_code"]: row for row in r.json()["coverage"]}[code]
    assert reviewed["reviewed_status"] == "covered"
    assert reviewed["reviewed_by"] == admin["user"]["id"]
    assert reviewed["reviewed_at"] is not None
    assert reviewed["in_review_queue"] is False
    # The suggestion is untouched: a review records, it does not rewrite.
    assert reviewed["status"] == "partial"
    with Sess() as s:
        (event,) = (
            s.execute(
                select(AuditEntry).where(AuditEntry.action == "attack.computed_status.reviewed")
            )
            .scalars()
            .all()
        )
        assert event.details == {"rows": 1, "codes": [code], "remaining": 0}

    released = c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer))
    assert released.status_code == 200, released.text


def test_the_refusal_counts_in_the_plural(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = standalone_rows(a["coverage"], 2)
    for row in rows:
        _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])
    detail = _detail(c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer)))
    codes = ", ".join(sorted(r["technique_code"] for r in rows))
    assert detail["message"] == (
        "Nothing was released: 2 techniques have a computed status that differs from the "
        f"AI's suggestion and has not been reviewed ({codes}). Review them in the Computed "
        "status review panel, then release again."
    ), detail


def test_a_review_does_not_carry_over_to_a_different_outcome(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": _as_shown(c, bearer, svc, [row["technique_code"]])},
    )
    assert r.status_code == 200, r.text
    # Prevention removed: the computed status moves from Covered to Partial, which
    # is not what the consultant reviewed.
    out = _patch(c, bearer, row["id"], {"prevention_tools": []})
    assert (out["computed_status"], out["reviewed_status"]) == ("partial", "covered")
    assert out["in_review_queue"] is True


def test_the_review_endpoint_refuses_in_its_own_words(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    queued, other = standalone_rows(a["coverage"], 2)
    _patch(c, bearer, queued["id"], {"status": "partial", **ALL_THREE})
    url = f"/attack/assessments/{a['id']}/computed-status-review"

    empty = c.post(url, headers=_auth(bearer), json={"reviews": []})
    assert empty.status_code == 422, empty.text
    assert _detail(empty) == {
        "reason": "no_codes",
        "message": "No techniques were given to review.",
    }

    stale = c.post(
        url,
        headers=_auth(bearer),
        json={"reviews": [{"code": other["technique_code"], "computed_status": "gap"}]},
    )
    assert stale.status_code == 422, stale.text
    assert _detail(stale)["reason"] == "codes_not_in_review_queue"
    assert _detail(stale)["message"] == (
        f"Some techniques are no longer awaiting review ({other['technique_code']}). "
        "Reload the panel and review again."
    )
    # Nothing was recorded for the code that WAS in the queue either.
    assert _assessment(c, bearer, svc)["coverage"]
    with Sess() as s:
        assert (
            s.execute(
                select(AttackCoverage.reviewed_status).where(
                    AttackCoverage.technique_code == queued["technique_code"]
                )
            ).scalar_one()
            is None
        )

    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(a["id"]))
            .values(status_rules=1)
        )
        s.commit()
    before = c.post(
        url,
        headers=_auth(bearer),
        json={"reviews": [{"code": queued["technique_code"], "computed_status": "covered"}]},
    )
    assert before.status_code == 409, before.text
    assert _detail(before) == {
        "reason": "attack_computed_status_not_used",
        "message": (
            "This assessment's statuses were set before computed status existed, so there "
            "is nothing to review."
        ),
    }


def test_a_released_assessment_cannot_be_reviewed(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "covered", **ALL_THREE})
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])
    assert (
        c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer)).status_code
        == 200
    )
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": _as_shown(c, bearer, svc, [row["technique_code"]])},
    )
    assert r.status_code == 409, r.text
    assert _detail(r) == {
        "reason": "attack_assessment_released",
        "message": "This assessment has been released, so its review is closed.",
    }


def test_an_assessment_approved_before_r3_is_never_gated_by_the_queue(env) -> None:  # noqa: F811
    """Rule 1 renders stored statuses, so nothing is computed and nothing differs."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "partial", "reason_code": "reach_limited", **ALL_THREE})
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(a["id"]))
            .values(status_rules=1)
        )
        s.commit()
    latest = _assessment(c, bearer, svc)
    assert latest["statuses_computed"] is False
    (out,) = [x for x in latest["coverage"] if x["technique_code"] == row["technique_code"]]
    assert (out["status"], out["computed_status"], out["capabilities"]) == ("partial", None, None)
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    rel = c.post(f"/attack/deliverables/{fin.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text


def test_the_client_sees_what_is_in_place_and_the_disclosure(env) -> None:  # noqa: F811
    """Through the route a client calls, and the finalize summary beside it."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    by_code = {row["technique_code"]: row for row in a["coverage"]}
    # T1082 is one MITRE lists no mitigation for (test_attack_not_preventable.py).
    _patch(
        c,
        bearer,
        by_code["T1082"]["id"],
        {"status": "covered", "detection_tools": ["Tool D"], "response_tools": ["Tool R"]},
    )
    awaiting, untouched = standalone_rows(
        [r for r in a["coverage"] if r["technique_code"] != "T1082"], 2
    )
    _patch(c, bearer, awaiting["id"], {"status": "partial", **ALL_THREE})
    # The world, not the outcome: one tool's citation is still awaiting a human,
    # as a run that inferred it leaves it. The PATCH above confirmed everything.
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(awaiting["id"]))
            .values(
                unconfirmed_citations=[
                    {"tool": "Tool D", "cited": "Tool D", "reason": "inferred", "cleared_at": None}
                ]
            )
        )
        s.commit()
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])
    sentence = (
        "1 technique lists tools awaiting review; it is scored as if those tools were not in "
        "place."
    )
    latest = c.get(f"/attack/services/{svc}/deliverables/latest", headers=_auth(bearer)).json()
    assert latest["summary"].endswith(sentence), latest["summary"]
    rel = c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    body = dash.json()
    techs = {t["code"]: t for t in body["techniques"]}
    assert techs["T1082"]["status"] == "covered"
    assert techs["T1082"]["in_place"] == {
        "detect": "in place",
        "prevent": "cannot be prevented",
        "respond": "in place",
        "line": "Detect: in place · Prevent: cannot be prevented · Respond: in place",
        "cannot_be_prevented": True,
        "state": {"detect": "in_place", "prevent": "cannot_be_prevented", "respond": "in_place"},
    }
    assert body["statuses_computed"] is True
    code = awaiting["technique_code"]
    assert techs[code]["status"] == "partial"
    assert techs[code]["in_place"]["line"] == (
        "Detect: awaiting review · Prevent: in place · Respond: in place"
    )
    assert techs[code]["partial_reason"] == {
        "label": "Set by what is in place",
        "sentence": "This technique's status is computed from which of Detect, Prevent and "
        "Respond are in place.",
    }
    assert body["awaiting_review_sentence"] == sentence
    assert untouched["technique_code"] not in techs  # unscored rows are not listed


def test_the_value_summary_counts_the_computed_gaps(env) -> None:  # noqa: F811
    """The client overview's ATT&CK figure is the dashboard's gap count: two rows
    the AI called Gap with all three tools in place compute to Covered, so the
    figure is 0 where the stored statuses would say 2."""
    c, _Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = standalone_rows(a["coverage"], 2)
    for row in rows:
        _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": _as_shown(c, bearer, svc, sorted(row["technique_code"] for row in rows))},
    )
    assert r.status_code == 200, r.text
    rel = c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/value-summary",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()
    assert body["attack_uncovered_count"] == 0, body


def test_the_risk_feed_reads_the_computed_status(env) -> None:  # noqa: F811
    """Risk synthesis turns each ATT&CK Gap or Partial into a finding, labelled
    with its status. Called at `_gather_findings`, the one function every
    synthesis route reads its ATT&CK findings from: a row the AI called Covered
    with nothing in place is a Gap finding, and one it called Gap with all three
    in place is no finding at all."""
    from app.routes.risk import _gather_findings

    c, Sess = env
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    was_covered, was_gap = standalone_rows(a["coverage"], 2)
    _patch(c, bearer, was_covered["id"], {"status": "covered"})
    _patch(c, bearer, was_gap["id"], {"status": "gap", **ALL_THREE})
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    # Both rows differ from their suggestion, so synthesis refuses until they
    # are reviewed (test_attack_computed_status_risk.py); reviewed here.
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={
            "reviews": _as_shown(
                c, bearer, svc, sorted([was_covered["technique_code"], was_gap["technique_code"]])
            )
        },
    )
    assert r.status_code == 200, r.text

    with Sess() as s:
        client_id = s.get(AttackAssessment, uuid.UUID(a["id"])).client_id
        findings, *_ = _gather_findings(s, client_id)
    attack = {f["source_id"]: f["label"] for f in findings if f["kind"] == "attack"}
    assert attack == {
        was_covered["technique_code"]: f"ATT&CK {was_covered['technique_code']}: gap"
    }, attack


def test_a_patch_that_clears_the_queue_is_audited(env) -> None:  # noqa: F811
    """The stated limit: setting the stored status to the computed one takes the
    row out of the queue without a review record -- and the PATCH that does it is
    on record, with its actor and the field it wrote."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    _svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    assert _patch(c, bearer, row["id"], {"status": "partial", **ALL_THREE})["in_review_queue"]

    out = _patch(c, bearer, row["id"], {"status": "covered"})
    assert (out["computed_status"], out["in_review_queue"]) == ("covered", False)
    assert out["reviewed_status"] is None
    with Sess() as s:
        events = (
            s.execute(
                select(AuditEntry)
                .where(AuditEntry.action == "attack.coverage.updated")
                .order_by(AuditEntry.at)
            )
            .scalars()
            .all()
        )
    last = events[-1]
    assert last.actor_user_id == uuid.UUID(admin["user"]["id"])
    assert last.target_id == uuid.UUID(row["id"])
    assert last.details["technique_code"] == row["technique_code"]
    assert last.details["fields"] == ["status"], last.details


def test_an_edit_after_the_review_is_caught_at_release(env) -> None:  # noqa: F811
    """The advisor's required proof (22:25Z): an input that moves after the queue
    was cleared is re-checked at release. Reviewed on the DRAFT, then an edit
    moves the computed status (Covered to Partial); approve, finalize, release:
    refused, naming the row."""
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": _as_shown(c, bearer, svc, [row["technique_code"]])},
    )
    assert r.status_code == 200, r.text
    _patch(c, bearer, row["id"], {"prevention_tools": []})
    deliverable = _approve_and_finalize(c, bearer, svc, a["id"])
    refused = c.post(f"/attack/deliverables/{deliverable}/release", headers=_auth(bearer))
    assert refused.status_code == 409, refused.text
    assert _detail(refused)["reason"] == "attack_computed_status_unreviewed"
    assert _detail(refused)["unreviewed"] == [row["technique_code"]]


def _inferred_detection(Sess, row_id: str) -> None:
    """The world a run leaves when it had to INFER the detection tool."""
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(row_id))
            .values(
                unconfirmed_citations=[
                    {
                        "tool": "Tool D",
                        "cited": "Tool D",
                        "reason": "inferred",
                        "field": "detection_tools",
                        "cleared_at": None,
                    }
                ]
            )
        )
        s.commit()


def test_a_status_only_patch_confirms_nothing_on_a_computed_assessment(env) -> None:  # noqa: F811
    """The review's API finding 3. The stored status scores nothing here, so a
    status-only edit must not vouch for an inferred tool: that would raise the
    computed status (Partial to Covered) as a side effect."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    _svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "partial", **ALL_THREE})
    _inferred_detection(Sess, row["id"])

    out = _patch(c, bearer, row["id"], {"status": "covered"})
    assert out["computed_status"] == "partial"
    assert out["capabilities"]["detect"] == "awaiting_review"
    assert [e["cleared_at"] for e in out["unconfirmed_citations"]] == [None]

    # A tool-list edit still authors the claim, and confirms.
    out = _patch(c, bearer, row["id"], {"detection_tools": ["Tool D"]})
    assert out["computed_status"] == "covered"
    assert out["unconfirmed_citations"][0]["cleared_at"] is not None


def test_a_status_only_patch_still_confirms_before_r3(env) -> None:  # noqa: F811
    """The pre-R3 rule, kept: setting the status authors the claim (#102). Only a
    DRAFT can be PATCHed and every draft is computed after 0059, so the draft is
    stamped 1 here to reach the branch every pre-R3 assessment was edited under."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    _svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "partial", **ALL_THREE})
    _inferred_detection(Sess, row["id"])
    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(a["id"]))
            .values(status_rules=1)
        )
        s.commit()

    out = _patch(c, bearer, row["id"], {"status": "covered"})
    assert out["unconfirmed_citations"][0]["cleared_at"] is not None


def test_a_review_records_only_the_status_the_consultant_saw(env) -> None:  # noqa: F811
    """The review's web finding 4. The panel loads (Covered shown), the input
    moves on the draft (Partial now), and the click posts what was shown:
    refused, typed, and nothing is recorded."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    code = row["technique_code"]
    _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    shown = _as_shown(c, bearer, svc, [code])
    assert shown == [{"code": code, "computed_status": "covered"}]

    _patch(c, bearer, row["id"], {"prevention_tools": []})  # now Partial, still queued
    r = c.post(
        f"/attack/assessments/{a['id']}/computed-status-review",
        headers=_auth(bearer),
        json={"reviews": shown},
    )
    assert r.status_code == 409, r.text
    assert _detail(r) == {
        "reason": "computed_status_changed",
        "message": (
            f"The computed status of some techniques changed after the panel loaded "
            f"({code}). Reload the panel and review again."
        ),
        "codes": [code],
    }
    with Sess() as s:
        assert (
            s.execute(
                select(AttackCoverage.reviewed_status).where(
                    AttackCoverage.id == uuid.UUID(row["id"])
                )
            ).scalar_one()
            is None
        )


def test_editing_one_tool_list_confirms_only_that_lists_inferences(env) -> None:  # noqa: F811
    """The review's F1, API-3's twin. Editing Respond says nothing about an
    inferred Detect tool: on a computed assessment it stays awaiting review, so
    the computed status does not rise and the row stays in the queue."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    _svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    _inferred_detection(Sess, row["id"])

    out = _patch(c, bearer, row["id"], {"response_tools": ["Tool R2"]})
    assert out["capabilities"]["detect"] == "awaiting_review"
    assert [e["cleared_at"] for e in out["unconfirmed_citations"]] == [None]
    assert (out["computed_status"], out["in_review_queue"]) == ("partial", True)


def test_the_audit_counts_only_the_confirmations_an_edit_made(env) -> None:  # noqa: F811
    """F1's record half: an edit to one list stamps only that list's inferences,
    and the audit row says how many it stamped -- never the whole record. A row
    claiming confirmations that did not happen is a success record written where
    the success is not."""
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    _svc, a = _service_and_assessment(c, bearer)
    (row,) = standalone_rows(a["coverage"], 1)
    _patch(c, bearer, row["id"], {"status": "gap", **ALL_THREE})
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(row["id"]))
            .values(
                unconfirmed_citations=[
                    {
                        "tool": "Tool D",
                        "cited": "Tool D",
                        "reason": "inferred",
                        "field": "detection_tools",
                        "cleared_at": None,
                    },
                    {
                        "tool": "Tool R",
                        "cited": "Tool R",
                        "reason": "inferred",
                        "field": "response_tools",
                        "cleared_at": None,
                    },
                ]
            )
        )
        s.commit()

    out = _patch(c, bearer, row["id"], {"response_tools": ["Tool R"]})
    stamped = [e["field"] for e in out["unconfirmed_citations"] if e["cleared_at"] is not None]
    assert stamped == ["response_tools"]
    with Sess() as s:
        event = (
            s.execute(
                select(AuditEntry)
                .where(AuditEntry.action == "attack.coverage.updated")
                .order_by(AuditEntry.at.desc())
            )
            .scalars()
            .first()
        )
    assert event.details["citations_confirmed_by_hand"] == len(stamped) == 1
