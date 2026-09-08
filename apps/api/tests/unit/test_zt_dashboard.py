"""Client-facing Zero Trust maturity dashboard endpoint (D-035).

GET /clients/{client_id}/zt/{service_id}/dashboard returns the current-vs-target
per-pillar maturity rollup to the CLIENT, gated on the service having a released
deliverable. Reuses the same admin approve -> finalize -> release preamble the
other ZT tests use.
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

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[TestClient]:
    db_path = tmp_path / "shield-zt-dash.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c


def _register(c: TestClient, email: str) -> dict:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _attach_intake_target(svc_id: str, *, zt_stage: int | None) -> None:
    """Give the service a source request carrying the client's chosen stage.

    This is what `seed_demo.py` and every e2e spec skip -- they create services
    by direct POST with no `source_request_id` -- and it is why #124 survived a
    green suite: with no intake choice AND every per-capability target set, the
    engagement target is both absent and irrelevant, so no fixture could
    express the failure. Another instance of #72.
    """
    import uuid as _uuid

    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = _SR(
            client_id=svc.client_id,
            service_type=svc.kind.value,
            requested_by=svc.opened_by,
            zt_target_stage=zt_stage,
        )
        s.add(sr)
        s.flush()
        svc.source_request_id = sr.id
        s.commit()


def _seed_release(
    c: TestClient,
    bearer: str,
    *,
    release: bool,
    target_stage: int | None = 4,
    kind: str = "zero_trust_cisa",
) -> str:
    """Open a ZT service, set every answer to current=2, approve, finalize,
    optionally release. Returns the service id.

    `target_stage=None` writes NO per-capability target, which is the ordinary
    consultant-scored engagement: only Run-AI and the client's self-assessment
    submit ever write those rows. That is the shape #124 is about, and every
    test here set all 37 of them until this parameter existed.
    """
    svc_id = c.post(
        "/zt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": kind, "title": "Atlas - Zero Trust"},
    ).json()["id"]
    assessment = c.post(
        f"/zt/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()
    patch: dict[str, int] = {"maturity_stage": 2}
    if target_stage is not None:
        patch["target_stage"] = target_stage
    for ans in assessment["answers"]:
        c.patch(
            f"/zt/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer}"},
            json=patch,
        )
    c.post(
        f"/zt/assessments/{assessment['id']}/approve",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    deliv_id = c.post(
        f"/zt/services/{svc_id}/deliverables/finalize",
        headers={"Authorization": f"Bearer {bearer}"},
    ).json()["id"]
    if release:
        rel = c.post(
            f"/zt/deliverables/{deliv_id}/release",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert rel.status_code == 200, rel.text
    return svc_id


def _finalize_and_release(c: TestClient, bearer: str, svc_id: str) -> None:
    h = {"Authorization": f"Bearer {bearer}"}
    deliv_id = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    rel = c.post(f"/zt/deliverables/{deliv_id}/release", headers=h)
    assert rel.status_code == 200, rel.text


def _release_latest(c: TestClient, bearer: str, svc_id: str) -> None:
    """Release the deliverable `_seed_release(release=False)` already finalized.

    Lets a test attach the intake target BETWEEN finalize and release, which is
    the ordering that matters: the dashboard reads the client's chosen stage
    live at request time, not from the frozen deliverable.
    """
    h = {"Authorization": f"Bearer {bearer}"}
    deliv_id = c.get(f"/zt/services/{svc_id}/deliverables/latest", headers=h).json()["id"]
    rel = c.post(f"/zt/deliverables/{deliv_id}/release", headers=h)
    assert rel.status_code == 200, rel.text


@pytest.mark.unit
def test_zt_dashboard_released_returns_pillars(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=True)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["framework"] == "cisa_ztmm_2_0"
    # current stage 2 of 4 -> 50%, "Initial"; target stage 4 -> 100%, "Optimal".
    assert body["current_pct"] == 50.0
    assert body["target_pct"] == 100.0
    assert body["current_label"] == "Initial"
    assert body["target_label"] == "Optimal"
    assert len(body["pillars"]) >= 5  # CISA has 5 pillars + cross-cutting
    # Two fields the whole suite left unasserted until the #124 review looked
    # for surviving mutants: `largest_gap_pillar` could be wired to the pillar
    # CODE and `framework_label` to the raw enum value, and every test stayed
    # green while the client's card read "Largest: ID" under a heading saying
    # "cisa_ztmm_2_0". Pinned to the human-readable forms, which is the whole
    # point of both fields.
    assert body["framework_label"] == "CISA ZTMM 2.0", "the label, not the enum value"
    assert body["largest_gap_pillar"] in {p["name"] for p in body["pillars"]}
    assert body["largest_gap_pillar"] not in {
        p["code"] for p in body["pillars"]
    }, "the pillar NAME, not its code"
    p0 = body["pillars"][0]
    assert p0["current_pct"] == 50.0
    assert p0["target_pct"] == 100.0
    assert p0["gap_pct"] == 50.0
    assert body["largest_gap_pct"] == 50.0


@pytest.mark.unit
def test_zt_dashboard_unreleased_is_404_typed(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


# --- Issue 4: admin preview before release -----------------------------------
#
# Finalize previously produced a PDF and an XLSX and nothing else, so an analyst
# released a dashboard to the client having never seen it. The admin now sees
# the SAME dashboard as soon as the deliverable is finalized; the client's gate
# is unchanged (still release-only, covered by the test above).


@pytest.mark.unit
def test_admin_sees_the_dashboard_once_finalized_before_release(app_client) -> None:
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["released"] is False, "an unreleased dashboard must be labelled a preview"
    # The figures are real, not placeholders — same engine output as post-release.
    assert body["current_pct"] == 50.0
    assert body["target_pct"] == 100.0


@pytest.mark.unit
def test_admin_preview_matches_the_released_client_view_exactly(app_client) -> None:
    """Parity: preview and client view run the same builder, so the only field
    that may differ is the `released` flag (and its timestamp)."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)
    c.headers["X-Client-Id"] = client_id

    preview = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    ).json()

    deliv_id = c.get(
        f"/zt/services/{svc_id}/deliverables/latest",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    ).json()["id"]
    rel = c.post(
        f"/zt/deliverables/{deliv_id}/release",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    assert rel.status_code == 200, rel.text

    released = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    assert released["released"] is True
    volatile = {"released", "released_at"}
    assert {k: v for k, v in preview.items() if k not in volatile} == {
        k: v for k, v in released.items() if k not in volatile
    }, "admin preview and client view must not diverge"


@pytest.mark.unit
def test_client_still_cannot_see_a_finalized_but_unreleased_dashboard(app_client) -> None:
    """The consultant-in-the-loop gate is unchanged for clients."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False)
    c.headers["X-Client-Id"] = client_id

    assert (
        c.get(
            f"/clients/{client_id}/zt/{svc_id}/dashboard",
            headers={"Authorization": f"Bearer {bearer_admin}"},
        ).status_code
        == 200
    ), "precondition: the admin can preview it"

    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


@pytest.mark.unit
def test_zt_release_flips_the_assessment_to_released(app_client) -> None:
    """W4 for Zero Trust. Before this, no API route assigned RELEASED at all, so
    a released ZT service kept an assessment that still read APPROVED and the
    progress bar showed `release` as the work still to do.
    """
    c = app_client
    bearer = _register(c, "w4-zt-parent@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = _seed_release(c, bearer, release=True)

    latest = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["status"] == "released"


# --- #124: the dashboard must use the ENGAGEMENT target --------------------
#
# `zt_dashboard` derived its target from per-capability `target_stage` rows and
# nothing else. Only Run-AI and the client's self-assessment submit write those,
# so a consultant-scored assessment left every one NULL: the target rolled up to
# None, every pillar's gap rounded to 0.0, and the client read "Target maturity:
# Unscored - +0 points to target" beside a released PDF from the SAME assessment
# listing its gaps against the stage they had contracted for.
#
# Every test above sets all 37 per-capability targets, which is exactly the
# state in which the defect is invisible.

# CISA ZTMM 2.0 has 37 capabilities (`app/zt/catalog.py`), and #124's report
# quotes "37 gap(s) at target S4" from a real released PDF. Every capability
# scored at stage 2 against a target of 4 is a gap, so the total IS the
# capability count -- derived from the framework, not from the endpoint.
_CISA_CAPABILITY_COUNT = 37


@pytest.mark.unit
def test_dashboard_uses_the_engagement_target_when_no_per_capability_targets(
    app_client,
) -> None:
    """#124. A consultant-scored assessment on a client who chose Stage 4."""
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False, target_stage=None)
    _attach_intake_target(svc_id, zt_stage=4)
    _release_latest(c, bearer_admin, svc_id)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    # The client chose 4 at intake and every capability inherits it.
    assert body["target_stage"] == 4
    assert body["target_stage_source"] == "client"
    assert body["engagement_target_capability_count"] == _CISA_CAPABILITY_COUNT

    # Was "Unscored"/None/0.0 -- the three values that made this read as good news.
    assert body["target_label"] == "Optimal"
    assert body["target_pct"] == 100.0
    assert body["largest_gap_pct"] == 50.0
    assert body["total_gap_count"] == _CISA_CAPABILITY_COUNT

    assert body["pillars"], "precondition: the rollup produced pillars"
    for p in body["pillars"]:
        code = p["code"]
        assert p["target_pct"] == 100.0, f"{code} target must not be unscored"
        assert p["target_label"] == "Optimal", f"{code} label must not be Unscored"
        assert p["gap_pct"] == 50.0, f"{code} must not report a 0-point move"


