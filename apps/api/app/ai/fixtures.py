"""Deterministic runtime AI fixtures for fixture mode (T6b / DECISIONS D-017).

Fixture mode (``SHIELD_LLM_MODE=fixture``) makes the demo/dev stack fully
exercisable OFFLINE: every AI "Run AI" returns a deterministic, demo-plausible
canned suggestion instead of calling a live provider. These fixtures only DRAFT
values (coverage statuses, maturity stages, dimension scores, risk links) - the
deterministic engines still compute every total, tier, roll-up and roadmap, so
"AI suggests, code computes" (Master Spec, AI Prompt) is preserved.

Each fixture is payload-aware: it reads the redacted job payload (technique
codes, capability codes, tiers/subcategories, findings) so the drafted
suggestions line up with the live assessment and Run AI actually changes rows.

All six job purposes are registered:
  mitre_map            -> ATT&CK coverage status + validated D/P/R tool citations
  zt_score             -> Zero Trust current/target (DoD respects the <=3 clamp)
  csf_score            -> NIST CSF five dimension scores (0-2) + narrative
  extract.capabilities -> Tech Debt capability extraction (with confidence_pct)
  risk_synthesize      -> Risk Register candidate entries (catalog-valid links)
  attack_scenario_delta -> the ATT&CK what-if's replacement credits

A missing fixture at runtime is an operator-actionable configuration error, not
a crash: ``RuntimeFixtureProvider`` raises ``MissingFixtureError``, mapped to
HTTP 503 (typed envelope, mirroring the T4 typed-error pattern) by the global
HTTPException handler - never a raw 500 ``KeyError``. Pytest keeps using the
bare ``FixtureProvider`` (loud ``KeyError`` on a forgotten registration), and
its dependency overrides take precedence over this runtime provider.
"""

from __future__ import annotations

import json
import re
from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.llm import FixtureProvider, LLMResponse
from app.tech_debt.extract import CATEGORIES as TECH_DEBT_CATEGORIES
from app.tech_debt.security_scope import NOT_IN_USE_PREFIX

# Job purposes (== FixtureProvider keys). Tech Debt keeps its historical
# "extract.capabilities" purpose for llm_calls + fixture compatibility.
PURPOSE_MITRE_MAP = "mitre_map"
PURPOSE_ZT_SCORE = "zt_score"
PURPOSE_CSF_SCORE = "csf_score"
PURPOSE_TECH_DEBT = "extract.capabilities"
PURPOSE_RISK_SYNTHESIZE = "risk_synthesize"
PURPOSE_ATTACK_SCENARIO_DELTA = "attack_scenario_delta"

ALL_PURPOSES: tuple[str, ...] = (
    PURPOSE_MITRE_MAP,
    PURPOSE_ZT_SCORE,
    PURPOSE_CSF_SCORE,
    PURPOSE_TECH_DEBT,
    PURPOSE_RISK_SYNTHESIZE,
    PURPOSE_ATTACK_SCENARIO_DELTA,
)


class MissingFixtureError(StarletteHTTPException):
    """Fixture-mode AI has no canned response registered for a job purpose.

    Mapped to HTTP 503 by the global HTTPException handler (typed envelope:
    ``reason=ai_fixture_unavailable``), so an operator sees an actionable
    configuration error instead of a raw 500 KeyError. Mirrors the T4
    typed-error pattern (a dict ``detail`` carrying ``reason`` + ``message``).
    """

    def __init__(self, purpose: str) -> None:
        super().__init__(
            status_code=503,
            detail={
                "reason": "ai_fixture_unavailable",
                "message": (
                    f"AI is running in fixture mode but no canned response is "
                    f"registered for '{purpose}'. Register it in app.ai.fixtures, "
                    f"or set SHIELD_LLM_MODE=live with a provider API key."
                ),
            },
        )


