"""Risk Register routes (Work Order E).

A derived, admin-only, point-in-time deliverable. Admin-only and cross-tenant:
the client id is named in the path (like /admin/services/{id}); no X-Client-Id.

  GET  /risk/clients/{cid}/gate
  POST /risk/clients/{cid}/register/generate
  GET  /risk/clients/{cid}/register/latest
"""

from __future__ import annotations

import contextvars
import re
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.engine import get_job, run_job
from app.ai.failures import ai_call_boundary
from app.ai.llm import LLMClient
from app.attack.catalog_version import catalog_mismatch_message, require_current_catalog
from app.attack.parents import is_computed_parent
from app.attack.rules import parents_computed
from app.audit import audit
from app.csf.gap import resolve_target_tier
from app.db.session import get_db
from app.dependencies import require_role
from app.docx_export import DOCX_MIME
from app.logging import get_logger
from app.models._common import utcnow
from app.models.artifact import Artifact, ArtifactOrigin
from app.models.attack_assessment import AttackAssessment, AttackCoverage
from app.models.client import Client
from app.models.csf_assessment import CsfAnswer, CsfAssessment
from app.models.risk_register import RiskEntry, RiskRegister
from app.models.user import User, UserRole
from app.models.zt_assessment import ZtAnswer, ZtAssessment
from app.risk import exporters as risk_exporters
from app.risk.engine import (
    Impact,
    Likelihood,
    RecommendedAction,
    RiskAxis,
    action_counts,
    axis_counts,
    tier_counts,
    tier_for,
)
from app.risk.link_scope import LinkScope, scope_for
from app.routes.artifacts import _storage_dep

