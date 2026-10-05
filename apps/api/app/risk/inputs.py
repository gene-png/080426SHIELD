"""What a Risk Register is built from, and whether all of it is final (#737).

Gene's rule (#736, 5984159954; approved 5986057990 item 13): a register may be
DRAFTED from in-progress work at any time, but it is PUBLISHED only when every
input the client has engaged is RELEASED and is still the version the register
was generated from.

The inputs are the ATT&CK coverage, CSF and Zero Trust assessments synthesis
reads, plus the Tech Debt capability list(s) ATT&CK draws its tools from.

ENGAGED is PER SERVICE: every non-archived Service of an input kind is one
input. A client with no Zero Trust service is not held up by Zero Trust; one
with a Zero Trust service and no assessment yet is, because there is work that
is not final. A client with two Zero Trust services (CISA and DoD) has two
inputs, and both must be final (#860 review B2).

THE CURRENT INPUT for each engaged service is that service's latest
non-discarded assessment (version, then creation time), or for Tech Debt its
latest non-discarded capability list. An ARCHIVED service contributes nothing:
its records are neither inputs nor evidence that an input is present.

This module only READS. `routes/risk.py` records `current_inputs` in the
register's provenance at generate, and `publish_blockers` compares that record
with the state at publish.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment
from app.models.capability import CapabilityList
from app.models.csf_assessment import CsfAssessment
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.zt_assessment import ZtAssessment

_log = get_logger(__name__)

#: Input kinds, in the order every surface lists them.
INPUT_KINDS = ("attack", "csf", "zt", "tech_debt")

_SERVICE_KINDS: dict[str, tuple[ServiceKind, ...]] = {
    "attack": (ServiceKind.ATTACK_COVERAGE,),
    "csf": (ServiceKind.NIST_CSF,),
    "zt": (ServiceKind.ZERO_TRUST_CISA, ServiceKind.ZERO_TRUST_DOD),
    "tech_debt": (ServiceKind.TECH_DEBT,),
}
_ASSESSMENTS = {"attack": AttackAssessment, "csf": CsfAssessment, "zt": ZtAssessment}

RELEASED = "released"


@dataclass(frozen=True)
class InputRecord:
    """One input as it stands: which record, which version, which status."""

    kind: str
    service_id: str
    record_id: str
    version: int
    status: str

    def as_json(self) -> dict:
        return {
            "kind": self.kind,
            "service_id": self.service_id,
            "record_id": self.record_id,
            "version": self.version,
            "status": self.status,
        }


def _status(value: object) -> str:
    return str(getattr(value, "value", value))


def _engaged_services(db: Session, client_id: uuid.UUID, kind: str) -> list[Service]:
    return list(
        db.execute(
            select(Service)
            .where(
                Service.client_id == client_id,
                Service.kind.in_(_SERVICE_KINDS[kind]),
                Service.status != ServiceStatus.ARCHIVED,
            )
            .order_by(Service.created_at)
        )
        .scalars()
        .all()
    )


def engaged_services(db: Session, client_id: uuid.UUID) -> list[tuple[str, Service]]:
    """Every (kind, service) pair that is an input, in `INPUT_KINDS` order."""
    return [(k, svc) for k in INPUT_KINDS for svc in _engaged_services(db, client_id, k)]


def _latest_record(db: Session, kind: str, service_id: uuid.UUID):
    model = CapabilityList if kind == "tech_debt" else _ASSESSMENTS[kind]
    return db.execute(
        select(model)
        .where(model.service_id == service_id, model.status != "discarded")
        .order_by(model.version.desc(), model.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def current_inputs(db: Session, client_id: uuid.UUID) -> list[InputRecord]:
    """The current record of every engaged service that has one.

    An engaged service with no record yet contributes nothing here; the gate
    reports it from `engaged_services` as "not started".
    """
    out: list[InputRecord] = []
    for kind, svc in engaged_services(db, client_id):
        rec = _latest_record(db, kind, svc.id)
        if rec is not None:
            out.append(
                InputRecord(kind, str(svc.id), str(rec.id), rec.version, _status(rec.status))
            )
    return out


@dataclass(frozen=True)
class Blocker:
    """Why publication is refused for one input."""

    kind: str
    reason: str  # "not_started" | "not_released" | "changed" | "not_recorded"
    status: str | None


def publish_blockers(db: Session, client_id: uuid.UUID, recorded: object) -> list[Blocker]:
    """What stops this register being published, per input. Empty = publishable
    as far as its inputs go.

    THREE CHECKS, and none of them may pass by absence:
      * every engaged SERVICE has a current input (else `not_started`);
      * every current input is RELEASED (else `not_released`);
      * every current input is the one the register was generated from, at the
        same version and already released then (else `changed`). A register
        generated from a draft is therefore never publishable, even after the
        draft is released: its findings were drafted from unreleased work.

    `recorded` is the register's provenance `current_inputs` list. When it is
    absent or unreadable the register cannot be certified (`not_recorded`):
    missing data defaults to UNCONFIRMED.
    """
    blockers: list[Blocker] = []
    if not isinstance(recorded, list) or not all(isinstance(r, dict) for r in recorded):
        _log.info("risk_publish_inputs_not_recorded", client_id=str(client_id))
        return [Blocker("register", "not_recorded", None)]
    then = {(r.get("kind"), r.get("service_id")): r for r in recorded}
    now = {(r.kind, r.service_id): r for r in current_inputs(db, client_id)}
    # PER ENGAGED SERVICE, never per kind: a released record of one service
    # must not stand in for a draft (or nothing) in another of the same kind.
    for kind, svc in engaged_services(db, client_id):
        r = now.get((kind, str(svc.id)))
        if r is None:
            blockers.append(Blocker(kind, "not_started", None))
            continue
        if r.status != RELEASED:
            blockers.append(Blocker(kind, "not_released", r.status))
            continue
        was = then.get((kind, r.service_id))
        if (
            was is None
            or was.get("record_id") != r.record_id
            or was.get("version") != r.version
            or was.get("status") != RELEASED
        ):
            blockers.append(Blocker(kind, "changed", r.status))
    if blockers:
        _log.info(
            "risk_publish_inputs_blocked",
            client_id=str(client_id),
            blockers=[(b.kind, b.reason) for b in blockers],
        )
    return blockers
