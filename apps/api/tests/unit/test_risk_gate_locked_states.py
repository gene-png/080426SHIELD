"""#1081, ruling (ii) (#736 6115773247; copy (B) for CSF/ZT replaced in #1081
comment 6116102972): a locked Risk Register says what to do, per missing kind.

The gate reports, per requirement (ATT&CK; CSF or Zero Trust), WHY it is
unmet:
- `no_assessment` (A): a service of that kind is engaged and has no live
  assessment, discarded-only included;
- `unpublished` (A, "Publish for processing"): no service, but the client's
  request for one is waiting in the Intake Queue (not fulfilled, not declined);
- `archived_only` (D): a live assessment exists only under an archived service;
- `no_service` (B): none of those.

The gate's `locked_message` and generate's 409 carry the approved copy, one
sentence per missing kind and then the closing line. Every expected string is
written out here from the issue text, never imported.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.service_request import ServiceRequest, ServiceType
from app.models.user import User
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _seed_attack_and_zt,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

ATTACK = "MITRE ATT&CK Coverage Mapping"
CSF = "NIST CSF 2.0 Assessment"
ZT_CISA = "Zero Trust Assessment (CISA ZTMM 2.0)"

B_ATTACK = (
    "Acme has no MITRE ATT&CK Coverage Mapping service. A client adds it by selecting "
    "MITRE ATT&CK Coverage Mapping in the Services step of its intake; there is no "
    "control here to add it."
)
B_CSF_ZT = (
    "Acme has no NIST CSF 2.0 Assessment or Zero Trust service. The client can add one "
    "by selecting it in the Services step of its intake, or by starting a "
    "self-assessment from My Assessments."
)
CLOSING = (
    "A draft assessment is enough to generate a draft register; approve the "
    "assessments before you publish it."
)


def _a(label: str) -> str:
    return (
        f"Acme's {label} service has no assessment in progress. In Intake Queue, open "
        "Acme, click Open workspace → on that service, then click Start assessment."
    )


def _a_unpublished(label: str) -> str:
    return (
        f"Acme's {label} service has no assessment in progress. In Intake Queue, open "
        "Acme, click Publish for processing on that service, then Open workspace "
        "→, then Start assessment."
    )


def _d(label: str, b: str) -> str:
    return (
        f"Acme's {label} assessment is under an archived service, and an archived "
        f"service cannot be restored. Acme needs a new {label} service: {b}"
    )


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def _gate(c, bearer: str, cid: str) -> dict:
    r = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid))
    assert r.status_code == 200, r.text
    return r.json()


def _states(g: dict) -> list[tuple]:
    return [(x["requirement"], x["state"], x["service_kind"]) for x in g["locked_inputs"]]


def _assert_locked(c, bearer: str, cid: str, states: list[tuple], message: str) -> None:
    """The gate and generate's 409 say the same thing."""
    g = _gate(c, bearer, cid)
    assert g["unlocked"] is False, g
    assert _states(g) == states, g["locked_inputs"]
    assert g["locked_message"] == message, g["locked_message"]
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=_h(bearer, cid))
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert (err["reason"], err["message"]) == ("risk_register_locked", message), err


def _service(c, bearer: str, cid: str, area: str, kind: str) -> str:
    r = c.post(f"/{area}/services", headers=_h(bearer, cid), json={"kind": kind, "title": kind})
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _assessment(c, bearer: str, cid: str, area: str, svc: str) -> str:
    r = c.post(f"/{area}/services/{svc}/assessments", headers=_h(bearer, cid))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _archive(c, bearer: str, cid: str, svc: str) -> None:
    r = c.delete(f"/admin/services/{svc}", headers=_h(bearer, cid))
    assert r.status_code == 204, r.text


def _request(cid: str, service_type: ServiceType, *, declined: bool = False) -> str:
    """A client's service request as intake submit writes it (setup only).
    Returns its id."""
    from datetime import UTC, datetime

    with _session() as db:
        user = db.query(User).filter(User.email == "admin@kentro.example").one()
        sr = ServiceRequest(
            service_type=service_type,
            client_id=uuid.UUID(cid),
            requested_by=user.id,
            declined_at=datetime.now(UTC) if declined else None,
        )
        db.add(sr)
        db.commit()
        return str(sr.id)