# IMPORTED, not copied -- and `routes/clients.py` carries a comment saying the
# opposite, which is stated at both sites rather than left contradictory.
#
# A fourth copy of this two-line query is how four surfaces come to disagree
# about one client's target, which is the defect #84 is titled for. The cycle
# hazard `clients.py` names is real and measured: the `app/routes/*` graph is
# a DAG and NOTHING imports `risk`, so this module is a leaf and may import
# upward. The durable answer is a shared non-router helper; filed, not done
# here.
from app.routes.csf import _client_target_tier
from app.routes.zt import _client_target_stage
from app.schemas.risk import (
    LinkScopeDisclosure,
    RiskEntryResponse,
    RiskGateStatus,
    RiskRegisterResponse,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter
from app.storage import StorageBackend
from app.tech_debt.filename import SERVICE_SLUG_RISK_REGISTER, deliverable_filename
from app.zt.maturity import ZtFrameworkCode
from app.zt.scoring import resolve_target_stage

router = APIRouter(prefix="/risk", tags=["risk-register"])

_log = get_logger(__name__)

_admin_required = Depends(require_role(UserRole.ADMIN))

# risk_synthesize drafts ONE candidate entry per finding, and findings are one
# per gap across every assessment a client has. The 2026-08-07 validation client
# produced 509 of them (472 ATT&CK gap/partial + 37 Zero Trust). Each entry
# carries a description, compensating controls, residual risk and a rationale —
# richer than a mitre_map row, which measured ~310-575 output tokens — so a
# single request wants roughly 250k output tokens against claude-opus-5's 128k
# ceiling. As with mitre_map, this is not a budget problem: one request cannot
# express the job, and raising the cap only trades a fast, well-messaged failure
# for a slow silent one. It is split.
#
# 20 keeps a batch near ~14k output tokens — inside every provider's ceiling and
# small enough that losing one costs little. Workers are capped at 5 for the
# same reason attack's are: the provider rate limit is shared with every other
# job in the deployment, and generate() already sits behind enforce_ai.
_RISK_BATCH_SIZE = 20
_RISK_MAX_WORKERS = 5


def _llm_dep(db: Annotated[Session, Depends(get_db)]) -> LLMClient:
    """Issue 2: build from the DB so a key an admin pasted at runtime is
    honoured on the very next Run-AI, with no redeploy."""
    return LLMClient.from_db(db)


# APPROVED or RELEASED. What "finalized" means for an assessment, and the same
# pair `clients.py` used before #114 deleted its helper. SUBMITTED is NOT in it:
# on CSF and ZT that is a client having answered, not a consultant having signed
# off, and synthesis is the consultant's signature reaching a deliverable.
_FINALIZED = ("approved", "released")


def _exists_for_gate(db: Session, model, client_id: uuid.UUID) -> bool:
    """Does the client have a live assessment of this kind AT ALL? (#237)

    EXISTENCE, and deliberately not provenance. A DRAFT counts: mapping ATT&CK
    before the tech-debt list is approved is a normal order of work, and forcing
    finalize-everything-then-start-Risk would be a workflow restriction nobody
    asked for. DISCARDED does not count (D-031).

    **This function and `_finalized_for_synthesis` must never be merged, and the
    protection is the SIGNATURE rather than this paragraph.** They return
    different types — `bool` here, a model or None there — so collapsing them
    into one helper cannot be done as a casual tidy: it requires changing types
    and touching every call site, which is the point where somebody notices.

    Prose alone would not hold. This file's own history is the argument: the
    single `_latest` these replace carried a docstring explaining precisely what
    `active_only` protected, and it was still asked to answer two questions —
    "is there work" and "may this be synthesized" — for as long as it existed.
    The docstring says why; the types are what hold.

    Pinned by `test_the_gate_path_must_not_filter_on_finalized`, which fails if
    this ever starts excluding drafts.
    """
    return (
        db.execute(
            select(model.id)
            .where(model.client_id == client_id, model.status != "discarded")
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _finalized_for_synthesis(db: Session, model, client_id: uuid.UUID):
    """The latest APPROVED-or-RELEASED assessment, or None. (#237)

    PROVENANCE, and the reason this is separate from `_exists_for_gate`. What
    synthesis reads is exported under a client's name, so a DRAFT must not reach
    it — that is unreviewed content leaving as a deliverable, which is a
    different and worse failure than a correct number under a wrong label.

    Returning None here does NOT mean "no assessment": it means none that may be
    synthesized. `_gate` reports that distinction so unlock and synthesis stop
    disagreeing silently — a consultant walking into a refusal the UI said was
    not there is worse than a locked gate.

    See `_exists_for_gate` for why the two are typed differently on purpose.

    Pinned by `test_the_synthesis_path_must_filter_on_finalized`, which fails if
    this ever stops excluding drafts.
    """
    return db.execute(
        select(model)
        .where(model.client_id == client_id, model.status.in_(_FINALIZED))
        .order_by(model.version.desc(), model.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _latest_register(db: Session, client_id: uuid.UUID) -> RiskRegister | None:
    """The client's current Risk Register version.

    Typed to `RiskRegister` and taking no `model` argument, deliberately. The
    generic `_latest(db, model, ...)` this replaces was an escape hatch: it
    accepted any of the four models, which is how one helper came to answer both
    the gate's question and synthesis's. Removing the parameter removes the
    hatch — an assessment cannot be passed to this at all.

    No status filter: a register has no discard state, and `finalized_at` is what
    gates the client-facing dashboard (`clients.py::risk_dashboard`).
    """
    return db.execute(
        select(RiskRegister)
        .where(RiskRegister.client_id == client_id)
        .order_by(RiskRegister.version.desc(), RiskRegister.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _gate(db: Session, client_id: uuid.UUID) -> RiskGateStatus:
    """Whether the Risk Register can be generated, in THREE dimensions (#237).

    `missing` — ABSENT. `not_finalized` — EXISTS, unapproved, REPORTED.
    `synthesizable_missing` — what actually BLOCKS, and it mirrors the unlock
    rule over finalized inputs rather than exceeding it.

    The third field exists because the second was briefly used as the refusal,
    which blocked a register the unlock rule already permitted: CSF and ZT are
    alternatives, so a draft ZT beside an approved CSF produced a 409 whose only
    remedies were to approve unfinished work or discard it.

    Unlock stays on EXISTENCE. What changed is that the gate also reports which
    existing inputs cannot be synthesized because they are not finalized.

    `missing` and `not_finalized` are separate fields and are NOT merged, though
    both feed one sentence. "There is no ATT&CK mapping" and "the ATT&CK mapping
    is a draft" are different facts with different remedies — create one versus
    approve one — and putting the second into a field named `missing` would make
    the API assert something untrue to serve a message. That is the exact defect
    #234 shipped and corrected (`not_recorded` borrowed for retired lists), so it
    is not repeated here one issue later.
    """
    has_attack = _exists_for_gate(db, AttackAssessment, client_id)
    has_csf = _exists_for_gate(db, CsfAssessment, client_id)
    has_zt = _exists_for_gate(db, ZtAssessment, client_id)
    unlocked = has_attack and (has_csf or has_zt)

    missing: list[str] = []
    if not has_attack:
        missing.append("a MITRE ATT&CK coverage mapping")
    if not (has_csf or has_zt):
        missing.append("a CSF or Zero Trust assessment")

    # EXISTS but cannot be synthesized. Named individually so the state is
    # visible on the gate rather than discovered by hitting it.
    #
    # **REPORTING, NOT BLOCKING, and the distinction is load-bearing.** An
    # earlier version refused generation on ANY entry here, which exceeded the
    # unlock rule: CSF and ZT are ALTERNATIVES, so ATT&CK + CSF both approved
    # with a ZT draft in progress produced a 409 over two assessments that
    # satisfied unlock. The only remedies were to approve unfinished work --
    # what this change exists to prevent -- or discard it. And it was the normal
    # path, not an edge: `_FINALIZED` excludes `submitted`, which is where a CSF
    # or ZT engagement sits while a consultant reviews it, so a client answering
    # their questionnaire blocked the Risk Register.
    #
    # What BLOCKS is `synthesizable_missing` below, which mirrors unlock exactly.
    # What is merely listed here is disclosed on the register instead.
    not_finalized: list[str] = []
    attack = _finalized_for_synthesis(db, AttackAssessment, client_id)
    finalized_attack = attack is not None
    # #556: synthesis refuses an ATT&CK input scored against another catalog
    # (`require_current_catalog`). The gate asks the SAME predicate and carries
    # the SAME sentence, or it offers a Generate whose only outcome is a 409. A
    # separate field, not `synthesizable_missing`: that list is rendered as
    # "cannot be generated until these are approved", and this input already is.
    attack_catalog_mismatch = catalog_mismatch_message(db, attack) if attack is not None else None
    finalized_csf = _finalized_for_synthesis(db, CsfAssessment, client_id) is not None
    finalized_zt = _finalized_for_synthesis(db, ZtAssessment, client_id) is not None
    for label, present, finalized in (
        ("the MITRE ATT&CK coverage mapping", has_attack, finalized_attack),
        ("the CSF assessment", has_csf, finalized_csf),
        ("the Zero Trust assessment", has_zt, finalized_zt),
    ):
        if present and not finalized:
            not_finalized.append(label)

    # The unlock rule restated over FINALIZED inputs. Same shape as `missing`
    # above and deliberately so: if these two predicates ever diverge again, the
    # gate promises something synthesis will refuse.
    synthesizable_missing: list[str] = []
    if not finalized_attack:
        synthesizable_missing.append("an approved MITRE ATT&CK coverage mapping")
    if not (finalized_csf or finalized_zt):
        synthesizable_missing.append("an approved CSF or Zero Trust assessment")

    return RiskGateStatus(
        unlocked=unlocked,
        has_attack=has_attack,
        has_csf=has_csf,
        has_zt=has_zt,
        missing=missing,
        not_finalized=not_finalized,
        synthesizable_missing=synthesizable_missing,
        attack_catalog_mismatch=attack_catalog_mismatch,
    )


def _require_client(db: Session, cid: uuid.UUID) -> Client:
    client = db.get(Client, cid)
    if client is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found.")
    return client


@router.get(
    "/clients/{cid}/gate",
    response_model=RiskGateStatus,
    summary="Whether the Risk Register can be generated (admin)",
)
def gate(
    cid: uuid.UUID,
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> RiskGateStatus:
    _require_client(db, cid)
    return _gate(db, cid)


def _provenance_snapshot(db: Session, client_id: uuid.UUID, excluded: list[str]) -> dict:
    """What this register is being built FROM, as it stands right now (#240).

    Captured at GENERATE and never revised. Recomputing it at export would read
    TODAY's statuses, so a ZT assessment approved after generation would let the
    export certify coverage over a register that never saw it -- D-053's
    snapshot-versus-live lesson, one table over.

    Reads through `_finalized_for_synthesis`, the SAME resolver `_gather_findings`
    uses, rather than re-querying. A second query answering the same question is
    a second place for the answer to differ, and this one exists to be evidence.
    """
    inputs: list[dict] = []
    for kind, model in (
        ("attack", AttackAssessment),
        ("csf", CsfAssessment),
        ("zt", ZtAssessment),
    ):
        a = _finalized_for_synthesis(db, model, client_id)
        if a is None:
            continue
        inputs.append(
            {
                "kind": kind,
                "assessment_id": str(a.id),
                "version": a.version,
                # The status AS IT STOOD. Never re-read.
                "status": str(getattr(a.status, "value", a.status)),
            }
        )
    return {"inputs": inputs, "excluded": list(excluded)}


#: Fields whose model-supplied values are checked against the client's own
#: assessments. Named here so the audit row, the response counter and the
#: persisted record cannot disagree about which fields they cover.
LINK_FIELDS = ("linked_techniques", "linked_controls", "source_id")


def _resolve_links(offered: object, universe: set[str]) -> tuple[list[str], list[str]]:
    """`(kept, dropped)` for one link field.

    Returning BOTH halves is the entire fix. The previous form was::

        techs = [t for t in (raw.get("linked_techniques") or []) if t in valid_techniques]

    -- a comprehension whose false branch drops the record instead of emitting
    it under a different reason, which `CLAUDE.md` names exactly: "make the
    false branch emit something; a zero-value record that names the fault is
    honest, and silence never is."

    **No fold, no alias tier, and that is a decision rather than an omission.**
    The ATT&CK resolver has one because the model there is shown REDACTED tool
    names and must be able to cite them back, so a miss is a transformation to
    reverse.

    The allow-lists here are not transformed -- but NOT "by construction", which
    is what an earlier draft of this docstring claimed while citing a function
    called `_batch_prompt` that does not exist. They reach the model through
    `_run_risk_synthesize_batched` -> `run_job` -> `llm.invoke(payload=)` ->
    `redact_payload`, which walks every string in the payload. They survive it
    CONTINGENTLY: ATT&CK ids because `_RE_PHONE` carries a lookbehind written
    for exactly this case (`T1003.001` would otherwise egress as `T[PHONE]`),
    and `GV.OC-01` / `CISA.<pillar>.<nn>` because two digits sit far under the
    phone rule's seven-digit floor.

    So what would invalidate this decision is a change to the redactor, not a
    change here: an id scheme with a longer digit run, or a relaxed phone
    lookbehind, would start rewriting the allow-list on the way out and a miss
    WOULD become a transformation to reverse. Until then, a value not in the
    lists is the model citing something it was never given, and adding a
    normalising tier would invent a second key space to be wrong in -- which
    `CLAUDE.md` records costing an `ambiguous` verdict on the only citable
    string, strictly worse than the defect being fixed.

    Order is preserved and duplicates collapse, so a model that repeats a code
    inflates neither list.
    """
    kept: list[str] = []
    dropped: list[str] = []
    if not isinstance(offered, list):
        # A non-list is NOT "no links offered". It is a payload shape the prompt
        # did not ask for, and reporting it as an empty offer is the silence
        # this function exists to end. `None` and `""` are genuine absence.
        if offered is not None and offered != "":
            dropped.append(str(offered)[:64])
        return kept, dropped
    for raw in offered:
        value = str(raw)
        if value in universe:
            if value not in kept:
                kept.append(value)
            continue
        # TRUNCATE FIRST, THEN DEDUPE. The first version appended `value[:64]`
        # while testing membership of the untruncated `value`, so a repeated
        # value longer than 64 characters -- a model citing a technique by its
        # full descriptive name, say -- was recorded twice and inflated the
        # count a consultant reads.
        #
        # And the truncation must happen AFTER the universe test, never before:
        # truncating first would let a 64-character member of the allow-list
        # start matching longer non-members, which turns a reporting bug into a
        # wrong link.
        short = value[:64]
        if short not in dropped:
            dropped.append(short)
    return kept, dropped


def _gather_findings(
    db: Session, client_id: uuid.UUID
) -> tuple[list[dict], set[str], set[str], dict[str, dict], dict[str, LinkScope]]:
    """Findings (one per gap) + the valid link universes + the TARGETS USED.

    valid_techniques = ATT&CK technique codes this client's assessment SCORED.
    valid_controls   = CSF subcategory + ZT capability codes it SCORED.
    target_sources   = per service, the target this run compared against and
                       WHERE IT CAME FROM (#84).
    link_scopes      = per service, those codes plus how many rows were left
                       out for carrying no judgement -- the operand the
                       disclosure renders (#403).

    **SCORED, not present, and the difference was the whole of #403.** All
    three allow-lists were built from every row, and every row is pre-seeded:
    `provisioning.py` creates a `CsfAnswer` per `SUBCATEGORIES` entry and a
    `ZtAnswer` per capability with no tier or stage, `routes/attack.py` creates
    an `AttackCoverage` per technique with `status=None`, and nothing under
    `apps/api/app` deletes a row from any of the three. So "present" was true of
    the whole catalog and the allow-list meant every code that exists -- while
    `_run_batches` told the reader it meant the opposite.

    The predicate lives in `app/risk/link_scope.py`, ONE table for three
    services, for the reason the `resolve_target_tier` import below already
    gives: a second copy is how two services come to disagree about one client.

    **The `or set(attack_all_codes())` fallback is GONE, and deleting it is what
    makes the narrowing safe rather than a separate tidy.** It fired when `rows`
    was empty, which the pre-seed made nearly unreachable. Against a SCORED
    predicate it would have fired whenever the client scored nothing -- handing
    the model the entire catalog in precisely the case where no citation is
    supportable, which is the defect inverted and amplified.

    An empty allow-list is therefore a legitimate answer, not an error:
    `approve_assessment` in `routes/attack.py` has no scoring precondition, so
    an APPROVED assessment with every `status` NULL is reachable today. Nothing
    is raised for it. Every finding this function emits already requires a
    judgement (`status in ("gap", "partial")`, `maturity_tier is not None`), so
    a scored-nothing service contributes no findings either -- the model is
    asked to link nothing and drops nothing. What must never happen is that
    state passing SILENTLY, which is what `link_scopes` is returned for.

    The fourth return value is not bookkeeping. Every finding here is "current
    is below target", so the target is the operand that decides whether a row
    exists at all -- and until #84 it was a hardcoded 3 for CSF and a hardcoded
    fallback of 3 for ZT, regardless of what the client engaged for. A register
    computed against the wrong baseline is not visibly wrong: it has the right
    shape, plausible counts, and no way for a reader to tell which tier it was
    measuring against. Recording the target beside the findings is what makes
    the next one falsifiable.

    NOT switched to `analyze_gaps`, and the reason is measured rather than
    preference. That function returns `gaps=tuple(rows[:top_n])` with
    `DEFAULT_TOP_N = 20`, so calling it here would silently cap this feed at 20
    findings per service -- the truncation #75/#79 record in three renderers,
    arriving in the risk register. Closing #84's baseline defect by opening a
    data-loss one is not a trade worth making, so the target RESOLUTION is
    shared (the point of #84) and the comparison stays here. Tracked as the
    remaining half.
    """
    findings: list[dict] = []
    valid_techniques: set[str] = set()
    valid_controls: set[str] = set()
    target_sources: dict[str, dict] = {}
    link_scopes: dict[str, LinkScope] = {}

    attack = _finalized_for_synthesis(db, AttackAssessment, client_id)
    if attack is not None:
        # #556: rows keyed to another catalog would reach the register by ID --
        # "ATT&CK T1649.001" is not a technique, and a T1558 row was answered
        # against the swapped name. Refused, never relabelled by ID (D-091).
        require_current_catalog(db, attack)
        rows = (
            db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == attack.id))
            .scalars()
            .all()
        )
        # PENDING-REVIEW ROWS ARE CITABLE HERE, AND THAT IS AN OPEN QUESTION
        # RATHER THAN AN OVERSIGHT -- stated at the site because an unstated
        # exemption reads as one to whoever runs this sweep next.
        #
        # #102 says a status backed by no CONFIRMED citation must not score:
        # `attack/pending.py::pending_codes` is the authoritative set the
        # heatmap withholds. This scope does NOT subtract it, so a technique
        # whose coverage status is withheld from the score can still appear in
        # the register's `linked_techniques` and in the client's export.
        #
        # Arguable both ways, which is why it is filed rather than decided
        # here. A link says "this risk relates to T1003", not "T1003 is
        # covered", so citing a pending row may be perfectly honest -- or it may
        # propagate an unreviewed model inference into a deliverable, which is
        # the harm #102 exists to prevent.
        #
        # NOT INTRODUCED and strictly improved by this change: before #403 every
        # technique in the catalog was citable, pending or not. Narrowing to
        # scored rows is a subset of that, so nothing got worse. Tracked in #415.
        attack_scope = scope_for(AttackCoverage, rows)
        valid_techniques = set(attack_scope.codes)
        link_scopes["attack"] = attack_scope
        # Gene's condition (D-094): only an assessment approved under D-094
        # takes its findings through sub-techniques; one approved before #620
        # keeps the findings it would always have produced.
        skip_parents = parents_computed(attack)
        for r in rows:
            # #620 round 3 (D-094, condition 6; the coordinator's call, pending
            # Gene): a computed parent's status is arithmetic over its
            # sub-techniques, so a finding for it counts the same technique a
            # second time beside theirs -- and a recompute would add or remove
            # findings with no change in the evidence. Findings come through
            # the sub-techniques only, as the client triad counts them. Still
            # CITABLE as a link: `scope_for` above is unchanged.
            if skip_parents and is_computed_parent(r.technique_code):
                continue
            if r.status in ("gap", "partial"):
                findings.append(
                    {
                        "source": "coverage_finding",
                        "source_id": r.technique_code,
                        "kind": "attack",
                        "label": f"ATT&CK {r.technique_code}: {r.status}",
                    }
                )

    csf = _finalized_for_synthesis(db, CsfAssessment, client_id)
    if csf is not None:
        # #84. This read `r.maturity_tier < 3` -- a HARDCODED tier, so every
        # client's CSF findings were computed against tier 3 no matter what
        # they engaged for. A client targeting tier 2 was handed findings for
        # controls already AT their goal; one targeting tier 4 was handed a
        # register that stopped looking one tier early. The number reached the
        # client's Risk Register, which is what makes it the defect it is
        # rather than an internal inconsistency.
        #
        # Resolved through `resolve_target_tier`, the SAME function
        # `routes/csf.py` uses -- imported rather than reimplemented, because a
        # second copy is how two services come to disagree about one client's
        # target. It returns the source too, so "the client chose nothing" and
        # "the client's choice could not be used" stay separate facts.
        csf_target, csf_target_source = resolve_target_tier(_client_target_tier(db, csf.service_id))
        target_sources["csf"] = {"target": csf_target, "source": csf_target_source}
        csf_rows = (
            db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == csf.id)).scalars().all()
        )
        csf_scope = scope_for(CsfAnswer, csf_rows)
        valid_controls |= csf_scope.codes
        link_scopes["csf"] = csf_scope
        for r in csf_rows:
            if r.maturity_tier is not None and r.maturity_tier < csf_target:
                findings.append(
                    {
                        "source": "questionnaire_response",
                        "source_id": r.subcategory_code,
                        "kind": "csf",
                        "label": f"CSF {r.subcategory_code}: tier {r.maturity_tier}",
                    }
                )

    zt = _finalized_for_synthesis(db, ZtAssessment, client_id)
    if zt is not None:
        # #84, the ZT half. Framework-aware, because DoD ZTRA has three stages
        # where CISA has four -- a client stage valid under one is out of range
        # under the other, and `resolve_target_stage` is what knows that.
        # CONVERTED, not passed through. `ZtAssessment.framework` is
        # `ZtFramework` (app/models); the engine takes `ZtFrameworkCode`
        # (app/zt/maturity). They are two StrEnum classes with identical
        # VALUES, and `stage_definitions` decides with `==`, so passing the
        # model enum straight in returns the right ladder today -- by
        # coincidence, not by contract.
        #
        # One ordinary edit ends that: change that `==` to `is` -- a routine
        # enum tidy no gate here would question -- and a DoD assessment gets
        # the CISA ladder, `max_stage` becomes 4, a stored DoD 4 resolves as
        # `(4, "client")` instead of out-of-range, and every DoD capability at
        # stage 3 becomes a finding for a client whose ladder tops out at 3.
        # ruff and black do not read annotations, so the signature violation
        # is invisible to CI.
        #
        # `routes/zt.py` bridges this at every engine boundary with
        # `_to_catalog_framework`; this is the same conversion, spelled from
        # the value so it needs no cross-router import.
        zt_target, zt_target_source = resolve_target_stage(
            ZtFrameworkCode(zt.framework.value),
            _client_target_stage(db, zt.service_id),
        )
        target_sources["zt"] = {"target": zt_target, "source": zt_target_source}
        zt_rows = (
            db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == zt.id)).scalars().all()
        )
        zt_scope = scope_for(ZtAnswer, zt_rows)
        valid_controls |= zt_scope.codes
        link_scopes["zt"] = zt_scope
        for r in zt_rows:
            # Per-capability target first, then the ENGAGEMENT target. The
            # fallback was a hardcoded 3 (#84); it is now the client's
            # resolved stage.
            #
            # SCOPE OF THE PARITY, stated because the first version of this
            # comment said "the same precedence `analyze_gaps` documents" --
            # true of the ORDER and false of the RULE. `analyze_gaps` resolves
            # through `capability_target_override`, which refuses a bool,
            # refuses anything outside `1..level_count(framework)`, falls back
            # to the engagement stage AND reports the discard through
            # `GapAnalysis.unusable_target_codes`, which `zt/exporters.py`
            # renders. This reads the stored value raw and discloses nothing.
            #
            # Not reachable through the API today -- `patch_answer` 422s a
            # target outside the framework's range and the AI-apply path
            # range-checks before storing -- so the divergence is latent, and
            # the exemption is written here rather than left to be discovered.
            # Closing it means calling `capability_target_override`; that
            # changes what the feed reports and wants its own both-states
            # evidence, so it is tracked rather than done here.
            tgt = r.target_stage if r.target_stage is not None else zt_target
            if r.maturity_stage is not None and r.maturity_stage < tgt:
                findings.append(
                    {
                        "source": "questionnaire_response",
                        "source_id": r.capability_code,
                        "kind": "zt",
                        "label": f"ZT {r.capability_code}: stage {r.maturity_stage}",
                    }
                )

    return findings, valid_techniques, valid_controls, target_sources, link_scopes


def _coerce_enum(enum_cls, value) -> tuple[object | None, str | None]:
    """Resolve a model-supplied token, and REPORT what it could not resolve.

    Returns `(member, rejected_raw)`. `rejected_raw` is non-None only when a
    non-empty value was supplied and could not be resolved at all.

    #121. This was `_enum_or_none`, a bare `enum_cls(value)` returning None on
    failure. Two things were wrong with it and they are separate.

    **It was case- and separator-exact against a prompt that instructed
    neither.** The prompt said `likelihood (Very Low..Very High)`, the enum
    wants `very_low`, so a model that OBEYED the prompt produced None for every
    likelihood and impact -- and because tier derives from the pair, None for
    tier too. The prompt now names the accepted tokens (`jobs.py`), which fixes
    the cause. The normalisation below fixes the class: a real model will not
    reliably emit snake_case however it is asked, and refusing a value it
    plainly meant is the same defect facing the other way -- what `CLAUDE.md`
    records for `int()`, where accepting `"2"` and `2.0` is right and coercing
    `1.9` to 1 is not. `Very High` and `very-high` mean `very_high`; nothing
    here invents a value the model did not send.

    **It was SILENT.** That is the half the client paid for: an unresolvable
    value became None, the entry was stored anyway, the aggregates filtered it
    out while `total_entries` counted it, and no counter anywhere went
    non-zero. So the rejected token is returned rather than dropped, and the
    caller records it. Absence is NOT a rejection -- a field the model never
    sent has nothing to report, and conflating the two would make the counter
    non-zero on every sparse but valid response.
    """
    if value is None:
        # ABSENT. Nothing was supplied, so there is nothing to report.
        return None, None
    raw = str(value).strip()
    if not raw:
        # SUPPLIED AND EMPTY, which is not the same event. A model that sent
        # the field and sent it blank made a claim it could not fill in; a
        # model that never sent it did not. Folding them together would hide
        # the first behind the carve-out written for the second.
        return None, "(empty string)"
    try:
        return enum_cls(raw), None
    except (ValueError, KeyError):
        pass
    # Case and separator ONLY. Not a fuzzy match: "very high", "Very-High" and
    # "VERY_HIGH" are one token typed three ways, while "severe" is a different
    # claim and must still be refused.
    normalised = re.sub(r"[\s\-]+", "_", raw.lower())
    try:
        return enum_cls(normalised), None
    except (ValueError, KeyError):
        return None, raw


def _run_risk_synthesize_batched(
    db: Session,
    llm: LLMClient,
    findings: list[dict],
    *,
    valid_techniques: list[str],
    valid_controls: list[str],
    requested_by: uuid.UUID,
    client_id: uuid.UUID,
    client_org_name: str | None,
) -> tuple[list[dict], int, int, dict[str, int]]:
    """Run risk_synthesize as concurrent batches.

    Returns `(entries, total, failed, discarded)`. The fourth is #122: the merge
    below drops any entry that is not an object, and it dropped them with no
    counter -- so a batch answering with a list of strings contributed nothing
    and said nothing, and the audit row's `findings` count was as high as if it
    had contributed everything.

    Each batch is a real `run_job` call and therefore writes its own `llm_calls`
    row — N rows per run. That is the honest accounting: N separately-billable
    provider calls were made.

    The allow-lists go to EVERY batch. `valid_techniques` / `valid_controls` are
    what stop the model citing a technique or control the client's assessments
    never SCORED, so a batch that did not receive them would be unguarded.
    They cost input tokens, which is the cheap side of this trade.

    **"never contained" is what this said until #403, and it was the sentence
    that made the defect invisible.** It described the guard correctly as
    designed and incorrectly as built: the lists were every row of each
    assessment, and every row is pre-seeded, so "contained" admitted the whole
    catalog. The claim read as a guarantee, sat exactly where a reader would
    check, and was true of a narrower thing than anyone would assume. See
    `_gather_findings` and `app/risk/link_scope.py`.

    Each worker gets its OWN Session bound to the REQUEST session's engine. A
    Session is not thread-safe, and reaching for the module-level SessionLocal
    instead would open a connection outside whatever the caller is bound to —
    which silently bypassed the test suite's injected engine when attack's
    batching was written.

    A partial failure does NOT discard the run: losing one batch should cost the
    consultant that slice, not every entry and the money already spent on them.
    Only a total failure raises, and it raises through `ai_call_boundary` so the
    error stays typed and carries `charged_likely`.
    """
    batches = [
        findings[i : i + _RISK_BATCH_SIZE] for i in range(0, len(findings), _RISK_BATCH_SIZE)
    ] or [[]]

    def _one(batch: list[dict]) -> dict:
        session = Session(bind=db.get_bind())
        try:
            out = run_job(
                session,
                llm,
                "risk_synthesize",
                inputs={
                    "findings": batch,
                    "valid_techniques": valid_techniques,
                    "valid_controls": valid_controls,
                },
                requested_by=requested_by,
                client_id=client_id,
                client_org_name=client_org_name,
            )
            session.commit()
            # Guaranteed a dict by `parse_json_object`; a wrong shape raises
            # and is counted as a failed batch rather than a silent empty one.
            return out.data
        except Exception:
            # Mirror ai_call_boundary: commit so the FAILED row survives the
            # exception, then let it propagate to be counted.
            session.commit()
            raise
        finally:
            session.close()

    # Warm the job registry on THIS thread before any worker touches it. Lazy
    # registration behind a module flag is not something a worker should be the
    # first to trigger.
    get_job("risk_synthesize")

    entries: list[dict] = []
    discarded: dict[str, int] = {}
    failed = 0
    first_error: Exception | None = None

    with ThreadPoolExecutor(max_workers=_RISK_MAX_WORKERS) as pool:
        # Each worker runs inside a COPY of the request's context. A pool thread
        # starts with an empty one, so `correlation_id_var` read None there and
        # every `llm_calls` row a batch wrote lost the request's correlation id
        # -- measured 2026-09-23 on the ATT&CK twin, 0 of 52 live mitre_map rows
        # carried one (no live risk_synthesize row existed to measure). A fresh
        # copy per submit, because one Context cannot be entered by two threads
        # at once. `routes/attack.py` has the same runner and the same fix.
        futures = [pool.submit(contextvars.copy_context().run, _one, b) for b in batches]
        for fut in as_completed(futures):
            try:
                data = fut.result()
            except Exception as exc:  # noqa: BLE001 - counted, not swallowed
                failed += 1
                first_error = first_error or exc
                _log.error(
                    "risk_synthesize_batch_failed",
                    client_id=str(client_id),
                    error=f"{type(exc).__name__}: {exc}",
                )
                continue
            for e in data.get("entries") or []:
                # #122, and it is recorded HERE because this is where the drop
                # happens. The per-entry loop in `generate` has the same guard,
                # but by the time a value reaches it this filter has already
                # removed every non-object -- so a counter there would have sat
                # at zero forever while the real losses happened one layer up.
                # CLAUDE.md: find the line that makes it true and put the record
                # below it.
                if isinstance(e, dict):
                    entries.append(e)
                else:
                    discarded["not_an_object"] = discarded.get("not_an_object", 0) + 1

    _log.info(
        "risk_synthesize_batched",
        client_id=str(client_id),
        findings=len(findings),
        batches_total=len(batches),
        batches_failed=failed,
        entries=len(entries),
        discarded_entries=discarded,
    )

    if failed == len(batches) and first_error is not None:
        # Nothing usable came back. Re-raise inside the boundary so the caller
        # gets the same typed 502 + charged_likely it always did.
        with ai_call_boundary(db, llm, purpose="risk_synthesize"):
            raise first_error

    return entries, len(batches), failed, discarded


@router.post(
    "/clients/{cid}/register/generate",
    response_model=RiskRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a new Risk Register version (admin)",
)
def generate(
    cid: uuid.UUID,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(_llm_dep)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> RiskRegisterResponse:
    # Per-client throttle on the most expensive egress (cross-assessment
    # synthesis). Risk pins the tenant via the path `cid`, not X-Client-Id,
    # so we key on it directly rather than via the current_client dependency.
    limiter.enforce_ai(cid)
    client = _require_client(db, cid)
    g = _gate(db, cid)
    if not g.unlocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Risk Register is locked. Missing: " + "; ".join(g.missing) + ".",
        )
    # REFUSE rather than synthesize from nothing (#237). Without this, moving
    # `_gather_findings` onto `_finalized_for_synthesis` would turn a
    # draft-sourced run into an EMPTY register instead of a refusal -- a register
    # with no entries, generated successfully, which reads as "no risks found".
    # That is a WORSE failure than the one being fixed: it replaces unreviewed
    # content with a confident absence, and both go out under the client's name.
    if g.synthesizable_missing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Risk Register cannot be generated from unapproved work. "
                "Approve first: " + "; ".join(g.synthesizable_missing) + "."
            ),
        )

    findings, valid_techniques, valid_controls, target_sources, link_scopes = _gather_findings(
        db, cid
    )
    client_org = client.legal_name  # NULL when nobody has named the org (D-080)
    # Batched: one request cannot express this job (see _RISK_BATCH_SIZE). A
    # total failure still raises typed, through ai_call_boundary.
    entries_draft, batches_total, batches_failed, discarded_in_batches = (
        _run_risk_synthesize_batched(
            db,
            llm,
            findings,
            valid_techniques=sorted(valid_techniques),
            valid_controls=sorted(valid_controls),
            requested_by=admin.id,
            client_id=cid,
            client_org_name=client_org,
        )
    )
    data = {"entries": entries_draft}

    # New version; supersede the prior current one.
    prior = _latest_register(db, cid)
    next_version = (prior.version + 1) if prior is not None else 1
    register = RiskRegister(
        client_id=cid,
        version=next_version,
        generated_by=admin.id,
        # #240. Captured HERE and never revised -- see `_provenance_snapshot`.
        # `g.not_finalized` is the present-but-unapproved set; the refusal above
        # already cleared the ones that block, so whatever remains contributed
        # nothing and the register now records that permanently rather than only
        # in the response.
        provenance=_provenance_snapshot(db, cid, g.not_finalized),
    )
    # #372. The batch tally is PERSISTED, into the provenance column 0047
    # already added -- no migration, and no new state to keep in step.
    #
    # It was response-only for one revision, and that was wrong in the way this
    # file has been wrong before: `export` and `latest` build their response
    # from a STORED register, so they had nothing to report and the schema
    # default said "zero failed" -- a positive claim about a run nobody
    # recorded. The consultant generated a short register, saw "INCOMPLETE",
    # clicked Export, and the click erased the warning it was warning about.
    #
    # `_serialize` reads this back, so the disclosure is DERIVED from stored
    # state on every path rather than carried by whichever response happened to
    # know. CLAUDE.md: prefer a derivation over a synchronization.
    #
    # Copy-then-reassign. In-place mutation of a plain JSON column does not
    # dirty it and the write is silently lost -- the same trap `entries_intended`
    # documents one field over.
    # AND `or {}` NORMALISES NULL PROVENANCE HERE, WHICH IS A FACT ANY LATER
    # GUARD ON THIS COLUMN INHERITS.
    #
    # After this line `register.provenance` is a dict on every path out of
    # `generate`. So a downstream `if register.provenance is not None:` is
    # always true from here on, and its else-branch is unreachable by
    # construction rather than by luck. That is fine as long as it is SAID:
    # #353 adds exactly such a guard further down, whose else-branch logs
    # `risk_register_intended_count_not_persisted` as a deliberate fail-loud
    # ratchet, and whose own blast-radius note certifies that nothing
    # reassigns this column between the register's construction and the guard.
    # This line is that reassignment.
    #
    # Found by a PAIRS review -- two branches that merge clean and are each
    # correct alone. Neither diff shows it; `CLAUDE.md` records that a per-PR
    # review structurally cannot. Whoever rebases #353 onto this owns the
    # reconciliation, and the choice is theirs: drop the now-vacuous None
    # check, or keep it as a ratchet and say here what would make it reachable
    # again. What is not acceptable is leaving the certificate standing.
    _prov_with_batches = dict(register.provenance or {})
    _prov_with_batches["batches"] = {
        "total": batches_total,
        "failed": batches_failed,
    }
    register.provenance = _prov_with_batches
    db.add(register)
    db.flush()
    if prior is not None:
        prior.superseded_by = register.id

    # Values the model supplied for an enum field that could not be resolved
    # even after case/separator normalisation. #121: these became None in
    # silence, and a register of forty entries with no likelihood, impact or
    # tier returned HTTP 201 with every counter at zero. `field -> [tokens]`,
    # deduped, so the audit row names WHAT to fix rather than only how many.
    rejected_enum_values: dict[str, list[str]] = {}
    # The OUTCOME, not a cause.
    #
    # `rejected_enum_values` names what to fix, and it can only see values that
    # were SUPPLIED and unresolvable. An entry whose `likelihood` key is simply
    # ABSENT produces the identical client-visible result -- no likelihood, no
    # impact, no tier, em dashes down the register and a matrix that drops it --
    # while the rejection map stays `{}` and the audit row reads as clean.
    #
    # That is the defect #121 is about, reachable by a second route, under a
    # record asserting nothing went wrong. So the count below is keyed on what
    # the CLIENT sees rather than on any enumeration of how it happened: it is
    # non-zero exactly when an entry renders without a tier. Causes are a list
    # and lists go stale; an outcome cannot.
    # DERIVED from the findings rather than returned as a fourth value: the
    # source ids ARE the findings' ids, and a second channel for one fact is a
    # second place for it to drift.
    valid_source_ids = {str(f["source_id"]) for f in findings if f.get("source_id") is not None}
    entries_total = 0
    entries_without_tier = 0
    # #132. `field -> [values]`, deduped across the whole run, so the audit row
    # names WHAT to fix -- the same shape `rejected_enum_values` uses one block
    # up, deliberately, because two vocabularies for "the model said something
    # we could not use" is how two halves of one register come to disagree.
    dropped_link_values: dict[str, list[str]] = {}
    # And the OUTCOME, for the same reason `entries_without_tier` exists beside
    # `rejected_enum_values`: the map above can only see values that were
    # SUPPLIED, and it answers "what is wrong with the model's spelling". This
    # answers "what does the consultant see". An entry that offered links and
    # kept none renders exactly like an entry that offered none -- no ATT&CK
    # linkage, no indication any was proposed -- which is #132's whole harm.
    entries_offered_links = 0
    entries_unlinked_after_drops = 0
    # #122. Entries the model sent that this loop DISCARDED -- keyed by why, so
    # the audit row names the fault rather than only its size.
    #
    # `findings` in the audit row is the INPUT. A run that received 137 findings
    # and persisted zero entries wrote a row indistinguishable from one that
    # persisted 137, because nothing ever measured the output. CLAUDE.md: a
    # success record must be written where the success is; this one was written
    # where the input is.
    # Seeded from the BATCH MERGE rather than starting empty: the drops that
    # happen up there are the same fact as the drops down here, and two separate
    # maps would let a reader add them up wrong or read one and think it was
    # the set.
    discarded_entries: dict[str, int] = dict(discarded_in_batches)
    # Seeded with what the MERGE already dropped, so this counts what the model
    # SENT rather than what survived to the loop. Counting only the loop's
    # iterations would report a smaller input than arrived and hide the merge's
    # losses inside a number that looks like agreement.
    #
    # The identity this buys, and BOTH halves of it are load-bearing:
    #
    #     entries_received == entries_total + sum(discarded_entries.values())
    #
    # `entries_total`, NOT `entries_written`. The two are equal exactly when
    # `entries_write_check` says "agreed", and the one interesting state is the
    # one where they are not: the test that expunges a row before the flush
    # produces received 2, total 2, written 1, discarded {} -- so the same
    # sentence written with `entries_written` is false in precisely the run it
    # would matter in, and this comment said that for one round.
    #
    # Every entry the model sent is therefore either counted into the loop or
    # named in the discard map, and any gap between that and what the DATABASE
    # holds is a separate fact, reported separately, by the read-back below.
    # Two claims, not one.
    #
    # It is "asserted rather than described" only in the weak sense: the
    # assertions in `test_risk_register.py` sit under literal equalities that
    # already fix all three operands, so they are arithmetic on constants.
    # Tracked as #321 -- the identity is real, the tests do not exercise it.
    entries_received = sum(discarded_in_batches.values())

    def _record_drops(field: str, values: list[str]) -> None:
        seen = dropped_link_values.setdefault(field, [])
        for value in values:
            if value not in seen:
                seen.append(value)

    def _record(field: str, rejected: str | None) -> None:
        if rejected is None:
            return
        seen = rejected_enum_values.setdefault(field, [])
        if rejected not in seen:
            seen.append(rejected)

    for raw in data.get("entries", []):
        # Counted from what the LOOP saw, not from `len(...)`. The two agree
        # today because a non-list `entries` is already refused upstream with a
        # 502 -- and counting the iterations keeps them agreeing if that ever
        # stops being true, rather than reporting a length nothing read.
        entries_received += 1
        # #122. The false branch EMITS rather than dropping the record. Two
        # causes, kept apart because they are different things to fix: a
        # payload shape the prompt did not ask for, and an entry that is
        # shaped right and has no title to show.
        if not isinstance(raw, dict):
            # NOT REACHABLE through the batched path today -- the merge in
            # `_run_risk_synthesize_batched` filters non-objects out before they
            # get here, and counts them. Kept, and kept COUNTING, because an
            # unfiring guard costs one branch while its absence costs a silent
            # discard the day anything else feeds this loop. Stated so the
            # zero it reports reads as a decision rather than as evidence.
            discarded_entries["not_an_object"] = discarded_entries.get("not_an_object", 0) + 1
            continue
        if not raw.get("title"):
            discarded_entries["no_title"] = discarded_entries.get("no_title", 0) + 1
            continue
        lk, lk_bad = _coerce_enum(Likelihood, raw.get("likelihood"))
        _record("likelihood", lk_bad)
        im, im_bad = _coerce_enum(Impact, raw.get("impact"))
        _record("impact", im_bad)
        # Tier is ALWAYS code-derived, never AI-set.
        tier = tier_for(lk, im).value if (lk is not None and im is not None) else None
        entries_total += 1
        if tier is None:
            entries_without_tier += 1
        # #132: resolve, do not filter. Both halves come back, and the lost
        # half is recorded ON THE ENTRY rather than only counted -- the
        # consultant reads the register, not the generate response.
        techs, techs_dropped = _resolve_links(raw.get("linked_techniques"), valid_techniques)
        controls, controls_dropped = _resolve_links(raw.get("linked_controls"), valid_controls)
        # `source_id` was stored with no validation at all, so an entry could
        # claim provenance from a finding that does not exist. An unrecognised
        # one is dropped rather than persisted: a dangling reference is a claim,
        # and CLAUDE.md's standing rule is that missing data defaults to
        # UNCONFIRMED. Dropped AND recorded -- dropping it silently would be
        # this issue's own defect, committed while fixing it.
        source_kept, source_dropped = _resolve_links(
            [raw["source_id"]] if raw.get("source_id") is not None else None,
            valid_source_ids,
        )
        dropped = {
            field: values
            for field, values in zip(
                LINK_FIELDS,
                (techs_dropped, controls_dropped, source_dropped),
                strict=True,
            )
            if values
        }
        # Driven from the SAME zip as `dropped`, so the audit row and the
        # persisted record cannot name different fields. Three string literals
        # stood here, which made `LINK_FIELDS`' claim that they "cannot
        # disagree" true of the persisted dict and false of the audit row --
        # add a fourth field, trust the comment, ship an audit row missing its
        # drops.
        for field, values in zip(
            LINK_FIELDS, (techs_dropped, controls_dropped, source_dropped), strict=True
        ):
            _record_drops(field, values)
        offered_any = bool(techs_dropped or controls_dropped or techs or controls)
        if offered_any:
            entries_offered_links += 1
            if not techs and not controls:
                entries_unlinked_after_drops += 1
        axis, axis_bad = _coerce_enum(RiskAxis, raw.get("axis"))
        _record("axis", axis_bad)
        action, action_bad = _coerce_enum(RecommendedAction, raw.get("recommended_action"))
        _record("recommended_action", action_bad)
        db.add(
            RiskEntry(
                register_id=register.id,
                client_id=cid,
                title=str(raw["title"])[:512],
                description=raw.get("description"),
                axis=axis.value if axis else None,
                source=raw.get("source"),
                source_id=source_kept[0] if source_kept else None,
                linked_techniques=techs,
                linked_controls=controls,
                # `{}` when nothing was dropped, never NULL. NULL is reserved
                # for pre-0048 rows and means "not recorded" -- see the
                # migration. Writing `{}` here is what makes a clean entry a
                # positive claim rather than an absence anyone may read either
                # way.
                dropped_links=dropped,
                likelihood=lk.value if lk else None,
                impact=im.value if im else None,
                tier=tier,
                compensating_controls=raw.get("compensating_controls"),
                residual_risk=raw.get("residual_risk"),
                recommended_action=action.value if action else None,
                rationale=raw.get("rationale"),
                origin="ai_generated",
                trust="admin_assisted",
            )
        )

    # Counted from the flushed rows, not from the loop.
    #
    # ## Blast radius, measured before keeping this
    #
    # A tally incremented beside each `db.add` counts INTENTIONS. The
    # population this read-back protects is "a run whose audit row claims rows
    # the database does not contain", and **no current writer can produce
    # one**, measured on this tree rather than assumed: no ORM event listener
    # touches `RiskEntry` (the only `before_flush` hook guards audit rows), no
    # trigger exists on `risk_entries` (the only two are on `audit_entries`),
    # `UUIDPKMixin` defaults to `uuid4` so two adds cannot collide on identity,
    # and a failing flush RAISES -- which produces no audit row at all rather
    # than a wrong one.
    #
    # It is kept as a RATCHET, and the first draft of this comment justified it
    # with "something between the add and the flush drops one" stated as a live
    # hazard. It is not one today. What would make it reachable again: a
    # `before_flush` listener on `RiskEntry`, a database trigger or rule on
    # `risk_entries`, a cascade that deletes siblings, or a partial-failure
    # write path that swallows instead of raising. Each is an ordinary change
    # somebody could make without touching this file.
    #
    # ## And it is pinned, rather than only argued
    #
    # A read-back nothing observes is indistinguishable from `entries_written =
    # entries_total`, and that substitution left every test on this branch
    # green. So the two counts are COMPARED here and a disagreement is recorded
    # loudly -- in the log and in the audit row -- which is what
    # `test_a_row_dropped_between_add_and_flush_is_recorded` constructs, by
    # installing exactly the `before_flush` listener named above. The ratchet
    # now has something that fires, and the test that fires it is also the
    # demonstration that the state is reachable at all.
    db.flush()
    entries_written = db.execute(
        select(func.count()).select_from(RiskEntry).where(RiskEntry.register_id == register.id)
    ).scalar_one()
    # Emitted in BOTH states. "They agreed" and "nobody compared" must not be
    # the same absence -- an audit row with no verdict here would read as the
    # former and mean the latter.
    entries_write_check = "agreed" if entries_written == entries_total else "MISMATCH"
    # #330. The INTENDED tally is a generate-time fact, so `_serialize` -- which
    # reads the table -- cannot recover it a week later. Persisted into the
    # provenance blob rather than a new column: no migration, and provenance is
    # already where this register's generate-time facts live (`inputs`,
    # `excluded`).
    #
    # Without it the client-facing banner has only the POST-LOSS count to
    # divide by, so a register that lost a row reads "0 of 1" instead of
    # "0 of 2" and presents as complete. Shrinking the denominator until the
    # ratio looks right is not an honest answer to losing a row.
    #
    # ## Blast radius, measured before keeping this
    #
    # THE GUARD CANNOT BE FALSE ON THIS PATH. `register` is constructed above
    # with `provenance=_provenance_snapshot(...)`, and that function ends
    # `return {"inputs": inputs, "excluded": list(excluded)}` unconditionally
    # -- no early return, no conditional -- and nothing between the
    # construction and here reassigns it. So this is a RATCHET, not protection
    # against a live hazard, and saying so is the difference between a reader
    # sizing their change against a real state and against one that cannot
    # occur.
    #
    # What would make it reachable: any writer that constructs a register with
    # NULL provenance (`seed_demo.py` already writes a partial dict, so the
    # shape is not hypothetical), or a `_provenance_snapshot` that gains an
    # early return.
    #
    # THE FALSE BRANCH IS NOT SILENT, because a silent one would publish
    # `entries_intended: null` -- "nobody counted" -- over a run that DID
    # count, and the three-state rendering treats that as benign. A zero-value
    # record that names the fault is honest; silence is not.
    if register.provenance is not None:
        _prov_with_count = dict(register.provenance)
        _prov_with_count["entries_intended"] = entries_total
        # #403. The scored share of each assessment, persisted for the same two
        # reasons as the tally above: it is a GENERATE-TIME fact, and the
        # provenance blob costs no migration.
        #
        # Written HERE, below the flush and beside the count it belongs with,
        # because a record saying "this is what the run was allowed to cite"
        # must sit after the run rather than beside the intention. It is read
        # back by `_serialize`, so the register's own disclosure survives a
        # reload -- the half #316 shipped without.
        _prov_with_count["link_scope"] = {
            service: {"scored": len(sc.codes), "total": sc.total}
            for service, sc in link_scopes.items()
        }
        register.provenance = _prov_with_count
        db.add(register)
    else:
        _log.error(
            "risk_register_intended_count_not_persisted",
            register_id=str(register.id),
            entries_intended=entries_total,
            # #403 rides in the same blob, so a NULL provenance loses the
            # scored-share disclosure too. Named here rather than left to the
            # field name above, or the log would report one of two losses and
            # read as complete.
            link_scope={
                service: {"scored": len(sc.codes), "total": sc.total}
                for service, sc in link_scopes.items()
            },
            reason="provenance is NULL, which no current writer produces",
        )
    if entries_written != entries_total:
        _log.error(
            "risk_register_entries_lost_before_flush",
            register_id=str(register.id),
            entries_total=entries_total,
            entries_written=entries_written,
            lost=entries_total - entries_written,
        )

    audit(
        db,
        action="risk_register.generated",
        target_type="risk_register",
        target_id=register.id,
        actor_user_id=admin.id,
        details={
            "version": next_version,
            "findings": len(findings),
            # #84. The TARGET each service was compared against, and where it
            # came from. Every finding is "current is below target", so this is
            # the operand that decides whether a row exists -- and it was a
            # hardcoded 3 until now, for every client regardless of what they
            # engaged for.
            #
            # A register computed against the wrong baseline is not visibly
            # wrong: right shape, plausible counts, no way for a reader to tell
            # which tier it measured against. Recording it here is what makes
            # the next one falsifiable, and `source` keeps "the client chose
            # nothing" apart from "the client's choice could not be used".
            "targets": target_sources,
            "batches_total": batches_total,
            "batches_failed": batches_failed,
            # Both present rather than omitted, so a reader can tell
            # "nothing went wrong" from "nobody looked".
            #
            # They answer different questions and neither implies the other.
            # `rejected_enum_values` names WHAT to fix and sees only supplied
            # values. `entries_without_tier` is the OUTCOME and is non-zero
            # whenever an entry reaches the client with no tier, whatever the
            # cause -- including a key the model simply omitted, which the
            # rejection map cannot see.
            "rejected_enum_values": rejected_enum_values,
            # #330. RENAMED from `entries_total`, which named two different
            # quantities on two surfaces: this LOOP TALLY, and the table
            # read-back `_serialize` publishes under the same key. They agree
            # on every run any current writer can produce and diverge in
            # exactly one state -- the one `test_a_row_dropped_between_add_and_flush_is_recorded`
            # constructs -- where the audit row said 2 and the response said 1
            # under one name.
            #
            # The two names will outlive the measurements that make them safe.
            "entries_intended": entries_total,
            "entries_without_tier": entries_without_tier,
            # #403. What the run was ALLOWED to cite, per service, and out of
            # how many rows. Beside the drop counters deliberately: together
            # they separate "the model named something wrong" from "the
            # assessment scored almost nothing", which are the two ways a
            # register comes out sparsely linked and have opposite remedies.
            "link_scope": {
                service: {"scored": len(sc.codes), "total": sc.total}
                for service, sc in link_scopes.items()
            },
            # #132, and the same pairing: the map names what to fix, the count
            # names what the consultant sees. `entries_offered_links` is the
            # denominator -- "3 entries lost every link" means something
            # different at 3 of 4 than at 3 of 40.
            "dropped_link_values": dropped_link_values,
            "entries_offered_links": entries_offered_links,
            "entries_unlinked_after_drops": entries_unlinked_after_drops,
            # #122. What the run RECEIVED and what it WROTE, side by side, plus
            # why the difference.
            #
            # `entries_received` is counted from the payload rather than from
            # `findings`: the prompt drafts one entry per finding but a batch
            # can fail, and reporting the finding count as the input would
            # hide a lost batch inside a discard number. `entries_written` is
            # read back from the flushed rows -- the count of what is in the
            # database, not the count of `db.add` calls, which is the same
            # distinction D-031 draws for the concurrent case.
            "entries_received": entries_received,
            "entries_written": entries_written,
            "entries_write_check": entries_write_check,
            "discarded_entries": discarded_entries,
        },
    )
    db.commit()
    # `g.not_finalized` is the full present-but-unapproved set; the refusal
    # above already cleared the ones that block. Whatever remains contributed
    # nothing to this register, and the register says so.
    # `excluded_inputs` is NOT passed in. `db.commit()` above has already
    # persisted the snapshot, so `_serialize` reads the same bytes `latest`
    # will read next week -- one answer instead of two kept in step. That also
    # makes the generate assertions cover write -> persist -> read end to end,
    # which is what closed #244 instance 1's write half.
    return _serialize(
        db,
        register,
        batches_total=batches_total,
        batches_failed=batches_failed,
    )


