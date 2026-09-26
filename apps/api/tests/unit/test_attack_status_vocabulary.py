"""The ATT&CK status vocabulary decided on #554 (2026-09-24), slice 1: storage and arithmetic.

WHERE THE EXPECTED VALUES COME FROM. The owner's decision on #554, typed here as
literals, never imported from `app.attack.coverage`: a test that reads its
expected vocabulary from the module under test agrees with it by construction.

What this slice establishes:
  * two new statuses: `outside_control_surface` (the technique applies; the
    client's control surface does not reach it) and `unable_to_determine`
    (nobody verified it), both OUTSIDE the assessed denominator;
  * a reason code per status: seven for Partial, `platform_absent` as the only
    N/A reason, three sub-cases for outside_control_surface, none for the rest;
  * a pairing the vocabulary forbids is refused at the click (a typed 422), and
    a status change drops a reason that no longer fits.
What it does NOT do yet: let anyone WRITE the two new statuses. No reporting
surface renders them, so they are refused at the PATCH (typed) and ignored from
the AI until the slice that teaches every surface to show them. Requiring a
reason, and blocking release on `unable_to_determine`, are that later slice too.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.attack import coverage as cov
from app.attack.analytics import compute
from app.attack.catalog import TECHNIQUES

pytestmark = pytest.mark.unit

# The owner's decision, verbatim as data.
PARTIAL_REASONS = {
    "missing_control_category",
    "reach_limited",
    "detection_weak",
    "prevention_limited",
    "evasive_variant_uncovered",
    "recovery_absent",
    "periodic_not_continuous",
}
NA_REASONS = {"platform_absent"}
OUTSIDE_SUBCASES = {"adversary_preparation", "external_reconnaissance", "third_party_compromise"}
DEFINITION = (
    "missing_control_category is legitimate for Partial (something defends it, a category "
    "is missing) and forbidden for N/A (nothing defends it -- that is a gap)."
)


def test_the_statuses_are_the_decided_six() -> None:
    assert {s.value for s in cov.CoverageStatus} == {
        "covered",
        "partial",
        "gap",
        "not_applicable",
        "outside_control_surface",
        "unable_to_determine",
    }


def test_the_reason_codes_per_status_are_the_decided_ones() -> None:
    assert set(cov.reason_codes_for("partial")) == PARTIAL_REASONS
    assert set(cov.reason_codes_for("not_applicable")) == NA_REASONS
    assert set(cov.reason_codes_for("outside_control_surface")) == OUTSIDE_SUBCASES
    for status in ("covered", "gap", "unable_to_determine", None):
        assert cov.reason_codes_for(status) == ()


def test_the_definition_that_stops_abuse_is_written_into_the_vocabulary() -> None:
    text = " ".join(cov.reason_definition("missing_control_category").split())
    assert DEFINITION in text
    assert "is anything defending it at all" in text.lower()


def test_coverage_is_computed_over_assessed_techniques_only() -> None:
    codes = [t.id for t in TECHNIQUES[:6]]
    rollup = compute(
        dict(
            zip(
                codes,
                [
                    "covered",
                    "partial",
                    "gap",
                    "unable_to_determine",
                    "outside_control_surface",
                    "not_applicable",
                ],
                strict=True,
            )
        )
    )
    # Assessed = covered + partial + gap = 3; (1 + 0.5) / 3.
    assert rollup.coverage_pct == 50.0
    assert (rollup.unable_to_determine, rollup.outside_control_surface) == (1, 1)
    # Every assigned status counts as scored, or the catalogue total would shrink
    # on screen as rows move out of the denominator.
    assert rollup.scored_count == 6


def test_an_unverified_row_is_never_counted_as_partial_or_gap() -> None:
    code = TECHNIQUES[0].id
    rollup = compute({code: "unable_to_determine"})
    assert (rollup.partial, rollup.gap, rollup.covered) == (0, 0, 0)
    assert rollup.unable_to_determine == 1
    assert rollup.coverage_pct == 0.0


# --- the click: a pairing the vocabulary forbids is refused, typed -----------


@pytest.fixture()
def api(tmp_path) -> Iterator[tuple[TestClient, str, dict, str, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-vocab.db'}"
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
        yield c, a["coverage"][0]["id"], auth, svc, Sess


def _patch(c: TestClient, row: str, auth: dict, body: dict):
    return c.patch(f"/attack/coverage/{row}", headers=auth, json=body)


def test_a_partial_with_a_decided_reason_is_stored(api) -> None:
    c, row, auth, _, _ = api
    r = _patch(c, row, auth, {"status": "partial", "reason_code": "reach_limited"})
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["reason_code"]) == ("partial", "reach_limited")


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("partial", "platform_absent"),
        # The prohibition: a missing control is a GAP, never an N/A reason.
        ("not_applicable", "missing_control_category"),
        ("covered", "reach_limited"),
        ("gap", "missing_control_category"),
        ("partial", "not_a_code"),
    ],
)
def test_a_pairing_the_vocabulary_forbids_is_refused_typed(api, status, reason) -> None:
    c, row, auth, _, _ = api
    r = _patch(c, row, auth, {"status": status, "reason_code": reason})
    assert r.status_code == 422, r.text
    detail = r.json().get("error", r.json())
    assert detail.get("reason") == "invalid_reason_code", r.json()


def test_changing_status_drops_a_reason_that_no_longer_fits(api) -> None:
    c, row, auth, _, _ = api
    assert (
        _patch(c, row, auth, {"status": "partial", "reason_code": "detection_weak"}).status_code
        == 200
    )
    r = _patch(c, row, auth, {"status": "gap"})
    assert r.status_code == 200, r.text
    assert r.json()["reason_code"] is None


def test_a_narrative_is_stored(api) -> None:
    c, row, auth, _, _ = api
    r = _patch(c, row, auth, {"status": "gap", "narrative": "What could not be established."})
    assert r.status_code == 200, r.text
    assert r.json()["narrative"] == "What could not be established."


@pytest.mark.parametrize("status", ["unable_to_determine", "outside_control_surface"])
def test_the_new_statuses_are_not_writable_until_a_surface_reports_them(api, status) -> None:
    """No dashboard, exporter or badge renders them yet: stored, an unverified row
    would reach the client as N/A and a PDF would read 100% over unverified rows."""
    c, row, auth, _, _ = api
    r = _patch(c, row, auth, {"status": status})
    assert r.status_code == 422, r.text
    detail = r.json().get("error", r.json())
    assert detail.get("reason") == "status_not_yet_reportable", r.json()
    assert status in detail["message"]


def test_the_heatmap_endpoint_carries_both_counts(api) -> None:
    """Through the route, not `compute()`: the counts are wired by the route, and
    a test of the arithmetic alone stays green with the wiring deleted. Rows are
    set in the database because no writer may produce these statuses yet."""
    from sqlalchemy import update

    from app.models.attack_assessment import AttackCoverage

    c, _, auth, svc, Sess = api
    with Sess() as s:
        ids = (
            s.execute(
                AttackCoverage.__table__.select().with_only_columns(AttackCoverage.id).limit(3)
            )
            .scalars()
            .all()
        )
        for rid, st in zip(
            ids, ["unable_to_determine", "outside_control_surface", "gap"], strict=True
        ):
            s.execute(update(AttackCoverage).where(AttackCoverage.id == rid).values(status=st))
        s.commit()
    r = c.get(f"/attack/services/{svc}/heatmap", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["unable_to_determine"], body["outside_control_surface"]) == (1, 1)
    # The percentage is pinned by the `compute()` tests above; a covered row with
    # no confirmed citation is withheld here as pending (#102), so it would not
    # read back as the arithmetic alone predicts.
    assert sum(t["unable_to_determine"] for t in body["by_tactic"]) >= 1
    assert sum(t["outside_control_surface"] for t in body["by_tactic"]) >= 1


# A newline and a tab, built with chr() rather than written as escapes, so the
# source holds no control byte for `check_no_control_chars.py` to flag.
@pytest.mark.parametrize("blank", ["", "   ", chr(10) + chr(9)])
def test_a_blank_narrative_is_stored_as_none(api, blank) -> None:
    """The release gate will ask whether an unverified row carries a narrative;
    a blank one must not answer yes (#603 review round 2)."""
    c, row, auth, _, _ = api
    r = _patch(c, row, auth, {"status": "gap", "narrative": blank})
    assert r.status_code == 200, r.text
    assert r.json()["narrative"] is None
