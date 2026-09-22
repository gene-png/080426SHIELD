"""End-to-end /intake route tests against an ephemeral SQLite + FastAPI TestClient."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.audit_entry import AuditEntry
from app.models.client import Client


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-intake-rt.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url

    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    test_engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=test_engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c, TestSession


def _register_and_bearer(client: TestClient) -> str:
    # The first registrant becomes the platform admin (client_id IS NULL).
    # Under Work Order B1 a client can only self-register against a pre-approved
    # org domain, so the admin first creates the org + approves "example.com",
    # then the client-role user registers and auto-joins it.
    admin = client.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "Admin",
        },
    )
    assert admin.status_code == 201, admin.text
    admin_bearer = admin.json()["tokens"]["access_token"]
    created = client.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        # D-080: the admin endpoint is a HUMAN NAMING AN ORG, so it gets a real
        # name. The pre-intake unnamed state is no longer reachable through
        # this endpoint and is covered where it actually happens, in
        # test_self_serve_legal_name_contract.py.
        json={"legal_name": "Example Org"},
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    dom = client.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={"domain": "example.com"},
    )
    assert dom.status_code == 201, dom.text
    r = client.post(
        "/auth/register",
        json={
            "email": "poc@example.com",
            "password": "correct horse battery staple!",
            "display_name": "POC",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["tokens"]["access_token"]


@pytest.mark.unit
def test_get_intake_creates_singleton_client(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"]["legal_name"] == "Example Org"
    assert body["service_requests"] == []
    assert body["intake_completed_at"] is None


@pytest.mark.unit
def test_patch_intake_updates_client_and_profile(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {
                "legal_name": "Atlas Defense Solutions",
                "industry": "Defense",
                "size_band": "501-1000",
            },
            "title": "CISO",
            "phone": "+1-555-0123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"]["legal_name"] == "Atlas Defense Solutions"
    assert body["client"]["industry"] == "Defense"
    assert body["client"]["size_band"] == "501-1000"


@pytest.mark.unit
def test_submit_intake_writes_service_requests_and_audit(app_client) -> None:
    client, TestSession = app_client
    bearer = _register_and_bearer(client)

    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {
                "legal_name": "Atlas Defense Solutions",
                "industry": "Defense",
                "address_line1": "123 Pentagon Way",
                "city": "Arlington",
                "state": "VA",
                "country": "US",
            },
            "service_requests": [
                {
                    "service_type": "nist_csf",
                    "notes": "Annual assessment refresh.",
                    "csf_target_tier": 3,
                    "csf_profile": "MOD",
                },
                {"service_type": "zero_trust_cisa", "zt_target_stage": 3},
            ],
            "title": "CISO",
            "phone": "+1-555-0123",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intake_completed_at"] is not None
    assert len(body["service_requests"]) == 2
    types = sorted(req["service_type"] for req in body["service_requests"])
    assert types == ["nist_csf", "zero_trust_cisa"]

    # Audit row written.
    with TestSession() as db:
        rows = (
            db.execute(select(AuditEntry).where(AuditEntry.action == "client.intake_submitted"))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].details["services"] == ["nist_csf", "zero_trust_cisa"]

        c_row = db.execute(select(Client)).scalar_one()
        assert c_row.intake_completed_at is not None
        assert c_row.legal_name == "Atlas Defense Solutions"


@pytest.mark.unit
def test_submit_rejects_empty_service_requests(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [],
        },
    )
    assert r.status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {"legal_name": ""},
        {"legal_name": None},
        {},
        # The whitespace case, added after the adversarial review: `"   "`
        # is TRUTHY, so it is the one arm a bare `not` lets through, and
        # the three arms above all pass with the guard's `.strip()`
        # deleted. Without this row the guard cannot go red on revert.
        {"legal_name": "   "},
    ],
)
def test_submit_rejects_an_unnamed_organization(app_client, payload: dict) -> None:
    """You cannot submit an intake without naming the organisation.

    THIS TEST REPLACES `test_submit_rejects_pending_placeholder_legal_name`,
    and the replacement is stated rather than done quietly because weakening a
    test to reach green is exactly what this repo forbids.

    The old test asserted that the literal string `"(pending intake)"` was
    refused. That string was a SENTINEL the server stored and compared against,
    and the submit guard rejected it because the wizard used to prefill the
    field with it -- so a user could submit the placeholder back unchanged
    without ever typing a name.

    D-080 removed the sentinel: an unnamed org is NULL, and `Step2Organization`
    now starts the field EMPTY. The round-trip the old assertion defended
    against cannot occur, and after the change `"(pending intake)"` is simply an
    odd name a user typed on purpose -- refusing it would mean keeping the magic
    string the decision exists to delete.

    What the guard always MEANT is what is pinned here, and it is pinned across
    all three ways a name can be absent rather than the one the old test
    happened to use. This is strictly wider coverage than it replaces: the old
    test exercised none of these three.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": payload,
            "service_requests": [{"service_type": "consultation"}],
        },
    )
    assert r.status_code == 422


