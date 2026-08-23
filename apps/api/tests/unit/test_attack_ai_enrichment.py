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
            # Seeded through the PRODUCTION writer, not a hand-written copy of
            # its shape. The first version of this fixture built the dicts here
            # under the comment "exactly the shape `approve_capability_list`
            # writes" -- which is a promise the fixture cannot keep. Rename
            # `item_id` in the writer and every test in this file would stay
            # green while the live join silently returned nothing and every tool
            # lost its category and security functions.
            #
            # Calling the real writer also picks up `security_scope_filter()`,
            # which the hand-written version skipped, so the snapshot-vs-scope
            # interaction is now exercised rather than assumed.
            from app.routes.tech_debt import build_approved_membership

            cl.approved_membership = build_approved_membership(db, cl.id)
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

    # Derived from what was SEEDED, not from the function under test. The first
    # version asserted `set(names) == set(enriched)` -- but `_client_tool_names`
    # is a projection of `_client_capability_inputs`, so that compared a function
    # with itself and was true by construction. It would have passed with the
    # allow-list empty, which is the one outcome it exists to forbid (N-033: an
    # empty allow-list once wrote 607 fabricated gaps).
    assert names == ["Okta Workforce Identity", "Wiz"], names
    assert names == sorted(names), "callers rely on a stable order"
    assert set(names) == set(enriched), "the two views of one query disagree"


# The `_unapproved_contributing_names` disclosure and its two tests moved OUT of
# this PR. The reviewer found them unwired -- nothing in any route, schema or
# component called the function, so a "fact a consultant can act on" reached
# nobody -- and, separately, wrong: it reports a tool as unapproved whenever it
# appears on a draft list, even when it is ALSO on an approved one, which for a
# client with an open v2 draft re-listing the same 40 tools would flag all 40.
#
# Shipping it unwired would have been a guard that cannot fire; shipping it wired
# would have been a false alarm. It belongs with `AttackAiInputsPanel` in item
# 7's second PR, where it has a consumer and where the approved-list exclusion
# can be asserted end to end.
#
# The lesson it was carrying is preserved in #33's comment thread: #29's branch
# reported these tools as "excluded until approved", and on `main` a DRAFT list
# CONTRIBUTES, so a straight port would have told the consultant the opposite of
# what the code does.
