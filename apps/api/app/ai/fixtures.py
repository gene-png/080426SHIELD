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

All five job purposes are registered:
  mitre_map            -> ATT&CK coverage status + validated D/P/R tool citations
  zt_score             -> Zero Trust current/target (DoD respects the <=3 clamp)
  csf_score            -> NIST CSF five dimension scores (0-2) + narrative
  extract.capabilities -> Tech Debt capability extraction (with confidence_pct)
  risk_synthesize      -> Risk Register candidate entries (catalog-valid links)

A missing fixture at runtime is an operator-actionable configuration error, not
a crash: ``RuntimeFixtureProvider`` raises ``MissingFixtureError``, mapped to
HTTP 503 (typed envelope, mirroring the T4 typed-error pattern) by the global
HTTPException handler - never a raw 500 ``KeyError``. Pytest keeps using the
bare ``FixtureProvider`` (loud ``KeyError`` on a forgotten registration), and
its dependency overrides take precedence over this runtime provider.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.ai.llm import FixtureProvider, LLMResponse

# Job purposes (== FixtureProvider keys). Tech Debt keeps its historical
# "extract.capabilities" purpose for llm_calls + fixture compatibility.
PURPOSE_MITRE_MAP = "mitre_map"
PURPOSE_ZT_SCORE = "zt_score"
PURPOSE_CSF_SCORE = "csf_score"
PURPOSE_TECH_DEBT = "extract.capabilities"
PURPOSE_RISK_SYNTHESIZE = "risk_synthesize"

