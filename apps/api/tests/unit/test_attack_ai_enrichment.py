"""Item 7 / plan part 1B: send the model what the extractor already knows.

The Tech Debt extractor produces `vendor`, `category` and — most usefully —
`security_functions`, its own prevent/detect/respond classification. All of it
was discarded. The pipeline computed "Falcon does detect + respond", threw that
away, sent the bare string `"CrowdStrike Falcon"`, and asked the model to
re-derive detection / prevention / response from the name alone.

The load-bearing design decision, because it interacts with D-053:

    `name` and `vendor` come from the APPROVED SNAPSHOT.
    `category` and `security_functions` are read LIVE.

That is not a compromise, it is the distinction D-053 is actually about.
W3 froze *membership* — which tools may be cited — because an approved list stays
editable and a citation "confirmed against the approved list" was being checked
against whatever the list had since become. `name` and `vendor` are what the
resolver matches on, so they define membership and must stay frozen.
`category` and `security_functions` describe a tool that is already citable; a
consultant re-classifying one after approval should improve the next run's input,
not be ignored until re-approval.

The snapshot carries `item_id`, which is what makes reading the descriptive half
live possible at all without loosening the frozen half.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus


@pytest.fixture()
def db_and_client(tmp_path) -> Iterator[tuple[sessionmaker, uuid.UUID]]:
    url = f"sqlite:///{tmp_path / 'shield-enrich.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield TestSession, uuid.uuid4()


def _seed_list(
    TestSession: sessionmaker,
    client_id: uuid.UUID,
    *,
    status: CapabilityListStatus,
    items: list[dict],
    snapshot: bool = False,
) -> None:
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="TD",
            client_id=client_id,
            opened_by=uuid.uuid4(),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=status)
        db.add(cl)
        db.flush()
        rows = []
        for spec in items:
            row = CapabilityItem(capability_list_id=cl.id, **spec)
            db.add(row)
            rows.append(row)
        db.flush()
        if snapshot:
            # Exactly the shape `approve_capability_list` writes.
            cl.approved_membership = [
                {"item_id": str(r.id), "name": r.name, "vendor": r.vendor} for r in rows
            ]
        db.commit()


@pytest.mark.unit
def test_the_payload_carries_the_structured_fields_not_bare_names(db_and_client) -> None:
    """The whole point of 1B. Four fields, and only four."""
    from app.routes.attack import _client_capability_inputs

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.DRAFT,
        items=[
            {
                "name": "CrowdStrike Falcon",
                "vendor": "CrowdStrike",
                "category": "EDR",
                "security_functions": ["detect", "respond"],
                "annual_cost_usd": 350000,
            }
        ],
    )
    with TestSession() as db:
        inputs = _client_capability_inputs(db, cid)

    assert len(inputs) == 1
    got = inputs[0]
    assert got.name == "CrowdStrike Falcon"
    assert got.vendor == "CrowdStrike"
    assert got.category == "EDR"
    assert got.security_functions == ["detect", "respond"]


@pytest.mark.unit
def test_cost_and_licence_never_egress(db_and_client) -> None:
    """A deliberate privacy boundary, not an oversight.

    Cost and licence count are irrelevant to mapping a technique and the
    redactor should not have to reason about them. Asserted on the serialised
    payload rather than on the dataclass, because that is what leaves the
    building.
    """
    from app.routes.attack import _capability_payload, _client_capability_inputs

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.DRAFT,
        items=[
            {
                "name": "Splunk Enterprise",
                "vendor": "Splunk",
                "category": "SIEM",
                "security_functions": ["detect"],
                "annual_cost_usd": 500000,
                "license_count": 900,
                "notes": "renewal in Q3, ask about the discount",
            }
        ],
    )
    with TestSession() as db:
        payload = _capability_payload(_client_capability_inputs(db, cid))

    assert payload == [
        {
            "name": "Splunk Enterprise",
            "vendor": "Splunk",
            "category": "SIEM",
            "security_functions": ["detect"],
        }
    ]
    blob = repr(payload)
    for leak in ("500000", "900", "renewal", "discount"):
        assert leak not in blob, f"{leak!r} reached the egress payload"


@pytest.mark.unit
def test_an_approved_list_takes_names_from_the_snapshot_and_description_live(
    db_and_client,
) -> None:
    """The D-053 interaction, which is the reason this function exists at all.

    `name`/`vendor` define membership — the resolver matches on them — so they
    stay frozen at approval. `category`/`security_functions` describe a tool that
    is *already* citable, so a consultant re-classifying one after approval
    should reach the next run rather than waiting for re-approval.

    Here the live row has been renamed AND re-classified since approval. The
    rename must be ignored (frozen membership); the re-classification must land.
    """
    from app.routes.attack import _client_capability_inputs

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.APPROVED,
        snapshot=True,
        items=[
            {
                "name": "Defender for Endpoint",
                "vendor": "Microsoft",
                "category": "EDR",
                "security_functions": ["detect"],
            }
        ],
    )
    with TestSession() as db:
        row = db.query(CapabilityItem).one()
        row.name = "Defender for Endpoint (renamed after approval)"
        row.security_functions = ["detect", "prevent", "respond"]
        row.category = "XDR"
        db.commit()

    with TestSession() as db:
        got = _client_capability_inputs(db, cid)[0]

    assert got.name == "Defender for Endpoint", (
        "a post-approval rename moved the allow-list — this is exactly what D-053 "
        "froze the snapshot to prevent"
    )
    assert got.security_functions == ["detect", "prevent", "respond"]
    assert got.category == "XDR"


@pytest.mark.unit
def test_a_snapshot_row_whose_live_item_is_gone_stays_citable_without_enrichment(
    db_and_client,
) -> None:
    """Fail-safe direction: membership is frozen, description is best-effort.

    If the live row is deleted, there is nothing to enrich from — but the tool
    was approved and must remain citable, or a deletion would silently narrow the
    allow-list, which is #96 exactly.
    """
    from app.routes.attack import _client_capability_inputs

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.APPROVED,
        snapshot=True,
        items=[{"name": "Tenable.io", "vendor": "Tenable", "category": "Vuln Management"}],
    )
    with TestSession() as db:
        db.delete(db.query(CapabilityItem).one())
        db.commit()

    with TestSession() as db:
        got = _client_capability_inputs(db, cid)

    assert [c.name for c in got] == ["Tenable.io"]
    assert got[0].vendor == "Tenable"
    assert got[0].category is None
    assert got[0].security_functions == []


@pytest.mark.unit
def test_the_hard_allow_list_is_unchanged_by_enrichment(db_and_client) -> None:
    """`_client_tool_names` is a HARD allow-list and several callers depend on it.

    Enrichment adds fields; it must not add or remove a single citable name. An
    empty allow-list once produced 607 fabricated gaps (N-033), so this function
    changing shape is not a refactor.
    """
    from app.routes.attack import _client_capability_inputs, _client_tool_names

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.DRAFT,
        items=[
            {"name": "Wiz", "vendor": "Wiz, Inc.", "category": "CNAPP"},
            {"name": "Okta Workforce Identity", "vendor": "Okta", "category": "IAM"},
        ],
    )
    with TestSession() as db:
        names = _client_tool_names(db, cid)
        enriched = [c.name for c in _client_capability_inputs(db, cid)]

    assert names == sorted(names), "callers rely on a stable order"
    assert set(names) == set(enriched)


@pytest.mark.unit
def test_unapproved_contributing_names_reports_what_is_actually_sent(db_and_client) -> None:
    """#33 finding 6/7, re-derived rather than ported -- and the port would have
    been backwards.

    #29's branch reported tools "excluded until approved" and counted DRAFT rows.
    On `main` a DRAFT list CONTRIBUTES: `_client_capability_inputs` says so in
    terms -- "Only DISCARDED is excluded here: DRAFT still counts". Porting that
    copy would have told the consultant the exact opposite of what the code does,
    and #33 finding 7 is the record of the two branches diverging on it.

    So the disclosure is inverted: not "these are held back" but "these are going
    out, and nobody has signed them off". That is actionable before a run is
    spent; the other is a false alarm.

    The first draft of this test asserted #29's model and returned `[]`, which is
    how the divergence was caught.
    """
    from app.routes.attack import _unapproved_contributing_names

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.APPROVED,
        snapshot=True,
        items=[{"name": "Wiz"}, {"name": "Splunk Enterprise"}],
    )
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.DRAFT,
        items=[{"name": "Tenable.io"}],
    )

    with TestSession() as db:
        sent = {
            c.name
            for c in __import__("app.routes.attack", fromlist=["x"])._client_capability_inputs(
                db, cid
            )
        }
        unapproved = _unapproved_contributing_names(db, cid)

    assert "Tenable.io" in sent, "a DRAFT list contributes on main; the fixture is wrong"
    assert unapproved == [
        "Tenable.io"
    ], "the draft-sourced tool being sent was not disclosed as unapproved"


@pytest.mark.unit
def test_unapproved_disclosure_matches_case_insensitively(db_and_client) -> None:
    """`SPLUNK` on a draft and `Splunk` in scope are the same tool.

    Reported ONCE, under the spelling actually being sent. Which spelling that
    is comes from the existing dedupe in `_client_capability_inputs`: it sorts
    and keeps the first, so `SPLUNK ENTERPRISE` beats `Splunk Enterprise` on
    ASCII ordering and the DRAFT's capitalisation is what the model sees, even
    though the approved list spells it differently.

    That is pre-existing and cosmetic -- the resolver dedupes case-insensitively,
    so a citation of either spelling resolves -- but it is worth knowing that an
    approved list does not win the spelling contest. Asserted here as the
    behaviour rather than the preference, because this test's first draft
    asserted the preference and was simply wrong about what the code does.
    """
    from app.routes.attack import _unapproved_contributing_names

    TestSession, cid = db_and_client
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.APPROVED,
        snapshot=True,
        items=[{"name": "Splunk Enterprise"}],
    )
    _seed_list(
        TestSession,
        cid,
        status=CapabilityListStatus.DRAFT,
        items=[{"name": "SPLUNK ENTERPRISE"}],
    )

    with TestSession() as db:
        assert _unapproved_contributing_names(db, cid) == ["SPLUNK ENTERPRISE"]
