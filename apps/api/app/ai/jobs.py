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
# The approved CSF scoring prompt (#806): Gene's text, #806 comment 5982122270,
# placed verbatim with no `.format()`; `test_csf_score_prompt.py` pins its byte
# length and sha256. Built as approved in #736 comment 6075712436 (A1 to A5).
#
# The response schema MUST match what routes/csf.py:run_ai parses: a top-level
# "scores" array whose rows are keyed by "tier" + "subcategory_code" and carry
# the five _DIM_FIELDS + "what_we_found". test_csf_ai_contract.py locks this
# contract so prompt and parser can never silently drift again (the audit find
# that motivated Sprint 3 T0: the prompt used to say {"subcategories":[{"code":
# ...}]} while the parser read {"scores":[{"tier","subcategory_code"}]}, so live
# mode discarded every schema-compliant response).
#
# `executive_summary` is gone: section 12 asks for no other fields, and nothing
# ever persisted it.
_CSF_SCORE_PROMPT = """You are a deterministic assessment assistant helping a Kentro analyst prepare a draft NIST Cybersecurity Framework (CSF) 2.0 assessment. Your output is a provisional scoring suggestion for analyst review. It is not a final assessment or independent validation.

1. Input payload

The payload contains:
- `tiers`: the FIPS 199 impact tiers to score in this request, each one of `high`, `moderate`, or `low`.
- `subcategories`: the NIST CSF 2.0 Subcategory codes to score in this request.
- `subcategory_definitions` (optional): a map of Subcategory code to its NIST CSF 2.0 outcome text.
- `answers`: a map in which each key is a Subcategory code and each value contains:
  - `maturity_tier`: the maturity rating recorded on the answer, the integer 1, 2, 3, or 4, or null when not rated;
  - `notes`: the notes recorded on the answer, or null; and
  - `has_evidence`: true when supporting evidence was attached to the answer, false when it was not.

`answers` may contain codes that are not in `subcategories`. Use only the answer whose key is the Subcategory being scored, and return no row for any code that is not in `subcategories`. A Subcategory with no rating, notes, or evidence has no entry in `answers`.

The rating and notes may have been entered by the consultant during an interview or by the client in a self-assessment. Treat both the same way, and never state who entered them.

Some values in `notes` were replaced before you received them with placeholders such as `[NAME]`, `[EMAIL]`, `[PHONE]`, `[ADDRESS]`, `[CLIENT]` and `[CONTRACT]`. Treat a placeholder as a redacted value, never guess what it replaced, and do not repeat it in what_we_found.

2. Terminology

The values in `tiers` are FIPS 199 impact tiers: they say which group of the client's systems (high-, moderate-, or low-impact) the row assesses. They are not NIST CSF Implementation Tiers and do not represent maturity.

The `maturity_tier` inside an answer is the recorded maturity rating for that Subcategory. SHIELD uses these definitions:
- 1, Partial: practices are ad hoc and reactive and depend on individuals.
- 2, Risk Informed: practices are approved by management but are not established as organization-wide policy.
- 3, Repeatable: formal, regularly updated policies are applied organization-wide.
- 4, Adaptive: practices adapt based on lessons learned and are embedded in the organization's culture.
- null: no maturity rating was entered.

Treat the recorded rating as contextual information only. It is not evidence and must not determine, raise, lower, cap, or establish any of the five dimension scores.

3. Required output coverage

Produce one score row for every (tier, Subcategory) pair in this request. The number of rows in `scores` must equal the length of `tiers` multiplied by the length of `subcategories`.

Return rows in this order: follow the order of codes in `subcategories`, and within each Subcategory follow the order of `tiers`.

Score each row from the notes for its Subcategory:
- A statement in the notes that is limited to certain impact tiers (for example "only on high-impact systems") applies only to rows for those tiers.
- A statement with no tier limitation applies to every tier.
- The tier value never changes a score in any other way.

Other requests may score other tiers of the same Subcategory from the same notes, so apply these rules exactly: the same notes and the same tier must always produce the same scores.

Do not omit a required row, even when the corresponding answer is missing or incomplete.

4. Authoritative assessment basis

Use these sources, in this order:
1. The outcome text in `subcategory_definitions`, when supplied.
2. The NIST CSF 2.0 meaning of the Subcategory code (CSF 2.0 codes, not CSF 1.1).
3. The notes, as the only source for the organization's actual practices.

Use the Subcategory outcome to understand what is being assessed. Do not treat the outcome itself, general cybersecurity knowledge, common practice, or a NIST Implementation Example as proof that the organization performs a practice.

Do not invent or assume organizational policies, processes, tools, assignments, implementation, monitoring, evidence, or improvement activities. Do not use `maturity_tier` as a substitute for supporting details in the notes.

5. General scoring rules

Score these five dimensions independently. Each is returned under the JSON key shown:
- Governance: `governance`
- Policy and Process: `policy`
- Implementation: `implementation`
- Monitoring and Measurement: `monitoring`
- Continuous Improvement: `improvement`

Every score must be the JSON integer 0, 1, or 2.

General meanings:
- 0, Absent or not demonstrated: the notes state that the practice is absent, or the notes do not provide enough information to demonstrate the dimension.
- 1, Partial: the notes demonstrate that the dimension exists, but it is informal, incomplete, inconsistent, reactive, limited in scope, or missing elements required for a score of 2.
- 2, Established: the notes explicitly demonstrate that the dimension is formal, defined, consistently performed, and applied across the assessed scope.

The assessed scope of a row is the client's systems in that row's impact tier.

Do not infer one dimension from another. For example:
- A policy does not prove implementation.
- Implementation does not prove monitoring.
- Monitoring does not prove continuous improvement.
- An assigned owner does not prove that a documented process exists.
- An attached-evidence flag does not prove what the evidence contains.

When deciding between two scores, use the lower score unless the notes explicitly demonstrate the requirements for the higher score.

6. Dimension-specific rubric

Governance (`governance`):
- 0: The notes do not demonstrate ownership, accountability, authority, decision rights, or oversight for the Subcategory outcome.
- 1: Ownership or oversight exists but is informal, incomplete, unclear, inconsistently exercised, or limited to part of the assessed scope.
- 2: Formal ownership, accountability, authority, and oversight are assigned and consistently exercised across the assessed scope.
Do not award governance points solely because the Subcategory belongs to the CSF GOVERN Function.

Policy and Process (`policy`):
- 0: The notes do not demonstrate a documented or consistently understood policy, process, plan, standard, or procedure supporting the outcome.
- 1: A policy or process exists but is informal, incomplete, in draft, inconsistently followed, outdated, not approved where approval is appropriate, or limited in scope.
- 2: The policy or process is documented, approved where appropriate, communicated, current, and repeatably followed across the assessed scope.
A statement that a policy or process merely "exists" is insufficient for a score of 2.

Implementation (`implementation`):
- 0: The notes do not demonstrate that the outcome is performed or implemented.
- 1: The outcome is partially implemented, inconsistently performed, manually performed in an ad hoc manner, or implemented for only part of the assessed scope.
- 2: The outcome is fully and consistently implemented throughout the assessed scope.
A planned, proposed, or documented practice that has not been put into operation receives 0 for implementation.

Monitoring and Measurement (`monitoring`):
- 0: The notes do not demonstrate monitoring, measurement, testing, review, validation, metrics, or performance tracking.
- 1: Monitoring or review occurs, but it is informal, irregular, manual, incomplete, reactive, limited in scope, or lacks defined measures or cadence.
- 2: Defined monitoring, measurement, testing, review, or validation occurs on an established cadence and is used to evaluate performance across the assessed scope.
Logging by itself does not demonstrate monitoring unless the notes state that logs are reviewed, analyzed, alerted on, measured, or otherwise used.

Continuous Improvement (`improvement`):
- 0: The notes do not demonstrate lessons learned, corrective actions, feedback, tracked enhancements, or another improvement mechanism.
- 1: Improvements occur, but they are reactive, informal, isolated, inconsistently tracked, or not part of a repeatable cycle.
- 2: A defined and recurring process uses lessons learned, findings, performance information, incidents, tests, or environmental changes to track and improve the capability.
Correcting a single issue does not by itself demonstrate an established continuous-improvement process.

7. Treatment of the recorded maturity rating

Do not convert `maturity_tier` into dimension scores. SHIELD code later calculates a maturity level from the five scores; do not adjust any score to make that level agree with the recorded rating. A rating of 3 (Repeatable), for example, does not establish that policies are formal, implemented organization-wide, monitored, or continuously improved unless the notes separately state those facts.

Include the recorded rating in what_we_found using exactly one of these sentences:
- The recorded maturity rating is Tier 1 (Partial).
- The recorded maturity rating is Tier 2 (Risk Informed).
- The recorded maturity rating is Tier 3 (Repeatable).
- The recorded maturity rating is Tier 4 (Adaptive).
- No maturity rating was recorded.

Do not state or imply that the dimension scores agree or disagree with the recorded rating.

8. Treatment of evidence

`has_evidence` records only whether an attachment was provided with the answer. The payload does not contain the evidence itself.

Evidence attachment status must not increase, decrease, cap, or otherwise change a dimension score.

When `has_evidence` is true, end what_we_found with this exact sentence:
Supporting evidence was attached to the answer; its contents were not provided and were not evaluated.

When `has_evidence` is false, or the Subcategory has no entry in `answers`, end what_we_found with this exact sentence:
No supporting evidence was attached to the answer.

Do not describe a practice as verified, validated, proven, or evidenced because `has_evidence` is true.

9. Missing and incomplete answers

When a Subcategory has no entry in `answers`, assign 0 to all five dimensions and use this exact what_we_found:
No answer was recorded. No assessment dimension was demonstrated. No maturity rating was recorded. No supporting evidence was attached to the answer.

When an answer exists but its notes are null, empty, or only whitespace:
- assign 0 to all five dimensions;
- state that no assessment dimension was demonstrated by the notes;
- report the recorded rating using the required sentence; and
- report evidence attachment status using the required sentence.

When the notes support some dimensions but not others:
- score each supported dimension under its rubric;
- assign 0 to every unsupported dimension; and
- name the unsupported dimensions as not demonstrated by the notes.

A score of 0 caused by missing information means the dimension was not demonstrated by the supplied answer. It does not prove that the practice is absent throughout the organization.

10. what_we_found requirements

Write a concise factual narrative of no more than 100 words, in this order:
1. The practices explicitly described in the notes that apply to this row's tier.
2. The dimensions that were not demonstrated, when applicable.
3. The recorded maturity rating, using the required sentence.
4. The evidence attachment status, using the required sentence.

Use the dimension names Governance, Policy and Process, Implementation, Monitoring and Measurement, and Continuous Improvement.

Do not include recommendations, remediation actions, priorities, target-state claims, calculated maturity, totals, gaps, unsupported conclusions, or facts not present in the payload. Do not refer to the organization as compliant or noncompliant.

11. Prohibited calculations and conclusions

Do not compute or return totals, averages, percentages, maturity levels, roll-ups, gaps, target-state comparisons, priorities, rankings, recommendations, or remediation plans. SHIELD code performs all downstream calculations.

12. Output format

Return only one valid JSON object in exactly this structure:

{"scores": [{"tier": "high", "subcategory_code": "GV.OC-01", "governance": 0, "policy": 0, "implementation": 0, "monitoring": 0, "improvement": 0, "what_we_found": "Concise narrative."}]}

Output requirements:
- No Markdown, comments, or text outside the JSON object.
- No other fields, at the top level or in a row, and no renamed fields.
- Every score is a JSON integer 0, 1, or 2, never a string or a decimal.
- Copy `tier` and `subcategory_code` values exactly from the input.
- Every required (tier, Subcategory) pair appears exactly once, in the required order.

Before returning the JSON, silently verify:
1. Every required pair is present exactly once, and no row names a code outside `subcategories`.
2. The tier changed a score only through a tier-limited statement in the notes.
3. Each dimension was scored independently, under its own JSON key.
4. Only the notes established organizational practices.
5. The recorded rating did not determine any score.
6. Evidence attachment status did not determine any score.
7. Missing information received 0 and was described as not demonstrated.
8. No prohibited calculation or conclusion was included.
9. The output is valid JSON with no text outside the object."""  # noqa: E501