def _publish(c, bearer: str, cid: str, request_id: str) -> str:
    """The real "Publish for processing" route; returns the service it opens."""
    r = c.post(f"/admin/service-requests/{request_id}/fulfill", headers=_h(bearer, cid))
    assert r.status_code in (200, 201), r.text
    return r.json()["service_id"]


def _live_attack(c, bearer: str, cid: str) -> str:
    svc = _service(c, bearer, cid, "attack", "attack_coverage")
    _assessment(c, bearer, cid, "attack", svc)
    return svc


# --- B: no service ------------------------------------------------------------------


def test_b_no_service_of_either_kind(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "no_service", None), ("csf_or_zt", "no_service", None)],
        f"{B_ATTACK} {B_CSF_ZT} {CLOSING}",
    )


def test_b_a_declined_request_is_no_service(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    _request(cid, ServiceType.NIST_CSF, declined=True)
    _assert_locked(c, bearer, cid, [("csf_or_zt", "no_service", None)], f"{B_CSF_ZT} {CLOSING}")


# --- A: an engaged service with no live assessment -------------------------------------


def test_a_an_engaged_service_with_no_assessment(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _service(c, bearer, cid, "attack", "attack_coverage")
    _service(c, bearer, cid, "zt", "zero_trust_cisa")
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("attack", "no_assessment", "attack_coverage"),
            ("csf_or_zt", "no_assessment", "zero_trust_cisa"),
        ],
        f"{_a(ATTACK)} {_a(ZT_CISA)} {CLOSING}",
    )


def test_a_a_discarded_only_service(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    svc = _service(c, bearer, cid, "attack", "attack_coverage")
    a = _assessment(c, bearer, cid, "attack", svc)
    r = c.post(f"/attack/assessments/{a}/discard", headers=_h(bearer, cid))
    assert r.status_code == 200, r.text
    _service(c, bearer, cid, "csf", "nist_csf")
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("attack", "no_assessment", "attack_coverage"),
            ("csf_or_zt", "no_assessment", "nist_csf"),
        ],
        f"{_a(ATTACK)} {_a(CSF)} {CLOSING}",
    )


def test_a_unpublished_a_pending_request(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _request(cid, ServiceType.ATTACK_COVERAGE)
    _request(cid, ServiceType.NIST_CSF)
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("attack", "unpublished", "attack_coverage"),
            ("csf_or_zt", "unpublished", "nist_csf"),
        ],
        f"{_a_unpublished(ATTACK)} {_a_unpublished(CSF)} {CLOSING}",
    )


# --- D: a live assessment only under an archived service --------------------------------


def test_d_an_assessment_only_under_an_archived_service(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _archive(c, bearer, cid, _live_attack(c, bearer, cid))
    csf = _service(c, bearer, cid, "csf", "nist_csf")
    _assessment(c, bearer, cid, "csf", csf)
    _archive(c, bearer, cid, csf)
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("attack", "archived_only", "attack_coverage"),
            ("csf_or_zt", "archived_only", "nist_csf"),
        ],
        f"{_d(ATTACK, B_ATTACK)} {_d(CSF, B_CSF_ZT)} {CLOSING}",
    )


# --- Precedence, and the unlocked state ----------------------------------------------------


def test_an_engaged_service_is_named_before_an_archived_one(app_client) -> None:  # noqa: F811
    """A beats D: the engaged service is the remedy that exists."""
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    csf = _service(c, bearer, cid, "csf", "nist_csf")
    _assessment(c, bearer, cid, "csf", csf)
    _archive(c, bearer, cid, csf)
    _service(c, bearer, cid, "zt", "zero_trust_cisa")
    _assert_locked(
        c,
        bearer,
        cid,
        [("csf_or_zt", "no_assessment", "zero_trust_cisa")],
        f"{_a(ZT_CISA)} {CLOSING}",
    )


