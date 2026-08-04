"""NIST CSF 2.0 catalog: 6 functions, 22 categories, 106 subcategories.

Reference data. Immutable. The wire types live in `app.schemas.csf`;
the workspace UI fetches this through GET /csf/catalog.

Each subcategory carries:
  - code         : canonical NIST identifier (e.g. "GV.OC-01")
  - function     : 2-letter function code
  - category     : 5-character category code (e.g. "GV.OC")
  - name         : short title in the workspace tab
  - outcome      : the "outcome statement" assessors score against

Notes on counts (CSF 2.0 Final, Feb 2024):
  GOVERN   31 subcategories across 6 categories
  IDENTIFY 22 subcategories across 3 categories
  PROTECT  22 subcategories across 5 categories
  DETECT   11 subcategories across 2 categories
  RESPOND  13 subcategories across 4 categories
  RECOVER   7 subcategories across 2 categories
  Total    106 subcategories / 22 categories / 6 functions
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class FunctionCode(enum.StrEnum):
    GV = "GV"  # GOVERN
    ID = "ID"  # IDENTIFY
    PR = "PR"  # PROTECT
    DE = "DE"  # DETECT
    RS = "RS"  # RESPOND
    RC = "RC"  # RECOVER


@dataclass(frozen=True)
class Function:
    code: FunctionCode
    name: str
    purpose: str


@dataclass(frozen=True)
class Category:
    code: str  # e.g. "GV.OC"
    function: FunctionCode
    name: str
    purpose: str


@dataclass(frozen=True)
class Subcategory:
    code: str  # e.g. "GV.OC-01"
    function: FunctionCode
    category: str  # "GV.OC"
    name: str
    outcome: str


FUNCTIONS: tuple[Function, ...] = (
    Function(
        code=FunctionCode.GV,
        name="GOVERN",
        purpose=(
            "Establish, communicate, and monitor the organization's "
            "cybersecurity risk management strategy, expectations, and policy."
        ),
    ),
    Function(
        code=FunctionCode.ID,
        name="IDENTIFY",
        purpose=(
            "Understand the organization's cybersecurity risk to systems, "
            "people, assets, data, and capabilities."
        ),
    ),
    Function(
        code=FunctionCode.PR,
        name="PROTECT",
        purpose=("Use safeguards to manage the organization's cybersecurity risk."),
    ),
    Function(
        code=FunctionCode.DE,
        name="DETECT",
        purpose=("Find and analyze possible cybersecurity attacks and compromises."),
    ),
    Function(
        code=FunctionCode.RS,
        name="RESPOND",
        purpose=("Take action regarding a detected cybersecurity incident."),
    ),
    Function(
        code=FunctionCode.RC,
        name="RECOVER",
        purpose=("Restore assets and operations affected by a cybersecurity incident."),
    ),
)


CATEGORIES: tuple[Category, ...] = (
    # GOVERN
    Category(
        "GV.OC",
        FunctionCode.GV,
        "Organizational Context",
        "The circumstances surrounding the organization's cybersecurity risk management.",
    ),
    Category(
        "GV.RM",
        FunctionCode.GV,
        "Risk Management Strategy",
        "The organization's priorities, constraints, risk tolerance, and assumptions are established.",
    ),
    Category(
        "GV.RR",
        FunctionCode.GV,
        "Roles, Responsibilities, and Authorities",
        "Cybersecurity roles and responsibilities are established and communicated.",
    ),
    Category(
        "GV.PO",
        FunctionCode.GV,
        "Policy",
        "Organizational cybersecurity policy is established, communicated, and enforced.",
    ),
    Category(
        "GV.OV",
        FunctionCode.GV,
        "Oversight",
        "Results of organization-wide cybersecurity risk-management activities inform strategy.",
    ),
    Category(
        "GV.SC",
        FunctionCode.GV,
        "Cybersecurity Supply Chain Risk Management",
        "Cyber supply chain risk-management processes are identified, established, and managed.",
    ),
    # IDENTIFY
    Category(
        "ID.AM",
        FunctionCode.ID,
        "Asset Management",
        "Assets, personnel, devices, systems, and facilities are identified and managed.",
    ),
    Category(
        "ID.RA",
        FunctionCode.ID,
        "Risk Assessment",
        "The cybersecurity risk to the organization, assets, and individuals is understood.",
    ),
    Category(
        "ID.IM",
        FunctionCode.ID,
        "Improvement",
        "Improvements to the organization's cybersecurity risk management are identified.",
    ),
    # PROTECT
    Category(
        "PR.AA",
        FunctionCode.PR,
        "Identity Management, Authentication, and Access Control",
        "Access to assets is limited to authorized users, services, and hardware.",
    ),
    Category(
        "PR.AT",
        FunctionCode.PR,
        "Awareness and Training",
        "Personnel receive cybersecurity awareness training and develop role-specific skills.",
    ),
    Category(
        "PR.DS",
        FunctionCode.PR,
        "Data Security",
        "Data is managed consistent with the organization's risk strategy.",
    ),
    Category(
        "PR.PS",
        FunctionCode.PR,
        "Platform Security",
        "Hardware, software, and services of physical and virtual platforms are managed securely.",
    ),
    Category(
        "PR.IR",
        FunctionCode.PR,
        "Technology Infrastructure Resilience",
        "Security architectures support availability and resilience requirements.",
    ),
    # DETECT
    Category(
        "DE.CM",
        FunctionCode.DE,
        "Continuous Monitoring",
        "Assets are monitored to find anomalies, indicators of compromise, and adverse events.",
    ),
    Category(
        "DE.AE",
        FunctionCode.DE,
        "Adverse Event Analysis",
        "Anomalies and adverse events are analyzed to characterize incidents.",
    ),
    # RESPOND
    Category(
        "RS.MA",
        FunctionCode.RS,
        "Incident Management",
        "Responses to detected incidents are managed.",
    ),
    Category(
        "RS.AN",
        FunctionCode.RS,
        "Incident Analysis",
        "Investigations are performed to support response and recovery.",
    ),
    Category(
        "RS.CO",
        FunctionCode.RS,
        "Incident Response Reporting and Communication",
        "Response activities are coordinated with internal and external stakeholders.",
    ),
    Category(
        "RS.MI",
        FunctionCode.RS,
        "Incident Mitigation",
        "Activities are performed to prevent expansion of an event and resolve incidents.",
    ),
    # RECOVER
    Category(
        "RC.RP",
        FunctionCode.RC,
        "Incident Recovery Plan Execution",
        "Restoration activities are coordinated and performed to ensure timely recovery.",
    ),
    Category(
        "RC.CO",
        FunctionCode.RC,
        "Incident Recovery Communication",
        "Restoration activities are coordinated with internal and external parties.",
    ),
)


def _sc(code: str, name: str, outcome: str) -> Subcategory:
    """Helper - derive function + category from the code."""
    cat = code.rsplit("-", 1)[0]
    fn = FunctionCode(cat.split(".", 1)[0])
    return Subcategory(code=code, function=fn, category=cat, name=name, outcome=outcome)


SUBCATEGORIES: tuple[Subcategory, ...] = (
    # ---- GOVERN ----------------------------------------------------------
    # GV.OC - Organizational Context (5)
    _sc(
        "GV.OC-01",
        "Mission understanding",
        "The organizational mission is understood and informs cybersecurity risk management.",
    ),
    _sc(
        "GV.OC-02",
        "Stakeholder expectations",
        "Internal and external stakeholders are understood, and their needs and expectations regarding cybersecurity are considered.",
    ),
    _sc(
        "GV.OC-03",
        "Legal, regulatory, contractual",
        "Legal, regulatory, and contractual requirements regarding cybersecurity are understood and managed.",
    ),
    _sc(
        "GV.OC-04",
        "Critical objectives, capabilities, services",
        "Critical objectives, capabilities, and services that stakeholders depend on are understood and communicated.",
    ),
    _sc(
        "GV.OC-05",
        "Outcomes, capabilities, services that the org depends on",
        "Outcomes, capabilities, and services that the organization depends on are understood and communicated.",
    ),
    # GV.RM - Risk Management Strategy (7)
    _sc(
        "GV.RM-01",
        "Risk management objectives",
        "Risk management objectives are established and agreed to by organizational stakeholders.",
    ),
    _sc(
        "GV.RM-02",
        "Risk appetite and tolerance",
        "Risk appetite and risk tolerance statements are established, communicated, and maintained.",
    ),
    _sc(
        "GV.RM-03",
        "Cybersecurity risk in ERM",
        "Cybersecurity risk management activities and outcomes are included in enterprise risk management processes.",
    ),
    _sc(
        "GV.RM-04",
        "Strategic direction",
        "Strategic direction describing appropriate risk response options is established and communicated.",
    ),
    _sc(
        "GV.RM-05",
        "Lines of communication",
        "Lines of communication across the organization are established for cybersecurity risks.",
    ),
    _sc(
        "GV.RM-06",
        "Standardized methods for risk",
        "A standardized method for calculating, documenting, categorizing, and prioritizing cybersecurity risks is established and communicated.",
    ),
    _sc(
        "GV.RM-07",
        "Strategic risk opportunities",
        "Strategic opportunities (i.e., positive risks) are characterized and included in organizational cybersecurity risk discussions.",
    ),
    # GV.RR - Roles, Responsibilities, and Authorities (4)
    _sc(
        "GV.RR-01",
        "Leadership accountability",
        "Organizational leadership is responsible and accountable for cybersecurity risk and fosters a culture that is risk-aware, ethical, and continually improving.",
    ),
    _sc(
        "GV.RR-02",
        "Roles & responsibilities established",
        "Roles, responsibilities, and authorities related to cybersecurity risk management are established, communicated, understood, and enforced.",
    ),
    _sc(
        "GV.RR-03",
        "Adequate resources",
        "Adequate resources are allocated commensurate with the cybersecurity risk strategy, roles, responsibilities, and policies.",
    ),
    _sc(
        "GV.RR-04",
        "Cybersecurity in HR practices",
        "Cybersecurity is included in human resources practices.",
    ),
    # GV.PO - Policy (2)
    _sc(
        "GV.PO-01",
        "Policy established",
        "Policy for managing cybersecurity risks is established based on organizational context, cybersecurity strategy, and priorities and is communicated and enforced.",
    ),
    _sc(
        "GV.PO-02",
        "Policy reviewed and updated",
        "Policy for managing cybersecurity risks is reviewed, updated, communicated, and enforced to reflect changes in requirements, threats, technology, and organizational mission.",
    ),
    # GV.OV - Oversight (3)
    _sc(
        "GV.OV-01",
        "Risk strategy outcomes reviewed",
        "Cybersecurity risk management strategy outcomes are reviewed to inform and adjust strategy and direction.",
    ),
    _sc(
        "GV.OV-02",
        "Risk strategy reviewed and adjusted",
        "The cybersecurity risk management strategy is reviewed and adjusted to ensure coverage of organizational requirements and risks.",
    ),
    _sc(
        "GV.OV-03",
        "Cybersecurity performance evaluated",
        "Organizational cybersecurity risk management performance is evaluated and reviewed for adjustments needed.",
    ),
    # GV.SC - Cybersecurity Supply Chain Risk Management (10)
    _sc(
        "GV.SC-01",
        "C-SCRM program established",
        "A cybersecurity supply chain risk management program, strategy, objectives, policies, and processes are established and agreed to by organizational stakeholders.",
    ),
    _sc(
        "GV.SC-02",
        "C-SCRM roles & responsibilities",
        "Cybersecurity roles and responsibilities for suppliers, customers, and partners are established, communicated, and coordinated internally and externally.",
    ),
    _sc(
        "GV.SC-03",
        "C-SCRM integrated",
        "Cybersecurity supply chain risk management is integrated into cybersecurity and enterprise risk management, risk assessment, and improvement processes.",
    ),
    _sc(
        "GV.SC-04",
        "Suppliers identified and prioritized",
        "Suppliers are known and prioritized by criticality.",
    ),
    _sc(
        "GV.SC-05",
        "Supplier requirements",
        "Requirements to address cybersecurity risks in supply chains are established, prioritized, and integrated into contracts and other types of agreements with suppliers and other relevant third parties.",
    ),
    _sc(
        "GV.SC-06",
        "Pre-engagement due diligence",
        "Planning and due diligence are performed to reduce risks before entering into formal supplier or other third-party relationships.",
    ),
    _sc(
        "GV.SC-07",
        "Supplier risks monitored",
        "The risks posed by a supplier, their products and services, and other third parties are understood, recorded, prioritized, assessed, responded to, and monitored over the course of the relationship.",
    ),
    _sc(
        "GV.SC-08",
        "Suppliers in IR/BC plans",
        "Relevant suppliers and other third parties are included in incident planning, response, and recovery activities.",
    ),
    _sc(
        "GV.SC-09",
        "Supply chain practices integrated",
        "Supply chain security practices are integrated into cybersecurity and enterprise risk management programs, and their performance is monitored throughout the technology product and service life cycle.",
    ),
    _sc(
        "GV.SC-10",
        "C-SCRM plan considers end-of-relationship",
        "Cybersecurity supply chain risk management plans include provisions for activities that occur after the conclusion of a partnership or service agreement.",
    ),
    # ---- IDENTIFY --------------------------------------------------------
    # ID.AM - Asset Management (8)
    _sc(
        "ID.AM-01",
        "Hardware inventory",
        "Inventories of hardware managed by the organization are maintained.",
    ),
    _sc(
        "ID.AM-02",
        "Software inventory",
        "Inventories of software, services, and systems managed by the organization are maintained.",
    ),
    _sc(
        "ID.AM-03",
        "Data flow + comm maps",
        "Representations of the organization's authorized network communication and internal and external network data flows are maintained.",
    ),
    _sc(
        "ID.AM-04",
        "External systems",
        "Inventories of services provided by suppliers are maintained.",
    ),
    _sc(
        "ID.AM-05",
        "Asset prioritization",
        "Assets are prioritized based on classification, criticality, resources, and impact on the mission.",
    ),
    _sc(
        "ID.AM-07",
        "Data and metadata inventories",
        "Inventories of data and corresponding metadata for designated data types are maintained.",
    ),
    _sc(
        "ID.AM-08",
        "Asset life cycle management",
        "Systems, hardware, software, services, and data are managed throughout their life cycles.",
    ),
    _sc(
        "ID.AM-09",
        "Personnel inventories",
        "Inventories of personnel with cybersecurity-related responsibilities are maintained.",
    ),
    # ID.RA - Risk Assessment (10)
    _sc(
        "ID.RA-01",
        "Vulnerabilities identified",
        "Vulnerabilities in assets are identified, validated, and recorded.",
    ),
    _sc(
        "ID.RA-02",
        "Cyber threat intelligence",
        "Cyber threat intelligence is received from information-sharing forums and sources.",
    ),
    _sc(
        "ID.RA-03",
        "Internal & external threats",
        "Internal and external threats to the organization are identified and recorded.",
    ),
    _sc(
        "ID.RA-04",
        "Likelihood and impact identified",
        "Potential impacts and likelihoods of threats exploiting vulnerabilities are identified and recorded.",
    ),
    _sc(
        "ID.RA-05",
        "Threats × vulns × impacts → risk",
        "Threats, vulnerabilities, likelihoods, and impacts are used to understand inherent risk and inform risk response prioritization.",
    ),
    _sc(
        "ID.RA-06",
        "Risk responses chosen",
        "Risk responses are chosen, prioritized, planned, tracked, and communicated.",
    ),
    _sc(
        "ID.RA-07",
        "Changes and exceptions",
        "Changes and exceptions are managed, assessed for risk impact, recorded, and tracked.",
    ),
    _sc(
        "ID.RA-08",
        "Vulnerability disclosure process",
        "Processes for receiving, analyzing, and responding to vulnerability disclosures are established.",
    ),
    _sc(
        "ID.RA-09",
        "Authenticity & integrity of HW/SW",
        "The authenticity and integrity of hardware and software are assessed prior to acquisition and use.",
    ),
    _sc(
        "ID.RA-10",
        "Critical supplier risk assessed",
        "Critical suppliers are assessed prior to acquisition.",
    ),
    # ID.IM - Improvement (4)
    _sc(
        "ID.IM-01",
        "Improvements identified from evals",
        "Improvements are identified from evaluations.",
    ),
    _sc(
        "ID.IM-02",
        "Improvements from tests/exercises",
        "Improvements are identified from security tests and exercises, including those done in coordination with suppliers and relevant third parties.",
    ),
    _sc(
        "ID.IM-03",
        "Improvements from execution",
        "Improvements are identified from execution of operational processes, procedures, and activities.",
    ),
    _sc(
        "ID.IM-04",
        "IR & BC plans",
        "Incident response plans and other cybersecurity plans that affect operations are established, communicated, maintained, and improved.",
    ),
    # ---- PROTECT ---------------------------------------------------------
    # PR.AA - Identity Mgmt, Authentication, Access Control (6)
    _sc(
        "PR.AA-01",
        "Identity issuance & management",
        "Identities and credentials for authorized users, services, and hardware are managed by the organization.",
    ),
    _sc(
        "PR.AA-02",
        "Identity proofing",
        "Identities are proofed and bound to credentials based on the context of interactions.",
    ),
    _sc("PR.AA-03", "Authentication strength", "Users, services, and hardware are authenticated."),
    _sc(
        "PR.AA-04",
        "Identity assertions protected",
        "Identity assertions are protected, conveyed, and verified.",
    ),
    _sc(
        "PR.AA-05",
        "Access permissions enforced",
        "Access permissions, entitlements, and authorizations are defined in a policy, managed, enforced, and reviewed, and incorporate the principles of least privilege and separation of duties.",
    ),
    _sc(
        "PR.AA-06",
        "Physical access",
        "Physical access to assets is managed, monitored, and enforced commensurate with risk.",
    ),
    # PR.AT - Awareness and Training (2)
    _sc(
        "PR.AT-01",
        "General awareness",
        "Personnel are provided with awareness and training so that they possess the knowledge and skills to perform general tasks with cybersecurity risks in mind.",
    ),
    _sc(
        "PR.AT-02",
        "Specialized awareness",
        "Individuals in specialized roles are provided with awareness and training so that they possess the knowledge and skills to perform relevant tasks with cybersecurity risks in mind.",
    ),
    # PR.DS - Data Security (4)
    _sc(
        "PR.DS-01",
        "Data-at-rest confidentiality, integrity, availability",
        "The confidentiality, integrity, and availability of data-at-rest are protected.",
    ),
    _sc(
        "PR.DS-02",
        "Data-in-transit",
        "The confidentiality, integrity, and availability of data-in-transit are protected.",
    ),
    _sc(
        "PR.DS-10",
        "Data-in-use",
        "The confidentiality, integrity, and availability of data-in-use are protected.",
    ),
    _sc(
        "PR.DS-11",
        "Backups maintained, protected",
        "Backups of data are created, protected, maintained, and tested.",
    ),
    # PR.PS - Platform Security (6)
    _sc(
        "PR.PS-01",
        "Configuration management",
        "Configuration management practices are established and applied.",
    ),
    _sc(
        "PR.PS-02",
        "Software maintained, replaced, removed",
        "Software is maintained, replaced, and removed commensurate with risk.",
    ),
    _sc(
        "PR.PS-03",
        "Hardware maintained, replaced, removed",
        "Hardware is maintained, replaced, and removed commensurate with risk.",
    ),
    _sc(
        "PR.PS-04",
        "Logs generated and made available",
        "Log records are generated and made available for continuous monitoring.",
    ),
    _sc(
        "PR.PS-05",
        "Installation/execution controlled",
        "Installation and execution of unauthorized software are prevented.",
    ),
    _sc(
        "PR.PS-06",
        "Secure SDLC practices",
        "Secure software development practices are integrated, and their performance is monitored throughout the software development life cycle.",
    ),
    # PR.IR - Tech Infrastructure Resilience (4)
    _sc(
        "PR.IR-01",
        "Networks/environments protected from unauth access",
        "Networks and environments are protected from unauthorized logical access and usage.",
    ),
    _sc(
        "PR.IR-02",
        "Resilience to environmental threats",
        "The organization's technology assets are protected from environmental threats.",
    ),
    _sc(
        "PR.IR-03",
        "Resilience requirements met",
        "Mechanisms are implemented to achieve resilience requirements in normal and adverse situations.",
    ),
    _sc(
        "PR.IR-04",
        "Adequate resource capacity",
        "Adequate resource capacity to ensure availability is maintained.",
    ),
    # ---- DETECT ----------------------------------------------------------
    # DE.CM - Continuous Monitoring (5)
    _sc(
        "DE.CM-01",
        "Networks monitored",
        "Networks and network services are monitored to find potentially adverse events.",
    ),
    _sc(
        "DE.CM-02",
        "Physical environment monitored",
        "The physical environment is monitored to find potentially adverse events.",
    ),
    _sc(
        "DE.CM-03",
        "Personnel activity monitored",
        "Personnel activity and technology usage are monitored to find potentially adverse events.",
    ),
    _sc(
        "DE.CM-06",
        "External service provider activity monitored",
        "External service provider activities and services are monitored to find potentially adverse events.",
    ),
    _sc(
        "DE.CM-09",
        "Hardware/software/services monitored",
        "Computing hardware and software, runtime environments, and their data are monitored to find potentially adverse events.",
    ),
    # DE.AE - Adverse Event Analysis (6)
    _sc(
        "DE.AE-02",
        "Indicators analyzed",
        "Potentially adverse events are analyzed to better understand associated activities.",
    ),
    _sc(
        "DE.AE-03",
        "Information correlated from many sources",
        "Information is correlated from multiple sources.",
    ),
    _sc(
        "DE.AE-04",
        "Impact and scope estimated",
        "The estimated impact and scope of adverse events are understood.",
    ),
    _sc(
        "DE.AE-06",
        "Notify other stakeholders",
        "Information on adverse events is provided to authorized staff and tools.",
    ),
    _sc(
        "DE.AE-07",
        "CTI integrated into detection",
        "Cyber threat intelligence and other contextual information are integrated into the analysis.",
    ),
    _sc(
        "DE.AE-08",
        "Incidents declared",
        "Incidents are declared when adverse events meet the defined incident criteria.",
    ),
    # ---- RESPOND ---------------------------------------------------------
    # RS.MA - Incident Management (5)
    _sc(
        "RS.MA-01",
        "Response plan executed in coordination",
        "The incident response plan is executed in coordination with relevant third parties once an incident is declared.",
    ),
    _sc("RS.MA-02", "Incidents triaged", "Incident reports are triaged and validated."),
    _sc(
        "RS.MA-03",
        "Incidents categorized & prioritized",
        "Incidents are categorized and prioritized.",
    ),
    _sc(
        "RS.MA-04", "Incidents escalated/elevated", "Incidents are escalated or elevated as needed."
    ),
    _sc(
        "RS.MA-05",
        "Criteria to initiate recovery applied",
        "The criteria for initiating incident recovery are applied.",
    ),
    # RS.AN - Incident Analysis (4)
    _sc(
        "RS.AN-03",
        "Analysis determines root cause",
        "Analysis is performed to establish what has taken place during an incident and the root cause of the incident.",
    ),
    _sc(
        "RS.AN-06",
        "Investigations documented",
        "Actions performed during an investigation are recorded, and the records' integrity and provenance are preserved.",
    ),
    _sc(
        "RS.AN-07",
        "Incident data and metadata collected",
        "Incident data and metadata are collected, and their integrity and provenance are preserved.",
    ),
    _sc(
        "RS.AN-08",
        "Incident magnitude estimated",
        "An incident's magnitude is estimated and validated.",
    ),
    # RS.CO - Incident Response Reporting & Communication (2)
    _sc(
        "RS.CO-02",
        "Stakeholders notified",
        "Internal and external stakeholders are notified of incidents.",
    ),
    _sc(
        "RS.CO-03",
        "Information shared with designated stakeholders",
        "Information is shared with designated internal and external stakeholders.",
    ),
    # RS.MI - Incident Mitigation (2)
    _sc("RS.MI-01", "Incidents contained", "Incidents are contained."),
    _sc("RS.MI-02", "Incidents eradicated", "Incidents are eradicated."),
    # ---- RECOVER ---------------------------------------------------------
    # RC.RP - Incident Recovery Plan Execution (6)
    _sc(
        "RC.RP-01",
        "Recovery plan executed",
        "The recovery portion of the incident response plan is executed once initiated from the incident response process.",
    ),
    _sc(
        "RC.RP-02",
        "Recovery actions selected, scoped, prioritized",
        "Recovery actions are selected, scoped, prioritized, and performed.",
    ),
    _sc(
        "RC.RP-03",
        "Backups & restoration assets verified",
        "The integrity of backups and other restoration assets is verified before using them for restoration.",
    ),
    _sc(
        "RC.RP-04",
        "Critical mission functions restored",
        "Critical mission functions and cybersecurity risk management are considered to establish post-incident operational norms.",
    ),
    _sc(
        "RC.RP-05",
        "Recovery verified",
        "The integrity of restored assets is verified, systems and services are restored, and normal operating status is confirmed.",
    ),
    _sc(
        "RC.RP-06",
        "End of recovery declared",
        "The end of incident recovery is declared based on criteria, and incident-related documentation is completed.",
    ),
    # RC.CO - Incident Recovery Communication (1)
    _sc(
        "RC.CO-03",
        "Public updates",
        "Recovery activities and progress in restoring operational capabilities are communicated to designated internal and external stakeholders.",
    ),
)


# ---------------------------------------------------------------------------
# Impact-profile scoping (FIPS-199 Low / Moderate / High)
# ---------------------------------------------------------------------------
# NIST CSF 2.0 does NOT itself define Low/Mod/High subcategory baselines (that's
# an 800-53B control-baseline concept), so this is a curated first-pass mapping
# at the category level - refine with SME review. A client at profile P answers
# the subcategories whose min_profile rank is <= P's rank (LOW < MOD < HIGH).
PROFILE_RANK: dict[str, int] = {"LOW": 0, "MOD": 1, "HIGH": 2}

_CATEGORY_MIN_PROFILE: dict[str, str] = {
    # GOVERN
    "GV.OC": "LOW",
    "GV.RM": "LOW",
    "GV.RR": "LOW",
    "GV.PO": "LOW",
    "GV.OV": "MOD",
    "GV.SC": "HIGH",
    # IDENTIFY
    "ID.AM": "LOW",
    "ID.RA": "LOW",
    "ID.IM": "MOD",
    # PROTECT
    "PR.AA": "LOW",
    "PR.AT": "LOW",
    "PR.DS": "LOW",
    "PR.PS": "MOD",
    "PR.IR": "HIGH",
    # DETECT
    "DE.CM": "LOW",
    "DE.AE": "MOD",
    # RESPOND
    "RS.MA": "LOW",
    "RS.AN": "MOD",
    "RS.CO": "MOD",
    "RS.MI": "MOD",
    # RECOVER
    "RC.RP": "LOW",
    "RC.CO": "MOD",
}


def min_profile_for_category(category: str) -> str:
    """Minimum impact profile at which a category's subcategories apply.

    Defaults to LOW (in scope for everyone) for any unmapped category.
    """
    return _CATEGORY_MIN_PROFILE.get(category, "LOW")


def applies_to_profile(min_profile: str, client_profile: str | None) -> bool:
    """Whether a subcategory at `min_profile` is in scope for `client_profile`.

    An unknown/absent client profile shows everything (no filtering).
    """
    if client_profile is None:
        return True
    return PROFILE_RANK.get(min_profile, 0) <= PROFILE_RANK.get(client_profile, 2)


def function_by_code(code: str | FunctionCode) -> Function:
    value = FunctionCode(code)
    for fn in FUNCTIONS:
        if fn.code == value:
            return fn
    raise KeyError(code)


def category_by_code(code: str) -> Category:
    for cat in CATEGORIES:
        if cat.code == code:
            return cat
    raise KeyError(code)


def subcategory_by_code(code: str) -> Subcategory:
    for sc in SUBCATEGORIES:
        if sc.code == code:
            return sc
    raise KeyError(code)


def subcategories_for_function(code: str | FunctionCode) -> tuple[Subcategory, ...]:
    value = FunctionCode(code)
    return tuple(s for s in SUBCATEGORIES if s.function == value)


def all_codes() -> frozenset[str]:
    return frozenset(s.code for s in SUBCATEGORIES)


# ---------------------------------------------------------------------------
# IG metric cross-reference (Core/Supplemental + Primary/Supporting alignment)
# ---------------------------------------------------------------------------
# Spec section 8 ("IG metric metadata"): per subcategory, which IG metric(s) it
# maps to, Core vs. Supplemental, and Primary vs. Supporting alignment. This
# data ships in the "Reference Data" tab of the Step 2.x Working Profile XLSX
# toolkit (columns "Core / Supp" and "Alignment"); imported here verbatim and
# consistent across the HIGH/MODERATE/LOW workbooks.
#
# It feeds the deterministic weighted-floor roll-up (app.csf.playbook):
#   - Rule 2 (strict floor)  needs is_core_primary  = Core AND Primary.
#   - Rule 5 (LOW override)   needs is_supporting_or_supplemental
#                                  = Supporting alignment OR Supplemental class.
#   - gap_priority            needs is_core          = Core class.
#
# ADDITIVE (C0 pattern): a subcategory absent from this map returns the safe
# pre-import defaults (not core, not primary, not supporting), so older
# persisted assessments roll up exactly as before. "AI suggests, code
# computes" - this is static catalog data; the LLM is never involved.


class CoreClass(enum.StrEnum):
    CORE = "Core"
    SUPPLEMENTAL = "Supplemental"


class Alignment(enum.StrEnum):
    PRIMARY = "Primary"
    SUPPORTING = "Supporting"


@dataclass(frozen=True)
class IgMetadata:
    core_class: CoreClass
    alignment: Alignment


_IG_METADATA: dict[str, IgMetadata] = {
    # DETECT
    "DE.AE-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "DE.AE-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "DE.AE-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "DE.AE-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.AE-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.AE-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.AE-07": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.AE-08": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "DE.CM-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "DE.CM-02": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.CM-03": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.CM-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "DE.CM-09": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    # GOVERN
    "GV.OC-01": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.OC-02": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.SUPPORTING),
    "GV.OC-03": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.OC-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.OC-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.OV-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.OV-02": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.OV-03": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.PO-01": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.PO-02": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.SUPPORTING),
    "GV.RM-01": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RM-02": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RM-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.RM-04": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RM-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.RM-06": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.RM-07": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.SUPPORTING),
    "GV.RR-01": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RR-02": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RR-03": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "GV.RR-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.SC-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-04": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-05": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-06": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-07": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-08": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "GV.SC-09": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "GV.SC-10": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    # IDENTIFY
    "ID.AM-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.AM-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.AM-03": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.AM-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.AM-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.AM-07": IgMetadata(CoreClass.SUPPLEMENTAL, Alignment.PRIMARY),
    "ID.AM-08": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.IM-01": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.IM-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.IM-03": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.IM-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-01": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-02": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.RA-04": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.RA-05": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.RA-06": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "ID.RA-07": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-08": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-09": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "ID.RA-10": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    # PROTECT
    "PR.AA-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.AA-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.AA-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.AA-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.AA-05": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.AA-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.AT-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.AT-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.DS-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.DS-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.DS-10": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.DS-11": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.IR-01": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.IR-02": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.IR-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.IR-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.PS-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.PS-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "PR.PS-03": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.PS-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.PS-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "PR.PS-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    # RECOVER
    "RC.CO-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RC.CO-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RC.RP-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RC.RP-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RC.RP-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RC.RP-04": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RC.RP-05": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RC.RP-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    # RESPOND
    "RS.AN-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.AN-06": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RS.AN-07": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RS.AN-08": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RS.CO-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.CO-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MA-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MA-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MA-03": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MA-04": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MA-05": IgMetadata(CoreClass.CORE, Alignment.SUPPORTING),
    "RS.MI-01": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
    "RS.MI-02": IgMetadata(CoreClass.CORE, Alignment.PRIMARY),
}


def ig_metadata_for(code: str) -> IgMetadata | None:
    """The IG Core/alignment classification for a subcategory, or None if the
    subcategory is not in the imported mapping (additive/safe-default)."""
    return _IG_METADATA.get(code)


def is_core(code: str) -> bool:
    """True iff the subcategory maps to a Core IG metric (gap_priority input)."""
    meta = _IG_METADATA.get(code)
    return meta is not None and meta.core_class is CoreClass.CORE


def is_core_primary(code: str) -> bool:
    """True iff Core AND Primary alignment - the weighted-floor Rule 2 trigger."""
    meta = _IG_METADATA.get(code)
    return (
        meta is not None
        and meta.core_class is CoreClass.CORE
        and meta.alignment is Alignment.PRIMARY
    )


def is_supporting_or_supplemental(code: str) -> bool:
    """True iff Supporting-aligned OR Supplemental - the Rule 5 override trigger."""
    meta = _IG_METADATA.get(code)
    if meta is None:
        return False
    return meta.alignment is Alignment.SUPPORTING or meta.core_class is CoreClass.SUPPLEMENTAL
