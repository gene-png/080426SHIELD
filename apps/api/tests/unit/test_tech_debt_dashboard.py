"""Client-facing Tech Debt (software portfolio) dashboard endpoint (D-035).

GET /clients/{client_id}/tech-debt/{service_id}/dashboard returns the portfolio
spend/sprawl/redundancy/savings rollup + full inventory, gated on a released
deliverable. Uses the FixtureProvider extract flow to seed real capability items.
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    db_path = tmp_path / "shield-td-dash.db"
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
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, provider


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


_ITEMS = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "function": "Endpoint detection",
        "annual_cost_usd": 195000,
        "license_count": 1500,
    },
    {
        "name": "Defender for Endpoint",
        "vendor": "Microsoft",
        "category": "EDR",
        "function": "Endpoint detection",
        "annual_cost_usd": 0,
        "license_count": 1200,
    },
    {
        "name": "CyberArk",
        "vendor": "CyberArk",
        "category": "PAM",
        "function": "Privileged access",
        "annual_cost_usd": 95000,
        "license_count": 200,
    },
    {
        "name": "BeyondTrust",
        "vendor": "BeyondTrust",
        "category": "PAM",
        "function": "Vendor remote access",
        "annual_cost_usd": 38000,
        "license_count": 150,
    },
    {
        "name": "Splunk ES",
        "vendor": "Splunk",
        "category": "SIEM",
        "function": "SOC platform",
        "annual_cost_usd": 380000,
        "license_count": None,
    },
]


def _inventory_csv() -> bytes:
    """An upload with exactly one row per item the mocked extractor returns.

    Keeps `source_rows_total` equal to `included_count` so the seeded list
    BALANCES. Anything else makes every completeness assertion in this file a
    statement about an impossible world.
    """
    nl = chr(10)
    rows = nl.join(f"{it['name']},1" for it in _ITEMS)
    return ("Tool,Cost" + nl + rows + nl).encode()


def _seed_release(c: TestClient, provider: FixtureProvider, bearer: str, *, release: bool) -> str:
    provider.register(
        "extract.capabilities",
        lambda _p: LLMResponse(
            content=json.dumps(
                {
                    "items": [
                        {**it, "notes": None, "confidence_pct": 90, "source_row_index": i}
                        for i, it in enumerate(_ITEMS)
                    ]
                }
            )
        ),
    )
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post(
        "/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "Atlas - Tech Debt"}
    ).json()["id"]
    artifact_id = c.post(
        "/artifacts",
        headers=h,
        # ONE ROW PER `_ITEMS` ENTRY, and the count is load-bearing rather than
        # decorative. `reconcile.py` records `received` from the upload's row
        # count while the mocked extractor above returns every `_ITEMS` entry, so
        # a single-row CSV produced a list reporting 5 items against 1 source row.
        #
        # `excluded_count` is `max(received - included, 0)`, which FLOORS that to
        # 0, so the impossible list read as "nothing was excluded" and every test
        # in this file asserted its completeness verdict over a reconciliation
        # that could not balance. The FIXTURE was wrong, not the assertions: a
        # test whose world is impossible says nothing about the states a real
        # list reaches, and this one hid the fourth state that
        # `test_an_unbalanced_reconciliation_never_reads_complete` now pins.
        files={
            "file": (
                "inv.csv",
                io.BytesIO(_inventory_csv()),
                "text/csv",
            )
        },
    ).json()["id"]
    ext = c.post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=h,
        json={"artifact_id": artifact_id},
    ).json()
    list_id = ext["id"]
    # Cut the two duplicate-category tools; keep the rest.
    for item in ext["items"]:
        disp = "cut" if item["name"] in ("BeyondTrust", "Defender for Endpoint") else "keep"
        c.patch(
            f"/tech-debt/capability-items/{item['id']}",
            headers=h,
            json={"disposition": disp},
        )
    c.post(f"/tech-debt/capability-lists/{list_id}/approve", headers=h)
    deliv_id = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    if release:
        rel = c.post(f"/tech-debt/deliverables/{deliv_id}/release", headers=h)
        assert rel.status_code == 200, rel.text
    return svc_id


@pytest.mark.unit
def test_tech_debt_dashboard_released(app_client) -> None:
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, provider, bearer_admin, release=True)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_applications"] == 5
    assert b["annual_spend_usd"] == 708000.0  # 195k + 0 + 95k + 38k + 380k
    assert b["identified_savings_usd"] == 38000.0  # BeyondTrust cut (Defender cut = 0)
    assert b["redundant_category_count"] == 2  # EDR + PAM
    assert len(b["items"]) == 5
    # Spend-by-category is sorted desc; SIEM (380k) leads.
    assert b["spend_by_category"][0]["category"] == "SIEM"


@pytest.mark.unit
def test_tech_debt_dashboard_unreleased_404(app_client) -> None:
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer_admin = admin["tokens"]["access_token"]
    bearer_client = client["tokens"]["access_token"]
    client_id = client["user"]["client_id"]

    svc_id = _seed_release(c, provider, bearer_admin, release=False)

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {bearer_client}"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["reason"] == "dashboard_not_released"


@pytest.mark.unit
def test_tech_debt_release_flips_the_capability_list_and_finalize_still_works(app_client) -> None:
    """W4 for Tech Debt, plus the break it would otherwise have shipped.

    Two facts in one test, because they are only dangerous together:

    1. Releasing flips `CapabilityList` to RELEASED, which makes
       `_editable_list_or_404` live — before W4 nothing outside `seed_demo.py`
       ever assigned that status, so the lock was dead code.
    2. Finalizing a SECOND deliverable version still works afterwards. The gate
       was `!= APPROVED` here while csf/zt/attack accept APPROVED or RELEASED,
       so W4 would have made a released tech-debt service unable to produce
       another report — and no test or spec covered it, because the only
       release-then-finalize coverage (`s17-documents`) runs on CSF.
    """
    c, provider = app_client
    bearer_admin = _register(c, "w4-td@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer_admin}"}
    svc_id = _seed_release(c, provider, bearer_admin, release=True)

    latest = c.get(f"/tech-debt/services/{svc_id}/capability-lists/latest", headers=h)
    assert latest.status_code == 200, latest.text
    assert latest.json()["status"] == "released"

    again = c.post(f"/tech-debt/services/{svc_id}/deliverables/finalize", headers=h)
    assert again.status_code == 201, again.text
    assert again.json()["version"] == 2


# --- #126: spend is a floor, and the card must say so ----------------------


@pytest.mark.unit
def test_spend_completeness_is_not_complete_when_an_item_has_no_cost(app_client) -> None:
    """The #126 asymmetry, stated as the assertion that would have caught it.

    An item with a NULL cost contributes 0.0 to the spend and is still counted
    in `total_applications`, so `annual_spend_usd` is a FLOOR.
    `savings_cost_known` has carried exactly this flag for the savings figure
    since it was written; the spend figure beside it carried nothing, and the
    client card labelled it "Across all tools".

    A NULL cost is seeded explicitly here rather than relying on the shared
    fixture. The fixture's Defender row is `"annual_cost_usd": 0` -- a RECORDED
    ZERO, not a missing cost -- and an earlier draft of this test read the
    existing "195k + 0 + 95k" comment as an uncosted row and asserted the
    dashboard must not report `complete`. It reports `complete`, correctly:
    a cost known to be zero is a fact, absence of a cost is not, and collapsing
    the two would be the same absent-vs-zero error this tri-state exists to
    prevent, pointed the other way.
    """
    import sqlalchemy as sa

    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)

    eng = sa.create_engine(os.environ["DATABASE_URL"], future=True)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE capability_items SET annual_cost_usd = NULL " "WHERE name = 'Splunk ES'"
            )
        )

    c.headers["X-Client-Id"] = client_id
    b = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    assert b["spend_completeness"] != "complete", (
        "a spend figure with an uncosted item claimed completeness - this is "
        "#126, the floor with no flag beside a savings figure that has one"
    )
    assert b["spend_completeness"] == "partial"
    # Splunk ES is a KEEP item, chosen deliberately. Nulling a CUT item would
    # flip `savings_cost_known` too, and the assertion below would then pass for
    # the wrong reason -- it is here to show the SPEND floor is tracked on its
    # own rather than inherited from the savings flag, which is the entire
    # asymmetry #126 is about.
    assert b["savings_cost_known"] is True


@pytest.mark.unit
def test_the_dashboard_can_express_an_exclusion_at_all(app_client) -> None:
    """The excluded-rows half was not undisclosed - it was INEXPRESSIBLE.

    `tech_debt/exporters.py` has derived `source_rows_total` / `included_count`
    / `excluded_count` since N-010 and the released PDF prints them. The
    dashboard response had no field for any of the three, so a client card
    could not have disclosed an exclusion even if someone had wanted it to.
    This asserts the fields exist and are populated, which is the precondition
    for the disclosure rather than the disclosure itself.
    """
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)

    c.headers["X-Client-Id"] = client_id
    b = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    for field in ("source_rows_total", "included_count", "excluded_count"):
        assert field in b, f"{field} is absent - the exclusion cannot be disclosed"
    # Source-derived items only, matching `build_context`, so decomposing a
    # bundle can never move the arithmetic.
    assert b["included_count"] == b["total_applications"]
    assert b["excluded_count"] >= 0


@pytest.mark.unit
def test_unknown_is_its_own_state_and_not_folded_into_complete(app_client) -> None:
    """A bool could not carry this, which is why it is a tri-state.

    A list whose `source_rows_total` is NULL was never reconciled - pre-0036,
    or never cut by an extraction. "Nothing was excluded" and "whether anything
    was excluded was never recorded" are different claims, and reporting the
    second as the first is what let the exporter print "Total annual cost" over
    an unreconciled figure.
    """
    import sqlalchemy as sa

    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)

    eng = sa.create_engine(os.environ["DATABASE_URL"], future=True)
    with eng.begin() as conn:
        conn.execute(sa.text("UPDATE capability_lists SET source_rows_total = NULL"))

    c.headers["X-Client-Id"] = client_id
    b = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    assert b["source_rows_total"] is None
    assert b["spend_completeness"] == "unknown", (
        "a list that was never reconciled reported a completeness verdict it " "has no basis for"
    )
    assert b["excluded_count"] == 0, "the derivation floors - that is the trap"


@pytest.mark.unit
def test_an_unbalanced_reconciliation_never_reads_complete(app_client) -> None:
    """The FOURTH state, which the three-valued label folds into "complete".

    `excluded_count` is `max(source_rows_total - included_count, 0)`. When more
    items exist than there were source rows -- two items attributed to one
    `source_row_index`, the case `build_context` already records for the
    exporter -- the subtraction floors to 0. With every cost known, the
    excluded-count branch and the uncosted branch both fall through, and the
    card claimed "complete": "every source row is accounted for", asserted over
    an accounting that cannot balance.

    Strictly worse than the exporter's version of the same hole, which merely
    fails to disclose. This one makes the affirmative claim, on a client-facing
    surface, and the dashboard's comment said it derived the count "the same
    way as the exporter" while carrying neither the caveat nor a test.

    "partial" is not a perfect word for it -- nothing is known to be MISSING --
    but of the three available it is the only one that is not a false claim,
    and unreliable data resolves to unconfirmed rather than to confirmed.
    """
    import sqlalchemy as sa

    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)

    c.headers["X-Client-Id"] = client_id
    url = f"/clients/{client_id}/tech-debt/{svc_id}/dashboard"
    auth = {"Authorization": f"Bearer {client['tokens']['access_token']}"}

    # POSITIVE CONTROL first: as seeded and balanced, this list is allowed to
    # say "complete". Without this the assertion below passes for a guard that
    # simply never returns "complete".
    before = c.get(url, headers=auth).json()
    assert before["spend_completeness"] == "complete", before["spend_completeness"]
    included = before["included_count"]

    # Now make the reconciliation impossible: fewer source rows than items.
    eng = sa.create_engine(os.environ["DATABASE_URL"], future=True)
    with eng.begin() as conn:
        conn.execute(
            sa.text("UPDATE capability_lists SET source_rows_total = :n"),
            {"n": included - 1},
        )

    after = c.get(url, headers=auth).json()
    assert after["included_count"] > after["source_rows_total"]
    assert after["excluded_count"] == 0, "the derivation floors - that is the trap"
    assert after["spend_completeness"] != "complete", (
        "an accounting that does not balance reported every source row as " "accounted for"
    )
    assert after["spend_completeness"] == "partial"


@pytest.mark.unit
def test_a_recorded_zero_cost_is_not_a_missing_cost(app_client) -> None:
    """The other direction, and the reason the tri-state is not just a bool.

    The seeded list contains `"annual_cost_usd": 0` for Defender for Endpoint.
    That is a cost that was recorded and happens to be zero, not an absent one,
    and a dashboard that called it incomplete would be making the same
    absent-versus-zero error as the defect - facing the other way.

    Without this, a guard that reported "partial" for everything would satisfy
    every other assertion in this file while making the field meaningless.
    """
    c, provider = app_client
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    svc_id = _seed_release(c, provider, admin["tokens"]["access_token"], release=True)

    c.headers["X-Client-Id"] = client_id
    b = c.get(
        f"/clients/{client_id}/tech-debt/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    ).json()

    assert b["spend_completeness"] == "complete", (
        "a recorded zero was treated as a missing cost - absence and zero are "
        "different facts and this is the tri-state's whole point"
    )
