"""A parent technique's status is arithmetic over its sub-techniques (#554, D-094).

The owner's decision on #554: "`parent_rollup` -- computed. A parent's status is
arithmetic over its children. AI suggests, code computes. Forbidden as a reason."
The arithmetic itself was not specified; D-094 records the rule chosen.

THE TRUTH TABLE COMES FIRST, written before `computed_parent_status` existed
(CLAUDE.md: a table written after its rule is a transcript of it). Each row is a
class of child combination, and the expected parent is a literal.
"""

from __future__ import annotations

import pytest

from app.attack.parents import computed_parent_status

pytestmark = pytest.mark.unit

C, P, G, NA = "covered", "partial", "gap", "not_applicable"
OUT, UTD = "outside_control_surface", "unable_to_determine"

# (id, children as (status, reason), expected (status, reason))
TABLE = [
    # Unknown is never rounded up: one unscored child leaves the parent unscored.
    ("one_unscored", [(C, None), (None, None)], (None, None)),
    ("all_unscored", [(None, None), (None, None)], (None, None)),
    # Unverified wins over every assessed value: it cannot be counted as any.
    ("one_unverified", [(C, None), (UTD, None)], (UTD, None)),
    ("unverified_and_unscored", [(UTD, None), (None, None)], (None, None)),
    # Uniform assessed children.
    ("all_covered", [(C, None), (C, None)], (C, None)),
    ("all_gap", [(G, None), (G, None)], (G, None)),
    ("all_partial", [(P, "reach_limited"), (P, "detection_weak")], (P, None)),
    # Mixed assessed children: something defends part of it, not all of it.
    ("covered_and_gap", [(C, None), (G, None)], (P, None)),
    ("covered_and_partial", [(C, None), (P, "reach_limited")], (P, None)),
    ("partial_and_gap", [(P, "reach_limited"), (G, None)], (P, None)),
    # Children that cannot occur here are set aside; the rest decide.
    ("covered_plus_na", [(C, None), (NA, "platform_absent")], (C, None)),
    ("gap_plus_na", [(G, None), (NA, "platform_absent")], (G, None)),
    ("covered_plus_outside", [(C, None), (OUT, "adversary_preparation")], (C, None)),
    # Nothing assessed at all.
    ("all_na", [(NA, "platform_absent"), (NA, "platform_absent")], (NA, "platform_absent")),
    (
        "all_outside_one_subcase",
        [(OUT, "adversary_preparation"), (OUT, "adversary_preparation")],
        (OUT, "adversary_preparation"),
    ),
    (
        "all_outside_mixed_subcases",
        [(OUT, "adversary_preparation"), (OUT, "external_reconnaissance")],
        (OUT, None),
    ),
    # Outside the surface beats N/A: the technique applies, just not reachably.
    # CORRECTED after first run: this row expected no reason. The reason names
    # WHICH surface is unreachable, and the only unreachable child names one;
    # the N/A child is set aside here as everywhere else in the rule. Said out
    # loud because a table edited to match its code is the defect CLAUDE.md
    # warns about -- this is the table being wrong, not the code being fitted.
    (
        "na_and_outside",
        [(NA, "platform_absent"), (OUT, "third_party_compromise")],
        (OUT, "third_party_compromise"),
    ),
]


@pytest.mark.parametrize(
    ("children", "expected"),
    [(children, expected) for _, children, expected in TABLE],
    ids=[row[0] for row in TABLE],
)
def test_the_parent_is_computed_from_its_children(children, expected) -> None:
    assert computed_parent_status(children) == expected


def test_a_parent_with_no_children_is_not_computed() -> None:
    """Only a parent WITH sub-techniques is computed; the caller never asks for
    one without, and an empty list is refused rather than guessed."""
    with pytest.raises(ValueError):
        computed_parent_status([])


# --- through the write paths -------------------------------------------------

import os  # noqa: E402
import uuid  # noqa: E402
from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, update  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.attack.parents import PARENT_CHILDREN  # noqa: E402

# The world: a parent with at least two sub-techniques. Picking it from the
# catalog builds the setup only; every expected status below is a literal.
PARENT, CHILDREN = next((p, cs) for p, cs in sorted(PARENT_CHILDREN.items()) if len(cs) >= 2)


