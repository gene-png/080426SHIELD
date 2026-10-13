"""SQLAlchemy ORM models.

Import order matters here: importing this package registers every model
against `Base.metadata`, which Alembic autogenerate relies on.
"""

from __future__ import annotations

from app.models.ai_run import AiRun, AiRunStatus
from app.models.artifact import Artifact, ArtifactDocStatus, ArtifactOrigin
from app.models.attack_assessment import (
    AttackAssessment,
    AttackAssessmentStatus,
    AttackCoverage,
)
from app.models.attack_scenario import (
    AttackScenario,
    AttackScenarioRow,
    AttackScenarioState,
)
from app.models.audit_entry import AuditEntry
from app.models.capability import (
    CapabilityItem,
    CapabilityList,
    CapabilityListStatus,
)
from app.models.client import Client
from app.models.client_domain import ClientDomain
from app.models.csf_assessment import (
    CsfAnswer,
    CsfAssessment,
    CsfAssessmentStatus,
)
from app.models.csf_profile import CsfDimensionScore, CsfEvidenceBasis, CsfGapAction
from app.models.deliverable import Deliverable
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.models.evidence_link import EvidenceLink, EvidenceLinkStatus, EvidenceTargetKind
from app.models.findings_report import FindingsReport, FindingsReportStatus
from app.models.integration_run import IntegrationRun
from app.models.llm_call import LLMCall, LLMCallMode, LLMCallStatus
from app.models.llm_credential import LlmCredential
from app.models.message import Message
from app.models.notification import Notification
from app.models.questionnaire import Question
from app.models.recommendation import (
    Recommendation,
    RecommendationEffectStatus,
    RecommendationKind,
    RecommendationScope,
    RecommendationStatus,
)
from app.models.risk_register import RiskEntry, RiskRegister
from app.models.service import Service, ServiceKind, ServiceStatus
from app.models.service_request import ServiceRequest, ServiceType
from app.models.user import User, UserRole
from app.models.user_recovery_code import UserRecoveryCode
from app.models.zt_assessment import (
    ZtAnswer,
    ZtAssessment,
    ZtAssessmentStatus,
    ZtFramework,
)

__all__ = [
    "AiRun",
    "AiRunStatus",
    "Artifact",
    "ArtifactDocStatus",
    "ArtifactOrigin",
    "AttackAssessment",
    "AttackAssessmentStatus",
    "AttackCoverage",
    "AttackScenario",
    "AttackScenarioRow",
    "AttackScenarioState",
    "AuditEntry",
    "CapabilityItem",
    "CapabilityList",
    "CapabilityListStatus",
    "Client",
    "ClientDomain",
    "CsfAnswer",
    "CsfAssessment",
    "CsfAssessmentStatus",
    "CsfDimensionScore",
    "CsfEvidenceBasis",
    "CsfGapAction",
    "Deliverable",
    "EmailToken",
    "EmailTokenPurpose",
    "EvidenceLink",
    "EvidenceLinkStatus",
    "EvidenceTargetKind",
    "FindingsReport",
    "FindingsReportStatus",
    "IntegrationRun",
    "LLMCall",
    "LLMCallMode",
    "LLMCallStatus",
    "LlmCredential",
    "Message",
    "Notification",
    "Question",
    "Recommendation",
    "RecommendationEffectStatus",
    "RecommendationKind",
    "RecommendationScope",
    "RecommendationStatus",
    "RiskEntry",
    "RiskRegister",
    "Service",
    "ServiceKind",
    "ServiceRequest",
    "ServiceStatus",
    "ServiceType",
    "User",
    "UserRole",
    "UserRecoveryCode",
    "ZtAnswer",
    "ZtAssessment",
    "ZtAssessmentStatus",
    "ZtFramework",
]
