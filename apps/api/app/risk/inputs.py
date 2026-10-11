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

import hashlib
import json
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.csf.retired import catalog_rows as csf_catalog_rows
from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment
from app.models.capability import CapabilityList
from app.models.csf_assessment import CsfAssessment
from app.models.csf_profile import CsfDimensionScore
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

#: The kinds findings are drawn from; Tech Debt feeds ATT&CK and publication only.
SYNTHESIS_KINDS = ("attack", "csf", "zt")


@dataclass(frozen=True)
class InputRecord:
    """One input as it stands: which record, which version, which status."""

    kind: str
    service_id: str
    record_id: str
    version: int
    status: str
    #: #474 D': CSF only, the content of its in-scope Playbook rows
    #: (`csf_playbook_fingerprint`). None for every other kind.
    playbook_fingerprint: str | None = None

    def as_json(self) -> dict:
        out = {
            "kind": self.kind,
            "service_id": self.service_id,
            "record_id": self.record_id,
            "version": self.version,
            "status": self.status,
        }
        if self.playbook_fingerprint is not None:
            out["playbook_fingerprint"] = self.playbook_fingerprint
        return out


#: Every Playbook field a CSF finding or its citability depends on: the
#: roll-up's (`app/csf/enterprise.py`: tier, the five dimensions,
#: `has_evidence`, `in_scope`, `target_level`) and
#: `csf/retired.py::has_recorded_score`'s (those, plus `answer_source`,
#: `rationale`, `what_we_found`, `evidence_artifact_id`).
_PLAYBOOK_FIELDS = (
    "tier",
    "subcategory_code",
    "governance",
    "policy",
    "implementation",
    "monitoring",
    "improvement",
    "has_evidence",
    "in_scope",
    "target_level",
    "answer_source",
    "rationale",
    "what_we_found",
    "evidence_artifact_id",
)


def csf_playbook_fingerprint(db: Session, assessment_id: str) -> str:
    """#474 D' (advisor, #736 6087786886, item 3, option (a)): a snapshot, not
    a lock. The sha256 of the assessment's in-scope catalog Playbook rows,
    every field above, sorted by (subcategory, tier). Playbook rows stay
    editable after approval (#37 is Gene's open decision), so publish compares
    this with the value recorded at generate and reports CSF `changed` when a
    score, target, note or scope changed since. A row moved out of scope
    leaves the set, so that changes it too."""
    rows = csf_catalog_rows(
        db.execute(
            select(CsfDimensionScore).where(
                CsfDimensionScore.assessment_id == uuid.UUID(assessment_id)
            )
        )
        .scalars()
        .all()
    )
    content = sorted(
        (
            [
                str(getattr(r, f)) if f == "evidence_artifact_id" else getattr(r, f)
                for f in _PLAYBOOK_FIELDS
            ]
            for r in rows
            if r.in_scope
        ),
        key=lambda v: (v[1], v[0]),
    )
    blob = json.dumps(content, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


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


def latest_record(db: Session, kind: str, service_id: uuid.UUID):
    """One engaged service's current record: its latest non-discarded
    assessment (or Tech Debt list), or None. Synthesis reads THIS too
    (#876), so the record publish checks is the one findings came from."""
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
        rec = latest_record(db, kind, svc.id)
        if rec is not None:
            out.append(
                InputRecord(
                    kind,
                    str(svc.id),
                    str(rec.id),
                    rec.version,
                    _status(rec.status),
                    csf_playbook_fingerprint(db, str(rec.id)) if kind == "csf" else None,
                )
            )
    return out


@dataclass(frozen=True)
class Blocker:
    """Why publication is refused for one input."""

    kind: str
    reason: str  # "not_started" | "not_released" | "changed" | "not_recorded"
    status: str | None


def publish_blockers(
    db: Session, client_id: uuid.UUID, recorded: object, synthesized: object
) -> list[Blocker]:
    """What stops this register being published, per input. Empty = publishable
    as far as its inputs go.

    FIVE CHECKS, and none of them may pass by absence:
      * every engaged SERVICE has a current input (else `not_started`);
      * every current input is RELEASED (else `not_released`);
      * every current input is the one the register was generated from, at the
        same version and already released then (else `changed`). A register
        generated from a draft is therefore never publishable, even after the
        draft is released: its findings were drafted from unreleased work.
      * every input RECORDED at generate is still engaged (else `changed`).
        A service archived after generate leaves its findings in the register,
        and walking only today's services would drop it from the check in
        silence -- an approved assessment's findings would then publish
        (#860 review F1). Released or not, the register no longer matches
        what the client has engaged, so it is regenerated.
      * every recorded ATT&CK, CSF or ZT input was SYNTHESIZED, by service
        (else `not_recorded`; #891 review B1). A register generated before
        #876 read one assessment per kind, so a client with CISA and DoD both
        released recorded both in `current_inputs` but drew findings from one
        -- and every check above passes for it. Its `inputs` rows carry no
        `service_id`, so the match fails closed and the consultant
        regenerates; publishing it would deliver #876's own gap after its fix.

    `recorded` is the register's provenance `current_inputs` list and
    `synthesized` its `inputs` list (what findings were drawn from). When it is
    absent or unreadable the register cannot be certified (`not_recorded`):
    missing data defaults to UNCONFIRMED.
    """
    blockers: list[Blocker] = []
    if not isinstance(recorded, list) or not all(isinstance(r, dict) for r in recorded):
        _log.info("risk_publish_inputs_not_recorded", client_id=str(client_id))
        return [Blocker("register", "not_recorded", None)]
    then = {(r.get("kind"), r.get("service_id")): r for r in recorded}
    now = {(r.kind, r.service_id): r for r in current_inputs(db, client_id)}
    engaged = engaged_services(db, client_id)
    # PER ENGAGED SERVICE, never per kind: a released record of one service
    # must not stand in for a draft (or nothing) in another of the same kind.
    for kind, svc in engaged:
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
            # #474 D': the CSF Playbook changed since generate. A register that
            # recorded no fingerprint (generated before this) reads None here
            # and is `changed` too: unconfirmed, never a match.
            or (kind == "csf" and was.get("playbook_fingerprint") != r.playbook_fingerprint)
        ):
            blockers.append(Blocker(kind, "changed", r.status))
    # And every RECORDED input, so one whose service is no longer engaged
    # (archived since generate) cannot drop out of the check.
    engaged_keys = {(kind, str(svc.id)) for kind, svc in engaged}
    for (kind, service_id), _was in then.items():
        if (kind, service_id) not in engaged_keys:
            blockers.append(Blocker(str(kind), "changed", None))
    drawn_from = (
        {
            str(i.get("service_id"))
            for i in synthesized
            if isinstance(i, dict) and i.get("service_id")
        }
        if isinstance(synthesized, list)
        else set()
    )
    # A register with NO `inputs` key at all (pre-0047, or the old seed shape)
    # is refused by publish's next guard, `_require_certifiable_inputs`, with
    # its own reason (`register_inputs_not_recorded`), which
    # `test_publish_refuses_inputs_that_cannot_be_certified` pins. So this
    # check runs only over a recorded `inputs` value; anything recorded that
    # is not a list counts as naming no service and fails closed above.
    if synthesized is not None:
        for (kind, service_id), _was in then.items():
            if kind in SYNTHESIS_KINDS and str(service_id) not in drawn_from:
                blockers.append(Blocker(str(kind), "not_recorded", None))
    if blockers:
        _log.info(
            "risk_publish_inputs_blocked",
            client_id=str(client_id),
            blockers=[(b.kind, b.reason) for b in blockers],
        )
    return blockers