def _write_artifact(
    db: Session,
    *,
    storage: StorageBackend,
    user: User,
    client_id: uuid.UUID,
    filename: str,
    mime_type: str,
    data: bytes,
) -> Artifact:
    from hashlib import sha256

    key = f"risk_register/{user.id}/{uuid.uuid4()}/{filename}"
    storage.put(key, data, content_type=mime_type)
    art = Artifact(
        client_id=client_id,
        title=filename,
        file_storage_key=key,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha256(data).hexdigest(),
        origin=ArtifactOrigin.CONSULTANT_APPROVED,
        stage="risk_register.export",
        uploaded_by=user.id,
    )
    db.add(art)
    db.flush()
    return art


@router.post(
    "/clients/{cid}/register/export",
    response_model=RiskRegisterResponse,
    summary="Render + store the current Risk Register as XLSX/PDF/Word (admin)",
)
def export(
    cid: uuid.UUID,
    admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[StorageBackend, Depends(_storage_dep)],
) -> RiskRegisterResponse:
    client = _require_client(db, cid)
    # #237 GUARDS GENERATE, NOT EXPORT, AND THE BLAST RADIUS IS STATED RATHER
    # THAN ASSUMED. `CLAUDE.md` requires checking it, and the 0044 precedent
    # worked because the radius was countable ("zero RELEASED assessments").
    #
    # Here it is NOT countable, and that is the finding rather than an excuse.
    # Every register created before this change was synthesized under the old
    # `_latest`, which read DRAFT assessments. Those rows stay exportable, and
    # `export` sets `finalized_at` -- the single condition
    # `clients.py::risk_dashboard` gates the CLIENT dashboard on -- so exporting
    # one publishes it.
    #
    # `models/risk_register.py` records no provenance: no source assessment ids,
    # no excluded inputs. So NO SINGLE COLUMN answers "was this draft-sourced".
    #
    # That is not the same as unanswerable, and an earlier draft of this note
    # said "INDISTINGUISHABLE ... in any database", which ended the check
    # `CLAUDE.md` requires instead of performing it. A reconstruction bounds it:
    # join each register's `created_at` against the assessment `_latest` would
    # have picked (highest non-discarded version) and ask whether that row's
    # `approved_at` was null or later. Measured on the dev database 2026-09-09:
    # **6 of 6 registers were built from an ATT&CK assessment unapproved at
    # build time, 6 of 6 from an unapproved ZT one, and 5 of the 6 are
    # finalized** -- so on this database the radius is every register, and
    # finalizing published five of them.
    #
    # The reconstruction is APPROXIMATE and its error direction is stated: it
    # reads today's discard state and today's version ordering, so a row
    # discarded or re-versioned since would change which assessment `_latest`
    # picked. It bounds the radius; it does not settle any individual row.
    # Persisting provenance at generate is what makes the question answerable
    # exactly, and that is #240.
    #
    # #240, and the reason it is checked HERE against a SNAPSHOT rather than
    # recomputed: guarding export on TODAY's statuses would re-read statuses
    # that have moved since the register was built, so an assessment approved
    # after generation would certify a register that never saw it. D-053.
    reg = _latest_register(db, cid)
    if reg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generate a Risk Register before exporting.",
        )

    # #240. Refuse to publish a register built from work nobody approved.
    #
    # Read from the SNAPSHOT written at generate, never recomputed. The three
    # states are deliberately distinct and only one of them is silence:
    #
    #   * provenance records inputs, all approved   -> export;
    #   * provenance records an unapproved input    -> refuse, name it;
    #   * provenance is NULL (pre-0047)             -> not recorded. Cannot be
    #     certified either way, so it is refused UNLESS the register was already
    #     finalized -- an already-delivered register was published under the old
    #     rules, and blocking its re-export protects nobody while breaking a
    #     working path. That carve-out is stated rather than implicit, and it is
    #     bounded: 0 of 1 registers in the dev database were unfinalized when
    #     this was written, so nothing is mid-flight through the hole.
    _prov = reg.provenance
    # HOISTED, and the nesting it replaces was a live defect. This fact was
    # consulted only inside the `_prov is None` branch, so a register whose
    # provenance dict merely LACKS `inputs` -- which is exactly what
    # `seed_demo.py` writes -- could never reach the carve-out and began
    # refusing its own re-export with 409. Measured, not argued: the test
    # `test_export_allows_the_seeded_shape_a_finalized_register_with_no_inputs_key`
    # returned 409 against this code and 200 against the version below.
    #
    # The reasoning is the same for both shapes, which is why it is one fact:
    # an already-finalized register was certified when it was finalized, and
    # refusing to re-export it protects nobody while breaking a delivered path.
    _already_delivered = reg.finalized_at is not None
    if _prov is None:
        if not _already_delivered:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This register predates provenance recording, so what it was "
                    "synthesized from is unknown and cannot be certified. "
                    "Regenerate it before exporting."
                ),
            )
    else:
        # A RATCHET, and unreachable today. Say so rather than let a reader
        # believe this is what catches the hazard.
        #
        # `_provenance_snapshot` records only what `_finalized_for_synthesis`
        # returns, and that resolver filters `status.in_(_FINALIZED)` where
        # `_FINALIZED = ("approved", "released")`. So every status the snapshot
        # CAN hold is already approved or released, and this list is empty by
        # construction for every register generated on or after 0047. The only
        # way in is mutating stored provenance, which is exactly how the test
        # for it reaches this branch.
        #
        # It is kept because the thing making it unreachable is one resolver's
        # WHERE clause, and that is a thing a future change can loosen without
        # noticing what depended on it. `test_the_synthesis_path_must_filter_on_finalized`
        # is what holds that clause in place; if that test is ever removed or
        # weakened, this branch stops being decorative and starts being the
        # last thing between unapproved work and a client's name.
        #
        # The pre-0047 DRAFT-input register -- the hazard #240 opens with -- is
        # NOT caught here. It has NULL provenance and is caught by the branch
        # above. Two different registers; two different branches.
        # A dict with no `inputs` key is NOT "recorded, all approved" -- it is a
        # fourth state the three enumerated above do not cover, and
        # `(_prov.get("inputs") or [])` would land it silently in the
        # reassuring bucket. `seed_demo.py` is currently the only writer of
        # that shape (it records `{"excluded": []}` and omits `inputs`
        # deliberately, because it does not go through `_provenance_snapshot`
        # and a hand-written input list would be a second, drifting answer).
        # The seeded register IS this shape, and the claim that used to stand
        # here -- "it exports through the carve-out above either way and the
        # blast radius is zero" -- was false. `finalized_at` was consulted only
        # when provenance was NULL, so the seeded dict never reached it and
        # every re-export of the demo register 409'd. The carve-out is now a
        # hoisted fact both branches read, and two tests pin the pair: the
        # finalized case must export, the unfinalized case must still refuse.
        #
        # Do NOT "fix" a caller by writing `"inputs": []` instead; an empty
        # list is exactly as vacuous and loses the distinction.
        if "inputs" not in _prov and not _already_delivered:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    # NOT `register_predates_provenance`, which was the reason
                    # this raised for one round and is false of the only shape
                    # that reaches it: this register does not predate
                    # provenance, it HAS provenance with one key missing. A
                    # reason mapped to copy would have named the wrong cause.
                    "reason": "register_inputs_not_recorded",
                    "message": (
                        "This register records which assessments were excluded but not "
                        "which were used, so its inputs cannot be certified. Re-generate "
                        "it before exporting."
                    ),
                },
            )
        unapproved = [
            f"{i.get('kind')} v{i.get('version')} ({i.get('status')})"
            for i in (_prov.get("inputs") or [])
            if str(i.get("status", "")).lower() not in ("approved", "released")
        ]
        if unapproved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This register was synthesized from work that was not "
                    "approved: " + "; ".join(unapproved) + ". Exporting would "
                    "put it under the client's name. Regenerate it now that the "
                    "inputs are approved."
                ),
            )
    entries = (
        db.execute(
            select(RiskEntry).where(RiskEntry.register_id == reg.id).order_by(RiskEntry.created_at)
        )
        .scalars()
        .all()
    )
    org = client.legal_name  # NULL when nobody has named the org (D-080)
    # #403. The scored share reaches the client's DELIVERABLE, not only the
    # consultant's screen -- read from the same persisted provenance the
    # response reads, so the PDF and the dashboard cannot disagree about one
    # register. `_link_scope_fields` is the single reader of that blob, for the
    # reason this file already gives at its `resolve_target_tier` import: a
    # second parser is how two surfaces come to disagree about one client.
    _scope_rows = _link_scope_fields(reg.provenance)["excluded_unscored_links"]
    ctx = risk_exporters.build_context(
        client_legal_name=org,
        version=reg.version,
        entries=entries,
        link_scope=[(r.service, r.scored, r.total) for r in _scope_rows],
    )
    today = utcnow().date()

    def _rr_name(extension: str) -> str:
        # §15.5: {Company}_Risk_Register{MMDDYY}[_v{n}].ext
        return deliverable_filename(
            company=org,
            service_slug=SERVICE_SLUG_RISK_REGISTER,
            extension=extension,
            day=today,
            version=reg.version,
        )

    xlsx = _write_artifact(
        db,
        storage=storage,
        user=admin,
        client_id=cid,
        filename=_rr_name("xlsx"),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=risk_exporters.render_xlsx(ctx),
    )
    pdf = _write_artifact(
        db,
        storage=storage,
        user=admin,
        client_id=cid,
        filename=_rr_name("pdf"),
        mime_type="application/pdf",
        data=risk_exporters.render_pdf(ctx),
    )
    docx = _write_artifact(
        db,
        storage=storage,
        user=admin,
        client_id=cid,
        filename=_rr_name("docx"),
        mime_type=DOCX_MIME,
        data=risk_exporters.render_docx(ctx),
    )
    reg.xlsx_artifact_id = xlsx.id
    reg.pdf_artifact_id = pdf.id
    reg.docx_artifact_id = docx.id
    reg.finalized_at = utcnow()
    audit(
        db,
        action="risk_register.exported",
        target_type="risk_register",
        target_id=reg.id,
        actor_user_id=admin.id,
        details={"version": reg.version},
    )
    db.commit()
    return _serialize(db, reg)