@pytest.fixture()
def api(tmp_path) -> Iterator[tuple[TestClient, dict, dict, str, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-parents.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    Sess = sessionmaker(bind=create_engine(url, future=True), autoflush=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.models.client import Client
    from app.models.client_domain import ClientDomain

    def override_get_db() -> Iterator[Session]:
        db = Sess()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    s = Sess()
    tenant = Client(legal_name="Test Tenant")
    s.add(tenant)
    s.flush()
    s.add(ClientDomain(client_id=tenant.id, domain="example.com"))
    s.commit()
    cid = str(tenant.id)
    s.close()
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        r = c.post(
            "/auth/register",
            json={
                "email": "a@example.com",
                "password": "correct horse battery staple!",
                "display_name": "a",
            },
        )
        assert r.status_code == 201, r.text
        auth = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}
        svc = c.post(
            "/attack/services",
            headers=auth,
            json={"kind": "attack_coverage", "title": "ATT&CK Coverage"},
        ).json()["id"]
        a = c.post(f"/attack/services/{svc}/assessments", headers=auth).json()
        by_code = {r["technique_code"]: r for r in a["coverage"]}
        yield c, auth, by_code, a["id"], Sess


def _set(c, auth, row_id: str, body: dict):
    return c.patch(f"/attack/coverage/{row_id}", headers=auth, json=body)


def _parent_now(c, auth, assessment_id: str, Sess) -> tuple[str | None, str | None]:
    from app.models.attack_assessment import AttackCoverage

    with Sess() as s:
        row = (
            s.query(AttackCoverage)
            .filter_by(assessment_id=uuid.UUID(assessment_id), technique_code=PARENT)
            .one()
        )
        return row.status, row.reason_code


@pytest.mark.parametrize(
    "field",
    [
        {"status": "covered"},
        {"reason_code": "reach_limited"},
        {"locked": True},
        # #620 round 2, finding 4: a parent's evidence is its children's. Its
        # own tools, rationale, narrative and evidence would be a second claim
        # beside the computed one, and the deliverable printed them.
        {"detection_tools": ["Tool A"]},
        {"prevention_tools": ["Tool A"]},
        {"response_tools": ["Tool A"]},
        {"rationale": "r"},
        {"narrative": "n"},
        {"evidence_artifact_id": "00000000-0000-4000-8000-000000000001"},
    ],
)
def test_a_computed_parents_status_and_reason_are_refused_typed(api, field) -> None:
    c, auth, by_code, _, _ = api
    r = _set(c, auth, by_code[PARENT]["id"], field)
    assert r.status_code == 422, r.text
    body = r.json().get("error", r.json())
    assert body["reason"] == "parent_status_computed", body


def test_a_computed_parents_notes_are_still_editable(api) -> None:
    c, auth, by_code, _, _ = api
    assert _set(c, auth, by_code[PARENT]["id"], {"notes": "Context."}).status_code == 200


def test_a_computed_parents_own_citations_cannot_be_confirmed(api) -> None:
    """#620 round 2, finding 2. A legacy parent can carry uncleared citations
    of its own, but its score rests on its children's evidence (D-094).
    Confirming the parent's would write an audit row vouching for evidence the
    score does not use, so it is refused typed, and nothing is written."""
    from app.models.attack_assessment import AttackCoverage
    from app.models.audit_entry import AuditEntry

    c, auth, by_code, _, Sess = api
    # The shape `resolve_citations` writes for a substring rescue (`reason` is
    # required on read): a state the application can produce, not a stub.
    entry = {
        "tool": "Tool A",
        "cited": "tool",
        "reason": "substring",
        "field": "detection_tools",
        "cleared_at": None,
    }
    with Sess() as s:
        row = s.get(AttackCoverage, uuid.UUID(by_code[PARENT]["id"]))
        row.unconfirmed_citations = [entry]
        s.commit()
        audits_before = s.query(AuditEntry).count()
    r = c.post(f"/attack/coverage/{by_code[PARENT]['id']}/confirm-citations", headers=auth)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["reason"] == "parent_status_computed"
    with Sess() as s:
        row = s.get(AttackCoverage, uuid.UUID(by_code[PARENT]["id"]))
        assert row.unconfirmed_citations == [entry], "the refusal must not clear anything"
        assert s.query(AuditEntry).count() == audits_before


def test_a_child_write_recomputes_its_parent(api) -> None:
    c, auth, by_code, assessment_id, Sess = api
    for child in CHILDREN:
        assert _set(c, auth, by_code[child]["id"], {"status": "covered"}).status_code == 200
    assert _parent_now(c, auth, assessment_id, Sess) == ("covered", None)
    assert _set(c, auth, by_code[CHILDREN[0]]["id"], {"status": "gap"}).status_code == 200
    assert _parent_now(c, auth, assessment_id, Sess) == ("partial", None)


def test_approve_recomputes_a_parent_that_drifted(api) -> None:
    """A draft scored before parents were computed carries a parent status no
    rule produced. Approval freezes the numbers, so it recomputes first."""
    from app.models.attack_assessment import AttackCoverage

    c, auth, by_code, assessment_id, Sess = api
    for child in CHILDREN:
        assert _set(c, auth, by_code[child]["id"], {"status": "gap"}).status_code == 200
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(by_code[PARENT]["id"]))
            .values(status="covered")
        )
        s.commit()
    assert _parent_now(c, auth, assessment_id, Sess) == ("covered", None)
    r = c.post(f"/attack/assessments/{assessment_id}/approve", headers=auth)
    assert r.status_code == 200, r.text
    assert _parent_now(c, auth, assessment_id, Sess) == ("gap", None)