ALL_PURPOSES: tuple[str, ...] = (
    PURPOSE_MITRE_MAP,
    PURPOSE_ZT_SCORE,
    PURPOSE_CSF_SCORE,
    PURPOSE_TECH_DEBT,
    PURPOSE_RISK_SYNTHESIZE,
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

_MITRE_STATUS_CYCLE = ("covered", "partial", "gap", "covered", "not_applicable")


def _fixture_mitre_map(payload: dict[str, Any]) -> LLMResponse:
    codes = sorted(_strs(payload.get("technique_codes")))
    tools = _strs(payload.get("capability_list"))
    techniques: list[dict[str, Any]] = []
    for i, code in enumerate(codes):
        status = _MITRE_STATUS_CYCLE[i % len(_MITRE_STATUS_CYCLE)]
        detection: list[str] = []
        response: list[str] = []
        # Cite tools ONLY from the supplied capability list; the route re-validates
        # every cited tool against the client's approved capability list.
        if status in ("covered", "partial") and tools:
            detection = [tools[i % len(tools)]]
            if status == "covered" and len(tools) > 1:
                response = [tools[(i + 1) % len(tools)]]
        techniques.append(
            {
                "technique_code": code,
                "status": status,
                "detection_tools": detection,
                "prevention_tools": [],
                "response_tools": response,
                "rationale": f"Fixture-mode draft coverage assessment for {code}.",
            }
        )
    body: dict[str, Any] = {
        "techniques": techniques,
        "executive_summary": (
            "Fixture-mode ATT&CK coverage draft. Statuses and tool citations are "
            "deterministic placeholders for offline demo; confirm before release."
        ),
        "top_blind_spots": [t["technique_code"] for t in techniques if t["status"] == "gap"][:5],
    }
    return _resp(body)


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
    pillar_narratives: dict[str, str] = {}
    for i, code in enumerate(codes):
        current = (i % 2) + 1  # 1 or 2 -> early-stage posture with room to grow
        target = min(current + 2, max_stage)  # DoD caps at 3, CISA at 4
        capabilities.append({"code": code, "current": current, "target": target})
        pillar = code.split(".", 1)[0] if "." in code else code[:2]
        pillar_narratives.setdefault(pillar, f"Fixture-mode narrative for the {pillar} pillar.")
    body: dict[str, Any] = {
        "capabilities": capabilities,
        "pillar_narratives": pillar_narratives,
        "executive_summary": (
            "Fixture-mode Zero Trust draft: current posture is early-stage with "
            "clear near-term targets across the pillars."
        ),
        "roadmap_summary": (
            "Prioritize the identity and device pillars in the first two quarters."
        ),
    }
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

_DEMO_TECH_DEBT_ITEMS: list[dict[str, Any]] = [
    {
        "name": "CrowdStrike Falcon",
        "vendor": "CrowdStrike",
        "category": "EDR",
        "function": "Endpoint detection and response.",
        "annual_cost_usd": 120000,
        "license_count": 500,
        "notes": "Fixture-mode demo capability.",
        "confidence_pct": 90,
        "source_row_index": 0,
    },
    {
        "name": "Splunk Enterprise",
        "vendor": "Splunk",
        "category": "SIEM",
        "function": "Log aggregation and security analytics.",
        "annual_cost_usd": 200000,
        "license_count": None,
        "notes": "Fixture-mode demo capability.",
        "confidence_pct": 80,
        "source_row_index": 1,
    },
    {
        "name": "Okta",
        "vendor": "Okta",
        "category": "IAM",
        "function": "Identity and single sign-on.",
        "annual_cost_usd": 60000,
        "license_count": 500,
        "notes": "Fixture-mode demo capability.",
        "confidence_pct": 70,
        "source_row_index": 2,
    },
]

_TECH_DEBT_NAME_KEYS = ("name", "product", "tool", "capability", "vendor_product", "item")


def _fixture_tech_debt(payload: dict[str, Any]) -> LLMResponse:
    rows = payload.get("rows")
    if isinstance(rows, list) and rows:
        items: list[dict[str, Any]] = []
        for i, row in enumerate(rows):
            row = row if isinstance(row, dict) else {}
            name: str | None = None
            for key in _TECH_DEBT_NAME_KEYS:
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    name = value.strip()
                    break
            vendor = row.get("vendor")
            items.append(
                {
                    "name": name or f"Capability {i + 1}",
                    "vendor": vendor if isinstance(vendor, str) and vendor.strip() else None,
                    "category": None,
                    "function": "Security capability (fixture-mode draft).",
                    "annual_cost_usd": None,
                    "license_count": None,
                    "notes": "Drafted offline in fixture mode; confirm before approving.",
                    "confidence_pct": 60 + (i % 4) * 10,  # 60..90
                    "source_row_index": i,
                }
            )
    else:
        items = _DEMO_TECH_DEBT_ITEMS
    return _resp({"items": items})


# ---------------------------------------------------------------------------
# risk_synthesize: candidate Risk Register entries from assessment findings
# ---------------------------------------------------------------------------

_RISK_LIKELIHOOD_CYCLE = ("low", "medium", "high", "medium", "very_high")
_RISK_IMPACT_CYCLE = ("moderate", "major", "catastrophic", "minor", "major")
_RISK_AXIS_CYCLE = ("detection", "prevention", "response")
_RISK_ACTION_CYCLE = ("remediate", "mitigate", "transfer", "accept", "avoid")


def _fixture_risk_synthesize(payload: dict[str, Any]) -> LLMResponse:
    findings = payload.get("findings")
    valid_techniques = set(_strs(payload.get("valid_techniques")))
    valid_controls = set(_strs(payload.get("valid_controls")))
    entries: list[dict[str, Any]] = []
    if isinstance(findings, list):
        for i, finding in enumerate(findings):
            if not isinstance(finding, dict):
                continue
            source_id = finding.get("source_id")
            kind = finding.get("kind")
            # Only cite techniques/controls that appear in the supplied
            # assessments; the route re-validates against the same catalogs.
            linked_techniques = (
                [source_id] if kind == "attack" and source_id in valid_techniques else []
            )
            linked_controls = (
                [source_id] if kind in ("csf", "zt") and source_id in valid_controls else []
            )
            label = finding.get("label") or source_id or f"finding {i + 1}"
            entries.append(
                {
                    "title": f"Gap: {label}",
                    "description": ("Fixture-mode candidate risk entry drafted from the finding."),
                    "axis": _RISK_AXIS_CYCLE[i % len(_RISK_AXIS_CYCLE)],
                    "linked_techniques": linked_techniques,
                    "linked_controls": linked_controls,
                    "likelihood": _RISK_LIKELIHOOD_CYCLE[i % len(_RISK_LIKELIHOOD_CYCLE)],
                    "impact": _RISK_IMPACT_CYCLE[i % len(_RISK_IMPACT_CYCLE)],
                    "compensating_controls": "Interim monitoring in place.",
                    "residual_risk": "Elevated until remediated.",
                    "recommended_action": _RISK_ACTION_CYCLE[i % len(_RISK_ACTION_CYCLE)],
                    "rationale": "Fixture-mode rationale; validate against evidence.",
                    "source": finding.get("source") or "coverage_finding",
                    "source_id": source_id,
                }
            )
    return _resp({"entries": entries})


# ---------------------------------------------------------------------------
# Runtime provider
# ---------------------------------------------------------------------------

_RUNTIME_FIXTURES: dict[str, Any] = {
    PURPOSE_MITRE_MAP: _fixture_mitre_map,
    PURPOSE_ZT_SCORE: _fixture_zt_score,
    PURPOSE_CSF_SCORE: _fixture_csf_score,
    PURPOSE_TECH_DEBT: _fixture_tech_debt,
    PURPOSE_RISK_SYNTHESIZE: _fixture_risk_synthesize,
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
    """Build a fixture provider with a deterministic response for all 5 purposes."""
    provider = RuntimeFixtureProvider(model=model)
    for purpose, fn in _RUNTIME_FIXTURES.items():
        provider.register(purpose, fn)
    return provider
