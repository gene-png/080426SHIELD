"""Seed the demo database with one of each service + a released deliverable.

After running this you can sign in as:
  admin@kentro.example / DemoPass!2026
  client@atlas.example / DemoPass!2026

…and immediately see populated workspaces + the global /deliverables list.

Usage (from apps/api):
  /tmp/shield-api-venv/bin/python -m scripts.seed_demo

The script is idempotent — if it sees the admin user already, it does nothing.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from hashlib import sha256
from pathlib import Path

# Make sure app imports work when invoked from anywhere.
APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))


def _ensure_db_url() -> None:
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = f"sqlite:///{APP_ROOT / 'demo.db'}"


_ensure_db_url()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.attack.analytics import compute as compute_attack  # noqa: E402
from app.attack.catalog import TECHNIQUES, parent_techniques  # noqa: E402
from app.attack.coverage import CoverageStatus  # noqa: E402
from app.attack.exporters import (  # noqa: E402
    build_context as build_attack_context,
)
from app.attack.exporters import (  # noqa: E402
    render_pdf as render_attack_pdf,
)
from app.attack.exporters import (  # noqa: E402
    render_xlsx as render_attack_xlsx,
)
from app.audit import audit  # noqa: E402
from app.csf.catalog import SUBCATEGORIES as CSF_SUBS  # noqa: E402
from app.csf.exporters import build_context as build_csf_context  # noqa: E402
from app.csf.exporters import render_pdf as render_csf_pdf  # noqa: E402
from app.csf.exporters import render_xlsx as render_csf_xlsx  # noqa: E402
from app.csf.gap import analyze as analyze_csf_gap  # noqa: E402
from app.csf.scoring import compute as compute_csf  # noqa: E402
from app.docx_export import DOCX_MIME  # noqa: E402
from app.models import (  # noqa: E402  -- triggers metadata registration
    Artifact,
    ArtifactOrigin,
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
    Client,
    ClientDomain,
    CsfAnswer,
    CsfAssessment,
    CsfAssessmentStatus,
    Deliverable,
    RiskEntry,
    RiskRegister,
    Service,
    ServiceKind,
    ServiceStatus,
    User,
    UserRole,
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)
from app.models._common import utcnow  # noqa: E402
from app.models.capability import CapabilityDisposition  # noqa: E402
from app.risk import exporters as risk_exporters  # noqa: E402
from app.risk.engine import (  # noqa: E402
    Impact,
    Likelihood,
    RecommendedAction,
    RiskAxis,
    tier_for,
)
from app.security.email_domains import domain_of  # noqa: E402
from app.security.password import hash_password  # noqa: E402
from app.storage import StorageBackend, get_storage  # noqa: E402
from app.tech_debt.exporters import (  # noqa: E402
    build_context as build_td_context,
)
from app.tech_debt.exporters import (  # noqa: E402
    render_pdf as render_td_pdf,
)
from app.tech_debt.exporters import (  # noqa: E402
    render_xlsx as render_td_xlsx,
)
from app.tech_debt.filename import (  # noqa: E402
    SERVICE_SLUG_ATTACK,
    SERVICE_SLUG_NIST_CSF,
    SERVICE_SLUG_RISK_REGISTER,
    SERVICE_SLUG_TECH_DEBT,
    SERVICE_SLUG_ZT_CISA,
    SERVICE_SLUG_ZT_DOD,
    deliverable_filename,
)
from app.zt.catalog import capabilities as zt_capabilities  # noqa: E402
from app.zt.exporters import build_context as build_zt_context  # noqa: E402
from app.zt.exporters import render_pdf as render_zt_pdf  # noqa: E402
from app.zt.exporters import render_xlsx as render_zt_xlsx  # noqa: E402
from app.zt.maturity import ZtFrameworkCode  # noqa: E402
from app.zt.scoring import analyze_gaps as analyze_zt_gap  # noqa: E402
from app.zt.scoring import compute as compute_zt  # noqa: E402

ADMIN_EMAIL = "admin@kentro.example"
CLIENT_EMAIL = "client@atlas.example"
PASSWORD = "DemoPass!2026"
COMPANY = "Atlas Defense Solutions"


def _upgrade_head() -> None:
    cfg = Config(str(APP_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")


def _engine():
    url = os.environ["DATABASE_URL"]
    return create_engine(url, future=True)


def _bootstrap_org(db: Session) -> tuple[User, User, Client]:
    """Create admin + client users + the singleton Client row."""
    admin = db.execute(select(User).where(User.email == ADMIN_EMAIL)).scalar_one_or_none()
    if admin is not None:
        client_user = db.execute(select(User).where(User.email == CLIENT_EMAIL)).scalar_one()
        client_org = db.execute(select(Client).limit(1)).scalar_one()
        return admin, client_user, client_org

    org = Client(
        legal_name=COMPANY,
        dba_name="Atlas",
        industry="Defense",
        size_band="500-1000",
        country="US",
        intake_completed_at=utcnow(),
    )
    db.add(org)
    db.flush()

    admin = User(
        email=ADMIN_EMAIL,
        password_hash=hash_password(PASSWORD),
        role=UserRole.ADMIN,
        display_name="Demo Admin",
        title="Senior Consultant",
        timezone="UTC",
        last_login_at=utcnow(),
        client_id=org.id,
    )
    db.add(admin)
    client_user = User(
        email=CLIENT_EMAIL,
        password_hash=hash_password(PASSWORD),
        role=UserRole.CLIENT,
        display_name="Atlas CISO",
        title="CISO",
        timezone="UTC",
        last_login_at=utcnow(),
        client_id=org.id,
    )
    db.add(client_user)
    db.flush()
    audit(
        db,
        action="user.created",
        target_type="user",
        target_id=admin.id,
        actor_user_id=admin.id,
        details={"role": "admin", "seed": True},
    )
    audit(
        db,
        action="user.created",
        target_type="user",
        target_id=client_user.id,
        actor_user_id=admin.id,
        details={"role": "client", "seed": True},
    )
    db.commit()
    return admin, client_user, org


def _ensure_client_domain(db: Session, org: Client, admin: User) -> None:
    """Approve the demo client's email domain (Work Order B1/B2).

    A fresh stack has no approved domains, so a user self-registering with an
    @atlas.example address hits the B1 "domain not approved" rejection instead
    of auto-joining Atlas. Seed the approved row here, mirroring the admin
    add-domain route's model usage.

    Idempotent: a running stack may already carry this row from a UI session,
    so we skip when it is present and never duplicate it (the table also
    enforces a unique constraint on `domain`). Running the seed twice is a no-op
    on the second pass.
    """
    domain = domain_of(CLIENT_EMAIL)
    existing = db.execute(
        select(ClientDomain).where(ClientDomain.domain == domain)
    ).scalar_one_or_none()
    if existing is not None:
        return
    db.add(ClientDomain(client_id=org.id, domain=domain, created_by=admin.id))
    db.flush()
    audit(
        db,
        action="client.domain.added",
        target_type="client",
        target_id=org.id,
        actor_user_id=admin.id,
        details={"domain": domain, "seed": True},
    )
    db.commit()


def _write_artifact(
    db: Session,
    storage: StorageBackend,
    *,
    user: User,
    filename: str,
    mime_type: str,
    data: bytes,
    stage: str,
) -> Artifact:
    key = f"deliverable/{user.id}/{uuid.uuid4()}/{filename}"
    storage.put(key, data, content_type=mime_type)
    art = Artifact(
        title=filename,
        client_id=user.client_id,
        file_storage_key=key,
        mime_type=mime_type,
        size_bytes=len(data),
        sha256=sha256(data).hexdigest(),
        origin=ArtifactOrigin.CONSULTANT_APPROVED,
        stage=stage,
        uploaded_by=user.id,
    )
    db.add(art)
    db.flush()
    return art


def _release(
    db: Session,
    storage: StorageBackend,
    *,
    user: User,
    service: Service,
    pdf_name: str,
    xlsx_name: str,
    pdf_bytes: bytes,
    xlsx_bytes: bytes,
    summary: str,
    stage: str,
) -> Deliverable:
    pdf_art = _write_artifact(
        db,
        storage,
        user=user,
        filename=pdf_name,
        mime_type="application/pdf",
        data=pdf_bytes,
        stage=stage,
    )
    xlsx_art = _write_artifact(
        db,
        storage,
        user=user,
        filename=xlsx_name,
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=xlsx_bytes,
        stage=stage,
    )
    now = utcnow()
    deliv = Deliverable(
        service_id=service.id,
        title=f"{service.title} v1",
        summary=summary,
        version=1,
        pdf_artifact_id=pdf_art.id,
        xlsx_artifact_id=xlsx_art.id,
        finalized_at=now,
        finalized_by=user.id,
        # Actually RELEASE to the client (D-025 / §12): the client list route and
        # the artifact-download gate both require released_at, so a finalize-only
        # deliverable stays invisible to client@atlas.example. The demo story
        # needs downloadable reports, so the seed releases as well as finalizes.
        released_at=now,
        released_by=user.id,
    )
    db.add(deliv)
    db.flush()
    audit(
        db,
        action=f"{stage}.finalized",
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={"service_id": str(service.id), "demo": True},
    )
    audit(
        db,
        action=f"{stage}.released",
        target_type="deliverable",
        target_id=deliv.id,
        actor_user_id=user.id,
        details={"service_id": str(service.id), "demo": True},
    )
    return deliv


# ---------------------------------------------------------------------------
# Tech Debt
# ---------------------------------------------------------------------------


# (name, vendor, category, function, annual_cost_usd, license_count, disposition,
#  disposition_rationale) — a believable Atlas Defense stack with real vendor
# overlap so the Tech Debt story reads as a genuine consolidation review.
_TD_ITEMS = [
    (
        "Wiz",
        "Wiz, Inc.",
        "CNAPP",
        "Cloud posture",
        350_000,
        200,
        "keep",
        "Primary CNAPP of record; broadest coverage across the AWS + Azure estate "
        "and already wired into the ticketing workflow.",
    ),
    (
        "Lacework",
        "Lacework",
        "CNAPP",
        "Cloud posture",
        120_000,
        60,
        "cut",
        "Redundant with Wiz; runtime signal is duplicative and the contract lapses "
        "in Q3 — retire at renewal for a clean $120k/yr saving.",
    ),
    (
        "Prisma Cloud",
        "Palo Alto Networks",
        "CNAPP",
        "Cloud posture",
        240_000,
        150,
        "consolidate",
        "Overlaps Wiz on posture; retain only the IaC-scanning module and fold the "
        "rest into the Wiz license at next true-up.",
    ),
    (
        "Splunk Enterprise",
        "Splunk",
        "SIEM",
        "Log analytics",
        480_000,
        None,
        "keep",
        "System of record for detections and the ATT&CK correlation rules; migration "
        "risk outweighs licence cost this cycle.",
    ),
    (
        "Sumo Logic",
        "Sumo Logic",
        "SIEM",
        "Log analytics",
        140_000,
        None,
        "cut",
        "Shadow SIEM stood up by one app team; forward its sources to Splunk and " "decommission.",
    ),
    (
        "CrowdStrike Falcon",
        "CrowdStrike",
        "EDR",
        "Endpoint detection",
        320_000,
        4500,
        "keep",
        "Strategic EDR; drives the highest-fidelity endpoint detections and threat "
        "hunting playbooks.",
    ),
    (
        "Defender for Endpoint",
        "Microsoft",
        "EDR",
        "Endpoint detection",
        90_000,
        4500,
        "consolidate",
        "Bundled with existing M365 E5 licensing; keep for Windows telemetry only and "
        "stop paying for the standalone add-on that overlaps Falcon.",
    ),
    (
        "Okta Workforce Identity",
        "Okta",
        "IAM",
        "Identity",
        210_000,
        4500,
        "keep",
        "Central IdP for SSO and the Zero Trust identity pillar; anchor for the MFA " "roll-out.",
    ),
    (
        "Duo",
        "Cisco",
        "IAM",
        "MFA",
        65_000,
        4500,
        "consolidate",
        "MFA duplicates Okta Verify; migrate remaining Duo enrolments to Okta and "
        "retire to remove a second push-fatigue attack surface.",
    ),
    (
        "Tenable.io",
        "Tenable",
        "Vuln Management",
        "Vulnerability scanning",
        175_000,
        None,
        "keep",
        "Authoritative vulnerability scanner feeding the remediation SLA dashboard.",
    ),
    (
        "Qualys VMDR",
        "Qualys",
        "Vuln Management",
        "Vulnerability scanning",
        160_000,
        None,
        "cut",
        "Second scanner producing conflicting CVSS data; consolidate on Tenable and "
        "cancel at renewal.",
    ),
    (
        "HashiCorp Vault",
        "HashiCorp",
        "Secrets",
        "Secrets management",
        95_000,
        None,
        "keep",
        "Sole enterprise secrets broker; no viable overlap — retain and expand "
        "dynamic-secrets adoption.",
    ),
]


def _seed_tech_debt(db: Session, storage: StorageBackend, admin: User, org: Client) -> Service:
    svc = Service(
        kind=ServiceKind.TECH_DEBT,
        status=ServiceStatus.RELEASED,
        title="Atlas Defense — Tech Debt Review",
        client_id=org.id,
        opened_by=admin.id,
        released_at=utcnow(),
    )
    db.add(svc)
    db.flush()

    cap_list = CapabilityList(
        service_id=svc.id,
        version=1,
        status=CapabilityListStatus.RELEASED,
        approved_at=utcnow(),
        approved_by=admin.id,
    )
    db.add(cap_list)
    db.flush()

    items: list[CapabilityItem] = []
    for name, vendor, cat, fn, cost, lic, disp, rationale in _TD_ITEMS:
        items.append(
            CapabilityItem(
                capability_list_id=cap_list.id,
                name=name,
                vendor=vendor,
                category=cat,
                function=fn,
                annual_cost_usd=cost,
                license_count=lic,
                confidence_pct=92,
                disposition=CapabilityDisposition(disp),
                disposition_rationale=rationale,
            )
        )
    db.add_all(items)
    db.flush()

    today = date.today()
    pdf_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_TECH_DEBT,
        extension="pdf",
        day=today,
    )
    xlsx_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_TECH_DEBT,
        extension="xlsx",
        day=today,
    )
    ctx = build_td_context(
        client_legal_name=org.legal_name,
        service_title=svc.title,
        cap_list=cap_list,
        items=items,
    )
    deliv = _release(
        db,
        storage,
        user=admin,
        service=svc,
        pdf_name=pdf_name,
        xlsx_name=xlsx_name,
        pdf_bytes=render_td_pdf(ctx),
        xlsx_bytes=render_td_xlsx(ctx),
        summary=(
            f"{len(items)} capabilities reviewed; "
            f"${ctx.estimated_savings:,.0f} estimated annual savings."
        ),
        stage="tech_debt.deliverable",
    )
    _ = deliv  # silence unused
    return svc


# ---------------------------------------------------------------------------
# CSF
# ---------------------------------------------------------------------------


def _csf_tier_for(index: int) -> int:
    """Deterministic but varied: cycles 1,2,3,4,3,2,2,3,3,3,4,..."""
    pattern = [1, 2, 3, 4, 3, 2, 2, 3, 3, 3, 4, 4, 2, 3, 3]
    return pattern[index % len(pattern)]


def _seed_csf(db: Session, storage: StorageBackend, admin: User, org: Client) -> Service:
    svc = Service(
        kind=ServiceKind.NIST_CSF,
        status=ServiceStatus.RELEASED,
        title="Atlas Defense — NIST CSF 2.0 Assessment",
        client_id=org.id,
        opened_by=admin.id,
        released_at=utcnow(),
    )
    db.add(svc)
    db.flush()

    assessment = CsfAssessment(
        service_id=svc.id,
        client_id=org.id,
        version=1,
        status=CsfAssessmentStatus.RELEASED,
        approved_at=utcnow(),
        approved_by=admin.id,
    )
    db.add(assessment)
    db.flush()

    answers: list[CsfAnswer] = []
    for idx, sc in enumerate(CSF_SUBS):
        ans = CsfAnswer(
            assessment_id=assessment.id,
            client_id=org.id,
            subcategory_code=sc.code,
            maturity_tier=_csf_tier_for(idx),
            notes=("Validated by ISSO walk-through." if idx % 7 == 0 else None),
            answered_by=admin.id,
            answered_at=utcnow(),
        )
        answers.append(ans)
    db.add_all(answers)
    db.flush()

    tier_map = {a.subcategory_code: a.maturity_tier for a in answers}
    notes_map = {a.subcategory_code: a.notes for a in answers}
    score = compute_csf(tier_map)
    gap = analyze_csf_gap(tier_map, notes=notes_map)

    today = date.today()
    pdf_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_NIST_CSF,
        extension="pdf",
        day=today,
    )
    xlsx_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_NIST_CSF,
        extension="xlsx",
        day=today,
    )
    ctx = build_csf_context(
        client_legal_name=org.legal_name,
        service_title=svc.title,
        assessment=assessment,
        answers=answers,
        score=score,
        gap=gap,
    )
    _release(
        db,
        storage,
        user=admin,
        service=svc,
        pdf_name=pdf_name,
        xlsx_name=xlsx_name,
        pdf_bytes=render_csf_pdf(ctx),
        xlsx_bytes=render_csf_xlsx(ctx),
        summary=(
            f"Overall maturity: {score.overall_maturity_label}. "
            f"{score.answered_subcategories}/{score.total_subcategories} scored; "
            f"{gap.total_gap_count} gaps at target T{gap.target_tier}."
        ),
        stage="csf.deliverable",
    )
    return svc


# ---------------------------------------------------------------------------
# Zero Trust (CISA + DoD)
# ---------------------------------------------------------------------------


def _zt_stage_for(index: int) -> int:
    pattern = [1, 2, 2, 3, 3, 3, 4, 2, 3, 1, 2, 3, 3, 3, 4]
    return pattern[index % len(pattern)]


def _seed_zt(
    db: Session,
    storage: StorageBackend,
    admin: User,
    org: Client,
    *,
    kind: ServiceKind,
    framework: ZtFramework,
    catalog_fw: ZtFrameworkCode,
    service_slug: str,
    title: str,
) -> Service:
    svc = Service(
        kind=kind,
        status=ServiceStatus.RELEASED,
        title=title,
        client_id=org.id,
        opened_by=admin.id,
        released_at=utcnow(),
    )
    db.add(svc)
    db.flush()

    assessment = ZtAssessment(
        service_id=svc.id,
        client_id=org.id,
        framework=framework,
        version=1,
        status=ZtAssessmentStatus.RELEASED,
        approved_at=utcnow(),
        approved_by=admin.id,
    )
    db.add(assessment)
    db.flush()

    answers: list[ZtAnswer] = []
    for idx, cap in enumerate(zt_capabilities(catalog_fw)):
        answers.append(
            ZtAnswer(
                assessment_id=assessment.id,
                client_id=org.id,
                capability_code=cap.code,
                maturity_stage=_zt_stage_for(idx),
                notes=(
                    "Validated via control inheritance from agency MAS." if idx % 9 == 0 else None
                ),
                answered_by=admin.id,
                answered_at=utcnow(),
            )
        )
    db.add_all(answers)
    db.flush()

    stage_map = {a.capability_code: a.maturity_stage for a in answers}
    notes_map = {a.capability_code: a.notes for a in answers}
    score = compute_zt(catalog_fw, stage_map)
    gap = analyze_zt_gap(catalog_fw, stage_map, notes=notes_map)

    today = date.today()
    pdf_name = deliverable_filename(
        company=org.legal_name,
        service_slug=service_slug,
        extension="pdf",
        day=today,
    )
    xlsx_name = deliverable_filename(
        company=org.legal_name,
        service_slug=service_slug,
        extension="xlsx",
        day=today,
    )
    ctx = build_zt_context(
        client_legal_name=org.legal_name,
        service_title=svc.title,
        framework=catalog_fw,
        assessment=assessment,
        answers=answers,
        score=score,
        gap=gap,
    )
    _release(
        db,
        storage,
        user=admin,
        service=svc,
        pdf_name=pdf_name,
        xlsx_name=xlsx_name,
        pdf_bytes=render_zt_pdf(ctx),
        xlsx_bytes=render_zt_xlsx(ctx),
        summary=(
            f"Overall stage: {score.overall_stage_label}. "
            f"{score.answered_capabilities}/{score.total_capabilities} scored; "
            f"{gap.total_gap_count} gaps at target S{gap.target_stage}."
        ),
        stage="zt.deliverable",
    )
    return svc


# ---------------------------------------------------------------------------
# ATT&CK Coverage
# ---------------------------------------------------------------------------


def _attack_status_for(index: int, is_sub: bool) -> str | None:
    """Mix: 50% covered, 20% partial, 15% gap, 10% N/A, 5% unscored."""
    bucket = index % 20
    if bucket < 10:
        return CoverageStatus.COVERED.value
    if bucket < 14:
        return CoverageStatus.PARTIAL.value
    if bucket < 17:
        return CoverageStatus.GAP.value
    if bucket < 19:
        return CoverageStatus.NOT_APPLICABLE.value
    return None


def _seed_attack(db: Session, storage: StorageBackend, admin: User, org: Client) -> Service:
    svc = Service(
        kind=ServiceKind.ATTACK_COVERAGE,
        status=ServiceStatus.RELEASED,
        title="Atlas Defense — MITRE ATT&CK Coverage",
        client_id=org.id,
        opened_by=admin.id,
        released_at=utcnow(),
    )
    db.add(svc)
    db.flush()

    assessment = AttackAssessment(
        service_id=svc.id,
        client_id=org.id,
        version=1,
        status=AttackAssessmentStatus.RELEASED,
        approved_at=utcnow(),
        approved_by=admin.id,
    )
    db.add(assessment)
    db.flush()

    coverage_rows: list[AttackCoverage] = []
    parent_ids = {t.id for t in parent_techniques()}
    for idx, tech in enumerate(TECHNIQUES):
        status_value = _attack_status_for(idx, tech.id not in parent_ids)
        coverage_rows.append(
            AttackCoverage(
                assessment_id=assessment.id,
                client_id=org.id,
                technique_code=tech.id,
                status=status_value,
                notes=(
                    "Detection: EDR + SIEM correlation rule."
                    if status_value == "covered" and idx % 25 == 0
                    else None
                ),
                answered_by=admin.id,
                answered_at=utcnow(),
            )
        )
    db.add_all(coverage_rows)
    db.flush()

    coverage_map = {r.technique_code: r.status for r in coverage_rows}
    rollup = compute_attack(coverage_map)

    today = date.today()
    pdf_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="pdf",
        day=today,
    )
    xlsx_name = deliverable_filename(
        company=org.legal_name,
        service_slug=SERVICE_SLUG_ATTACK,
        extension="xlsx",
        day=today,
    )
    ctx = build_attack_context(
        client_legal_name=org.legal_name,
        service_title=svc.title,
        assessment=assessment,
        coverage=coverage_rows,
        rollup=rollup,
    )
    _release(
        db,
        storage,
        user=admin,
        service=svc,
        pdf_name=pdf_name,
        xlsx_name=xlsx_name,
        pdf_bytes=render_attack_pdf(ctx),
        xlsx_bytes=render_attack_xlsx(ctx),
        summary=(
            f"Coverage: {rollup.coverage_pct}%. "
            f"{rollup.covered} covered, {rollup.partial} partial, "
            f"{rollup.gap} gaps, {rollup.not_applicable} N/A across "
            f"{rollup.scored_count} scored techniques."
        ),
        stage="attack.deliverable",
    )
    return svc


# ---------------------------------------------------------------------------
# Risk Register (Work Order E)
#
# A deterministic, believable synthesis of the four services above. The live
# product generates entries through the redacting LLM egress and then derives
# every tier in code; the seed skips the egress (it must run offline/fixture)
# and writes a hand-authored register whose tiers are STILL derived by the same
# `tier_for` engine — never hard-coded — so the demo mirrors the real
# "AI suggests, code computes" contract. Technique + control links reference
# real codes present in the seeded ATT&CK / CSF assessments so traceability is
# genuine.
# ---------------------------------------------------------------------------


# (title, description, axis, source, source_id, likelihood, impact,
#  linked_techniques, linked_controls, compensating_controls, residual_risk,
#  recommended_action, rationale)
_RISK_ENTRIES = [
    (
        "Active exploitation of an unpatched internet-facing appliance",
        "The perimeter VPN/edge appliance is running firmware with a known, "
        "actively-exploited RCE. A successful exploit yields an unauthenticated "
        "foothold into the DMZ.",
        RiskAxis.PREVENTION,
        "coverage_finding",
        "T1190",
        Likelihood.VERY_HIGH,
        Impact.CATASTROPHIC,
        ["T1190", "T1210"],
        ["ID.AM-08"],
        "WAF virtual-patching rule deployed; appliance reachable only from "
        "allow-listed ranges pending firmware upgrade.",
        "High until the vendor firmware upgrade lands in the next maintenance " "window.",
        RecommendedAction.REMEDIATE,
        "Public exploit code and in-the-wild activity make compromise near-certain "
        "absent immediate patching.",
    ),
    (
        "Ransomware impact on production file services",
        "ATT&CK coverage shows partial detection for data-encryption behaviour on "
        "the file-server tier; a ransomware event could halt operations.",
        RiskAxis.RESPONSE,
        "coverage_finding",
        "T1486",
        Likelihood.MEDIUM,
        Impact.CATASTROPHIC,
        ["T1486"],
        ["RS.MA-01", "DE.CM-01"],
        "Immutable off-site backups tested quarterly; EDR ransomware canaries "
        "enabled on the file-server fleet.",
        "Recovery-time objective still exceeds the business tolerance for the " "core ERP volume.",
        RecommendedAction.MITIGATE,
        "Impact is catastrophic; tested backups reduce likelihood but not the "
        "operational disruption window.",
    ),
    (
        "Phishing-driven credential compromise",
        "Spearphishing remains the most common initial-access vector; harvested "
        "credentials feed valid-account abuse across cloud consoles.",
        RiskAxis.PREVENTION,
        "coverage_finding",
        "T1566",
        Likelihood.HIGH,
        Impact.MAJOR,
        ["T1566", "T1078"],
        ["PR.AA-02"],
        "Phishing-resistant MFA on the IdP; monthly simulated-phishing programme "
        "with mandatory remediation training.",
        "Residual exposure on legacy service accounts not yet behind SSO.",
        RecommendedAction.MITIGATE,
        "High volume of attempts against a large workforce keeps likelihood high "
        "despite strong controls.",
    ),
    (
        "Valid-account lateral movement due to partial MFA coverage",
        "Duplicate MFA tooling (Okta + Duo) left a subset of enrolments outside "
        "phishing-resistant factors, enabling valid-account reuse for lateral "
        "movement.",
        RiskAxis.PREVENTION,
        "questionnaire_response",
        "PR.AA-01",
        Likelihood.MEDIUM,
        Impact.MAJOR,
        ["T1078", "T1021"],
        ["PR.AA-01"],
        "Conditional-access policies flag impossible-travel; privileged accounts "
        "already on hardware keys.",
        "Standard-user population on push-based MFA remains susceptible to "
        "fatigue attacks until Duo retirement completes.",
        RecommendedAction.REMEDIATE,
        "Consolidating on Okta Verify closes the gap; tracked in the Tech Debt "
        "consolidation plan.",
    ),
    (
        "Detection-engineering gaps and alert fatigue",
        "Overlapping SIEM tooling produced duplicate, low-fidelity alerts; some "
        "execution techniques lack tuned detections.",
        RiskAxis.DETECTION,
        "questionnaire_response",
        "DE.AE-02",
        Likelihood.HIGH,
        Impact.MODERATE,
        ["T1059"],
        ["DE.AE-02", "DE.CM-01"],
        "Sumo Logic sources being folded into Splunk; detection backlog "
        "prioritised against the ATT&CK gap list.",
        "Mean-time-to-detect for scripting-based execution still above target.",
        RecommendedAction.MITIGATE,
        "Consolidating on Splunk plus detection tuning lowers noise and closes "
        "the highest-value coverage gaps.",
    ),
    (
        "Incomplete asset inventory for cloud workloads",
        "Ephemeral cloud workloads are not consistently captured in the CMDB, "
        "weakening exposure management.",
        RiskAxis.PREVENTION,
        "questionnaire_response",
        "ID.AM-01",
        Likelihood.MEDIUM,
        Impact.MINOR,
        [],
        ["ID.AM-01"],
        "Wiz agentless discovery reconciles daily against the CMDB; drift alerts "
        "route to the platform team.",
        "Short-lived workloads may still evade a daily reconciliation window.",
        RecommendedAction.ACCEPT,
        "Compensating discovery keeps residual impact minor; formal acceptance "
        "with quarterly review.",
    ),
    (
        "Immature incident-response runbooks",
        "IR runbooks for cloud and ransomware scenarios are draft-only and have "
        "not been exercised end-to-end.",
        RiskAxis.RESPONSE,
        "questionnaire_response",
        "RS.MA-02",
        Likelihood.MEDIUM,
        Impact.MAJOR,
        [],
        ["RS.MA-02", "RS.MA-03"],
        "Retainer with an external DFIR provider; on-call rotation established.",
        "Unrehearsed runbooks risk slow, inconsistent response until the first "
        "tabletop completes.",
        RecommendedAction.MITIGATE,
        "Scheduled tabletop exercises and runbook sign-off will move this to Low.",
    ),
]


def _seed_risk_register(
    db: Session, storage: StorageBackend, admin: User, org: Client
) -> RiskRegister:
    register = RiskRegister(
        client_id=org.id,
        version=1,
        generated_by=admin.id,
    )
    db.add(register)
    db.flush()

    entries: list[RiskEntry] = []
    for (
        title,
        description,
        axis,
        source,
        source_id,
        likelihood,
        impact,
        techniques,
        controls,
        compensating,
        residual,
        action,
        rationale,
    ) in _RISK_ENTRIES:
        # Tier is ALWAYS code-derived (never authored) — same engine the route uses.
        tier = tier_for(likelihood, impact).value
        entries.append(
            RiskEntry(
                register_id=register.id,
                client_id=org.id,
                title=title,
                description=description,
                axis=axis.value,
                source=source,
                source_id=source_id,
                linked_techniques=techniques,
                linked_controls=controls,
                likelihood=likelihood.value,
                impact=impact.value,
                tier=tier,
                compensating_controls=compensating,
                residual_risk=residual,
                recommended_action=action.value,
                rationale=rationale,
                origin="ai_generated",
                trust="admin_assisted",
            )
        )
    db.add_all(entries)
    db.flush()

    # Export the register to XLSX/PDF/Word so the admin demo shows downloadable
    # artifacts, mirroring the /register/export route (which sets finalized_at).
    ctx = risk_exporters.build_context(
        client_legal_name=org.legal_name,
        version=register.version,
        entries=entries,
    )
    today = date.today()

    def _rr_name(extension: str) -> str:
        return deliverable_filename(
            company=org.legal_name,
            service_slug=SERVICE_SLUG_RISK_REGISTER,
            extension=extension,
            day=today,
            version=register.version,
        )

    xlsx_art = _write_artifact(
        db,
        storage,
        user=admin,
        filename=_rr_name("xlsx"),
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=risk_exporters.render_xlsx(ctx),
        stage="risk_register.export",
    )
    pdf_art = _write_artifact(
        db,
        storage,
        user=admin,
        filename=_rr_name("pdf"),
        mime_type="application/pdf",
        data=risk_exporters.render_pdf(ctx),
        stage="risk_register.export",
    )
    docx_art = _write_artifact(
        db,
        storage,
        user=admin,
        filename=_rr_name("docx"),
        mime_type=DOCX_MIME,
        data=risk_exporters.render_docx(ctx),
        stage="risk_register.export",
    )
    register.xlsx_artifact_id = xlsx_art.id
    register.pdf_artifact_id = pdf_art.id
    register.docx_artifact_id = docx_art.id
    register.finalized_at = utcnow()
    db.flush()

    audit(
        db,
        action="risk_register.generated",
        target_type="risk_register",
        target_id=register.id,
        actor_user_id=admin.id,
        details={"version": register.version, "entries": len(entries), "seed": True},
    )
    audit(
        db,
        action="risk_register.exported",
        target_type="risk_register",
        target_id=register.id,
        actor_user_id=admin.id,
        details={"version": register.version, "seed": True},
    )
    return register


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print(f"DATABASE_URL = {os.environ['DATABASE_URL']}")
    print("Applying migrations...")
    _upgrade_head()

    # Write artifacts through the SAME backend the API reads from (get_storage
    # picks MinIO/S3 vs local from Settings.s3_endpoint_url). Previously the seed
    # wrote to a local-FS stub the S3-backed API couldn't read -> seeded
    # deliverable downloads 410'd (Sprint 6 T2).
    storage = get_storage()

    engine = _engine()
    with Session(engine, future=True) as db:
        admin, client_user, org = _bootstrap_org(db)
        _ensure_client_domain(db, org, admin)
        if db.execute(select(Service).limit(1)).scalar_one_or_none() is not None:
            print("Services already present; skipping seeding.")
            print("  admin: ", ADMIN_EMAIL)
            print("  client:", CLIENT_EMAIL)
            print("  password:", PASSWORD)
            return

        print("Seeding Tech Debt service...")
        td = _seed_tech_debt(db, storage, admin, org)
        print(f"  -> {td.id}")

        print("Seeding CSF service...")
        csf = _seed_csf(db, storage, admin, org)
        print(f"  -> {csf.id}")

        print("Seeding Zero Trust (CISA) service...")
        zt_cisa = _seed_zt(
            db,
            storage,
            admin,
            org,
            kind=ServiceKind.ZERO_TRUST_CISA,
            framework=ZtFramework.CISA_ZTMM_2_0,
            catalog_fw=ZtFrameworkCode.CISA_ZTMM_2_0,
            service_slug=SERVICE_SLUG_ZT_CISA,
            title="Atlas Defense — Zero Trust (CISA ZTMM 2.0)",
        )
        print(f"  -> {zt_cisa.id}")

        print("Seeding Zero Trust (DoD) service...")
        zt_dod = _seed_zt(
            db,
            storage,
            admin,
            org,
            kind=ServiceKind.ZERO_TRUST_DOD,
            framework=ZtFramework.DOD_ZTRA,
            catalog_fw=ZtFrameworkCode.DOD_ZTRA,
            service_slug=SERVICE_SLUG_ZT_DOD,
            title="Atlas Defense — Zero Trust (DoD ZTRA)",
        )
        print(f"  -> {zt_dod.id}")

        print("Seeding MITRE ATT&CK Coverage service...")
        attack = _seed_attack(db, storage, admin, org)
        print(f"  -> {attack.id}")

        print("Seeding synthesized Risk Register...")
        register = _seed_risk_register(db, storage, admin, org)
        print(f"  -> {register.id} (v{register.version}, {len(_RISK_ENTRIES)} entries)")

        db.commit()

    print()
    print("Demo seed complete: 4 services + a synthesized Risk Register, all released.")
    print("Sign in:")
    print(f"  admin: {ADMIN_EMAIL} / {PASSWORD}")
    print(f"  client: {CLIENT_EMAIL} / {PASSWORD}")


if __name__ == "__main__":
    main()