@pytest.mark.unit
def test_submit_dedupes_duplicate_service_requests(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [
                {"service_type": "nist_csf", "csf_target_tier": 3, "csf_profile": "MOD"},
                {"service_type": "nist_csf", "csf_target_tier": 3, "csf_profile": "MOD"},
                {"service_type": "consultation"},
            ],
        },
    )
    assert r.status_code == 200
    assert len(r.json()["service_requests"]) == 2


@pytest.mark.unit
def test_submit_requires_csf_and_zt_targets(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)

    # NIST CSF without a target tier + profile is rejected.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [{"service_type": "nist_csf"}],
        },
    )
    assert r.status_code == 422

    # Zero Trust without a target stage is rejected.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [{"service_type": "zero_trust_dod"}],
        },
    )
    assert r.status_code == 422

    # With targets supplied, the same services are accepted and persisted.
    r = client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [
                {"service_type": "nist_csf", "csf_target_tier": 4, "csf_profile": "HIGH"},
                {"service_type": "zero_trust_dod", "zt_target_stage": 2},
            ],
        },
    )
    assert r.status_code == 200, r.text
    by_type = {s["service_type"]: s for s in r.json()["service_requests"]}
    assert by_type["nist_csf"]["csf_target_tier"] == 4
    assert by_type["nist_csf"]["csf_profile"] == "HIGH"
    assert by_type["zero_trust_dod"]["zt_target_stage"] == 2


