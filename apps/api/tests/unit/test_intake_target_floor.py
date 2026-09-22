"""The target FLOOR is refused with client copy, not with a schema dump (#406).

## What changed, and why the schema bound was the defect

`csf_target_tier` and `zt_target_stage` carried `Field(..., ge=2, le=4)` on
both `ServiceRequestInput` and `EngagementCreateRequest`. Measured at
`1281cbd`, `POST /intake/submit` with `csf_target_tier: 1` returned:

    {"error": {"code": 422, "message": "Request validation failed.",
               "reason": "schema_greater_than_equal",
               "details": [{"msg": "Input should be greater than or equal to 2",
                            "loc": [...], "ctx": {"ge": 2}}]}}

`CLAUDE.md` records the shape: a declarative bound opts a route out of the
typed-error convention while looking like MORE validation. The reason is a
`schema_*` machine token with no client copy behind it, and `serverReason` in
`apps/web/src/lib/describe-save-error.ts` withholds every `schema_*` code by
design -- so the client's intake wizard showed the bare fallback "Failed to
submit intake." with nothing naming the field, the range, or what to do.

**The correction is deliberate and matters:** the raw Pydantic `msg` did NOT
reach the screen, because `describe-save-error.ts` guards it. It DID reach the
browser, in `error.details`, one careless consumer away from #317. The defect
fixed here is the client being told nothing, not a string already on a page.

## Why both the `ge` and the `le` half went

The floor was the ruling; the ceiling follows from the same deciding fact.
Left declarative, one field would answer two ways depending on the MAGNITUDE
of the mistake -- tier 1 typed, tier 5 a raw dump; DoD stage 4 typed (the #125
guard), CISA stage 5 a raw dump. A client meets whichever it happens to hit.

## Why this suite calls the ENDPOINT and not the schema

`CLAUDE.md`: #195's schema tests stayed green with the route pointed at the
wrong model, because they pinned two Pydantic models while the defect was
which model the handler NAMES. Both writers of these columns are exercised --
`/intake/submit` and `/intake/engagements` -- because they reach
`_validate_targets` by different paths: the first takes `ServiceRequestInput`
straight off the body, the second RECONSTRUCTS one from
`EngagementCreateRequest`. Removing a bound from one model and not the other
leaves a live hole that a single-route test cannot see.
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

from app.assessment_targets import MIN_TARGET_STAGE, MIN_TARGET_TIER

# `_register_and_bearer` is a plain helper, so importing it is free. The FIXTURE
# is declared locally instead, which every one of the fifty-odd unit modules
# here does: a cross-module fixture import makes the parameter shadow the
# imported name, and ruff refuses it as F811 on every test that takes it.
from tests.unit.test_intake_routes import _register_and_bearer


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker]]:
    db_path = tmp_path / "shield-intake-floor.db"
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


def _submit(client, bearer, request_body):
    return client.post(
        "/intake/submit",
        headers={"Authorization": f"Bearer {bearer}"},
        json={
            "client": {"legal_name": "Atlas Defense Solutions"},
            "service_requests": [request_body],
        },
    )


def _engagement(client, bearer, request_body):
    """POST /intake/engagements, with the org profile the route requires.

    Without the PATCH the route refuses at an EARLIER guard -- "Complete your
    organization profile in intake before starting an engagement." -- which is
    also a 422 and would have let every assertion below pass over a refusal
    that had nothing to do with the target. Found by writing the test first:
    it failed on a missing `reason` key rather than on a wrong one.
    """
    headers = {"Authorization": f"Bearer {bearer}"}
    patched = client.patch(
        "/intake",
        headers=headers,
        json={"client": {"legal_name": "Atlas Defense Solutions"}},
    )
    assert patched.status_code == 200, patched.text
    return client.post("/intake/engagements", headers=headers, json=request_body)


def _typed_error(response):
    """The `{reason, message}` detail, asserting it is not a schema dump.

    `app/exceptions.py` rewraps a dict detail into `{"error": {...}}`, so both
    the typed refusal and the schema rejection arrive under the same key. What
    tells them apart is the reason's namespace and the presence of `details`.
    """
    assert response.status_code == 422, response.text
    err = response.json()["error"]
    # Named rather than left to KeyError: a 422 from a DIFFERENT guard on the
    # same route carries a string detail and no `reason` at all, and that is
    # the shape a mis-set-up fixture produces.
    assert "reason" in err, f"no typed reason -- refused by another guard? {err}"
    assert not err["reason"].startswith("schema_"), err
    assert "details" not in err, err
    assert err["message"] != "Request validation failed.", err
    return err


# --------------------------------------------------------------------------
# CSF tier
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("route", ["submit", "engagements"])
def test_csf_tier_below_the_floor_is_refused_with_client_copy(app_client, route) -> None:
    client, _ = app_client
    bearer = _register_and_bearer(client)
    body = {"service_type": "nist_csf", "csf_target_tier": 1, "csf_profile": "MOD"}

    r = _submit(client, bearer, body) if route == "submit" else _engagement(client, bearer, body)

    err = _typed_error(r)
    assert err["reason"] == "csf_target_tier_out_of_range", err
    # The CAUSE, not the check: Tier 1 exists, and is not a thing to aim at.
    assert "Tier 1" in err["message"], err["message"]
    assert "Tier 2" in err["message"], err["message"]


@pytest.mark.unit
@pytest.mark.parametrize("route", ["submit", "engagements"])
def test_csf_tier_above_the_ladder_is_refused_with_client_copy(app_client, route) -> None:
    """A tier CSF does not have. A different cause, so a different sentence."""
    client, _ = app_client
    bearer = _register_and_bearer(client)
    body = {"service_type": "nist_csf", "csf_target_tier": 5, "csf_profile": "MOD"}

    r = _submit(client, bearer, body) if route == "submit" else _engagement(client, bearer, body)

    err = _typed_error(r)
    assert err["reason"] == "csf_target_tier_out_of_range", err
    assert "tiers 1-4" in err["message"], err["message"]
    assert "5" in err["message"], err["message"]


@pytest.mark.unit
@pytest.mark.parametrize("tier", [2, 3, 4])
def test_every_tier_a_client_may_target_still_submits(app_client, tier) -> None:
    """Positive controls. A guard refusing every tier would satisfy the 422s."""
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _submit(
        client,
        bearer,
        {"service_type": "nist_csf", "csf_target_tier": tier, "csf_profile": "MOD"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["service_requests"][0]["csf_target_tier"] == tier


# --------------------------------------------------------------------------
# ZT stage
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("service_type", ["zero_trust_cisa", "zero_trust_dod"])
@pytest.mark.parametrize("route", ["submit", "engagements"])
def test_zt_stage_below_the_floor_is_refused_with_client_copy(
    app_client, service_type, route
) -> None:
    """Stage 1 is a starting point. Both frameworks have one; neither offers it.

    Parametrised over the framework because the floor is the one part of this
    rule that does NOT vary with the ladder, and a test run against a single
    framework cannot tell a shared floor from a per-framework coincidence.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)
    body = {"service_type": service_type, "zt_target_stage": 1}

    r = _submit(client, bearer, body) if route == "submit" else _engagement(client, bearer, body)

    err = _typed_error(r)
    assert err["reason"] == "zt_target_stage_out_of_range", err
    assert "Stage 1" in err["message"], err["message"]
    assert "Stage 2" in err["message"], err["message"]