@router.get(
    "/clients/{cid}/register/latest",
    response_model=RiskRegisterResponse,
    summary="The current Risk Register version (admin)",
)
def latest(
    cid: uuid.UUID,
    _admin: Annotated[User, _admin_required],
    db: Annotated[Session, Depends(get_db)],
) -> RiskRegisterResponse:
    _require_client(db, cid)
    reg = _latest_register(db, cid)
    if reg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Risk Register generated yet.",
        )
    return _serialize(db, reg)


def _dropped_citations(entries: list) -> int | None:
    """#403. How many CITATION VALUES a register's run discarded, three-state.

    `None` means nobody counted; a number -- including a legitimate `0` -- means
    somebody did. `schemas/risk.py`'s field comment carries the argument for why
    the third state is not `0`.

    ## The empty register is its own branch, deliberately

    `all(e.dropped_links is None for e in entries)` is vacuously TRUE for an
    empty list, so writing this as a one-line conditional would report a
    zero-entry register as "nobody counted". That is false: `_resolve_links` runs
    per entry, so a register with no entries had no citation offered and dropped
    none -- an OBSERVED zero, not an absence. Reporting it as `None` would
    understate what the run actually established.

    The distinction is written as a branch rather than left to `all()`'s vacuous
    truth because a vacuous-truth branch is a decision nobody made, and this file
    already records the cost of those.

    ## Partial coverage is summed, and the gap is disclosed elsewhere

    Where some entries carry a record and some do not (a register generated
    before 0048 and since partly regenerated), this sums the ones that do.
    `entries_links_not_recorded` is the count this could not see, and the two
    render together -- a scalar that silently summed a subset with nothing naming
    the population would be the partial-read-as-whole-answer defect.
    """
    if entries and all(e.dropped_links is None for e in entries):
        return None
    return sum(
        len(values)
        for e in entries
        for values in (e.dropped_links or {}).values()
        # A persisted `dropped_links` value is a list of discarded strings. A
        # non-list would be a blob no writer produces; skipping it here rather
        # than raising keeps a malformed row from 500-ing a read, and the entry
        # counters beside this one still report the row as having drops.
        if isinstance(values, list)
    )


