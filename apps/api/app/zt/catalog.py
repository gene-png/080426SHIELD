"""Zero Trust catalogs: CISA ZTMM 2.0 + DoD ZT Reference Architecture.

Both frameworks share the same shape (Framework -> Pillar -> Capability),
which lets a single scoring + gap engine handle both. Capability codes
embed the framework prefix to keep them globally unique:

  CISA codes: "CISA.<PILLAR>.<NN>"   e.g. "CISA.ID.01"
  DoD codes:  "DOD.<PILLAR>.<NN>"    e.g. "DOD.USR.01"

Counts:
  CISA ZTMM 2.0:  5 pillars / 37 rows, verbatim from CISA's PDF (#838):
                  each pillar's functions plus its own three cross-cutting rows
  DoD ZTRA:       7 pillars / 50 capabilities (v1 baseline; corrected to the
                  DoD Execution Roadmap's 45 + 152 activities by #839)
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
    #: "function", or "cross_cutting" for a CISA pillar's Visibility and
    #: Analytics, Automation and Orchestration and Governance rows (#838).
    kind: str = "function"


# ---------------------------------------------------------------------------
# CISA ZTMM 2.0 (#838): verbatim from CISA's own PDF, Version 2.0, April 2023
# ---------------------------------------------------------------------------
#
# Five pillars (Section 5.1-5.5), each holding its functions and its own three
# cross-cutting rows, as CISA's Tables 2-6 do: 37 rows. Names, pillar
# definitions (`purpose`) and each row's Optimal stage text (`outcome`, labelled
# "CISA Optimal:") are CISA's, verbatim, from the committed extraction
# `reference-docs/cisa/cisa_ztmm_v2_rows.json`, which `test_zt_catalog_source.py`
# holds this section to. Table 7 (the enterprise-level cross-cutting
# capabilities) is out of scope (#838 decision 1). Codes are Kentro's:
# functions `CISA.<P>.<NN>` in CISA's row order, cross-cutting rows
# `CISA.<P>.VA` / `.AO` / `.GV` (never `.05`+, which would re-use codes that
# meant something else before #838).

CISA_PILLARS: tuple[Pillar, ...] = (
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "ID",
        "Identity",
        "An identity refers to an attribute or set of attributes that uniquely describes an agency user or entity, including non-person entities.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "DV",
        "Devices",
        "A device refers to any asset (including its hardware, software, firmware, etc.) that can connect to a network, including servers, desktop and laptop machines, printers, mobile phones, IoT devices, networking equipment, and more.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "NW",
        "Networks",
        "A network refers to an open communications medium including typical channels such as agency internal networks, wireless networks, and the Internet as well as other potential channels such as cellular and application-level channels used to transport messages.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "AW",
        "Applications and Workloads",
        "Applications and workloads include agency systems, computer programs, and services that execute on-premises, on mobile devices, and in cloud environments.",
    ),
    Pillar(
        ZtFrameworkCode.CISA_ZTMM_2_0,
        "DT",
        "Data",
        "Data includes all structured and unstructured files and fragments that reside or have resided in federal systems, devices, networks, applications, databases, infrastructure, and backups (including on-premises and virtual environments) as well as the associated metadata.",
    ),
)


def _cisa(pillar: str, row: int | str, name: str, optimal: str) -> Capability:
    """A function row (`row` is its 1-based number) or one of the pillar's three
    cross-cutting rows (`row` is "VA", "AO" or "GV")."""
    cross_cutting = isinstance(row, str)
    return Capability(
        framework=ZtFrameworkCode.CISA_ZTMM_2_0,
        pillar_code=pillar,
        code=f"CISA.{pillar}.{row}" if cross_cutting else f"CISA.{pillar}.{row:02d}",
        name=name,
        outcome=f"CISA Optimal: {optimal}",
        kind="cross_cutting" if cross_cutting else "function",
    )


CISA_CAPABILITIES: tuple[Capability, ...] = (
    # Identity (7): pages 13-15
    _cisa(
        "ID",
        1,
        "Authentication",
        "Agency continuously validates identity with phishing-resistant MFA, not just when access is initially granted.",
    ),
    _cisa(
        "ID",
        2,
        "Identity Stores",
        "Agency securely integrates their identity stores across all partners and environments as appropriate.",
    ),
    _cisa(
        "ID",
        3,
        "Risk Assessments",
        "Agency determines identity risk in real time based on continuous analysis and dynamic rules to deliver ongoing protection.",
    ),
    _cisa(
        "ID",
        4,
        "Access Management",
        "Agency uses automation to authorize just-in-time and just-enough access tailored to individual actions and individual resource needs.",
    ),
    _cisa(
        "ID",
        "VA",
        "Visibility and Analytics Capability",
        "Agency maintains comprehensive visibility and situational awareness across enterprise by performing automated analysis over user activity log types, including behavior-based analytics.",
    ),
    _cisa(
        "ID",
        "AO",
        "Automation and Orchestration Capability",
        "Agency automates orchestration of all identities with full integration across all environments based on behaviors, enrollments, and deployment needs.",
    ),
    _cisa(
        "ID",
        "GV",
        "Governance Capability",
        "Agency implements and fully automates enterprise-wide identity policies for all users and entities across all systems with continuous enforcement and dynamic updates.",
    ),
    # Devices (7): pages 17-19
    _cisa(
        "DV",
        1,
        "Policy Enforcement & Compliance Monitoring",
        "Agency continuously verifies insights and enforces compliance throughout the lifetime of devices and virtual assets. Agency integrates device, software, configuration, and vulnerability management across all agency environments, including for virtual assets.",
    ),
    _cisa(
        "DV",
        2,
        "Asset & Supply Chain Risk Management",
        "Agency has a comprehensive, at- or near-real-time view of all assets across vendors and service providers, automates its supply chain risk management as applicable, builds operations that tolerate supply chain failures, and incorporates best practices.",
    ),
    _cisa(
        "DV",
        3,
        "Resource Access",
        "Agency’s resource access considers real-time risk analytics within devices and virtual assets.",
    ),
    _cisa(
        "DV",
        4,
        "Device Threat Protection",
        "Agency has a centralized threat protection security solution(s) deployed with advanced capabilities for all devices and virtual assets and a unified approach for device threat protection, policy enforcement, and compliance monitoring.",
    ),
    _cisa(
        "DV",
        "VA",
        "Visibility and Analytics Capability",
        "Agency automates status collection of all network-connected devices and virtual assets while correlating with identities, conducting endpoint monitoring, and performing anomaly detection to inform resource access. Agency tracks patterns of provisioning and/or de-provisioning of virtual assets for anomalies.",
    ),
    _cisa(
        "DV",
        "AO",
        "Automation and Orchestration Capability",
        "Agency has fully automated processes for provisioning, registering, monitoring, isolating, remediating, and deprovisioning devices and virtual assets.",
    ),
    _cisa(
        "DV",
        "GV",
        "Governance Capability",
        "Agency automates policies for the lifecycle of all network-connected devices and virtual assets across the enterprise.",
    ),
    # Networks (7): pages 20-22
    _cisa(
        "NW",
        1,
        "Network Segmentation",
        "Agency network architecture consists of fully distributed ingress/egress micro-perimeters and extensive micro-segmentation based around application profiles with dynamic just-in-time and just-enough connectivity for service-specific interconnections.",
    ),
    _cisa(
        "NW",
        2,
        "Network Traffic Management",
        "Agency implements dynamic network rules and configurations that continuously evolve to meet application profile needs and reprioritize applications based on mission criticality, risk, etc.",
    ),
    _cisa(
        "NW",
        3,
        "Traffic Encryption",
        "Agency continues to encrypt traffic as appropriate, enforces least privilege principles for secure key management enterprise-wide, and incorporates best practices for cryptographic agility as widely as possible.",
    ),
    _cisa(
        "NW",
        4,
        "Network Resilience",
        "Agency integrates holistic delivery and awareness in adapting to changes in availability demands for all workloads and provides proportionate resilience.",
    ),
    _cisa(
        "NW",
        "VA",
        "Visibility and Analytics Capability",
        "Agency maintains visibility into communication across all agency networks and environments while enabling enterprise-wide situational awareness and advanced monitoring capabilities that automate telemetry correlation across all detection sources.",
    ),
    _cisa(
        "NW",
        "AO",
        "Automation and Orchestration Capability",
        "Agency networks and environments are defined using infrastructure-as-code managed by automated change management methods, including automated initiation and expiration to align with changing needs.",
    ),
    _cisa(
        "NW",
        "GV",
        "Governance Capability",
        "Agency implements enterprise-wide network policies that enable tailored, local controls; dynamic updates; and secure external connections based on application and user workflows.",
    ),
    # Applications and Workloads (8): pages 23-25
    _cisa(
        "AW",
        1,
        "Application Access",
        "Agency continuously authorizes application access, incorporating real-time risk analytics and factors such as behavior or usage patterns.",
    ),
    _cisa(
        "AW",
        2,
        "Application Threat Protections",
        "Agency integrates advanced threat protections into all application workflows, offering real-time visibility and content-aware protections against sophisticated attacks tailored to applications.",
    ),
    _cisa(
        "AW",
        3,
        "Accessible Applications",
        "Agency makes all applicable applications available over open public networks to authorized users and devices, where appropriate, as needed.",
    ),
    _cisa(
        "AW",
        4,
        "Secure Application Development and Deployment Workflow",
        "Agency leverages immutable workloads where feasible, only allowing changes to take effect through redeployment, and removes administrator access to deployment environments in favor of automated processes for code deployment.",
    ),
    _cisa(
        "AW",
        5,
        "Application Security Testing",
        "Agency integrates application security testing throughout the software development lifecycle across the enterprise with routine automated testing of deployed applications.",
    ),
    _cisa(
        "AW",
        "VA",
        "Visibility and Analytics Capability",
        "Agency performs continuous and dynamic monitoring across all applications to maintain enterprise-wide comprehensive visibility.",
    ),
    _cisa(
        "AW",
        "AO",
        "Automation and Orchestration Capability",
        "Agency automates application configurations to continuously optimize for security and performance.",
    ),
    _cisa(
        "AW",
        "GV",
        "Governance Capability",
        "Agency fully automates policies governing applications development and deployment, including incorporating dynamic updates for applications through the CI/CD pipeline.",
    ),
    # Data (8): pages 26-28
    _cisa(
        "DT",
        1,
        "Data Inventory Management",
        "Agency continuously inventories all applicable agency data and employs robust data loss prevention strategies that dynamically block suspected data exfiltration.",
    ),
    _cisa(
        "DT",
        2,
        "Data Categorization",
        "Agency automates data categorization and labeling enterprise-wide with robust techniques; granular, structured formats; and mechanisms to address all data types.",
    ),
    _cisa(
        "DT",
        3,
        "Data Availability",
        "Agency uses dynamic methods to optimize data availability, including historical data, according to user and entity need.",
    ),
    _cisa(
        "DT",
        4,
        "Data Access",
        "Agency automates dynamic just-in-time and just-enough data access controls enterprise-wide with continuous review of permissions.",
    ),
    _cisa(
        "DT",
        5,
        "Data Encryption",
        "Agency encrypts data in use where appropriate, enforces least privilege principles for secure key management enterprise-wide, and applies encryption using up-to-date standards and cryptographic agility to the extent possible.",
    ),
    _cisa(
        "DT",
        "VA",
        "Visibility and Analytics Capability",
        "Agency has visibility across the full data lifecycle with robust analytics, including predictive analytics, that support comprehensive views of agency data and continuous security posture assessment.",
    ),
    _cisa(
        "DT",
        "AO",
        "Automation and Orchestration Capability",
        "Agency automates, to the maximum extent possible, data lifecycles and security policies for all agency data across the enterprise.",
    ),
    _cisa(
        "DT",
        "GV",
        "Governance Capability",
        "Agency data lifecycle policies are unified to the maximum extent possible and dynamically enforced across the enterprise.",
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
