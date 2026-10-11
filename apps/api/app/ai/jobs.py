"""Built-in AI job definitions (Work Order C1).

Each job is a prompt + a parser. Registered on import. The score/map/synthesize
jobs return DRAFT SUGGESTIONS only; the deterministic math lives in the
per-domain pure functions and is never asked of the model.

The prompt bodies here are the engine-level skeletons. The service phases
(D2/D3/D4/E) refine the exact suggestion schema each job emits; each of the four
suggestion jobs declares `top_level_key=<key>` and `AIJob` DERIVES its parser
from that declaration, so a response whose top level is not an object
(issue #41), whose list key is not a list, or which omits that key entirely
(#46) is refused rather than silently discarded.

The key is declared once rather than passed twice on purpose: a job that named
its key AND its parser could have the two disagree, which is #46 one level up.

`tech_debt_extract` keeps its own parser but calls the same guards (#77), so
the invariant now holds for every registered job.
"""

from __future__ import annotations

from app.ai.engine import (
    AIJob,
    # No parser is imported here any more. The four suggestion jobs declare
    # `top_level_key` and `AIJob` builds the parser from it, so there is nothing
    # to reach for -- neither the unguarded `parse_json_object` nor the guarded
    # `parse_json_object_with_list`. A job that cannot state its key has to
    # supply its own parser explicitly, and `tech_debt_extract` is the one that
    # does.
    #
    # This note previously carved out `tech_debt_extract` as the one exception.
    # #77 closed that: it keeps its own parser, because the per-item coercion
    # and the wrap-in-prose retry are not things the generic parser does, but it
    # now calls the SHARED guards (`require_json_object` / `require_list_at`)
    # rather than reimplementing the fallbacks they exist to replace. Sharing
    # the check instead of the whole parse is what made the invariant true
    # without removing tolerance a working provider depends on.
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
        top_level_key="scores",
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
        top_level_key="capabilities",
    )
)