def _service_id(Sess, assessment_id: str) -> str:
    from app.models.attack_assessment import AttackAssessment

    with Sess() as s:
        return str(s.get(AttackAssessment, uuid.UUID(assessment_id)).service_id)


def test_a_computed_parent_with_confirmed_children_is_NOT_pending(api) -> None:
    """#620 review, finding 1. A new assessment's rows are created with NULL
    citations, and NULL on a covered row reads as pending. The parent's claim
    rests on its children's evidence, so once the children are confirmed (a
    hand-set status confirms them), the parent is not pending -- through the
    heatmap, on a fresh assessment, not the seed (which writes [] everywhere)."""
    c, auth, by_code, assessment_id, Sess = api
    for child in CHILDREN:
        assert _set(c, auth, by_code[child]["id"], {"status": "covered"}).status_code == 200
    assert _parent_now(c, auth, assessment_id, Sess) == ("covered", None)

    heat = c.get(f"/attack/services/{_service_id(Sess, assessment_id)}/heatmap", headers=auth)
    assert heat.status_code == 200, heat.text
    assert heat.json()["pending_review"] == 0
    assert heat.json()["covered"] == len(CHILDREN) + 1

    rows = c.get(
        f"/attack/services/{_service_id(Sess, assessment_id)}/assessments/latest", headers=auth
    ).json()["coverage"]
    parent_row = next(r for r in rows if r["technique_code"] == PARENT)
    assert parent_row["pending_review"] is False


def test_a_computed_parent_is_pending_when_a_child_is(api) -> None:
    """The derivation's other half: a parent claiming support on a child whose
    evidence is unconfirmed is held out with it, and the badge agrees."""
    from app.models.attack_assessment import AttackCoverage

    c, auth, by_code, assessment_id, Sess = api
    for child in CHILDREN:
        assert _set(c, auth, by_code[child]["id"], {"status": "covered"}).status_code == 200
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(by_code[CHILDREN[0]]["id"]))
            .values(
                unconfirmed_citations=[
                    {
                        "tool": "Tool A",
                        "cited": "Tool",
                        "reason": "substring",
                        "field": "detection_tools",
                        "cleared_at": None,
                    }
                ]
            )
        )
        s.commit()

    svc = _service_id(Sess, assessment_id)
    assert c.get(f"/attack/services/{svc}/heatmap", headers=auth).json()["pending_review"] == 2
    rows = c.get(f"/attack/services/{svc}/assessments/latest", headers=auth).json()["coverage"]
    assert next(r for r in rows if r["technique_code"] == PARENT)["pending_review"] is True


def test_a_legacy_locked_parent_is_unlocked_and_recomputed_with_a_record(api) -> None:
    """#620 review, finding 2. A lock that predates D-094 would freeze a number
    the rule owns, and hide the freeze from run-ai's diff. The recompute unlocks
    it, and the audit row says so."""
    from sqlalchemy import select

    from app.models.attack_assessment import AttackCoverage
    from app.models.audit_entry import AuditEntry

    c, auth, by_code, assessment_id, Sess = api
    with Sess() as s:
        s.execute(
            update(AttackCoverage)
            .where(AttackCoverage.id == uuid.UUID(by_code[PARENT]["id"]))
            .values(locked=True, status="covered")
        )
        s.commit()
    for child in CHILDREN:
        assert _set(c, auth, by_code[child]["id"], {"status": "gap"}).status_code == 200

    assert _parent_now(c, auth, assessment_id, Sess) == ("gap", None)
    with Sess() as s:
        parent = s.get(AttackCoverage, uuid.UUID(by_code[PARENT]["id"]))
        assert parent.locked is False
        unlocked = [
            d.get("parents_unlocked")
            for d in s.execute(
                select(AuditEntry.details).where(AuditEntry.action == "attack.coverage.updated")
            ).scalars()
        ]
    assert [PARENT] in unlocked
