"""Zero Trust catalogs: CISA ZTMM 2.0 + DoD ZT Reference Architecture.

Both frameworks share the same shape (Framework -> Pillar -> Capability),
which lets a single scoring + gap engine handle both. Capability codes
embed the framework prefix to keep them globally unique:

  CISA codes: "CISA.<PILLAR>.<NN>"   e.g. "CISA.ID.01"
  DoD codes:  "DOD.<PILLAR>.<NN>"    e.g. "DOD.USR.01"

Counts (Phase 5 v1):
  CISA ZTMM 2.0:  8 pillars / 37 capabilities (complete)
  DoD ZTRA:       7 pillars / 50 capabilities (v1 baseline; full DoD
                  catalog of 152 activities lands as a future patch)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.zt.maturity import ZtFrameworkCode


@dataclass(frozen=True)
class Pillar:
    framework: ZtFrameworkCode
    code: str  # 2-3 letter pillar code, e.g. "ID" (CISA Identity)
    name: str
    purpose: str


@dataclass(frozen=True)
class Capability:
    framework: ZtFrameworkCode
    pillar_code: str
    code: str  # full code, e.g. "CISA.ID.01"
    name: str
    outcome: str


# ---------------------------------------------------------------------------
# CISA ZTMM 2.0 pillars
# ---------------------------------------------------------------------------

CISA_PILLARS: tuple[Pillar, ...] = (
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "ID",
        "Identity",
        "Verify users + non-person entities with phishing-resistant credentials and risk-adaptive access decisions.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "DV",
        "Devices",
        "Maintain comprehensive device inventory, enforce compliance posture, and use device signals in access decisions.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "NW",
        "Networks",
        "Segment networks, encrypt traffic, and monitor for anomalous flows.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "AW",
        "Applications & Workloads",
        "Secure applications by design; protect APIs and microservices throughout the lifecycle.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "DT",
        "Data",
        "Inventory, classify, encrypt, and govern data with rights-based access enforcement.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "VA",
        "Visibility & Analytics",
        "Collect telemetry across pillars and feed analytics into automated risk scoring.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "AO",
        "Automation & Orchestration",
        "Automate policy enforcement, incident response, and continuous compliance verification.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "GV",
        "Governance",
        "Govern ZT strategy, policies, and supply-chain risk; align with mission objectives.",
    ),
)


def _cisa(pillar: str, num: int, name: str, outcome: str) -> Capability:
    return Capability(
        framework=ZtFrameworkCode.CISA_ZTMM_2_0,
        pillar_code=pillar,
        code=f"CISA.{pillar}.{num:02d}",
        name=name,
        outcome=outcome,
    )


CISA_CAPABILITIES: tuple[Capability, ...] = (
    # Identity (5)
    _cisa(
        "ID",
        1,
        "Authentication",
        "Authenticate users with phishing-resistant MFA across all access points.",
    ),
    _cisa(
        "ID",
        2,
        "Identity Stores",
        "Consolidate identity stores; federate non-person entity identities.",
    ),
    _cisa(
        "ID",
        3,
        "Risk Assessments",
        "Apply continuous, risk-based authentication decisions using behavioral signals.",
    ),
    _cisa(
        "ID",
        4,
        "Access Management",
        "Enforce just-in-time, just-enough access with continuous validation.",
    ),
    _cisa(
        "ID",
        5,
        "Visibility for Identity",
        "Stream identity signals (login, role change, anomaly) into the analytics pillar.",
    ),
    # Devices (5)
    _cisa(
        "DV",
        1,
        "Policy Enforcement & Compliance",
        "Devices enforce compliance baselines (patch level, EDR, FDE) before access.",
    ),
    _cisa(
        "DV",
        2,
        "Asset & Supply Chain Risk",
        "Inventory hardware + firmware provenance and surface supply-chain risk.",
    ),
    _cisa(
        "DV",
        3,
        "Resource Access",
        "Device posture is evaluated for every resource request, not just at login.",
    ),
    _cisa(
        "DV",
        4,
        "Device Threat Protection",
        "Endpoint detection + response with automated containment of compromised devices.",
    ),
    _cisa(
        "DV", 5, "Visibility for Devices", "Continuous device telemetry feeds the analytics pillar."
    ),
    # Networks (4)
    _cisa(
        "NW",
        1,
        "Network Segmentation",
        "Implement microsegmentation; deny-by-default east-west traffic between workloads.",
    ),
    _cisa(
        "NW",
        2,
        "Network Traffic Management",
        "Encrypt all traffic; inspect with privacy-respecting controls.",
    ),
    _cisa(
        "NW",
        3,
        "Traffic Encryption",
        "Enforce TLS 1.3+ and post-quantum-ready algorithms across internal links.",
    ),
    _cisa(
        "NW",
        4,
        "Network Resilience",
        "Resilient network architectures with automated traffic steering during incidents.",
    ),
    # Applications & Workloads (5)
    _cisa(
        "AW",
        1,
        "Application Access",
        "Brokered, identity-aware access to applications regardless of network.",
    ),
    _cisa(
        "AW",
        2,
        "Application Threat Protections",
        "Runtime application protection; secrets isolated from code.",
    ),
    _cisa(
        "AW",
        3,
        "Accessible Applications",
        "Public-facing applications use ZT-aligned brokers; internal apps require no VPN.",
    ),
    _cisa(
        "AW",
        4,
        "Secure Application Development & Deployment Workflow",
        "Secure-by-default CI/CD pipelines with SBOM, signed artifacts, and policy gates.",
    ),
    _cisa(
        "AW",
        5,
        "Application Security Testing",
        "Continuous SAST/DAST/IaC scanning integrated into the change pipeline.",
    ),
    # Data (5)
    _cisa(
        "DT",
        1,
        "Data Inventory Management",
        "Maintain dynamic inventory of data assets with sensitivity classification.",
    ),
    _cisa(
        "DT",
        2,
        "Data Categorization",
        "Automated, ML-assisted data classification driving rights enforcement.",
    ),
    _cisa(
        "DT",
        3,
        "Data Availability",
        "Data availability + integrity guarantees enforced by replication and immutable backups.",
    ),
    _cisa(
        "DT",
        4,
        "Data Access",
        "Data access decisions consider user, device, location, and request context.",
    ),
    _cisa(
        "DT",
        5,
        "Data Encryption",
        "Data encrypted at rest, in transit, and in use; key custody separated from data plane.",
    ),
    # Visibility & Analytics (4)
    _cisa(
        "VA",
        1,
        "Log Storage",
        "Centralized, immutable log storage with retention aligned to mission needs.",
    ),
    _cisa(
        "VA",
        2,
        "Security Information & Event Management",
        "Cross-pillar SIEM correlation with risk scoring.",
    ),
    _cisa(
        "VA",
        3,
        "Threat Detection",
        "Behavior-based detections; threat hunting integrated into operations.",
    ),
    _cisa(
        "VA",
        4,
        "Common Security & Risk Analytics",
        "Unified risk model fusing identity, device, data, and workload signals.",
    ),
    # Automation & Orchestration (4)
    _cisa(
        "AO",
        1,
        "Policy Decision Point & Policy Orchestration",
        "Centralized PDP; policies expressed as code and enforced consistently.",
    ),
    _cisa(
        "AO",
        2,
        "Critical Process Automation",
        "Automated incident triage, containment, and remediation for known patterns.",
    ),
    _cisa("AO", 3, "Machine Learning", "ML-driven anomaly detection and adaptive policy tuning."),
    _cisa(
        "AO",
        4,
        "Artificial Intelligence",
        "AI-assisted decision support with human-in-the-loop for high-risk actions.",
    ),
    # Governance (5)
    _cisa(
        "GV", 1, "Policy", "Documented ZT policy with measurable outcomes; updated on a cadence."
    ),
    _cisa(
        "GV",
        2,
        "Compliance",
        "Continuous compliance monitoring against regulatory + agency requirements.",
    ),
    _cisa(
        "GV",
        3,
        "Supply Chain Risk Management",
        "Third-party + supply-chain risk integrated into ZT decisioning.",
    ),
    _cisa(
        "GV", 4, "Workforce", "ZT-aware workforce: training, role-based curricula, and exercises."
    ),
    _cisa(
        "GV",
        5,
        "Strategic Planning",
        "ZT roadmap aligned to mission objectives with measurable milestones.",
    ),
)


# ---------------------------------------------------------------------------
# DoD Zero Trust Reference Architecture (v1 baseline)
# ---------------------------------------------------------------------------

DOD_PILLARS: tuple[Pillar, ...] = (
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "USR",
        "User",
        "Authenticate, authorize, and continuously evaluate users against mission-driven risk.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "DEV",
        "Device",
        "Identify, authenticate, and continuously evaluate device security posture.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "APP",
        "Application & Workload",
        "Secure DevSecOps lifecycle and runtime protection for mission applications.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "DAT",
        "Data",
        "Tag, encrypt, and control data based on attributes throughout its lifecycle.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "NET",
        "Network & Environment",
        "Segment, isolate, and continuously monitor mission networks.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "VIS",
        "Visibility & Analytics",
        "Centralize sensor data and apply analytics across all pillars.",
    ),
    Pillar(
        ZtFrameworkCode.DOD_ZTRA,
        "AUT",
        "Automation & Orchestration",
        "Automate policy enforcement, response, and continuous validation across pillars.",
    ),
)


def _dod(pillar: str, num: int, name: str, outcome: str) -> Capability:
    return Capability(
        framework=ZtFrameworkCode.DOD_ZTRA,
        pillar_code=pillar,
        code=f"DOD.{pillar}.{num:02d}",
        name=name,
        outcome=outcome,
    )


DOD_CAPABILITIES: tuple[Capability, ...] = (
    # User (8)
    _dod(
        "USR",
        1,
        "User Inventory",
        "Authoritative user inventory across mission partners and contractors.",
    ),
    _dod(
        "USR",
        2,
        "Conditional User Access",
        "Risk-adaptive conditional access decisions per request.",
    ),
    _dod("USR", 3, "Multi-Factor Authentication", "Phishing-resistant MFA mandated for all users."),
    _dod(
        "USR", 4, "Privileged Access Management", "Just-in-time elevation with session recording."
    ),
    _dod(
        "USR",
        5,
        "Identity Federation & User Credentialing",
        "Federated identity with non-person-entity support.",
    ),
    _dod(
        "USR",
        6,
        "Behavioral Contextual ID + Biometrics",
        "Continuous behavior + biometric signals shape trust.",
    ),
    _dod(
        "USR", 7, "Least Privilege Access", "Defaults to least privilege; periodic recertification."
    ),
    _dod(
        "USR", 8, "Continuous Authentication", "Continuous re-authentication based on session risk."
    ),
    # Device (7)
    _dod("DEV", 1, "Device Inventory", "Hardware + firmware inventory maintained continuously."),
    _dod(
        "DEV",
        2,
        "Device Detection & Compliance",
        "Compliance posture checked before every resource access.",
    ),
    _dod(
        "DEV",
        3,
        "Device Authorization w/ Real Time Inspection",
        "Real-time device authorization with health attestation.",
    ),
    _dod("DEV", 4, "Remote Access", "Brokered remote access; per-resource authorization."),
    _dod(
        "DEV",
        5,
        "Partially & Fully Automated Asset, Vulnerability and Patch Management",
        "Automated patching with measured success rate.",
    ),
    _dod(
        "DEV",
        6,
        "Unified Endpoint Management & Mobile Device Management",
        "Unified policy across endpoint OSes and mobile.",
    ),
    _dod(
        "DEV",
        7,
        "Endpoint & Extended Detection & Response",
        "EDR/XDR coverage with automated containment.",
    ),
    # Application & Workload (7)
    _dod(
        "APP", 1, "Application Inventory", "Authoritative application portfolio with criticality."
    ),
    _dod(
        "APP",
        2,
        "Secure Software Development & Integration",
        "Secure-by-default DevSecOps with SBOM + signing.",
    ),
    _dod(
        "APP",
        3,
        "Software Risk Management",
        "Application-level risk register and remediation tracking.",
    ),
    _dod(
        "APP",
        4,
        "Resource Authorization & Integration",
        "Per-resource authorization integrated with PDP.",
    ),
    _dod(
        "APP",
        5,
        "Continuous Monitoring & Ongoing Authorizations",
        "Continuous ATO with automated artifact collection.",
    ),
    _dod(
        "APP",
        6,
        "Application Delivery",
        "Trusted application delivery with deployment policy gates.",
    ),
    _dod(
        "APP",
        7,
        "Software Defined Compute Infrastructure",
        "Software-defined compute with policy-enforced runtime.",
    ),
    # Data (7)
    _dod(
        "DAT", 1, "Data Catalog Risk Alignment", "Catalog data assets and align controls to risk."
    ),
    _dod(
        "DAT",
        2,
        "DoD Enterprise Data Governance",
        "Enterprise data governance applied to mission data.",
    ),
    _dod(
        "DAT", 3, "Data Labeling & Tagging", "Automated data tagging drives downstream enforcement."
    ),
    _dod(
        "DAT",
        4,
        "Data Monitoring & Sensing",
        "Data loss + exfiltration monitoring across egress points.",
    ),
    _dod(
        "DAT",
        5,
        "Data Encryption & Rights Management",
        "Rights-based access + encryption tied to data tags.",
    ),
    _dod("DAT", 6, "Data Access Control", "Attribute-based access enforced on every data request."),
    _dod("DAT", 7, "Data Loss Prevention", "Active DLP across endpoints, networks, and cloud."),
    # Network & Environment (7)
    _dod("NET", 1, "Data Flow Mapping", "Data flow maps maintained and used in policy decisions."),
    _dod("NET", 2, "Software Defined Networking", "SDN enables policy-driven traffic isolation."),
    _dod("NET", 3, "Macro Segmentation", "Mission-level macro segmentation with deny-by-default."),
    _dod(
        "NET",
        4,
        "Micro Segmentation",
        "Workload-level microsegmentation enforced by identity-aware proxies.",
    ),
    _dod(
        "NET",
        5,
        "Network Inspection & Traffic Analytics",
        "Encrypted-traffic-aware analytics with privacy safeguards.",
    ),
    _dod(
        "NET",
        6,
        "Network Threat Protection",
        "Inline threat protection with rapid signature distribution.",
    ),
    _dod(
        "NET",
        7,
        "Network Access Control",
        "ZT-aligned NAC; no implicit trust based on network position.",
    ),
    # Visibility & Analytics (7)
    _dod(
        "VIS",
        1,
        "Log All Traffic - Network, Data, Apps, Users",
        "Comprehensive logging with retention policies.",
    ),
    _dod(
        "VIS",
        2,
        "Security Information & Event Management (SIEM)",
        "SIEM correlates events across all pillars.",
    ),
    _dod(
        "VIS", 3, "Common Security & Risk Analytics", "Unified risk scoring informs PDP decisions."
    ),
    _dod(
        "VIS",
        4,
        "User & Entity Behavior Analytics",
        "UEBA detects anomalies across user + entity activity.",
    ),
    _dod(
        "VIS",
        5,
        "Threat Intelligence Integration",
        "Threat intel actively shapes detections + policy.",
    ),
    _dod(
        "VIS",
        6,
        "Automated Dynamic Policies",
        "Analytics output adjusts policy automatically within guardrails.",
    ),
    _dod(
        "VIS",
        7,
        "Asset ID & Alert Correlation",
        "Asset-aware alert correlation drives prioritization.",
    ),
    # Automation & Orchestration (7)
    _dod(
        "AUT",
        1,
        "Policy Decision Point & Policy Orchestration",
        "Centralized PDP enforces unified policy.",
    ),
    _dod(
        "AUT",
        2,
        "Critical Process Automation",
        "Automated response to defined high-confidence patterns.",
    ),
    _dod("AUT", 3, "Machine Learning", "ML adapts policy and detections to current telemetry."),
    _dod(
        "AUT", 4, "Artificial Intelligence", "AI-assisted decision support with human-in-the-loop."
    ),
    _dod(
        "AUT",
        5,
        "Security Orchestration, Automation & Response (SOAR)",
        "SOAR runbooks executed with audit trail.",
    ),
    _dod("AUT", 6, "API Standardization", "Standardized APIs across pillars enable orchestration."),
    _dod(
        "AUT",
        7,
        "Security Operations Center & Incident Response",
        "SOC + IR drilled regularly with measurable outcomes.",
    ),
)


# ---------------------------------------------------------------------------
# Combined accessors
# ---------------------------------------------------------------------------


def pillars(framework: ZtFrameworkCode) -> tuple[Pillar, ...]:
    return CISA_PILLARS if framework == ZtFrameworkCode.CISA_ZTMM_2_0 else DOD_PILLARS


def capabilities(framework: ZtFrameworkCode) -> tuple[Capability, ...]:
    return CISA_CAPABILITIES if framework == ZtFrameworkCode.CISA_ZTMM_2_0 else DOD_CAPABILITIES


def pillar_by_code(framework: ZtFrameworkCode, code: str) -> Pillar:
    for p in pillars(framework):
        if p.code == code:
            return p
    raise KeyError(f"{framework}:{code}")


def capability_by_code(code: str) -> Capability:
    for c in CISA_CAPABILITIES:
        if c.code == code:
            return c
    for c in DOD_CAPABILITIES:
        if c.code == code:
            return c
    raise KeyError(code)


def all_codes(framework: ZtFrameworkCode) -> frozenset[str]:
    return frozenset(c.code for c in capabilities(framework))


__all__ = [
    "CISA_CAPABILITIES",
    "CISA_PILLARS",
    "Capability",
    "DOD_CAPABILITIES",
    "DOD_PILLARS",
    "Pillar",
    "ZtFrameworkCode",
    "all_codes",
    "capabilities",
    "capability_by_code",
    "pillar_by_code",
    "pillars",
]