def test_unlocked_carries_no_locked_state(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    g = _gate(c, bearer, cid)
    assert g["unlocked"] is True, g  # positive first
    assert (g["locked_inputs"], g["locked_message"]) == ([], None), g


# --- The schema holds the locked state to `unlocked` ------------------------------------


def _gate_fields(**over: object) -> dict:
    base: dict = {
        "unlocked": False,
        "has_attack": False,
        "has_csf": False,
        "has_zt": False,
        "missing": ["a MITRE ATT&CK coverage mapping"],
        "attack_catalog_mismatch": None,
        "attack_computed_status_unreviewed": None,
        "locked_inputs": [
            {
                "requirement": "attack",
                "state": "no_service",
                "service_kind": None,
                "sentence": B_ATTACK,
            }
        ],
        "locked_message": f"{B_ATTACK} {CLOSING}",
    }
    base.update(over)
    return base


def test_the_schema_refuses_a_locked_gate_with_no_reason() -> None:
    from pydantic import ValidationError

    from app.schemas.risk import RiskGateStatus

    RiskGateStatus(**_gate_fields())  # positive first: a reasoned lock builds
    for over in ({"locked_inputs": []}, {"locked_message": None}):
        with pytest.raises(ValidationError) as exc:
            RiskGateStatus(**_gate_fields(**over))
        assert "a locked gate carries no locked state" in str(exc.value), over
    with pytest.raises(ValidationError) as exc:
        RiskGateStatus(**_gate_fields(unlocked=True))
    assert "an unlocked gate carries a locked state" in str(exc.value)


# --- Services that came through the Intake Queue (review of #1100, finding 1) ------------

ZT_DOD = "Zero Trust Assessment (DoD ZTRA)"


def test_d_a_published_request_whose_service_was_archived(app_client) -> None:  # noqa: F811
    """The production path: a request published through the real route, a
    draft assessment started, the service archived. The request is fulfilled,
    so it is not "waiting in the Intake Queue": D, not the unpublished A."""
    c, _ = app_client
    bearer, cid = _admin(c)
    svc = _publish(c, bearer, cid, _request(cid, ServiceType.ATTACK_COVERAGE))
    _assessment(c, bearer, cid, "attack", svc)
    _archive(c, bearer, cid, svc)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "archived_only", "attack_coverage"), ("csf_or_zt", "no_service", None)],
        f"{_d(ATTACK, B_ATTACK)} {B_CSF_ZT} {CLOSING}",
    )


def test_a_pending_consultation_request_is_not_a_service_kind(app_client) -> None:  # noqa: F811
    """A consultation is published nowhere and has no service kind; a pending
    one beside a locked gate changes nothing (and is not a 500)."""
    c, _ = app_client
    bearer, cid = _admin(c)
    _request(cid, ServiceType.CONSULTATION)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "no_service", None), ("csf_or_zt", "no_service", None)],
        f"{B_ATTACK} {B_CSF_ZT} {CLOSING}",
    )


def test_a_waiting_request_is_named_before_an_archived_assessment(app_client) -> None:  # noqa: F811
    """Unpublished A beats D: publishing the waiting request is the remedy
    that exists."""
    c, _ = app_client
    bearer, cid = _admin(c)
    _archive(c, bearer, cid, _live_attack(c, bearer, cid))
    _request(cid, ServiceType.ATTACK_COVERAGE)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "unpublished", "attack_coverage"), ("csf_or_zt", "no_service", None)],
        f"{_a_unpublished(ATTACK)} {B_CSF_ZT} {CLOSING}",
    )


