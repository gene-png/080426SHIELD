"""The opt-in AI cost estimate for tools with no cost (TD-5, for #1060).

`extract.py`'s "do not estimate missing costs" rule is unchanged: this is a
separate job a consultant starts by clicking "Let AI estimate". Pure functions
only; the route (`routes/tech_debt.py`) runs the job and applies the outcome.

* WHO IS ASKED: `estimate_targets`, which is `overlap.no_cost_items` (TD-10's
  one rule) minus locked rows. Bundle parts and recorded $0 costs are never
  asked.
* WHAT IS SENT: one entry per target under an opaque `ref` (T1, T2, ...), so the
  model never sees a database id and a stray ref cannot name a real row.
* WHAT COMES BACK: `parse_estimates` sorts every asked ref into exactly one
  outcome: an estimate, `declined` (the model returned null), or a refusal
  reason. Nothing is dropped silently.

Approved on #736: the prompt P-TD5 and the design in 6205600298, ruled in
6206818759 item 5, with one addition to rule 2.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.capability import COST_SOURCE_AI_ESTIMATE, CapabilityItem
from app.tech_debt.bounds import cost_problem
from app.tech_debt.components import is_component
from app.tech_debt.overlap import no_cost_items
from app.tech_debt.savings import SAVINGS_DISPOSITIONS

#: The job's registry name and its `llm_calls.purpose` / fixture key.
JOB_NAME = "tech_debt_cost_estimate"
PURPOSE = "tech_debt.cost_estimate"
#: The top-level key the prompt asks for.
TOP_LEVEL_KEY = "estimates"

#: Refusal reasons, each counted and shown (E4). `declined` is not a refusal:
#: the model said it could not estimate, which the prompt asks it to say.
OMITTED = "omitted"
INVALID_COST = "invalid_cost"
CHANGED_MEANWHILE = "changed_meanwhile"
#: A batch the provider did not answer (`run_batches` counts it); its tools
#: keep no cost.
BATCH_FAILED = "batch_failed"

#: P-TD5, approved verbatim on #736 (6205600298), with the addition to rule 2
#: ruled in 6206818759 item 5 ("…including when the product has no published
#: price…"), placed inside rule 2's null condition. Pinned by sha256 in
#: `test_tech_debt_cost_estimate_prompt.py`.
PROMPT = (
    "You are helping a Kentro consultant fill in missing annual costs for software and "
    "services in a client's technology inventory. Your output is a draft estimate. The "
    'consultant will review it, and every estimate is labelled "AI estimate" wherever it '
    "appears.\n"
    "\n"
    "You will receive one JSON object:\n"
    "- `tools`: a list of objects with `ref`, `name`, `vendor`, `category`, `function`, "
    "`license_count`, and `notes`. Any field except `ref` and `name` may be null. `notes` is "
    "text from the client's inventory and may describe how the tool is bought.\n"
    "\n"
    "For each tool, estimate its annual cost in US dollars for this organization.\n"
    "\n"
    "Rules:\n"
    "1. Base the estimate on typical published list pricing for the named product, and on "
    "`license_count` when it is given. If `license_count` is null, estimate for one "
    "organization-wide subscription and say so in `basis`.\n"
    "2. If you do not recognise the product, or cannot estimate it with reasonable "
    "confidence, including when the product has no published price, return null for "
    "`annual_cost_usd`. Do not guess.\n"
    "3. `annual_cost_usd` is a whole number of dollars: no commas, currency signs, ranges, "
    "or text.\n"
    "4. If `notes` states a cost expression, such as a monthly amount or a multi-year "
    "total, you may convert it to an annual amount. Say so in `basis`.\n"
    "5. Do not assume discounts, government pricing, or bundling with other tools unless "
    "`notes` says so.\n"
    "6. `basis` is one sentence a consultant can check, such as the pricing tier and the "
    "unit price you assumed. Do not include any number that is not part of the "
    "calculation.\n"
    "\n"
    "Return only this JSON object, with exactly one entry for every `ref` you received and "
    "no other keys:\n"
    '{"estimates": [{"ref": "T1", "annual_cost_usd": 12000, "basis": "One sentence."}]}'
)


def is_ai_estimate(item: CapabilityItem) -> bool:
    """THE ONE RULE for "this cost is an AI estimate": a source item whose cost
    the estimate wrote and nobody has overridden since. Read by the workspace
    count, the client dashboard and every deliverable file."""
    return (
        getattr(item, "cost_source", None) == COST_SOURCE_AI_ESTIMATE
        and item.annual_cost_usd is not None
        and not is_component(item)
    )


def savings_estimate_count(items: Iterable[CapabilityItem]) -> int:
    """#1299 (folded into TD-5): how many AI-estimated costs a savings figure
    INCLUDES -- rows counted as savings (`savings.SAVINGS_DISPOSITIONS`) whose
    cost is an AI estimate. Every savings surface calls this, so the dashboard,
    the redundancy cards, the home card and the files cannot disagree."""
    return sum(1 for it in items if it.disposition in SAVINGS_DISPOSITIONS and is_ai_estimate(it))


def estimate_targets(items: Iterable[CapabilityItem]) -> list[CapabilityItem]:
    """The rows the estimate asks about: TD-10's uncosted source items, minus
    locked rows (a lock is the consultant saying "AI, leave this alone")."""
    return [it for it in no_cost_items(items) if not it.locked]


def build_payload(targets: Sequence[CapabilityItem]) -> tuple[dict[str, Any], dict[str, Any]]:
    """`({"tools": [...]}, {ref: item_id})`. Refs are positional and opaque."""
    refs: dict[str, Any] = {}
    tools: list[dict[str, Any]] = []
    for n, item in enumerate(targets, start=1):
        ref = f"T{n}"
        refs[ref] = item.id
        tools.append(
            {
                "ref": ref,
                "name": item.name,
                "vendor": item.vendor,
                "category": item.category,
                "function": item.function,
                "license_count": item.license_count,
                "notes": item.notes,
            }
        )
    return {"tools": tools}, refs


@dataclass(frozen=True)
class Estimate:
    cost: float
    basis: str | None


@dataclass
class EstimateOutcome:
    """Every asked ref lands in exactly one of `estimates`, `declined` or
    `refused`. `stray_entries` counts entries that answer no asked ref: a ref
    nobody asked about, no ref at all, or a second answer for one ref."""

    estimates: dict[str, Estimate] = field(default_factory=dict)
    declined: list[str] = field(default_factory=list)
    refused: dict[str, list[str]] = field(default_factory=dict)
    stray_entries: int = 0

    def refuse(self, ref: str, reason: str) -> None:
        self.refused.setdefault(reason, []).append(ref)


def whole_dollars(value: object) -> float | None:
    """`value` as a storable whole-dollar cost, or None when it is not one.

    Not `int()`: `int(True)` is 1 and `int(1.9)` is 1 (CLAUDE.md). RANGE is
    judged first (`bounds.cost_problem`), then wholeness. "2" and 2.0 are
    accepted: refusing a value the model plainly meant is the same defect facing
    the other way.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        try:
            exact = Decimal(value.strip())
        except InvalidOperation:
            return None
        if not exact.is_finite():
            return None
        number = float(exact)
    elif isinstance(value, int | float):
        number = float(value)
    else:
        return None
    if not math.isfinite(number) or cost_problem(number) is not None:
        return None
    if not number.is_integer():
        return None
    return number