@pytest.mark.unit
def test_dashboard_gap_total_covers_a_mixed_assessment(app_client) -> None:
    """The two surfaces must tell one story about one assessment.

    #124 is not "a percentage was null" -- it is that the dashboard and the PDF
    built from the SAME approved assessment disagreed. A MIXED assessment is
    used deliberately: with a uniform one, "used the engagement target" and
    "used the per-row targets" produce identical numbers and the test cannot
    tell them apart.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = c.post(
        "/zt/services",
        headers={"Authorization": f"Bearer {bearer_admin}"},
        json={"kind": "zero_trust_cisa", "title": "Atlas - Zero Trust"},
    ).json()["id"]
    _attach_intake_target(svc_id, zt_stage=4)
    assessment = c.post(
        f"/zt/services/{svc_id}/assessments",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    ).json()
    for i, ans in enumerate(assessment["answers"]):
        payload: dict[str, int] = {"maturity_stage": 2}
        if i == 0:
            payload["target_stage"] = 2  # already met -> not a gap
        c.patch(
            f"/zt/answers/{ans['id']}",
            headers={"Authorization": f"Bearer {bearer_admin}"},
            json=payload,
        )
    c.post(
        f"/zt/assessments/{assessment['id']}/approve",
        headers={"Authorization": f"Bearer {bearer_admin}"},
    )
    _finalize_and_release(c, bearer_admin, svc_id)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    # 36 of 37: the one capability whose own target of 2 is already met drops
    # out. The engagement stage decided the other 36, which is what
    # `engagement_target_capability_count` reports.
    assert body["total_gap_count"] == _CISA_CAPABILITY_COUNT - 1
    assert body["engagement_target_capability_count"] == _CISA_CAPABILITY_COUNT - 1
    assert body["target_stage"] == 4
    assert body["target_stage_source"] == "client"


@pytest.mark.unit
def test_dashboard_labels_a_default_target_as_a_default(app_client) -> None:
    """No intake choice: the number is the engine's, and must say so.

    A fallback that renders identically to a decision is the #73/#79 lesson and
    the reason `target_stage_source` exists at all.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    # No `_attach_intake_target` call at all -- no source request.
    svc_id = _seed_release(c, bearer_admin, release=True, target_stage=None)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    assert body["target_stage"] == 3, "DEFAULT_TARGET_STAGE"
    assert body["target_stage_source"] == "default"
    assert body["engagement_target_capability_count"] == _CISA_CAPABILITY_COUNT
    # Stage 3 of 4 = 75%, and current 2 of 4 = 50%.
    assert body["target_pct"] == 75.0
    assert body["largest_gap_pct"] == 25.0


