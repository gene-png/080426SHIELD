"""What a Risk Register is built from, and whether all of it is final (#737).

Gene's rule (#736, 5984159954; approved 5986057990 item 13): a register may be
DRAFTED from in-progress work at any time, but it is PUBLISHED only when every
input the client has engaged is RELEASED and is still the version the register
was generated from.

The inputs are the ATT&CK coverage, CSF and Zero Trust assessments synthesis
reads, plus the Tech Debt capability list(s) ATT&CK draws its tools from.

ENGAGED means the client has a non-archived Service of that kind. A client
with no Zero Trust service is not held up by Zero Trust; one with a Zero Trust
service and no assessment yet is, because there is work that is not final.

THE CURRENT INPUT for ATT&CK, CSF and ZT is the latest non-discarded assessment
of that kind across the client's services (version, then creation time) --
the one a draft synthesizes from. For Tech Debt it is each engaged service's
latest non-discarded capability list, because ATT&CK's tool membership draws
on every Tech Debt service.

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


def engaged_kinds(db: Session, client_id: uuid.UUID) -> list[str]:
    return [k for k in INPUT_KINDS if _engaged_services(db, client_id, k)]


def current_inputs(db: Session, client_id: uuid.UUID) -> list[InputRecord]:
    """Every current input the client has, engaged kinds only.

    An engaged kind with no record yet contributes nothing here; the gate
    reports it from `engaged_kinds` as "not started".
    """
    out: list[InputRecord] = []
    for kind in ("attack", "csf", "zt"):
        model = _ASSESSMENTS[kind]
        a = db.execute(
            select(model)
            .where(model.client_id == client_id, model.status != "discarded")
            .order_by(model.version.desc(), model.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if a is not None:
            out.append(
                InputRecord(kind, str(a.service_id), str(a.id), a.version, _status(a.status))
            )
    for svc in _engaged_services(db, client_id, "tech_debt"):
        lst = db.execute(
            select(CapabilityList)
            .where(CapabilityList.service_id == svc.id, CapabilityList.status != "discarded")
            .order_by(CapabilityList.version.desc(), CapabilityList.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if lst is not None:
            out.append(
                InputRecord("tech_debt", str(svc.id), str(lst.id), lst.version, _status(lst.status))
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
      * every engaged kind has a current input (else `not_started`);
      * every current input is RELEASED (else `not_released`);
      * every current input is the one the register was generated from, at the
        same version and already released then (else `changed`). A register
        generated from a draft is therefore never publishable, even after the
        draft is released: its findings were drafted from unreleased work.

    `recorded` is the register's provenance `current_inputs` list. When it is
    absent or unreadable the register cannot be certified (`not_recorded`):
    missing data defaults to UNCONFIRMED.
    """
    now = current_inputs(db, client_id)
    blockers: list[Blocker] = []
    if not isinstance(recorded, list) or not all(isinstance(r, dict) for r in recorded):
        _log.info("risk_publish_inputs_not_recorded", client_id=str(client_id))
        return [Blocker("register", "not_recorded", None)]
    then = {(r.get("kind"), r.get("service_id")): r for r in recorded}
    present = {r.kind for r in now}
    for kind in engaged_kinds(db, client_id):
        if kind not in present:
            blockers.append(Blocker(kind, "not_started", None))
    for r in now:
        if r.status != RELEASED:
            blockers.append(Blocker(r.kind, "not_released", r.status))
            continue
        was = then.get((r.kind, r.service_id))
        if (
            was is None
            or was.get("record_id") != r.record_id
            or was.get("version") != r.version
            or was.get("status") != RELEASED
        ):
            blockers.append(Blocker(r.kind, "changed", r.status))
    return blockers