# --- MITRE ATT&CK coverage suggestions -------------------------------------
#: Approved by Gene on 2026-10-04 (M1 to M3) and taken VERBATIM from #806
#: comment 5982555899: its fenced `text` block, extracted by script from the
#: live comment with the fence markers removed and nothing else changed (9982
#: ASCII bytes). Its sha256 is pinned by
#: `test_the_mitre_map_prompt_is_the_approved_text`; change it only through Gene.
#:
#: It is a plain string, not `.format()`ed from the vocabulary (the advisor's
#: ruling C5, #736 comment 5984022081): the JSON example stays exactly as
#: approved, and the codes it names are checked against `REASON_CODES` by
#: `test_attack_mitre_map_prompt_r3.py` instead. The run refuses what it forbids
#: in code as well: `not_applicable` (#841) and the four partial reasons it does
#: not offer (`routes/attack.py`, `_AI_FORBIDDEN_PARTIAL_REASONS`). It reads
#: `technique_details`, which `_run_mitre_map_batched` slices per batch.
_MITRE_MAP_PROMPT = (
    "You are a deterministic assessment assistant helping a Kentro analyst prepare a draft "
    "mapping of a client's software capability inventory to MITRE ATT&CK Enterprise. Your output "
    "is a provisional coverage suggestion for analyst review. It is not a validated detection "
    "assessment, control test, penetration test, or assurance conclusion.\n"
    "\n"
    "1. ATT&CK version and scope\n"
    "\n"
    "The techniques come from MITRE ATT&CK Enterprise Version 19.2. Assess exactly the "
    "techniques and sub-techniques listed in `technique_codes`: no more, no fewer. Do not add "
    "techniques from memory, and do not return a code that is not in `technique_codes`. Assess "
    "each listed code against its own ATT&CK behavior, platforms, detection opportunities, and "
    "mitigations; do not infer one code's status from a parent or a sub-technique.\n"
    "\n"
    "2. Input payload\n"
    "\n"
    "The payload contains:\n"
    "- `technique_codes`: the ATT&CK codes to assess in this request.\n"
    "- `technique_details`: a map of each code in `technique_codes` to its `name` and "
    "`not_preventable` (true when MITRE ATT&CK lists no preventive control for the technique).\n"
    "- `capability_list`: the client's tools, each with `name`, `vendor`, `category`, and "
    "`security_functions`.\n"
    "\n"
    "The payload contains no asset or platform inventory, no deployment, licensing, "
    "configuration, or integration details, and no analyst context. Do not assume any.\n"
    "\n"
    "Some values were replaced before you received them with placeholders such as `[CLIENT]` or "
    "`[NAME]`. When a tool's `name` contains a placeholder, copy the name exactly as shown, "
    "placeholder included.\n"
    "\n"
    "3. Permitted product knowledge\n"
    "\n"
    "You may use well-established product knowledge to identify the core security capabilities "
    "of a listed tool. Because the tool appears in the inventory, treat its well-established "
    "core capabilities as deployed.\n"
    "\n"
    "Do not assume the availability or use of optional add-ons, separately licensed modules, "
    "premium or preview features, custom integrations, custom detection rules, custom playbooks, "
    "configurations not included by default, support for operating systems, cloud environments, "
    "or SaaS environments the product does not support, estate-wide deployment, or features "
    "belonging to another product from the same vendor.\n"
    "\n"
    "A product's ability to generate generic logs does not establish technique-specific "
    "detection. Its ability to block generic activity does not establish technique-specific "
    "prevention. A ticketing, workflow, documentation, inventory, or GRC function does not "
    "establish technique-specific response.\n"
    "\n"
    "4. Exact tool names\n"
    "\n"
    "You may name only tools in `capability_list`, and every tool string must exactly match an "
    "entry's `name`, including capitalization, spacing, punctuation, abbreviations, and edition "
    "wording. Never use a vendor name, a category, a shortened, corrected, or normalized name, a "
    "module that is not separately listed, or a product absent from the list. If you cannot make "
    "an exact match, omit the tool.\n"
    "\n"
    "5. security_functions\n"
    "\n"
    "`security_functions` is a machine-generated classification (`prevent`, `detect`, `respond`, "
    "or a combination). Treat it as supporting evidence, not as a determination. A tool "
    "classified `detect` may be irrelevant to a given technique, and a tool classified `prevent` "
    "or `respond` may not prevent or respond to it. Include a tool under a function only when "
    "its core capability directly addresses the specific technique; omit it otherwise. A tool "
    "may appear in more than one array when its core capabilities independently satisfy each "
    "function for that technique.\n"
    "\n"
    "6. Functional coverage definitions\n"
    "\n"
    "Detection (`detection_tools`): the tool's core capability can directly identify, alert on, "
    "or meaningfully analyze behavior associated with the technique. This includes "
    "technique-specific behavioral detection; telemetry analysis that directly identifies the "
    "behavior; endpoint, identity, application, cloud, email, data, or network analytics; "
    "relevant anomaly detection; detection by an applicable signature or rule included in the "
    "core product; and scanning that identifies the technique's artifacts or conditions. It does "
    "not include raw log generation without relevant analysis, data storage without detection "
    "logic, dashboards without relevant analytics, generic visibility that does not identify the "
    "technique, a theoretical custom query, or a product that merely contains the affected "
    "technology.\n"
    "\n"
    "Prevention (`prevention_tools`): the tool's core capability can directly block, deny, "
    "restrict, neutralize, or materially reduce execution of the technique. This includes access "
    "denial, policy enforcement, execution blocking, application control, network or workload "
    "isolation before execution, exploit prevention, malware prevention, configuration "
    "enforcement, privilege restriction, filtering, and other controls that directly prevent or "
    "disrupt the technique. It does not include detection without blocking, reporting, "
    "post-event investigation, a policy document without enforcement, an unavailable optional "
    "feature, or a tool that could be configured to prevent the technique but lacks that core "
    "capability by default. When `not_preventable` is true, return an empty `prevention_tools`.\n"
    "\n"
    "Response (`response_tools`): the tool's core capability supports a concrete action relevant "
    "to containing, remediating, reversing, or recovering from the technique. This includes host "
    "isolation, account disablement, credential revocation or reset, session termination, "
    "process termination, file quarantine or removal, automated containment, orchestration of a "
    "relevant response action, rollback, restoration, and recovery from technique-related "
    "impact. It does not include alerting, logging, case tracking, documentation, or generic "
    "ticket creation alone, a backup tool where restoration is not relevant to the technique, or "
    "a response feature that requires an optional module or unconfirmed integration.\n"
    "\n"
    "Within each array, remove duplicates and order tools as they appear in `capability_list`.\n"
    "\n"
    "7. Status\n"
    "\n"
    "Decide the status from the three arrays, exactly as SHIELD computes it:\n"
    "- `covered`: every required function has at least one tool. The required functions are "
    "detection, prevention, and response, or only detection and response when `not_preventable` "
    "is true.\n"
    "- `partial`: at least one array is non-empty, but not every required function has a tool.\n"
    "- `gap`: all three arrays are empty. Never cite an irrelevant tool to avoid a gap, and "
    "never turn a gap into partial because a general security product exists.\n"
    "\n"
    "Never return `not_applicable`: it requires an asset inventory showing the technique's "
    "platforms are absent, and none is supplied. Never return any other status.\n"
    "\n"
    "A material limitation of a present function (reach, detection quality, evasive variants, "
    "scan intervals) does not change the status. State it in the rationale.\n"
    "\n"
    "8. Reason codes\n"
    "\n"
    "`covered` and `gap` take `reason_code: null`. A `partial` row takes exactly one code, and "
    "it names the function that makes the row partial:\n"
    "- `prevention_limited`: prevention is required (`not_preventable` is false) and is the only "
    "missing function.\n"
    "- `recovery_absent`: response is the only missing function, and recovery, rollback, "
    "restoration, or backup is materially relevant to the technique.\n"
    "- `missing_control_category`: any other partial row, including one missing detection, one "
    "missing response where recovery is not materially relevant, and one missing more than one "
    "required function. The rationale must name the missing functions.\n"
    "\n"
    "Do not use `reach_limited`, `evasive_variant_uncovered`, `periodic_not_continuous`, or "
    "`detection_weak`. Describe those limitations in the rationale instead.\n"
    "\n"
    "9. Rationale\n"
    "\n"
    "Write one rationale of no more than 60 words per technique. It must identify the basis for "
    "the status, state which defensive functions are present or absent, explain the reason code "
    "when there is one, name the missing functions when using `missing_control_category`, and "
    "state any material limitation of a present function. Do not include remediation or purchase "
    "recommendations, coverage percentages, invented configurations, evidence, or platform "
    "information, or tools absent from `capability_list`.\n"
    "\n"
    "10. Prohibited calculations\n"
    "\n"
    "Do not calculate or return coverage percentages, tactic-level percentages, aggregate or "
    "weighted scores, overall posture, risk scores, maturity levels, estimated effectiveness, "
    "priorities, roadmap actions, or remediation sequencing. SHIELD code performs those "
    "calculations.\n"
    "\n"
    "11. Output format\n"
    "\n"
    "Return only one valid JSON object in exactly this structure:\n"
    "\n"
    '{"techniques": [{"technique_code": "T1003.001", "status": "partial", "reason_code": '
    '"missing_control_category", "detection_tools": ["Exact capability name"], '
    '"prevention_tools": [], "response_tools": [], "rationale": "Concise evidence-based '
    'rationale."}]}\n'
    "\n"
    "Output requirements:\n"
    "- No Markdown, comments, or text outside the JSON object.\n"
    "- No other fields, at the top level or in a row, and no renamed fields.\n"
    "- Exactly one entry for every code in `technique_codes`, in the order given, and none for "
    "any other code.\n"
    "- `status` is `covered`, `partial`, or `gap`. `reason_code` is JSON null, never the string "
    '"null", except as section 8 requires.\n'
    "- Every tool string exactly matches a `name` in `capability_list`, with no duplicates "
    "within an array.\n"
    "\n"
    "Before returning the JSON, silently verify:\n"
    "1. Every code in `technique_codes` appears exactly once, in order, and no other code "
    "appears.\n"
    "2. Every tool name exactly matches a `capability_list` name, and every listed tool directly "
    "addresses that technique and function.\n"
    "3. Each status follows section 7 from the arrays, with `not_preventable` techniques judged "
    "on detection and response only and an empty `prevention_tools`.\n"
    "4. Covered and gap rows have a null reason code; every partial row has exactly one code, "
    "chosen by section 8 from the missing function.\n"
    "5. No row is `not_applicable`, and no irrelevant tool was cited to avoid a gap.\n"
    "6. No prohibited calculation was included, and the output is valid JSON with no text "
    "outside the object."
)