@pytest.mark.unit
@pytest.mark.parametrize("route", ["submit", "engagements"])
def test_zt_stage_above_the_ladder_is_refused_with_client_copy(app_client, route) -> None:
    """CISA ends at 4, so stage 9 was the `le=4` raw dump. Now typed.

    This is the half the schema bound owned. `_validate_targets` already
    refused DoD Stage 4 (#125) with a typed reason, so the same field answered
    a client in two different shapes depending on how far out the value was.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)
    body = {"service_type": "zero_trust_cisa", "zt_target_stage": 9}

    r = _submit(client, bearer, body) if route == "submit" else _engagement(client, bearer, body)

    err = _typed_error(r)
    assert err["reason"] == "zt_target_stage_out_of_range", err
    assert "stages 1-4" in err["message"], err["message"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("service_type", "stage"),
    [
        ("zero_trust_cisa", 2),
        ("zero_trust_cisa", 3),
        ("zero_trust_cisa", 4),
        ("zero_trust_dod", 2),
        ("zero_trust_dod", 3),
    ],
)
def test_every_stage_a_client_may_target_still_submits(app_client, service_type, stage) -> None:
    """Positive controls, per framework. DoD's ladder ends at 3 and CISA's at 4."""
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _submit(client, bearer, {"service_type": service_type, "zt_target_stage": stage})
    assert r.status_code == 200, r.text
    assert r.json()["service_requests"][0]["zt_target_stage"] == stage


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [
        {"service_type": "nist_csf", "csf_target_tier": 2, "csf_profile": "MOD"},
        {"service_type": "nist_csf", "csf_target_tier": 4, "csf_profile": "HIGH"},
        {"service_type": "zero_trust_cisa", "zt_target_stage": 4},
        {"service_type": "zero_trust_dod", "zt_target_stage": 3},
    ],
)
def test_the_engagements_route_still_accepts_every_legal_target(app_client, body) -> None:
    """Positive controls on the OTHER writer.

    Both models lost their bounds, and a guard that refused everything on this
    route would satisfy every 422 assertion above without anyone noticing that
    starting an engagement had stopped working.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _engagement(client, bearer, body)
    assert r.status_code == 201, r.text