def _link_scope_row_fault(counts: object) -> str | None:
    """Why one persisted `link_scope` row is unusable, or None if it is fine.

    Separated from `_link_scope_fields` so the CALLER's response to a fault is a
    single line -- see the comment at that line. A validator whose every failure
    branch is inline is a validator whose failure POLICY cannot be changed, or
    mutated, in one edit.

    Returns a reason string rather than a bool, because the log line that
    records this is the only place a malformed blob is ever visible: nothing
    user-facing can say "the provenance is malformed", and "invalid" without a
    reason is the empty-reason defect `check_test_integrity` exists to reject.
    """
    if not isinstance(counts, dict):
        return "service entry is not an object"
    scored, total = counts.get("scored"), counts.get("total")
    for name, value in (("scored", scored), ("total", total)):
        # `bool` is an `int` in Python, so excluding it is load-bearing rather
        # than defensive: `isinstance(True, int)` is True and `True` would render
        # as a scored count of 1. `CLAUDE.md`: `int()` is not a validator.
        if not isinstance(value, int) or isinstance(value, bool):
            return f"{name} is not a plain integer"
    # NO NARROWING `assert` HERE, and the absence is deliberate rather than an
    # oversight: bandit flags every `assert` as B101, `B101` is not in
    # `pyproject.toml`'s `skips`, and `CLAUDE.md` records that ruff's
    # suppression comment for S101 does NOT suppress bandit.
    #
    # THE DIRECTIVE IS NAMED IN WORDS RATHER THAN SPELLED, and that is not
    # squeamishness: ruff parses its own suppression token out of ANY comment,
    # including a sentence about the token, and two drafts of this paragraph
    # each emitted an invalid-directive warning for quoting it. A marker means
    # something wherever it appears -- which is the same class of defect as the
    # asserts below it, one layer down.
    #
    # Both asserts this function briefly carried turned CI's Python job red,
    # caught here rather than there. The comparison below is
    # reached only after the loop above has proved both operands are plain
    # ints, so nothing is lost by dropping them.
    if not isinstance(scored, int) or not isinstance(total, int):  # pragma: no cover
        return "counts are not plain integers"
    if scored < 0 or total < 0 or scored > total:
        return "counts are not a scored-subset-of-total pair"
    return None


