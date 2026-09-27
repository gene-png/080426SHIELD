"""An ATT&CK assessment with a Not verified row, or a Partial with no reason,
is not released and not approved (#622, #554 c3b, scope recorded 2026-09-26).

Driven through the routes a consultant uses -- approve, finalize, release --
because the guard is selected in the WIRING (CLAUDE.md: a test that imports the
thing it defends is weaker than the endpoint that reaches it).

`unable_to_determine` has no writer yet (`coverage.WRITABLE`), and an approved
assessment is locked, so the states the release guard exists for are written
straight to the database between finalize and release. They are REACHABLE: an
assessment approved before this gate existed can hold them (approve checked
nothing), and the guard is the backstop for whatever reaches an approved row
by any path.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import update

from app.attack.coverage import reason_codes_for
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from tests._attack_rows import standalone_rows
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit

REASON = "attack_not_release_ready"


def _detail(r) -> dict:
    assert r.status_code == 409, r.text
    body = r.json()
    return body.get("error", body)


def _set(Sess, row_id: str, **values) -> None:
    with Sess() as s:
        s.execute(
            update(AttackCoverage).where(AttackCoverage.id == uuid.UUID(row_id)).values(**values)
        )
        s.commit()


def _rule(Sess, assessment_id: str, value: int | None) -> None:
    with Sess() as s:
        s.execute(
            update(AttackAssessment)
            .where(AttackAssessment.id == uuid.UUID(assessment_id))
            .values(parent_rules=value)
        )
        s.commit()


def _scored(c, bearer, a: dict, n: int = 2) -> list[dict]:
    """`n` standalone rows scored covered through the PATCH, so the draft is a
    real, approvable assessment."""
    rows = standalone_rows(a["coverage"], n)
    for row in rows:
        r = c.patch(
            f"/attack/coverage/{row['id']}", headers=_auth(bearer), json={"status": "covered"}
        )
        assert r.status_code == 200, r.text
    return rows


def _approve_and_finalize(c, bearer, svc: str, a: dict) -> str:
    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    return fin.json()["id"]


def _release(c, bearer, deliverable_id: str):
    return c.post(f"/attack/deliverables/{deliverable_id}/release", headers=_auth(bearer))


# --- release -------------------------------------------------------------------


def test_a_not_verified_row_refuses_the_release_and_names_it(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _set(Sess, rows[0]["id"], status="unable_to_determine")

    d = _detail(_release(c, bearer, deliv))
    assert d["reason"] == REASON
    assert d["not_verified"] == [rows[0]["technique_code"]]
    assert d["message"].startswith("Nothing was released: 1 technique is Not verified (")
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer))
    assert latest.json()["status"] == "approved", latest.text


def test_a_partial_with_no_reason_refuses_the_release_under_the_new_rules(
    env,  # noqa: F811
) -> None:
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _set(Sess, rows[0]["id"], status="partial", reason_code=None)

    d = _detail(_release(c, bearer, deliv))
    assert d["partial_without_reason"] == [rows[0]["technique_code"]]
    assert "1 Partial technique has no reason" in d["message"]


def test_a_partial_with_a_reason_is_released(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _set(Sess, rows[0]["id"], status="partial", reason_code=reason_codes_for("partial")[0])

    r = _release(c, bearer, deliv)
    assert r.status_code == 200, r.text


def test_under_rule_1_a_reasonless_partial_does_not_block_but_not_verified_does(
    env,  # noqa: F811
) -> None:
    # Approved before #620, so before reason codes: none of its Partials has
    # one, and an approved assessment is locked, so the clause would refuse it
    # with nothing able to clear it. Not verified has no such history.
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _rule(Sess, a["id"], 1)
    _set(Sess, rows[0]["id"], status="partial", reason_code=None)
    _set(Sess, rows[1]["id"], status="unable_to_determine")

    d = _detail(_release(c, bearer, deliv))
    assert d["not_verified"] == [rows[1]["technique_code"]]
    assert d["partial_without_reason"] == []

    _set(Sess, rows[1]["id"], status="covered")
    assert _release(c, bearer, deliv).status_code == 200


def _family(Sess, a: dict, *, child_reason: bool) -> tuple[str, tuple[str, ...]]:
    """A computed parent Partial with no reason of its own, its children
    Partial with or without reasons. Returns (parent, children)."""
    from app.attack.parents import PARENT_CHILDREN

    parent, children = next(iter(PARENT_CHILDREN.items()))
    by_code = {r["technique_code"]: r["id"] for r in a["coverage"]}
    _set(Sess, by_code[parent], status="partial", reason_code=None)
    for child in children:
        _set(
            Sess,
            by_code[child],
            status="partial",
            reason_code=reason_codes_for("partial")[0] if child_reason else None,
        )
    return parent, children


def test_a_computed_parent_needs_no_reason_of_its_own(env) -> None:  # noqa: F811
    # D-094: a computed Partial has no reason of its own; its children carry
    # theirs, and they are the evidence.
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    _family(Sess, a, child_reason=True)

    r = _release(c, bearer, deliv)
    assert r.status_code == 200, r.text


def test_a_computed_parents_reasonless_children_block_it(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _scored(c, bearer, a)
    deliv = _approve_and_finalize(c, bearer, svc, a)
    parent, children = _family(Sess, a, child_reason=False)

    d = _detail(_release(c, bearer, deliv))
    assert d["partial_without_reason"] == sorted(children)
    assert parent not in d["partial_without_reason"]


# --- approve -------------------------------------------------------------------


def test_approve_refuses_a_partial_with_no_reason_and_names_the_control(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    r = c.patch(
        f"/attack/coverage/{rows[0]['id']}", headers=_auth(bearer), json={"status": "partial"}
    )
    assert r.status_code == 200, r.text

    d = _detail(c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)))
    assert d["reason"] == REASON
    assert d["message"] == (
        "This assessment cannot be approved: 1 Partial technique has no reason "
        f"({rows[0]['technique_code']}). Choose a reason for each Partial technique in "
        "its panel, then approve again."
    )
    latest = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer))
    assert latest.json()["status"] == "draft", latest.text

    r = c.patch(
        f"/attack/coverage/{rows[0]['id']}",
        headers=_auth(bearer),
        json={"status": "partial", "reason_code": reason_codes_for("partial")[0]},
    )
    assert r.status_code == 200, r.text
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )


def test_approve_refuses_not_verified_with_no_imperative(env) -> None:  # noqa: F811
    # Nothing can write or clear Not verified yet, so the message names what
    # blocks it and tells nobody to do anything (D-076).
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    rows = _scored(c, bearer, a)
    _set(Sess, rows[0]["id"], status="unable_to_determine")

    d = _detail(c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)))
    assert d["message"] == (
        "This assessment cannot be approved: 1 technique is Not verified "
        f"({rows[0]['technique_code']})."
    )


def test_approve_passes_a_computed_parent_whose_children_carry_reasons(env) -> None:  # noqa: F811
    # Through approve itself: the recompute makes the parent a Partial with no
    # reason of its own, and that must not refuse the approval (D-094).
    from app.attack.parents import PARENT_CHILDREN

    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    parent, children = next(iter(PARENT_CHILDREN.items()))
    by_code = {r["technique_code"]: r["id"] for r in a["coverage"]}
    for child in children:
        r = c.patch(
            f"/attack/coverage/{by_code[child]}",
            headers=_auth(bearer),
            json={"status": "partial", "reason_code": reason_codes_for("partial")[0]},
        )
        assert r.status_code == 200, r.text

    r = c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    parent_row = next(x for x in r.json()["coverage"] if x["technique_code"] == parent)
    assert (parent_row["status"], parent_row["reason_code"]) == ("partial", None)