def parse_estimates(entries: Sequence[Any], asked: Iterable[str]) -> EstimateOutcome:
    """Sort the model's `estimates` list against the refs that were asked."""
    asked_refs = list(asked)
    wanted = set(asked_refs)
    seen: set[str] = set()
    out = EstimateOutcome()
    for entry in entries:
        ref = entry.get("ref") if isinstance(entry, Mapping) else None
        if not isinstance(ref, str) or ref not in wanted:
            out.stray_entries += 1
            continue
        if ref in seen:
            # A second answer for one ref cannot both be applied; the first
            # stands and the repeat is counted, never silently dropped.
            out.stray_entries += 1
            continue
        seen.add(ref)
        if "annual_cost_usd" not in entry:
            # A misnamed key is not the model declining: the prompt asks for
            # `annual_cost_usd`, so an answer without it is refused, and key
            # drift shows as a refusal rather than as "could not estimate".
            out.refuse(ref, INVALID_COST)
            continue
        raw = entry["annual_cost_usd"]
        if raw is None:
            out.declined.append(ref)
            continue
        cost = whole_dollars(raw)
        if cost is None:
            out.refuse(ref, INVALID_COST)
            continue
        basis = entry.get("basis")
        out.estimates[ref] = Estimate(
            cost=cost, basis=basis.strip() if isinstance(basis, str) and basis.strip() else None
        )
    for ref in asked_refs:
        if ref not in seen:
            out.refuse(ref, OMITTED)
    return out