def test_d_the_dod_zero_trust_kind_has_its_own_label(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    zt = _service(c, bearer, cid, "zt", "zero_trust_dod")
    _assessment(c, bearer, cid, "zt", zt)
    _archive(c, bearer, cid, zt)
    _assert_locked(
        c,
        bearer,
        cid,
        [("csf_or_zt", "archived_only", "zero_trust_dod")],
        f"{_d(ZT_DOD, B_CSF_ZT)} {CLOSING}",
    )


# --- Review of #1100, round 2 -------------------------------------------------------------


def test_an_engaged_service_is_named_before_a_waiting_request(app_client) -> None:  # noqa: F811
    """Engaged A beats unpublished A: the client asked for NIST CSF and Zero
    Trust (CISA); only CSF was published, and it has no assessment yet."""
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    _publish(c, bearer, cid, _request(cid, ServiceType.NIST_CSF))
    _request(cid, ServiceType.ZERO_TRUST_CISA)
    _assert_locked(
        c,
        bearer,
        cid,
        [("csf_or_zt", "no_assessment", "nist_csf")],
        f"{_a(CSF)} {CLOSING}",
    )


def test_a_discarded_assessment_under_an_archived_service_is_no_service(
    app_client,  # noqa: F811
) -> None:
    """D says an assessment exists; a discarded one does not count."""
    c, _ = app_client
    bearer, cid = _admin(c)
    svc = _service(c, bearer, cid, "attack", "attack_coverage")
    a = _assessment(c, bearer, cid, "attack", svc)
    r = c.post(f"/attack/assessments/{a}/discard", headers=_h(bearer, cid))
    assert r.status_code == 200, r.text
    _archive(c, bearer, cid, svc)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "no_service", None), ("csf_or_zt", "no_service", None)],
        f"{B_ATTACK} {B_CSF_ZT} {CLOSING}",
    )


def test_another_clients_services_and_requests_change_nothing(app_client) -> None:  # noqa: F811
    """Client scoping: a second tenant with a waiting request, an engaged
    service and an assessment under an archived service, of both kinds. The
    first client's gate and 409 are what they would be alone."""
    c, _ = app_client
    bearer, cid = _admin(c)
    other = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Beta"},
    )
    assert other.status_code in (200, 201), other.text
    oid = other.json()["id"]
    _request(oid, ServiceType.ATTACK_COVERAGE)
    _request(oid, ServiceType.NIST_CSF)
    _service(c, bearer, oid, "attack", "attack_coverage")
    _service(c, bearer, oid, "zt", "zero_trust_cisa")
    _archive(c, bearer, oid, _live_attack(c, bearer, oid))
    csf = _service(c, bearer, oid, "csf", "nist_csf")
    _assessment(c, bearer, oid, "csf", csf)
    _archive(c, bearer, oid, csf)
    _assert_locked(
        c,
        bearer,
        cid,
        [("attack", "no_service", None), ("csf_or_zt", "no_service", None)],
        f"{B_ATTACK} {B_CSF_ZT} {CLOSING}",
    )


# --- Review of #1100, round 3: two kinds in one arm ----------------------------------------


def test_two_engaged_kinds_are_both_named_in_kind_order(app_client) -> None:  # noqa: F811
    """Engaged NIST CSF and Zero Trust (CISA), neither with an assessment: both
    remedies, in the requirement's kind order, never just the first."""
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    _service(c, bearer, cid, "zt", "zero_trust_cisa")
    _service(c, bearer, cid, "csf", "nist_csf")
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("csf_or_zt", "no_assessment", "nist_csf"),
            ("csf_or_zt", "no_assessment", "zero_trust_cisa"),
        ],
        f"{_a(CSF)} {_a(ZT_CISA)} {CLOSING}",
    )


def test_two_waiting_requests_are_both_named_in_kind_order(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    _live_attack(c, bearer, cid)
    _request(cid, ServiceType.ZERO_TRUST_CISA)
    _request(cid, ServiceType.NIST_CSF)
    _assert_locked(
        c,
        bearer,
        cid,
        [
            ("csf_or_zt", "unpublished", "nist_csf"),
            ("csf_or_zt", "unpublished", "zero_trust_cisa"),
        ],
        f"{_a_unpublished(CSF)} {_a_unpublished(ZT_CISA)} {CLOSING}",
    )