def _resp(body: dict[str, Any]) -> LLMResponse:
    """Serialize a fixture body to an LLMResponse with deterministic token counts."""
    content = json.dumps(body)
    # Deterministic, non-None token counts so the llm_calls audit row looks like
    # a real completion (fixture mode supplies them; the arithmetic is stable).
    return LLMResponse(
        content,
        input_tokens=max(1, len(str(body)) // 4),
        output_tokens=max(1, len(content) // 4),
    )


def _strs(value: object) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# mitre_map: ATT&CK coverage + Detection/Prevention/Response tool citations
# ---------------------------------------------------------------------------


def _capability_names(value: object) -> list[str]:
    """Tool names from either payload shape.

    `capability_list` carries enriched OBJECTS since plan part 1B — name, vendor,
    category, security_functions — and carried bare strings before it. Both are
    read here on purpose: a stored payload written before the change (an
    `llm_calls` row replayed, an older preview) is still a list of strings, and
    the C0 pattern says those must keep parsing.

    This is the single highest-risk line in that change. The previous version was
    `_strs(...)`, which keeps only `isinstance(v, str)` — so the moment objects
    arrived it returned `[]`, fixture mode cited zero tools, and fixture mode is
    what CI runs. Every existing assertion about tool citations would have gone
    red at once with the cause three files away.

    An entry with no usable name is dropped rather than becoming a citation of
    the empty string, which the resolver would otherwise count as unusable on
    every technique.
    """
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            name = entry
        elif isinstance(entry, dict):
            name = entry.get("name") or ""
        else:
            continue
        if isinstance(name, str) and name.strip():
            out.append(name)
    return out


#: The #806 prompt (#806 comment 5982555899) is what this is written from
#: (CLAUDE.md: author fixtures from the PROMPT, never from the parser):
#: - section 7: the status follows from the three arrays. `covered` has every
#:   required function, `partial` some, `gap` none; never `not_applicable`;
#: - section 6: a not-preventable technique has an empty `prevention_tools` and
#:   is covered on Detect and Respond;
#: - section 8: a partial row's one reason names its missing function, from the
#:   three the prompt offers; covered and gap rows carry null;
#: - section 11: only `techniques`, and only the seven row keys.
#: The cycle keeps the old fixture's statuses and length, so rows land where
#: they did; a status the arrays cannot support (no tools) is a gap instead.
_MITRE_STATUS_CYCLE = ("covered", "partial", "gap", "covered", "gap")
#: The partial reasons the prompt offers (section 8), in the order the fixture
#: cycles through them.
_MITRE_PARTIAL_REASONS = ("prevention_limited", "recovery_absent", "missing_control_category")


def _mitre_not_preventable(payload: dict[str, Any], code: str) -> bool:
    """`technique_details[code].not_preventable`, as the prompt reads it.

    C0: a payload stored before #806 (an `llm_calls` row replayed, an older
    preview) carries no `technique_details`, and the prompt it was sent with
    made no such distinction, so the code is judged preventable: all three
    functions required, the stricter reading."""
    details = payload.get("technique_details")
    entry = details.get(code) if isinstance(details, dict) else None
    return isinstance(entry, dict) and entry.get("not_preventable") is True


def _mitre_arrays(
    status: str, reason: str | None, not_preventable: bool, tools: list[str], i: int
) -> tuple[list[str], list[str], list[str]]:
    """Detection, prevention and response for a row the fixture means to be
    `status` with `reason`, built so the prompt's section 7 and 8 rules hold.
    One tool may fill more than one array (section 5)."""
    if status == "gap" or not tools:
        return [], [], []
    d = [tools[i % len(tools)]]
    r = [tools[(i + 1) % len(tools)]]
    p = [] if not_preventable else [tools[(i + 2) % len(tools)]]
    if status == "covered":
        return d, p, r
    if reason == "prevention_limited":
        return d, [], r
    if reason == "recovery_absent":
        return d, p, []
    # missing_control_category: missing Detect when not preventable, else
    # missing Prevent and Respond.
    return ([], [], r) if not_preventable else (d, [], [])


def _fixture_mitre_map(payload: dict[str, Any]) -> LLMResponse:
    # Section 11: one entry per code, in the order given.
    codes = _strs(payload.get("technique_codes"))
    tools = _capability_names(payload.get("capability_list"))
    techniques: list[dict[str, Any]] = []
    for i, code in enumerate(codes):
        status = _MITRE_STATUS_CYCLE[i % len(_MITRE_STATUS_CYCLE)] if tools else "gap"
        not_preventable = _mitre_not_preventable(payload, code)
        reason = None
        if status == "partial":
            reason = _MITRE_PARTIAL_REASONS[
                (i // len(_MITRE_STATUS_CYCLE)) % len(_MITRE_PARTIAL_REASONS)
            ]
            if reason == "prevention_limited" and not_preventable:
                # Section 8: prevention_limited needs prevention to be required.
                reason = "recovery_absent"
        # Cite tools ONLY from the supplied capability list; the route re-validates
        # every cited tool against the client's approved capability list.
        detection, prevention, response = _mitre_arrays(status, reason, not_preventable, tools, i)
        techniques.append(
            {
                "technique_code": code,
                "status": status,
                "reason_code": reason,
                "detection_tools": detection,
                "prevention_tools": prevention,
                "response_tools": response,
                "rationale": f"Fixture-mode draft coverage assessment for {code}.",
            }
        )
    return _resp({"techniques": techniques})


# ---------------------------------------------------------------------------
# zt_score: Zero Trust current + target per capability (framework-clamped)
# ---------------------------------------------------------------------------


def _fixture_zt_score(payload: dict[str, Any]) -> LLMResponse:
    framework = str(payload.get("framework") or "").lower()
    # CISA ZTMM 2.0 -> 1..4, DoD ZTRA -> 1..3. Emit values already inside the
    # framework's ladder so DoD suggestions respect the <=3 clamp (never a 4 the
    # route would silently drop).
    max_stage = 3 if "dod" in framework else 4
    codes = sorted(_strs(payload.get("capabilities")))
    capabilities: list[dict[str, Any]] = []
    for i, code in enumerate(codes):
        current = (i % 2) + 1  # 1 or 2 -> early-stage posture with room to grow
        target = min(current + 2, max_stage)  # DoD caps at 3, CISA at 4
        capabilities.append({"code": code, "current": current, "target": target})
    # Narrative keys were removed from `_ZT_SCORE_PROMPT` (issue #64) because
    # nothing consumed them, so the fixture must not emit them either — a
    # fixture richer than the prompt teaches the parser to expect fields a real
    # model will never be asked for.
    body: dict[str, Any] = {"capabilities": capabilities}
    return _resp(body)


# ---------------------------------------------------------------------------
# csf_score: NIST CSF five dimension scores (0-2) + narrative per (tier, subcat)
# ---------------------------------------------------------------------------

_CSF_DIMENSIONS = ("governance", "policy", "implementation", "monitoring", "improvement")


def _fixture_csf_score(payload: dict[str, Any]) -> LLMResponse:
    tiers = sorted(_strs(payload.get("tiers")))
    subcategories = sorted(_strs(payload.get("subcategories")))
    scores: list[dict[str, Any]] = []
    for ti, tier in enumerate(tiers):
        for si, code in enumerate(subcategories):
            base = (ti + si) % 3
            row: dict[str, Any] = {"tier": tier, "subcategory_code": code}
            for di, dim in enumerate(_CSF_DIMENSIONS):
                row[dim] = (base + di) % 3  # deterministic 0/1/2
            row["what_we_found"] = f"Fixture-mode finding for {code} in the {tier} tier profile."
            scores.append(row)
    body: dict[str, Any] = {
        "scores": scores,
        "executive_summary": ("Fixture-mode NIST CSF draft across the seeded working profile."),
    }
    return _resp(body)


# ---------------------------------------------------------------------------
# extract.capabilities: Tech Debt capability extraction from inventory rows
# ---------------------------------------------------------------------------
#
# Authored from Tech Debt prompt v3.2's TEXT (issue 806, comment 5983838515; for
# #806), never from the parser. What the prompt says, and so what this does:
#   - section 1: skip a total line and a retired row that states no cost; keep an
#     inactive, planned or no-longer-used row that still carries a cost, its
#     status in `notes` and confidence 60;
#   - section 6: `category` is one of the closed list or null, with the actual
#     category in `notes` when it is known but not on the list;
#   - section 6, `notes`: plain facts about the row, never an instruction to a
#     reviewer ("confirm before approving" was one, and is gone);
#   - section 7 (for #845): a security tool the row describes as planned, not
#     yet deployed, inactive or no longer used is `security_related: false` with
#     no functions, its note beginning with exactly the not-in-use prefix;
#   - section 8: confidence is 100, 90 or 60, and every 60 has a note.
#   - section 10: no rows (missing, not an array, or empty) is {"items":[]}.
# Costs and licence counts stay null, as before: the fixture drafts the
# classification, and offline demo totals are not its job.

_TECH_DEBT_NAME_KEYS = ("name", "product", "tool", "capability", "vendor_product", "item")


# Deterministic per-row function so offline output is stable across runs.
_TECH_DEBT_FUNCTION_CYCLE = ("prevent", "detect", "respond")

#: v3.2 section 1, "a total, subtotal, or summary line that adds up other rows".
_TECH_DEBT_TOTAL_LINE = re.compile(r"^\s*(sub|grand\s+)?totals?\b", re.IGNORECASE)
#: v3.2 section 1, exclusion 6: "retired, removed, or decommissioned".
_TECH_DEBT_RETIRED_WORDS = ("retired", "removed", "decommissioned")
#: v3.2 sections 1 and 7: "inactive, planned, and no-longer-used", "not yet
#: deployed". Retired-with-a-cost rows are kept and read as no longer used.
_TECH_DEBT_NOT_IN_USE_WORDS = ("not yet deployed", "no longer used", "inactive", "planned")
#: v3.2 section 6, `annual_cost_usd` and `license_count`: a header naming cost,
#: price, spend or fees, or a license, seat or user count.
_TECH_DEBT_COST_HEADER_WORDS = ("cost", "price", "spend", "fee", "licen", "seat")


def _row_cells(row: dict[str, Any]) -> list[str]:
    return [v.strip() for v in row.values() if isinstance(v, str) and v.strip()]


def _lifecycle(row: dict[str, Any]) -> tuple[str, str] | None:
    """(word, the cell as the row states it) for the first lifecycle word any
    cell carries, retired words first, or None."""
    for word in (*_TECH_DEBT_RETIRED_WORDS, *_TECH_DEBT_NOT_IN_USE_WORDS):
        for cell in _row_cells(row):
            if word in cell.lower():
                return word, cell.rstrip(".")
    return None


def _states_a_cost(row: dict[str, Any]) -> bool:
    return any(
        isinstance(k, str)
        and any(w in k.lower() for w in _TECH_DEBT_COST_HEADER_WORDS)
        and str(v).strip() != ""
        for k, v in row.items()
        if v is not None
    )


def _v32_category(row: dict[str, Any]) -> tuple[str | None, str | None]:
    """(category, note): the row's own category when it names a value on v3.2's
    list (whole, or the part before its "/", so "EDR" is "EDR/XDR"); otherwise
    null, with the actual category stated in a note."""
    stated = row.get("category")
    if not isinstance(stated, str) or not stated.strip():
        return None, None
    word = stated.strip().lower()
    for listed in TECH_DEBT_CATEGORIES:
        if word in (listed.lower(), listed.split("/")[0].lower()):
            return listed, None
    return None, f"Category: {stated.strip()}."


def _fixture_tech_debt(payload: dict[str, Any]) -> LLMResponse:
    rows = payload.get("rows")
    if not (isinstance(rows, list) and rows):
        # v3.2 section 10: "If `rows` is missing, is not an array, or contains no
        # identifiable capabilities, return exactly: {"items":[]}". This branch
        # used to invent three costed demo capabilities (advisor ruling F3,
        # issue 736 comment 6069328834).
        return _resp({"items": []})
    items: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        row = row if isinstance(row, dict) else {}
        name: str | None = None
        for key in _TECH_DEBT_NAME_KEYS:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                name = value.strip()
                break
        if name is None or _TECH_DEBT_TOTAL_LINE.match(name):
            # No usable name in any known column (a note, a blank, a section
            # header), or a totals line: v3.2 section 1 excludes exactly these,
            # so the fixture does too. Skipping keeps `excluded_rows` and its
            # review queue reachable offline; an unreachable review surface is
            # an untested one.
            continue
        lifecycle = _lifecycle(row)
        retired = lifecycle is not None and lifecycle[0] in _TECH_DEBT_RETIRED_WORDS
        if retired and not _states_a_cost(row):
            # v3.2 section 1, exclusion 6: retired AND no current cost.
            continue

        vendor = row.get("vendor")
        vendor = vendor.strip() if isinstance(vendor, str) and vendor.strip() else None
        # Cycle the security call so offline mode exercises BOTH branches;
        # otherwise the sign-off queue could never appear in a demo or an e2e
        # run.
        security_tool = i % 4 != 3
        not_in_use = lifecycle is not None and security_tool
        security_related = security_tool and not not_in_use
        category, category_note = _v32_category(row)

        notes: list[str] = []
        if lifecycle is not None:
            # v3.2 sections 1 and 7: the status as the row states it, and for a
            # security tool, a note beginning with exactly the prefix.
            status = lifecycle[1]
            notes.append(f"{NOT_IN_USE_PREFIX} {status}." if not_in_use else f"Status: {status}.")
            confidence = 60
        elif i % 4 == 0:
            # One row in four needs review, with the reason v3.2's own example
            # gives, so the low-confidence flag is reachable offline (s4).
            notes.append("Edition not stated.")
            confidence = 60
        else:
            # v3.2 section 8: 100 when the row states name and vendor.
            confidence = 100 if vendor else 90
        if category_note:
            notes.append(category_note)

        items.append(
            {
                "name": name,
                "vendor": vendor,
                "category": category,
                "function": (
                    "Security capability (fixture-mode draft)."
                    if security_tool
                    else "Business capability (fixture-mode draft)."
                ),
                "annual_cost_usd": None,
                "license_count": None,
                "notes": " ".join(notes) or None,
                "confidence_pct": confidence,
                "source_row_index": i,
                "security_related": security_related,
                "security_functions": (
                    [_TECH_DEBT_FUNCTION_CYCLE[i % len(_TECH_DEBT_FUNCTION_CYCLE)]]
                    if security_related
                    else []
                ),
            }
        )
    return _resp({"items": items})


# ---------------------------------------------------------------------------
# risk_synthesize: candidate Risk Register entries from assessment findings
# ---------------------------------------------------------------------------

_RISK_LIKELIHOOD_CYCLE = ("low", "medium", "high", "medium", "very_high")
_RISK_IMPACT_CYCLE = ("moderate", "major", "catastrophic", "minor", "major")
_RISK_AXIS_CYCLE = ("detection", "prevention", "response")
_RISK_ACTION_CYCLE = ("remediate", "mitigate", "transfer", "accept", "avoid")
#: The approved prompt's exact sentence for "no compensating control".
_RISK_NO_CONTROLS = "None identified in the supplied information."
#: The approved prompt's axis order, which `other_axes` follows.
_RISK_AXIS_ORDER = ("detection", "prevention", "response")


def _risk_evidenced_controls(evidence: Any) -> str:
    """The approved prompt's COMPENSATING CONTROLS rule, for an ATT&CK finding:
    only confirmed tools in an `in_place` function, named, with what they do.
    Never an invented control (#806 record, item 4). CSF and Zero Trust
    evidence names no control the fixture can read, so it gets the exact
    "none" sentence, as does a finding with no function in place."""
    if not isinstance(evidence, dict):
        return _RISK_NO_CONTROLS
    named = [
        f"{tool} provides {function} for this technique."
        for function in _RISK_AXIS_ORDER
        if isinstance(evidence.get(function), dict)
        and evidence[function].get("state") == "in_place"
        for tool in _strs(evidence[function].get("tools"))
    ]
    return " ".join(named) if named else _RISK_NO_CONTROLS


def _risk_other_axes(evidence: Any, axis: str) -> list[str]:
    """The approved prompt's `other_axes` rule, for an ATT&CK finding: each
    function in `missing_functions` is directly affected, so every one but the
    primary `axis`, in the prompt's order. Empty for CSF and Zero Trust, whose
    evidence names no function."""
    missing = _strs(evidence.get("missing_functions")) if isinstance(evidence, dict) else []
    return [a for a in _RISK_AXIS_ORDER if a in missing and a != axis]


def _fixture_risk_synthesize(payload: dict[str, Any]) -> LLMResponse:
    findings = payload.get("findings")
    valid_techniques = set(_strs(payload.get("valid_techniques")))
    valid_controls = set(_strs(payload.get("valid_controls")))
    entries: list[dict[str, Any]] = []
    # #474 E, ruling 6: `findings` is an object keyed by `source_id`, and the
    # prompt says to copy the key into the entry as `source_id`.
    if isinstance(findings, dict):
        for i, (source_id, finding) in enumerate(findings.items()):
            if not isinstance(finding, dict):
                continue
            kind = finding.get("kind")
            # Only cite codes present in the supplied
            # valid_techniques / valid_controls lists, which since #403 are the
            # codes the client's assessments SCORED -- not the catalogs, and not
            # every row the assessment holds. The route re-validates against the
            # same lists.
            #
            # SO FIXTURE MODE CANNOT PRODUCE A DROP AT ALL: this filters its own
            # output by the very lists `_resolve_links` will check it against, so
            # it agrees with the validator by construction. Every drop counter,
            # and the #403 disclosure that explains them, is unreachable from a
            # fixture-mode run and needs a synthetic unit test or a live call --
            # which is why the tests for them build the response by hand rather
            # than going through this function.
            linked_techniques = (
                [source_id] if kind == "attack" and source_id in valid_techniques else []
            )
            linked_controls = (
                [source_id] if kind in ("csf", "zt") and source_id in valid_controls else []
            )
            label = finding.get("label") or source_id or f"finding {i + 1}"
            evidence = finding.get("evidence")
            axis = _RISK_AXIS_CYCLE[i % len(_RISK_AXIS_CYCLE)]
            entries.append(
                {
                    "title": f"Gap: {label}",
                    "description": ("Fixture-mode candidate risk entry drafted from the finding."),
                    "axis": axis,
                    "other_axes": _risk_other_axes(evidence, axis),
                    "linked_techniques": linked_techniques,
                    "linked_controls": linked_controls,
                    "likelihood": _RISK_LIKELIHOOD_CYCLE[i % len(_RISK_LIKELIHOOD_CYCLE)],
                    "impact": _RISK_IMPACT_CYCLE[i % len(_RISK_IMPACT_CYCLE)],
                    "compensating_controls": _risk_evidenced_controls(evidence),
                    "residual_risk": "Elevated until remediated.",
                    "recommended_action": _RISK_ACTION_CYCLE[i % len(_RISK_ACTION_CYCLE)],
                    "rationale": "Fixture-mode rationale; validate against evidence.",
                    "source": finding.get("source") or "coverage_finding",
                    "source_id": source_id,
                }
            )
    return _resp({"entries": entries})


# ---------------------------------------------------------------------------
# attack_scenario_delta: the ATT&CK what-if's replacement credits (#802)
# ---------------------------------------------------------------------------

#: The prompt's function names, and the `security_functions` value that
#: declares each (the prompt: "`detect` for `detection`, ...").
_SCENARIO_FUNCTIONS = (
    ("detection", "detect"),
    ("prevention", "prevent"),
    ("response", "respond"),
)


def _tool_entries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [t for t in value if isinstance(t, dict) and isinstance(t.get("name"), str)]


def _tool_entries_by_code(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [r for r in value if isinstance(r, dict) and isinstance(r.get("technique_code"), str)]


def _declares(tool: dict[str, Any], short: str) -> bool:
    return short in _strs(tool.get("security_functions"))


def _fixture_attack_scenario_delta(payload: dict[str, Any]) -> LLMResponse:
    """Authored from the prompt's contract, not from `parse_delta`: for each of
    `technique_codes`, a function in its `lost_functions` goes to the first
    tool in `available_tools` that declares it and is not already listed for it
    in `frozen_rows`; a function only in its `open_functions` goes to the first
    tool in `added_tools` that declares it. One row per (technique, tool)."""
    available = _tool_entries(payload.get("available_tools"))
    added = _tool_entries(payload.get("added_tools"))
    frozen = {r.get("technique_code"): r for r in _tool_entries_by_code(payload.get("frozen_rows"))}
    lost = payload.get("lost_functions") if isinstance(payload.get("lost_functions"), dict) else {}
    opened = (
        payload.get("open_functions") if isinstance(payload.get("open_functions"), dict) else {}
    )
    rows: list[dict[str, Any]] = []
    for code in _strs(payload.get("technique_codes")):
        credits: dict[str, set[str]] = {}
        listed = frozen.get(code, {})
        lost_here = _strs(lost.get(code))
        for function, short in _SCENARIO_FUNCTIONS:
            if function in lost_here:
                pool = [
                    t for t in available if t["name"] not in _strs(listed.get(f"{function}_tools"))
                ]
            elif function in _strs(opened.get(code)):
                pool = added
            else:
                continue
            tool = next((t["name"] for t in pool if _declares(t, short)), None)
            if tool is not None:
                credits.setdefault(tool, set()).add(function)
        for tool, functions in credits.items():
            rows.append(
                {
                    "technique_code": code,
                    "tool": tool,
                    **{f: f in functions for f, _ in _SCENARIO_FUNCTIONS},
                    "rationale": f"Fixture-mode draft replacement credit for {code}.",
                }
            )
    return _resp({"rows": rows})


# ---------------------------------------------------------------------------
# Runtime provider
# ---------------------------------------------------------------------------

_RUNTIME_FIXTURES: dict[str, Any] = {
    PURPOSE_MITRE_MAP: _fixture_mitre_map,
    PURPOSE_ZT_SCORE: _fixture_zt_score,
    PURPOSE_CSF_SCORE: _fixture_csf_score,
    PURPOSE_TECH_DEBT: _fixture_tech_debt,
    PURPOSE_RISK_SYNTHESIZE: _fixture_risk_synthesize,
    PURPOSE_ATTACK_SCENARIO_DELTA: _fixture_attack_scenario_delta,
}


class RuntimeFixtureProvider(FixtureProvider):
    """FixtureProvider preloaded with the runtime fixtures for every job purpose.

    Unlike the bare ``FixtureProvider`` (which pytest uses and which raises a
    loud ``KeyError`` on a forgotten registration), a missing purpose here is a
    runtime configuration error surfaced as HTTP 503 via ``MissingFixtureError``.
    """

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        purpose = payload.get("__purpose__") or "default"
        if purpose not in self._fixtures and "default" not in self._fixtures:
            raise MissingFixtureError(purpose)
        return super().complete(prompt, payload)


def build_runtime_provider(model: str = "fixture-model-1") -> RuntimeFixtureProvider:
    """Build a fixture provider with a deterministic response for every purpose."""
    provider = RuntimeFixtureProvider(model=model)
    for purpose, fn in _RUNTIME_FIXTURES.items():
        provider.register(purpose, fn)
    return provider
