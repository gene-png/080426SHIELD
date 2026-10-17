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
from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.orm import Session, undefer_group

from app.csf.retired import catalog_rows as csf_catalog_rows
from app.logging import get_logger
from app.models.attack_assessment import AttackAssessment
from app.models.capability import CapabilityList
from app.models.csf_assessment import CsfAssessment
from app.models.csf_profile import (
    EVIDENCE_STATUS_GROUP,
    CsfDimensionScore,
    CsfEvidenceStatus,
)
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.zt_assessment import ZtAssessment
from app.risk.selection import Selection, SelectionRead, selection_roles

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
    every field above, sorted by (subcategory, tier). Publish compares this
    with the value recorded at generate and reports CSF `changed` when a
    score, target, note or scope changed since. A row moved out of scope
    leaves the set, so that changes it too.

    Since #1120's ruling A2 (#736 6136101129) an APPROVED or RELEASED
    assessment's Playbook rows are not edited in place: the dimension-score
    PATCH and the gap-action upsert refuse it, and a change goes through a
    revision, which is a new record. One writer still reaches it: seeding
    creates the rows of an approved record that has none, which changes this
    fingerprint from the empty set's. Any route that later edits an approved
    record's rows in place would make the other changes reachable again."""
    rows = csf_catalog_rows(
        db.execute(
            select(CsfDimensionScore)
            .where(CsfDimensionScore.assessment_id == uuid.UUID(assessment_id))
            .options(undefer_group(EVIDENCE_STATUS_GROUP))
        )
        .scalars()
        .all()
    )
    content = sorted(
        ([_fingerprint_value(r, f) for f in _PLAYBOOK_FIELDS] for r in rows if r.in_scope),
        key=lambda v: (v[1], v[0]),
    )
    blob = json.dumps(content, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _fingerprint_value(row: CsfDimensionScore, field: str) -> object:
    """One field as the fingerprint hashes it. `has_evidence` became the
    three-valued `evidence_status` (migration 0075): its two old values hash
    as the boolean did, so a fingerprint recorded before 0075 still matches an
    unchanged Playbook, and the new middle value hashes as itself, so a move
    to or from it reads as changed."""
    if field == "evidence_artifact_id":
        return str(row.evidence_artifact_id)
    if field == "has_evidence":
        status = row.evidence_status
        if status == CsfEvidenceStatus.CONFIRMED_IN_DISCUSSION:
            return status.value
        return status == CsfEvidenceStatus.ON_FILE
    return getattr(row, field)


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


def latest_record(
    db: Session, kind: str, service_id: uuid.UUID, ignore_ids: frozenset[str] = frozenset()
):
    """One engaged service's current record: its latest non-discarded
    assessment (or Tech Debt list), or None. Synthesis reads THIS too
    (#876), so the record publish checks is the one findings came from.

    `ignore_ids` reads the service as if those records were discarded: the
    counterfactual `publish_blockers` asks (#1156), never a state anything
    else sees."""
    model = CapabilityList if kind == "tech_debt" else _ASSESSMENTS[kind]
    query = select(model).where(model.service_id == service_id, model.status != "discarded")
    if ignore_ids:
        query = query.where(model.id.notin_([uuid.UUID(i) for i in ignore_ids]))
    return db.execute(
        query.order_by(model.version.desc(), model.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def current_inputs(
    db: Session, client_id: uuid.UUID, ignore_ids: frozenset[str] = frozenset()
) -> list[InputRecord]:
    """The current record of every engaged service that has one.

    An engaged service with no record yet contributes nothing here; the gate
    reports it from `engaged_services` as "not started".
    """
    out: list[InputRecord] = []
    for kind, svc in engaged_services(db, client_id):
        rec = latest_record(db, kind, svc.id, ignore_ids)
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
    #: For a `changed` blocker only: which remedy a person can follow to a
    #: publishable register (`changed_remedy`). None reads as REGENERATE.
    remedy: str | None = None
    #: The draft record a DISCARD_DRAFT candidate would discard (not in the
    #: API payload); `publish_blockers` reads it for the counterfactual.
    draft_id: str | None = None


DISCARD_DRAFT = "discard_draft"
RELEASE_NEWER = "release_newer"
REGENERATE = "regenerate"


def changed_remedy(*, was_status: str | None, newest_status: str | None) -> str:
    """What a `changed` input's newest record asks of a person (#1156). The
    table is `tests/unit/test_risk_changed_remedy_table.py`.

    * the newest record is released (or there is none): a new version draws on
      it and can publish, REGENERATE;
    * the register drew on RELEASED work and the newest record is a DRAFT:
      DISCARD_DRAFT is a CANDIDATE only. Whether discarding really leaves a
      publishable register is not decided here by listing cases; the caller
      asks the real gate (`publish_blockers`, counterfactually);
    * any other unreleased newest record: a new version would draw on it and be
      refused, so RELEASE_NEWER (release it, then generate).

    A register that drew on UNRELEASED work is never publishable as it stands,
    so DISCARD_DRAFT is never a candidate for it."""
    if newest_status not in ("draft", "submitted", "approved"):
        return REGENERATE
    if was_status == RELEASED and newest_status == "draft":
        return DISCARD_DRAFT
    return RELEASE_NEWER


def _publish_blockers(
    db: Session,
    client_id: uuid.UUID,
    recorded: object,
    synthesized: object,
    *,
    selection: SelectionRead,
    ignore_ids: frozenset[str] = frozenset(),
) -> list[Blocker]:
    """What stops this register being published, per input. Empty = publishable
    as far as its inputs go.

    FIVE CHECKS, and none of them may pass by absence:
      * every engaged SERVICE has a current input (else `not_started`);
      * every current input is RELEASED (else `not_released`), unless it is
        a newer record than the one the register drew on, which is `changed`
        first (#1156: a revision draft opened after generate);
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

    RR-1 (for #1122), design note §5: `selection` is `selection_of(provenance)`,
    REQUIRED with no default, so a caller that forgets it is a `TypeError`
    rather than a silent fall-back to the pre-RR-1 rule.
      * A register with no usable selection (`SELECTION_NOT_RECORDED` or
        `SELECTION_UNREADABLE`) is refused for the WHOLE register, first,
        before any row is looked up (§5.3).
      * Otherwise each engaged service has a role (`selection_roles`). A
        DESELECTED service, or an INELIGIBLE one that still has no record, is
        not part of this register and is skipped (Q4: disclosed, not blocked).
        Every other role runs the checks below, unchanged.

    RATCHETS, stated: the register-level unreadable-`current_inputs` branch
    and the per-input `not_recorded` check at the end are reached by no
    register now, because `selection_of`'s check 5 and check 2 refuse those
    shapes first. They stay, so a writer that bypasses the selection cannot
    publish them.
    """
    blockers: list[Blocker] = []
    if not isinstance(selection, Selection):
        _log.info("risk_publish_selection_not_recorded", client_id=str(client_id))
        return [Blocker("register", "not_recorded", None)]
    if not isinstance(recorded, list) or not all(isinstance(r, dict) for r in recorded):
        _log.info("risk_publish_inputs_not_recorded", client_id=str(client_id))
        return [Blocker("register", "not_recorded", None)]
    then = {(r.get("kind"), r.get("service_id")): r for r in recorded}
    # The ordinary call is unchanged; only the counterfactual pass passes the
    # records to ignore.
    current = (
        current_inputs(db, client_id, ignore_ids) if ignore_ids else current_inputs(db, client_id)
    )
    now = {(r.kind, r.service_id): r for r in current}
    engaged = engaged_services(db, client_id)
    roles = selection_roles(
        selection,
        {(str(k), str(sid)) for (k, sid) in then},
        [(kind, str(svc.id)) for kind, svc in engaged],
    )
    # PER ENGAGED SERVICE, never per kind: a released record of one service
    # must not stand in for a draft (or nothing) in another of the same kind.
    for kind, svc in engaged:
        r = now.get((kind, str(svc.id)))
        role = roles[(kind, str(svc.id))].name
        # RR-1: not in this register by the admin's choice, or engaged with no
        # assessment at generate and still none. Neither holds it up.
        if role == "deselected" or (role == "ineligible" and r is None):
            continue
        if r is None:
            blockers.append(Blocker(kind, "not_started", None))
            continue
        was = then.get((kind, r.service_id))
        # #1156: a newer record than the one this register drew on (a revision
        # draft, #1120, or any newer version) is a CHANGED input, checked before
        # `not_released`. Otherwise a register drawn from a released v1 was
        # refused as "(draft)", naming a record it never read, and releasing
        # that draft then met `changed` anyway. Regenerating is the remedy.
        if was is not None and was.get("record_id") != r.record_id:
            remedy = changed_remedy(was_status=was.get("status"), newest_status=r.status)
            blockers.append(
                Blocker(
                    kind,
                    "changed",
                    r.status,
                    remedy,
                    r.record_id if remedy == DISCARD_DRAFT else None,
                )
            )
            continue
        if r.status != RELEASED:
            blockers.append(Blocker(kind, "not_released", r.status))
            continue
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


def publish_blockers(
    db: Session,
    client_id: uuid.UUID,
    recorded: object,
    synthesized: object,
    *,
    selection: SelectionRead,
) -> list[Blocker]:
    """`_publish_blockers`, with each DISCARD_DRAFT candidate CHECKED against the
    real gate (#1156). "Discard that draft, then publish again" is a promise
    that publishing then succeeds, so it is kept only if re-running the very
    same checks with every candidate draft removed returns NO blockers. A draft
    beside any other blocker, a recorded record whose CSF Playbook fingerprint
    has drifted, a service archived or newly engaged since generate: each fails
    that re-run by the same code path that would refuse the publish, so none is
    listed here. A failed candidate is told to release the draft instead."""
    blockers = _publish_blockers(db, client_id, recorded, synthesized, selection=selection)
    candidates = [b for b in blockers if b.remedy == DISCARD_DRAFT]
    if not candidates:
        return blockers
    drafts = frozenset(b.draft_id for b in candidates if b.draft_id)
    if len(drafts) == len(candidates) and not _publish_blockers(
        db, client_id, recorded, synthesized, selection=selection, ignore_ids=drafts
    ):
        return blockers
    return [replace(b, remedy=RELEASE_NEWER) if b.remedy == DISCARD_DRAFT else b for b in blockers]