@pytest.mark.unit
def test_dashboard_reports_an_out_of_range_stored_target_rather_than_500ing(
    app_client,
) -> None:
    """A DoD engagement whose stored stage is 4. DoD ZTRA has three.

    The intake UI offered a fourth (#125), so this is on disk in real
    engagements. `analyze_gaps` REFUSES an out-of-range target now instead of
    clamping, so the dashboard must resolve before calling it -- otherwise the
    client's own dashboard 500s on data they can neither see nor fix. And the
    resolved source must name the fault rather than reporting "default", which
    would tell a consultant the client never chose when in fact their choice is
    unusable and can be re-asked.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(
        c,
        bearer_admin,
        release=True,
        target_stage=None,
        kind="zero_trust_dod",
    )
    _attach_intake_target(svc_id, zt_stage=4)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_stage_source"] == "client_out_of_range"
    assert body["target_stage"] == 3, "the DoD ladder's top stage, not the stored 4"


@pytest.mark.unit
def test_dashboard_does_not_credit_intake_for_a_fully_overridden_target(
    app_client,
) -> None:
    """The mirror image of #124, and the reason the count is in the payload.

    When every capability carries its own target, the engagement stage decides
    NOTHING -- so captioning the rendered percentage "your target, chosen at
    intake" would name a source that contributed none of it. Same defect as
    #124 (a label that does not describe the number beside it), facing the
    other way.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, bearer_admin, release=False, target_stage=4)
    _attach_intake_target(svc_id, zt_stage=2)
    _release_latest(c, bearer_admin, svc_id)

    c.headers["X-Client-Id"] = client_id
    body = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    ).json()

    # The intake choice is reported honestly...
    assert body["target_stage"] == 2
    assert body["target_stage_source"] == "client"
    # ...and so is the fact that it decided none of the rendered figure, which
    # comes entirely from the per-capability 4s.
    assert body["engagement_target_capability_count"] == 0
    assert body["target_pct"] == 100.0
    # The ONLY place in this file where the gap total and the engagement count
    # are far apart, which is what makes wiring one to the other detectable.
    # Every other test seeds a state where the two coincide, so without this
    # line `total_gap_count=engagement_target_capability_count` passes the
    # whole suite -- a surviving mutant found by the adversarial reviewer.
    assert body["total_gap_count"] == _CISA_CAPABILITY_COUNT


