"""Risk Register routes (Work Order E).

A derived, admin-only, point-in-time deliverable. Admin-only and cross-tenant:
the client id is named in the path (like /admin/services/{id}); no X-Client-Id.

  GET  /risk/clients/{cid}/gate
  POST /risk/clients/{cid}/register/generate
  GET  /risk/clients/{cid}/register/latest
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.engine import get_job, run_job
from app.ai.failures import ai_call_boundary
from app.ai.llm import LLMClient
from app.attack.catalog import all_codes as attack_all_codes
from app.audit import audit
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
from app.routes.artifacts import _storage_dep
from app.schemas.risk import (
    RiskEntryResponse,
    RiskGateStatus,
    RiskRegisterResponse,
)
from app.security.rate_limit import RateLimiter, get_rate_limiter
from app.storage import StorageBackend
from app.tech_debt.filename import SERVICE_SLUG_RISK_REGISTER, deliverable_filename

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
    finalized_attack = _finalized_for_synthesis(db, AttackAssessment, client_id) is not None
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


def _gather_findings(db: Session, client_id: uuid.UUID) -> tuple[list[dict], set[str], set[str]]:
    """Findings (one per gap) + the valid technique/control link universes.

    valid_techniques = every technique in the client's ATT&CK assessment.
    valid_controls   = CSF subcategory codes + ZT capability codes present.
    """
    findings: list[dict] = []
    valid_techniques: set[str] = set()
    valid_controls: set[str] = set()

    attack = _finalized_for_synthesis(db, AttackAssessment, client_id)
    if attack is not None:
        rows = (
            db.execute(select(AttackCoverage).where(AttackCoverage.assessment_id == attack.id))
            .scalars()
            .all()
        )
        valid_techniques = {r.technique_code for r in rows} or set(attack_all_codes())
        for r in rows:
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
        for r in (
            db.execute(select(CsfAnswer).where(CsfAnswer.assessment_id == csf.id)).scalars().all()
        ):
            valid_controls.add(r.subcategory_code)
            if r.maturity_tier is not None and r.maturity_tier < 3:
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
        for r in (
            db.execute(select(ZtAnswer).where(ZtAnswer.assessment_id == zt.id)).scalars().all()
        ):
            valid_controls.add(r.capability_code)
            tgt = r.target_stage if r.target_stage is not None else 3
            if r.maturity_stage is not None and r.maturity_stage < tgt:
                findings.append(
                    {
                        "source": "questionnaire_response",
                        "source_id": r.capability_code,
                        "kind": "zt",
                        "label": f"ZT {r.capability_code}: stage {r.maturity_stage}",
                    }
                )

    return findings, valid_techniques, valid_controls


def _enum_or_none(enum_cls, value):
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        return None


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
) -> tuple[list[dict], int, int]:
    """Run risk_synthesize as concurrent batches. Returns (entries, total, failed).

    Each batch is a real `run_job` call and therefore writes its own `llm_calls`
    row — N rows per run. That is the honest accounting: N separately-billable
    provider calls were made.

    The allow-lists go to EVERY batch. `valid_techniques` / `valid_controls` are
    what stop the model citing a technique or control the client's assessments
    never contained, so a batch that did not receive them would be unguarded.
    They cost input tokens, which is the cheap side of this trade.

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
    failed = 0
    first_error: Exception | None = None

    with ThreadPoolExecutor(max_workers=_RISK_MAX_WORKERS) as pool:
        futures = [pool.submit(_one, b) for b in batches]
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
            entries.extend(e for e in (data.get("entries") or []) if isinstance(e, dict))

    _log.info(
        "risk_synthesize_batched",
        client_id=str(client_id),
        findings=len(findings),
        batches_total=len(batches),
        batches_failed=failed,
        entries=len(entries),
    )

    if failed == len(batches) and first_error is not None:
        # Nothing usable came back. Re-raise inside the boundary so the caller
        # gets the same typed 502 + charged_likely it always did.
        with ai_call_boundary(db, llm, purpose="risk_synthesize"):
            raise first_error

    return entries, len(batches), failed


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

    findings, valid_techniques, valid_controls = _gather_findings(db, cid)
    client_org = None if client.legal_name == "(pending intake)" else client.legal_name
    # Batched: one request cannot express this job (see _RISK_BATCH_SIZE). A
    # total failure still raises typed, through ai_call_boundary.
    entries_draft, batches_total, batches_failed = _run_risk_synthesize_batched(
        db,
        llm,
        findings,
        valid_techniques=sorted(valid_techniques),
        valid_controls=sorted(valid_controls),
        requested_by=admin.id,
        client_id=cid,
        client_org_name=client_org,
    )
    data = {"entries": entries_draft}

    # New version; supersede the prior current one.
    prior = _latest_register(db, cid)
    next_version = (prior.version + 1) if prior is not None else 1
    register = RiskRegister(client_id=cid, version=next_version, generated_by=admin.id)
    db.add(register)
    db.flush()
    if prior is not None:
        prior.superseded_by = register.id

    for raw in data.get("entries", []):
        if not isinstance(raw, dict) or not raw.get("title"):
            continue
        lk = _enum_or_none(Likelihood, raw.get("likelihood"))
        im = _enum_or_none(Impact, raw.get("impact"))
        # Tier is ALWAYS code-derived, never AI-set.
        tier = tier_for(lk, im).value if (lk is not None and im is not None) else None
        techs = [t for t in (raw.get("linked_techniques") or []) if t in valid_techniques]
        controls = [c for c in (raw.get("linked_controls") or []) if c in valid_controls]
        axis = _enum_or_none(RiskAxis, raw.get("axis"))
        action = _enum_or_none(RecommendedAction, raw.get("recommended_action"))
        db.add(
            RiskEntry(
                register_id=register.id,
                client_id=cid,
                title=str(raw["title"])[:512],
                description=raw.get("description"),
                axis=axis.value if axis else None,
                source=raw.get("source"),
                source_id=raw.get("source_id"),
                linked_techniques=techs,
                linked_controls=controls,
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

    audit(
        db,
        action="risk_register.generated",
        target_type="risk_register",
        target_id=register.id,
        actor_user_id=admin.id,
        details={
            "version": next_version,
            "findings": len(findings),
            "batches_total": batches_total,
            "batches_failed": batches_failed,
        },
    )
    db.commit()
    # `g.not_finalized` is the full present-but-unapproved set; the refusal
    # above already cleared the ones that block. Whatever remains contributed
    # nothing to this register, and the register says so.
    return _serialize(
        db,
        register,
        excluded_inputs=g.not_finalized,
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
    reg = _latest_register(db, cid)
    if reg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generate a Risk Register before exporting.",
        )
    entries = (
        db.execute(
            select(RiskEntry).where(RiskEntry.register_id == reg.id).order_by(RiskEntry.created_at)
        )
        .scalars()
        .all()
    )
    org = None if client.legal_name == "(pending intake)" else client.legal_name
    ctx = risk_exporters.build_context(client_legal_name=org, version=reg.version, entries=entries)
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


def _serialize(
    db: Session,
    register: RiskRegister,
    *,
    excluded_inputs: list[str] | None = None,
    batches_total: int = 0,
    batches_failed: int = 0,
) -> RiskRegisterResponse:
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

    return RiskRegisterResponse(
        excluded_inputs=excluded_inputs or [],
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
