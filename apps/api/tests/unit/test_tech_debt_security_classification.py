"""Portfolio scope + security classification through the routes (migration 0038).

Tech Debt used to keep security capabilities and silently drop everything else:
the 2026-08-04 guided review uploaded 21 rows / $1,634,236 and the workspace
showed 12 rows / $891,796 as though that were the whole inventory. Prompt v2
keeps every row and classifies it instead.

That moves the risk rather than removing it. `_client_tool_names` in
routes/attack.py is a hard allow-list on which tools the ATT&CK model may cite,
so a wrong "not security-related" call now silently shrinks the mapping's input
— and the technique that tool covered reads as uncovered rather than
unassessed. Hence the sign-off: a negative is provisional until a human agrees.

These tests drive that through the API. The unit-level rules live in
test_tech_debt_security_scope.py.
"""

from __future__ import annotations

import io
import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.service import Service
from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    db_path = tmp_path / "shield-sec.db"
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
    provider = FixtureProvider()
    llm = LLMClient(provider)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep
    from app.routes.tech_debt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage
    app.dependency_overrides[_llm_dep] = lambda: llm

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Northwind Logistics")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, TestSession, provider


def _register(c: TestClient, email: str) -> str:
    r = c.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple!",
            "display_name": email.split("@")[0],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["tokens"]["access_token"]


def _upload_csv(c: TestClient, bearer: str, name: str, csv_bytes: bytes) -> str:
    r = c.post(
        "/artifacts",
        headers={"Authorization": f"Bearer {bearer}"},
        files={"file": (name, io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _extract(
    c: TestClient, bearer: str, provider, items: list[dict], csv: bytes
) -> tuple[str, dict]:
    provider.register("extract.capabilities", lambda _p: LLMResponse(json.dumps({"items": items})))
    sr = c.post(
        "/tech-debt/services",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"kind": "tech_debt", "title": "Portfolio"},
    )
    svc_id = sr.json()["id"]
    artifact_id = _upload_csv(c, bearer, "inventory.csv", csv)
    r = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"artifact_id": artifact_id},
    )
    assert r.status_code == 201, r.text
    return svc_id, r.json()


# One security tool, one unambiguous non-security tool.
_PORTFOLIO = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "annual_cost_usd": 120000,
        "confidence_pct": 95,
        "source_row_index": 0,
        "security_related": True,
        "security_functions": ["prevent", "detect", "respond"],
    },
    {
        "name": "Workday HCM",
        "vendor": "Workday",
        "category": "HCM",
        "annual_cost_usd": 81700,
        "confidence_pct": 90,
        "source_row_index": 1,
        "security_related": False,
        "security_functions": [],
    },
]
_PORTFOLIO_CSV = (
    b"Tool,Vendor,Annual Cost\n"
    b"CrowdStrike Falcon,CrowdStrike,120000\n"
    b"Workday HCM,Workday,81700\n"
)


def _tenant_id(TestSession: sessionmaker):
    db = TestSession()
    cid = db.execute(select(Service.client_id)).scalars().first()
    db.close()
    return cid


def _tool_names(TestSession: sessionmaker, client_id) -> list[str]:
    from app.routes.attack import _client_tool_names

    db = TestSession()
    try:
        return _client_tool_names(db, client_id)
    finally:
        db.close()