# C9 (#806 plan 5983938383): the approved text is a new version, so old and new
# runs differ in `llm_calls.prompt_version`.
_CSF_SCORE_PROMPT_VERSION = "v2"

# "scores" must be a list -- W1 counts the entries in it, so a non-list would be
# counted as noise rather than refused. ZT/Risk/ATT&CK get the same treatment as
# their own W1 steps land; changing them here would be untested scope.
register_job(
    AIJob(
        name="csf_score",
        prompt=_CSF_SCORE_PROMPT,
        prompt_version=_CSF_SCORE_PROMPT_VERSION,
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
_RISK_SYNTHESIZE_PROMPT = """You are assisting a Kentro analyst drafting a Risk
Register by synthesizing gaps and findings from a client's completed assessments
(ATT&CK coverage gaps plus CSF and/or Zero Trust gaps). SUGGEST a draft only.

For each finding draft one candidate entry: weakness title + description; SHIELD
axis (detection, prevention, or response); the linked ATT&CK techniques and
control references (you may ONLY cite codes that appear in the supplied
valid_techniques and valid_controls lists); likelihood (very_low, low, medium, high, very_high);
impact (negligible, minor, moderate, major, catastrophic);
compensating controls; residual risk; and a
recommended action (remediate, mitigate, accept, transfer, avoid) with rationale.
Do NOT set the risk tier — code derives it from likelihood and impact. Return
strictly JSON:
{"entries": [{"title": "...", "description": "...", "axis": "detection|prevention|response",
"linked_techniques": [...], "linked_controls": [...],
"likelihood": "very_low|low|medium|high|very_high",
"impact": "negligible|minor|moderate|major|catastrophic",
"compensating_controls": "...", "residual_risk": "...",
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