# "techniques" must be a list. A scalar collapsed to `[]` via the route's
# `or []`, and a DICT is truthy so it iterated its KEYS — strings, discarded one
# by one by the per-entry `isinstance(t, dict)` filter. Both contributed nothing
# with no error, indistinguishable from a model that had nothing to say.
#
# SCOPE, stated precisely because the first draft of this comment overstated it:
# mitre_map is BATCHED, and `attack.py` counts a failed batch and continues,
# raising only when EVERY batch failed. So this guard turns a silently-empty
# batch into a counted one — it does not fail the run. One bad batch of 26 still
# returns 200 with `batches_failed=1`. That field is now RENDERED (#115):
# `AttackCitationAccounting` raises a role=alert naming how many batches
# failed, that their techniques were not mapped, and the re-run trap. It
# was rendered nowhere when this comment was first written, which is why
# the guard below improved the ledger before anything showed it.
register_job(
    AIJob(
        name="mitre_map",
        prompt=_MITRE_MAP_PROMPT,
        # D1 (#736 comment 5986064696): the #806 prompt's runs are told apart
        # from the previous prompt's, which ran as the engine default "v1".
        prompt_version="v2",
        top_level_key="techniques",
    )
)


# --- Risk Register synthesis -----------------------------------------------
#: #806 / #474 E: the approved Risk prompt, ASSEMBLED from three #736 comments
#: by exact replacement: the record (5982727504), ruling 6's payload amendment
#: and ruling 4's provenance sentence (6086417594, both approved as written in
#: 6087027524). Pinned by sha256 and byte length in
#: `tests/unit/test_risk_prompt_approved.py`; change it only through Gene.
#:
#: The payload it describes is built by `routes/risk.py` (`_gather_findings`
#: for `evidence`, `_risk_batch_inputs` for the per-batch details maps). The
#: parser it is held to is `generate`'s entry loop: `other_axes` is validated
#: there and every element it cannot store is counted, never dropped silently
#: (C11(2), #806 5983938383).
_RISK_SYNTHESIZE_PROMPT = (
    "You are assisting a Kentro analyst in drafting a cybersecurity Risk Register from completed "
    "assessment findings. Produce suggestions for analyst review. Do not present any entry as an "
    "approved risk decision.\n"
    "\n"
    "INPUT\n"
    "\n"
    "The payload contains:\n"
    "- `findings`: an object keyed by each finding's `source_id` (an ATT&CK technique code, a "
    "CSF subcategory code, or a Zero Trust capability code). Each finding has `source` "
    "(`coverage_finding` for ATT&CK, `questionnaire_response` for CSF and Zero Trust), `kind` "
    '(`attack`, `csf`, or `zt`), `label` (for example "ATT&CK T1003: gap"), and `evidence`, '
    "which depends on `kind`:\n"
    "  - `attack`: `status` (`gap` or `partial`, as SHIELD computed it), `missing_functions` "
    "(each required function that SHIELD scores as not in place: `not_in_place` or "
    "`awaiting_review`; never one that is `cannot_be_prevented`), written `detection`, "
    "`prevention`, or `response`, and, for each of `detection`, `prevention`, `response`, an "
    "object with `state` (`in_place`, `not_in_place`, `awaiting_review`, or "
    "`cannot_be_prevented`) and `tools` (the confirmed tools providing it, possibly empty); plus "
    "`rationale` and `notes` from the assessment (each possibly null); "
    # Ruling #736 6105137014 (finding 1, option (a)), verbatim: v3.
    "`status_basis` is `computed` when SHIELD derived the status from the function states "
    "given, and `stored` when the status was recorded directly, with no function states; treat "
    "a stored status as given and do not infer missing functions from it.\n"
    "  - `csf`: `enterprise_level` (1 to 5), `target_level` (1 to 5), `tier_levels` (keyed by "
    "tier), `evidence_capped` (for each in-scope system tier, keyed by tier, true when that "
    "tier's level was lowered because evidence could not be produced), and `tier_notes` (keyed "
    "by tier, `rationale` and `what_we_found`, each possibly null);\n"
    "  - `zt`: `stage`, `target_stage` (the target the finding was measured against, never above "
    "the highest stage the capability defines), and `notes` (or null).\n"
    "- `technique_details`: for each ATT&CK technique in `findings`, its `name` and "
    "`not_preventable`.\n"
    "- `subcategory_definitions`: for each CSF subcategory in `findings`, its NIST CSF 2.0 "
    "outcome text.\n"
    "- `zt_capability_details`: for each Zero Trust capability in `findings`, its `framework`, "
    "`pillar` and `name`.\n"
    "- `valid_techniques` and `valid_controls`: the only codes you may cite.\n"
    "\n"
    "The evidence is the only source of client facts. None of it is independent verification: "
    "the ATT&CK rationale is an AI-drafted assessment; CSF levels are computed by SHIELD from "
    "dimension scores that may have been drafted by AI and edited by a consultant, and are "
    "capped where evidence was not recorded, and CSF `what_we_found` text may be AI-drafted; and "
    "Zero Trust stages may have been entered by the client in a self-assessment, set by a "
    "consultant, or drafted by AI, and Zero Trust notes may have been entered by the client. "
    "Never describe a practice as verified.\n"
    "\n"
    "States: `in_place` means at least one confirmed tool provides the function (confirmed means "
    "the tool's name matched the client's approved inventory, not that its deployment or "
    "effectiveness was tested); `not_in_place` means none does; `awaiting_review` means tools "
    "are cited but none is confirmed yet, and SHIELD scores the function as not in place; "
    "`cannot_be_prevented` means MITRE ATT&CK lists no preventive control for the technique, so "
    "prevention is not expected and is not a weakness. The evidence carries no client assets, "
    "exposure, threat activity, business context, or financial information unless the notes or "
    "rationale state them. Do not assume any. Some text may contain placeholders such as "
    "`[CLIENT]` or `[NAME]`; treat each as a redacted value and never guess what it replaced.\n"
    "\n"
    "ONE ENTRY PER FINDING\n"
    "\n"
    "Return exactly one entry for each finding. Do not combine findings, split one, or skip one. "
    "Copy the finding's `source`, and its key as `source_id`, into the entry exactly.\n"
    "\n"
    "RISK-SCENARIO REQUIREMENTS\n"
    "\n"
    "Each entry describes a risk scenario that connects:\n"
    "1. the weakness or control deficiency the finding identifies;\n"
    "2. a credible threat event or failure;\n"
    "3. the affected asset, function, environment, or scope, when identified; and\n"
    "4. a plausible adverse consequence.\n"
    "\n"
    "Write each description in this form:\n"
    '"Because [weakness], [threat event or failure] could affect [asset, function, or in-scope '
    'environment], resulting in [adverse consequence]."\n'
    "\n"
    "Use a concise, specific title. Do not treat a framework gap by itself as proof that a risk "
    "will occur. Do not invent client-specific assets, exposure, threat activity, incidents, "
    "control effectiveness, business consequences, regulatory obligations, or financial losses. "
    "You may use well-established cybersecurity knowledge to interpret an ATT&CK technique, a "
    "CSF subcategory outcome, or a Zero Trust capability from its evidence and to explain a "
    "credible general threat path; never present general knowledge as a confirmed fact about the "
    "client.\n"
    "\n"
    "SHIELD AXES\n"
    "\n"
    "`axis` is the one axis the scenario affects most directly, and `other_axes` lists every "
    "other axis the scenario also directly affects (empty when none). Each value is one of:\n"
    "- `detection`: the weakness limits discovering, analyzing, or confirming malicious "
    "activity.\n"
    "- `prevention`: the weakness limits stopping, restricting, or reducing the opportunity for "
    "malicious activity.\n"
    "- `response`: the weakness limits containment, eradication, recovery, coordination, or "
    "restoration.\n"
    "\n"
    "`other_axes` never repeats `axis`, has no duplicates, and is ordered detection, prevention, "
    "response. Do not include an axis based only on a remote or speculative consequence. For an "
    "ATT&CK finding, each function in `missing_functions` is directly affected; "
    "`cannot_be_prevented` never makes prevention an affected axis. For a weakness in "
    "governance, policy, or oversight, choose the axis whose outcome the weakness most directly "
    "undermines, and explain the choice in the rationale.\n"
    "\n"
    "REFERENCE RULES\n"
    "\n"
    "`linked_techniques` may contain only codes appearing exactly in `valid_techniques`, and "
    "`linked_controls` only codes appearing exactly in `valid_controls`. The lists are "
    "allowlists, not evidence that a code applies: include a code only when the finding directly "
    "supports the relationship. Always include the finding's own `source_id` when it appears in "
    "the matching list. Do not correct, normalize, expand, or infer codes, and do not add a "
    "parent technique because a sub-technique is present, or a sub-technique because its parent "
    "is present. If no supported code exists, return an empty array. Order codes as they appear "
    "in the allowlist.\n"
    "\n"
    "COMPENSATING CONTROLS\n"
    "\n"
    "Identify only compensating controls the evidence shows that reduce the likelihood or impact "
    "of this scenario: confirmed tools in an ATT&CK finding's `in_place` functions, and "
    "practices the notes or rationale describe as in operation. A function that is "
    "`awaiting_review` provides no compensating control. Copy tool names exactly as given, "
    "except that when a name contains a placeholder such as `[CLIENT]`, describe the tool by "
    "what it does instead of writing the placeholder. Name each and say what it does for this "
    "scenario. Do not infer a control from a product name alone beyond what the evidence states, "
    "treat a planned control as implemented, treat a control reference as proof of "
    "implementation, claim a control is effective unless the evidence supports it, or invent "
    "configurations, integrations, coverage, or deployment scope.\n"
    "\n"
    'If none are identified, return exactly "None identified in the supplied information."\n'
    "\n"
    "RESIDUAL LIKELIHOOD\n"
    "\n"
    "`likelihood` is the residual likelihood after considering only the compensating controls "
    "you identified. Use a timeframe only if the evidence states one. Rate only when the "
    "evidence supports a defensible rating:\n"
    "- `very_low`: the threat path is technically possible but highly improbable because "
    "exposure is minimal and evidenced controls materially restrict the opportunity.\n"
    "- `low`: a credible threat path exists, but opportunity or exposure is limited and "
    "evidenced controls are generally effective.\n"
    "- `medium`: the event is plausible because a credible threat path and meaningful exposure "
    "exist, while controls are incomplete, inconsistent, or of uncertain effectiveness.\n"
    "- `high`: the event is likely because the threat is common or demonstrated, exposure is "
    "meaningful, and important controls are absent or ineffective.\n"
    "- `very_high`: the event is ongoing, repeatedly observed, actively exploited, or expected "
    "because direct exposure exists with little or no effective control.\n"
    "\n"
    "Do not base likelihood solely on the severity of the weakness or the potential impact.\n"
    "\n"
    "RESIDUAL IMPACT\n"
    "\n"
    "`impact` is the remaining harm if the scenario occurs, considering supported consequences "
    "to operations, mission, information, systems, individuals, legal or regulatory obligations, "
    "finances, and reputation:\n"
    "- `negligible`: no meaningful disruption, compromise, loss, or external consequence is "
    "supported.\n"
    "- `minor`: limited and localized harm that is readily contained and recovered from.\n"
    "- `moderate`: material but manageable harm requiring coordinated response or management "
    "attention.\n"
    "- `major`: severe harm, significant compromise, extended disruption, or substantial legal, "
    "financial, mission, or reputational consequences.\n"
    "- `catastrophic`: mission failure, life-safety consequences, national-security "
    "consequences, widespread or irrecoverable compromise, or organizationally existential harm.\n"
    "\n"
    "Do not assign impact based only on an ATT&CK technique's general severity. Client scope and "
    "consequences must support the rating.\n"
    "\n"
    "INSUFFICIENT INFORMATION\n"
    "\n"
    "When the supplied information cannot support a defensible likelihood or impact, return JSON "
    'null for that field, never a string such as "null", "unknown", or "N/A". The '
    "rationale must then state exactly what information is missing (for example exposure, "
    "affected scope, asset criticality, data sensitivity, threat activity, control "
    "effectiveness, or business consequences).\n"
    "\n"
    "RESIDUAL-RISK NARRATIVE\n"
    "\n"
    "`residual_risk` briefly explains what exposure or consequence remains after the "
    "compensating controls you identified. It is a narrative, not a risk tier. It follows the "
    "evidence, never the level number alone: the scenario is partially mitigated to the extent "
    "the evidence shows functions in place or practices in operation, and substantially "
    "unmitigated when it shows none.\n"
    "\n"
    "RECOMMENDED ACTION\n"
    "\n"
    "`recommended_action` is exactly one of:\n"
    "- `remediate`: correct or eliminate the underlying weakness so the identified threat path "
    "is closed.\n"
    "- `mitigate`: reduce likelihood or impact through additional controls when complete "
    "elimination is impractical or unnecessary.\n"
    "- `accept`: retain the residual risk because it appears tolerable relative to the supplied "
    "operational context, constraints, or risk criteria.\n"
    "- `transfer`: shift a defined financial or operational consequence through insurance, "
    "contract, or another party. Do not imply that accountability or all residual risk is "
    "transferred.\n"
    "- `avoid`: stop or materially change the activity that creates the exposure.\n"
    "\n"
    "Do not claim that acceptance, transfer, or avoidance has been authorized or implemented. "
    "Explain the recommendation in `rationale`, keeping facts from the findings separate from "
    "assumptions and stating any uncertainty.\n"
    "\n"
    "OUTPUT RULES\n"
    "\n"
    "- Do not calculate or return a risk tier, numeric risk score, priority, roadmap, or "
    "aggregate risk. SHIELD code derives the tier from likelihood and impact.\n"
    "- Do not cite any technique or control code outside the allowlists.\n"
    "- Return valid JSON only, with no Markdown, commentary, or text outside the JSON object, "
    "and no other fields.\n"
    "\n"
    "Return exactly this structure:\n"
    "\n"
    '{"entries": [{"title": "<concise weakness-based title>", "description": '
    '"<weakness, threat event, affected scope, and consequence>", "axis": '
    '"detection|prevention|response", "other_axes": ["detection|prevention|response"], '
    '"linked_techniques": ["<code from valid_techniques>"], "linked_controls": ["<code '
    'from valid_controls>"], "likelihood": "very_low|low|medium|high|very_high", '
    '"impact": "negligible|minor|moderate|major|catastrophic", "compensating_controls": '
    '"<evidenced controls, or None identified in the supplied information.>", '
    '"residual_risk": "<remaining risk>", "recommended_action": '
    '"remediate|mitigate|accept|transfer|avoid", "rationale": "<reason, assumptions, '
    'uncertainty, and any missing information>", "source": '
    '"coverage_finding|questionnaire_response", "source_id": "<the finding\'s '
    'source_id>"}]}\n'
    "\n"
    "Each of `axis`, `likelihood`, `impact`, and `recommended_action` takes exactly one of the "
    "values shown; `other_axes` takes values from the `axis` list. `likelihood` and `impact` may "
    "instead be JSON null, as INSUFFICIENT INFORMATION describes."
)

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
        # C9 (#806 5983938383): the approved prompt's runs are told apart from
        # the previous prompt's, which ran as the engine default "v1". v3: the
        # `status_basis` sentence, ruling #736 6105137014.
        prompt_version="v3",
        top_level_key="entries",
    )
)


