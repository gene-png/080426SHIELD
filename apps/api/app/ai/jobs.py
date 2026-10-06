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
from app.attack.coverage import (
    REASON_CODES,
    CoverageStatus,
    reason_codes_for,
    reason_definition,
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
_NEWLINE = chr(10)

_MITRE_MAP_PROMPT = """You are assisting a Kentro analyst mapping a security tool
inventory to the MITRE ATT&CK Enterprise matrix. From the capability list and any
context, SUGGEST a draft only.

For each technique you can speak to, suggest a coverage status (covered, partial,
gap, not_applicable) and which listed tools provide detection, prevention, and
response, plus a short rationale.

Give a `reason_code` for two statuses, and null for every other:
* partial: exactly one code naming what is missing from a defence that exists:
{partial_reasons}
* not_applicable: only {na_reasons}
  An argument about reach or a missing control is NOT not_applicable.

The test between partial, gap and not_applicable: is anything defending it at
all? If something does and a named category of control is missing, that is
partial with `missing_control_category`. If nothing does, that is gap -- never
not_applicable.

You may ONLY name tools that appear in the supplied capability list, and you must
cite the `name` field of an entry EXACTLY as written -- not the vendor, not the
category, and not a tidied-up version of the name. A citation that does not match
an entry's `name` is dropped, and the technique it was meant to support reads as
uncovered.

Each entry also carries `vendor`, `category`, and `security_functions` -- the
extractor's own prevent/detect/respond finding for that tool. Treat
`security_functions` as EVIDENCE, not as gospel: it is a machine classification
of a software inventory, so it is a strong hint about which of detection /
prevention / response a tool belongs under, and it is not a substitute for
judging whether the tool actually addresses THIS technique. A tool classified
`detect` may still be irrelevant to a given technique; say so by omitting it.

Do NOT compute coverage percentages — code does that.
Return strictly JSON:
{{"techniques": [{{"technique_code": "T1003", "status": "covered|partial|gap|not_applicable",
"reason_code": "<a code above, or null>",
"detection_tools": [...], "prevention_tools": [...], "response_tools": [...],
"rationale": "..."}}], "executive_summary": "...", "top_blind_spots": [...]}}
""".format(
    # Built FROM the vocabulary (#554), never restated -- both lists, Partial's
    # and N/A's -- so the prompt cannot offer a code the parser rejects or omit
    # one it accepts.
    partial_reasons=_NEWLINE.join(
        f"    - {r.code}: {r.definition}" for r in REASON_CODES if r.status == "partial"
    ),
    na_reasons="; ".join(
        f"`{code}` -- {reason_definition(code)}"
        for code in reason_codes_for(CoverageStatus.NOT_APPLICABLE)
    ),
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