# --------------------------------------------------------------------------
# RANGE is not conditional on service_type. The removed bound was not either.
# --------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("csf_target_tier", -99, "csf_target_tier_out_of_range"),
        ("csf_target_tier", 99, "csf_target_tier_out_of_range"),
        ("zt_target_stage", -99, "zt_target_stage_out_of_range"),
        ("zt_target_stage", 99, "zt_target_stage_out_of_range"),
    ],
)
def test_a_target_on_a_service_that_does_not_use_it_is_still_range_checked(
    app_client, field, value, reason
) -> None:
    """The schema bound ran for every item. The guard replacing it must too.

    `submit_intake` writes BOTH columns for every `ServiceRequest` it creates,
    whatever the `service_type` -- so a range check sited inside the
    `if NIST_CSF / elif ZT` branches that check PRESENCE silently stopped
    running for `tech_debt`, `attack_coverage` and `consultation`. At `1281cbd`
    `Field(ge=2, le=4)` refused `{"service_type": "tech_debt",
    "csf_target_tier": -99}`; the first draft of this PR returned 200 and
    stored -99.

    No reader renders such a value today, which is exactly why it is fixed
    rather than excused: a storage-only hole is indistinguishable from an
    oversight to whoever inherits the column.

    `tech_debt` is used because it needs neither target, so nothing about the
    request makes the field plausible -- and because it is not in
    `SELF_ASSESSMENT_TYPES`, so it cannot be reached through the engagements
    route at all.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)

    r = _submit(client, bearer, {"service_type": "tech_debt", field: value})

    err = _typed_error(r)
    assert err["reason"] == reason, err


@pytest.mark.unit
def test_a_service_that_needs_no_target_still_submits_without_one(app_client) -> None:
    """Positive control for the test above.

    Range-checking every value that arrives must not start DEMANDING one: a
    guard that refused `tech_debt` outright would satisfy every assertion
    above while breaking the most ordinary request on the route.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)
    r = _submit(client, bearer, {"service_type": "tech_debt"})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------