_NOT_RECORDED = {"excluded_unscored_links": [], "excluded_unscored_links_recorded": False}


def _link_scope_unreadable(reason: str, **fields: object) -> dict:
    """The #403 disclosure withheld because this blob could not be read.

    HOISTED TO MODULE LEVEL, and that is the fix rather than a tidy. It was a
    closure defined BELOW `_link_scope_fields`' first return, so the two inputs
    that return earliest -- a NULL provenance and a non-dict -- could not reach
    it however the code was written. The docstring above promised all four
    unreadable shapes "plus a loud log" and two of them were silent: the only
    visibility a malformed blob has, absent for the two cases a real writer is
    likeliest to produce.

    Same shape as everything else this change is about -- "I could not look"
    sharing a branch, and here a RETURN STATEMENT, with "nothing to report" --
    committed inside the function written to close it.
    """
    _log.error("risk_register_link_scope_unreadable", reason=reason, **fields)
    return dict(_NOT_RECORDED)


def _link_scope_fields(stored: object) -> dict:
    """The #403 disclosure fields, read out of a register's provenance blob.

    Returns the two keys `_serialize` splats, and the two keys are one decision:
    WHAT was scored, and whether this function was able to answer at all.

    ## Four states, and the split between the first two is the point

      * NO `link_scope` KEY -- this register predates the recording. Nothing on
        file says how much was scored, which is NOT "everything was scored".
        `recorded=False`, empty list, and SILENT: there is no fault to report,
        every register generated before this shipped is in this state, and
        logging an error per read would be noise that teaches readers to ignore
        the log.
      * A NULL OR NON-DICT `provenance` -- `recorded=False` AND A LOUD LOG. This
        is not "predates the recording", it is a blob this function cannot read,
        and the two must not share a branch. They did: the condition was
        `not isinstance(stored, dict) or "link_scope" not in stored`, one `or`
        and one return covering both, with the logging helper defined below it
        and therefore unreachable from it.
      * A key holding per-service counts, EVERY ONE READABLE and AT LEAST ONE
        PRESENT -- `recorded=True`, one row each.
      * A key this function cannot fully read -- a non-dict, an EMPTY object, or
        ANY malformed row -- `recorded=False` and a loud log.

    ## Why an empty object is unreadable rather than "recorded, zero services"

    `{}` used to fall through the loop to `recorded=True` with no rows, and the
    dashboard -- gated on `recorded` alone at the time -- rendered the heading
    "Links can only cite what each assessment has scored" over an empty list.
    `render_xlsx`' own comment calls that state "a false claim rather than an
    absence" and refuses it; the screen took the option the exporter refuses.

    UNREACHABLE from the one writer, measured: `_gate` sets
    `unlocked = has_attack and (has_csf or has_zt)` from `_finalized_for_synthesis`
    for all three services, and `generate` 409s unless `synthesizable_missing` is
    empty, so `link_scopes` always carries at least two services. So this is a
    ratchet -- and it is the one sibling of a hardened class that was left
    unhandled, which is the unstated-exemption shape rather than a judgement.

    ## The partial read is the trap, and the first version of this walked into it

    It validated each row and `continue`d past a bad one, then returned
    `recorded=True`. So a blob carrying one good service and one malformed one
    reported a COMPLETE answer over a PARTIAL read -- a consultant would see
    "ATT&CK 12 of 700" and no CSF line, indistinguishable from a register that
    genuinely had no CSF assessment.

    ## Reachability, measured rather than assumed

    NO CURRENT WRITER CAN PRODUCE ANY UNREADABLE SHAPE. `generate` builds
    `{"scored": len(sc.codes), "total": sc.total}` -- two `int`s by construction
    -- and `_provenance_snapshot` ends `return {"inputs": ..., "excluded": ...}`
    unconditionally, so `generate` cannot write a NULL or non-dict provenance
    either. `seed_demo.py` writes no `link_scope` key at all, which is state one.

    So every validation here is a RATCHET. What would make it reachable is
    ordinary: a hand-edited blob, a migration backfilling the key, a future
    writer persisting a float or a string, or a second writer recording only some
    services. The `bool` exclusion is part of the same ratchet -- NOT
    "load-bearing", which an earlier draft of its comment claimed and which
    asserts a reachability no writer has.
    """
    if not isinstance(stored, dict):
        return _link_scope_unreadable("provenance is not an object", got=type(stored).__name__)
    if "link_scope" not in stored:
        # STATE ONE, and the only silent return in this function. Not a fault:
        # every register generated before #403 shipped is here.
        return dict(_NOT_RECORDED)
    raw = stored.get("link_scope")
    if not isinstance(raw, dict):
        return _link_scope_unreadable("link_scope is not an object", got=type(raw).__name__)
    if not raw:
        return _link_scope_unreadable("link_scope names no service")
    rows: list[LinkScopeDisclosure] = []
    for service, counts in raw.items():
        fault = _link_scope_row_fault(counts)
        if fault is not None:
            # ONE LINE, and it is the line that decides the whole behaviour of
            # this function. The first version `continue`d here and still
            # returned `recorded=True`; mutating this back to `continue` is what
            # `test_an_unreadable_scope_reports_NOT_RECORDED_rather_than_a_partial_answer`
            # is verified red against.
            return _link_scope_unreadable(fault, service=str(service), counts=repr(counts))
        # `counts` is a dict carrying two plain ints: `_link_scope_row_fault`
        # returned None, which it can only do after proving both.
        rows.append(
            LinkScopeDisclosure(
                service=str(service),
                scored=counts["scored"],  # type: ignore[index]
                total=counts["total"],  # type: ignore[index]
            )
        )
    return {
        "excluded_unscored_links": sorted(rows, key=lambda r: r.service),
        "excluded_unscored_links_recorded": True,
    }


