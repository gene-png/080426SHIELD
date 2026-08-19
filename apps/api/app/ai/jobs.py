"""Built-in AI job definitions (Work Order C1).

Each job is a prompt + a parser. Registered on import. The score/map/synthesize
jobs return DRAFT SUGGESTIONS only; the deterministic math lives in the
per-domain pure functions and is never asked of the model.

The prompt bodies here are the engine-level skeletons. The service phases
(D2/D3/D4/E) refine the exact suggestion schema each job emits; the parser is
`parse_json_object_with_list(<key>)` for all four suggestion jobs, so a response
whose top level is not an object (issue #41) — or whose list key is not a list —
is refused rather than silently discarded.
"""

from __future__ import annotations

from app.ai.engine import (
    AIJob,
    # `parse_json_object` is deliberately NOT imported any more: all four
    # SUGGESTION jobs now carry a top-level shape guard, so reaching for the
    # unguarded parser here would be a step backwards rather than a default.
    #
    # NOT "every registered job" — `tech_debt_extract` has its own parser
    # (`tech_debt/extract.py`), which still does
    # `decoded.get("items", []) if isinstance(decoded, dict) else []` and still
    # iterates the keys of a non-list `items`. It is partly self-reporting,
    # because `reconcile_rows` then flags every uploaded row as excluded, so a
    # silent empty extraction is loud-ish rather than clean. Tracked separately;
    # do not read this import as covering it.
    parse_json_object_with_list,
    register_job,
)

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

# "scores" must be a list — W1 counts the entries in it, so a non-list would be
# counted as noise rather than refused. ZT/Risk/ATT&CK get the same treatment as
# their own W1 steps land; changing them here would be untested scope.
register_job(
    AIJob(
        name="csf_score",
        prompt=_CSF_SCORE_PROMPT,
        parser=parse_json_object_with_list("scores"),
    )
)


# --- Zero Trust current/target suggestions ---------------------------------
_ZT_SCORE_PROMPT = """You are assisting a Kentro analyst scoring a Zero Trust
assessment for the stated framework (CISA ZTMM 2.0 or DoD ZTRA). From the
questionnaire answers and evidence, SUGGEST a draft only.

For each capability return a suggested current maturity level and a suggested
target level, on the framework's own scale (CISA 1-4, DoD 1-3). Do NOT compute
pillar roll-ups, overall posture, gaps, or the roadmap — code does that. Return
strictly JSON:
{"capabilities": [{"code": "...", "current": int, "target": int}]}
"""

# `pillar_narratives`, `executive_summary` and `roadmap_summary` were removed
# from this prompt (issue #64). All three were parsed and returned, and NOTHING
# consumed them: no column on `ZtAssessment`, no migration, no reader in
# `zt/exporters.py`, and no reference anywhere in `apps/web/src` beyond the type
# declaration itself. The run paid output tokens for them on every call.
#
# They were briefly scoped into W1's suggestion accounting instead, on the
# strength of D-045's claim that ZT persisted them — which was false, and is
# corrected there. Counting them was the wrong fix: these values were discarded
# unconditionally, valid or not, so a "dropped narrative" number would report
# loss where a validation failure lost nothing that was not already being thrown
# away by design. A counter that implies the harm of a real dropped score, for
# content with no consumer, trains the reader to discount the counters that
# matter (the #31 constraint). Re-adding them is the LAST step of building a
# consumer, not the first.

# "capabilities" must be a list — W1 counts the entries in it, so a non-list
# would be counted as noise rather than refused (matching csf_score above).
register_job(
    AIJob(
        name="zt_score",
        prompt=_ZT_SCORE_PROMPT,
        parser=parse_json_object_with_list("capabilities"),
    )
)


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

# "techniques" must be a list. A scalar collapsed to `[]` via the route's
# `or []`, and a DICT is truthy so it iterated its KEYS — strings, discarded one
# by one by the per-entry `isinstance(t, dict)` filter. Both contributed nothing
# with no error, indistinguishable from a model that had nothing to say.
#
# SCOPE, stated precisely because the first draft of this comment overstated it:
# mitre_map is BATCHED, and `attack.py` counts a failed batch and continues,
# raising only when EVERY batch failed. So this guard turns a silently-empty
# batch into a counted one — it does not fail the run. One bad batch of 26 still
# returns 200 with `batches_failed=1`, and that field is not rendered anywhere
# in the web app (plan finding F7). The guard improves the ledger, not yet what
# the consultant sees.
register_job(
    AIJob(
        name="mitre_map",
        prompt=_MITRE_MAP_PROMPT,
        parser=parse_json_object_with_list("techniques"),
    )
)


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

register_job(
    # "entries" must be a list.
    #
    # CORRECTED from the first draft of this comment, which claimed a scalar
    # produced a bare 500. It does not: the batching loop reads
    # `(data.get("entries") or [])`, so `0` and `""` collapse to an empty list
    # and generate an EMPTY REGISTER reporting success — the silent shape, not
    # the loud one. A dict is truthy and iterates its keys, same outcome. Only a
    # truthy non-iterable reaches a TypeError, and that one escapes the
    # per-future try as an untyped 500.
    #
    # Both failure modes are wrong in different directions; the guard replaces
    # them with one typed 502.
    AIJob(
        name="risk_synthesize",
        prompt=_RISK_SYNTHESIZE_PROMPT,
        parser=parse_json_object_with_list("entries"),
    )
)