# The refusal names a product, not a database identifier
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_the_ceiling_refusal_names_the_product_not_the_enum(app_client) -> None:
    """`clientFacingError` renders this sentence verbatim to a client.

    It read "zero_trust_dod has stages 1-3; 4 is not one of them." -- a StrEnum
    value in client copy -- while the CSF branch twelve lines up said
    "NIST CSF 2.0", so the inconsistency sat inside one guard. Both halves are
    pinned: the product name must appear AND the enum must not, so a revert
    fails here rather than passing on the surviving substring.
    """
    client, _ = app_client
    bearer = _register_and_bearer(client)

    r = _submit(client, bearer, {"service_type": "zero_trust_dod", "zt_target_stage": 4})

    err = _typed_error(r)
    assert "Zero Trust (DoD ZTRA)" in err["message"], err["message"]
    assert "zero_trust_dod" not in err["message"], err["message"]


# --------------------------------------------------------------------------
# The bound is gone from the SCHEMA, which is the thing that made the dump
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_no_intake_target_field_carries_a_declarative_range_bound() -> None:
    """No declarative bound on any of the four, however WIDE.

    **A first draft of this docstring claimed the route tests above would stay
    green with `ge=2` restored, and that is false** -- measured by restoring
    `ge=2, le=4` on `ServiceRequestInput.csf_target_tier`, which reddened four
    of them. `_typed_error` refuses a `schema_*` reason, so a bound that
    rejects a value a route test sends is caught there. The claim was written
    from a plausible mechanism nobody ran, which is the shape `CLAUDE.md`
    records under a correct change with a justification that does not survive
    contact with the code.

    The change stays, and the reason is rewritten to the one that holds: a
    bound WIDER than the guard -- `ge=1, le=9` -- is invisible to every test
    above, because no value any of them sends would reach it. It would sit
    there looking like validation, and the next person to narrow it would
    reinstate #406 without tripping anything. This assertion is about the
    DECLARATION rather than a response, so it can see that and they cannot.
    """
    from app.schemas.intake import EngagementCreateRequest, ServiceRequestInput

    for model in (ServiceRequestInput, EngagementCreateRequest):
        for name in ("csf_target_tier", "zt_target_stage"):
            field = model.model_fields[name]
            bounds = [m for m in field.metadata if hasattr(m, "ge") or hasattr(m, "le")]
            assert bounds == [], (
                f"{model.__name__}.{name} carries {bounds}. A declarative bound "
                f"here is refused as a raw `schema_*` 422 with no client copy; "
                f"the range lives in `routes/intake.py::_validate_targets`."
            )


# --------------------------------------------------------------------------
# The cross-language copy
# --------------------------------------------------------------------------


@pytest.mark.unit
def test_the_floor_is_the_number_the_web_bundle_spells_out() -> None:
    """Both floors, spelled rather than imported, so a Python-side edit is loud.

    There is no build step shared by this app and the web bundle.
    `SCHEMA_REASON_PREFIX` faced the identical problem one module over and
    settled it this way: spell the literal in each language's own suite, and
    name the other file in the failure.

    **What this closes, stated exactly:** a change on THIS side goes red here,
    naming the file that must change with it. It does NOT prove the two agree,
    so an author who updates both this number and this assertion and stops has
    not been stopped.

    **What it is NOT is the best available check, and this docstring used to
    claim otherwise** -- it said the api container "mounts `./apps/api` alone",
    so no test on either side could read across. Measured: the api service also
    mounts `./pyproject.toml:ro` and `./packages/zt-data:/packages/zt-data:ro`,
    the latter added expressly so a contract test could read a tree outside the
    app. A real parity check is a compose line away; it is deferred on SCOPE
    (a `docker-compose.yml` edit is merge-rule condition 5) and tracked in
    **#422**, not because it is impossible.
    """
    assert MIN_TARGET_TIER == 2, (
        "apps/web/src/lib/assessment-targets.ts spells this too, as "
        "MIN_TARGET_TIER, and derives CSF_TARGET_TIERS from it. Change both."
    )
    assert MIN_TARGET_STAGE == 2, (
        "apps/web/src/lib/assessment-targets.ts spells this too, as "
        "MIN_TARGET_STAGE, and derives both ZT_TARGET_STAGES from it. Change both."
    )