@pytest.mark.unit
def test_zt_dashboard_numbers_come_from_the_version_the_header_claims(app_client) -> None:
    """#114, ZT's half. Released v1 at stage 2; v2 approved at stage 4, unfinalized.

    The dashboard must keep reporting v1's 50% under its "v1, released" header
    rather than swapping to v2's 100% the moment the consultant approves it.
    """
    c = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]
    h = {"Authorization": f"Bearer {bearer_admin}"}

    svc_id = _seed_release(c, bearer_admin, release=True)

    v2 = c.post(f"/zt/services/{svc_id}/assessments", headers=h)
    assert v2.status_code == 201, v2.text
    v2 = v2.json()
    assert v2["version"] == 2, "the preamble did not actually cut a second version"
    for ans in v2["answers"]:
        c.patch(
            f"/zt/answers/{ans['id']}",
            headers=h,
            json={"maturity_stage": 4, "target_stage": 4},
        )
    assert c.post(f"/zt/assessments/{v2['id']}/approve", headers=h).status_code == 200

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/zt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["deliverable_version"] == 1, "the header stopped naming the released report"
    assert body["current_pct"] == 50.0, (
        "the dashboard served v2's stage-4 score (100%) under a header naming the "
        "released v1 report, whose PDF says 50%"
    )
    assert body["current_label"] == "Initial", "the maturity label followed the wrong version"
    assert body["largest_gap_pct"] == 50.0, "the gap figure came from the wrong version too"