@pytest.mark.unit
def test_non_security_rows_are_kept_not_dropped(app_client) -> None:
    """The scope change itself. Workday belongs to the portfolio; under the v1
    prompt it vanished, taking $81,700 of real spend off the dashboard."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "scope1@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)

    assert {i["name"] for i in body["items"]} == {"CrowdStrike Falcon", "Workday HCM"}
    # Both uploaded rows produced a capability: nothing excluded, so the
    # dashboard total now covers the whole upload.
    assert body["source_rows_total"] == 2
    assert body["excluded_rows"] == []


@pytest.mark.unit
def test_classification_is_persisted_and_returned(app_client) -> None:
    c, _TestSession, provider = app_client
    bearer = _register(c, "scope2@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)
    by_name = {i["name"]: i for i in body["items"]}

    assert by_name["CrowdStrike Falcon"]["security_related"] is True
    assert by_name["CrowdStrike Falcon"]["security_functions"] == [
        "prevent",
        "detect",
        "respond",
    ]
    assert by_name["Workday HCM"]["security_related"] is False
    assert by_name["Workday HCM"]["security_functions"] == []
    # Nobody has agreed with the negative yet.
    assert by_name["Workday HCM"]["security_class_confirmed"] is False


@pytest.mark.unit
def test_unconfirmed_negative_still_reaches_the_attack_subset(app_client) -> None:
    """The safeguard, end to end: an un-reviewed negative removes nothing."""
    c, TestSession, provider = app_client
    bearer = _register(c, "scope3@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)
    workday_id = next(i["id"] for i in body["items"] if i["name"] == "Workday HCM")
    client_id = _tenant_id(TestSession)

    assert "Workday HCM" in _tool_names(TestSession, client_id)

    r = c.post(
        f"/tech-debt/capability-items/{workday_id}/security-classification/confirm",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text

    remaining = _tool_names(TestSession, client_id)
    assert "Workday HCM" not in remaining
    assert "CrowdStrike Falcon" in remaining


@pytest.mark.unit
def test_overriding_a_negative_puts_it_back_in_scope(app_client) -> None:
    """The Claroty-shaped case: an OT security tool the model called
    non-security. Overturning must also clear the stale sign-off."""
    c, TestSession, provider = app_client
    bearer = _register(c, "scope4@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)
    workday_id = next(i["id"] for i in body["items"] if i["name"] == "Workday HCM")
    client_id = _tenant_id(TestSession)

    c.post(
        f"/tech-debt/capability-items/{workday_id}/security-classification/confirm",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert "Workday HCM" not in _tool_names(TestSession, client_id)

    r = c.post(
        f"/tech-debt/capability-items/{workday_id}/security-classification/override",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"security_functions": ["detect"]},
    )
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["id"] == workday_id)
    assert item["security_related"] is True
    assert item["security_functions"] == ["detect"]
    assert item["security_class_confirmed"] is False
    assert "Workday HCM" in _tool_names(TestSession, client_id)


@pytest.mark.unit
def test_confirming_a_security_related_row_is_refused(app_client) -> None:
    """Sign-off is only meaningful on a negative — agreeing with a positive
    would record a decision that changes nothing, so it is refused rather than
    stored as though it mattered."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "scope5@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)
    falcon_id = next(i["id"] for i in body["items"] if i["name"] == "CrowdStrike Falcon")

    r = c.post(
        f"/tech-debt/capability-items/{falcon_id}/security-classification/confirm",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 409, r.text
    # D-016 envelope: a dict detail is surfaced as {"error": {reason, message}}.
    assert r.json()["error"]["reason"] == "not_a_negative_classification"


@pytest.mark.unit
def test_override_requires_at_least_one_security_function(app_client) -> None:
    """ "Security-related but serves none of prevent/detect/respond" is not a
    claim the ATT&CK mapping can act on."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "scope6@example.com")
    _svc, body = _extract(c, bearer, provider, _PORTFOLIO, _PORTFOLIO_CSV)
    workday_id = next(i["id"] for i in body["items"] if i["name"] == "Workday HCM")

    r = c.post(
        f"/tech-debt/capability-items/{workday_id}/security-classification/override",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"security_functions": []},
    )
    assert r.status_code == 422, r.text


@pytest.mark.unit
def test_a_named_security_function_overrides_a_false_flag(app_client) -> None:
    """Contradictory model output resolves toward inclusion: naming a function
    is the more specific claim, and it is the safe direction."""
    c, _TestSession, provider = app_client
    bearer = _register(c, "scope7@example.com")
    _svc, body = _extract(
        c,
        bearer,
        provider,
        [
            {
                "name": "Claroty xDome",
                "annual_cost_usd": 133000,
                "confidence_pct": 70,
                "source_row_index": 0,
                "security_related": False,
                "security_functions": ["detect"],
            }
        ],
        b"Tool,Cost\nClaroty xDome,133000\n",
    )
    item = body["items"][0]
    assert item["security_related"] is True
    assert item["security_functions"] == ["detect"]


@pytest.mark.unit
def test_omitted_classification_stays_unclassified(app_client) -> None:
    """A provider that ignores the v2 fields must not have its silence read as
    "not security-related" — that would drop the whole list out of ATT&CK."""
    c, TestSession, provider = app_client
    bearer = _register(c, "scope8@example.com")
    _svc, body = _extract(
        c,
        bearer,
        provider,
        [{"name": "Splunk Enterprise", "annual_cost_usd": 200000, "source_row_index": 0}],
        b"Tool,Cost\nSplunk Enterprise,200000\n",
    )
    item = body["items"][0]
    assert item["security_related"] is None
    assert item["security_functions"] == []
    assert "Splunk Enterprise" in _tool_names(TestSession, _tenant_id(TestSession))