@pytest.mark.unit
def test_submit_refuses_a_zt_target_the_framework_does_not_have(app_client) -> None:
    """DoD ZTRA ends at Stage 3. Intake must refuse 4 rather than store it.

    The front half of #125. `ServiceRequestInput.zt_target_stage` WAS bound
    `ge=2, le=4` for BOTH frameworks -- a pydantic field constraint cannot see
    `service_type` -- and `_validate_targets` checked PRESENCE only. So a DoD
    engagement stored a 4, `analyze_gaps` clamped it to 3, and the finalize
    audit row reported `target_stage: 3, target_stage_source: "client"`: a stage
    the framework does not have, attributed to a client who could not have
    meant it.

    `resolve_target_stage` now reports such a stored value as
    `client_out_of_range` instead of as the client's choice, which is the
    honest answer to a value already on disk. This is the other end: refusing
    it at the door means there is nothing to be honest about later.

    The positive controls are the point. A guard that refused every target
    would satisfy the 422 assertion alone, so this also pins that DoD 2 and 3
    still submit, and that CISA 4 -- a stage CISA really has -- is untouched.

    **The tense above is deliberate: that bound is GONE as of #406**, and both
    ends of the range now live in `_validate_targets`. Corrected here because
    the identical sentence was corrected in `lib/intake/types.ts` in the same
    change and this twin was left standing -- a reader greps `ge=2`, finds
    nothing, and concludes this docstring or the fix is wrong. The history is
    kept rather than deleted: it is why the guard exists.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)

    def submit(service_type: str, stage: int):
        return client.post(
            "/intake/submit",
            headers={"Authorization": f"Bearer {bearer}"},
            json={
                "client": {"legal_name": "Atlas Defense Solutions"},
                "service_requests": [{"service_type": service_type, "zt_target_stage": stage}],
            },
        )

    # DoD has no Stage 4. Refused, and the reason names the real range rather
    # than dumping a validation error (the D-016 typed-detail pattern).
    r = submit("zero_trust_dod", 4)
    assert r.status_code == 422, r.text
    # The app wraps a typed detail in its own envelope (`app/exceptions.py`),
    # so `reason`/`message` sit under "error", not under FastAPI's "detail".
    err = r.json()["error"]
    assert err["reason"] == "zt_target_stage_out_of_range", err
    assert "stages 1-3" in err["message"], err["message"]
    # The PRODUCT NAME, not the StrEnum value. This assertion used to read
    # `"zero_trust_dod" in err["message"]` and so PINNED a database identifier
    # inside client-facing copy -- the sentence is rendered verbatim by
    # `clientFacingError` in `IntakeWizard.tsx`. Changed because the behaviour
    # changed, not to reach green: `_refuse_zt_stage_out_of_range` now reads
    # `provisioning.SERVICE_TITLES`. Both halves are pinned, so a revert to the
    # enum fails here rather than passing on a substring.
    assert "Zero Trust (DoD ZTRA)" in err["message"], err["message"]
    assert "zero_trust_dod" not in err["message"], err["message"]

    # POSITIVE CONTROLS -- every stage each framework really has still submits.
    for stage in (2, 3):
        assert submit("zero_trust_dod", stage).status_code == 200, stage
    for stage in (2, 3, 4):
        assert submit("zero_trust_cisa", stage).status_code == 200, stage


@pytest.mark.unit
def test_intake_requires_authentication(app_client) -> None:
    client, _ = app_client
    r = client.get("/intake")
    assert r.status_code == 401
    r = client.patch("/intake", json={})
    assert r.status_code == 401
    r = client.post(
        "/intake/submit",
        json={
            "client": {"legal_name": "X"},
            "service_requests": [{"service_type": "consultation"}],
        },
    )
    assert r.status_code == 401


# --------------------------------------------------------------------------- #
# The review step must be able to show what it is about to submit.
#
# UX finding 3 / E2E F-7: "Review & submit" rendered Organization, Services and
# Systems but NOT the contact details, because /intake never returned them. A
# client could not check the POC name, title, phone or timezone before
# committing the intake.
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_intake_state_returns_the_contact_for_review(app_client) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "display_name": "Dana Reyes",
            "title": "Director of Information Security",
            "phone": "+1 319 555 0142",
            "timezone": "America/Chicago",
        },
    )

    r = client.get("/intake", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    contact = r.json()["contact"]
    assert contact["display_name"] == "Dana Reyes"
    assert contact["title"] == "Director of Information Security"
    assert contact["phone"] == "+1 319 555 0142"
    assert contact["timezone"] == "America/Chicago"
    # The email is the account's own and is shown read-only on the wizard.
    assert contact["email"]


@pytest.mark.unit
def test_patch_normalises_a_whitespace_only_name_to_null(app_client) -> None:
    """A blank name is stored as NULL, not as blanks.

    This is the WRITE half of D-080's "one representation of unnamed". Without
    it `"   "` survives in the column: every exporter's `client_legal_name or
    "Client"` sees a truthy value and renders a BLANK organisation line on the
    client's DOCX/PDF/XLSX, while the admin UI calls the same row unnamed.

    Asserts the stored column rather than the response, because the response
    would echo whatever the normaliser produced and could agree with a broken
    one by construction.
    """
    client, TestSession = app_client
    bearer = _register_and_bearer(client)

    r = client.patch(
        "/intake",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"client": {"legal_name": "   "}},
    )
    assert r.status_code == 200, r.text

    with TestSession() as db:
        row = db.execute(select(Client)).scalar_one()
        assert row.legal_name is None, (
            f"a whitespace-only name was stored as {row.legal_name!r}; it must "
            f"normalise to NULL so there is one representation of 'unnamed'"
        )


@pytest.mark.unit
def test_engagement_refuses_a_legacy_blank_name_with_422_not_500(app_client) -> None:
    """A row that predates the write-time normalisation must still be REFUSED.

    The setup writes `"   "` by direct SQL on purpose. That is not the step
    under test -- it is the WORLD: `ClientProfilePatch` carries no validator, so
    any pre-D-080 `PATCH /intake` could store it, and migration 0049 does not
    NULL it (its predicates match a domain, a display name, or the old
    sentinel). The invariant is enforced at every writer and does not reach
    backwards, so the read side has to cope.

    Before the guard stripped, `"   "` was truthy: this guard passed and
    `provision_self_assessment_service` raised `ValueError` on the next call --
    an untyped 500 six lines below a typed 422, against core principle 2.
    """
    client, TestSession = app_client
    bearer = _register_and_bearer(client)

    with TestSession() as db:
        row = db.execute(select(Client)).scalar_one()
        row.legal_name = "   "
        db.commit()

    r = client.post(
        "/intake/engagements",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"service_type": "nist_csf", "csf_target_tier": 2, "csf_profile": "current"},
    )
    assert r.status_code == 422, (
        f"expected a typed 422 refusal, got {r.status_code}. A 500 here is the "
        f"ValueError from provision_self_assessment_service escaping untyped."
    )
