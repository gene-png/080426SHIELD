"""#1081, ruling (ii): why a locked Risk Register is locked, per missing kind,
and what to do about it, in the approved copy.

Advisor ruling #736 6115773247 on 6115613987; copy (B) for CSF/ZT replaced in
#1081 comment 6116102972. Every sentence below is that copy, verbatim.

The gate has two requirements, matching its unlock rule: an ATT&CK assessment,
and a CSF or Zero Trust assessment (alternatives). For each unmet one, every
service kind that could meet it gets ONE state, the first that holds of:

- `no_assessment` (A): an engaged service of that kind with no live assessment,
  discarded-only included (the requirement is unmet, so none is live);
- `unpublished` (A, the "Publish for processing" variant): no engaged service,
  but a request for one waits in the Intake Queue (`fulfilled_service_id` and
  `declined_at` both NULL), because publishing that request is what opens the
  service (`routes/admin.py::fulfill_service_request`);
- `archived_only` (D): a live assessment exists only under an archived service.

A requirement none of its kinds reaches is `no_service` (B), stated once. The
order is the order of the remedies: an engaged service is acted on, a waiting
request is published, and only then is a new service needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.client_naming import org_display_name
from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment
from app.models.client import Client
from app.models.csf_assessment import CsfAssessment
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.service_request import ServiceRequest, ServiceType
from app.models.zt_assessment import ZtAssessment

_log = get_logger(__name__)

NO_ASSESSMENT = "no_assessment"
UNPUBLISHED = "unpublished"
ARCHIVED_ONLY = "archived_only"
NO_SERVICE = "no_service"

ATTACK = "attack"
CSF_OR_ZT = "csf_or_zt"

#: The requirement's service kinds, in the order their sentences are stated.
_KINDS: dict[str, tuple[ServiceKind, ...]] = {
    ATTACK: (ServiceKind.ATTACK_COVERAGE,),
    CSF_OR_ZT: (ServiceKind.NIST_CSF, ServiceKind.ZERO_TRUST_CISA, ServiceKind.ZERO_TRUST_DOD),
}

_ASSESSMENT_BY_KIND = {
    ServiceKind.ATTACK_COVERAGE: AttackAssessment,
    ServiceKind.NIST_CSF: CsfAssessment,
    ServiceKind.ZERO_TRUST_CISA: ZtAssessment,
    ServiceKind.ZERO_TRUST_DOD: ZtAssessment,
}

#: {kind label}: the name the client picks in the Services step of its intake.
#: COPIED from `apps/web/src/lib/intake/types.ts` (the service labels), which
#: (B) quotes; change both.
KIND_LABELS: dict[ServiceKind, str] = {
    ServiceKind.ATTACK_COVERAGE: "MITRE ATT&CK Coverage Mapping",
    ServiceKind.NIST_CSF: "NIST CSF 2.0 Assessment",
    ServiceKind.ZERO_TRUST_CISA: "Zero Trust Assessment (CISA ZTMM 2.0)",
    ServiceKind.ZERO_TRUST_DOD: "Zero Trust Assessment (DoD ZTRA)",
}

CLOSING = (
    "A draft assessment is enough to generate a draft register; approve the "
    "assessments before you publish it."
)


def _b(requirement: str, client: str) -> str:
    if requirement == ATTACK:
        return (
            f"{client} has no MITRE ATT&CK Coverage Mapping service. A client adds it by "
            "selecting MITRE ATT&CK Coverage Mapping in the Services step of its intake; "
            "there is no control here to add it."
        )
    return (
        f"{client} has no NIST CSF 2.0 Assessment or Zero Trust service. The client can "
        "add one by selecting it in the Services step of its intake, or by starting a "
        "self-assessment from My Assessments."
    )


def _a(label: str, client: str) -> str:
    return (
        f"{client}'s {label} service has no assessment in progress. In Intake Queue, "
        f"open {client}, click Open workspace → on that service, then click Start "
        "assessment."
    )


def _a_unpublished(label: str, client: str) -> str:
    return (
        f"{client}'s {label} service has no assessment in progress. In Intake Queue, "
        f"open {client}, click Publish for processing on that service, then Open "
        "workspace →, then Start assessment."
    )


def _d(label: str, client: str, b: str) -> str:
    return (
        f"{client}'s {label} assessment is under an archived service, and an archived "
        f"service cannot be restored. {client} needs a new {label} service: {b}"
    )


@dataclass(frozen=True)
class LockedInput:
    requirement: str
    state: str
    service_kind: ServiceKind | None
    sentence: str


def locked_inputs(db: Session, client_id: uuid.UUID, *, unmet: list[str]) -> list[LockedInput]:
    """One entry per (unmet requirement, service kind) reached, or one
    `no_service` entry for a requirement none of its kinds reaches.

    `unmet` is the gate's own verdict (`ATTACK`, `CSF_OR_ZT`), passed in rather
    than re-derived, so this cannot disagree with `unlocked`."""
    client_row = db.get(Client, client_id)
    if client_row is None:
        raise ValueError(f"client {client_id} does not exist")
    client = org_display_name(client_row.legal_name)
    engaged = _engaged_kinds(db, client_id)
    requested = _pending_request_kinds(db, client_id)
    archived = _archived_live_kinds(db, client_id)
    out: list[LockedInput] = []
    for requirement in (ATTACK, CSF_OR_ZT):
        if requirement not in unmet:
            continue
        kinds = _KINDS[requirement]
        found = (
            [
                LockedInput(requirement, NO_ASSESSMENT, k, _a(KIND_LABELS[k], client))
                for k in kinds
                if k in engaged
            ]
            or [
                LockedInput(requirement, UNPUBLISHED, k, _a_unpublished(KIND_LABELS[k], client))
                for k in kinds
                if k in requested
            ]
            or [
                LockedInput(
                    requirement,
                    ARCHIVED_ONLY,
                    k,
                    _d(KIND_LABELS[k], client, _b(requirement, client)),
                )
                for k in kinds
                if k in archived
            ]
            or [LockedInput(requirement, NO_SERVICE, None, _b(requirement, client))]
        )
        out.extend(found)
    _log.info(
        "risk.gate.locked_inputs",
        client_id=str(client_id),
        states=[(x.requirement, x.state, x.service_kind and x.service_kind.value) for x in out],
    )
    return out


def locked_message(inputs: list[LockedInput]) -> str:
    """The sentences, then the closing line."""
    if not inputs:
        raise ValueError("a locked message needs at least one locked input")
    return " ".join([*(x.sentence for x in inputs), CLOSING])


def _engaged_kinds(db: Session, client_id: uuid.UUID) -> set[ServiceKind]:
    return set(
        db.execute(
            select(Service.kind).where(
                Service.client_id == client_id, Service.status != ServiceStatus.ARCHIVED
            )
        )
        .scalars()
        .all()
    )


def _pending_request_kinds(db: Session, client_id: uuid.UUID) -> set[ServiceKind]:
    types = (
        db.execute(
            select(ServiceRequest.service_type).where(
                ServiceRequest.client_id == client_id,
                ServiceRequest.fulfilled_service_id.is_(None),
                ServiceRequest.declined_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    return {ServiceKind(t.value) for t in types if t != ServiceType.CONSULTATION}


def _archived_live_kinds(db: Session, client_id: uuid.UUID) -> set[ServiceKind]:
    out: set[ServiceKind] = set()
    for kind, model in _ASSESSMENT_BY_KIND.items():
        hit = db.execute(
            select(model.id)
            .join(Service, Service.id == model.service_id)
            .where(
                model.client_id == client_id,
                model.status != "discarded",
                Service.kind == kind,
                Service.status == ServiceStatus.ARCHIVED,
            )
            .limit(1)
        ).scalar_one_or_none()
        if hit is not None:
            out.add(kind)
    return out
