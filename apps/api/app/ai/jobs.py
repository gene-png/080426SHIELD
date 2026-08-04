"""Built-in AI job definitions (Work Order C1).

Each job is a prompt + a parser. Registered on import. The score/map/synthesize
jobs return DRAFT SUGGESTIONS only; the deterministic math lives in the
per-domain pure functions and is never asked of the model.

The prompt bodies here are the engine-level skeletons. The service phases
(D2/D3/D4/E) refine the exact suggestion schema each job emits; the parser is
`parse_json` so any well-formed JSON suggestion object round-trips.
"""

from __future__ import annotations

from app.ai.engine import AIJob, parse_json, register_job

# --- Tech Debt extraction (moved behind the registry) ----------------------
# Keeps the historical "extract.capabilities" purpose so existing fixtures and
# llm_calls history stay stable.
from app.tech_debt.extract import (  # noqa: E402  (import after engine to avoid a cycle)
    PROMPT as _TECH_DEBT_PROMPT,
)
from app.tech_debt.extract import (
    PROMPT_VERSION as _TECH_DEBT_PROMPT_VERSION,
)
from app.tech_debt.extract import (
    _parse_response as _parse_tech_debt,
)

register_job(
    AIJob(
        name="tech_debt_extract",
        purpose="extract.capabilities",
        prompt=_TECH_DEBT_PROMPT,
        prompt_version=_TECH_DEBT_PROMPT_VERSION,
        parser=_parse_tech_debt,
    )
)


# --- CSF dimension-score suggestions ---------------------------------------
# The response schema below MUST match what routes/csf.py:run_ai parses: a top-
# level "scores" array whose rows are keyed by "tier" + "subcategory_code" and
# carry the five _DIM_FIELDS + "what_we_found". test_csf_ai_contract.py locks
# this contract so prompt and parser can never silently drift again (the audit
# find that motivated Sprint 3 T0: the prompt used to say {"subcategories":[{
# "code":...}]} while the parser read {"scores":[{"tier","subcategory_code"}]},
# so live mode discarded every schema-compliant response).
_CSF_SCORE_PROMPT = """You are assisting a Kentro analyst scoring a NIST CSF 2.0
assessment. The payload supplies the in-scope tier profiles ("tiers"), the in-
scope subcategory codes ("subcategories"), and the client's interview answers
("answers": a map of subcategory_code -> {maturity_tier, notes, has_evidence},
where has_evidence records whether supporting evidence was attached). SUGGEST a
draft only, grounded in those answers.

Score EACH in-scope (tier, subcategory) pair: for every subcategory code emit
one row per tier listed in "tiers". Each row carries the five dimension scores —
Governance, Policy and Process, Implementation, Monitoring and Measurement,
Continuous Improvement — each an integer 0, 1, or 2, plus a short "what we
found" narrative.

Do NOT compute totals, maturity levels, roll-ups, gaps, or priorities — those are
calculated by code. Return strictly JSON of the form:
{"scores": [{"tier": "high", "subcategory_code": "GV.OC-01", "governance": 0,
"policy": 0, "implementation": 0, "monitoring": 0, "improvement": 0,
"what_we_found": "..."}], "executive_summary": "..."}
"""

register_job(AIJob(name="csf_score", prompt=_CSF_SCORE_PROMPT, parser=parse_json))


# --- Zero Trust current/target suggestions ---------------------------------
_ZT_SCORE_PROMPT = """You are assisting a Kentro analyst scoring a Zero Trust
assessment for the stated framework (CISA ZTMM 2.0 or DoD ZTRA). From the
questionnaire answers and evidence, SUGGEST a draft only.

For each capability return a suggested current maturity level and a suggested
target level, on the framework's own scale (CISA 1-4, DoD 1-3), plus a per-pillar
"what we found" narrative. Do NOT compute pillar roll-ups, overall posture, gaps,
or the roadmap — code does that. Return strictly JSON:
{"capabilities": [{"code": "...", "current": int, "target": int}],
"pillar_narratives": {"<pillar_code>": "..."}, "executive_summary": "...",
"roadmap_summary": "..."}
"""

register_job(AIJob(name="zt_score", prompt=_ZT_SCORE_PROMPT, parser=parse_json))


# --- MITRE ATT&CK coverage suggestions -------------------------------------
_MITRE_MAP_PROMPT = """You are assisting a Kentro analyst mapping a security tool
inventory to the MITRE ATT&CK Enterprise matrix. From the capability list and any
context, SUGGEST a draft only.

For each technique you can speak to, suggest a coverage status (covered, partial,
gap, not_applicable) and which listed tools provide detection, prevention, and
response, plus a short rationale. You may ONLY name tools that appear in the
supplied capability list. Do NOT compute coverage percentages — code does that.
Return strictly JSON:
{"techniques": [{"technique_code": "T1003", "status": "covered|partial|gap|not_applicable",
"detection_tools": [...], "prevention_tools": [...], "response_tools": [...],
"rationale": "..."}], "executive_summary": "...", "top_blind_spots": [...]}
"""

register_job(AIJob(name="mitre_map", prompt=_MITRE_MAP_PROMPT, parser=parse_json))


# --- Risk Register synthesis -----------------------------------------------
_RISK_SYNTHESIZE_PROMPT = """You are assisting a Kentro analyst drafting a Risk
Register by synthesizing gaps and findings from a client's completed assessments
(ATT&CK coverage gaps plus CSF and/or Zero Trust gaps). SUGGEST a draft only.

For each finding draft one candidate entry: weakness title + description; SHIELD
axis (detection, prevention, or response); the linked ATT&CK techniques and
control references (you may ONLY cite techniques/controls that appear in the
supplied assessments); likelihood (Very Low..Very High); impact
(Negligible..Catastrophic); compensating controls; residual risk; and a
recommended action (remediate, mitigate, accept, transfer, avoid) with rationale.
Do NOT set the risk tier — code derives it from likelihood and impact. Return
strictly JSON:
{"entries": [{"title": "...", "description": "...", "axis": "detection|prevention|response",
"linked_techniques": [...], "linked_controls": [...], "likelihood": "...",
"impact": "...", "compensating_controls": "...", "residual_risk": "...",
"recommended_action": "...", "rationale": "...",
"source": "coverage_finding|questionnaire_response", "source_id": "..."}]}
"""

register_job(AIJob(name="risk_synthesize", prompt=_RISK_SYNTHESIZE_PROMPT, parser=parse_json))
