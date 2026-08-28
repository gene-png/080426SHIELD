"""`GET /attack/services/{id}/ai-inputs` — provenance and exclusions.

**Not a second payload view.** `POST /ai/preview` already answers "what will be
sent?", generically for all three services, and its button already renders in
the ATT&CK workspace. This endpoint answers the question nothing answers today:
**what was NOT sent, and where did what was sent come from?**

Why that matters, in the filter's own words
(`_client_capability_inputs` in `app/routes/attack.py`):

    "a tool missing from it cannot be named, and the technique it covers reads
     as uncovered"

The filter is CORRECT on all three counts — security scope, list status, and
approved-snapshot membership. That is exactly the point: this is not a bug, it
is a correct filter whose drops are invisible. A `gap` on a client deliverable
can mean "no control here" or "the tool was filtered and nobody could see it",
and the client cannot tell which.

Each test below drives one drop-path, and each asserts the capability is
ABSENT from what would be sent as well as PRESENT in the exclusions — because
"it appears in not_sent" and "it was actually withheld" are different claims,
and only asserting the first would pass over an endpoint that reported
everything twice.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    url = f"sqlite:///{tmp_path / 'shield-aiinputs.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

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


def _admin(c: TestClient) -> tuple[str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    return bearer, cid


def _tech_debt_list(
    TestSession: sessionmaker,
    cid: str,
    user_id: str,
    tools: list[tuple[str, bool | None, bool]],
    *,
    status: CapabilityListStatus = CapabilityListStatus.APPROVED,
) -> None:
    """A Tech Debt service + capability list. `tools` is (name, security_related, confirmed)."""
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=status)
        db.add(cl)
        db.flush()
        for name, related, confirmed in tools:
            db.add(
                CapabilityItem(
                    capability_list_id=cl.id,
                    name=name,
                    security_related=related,
                    security_class_confirmed=confirmed,
                )
            )
        db.commit()


def _attack_service(c: TestClient, bearer: str, cid: str) -> str:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    return c.post(
        "/attack/services",
        headers=h,
        json={"kind": "attack_coverage", "title": "Acme ATT&CK"},
    ).json()["id"]


@pytest.mark.unit
def test_a_capability_filtered_by_security_scope_is_reported_as_not_sent(app_client) -> None:
    """The misclassification case, and the reason this endpoint exists.

    A tool confirmed non-security is CORRECTLY dropped by `security_scope_filter`.
    Nothing in the product shows that it was dropped, so the technique it covers
    reads as a gap and the client cannot tell that from "no control here".
    """
    c, TestSession = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _tech_debt_list(
        TestSession,
        cid,
        me["id"],
        [("Splunk", None, False), ("Figma", False, True)],
    )
    sid = _attack_service(c, bearer, cid)

    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.get(f"/attack/services/{sid}/ai-inputs", headers=h)

    assert r.status_code == 200, r.text
    body = r.json()

    sent = [x["name"] for x in body["capabilities"]]
    assert "Splunk" in sent
    assert "Figma" not in sent, "an out-of-scope tool must not be offered to the model"

    withheld = {x["name"]: x for x in body["not_sent"]}
    assert "Figma" in withheld, "the drop must be visible, not merely correct"
    assert withheld["Figma"]["reason"] == "security_scope"