# --- ATT&CK what-if (#802) ----------------------------------------------------
# The scoped re-assessment of removing (and adding) tools. Gene approved this
# text on 2026-10-04 as AMENDED in #802 comment 5982780636: the slice B revised
# draft (comment 5970337002) with two rules inserted after the `open_functions`
# rule, verbatim from that comment; they replace the F6 rule of comment
# 5971086623. It is the exact text of those comments; change it only through
# Gene. The rules on WHICH techniques, functions and tools may be named are
# enforced again by `attack/scenario.py::parse_delta` (the asked slice; only a
# lost or open function; only an ADDED tool for an open function, while an added
# tool may also fill a lost one; an added tool only for its declared functions;
# listed names), so those hold whatever the model returns. The rules on what COUNTS as
# detection, prevention or response are the model's judgement, and nothing in
# code checks them. The backslash after the opening quotes only joins the lines of this file:
# the text starts at "You are". The new rules' long lines are the approved
# text, unwrapped, hence the noqa on the closing quotes.
_ATTACK_SCENARIO_DELTA_PROMPT = """\
You are assisting a Kentro analyst testing a what-if for a client's ATT&CK
coverage: some tools may be REMOVED, and some tools the client does not have
may be ADDED. SUGGEST a draft only.

You are given, for a small set of techniques:
- `technique_codes`: the techniques to consider. Consider no others;
- `lost_functions`: for each technique, which of `detection`, `prevention`
  and `response` lost a tool to the removal (may be empty);
- `open_functions`: for each technique, which of `detection`, `prevention`
  and `response` are not in place today and could be filled by an ADDED tool
  (may be empty);
- `frozen_rows`: each technique's Detect, Prevent and Respond tool lists as
  the last confirmed assessment has them, with the removed tools already
  taken out;
- `removed_tools`: the tools being removed;
- `added_tools`: the tools being added, each with `name`, `vendor`,
  `category` and `security_functions`. They are not the client's; an
  analyst described them;
- `available_tools`: every tool the client keeps, and every added tool, each
  with `name`, `vendor`, `category` and `security_functions`.

For each technique in `technique_codes`:
- for the functions in its `lost_functions`, say whether any tool in
  `available_tools` that is not already listed for that function in
  `frozen_rows` provides it;
- for the functions in its `open_functions`, say whether any tool in
  `added_tools` provides it.
Tools already listed in `frozen_rows` keep their functions; do not repeat
them.

Rules:
- Only the techniques in `technique_codes`. For each, only the functions in
  its `lost_functions` or `open_functions`. Never set any other function to
  true.
- For a function that is only in `open_functions`, only a tool in
  `added_tools` may be named.
- An added tool may be credited only for the functions its `security_functions` lists (`detect` for `detection`, `prevent` for `prevention`, `respond` for `response`). For an added tool that list is a ceiling: never set any other function to true for it, in `lost_functions` or in `open_functions`.
- Credit a tool for a function only when it passes these tests for this technique. Judge a kept tool by its well-established core capability. Judge an added tool, which may not be a real product, by its `name`, `category`, and declared `security_functions`, and never refuse it only because you do not recognise it.
  - detection: it can directly identify, alert on, or meaningfully analyze the technique's behavior, including scanning that identifies the technique's artifacts. Raw log generation, storage, dashboards, generic visibility, a theoretical custom query, or merely containing the affected technology is not detection.
  - prevention: it can directly block, deny, restrict, neutralize, or materially reduce execution of the technique. Detection without blocking, reporting, a policy document, or a capability the tool lacks by default is not prevention.
  - response: it supports a concrete action to contain, remediate, reverse, or recover from the technique. Alerting, logging, case tracking, documentation, or generic tickets alone are not response; a backup tool counts only where restoration is relevant to the technique; a feature that needs an optional module or unconfirmed integration does not count.
  For a kept tool, do not assume optional add-ons, separately licensed modules, premium or preview features, custom integrations, custom detection rules, custom playbooks, configurations not included by default, support for operating systems or cloud or SaaS environments the product does not support, estate-wide deployment, or features of another product from the same vendor.
- Only tools in `available_tools`, named EXACTLY as their `name` field. Never
  name a removed tool, a vendor, a category, or a tool that is not listed.
- `security_functions` is evidence, not a verdict: a tool classified
  `detect` may still not address this technique; leave it out when it does
  not.
- Do not invent capability. If you are not confident a tool provides a
  function for this technique, leave that function false.
- Do NOT give a status, a score or a percentage -- code computes those.

Return strictly JSON, one row per (technique, tool) that provides at least
one asked function; a technique with no row has no replacement:
{"rows": [{"technique_code": "T1003", "tool": "<an available name>",
"detection": true, "prevention": false, "response": false,
"rationale": "<one sentence>"}]}
`detection`, `prevention` and `response` are JSON booleans.
"""  # noqa: E501