def _serialize(
    db: Session,
    register: RiskRegister,
    *,
    batches_total: int | None = None,
    batches_failed: int | None = None,
) -> RiskRegisterResponse:
    # #372. Read the persisted tally back when the caller did not supply one,
    # so `export` and `latest` report the run the register came from instead of
    # defaulting to a claim of completeness.
    #
    # Both stay None when provenance predates this, and None renders NO banner
    # either way -- "nobody counted" is not "nothing failed", and the web type
    # is `number | null` so a consumer can tell them apart. The residual is
    # stated rather than hidden: a register generated before this shipped
    # cannot be distinguished from a complete one, and nothing in the product
    # can clear that. Fail-closed is unavailable here because there is no
    # record to fail closed ON; what is available is refusing to assert the
    # positive, which is what None does.
    if batches_total is None and batches_failed is None:
        _recorded = (register.provenance or {}).get("batches")
        if isinstance(_recorded, dict):
            _t = _recorded.get("total")
            _f = _recorded.get("failed")
            # Both, and both ints. A half-written record is not a tally, and
            # `bool` is an `int` in Python -- exclude it, per CLAUDE.md's rule
            # that a coercion is not a validator.
            if (
                isinstance(_t, int)
                and not isinstance(_t, bool)
                and isinstance(_f, int)
                and not isinstance(_f, bool)
            ):
                batches_total = _t
                batches_failed = _f

    entries = (
        db.execute(
            select(RiskEntry)
            .where(RiskEntry.register_id == register.id)
            .order_by(RiskEntry.created_at)
        )
        .scalars()
        .all()
    )
    from app.risk.engine import RiskTier

    tiers = [RiskTier(e.tier) for e in entries if e.tier]
    axes = [RiskAxis(e.axis) for e in entries if e.axis]
    actions = [RecommendedAction(e.recommended_action) for e in entries if e.recommended_action]

    def _fn(aid: uuid.UUID | None) -> str | None:
        if aid is None:
            return None
        art = db.get(Artifact, aid)
        return art.title if art else None

    # #244 instance 1. `excluded_inputs` was passed in by ONE call site -- the
    # POST that generates -- so `latest` and `export` returned `[]` and the
    # disclosure did not survive a page reload. It is the same argument the
    # `entries_with_dropped_links` comment below makes, one field up: a
    # register read back next week must report what the generate run reported.
    #
    # The value is persisted. #240's migration 0047 put it in
    # `register.provenance["excluded"]`, written by `_provenance_snapshot` and
    # never revised. Nothing needed building; the read-back was simply never
    # wired, and `excluded_inputs: list[str] = []` could not express the
    # difference between "nothing was excluded" and "nobody recorded".
    #
    # THREE STATES, and the third is why `recorded` exists as its own field:
    #
    #   provenance is NULL      -> pre-0047. NOT RECORDED. `recorded=False`.
    #   provenance["excluded"]  -> [] means nothing was excluded, and a list
    #                              means these were. `recorded=True` for both.
    #
    # Collapsing NULL into `[]` would tell a consultant that a register built
    # before provenance existed had a clean input set, which is a false
    # assurance about the one population that cannot be checked.
    #
    # There is NO explicit `excluded_inputs=` override any more, and removing it
    # is the fix rather than a tidy-up. The generate handler used to pass
    # `g.not_finalized` while `_provenance_snapshot` stored the same expression
    # -- two answers to one question, kept in step by hand. So every assertion
    # on the generate response was green off the parameter and NOTHING read the
    # stored value back: the third argument to `_provenance_snapshot` was
    # replaceable with `[]` with the suite green, and the resulting reload
    # reported `excluded_inputs: []` with `recorded=True` -- a positive
    # certificate that the server looked and nothing was withheld, which is
    # worse than the `[]` #244 was filed for.
    #
    # `db.commit()` runs before this call, so the snapshot is already readable.
    # Derivation over synchronization, and the existing generate assertions now
    # cover write -> persist -> read for free.
    stored = register.provenance
    # A LIST, not merely a PRESENT KEY. `"excluded" in stored` with `or []`
    # let a null collapse to an empty list carrying `recorded=True` -- a
    # positive certificate that the server looked and withheld nothing,
    # manufactured out of a value recording nothing. The comment on the export
    # guard above calls that outcome worse than the bare `[]` #244 was filed
    # for; this is the same fourth state, one function down, and it was the
    # half that was left.
    #
    # Unreachable today -- `_provenance_snapshot` always writes a list and the
    # seed writes `[]` -- and kept as a ratchet for the reason the export guard
    # is: the seed proves hand-written provenance dicts are ordinary here, and
    # the seed is what produced the export defect this PR fixed.
    _excluded = stored.get("excluded") if isinstance(stored, dict) else None
    if isinstance(_excluded, list):
        resolved_excluded, excluded_recorded = list(_excluded), True
    else:
        resolved_excluded, excluded_recorded = [], False

    return RiskRegisterResponse(
        excluded_inputs=resolved_excluded,
        excluded_inputs_recorded=excluded_recorded,
        entries_total=len(entries),
        # #330. From provenance, because it is a GENERATE-TIME fact this
        # function cannot recompute -- it reads the table, and a row lost
        # before the flush is not in the table to be counted. Absent on any
        # register generated before the field existed, which renders as
        # silence rather than as a zero.
        entries_intended=(stored.get("entries_intended") if isinstance(stored, dict) else None),
        entries_without_tier=sum(1 for e in entries if e.tier is None),
        # #132, derived here rather than passed in, so a register read back next
        # week reports the same thing the generate run did.
        entries_with_dropped_links=sum(1 for e in entries if e.dropped_links),
        entries_unlinked_after_drops=sum(
            1
            for e in entries
            if e.dropped_links and not e.linked_techniques and not e.linked_controls
            # `source_id` is a link field but not a LINKAGE: an entry whose
            # source_id was dropped still shows its technique links, so counting
            # it here would report an outcome the consultant does not see.
            and any(e.dropped_links.get(f) for f in ("linked_techniques", "linked_controls"))
        ),
        entries_links_not_recorded=sum(1 for e in entries if e.dropped_links is None),
        # #403, the three-state VALUE tally, derived here for the same reason the
        # three entry counters above are: it describes the REGISTER, so it is
        # correct whenever the register is read rather than only on the generate
        # response. Possible only because the drop is PERSISTED (0048).
        #
        # `None` when NO entry carries a record -- nobody counted -- and a number
        # otherwise, including a legitimate 0. See the field's own comment in
        # `schemas/risk.py` for why `int = 0` would be a false positive claim.
        #
        # `sum(len(v) ...)` over the persisted lists counts VALUES, not entries;
        # `source_id` is included because a discarded provenance claim is a
        # discarded citation, and the consultant-facing copy names it separately.
        dropped_citations=_dropped_citations(entries),
        # #403, read back from provenance rather than recomputed, because it is
        # a GENERATE-TIME fact. Recomputing from today's assessments would
        # render a present-tense claim beside entries drafted earlier: a
        # register generated against version 1 and read after version 2 was
        # approved would publish version 2's scored share as the reason
        # version 1's links are sparse. That is a certificate over an adjacent
        # proposition, which this repo treats as worse than no certificate.
        #
        # `_recorded` is derived from the KEY's presence, not from the list
        # being non-empty. An assessment that scored everything records
        # `{"csf": {"scored": 106, "total": 106}}`, and a register predating
        # this records no key at all -- if emptiness were the test those two
        # would be one state, which is the trap `excluded_inputs_recorded`
        # exists for.
        **_link_scope_fields(stored),
        id=register.id,
        client_id=register.client_id,
        version=register.version,
        generated_by=register.generated_by,
        finalized_at=register.finalized_at,
        created_at=register.created_at,
        xlsx_artifact_id=register.xlsx_artifact_id,
        pdf_artifact_id=register.pdf_artifact_id,
        docx_artifact_id=register.docx_artifact_id,
        xlsx_filename=_fn(register.xlsx_artifact_id),
        pdf_filename=_fn(register.pdf_artifact_id),
        docx_filename=_fn(register.docx_artifact_id),
        entries=[RiskEntryResponse.model_validate(e, from_attributes=True) for e in entries],
        tier_counts=tier_counts(tiers),
        axis_counts=axis_counts(axes),
        action_counts=action_counts(actions),
        batches_total=batches_total,
        batches_failed=batches_failed,
    )
