"""#254 contract: a self-serve signup's email never becomes the org's legal name.

`Client.legal_name` is the string printed on the organisation line of every
client deliverable. Self-service provisioning (D-034) used to derive it from
the registrant's email -- the domain for an unknown company domain, and the
registrant's own DISPLAY NAME for a generic provider -- so a deliverable could
carry `acme.example`, or a person's name, as the client organisation.

**Both write paths are covered here on purpose.** They are two calls to one
helper in `routes/auth.py` and they leak different things, so a fix verified
against one of them says nothing about the other. The generic-provider path is
the worse of the two: a domain reads as a system placeholder, whereas a
person's name on the organisation line is PII on a delivered document.

WHAT THE SPEC SAYS, which is where the expected values come from rather than
from the code under test:

  * D-080 -- `legal_name` is NULL until a human names the organisation. A
    self-serve registrant has named nothing, so the column records nothing.
  * Master Spec Sec 15.5, restated in `tech_debt/filename.py`'s own docstring --
    the company slug of an empty name is the literal `Unknown`.

The world these tests build is a registration request. They do NOT construct a
`Client` row, because writing the row is the step under test: a setup that
stamped `legal_name` itself would prove the assertion against its own fixture
(CLAUDE.md, "a test that supplies its own precondition from the thing under
test cannot fail").
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-self-serve.db"
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


def _register(client: TestClient, *, email: str, display_name: str) -> dict:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": display_name,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# The two self-serve write paths, and the string each one used to leak.
#
# `must_not_appear` is what the test WROTE INTO the world (an address it chose,
# a display name it chose), never a value read back out of the code under test.
_SELF_SERVE_PATHS = [
    pytest.param(
        "newhire@acme-unregistered.example",
        "Dana Whitfield",
        "acme-unregistered.example",
        id="unknown-company-domain",
    ),
    pytest.param(
        "dana.whitfield@gmail.com",
        "Dana Whitfield",
        "Dana Whitfield",
        id="generic-provider-is-a-persons-name",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_provisioning_records_no_derived_legal_name(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The store records that nobody has named the org -- not a guess at one."""
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = body["user"]["client_id"]
    assert cid is not None, "a self-serve registrant must land in its own tenant"
    cid = uuid.UUID(cid)

    from app.models.client import Client

    with TestSession() as db:
        row = db.get(Client, cid)
        assert row is not None
        # D-080: NULL is the record of "no name was offered", which is the
        # condition every downstream guard needs and the only one the row can
        # state without a second field to keep in sync.
        assert row.legal_name is None, (
            f"self-serve provisioning stored {row.legal_name!r} as the organisation's "
            f"legal name; it must store NULL until a human names the org"
        )
        assert row.legal_name != must_not_appear


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_legal_name_never_reaches_a_deliverable(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The client-reachable surface: the filename on the document they download.

    This asserts through `deliverable_filename` rather than through the stored
    column, because the column is not what the client reads. Every finalize
    route builds its filenames from a bare `client.legal_name` read, and that
    read is reproduced here.

    The needle is the SLUGIFIED form. A raw-string check would pass while the
    defect was live -- Sec 15.5 strips `.` and `-` and turns a space into `_`,
    so `Dana Whitfield` reaches the filename as `Dana_Whitfield` and
    `"Dana Whitfield" not in name` is satisfied by a filename that carries the
    person's name in full.
    """
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = uuid.UUID(body["user"]["client_id"])

    from app.models.client import Client
    from app.tech_debt.filename import SERVICE_SLUG_ATTACK, deliverable_filename, slugify

    with TestSession() as db:
        org = db.get(Client, cid).legal_name

    name = deliverable_filename(
        company=org,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="pdf",
        day=date(2026, 9, 22),
        version=1,
    )
    leaked = slugify(must_not_appear)
    assert leaked not in name, (
        f"the deliverable filename {name!r} carries {leaked!r}, which came from the "
        f"registrant's email rather than from a name the organisation gave"
    )
    # Sec 15.5's documented empty-company behaviour, quoted in filename.py's
    # module docstring: "empty result -> Unknown".
    assert name.startswith("Unknown_")


@pytest.mark.unit
@pytest.mark.parametrize(("email", "display_name", "must_not_appear"), _SELF_SERVE_PATHS)
def test_self_serve_legal_name_never_reaches_the_ai_egress_path(
    app_client: tuple[TestClient, sessionmaker],
    email: str,
    display_name: str,
    must_not_appear: str,
) -> None:
    """The second surface an unnamed org can leak through: the Tech Debt extractor.

    `client_org_name_for_tenant` is what feeds the tenant's own name to the
    redactor as a name hint. An unnamed tenant has no name to hint with, and
    handing it the registrant's personal name would put that name into the
    prompt built to keep names OUT.
    """
    client, TestSession = app_client
    _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")

    body = _register(client, email=email, display_name=display_name)
    cid = uuid.UUID(body["user"]["client_id"])

    from app.tech_debt.extract import client_org_name_for_tenant

    with TestSession() as db:
        resolved = client_org_name_for_tenant(db, cid)

    assert resolved is None, (
        f"the Tech Debt extractor resolved {resolved!r} as this tenant's organisation "
        f"name; a self-serve tenant that has completed no intake has none"
    )
    assert resolved != must_not_appear


@pytest.mark.unit
def test_admin_created_client_keeps_its_name(
    app_client: tuple[TestClient, sessionmaker],
) -> None:
    """The exemption, pinned so the fix cannot over-reach.

    `routes/admin.py`'s create-client path is a human naming an organisation,
    and it stays. This test is the reason the guards are keyed on the NAME
    being absent rather than on `intake_completed_at` being NULL: an
    admin-created tenant has a real name and never completes intake, so keying
    on intake would blank its deliverables and block its engagements -- a
    regression strictly worse than the defect being fixed.
    """
    client, TestSession = app_client
    admin = _register(client, email="founder@kentro.example", display_name="Bootstrap Admin")
    bearer = admin["tokens"]["access_token"]

    created = client.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Northwind Grid Cooperative"},
    )
    assert created.status_code == 201, created.text
    cid = uuid.UUID(created.json()["id"])

    from app.models.client import Client
    from app.tech_debt.extract import client_org_name_for_tenant

    with TestSession() as db:
        row = db.get(Client, cid)
        assert row.legal_name == "Northwind Grid Cooperative"
        assert row.intake_completed_at is None
        assert client_org_name_for_tenant(db, cid) == "Northwind Grid Cooperative"