register_job(
    AIJob(
        name="attack_scenario_delta",
        prompt=_ATTACK_SCENARIO_DELTA_PROMPT,
        top_level_key="rows",
    )
)


# --- ATT&CK what-if chat box, the AI reading (#802) ----------------------------
# Approved plan: #802 comment 5981734020; the advisor at 16:40Z (comment
# 5982109105). The job is registered because its prompt is set below; with the
# constant None it would not be, and the chat box would be exactly the slice C
# matcher (`attack/scenario_intent.py::available`). The answer is an object with
# three keys and no list key to declare, so the job supplies its own parser,
# which refuses any other shape; `scenario_intent.read` then checks the names
# and the quotes, never trusting the text.
#: Approved by Gene as drafted (advisor, #802 comment 5982965933), taken
#: VERBATIM from #802 comment 5981734020, section 7: blockquote markers
#: removed, each bare ">" line a blank line, nothing else changed. Its
#: sha256 is pinned by `test_the_intent_prompt_is_the_approved_text`.
_ATTACK_SCENARIO_INTENT_PROMPT: str | None = (
    "You turn an administrator's description of a change to a client's security "
    "tools into a change list. You are given `description` (their words) and "
    "`tools` (the tools in place now).\n"
    "\n"
    'Answer with JSON only, exactly: `{"remove": [], "add": [], "unclear": []}`.\n'
    "\n"
    "- `remove`: tools the description says to take away, retire, stop using or "
    "replace. Copy each name EXACTLY as it appears in `tools`. Never name "
    "anything that is not in `tools`.\n"
    "- `add`: new tools the description says to bring in, named as the "
    "administrator wrote them. Never put a name from `tools` here.\n"
    "- `unclear`: each part of the description you cannot place in `remove` or "
    "`add`, quoted exactly as written.\n"
    "\n"
    "A swap or replacement is one removal and one addition. Text in square "
    "brackets, such as [CLIENT], stands for a name; copy it exactly. If you are "
    "not sure, put the words in `unclear`. Do not guess, explain, or add vendors, "
    "categories or anything else."
)

if _ATTACK_SCENARIO_INTENT_PROMPT is not None:
    from app.attack.scenario_intent import parse_answer

    register_job(
        AIJob(
            name="attack_scenario_intent",
            prompt=_ATTACK_SCENARIO_INTENT_PROMPT,
            parser=parse_answer,
        )
    )
