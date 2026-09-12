"""Risk Register routes (Work Order E).

A derived, admin-only, point-in-time deliverable. Admin-only and cross-tenant:
the client id is named in the path (like /admin/services/{id}); no X-Client-Id.

  GET  /risk/clients/{cid}/gate
  POST /risk/clients/{cid}/register/generate
  GET  /risk/clients/{cid}/register/latest
"""

from __future__ import annotations

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
    discarded: dict[str, int] = {}
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

    findings, valid_techniques, valid_controls = _gather_findings(db, cid)
    client_org = None if client.legal_name == "(pending intake)" else client.legal_name
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
    # The invariant this buys, and it is asserted rather than described:
    #     entries_received == entries_written + sum(discarded_entries.values())
    # Two sides that can only agree if every entry is accounted for.
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
                LINK_FIELDS, (techs_dropped, controls_dropped, source_dropped), strict=True
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

    # Counted from the flushed rows, not from the loop. A tally incremented
    # beside each `db.add` counts INTENTIONS: it is right until something
    # between the add and the flush drops one, which is exactly the case an
    # audit row exists to survive. Reading the table back is a check whose two
    # sides can only agree if the rows are there.
    db.flush()
    entries_written = db.execute(
        select(func.count()).select_from(RiskEntry).where(RiskEntry.register_id == register.id)
    ).scalar_one()

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
            "entries_total": entries_total,
            "entries_without_tier": entries_without_tier,
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
            "discarded_entries": discarded_entries,
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
    if _prov is None:
        if reg.finalized_at is None:
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
        entries_total=len(entries),
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
