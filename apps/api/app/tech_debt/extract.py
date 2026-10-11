"""Capability extraction - call the LLM with redacted inventory rows.

Master Spec §15 Phase 3 + §12. The flow:

  1. Load the source artifact bytes via the storage backend.
  2. Parse into row-dicts (tech_debt.parsers).
  3. Build a structured prompt + a payload of {"rows": [...], "context": {...}}.
  4. Call LLMClient.invoke(purpose="extract.capabilities"). The client
     redacts the payload before send and writes an llm_calls audit row.
  5. Parse the LLM's JSON response into ExtractedCapability rows. The
     route layer turns those into CapabilityItem ORM rows.

The prompt is versioned (`PROMPT_VERSION` constant) so a future change
to the prompt shape doesn't silently regress past extractions; the
llm_calls row records the version that ran.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy.orm import Session

from app.ai.engine import require_json_object, require_list_at
from app.ai.llm import LLMClient
from app.models.artifact import Artifact
from app.models.capability import CapabilityItem, SecurityFunction
from app.models.client import Client
from app.models.llm_call import LLMCall
from app.models.user import User
from app.storage import StorageBackend
from app.tech_debt.bounds import (
    INT_MAX,
    NOT_WHOLE_CENTS,
    OUT_OF_RANGE,
    cost_in_cents,
    cost_problem,
)
from app.tech_debt.parsers import parse_inventory
from app.tech_debt.reconcile import Reconciliation, reconcile_rows

# v3.2 (issue 806, comment 5983838515, approved by Gene 2026-10-04; for #806).
# What it changes from v2, which asked only for a portfolio-wide list:
#   - the scope rules are explicit (section 1): a total line, a header, a note and
#     an exact duplicate are skipped; a retired row with no cost is skipped; an
#     inactive, planned or no-longer-used capability that still carries a cost is
#     kept with its status in `notes` and confidence 60;
#   - one item per row (section 4), so two items naming one row are counted;
#   - `category` is one of a closed list or null (`CATEGORIES` below);
#   - `confidence_pct` is 100, 90 or 60 only (section 8), and every 60 says why;
#   - `notes` are plain facts for the client's deliverable, never instructions;
#   - a security tool not in use today is `security_related: false` with a note
#     beginning with exactly `security_scope.NOT_IN_USE_PREFIX` (for #845).
# The text is placed verbatim, with no `.format()`: a test pins its sha256.
# `llm_calls.prompt_version` tells a v3.2 run from a v2 one.
PROMPT_VERSION = "v3.2"

PROMPT = """You are a deterministic software-inventory extraction engine. Convert the input JSON `rows` array into a normalized capability list by applying the rules below exactly.

## 1. Scope

The inventory represents the organization's entire software portfolio, not only dedicated security products.

Include every identifiable software capability, regardless of business purpose; whether it is paid, free, bundled, open-source, or internally developed; or whether it is hosted, installed, subscribed to, or provided as a service. A capability may be a tool, application, platform, service, subscription, suite, product, or explicitly identified module.

Exclude a row only when it is:

1. blank;
2. solely a title, section label, or column header;
3. solely an instruction or explanatory note and does not identify a capability;
4. a total, subtotal, or summary line that adds up other rows;
5. an exact duplicate under the duplicate rules below; or
6. explicitly described as retired, removed, or decommissioned AND the row states no current cost or license count.

Do not exclude a capability merely because information is incomplete. Keep inactive, planned, and no-longer-used capabilities that still carry a cost or license count; record their status in `notes` and set `confidence_pct` to 60.

## 2. Redacted values

Some values were replaced before you received them with placeholders such as `[NAME]`, `[EMAIL]`, `[PHONE]`, `[ADDRESS]`, `[CLIENT]` and `[CONTRACT]`. Keep a placeholder exactly as written when it is part of a capability's name (for example `[CLIENT] Portal`). Never treat a placeholder alone as a capability, and never guess what it replaced.

## 3. Permitted inference

You may use well-established product knowledge only to determine:

- canonical product name;
- vendor;
- category;
- one-line function;
- whether the capability is security-related; and
- which security functions it provides.

Do not use outside knowledge to infer cost, license count, acquisition type, lifecycle status, organizational owner, deployment status, or contract details.

When a permitted inference is not supported by either the row or well-established product knowledge, return `null`, or an empty array for `security_functions`.

Do not invent products, modules, costs, licenses, statuses, or contractual relationships.

## 4. One item per row

1. Inspect all fields in each row, not only the first field.
2. Return exactly one item for each row you keep.
3. If a row names a suite and products or modules included in it, return the suite as the item and list the included products in `notes` (for example "Includes: X, Y.").
4. If a row names several independent products, return the one the row's cost and license values belong to and list the others in `notes` (for example "Row also names: X, Y."). When it is unclear which one the values belong to, return the first named and set `confidence_pct` to 60.
5. Never name a product or module in `notes` that the row does not name, even if it is commonly included in a known suite.

## 5. Duplicate handling

Two rows are exact duplicates only when their substantive contents are identical after ignoring differences in capitalization, surrounding whitespace, and inconsequential punctuation.

When rows are exact duplicates, return the item from the earliest row and return no item for the later rows.

Do not merge rows merely because they name the same product. Keep separate items when any material information differs, including cost, license count, edition or tier, business unit, owner, contract, deployment, environment, lifecycle status, notes, or acquisition arrangement.

Never add or aggregate costs or license counts across rows.

## 6. Field rules

### `name`

The shortest unambiguous canonical product or capability name, at most 100 characters. Normalize obvious abbreviations and naming variations only when well-established product knowledge makes the identity certain. Do not include cost, license quantity, status, or descriptive notes in the name.

### `vendor`

The canonical vendor name, at most 100 characters, when stated in the row or unambiguously established by product knowledge. Otherwise `null`.

### `category`

Exactly one value from this list, or `null`:

`AI/ML`, `Analytics/BI`, `Application Security`, `Backup/Recovery`, `Cloud Infrastructure`, `CNAPP`, `Collaboration/Communication`, `CRM/Sales`, `Data/Database`, `DevOps/Engineering`, `EDR/XDR`, `ERP`, `Finance/Accounting`, `GRC/Compliance`, `HCM/HR`, `IAM/PAM`, `Incident Response`, `IT Asset Management`, `IT Operations/ITSM`, `Legal`, `Marketing`, `Network Infrastructure`, `Network Security`, `Productivity/Content`, `Project/Work Management`, `Security Awareness`, `SIEM/SOAR`, `Storage`, `Vulnerability Management`

Choose the most specific applicable category. Return `null` when the category cannot be determined, or when it is known but not on the list; in the second case, state the actual category in `notes`.

### `function`

One factual sentence, at most 200 characters, describing the capability's primary operational purpose. It must describe what the capability does, not merely repeat its category. Return `null` when the function cannot be determined reliably.

### `annual_cost_usd`

A JSON number with no currency symbol, commas, or text (for example `12000.5`).

- A number in a column whose header names cost, price, spend, or fees is an annual U.S. dollar cost, unless the header or the row states a different billing period or currency.
- An amount the row explicitly states as annual and in U.S. dollars is an annual U.S. dollar cost. Accept a dollar sign as USD unless the row explicitly identifies another currency.
- Return `0` when the row explicitly states the capability is free or costs nothing.

Do not annualize monthly, quarterly, or multiyear amounts; convert foreign currencies; divide bundled costs among products; estimate missing costs; or infer costs from product knowledge. In those cases return `null`, and when the row contains any cost information, copy that cost expression exactly as stated into `notes`.

### `license_count`

A JSON integer with no commas or text, only when the row explicitly states a numeric license, seat, or user count for that capability. Do not infer or calculate a license count. For values such as `enterprise`, `unlimited`, a range, or an unclear shared count, return `null` and preserve the source wording in `notes`.

### `notes`

At most 300 characters. Notes appear in the client's deliverable, so write them as short, plain facts about the source row (for example "Edition not stated."), never as instructions or questions to a reviewer. Include, when the row states it:

- the cost as stated, when `annual_cost_usd` is `null`;
- license wording that is not a plain count;
- lifecycle status, when inactive, planned, or no longer used;
- acquisition arrangement (bundled, free, open source, internally developed);
- the suite or parent product it belongs to;
- other products the row names (section 4);
- the actual category, when `category` is `null` for that reason; and
- what is ambiguous, when `confidence_pct` is 60.

Do not place hidden reasoning, speculation, or unsupported assumptions in this field. Return `null` when no note is needed.

## 7. Security classification

### `security_related`

`true` when defending the organization (preventing, detecting, or responding to threats) is part of the capability's purpose: for example endpoint, email, network, cloud or application protection, identity and access management, SIEM or SOAR, vulnerability management, data-loss prevention, backup and recovery, security awareness, and incident response.

`false` when the capability only has the built-in protections any business software has, such as a login, permissions, or audit history. A payroll, HR, finance, collaboration, engineering, or productivity product is `false` unless it is also sold as a security capability.

This overrides the rule above: a security capability that the row describes as planned, not yet deployed, inactive, or no longer used is `false`, with an empty `security_functions`, because it does not protect the organization today. Begin `notes` with exactly `Security tool not in use:` followed by the status as the row states it (for example "Security tool not in use: planned, not yet deployed."). An analyst reviews this classification before the tool is left out of the ATT&CK assessment.

### `security_functions`

When `security_related` is `true`, return every applicable value, using these decision rules:

- `prevent`: authentication, MFA, access enforcement, encryption, filtering, blocking, hardening, segmentation, or another protection intended to stop or reduce unauthorized or harmful activity.
- `detect`: security monitoring, scanning, analysis, alerting, anomaly identification, security audit logging, or another function that identifies potentially harmful activity.
- `respond`: containment, isolation, remediation, recovery, restoration, incident workflow, or another function that helps act on or recover from an event. Backup and restoration are `respond`.

When `security_related` is `true`, return at least one value. When it is `false`, return an empty array.

## 8. Confidence scoring

Use only these values for `confidence_pct`:

- `100`: the row states the capability's name and vendor, and nothing about the item is ambiguous.
- `90`: identity is unambiguous, but vendor, category, function, or security classification relies on well-established product knowledge.
- `60`: the item needs human review: its identity, edition, module, or parent relationship is ambiguous; it was chosen as the first named product under section 4; or it is an inactive, planned, or no-longer-used capability kept under section 1.

Low confidence does not justify excluding an identifiable capability. State what is ambiguous in `notes`.

## 9. Source indexes and output order

`source_row_index` is the zero-based index of the source row in `rows[]`. Return items in ascending `source_row_index` order.

## 10. Output requirements

Return only valid JSON. Do not include Markdown, explanations, comments, headings, or text outside the JSON object. Use `null` exactly where required; do not substitute empty strings, "N/A", "none", or "unknown".

{
  "items": [
    {
      "name": "Canonical capability name",
      "vendor": null,
      "category": null,
      "function": null,
      "annual_cost_usd": null,
      "license_count": null,
      "notes": null,
      "security_related": false,
      "security_functions": [],
      "confidence_pct": 90,
      "source_row_index": 0
    }
  ]
}

If `rows` is missing, is not an array, or contains no identifiable capabilities, return exactly:

{"items":[]}

Before returning the JSON, silently verify:

1. Every included item represents an identifiable capability, and every excluded row satisfies an exclusion rule.
2. No total or summary line was returned as an item.
3. No row produced more than one item, and no two items share a `source_row_index`.
4. No unnamed suite components were invented.
5. Costs and license counts are plain JSON numbers, never inferred or aggregated.
6. Every security-related item has at least one security function; every other item, including a planned, inactive, or no-longer-used security tool, has none.
7. `confidence_pct` is 100, 90, or 60, and every 60 has a note saying why.
8. No field exceeds its length limit.
9. The response is valid JSON with no text outside the object."""  # noqa: E501

#: v3.2 section 6's closed `category` list, held ONCE. A test parses the list
#: out of `PROMPT` and requires it to equal this tuple, so a drift between the
#: prompt and the code goes red.
CATEGORIES: tuple[str, ...] = (
    "AI/ML",
    "Analytics/BI",
    "Application Security",
    "Backup/Recovery",
    "Cloud Infrastructure",
    "CNAPP",
    "Collaboration/Communication",
    "CRM/Sales",
    "Data/Database",
    "DevOps/Engineering",
    "EDR/XDR",
    "ERP",
    "Finance/Accounting",
    "GRC/Compliance",
    "HCM/HR",
    "IAM/PAM",
    "Incident Response",
    "IT Asset Management",
    "IT Operations/ITSM",
    "Legal",
    "Marketing",
    "Network Infrastructure",
    "Network Security",
    "Productivity/Content",
    "Project/Work Management",
    "Security Awareness",
    "SIEM/SOAR",
    "Storage",
    "Vulnerability Management",
)

#: v3.2 section 8: the only confidence values the prompt allows.
CONFIDENCE_SCALE: frozenset[int] = frozenset({100, 90, 60})

#: The prompt versions whose rules `extraction_flags` judges by. A list an
#: earlier prompt drafted followed that prompt's rules (v2 asked for any
#: confidence from 0 to 100 and offered "EDR" as a category), so its flags are
#: not measured rather than counted. Add a version only when its prompt carries
#: the same closed scale, closed list and one-item-per-row rule.
PROMPT_VERSIONS_WITH_CLOSED_SCALES: frozenset[str] = frozenset({"v3.2"})

#: The name an item is stored under when the model sent none. Kept, not
#: dropped: the row is a capability the client pays for (C6 (1), for #806).
UNKNOWN_NAME = "Unknown capability"

#: The finding reason for an item whose `source_row_index` an earlier item in
#: the same answer already named (v3.2 section 4, "Return exactly one item for
#: each row you keep"). Both items are kept; the later one is recorded.
DUPLICATED = "duplicated"


@dataclass(frozen=True)
class ExtractedCapability:
    name: str
    vendor: str | None
    category: str | None
    function: str | None
    annual_cost_usd: float | None
    license_count: int | None
    notes: str | None
    confidence_pct: int | None
    source_row_index: int | None
    # Since prompt v2 (v3.2 keeps it). None when the provider omitted the field
    # (an older prompt, or a response that dropped it), never coerced to False, because False is a
    # decision and None is the absence of one. app.tech_debt.security_scope
    # keeps unclassified rows in the ATT&CK subset for exactly that reason.
    security_related: bool | None = None
    security_functions: tuple[str, ...] = ()
    # #833 / #834: what this item's values could not be stored as given, each
    # `{source_row_index, item_name, field, reason, value}`. The value itself
    # is stored as NULL (a number) or cut to its column (a string); the record
    # is what says so.
    findings: tuple[dict[str, Any], ...] = ()


@dataclass
class ExtractionResult:
    items: list[ExtractedCapability]
    llm_call: LLMCall
    # How the uploaded rows map onto `items`. Since prompt v2 the extraction is
    # portfolio-wide, so exclusions should now be rare — notes, headers and
    # duplicates rather than whole categories of software. The reconciliation
    # stays because "rare" is not "never" (UX finding 4 / E2E F-5).
    reconciliation: Reconciliation
    # #833 / #834: every value the extraction could not store as given, in item
    # order. [] means checked and nothing to record. Stored on the list as
    # `extraction_findings`.
    findings: list[dict[str, Any]] = field(default_factory=list)


def _load_artifact_bytes(storage: StorageBackend, artifact: Artifact) -> bytes:
    """Read the raw artifact bytes through the storage protocol.

    Uses the backend-agnostic `get()` so extraction works identically against
    the local FS (tests, keyless dev) and MinIO/S3 (compose, prod). Raises
    FileNotFoundError if the object is missing (fail loudly)."""
    return storage.get(artifact.file_storage_key)


def _decode_wrapped_in_prose(content: str, exc: json.JSONDecodeError) -> Any:
    """Recover JSON a provider wrapped in prose despite the instruction.

    Considers BOTH `{...}` and `[...]`, which the brace-only version did not.
    That mattered: a bare list wrapped in prose — the likeliest drift, the model
    returning the array it was told to nest — sliced down to the first ITEM's
    braces and decoded as a single object with no `items` key, so the run
    reported one capability found or zero, and the shape guard never saw a list
    at all. Widening the retry is what lets `require_json_object` observe the
    real shape and refuse.

    Candidates are tried in the order they appear, and the first that decodes
    wins: prose like "see [1] for details {...}" would otherwise slice from an
    unrelated bracket and raise an uncaught decode error.
    """
    spans = [
        (content.find(open_c), content.rfind(close_c))
        for open_c, close_c in (("{", "}"), ("[", "]"))
    ]
    candidates = sorted(
        (first, content[first : last + 1]) for first, last in spans if first != -1 and last > first
    )
    for _, snippet in candidates:
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"LLM response was not parseable JSON: {exc}") from exc


def _parse_response(content: str) -> list[ExtractedCapability]:
    """#77: the last AI parser without a top-level shape guard.

    It carried both halves of the family `AIResponseShapeError` exists for — a
    `if isinstance(decoded, dict) else []` fallback that swallowed a bare-list
    top level whole, and a `for item in raw_items` that iterated the KEYS of a
    non-list `items` and then dropped each one. Either reported zero extracted
    capabilities, indistinguishable from an inventory holding nothing the model
    recognised. This path feeds the ATT&CK allow-list, where an empty capability
    list once produced 607 fabricated `gap` rows.

    It reuses `require_json_object` / `require_list_at` rather than switching to
    `parse_json_object_with_list`, because the prose retry below is tolerance
    `parse_json` does not have and a wholesale swap would have silently removed
    it — turning providers that work today into hard failures. Sharing the CHECK
    and keeping the DECODE is what closes #77 without that regression.
    """
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        decoded = _decode_wrapped_in_prose(content, exc)

    require_list_at(require_json_object(decoded), "items")
    raw_items = decoded.get("items", [])
    return [_coerce_item(item) for item in raw_items if isinstance(item, dict)]


def _security_functions(raw: Any) -> tuple[str, ...]:
    """Keep only recognised prevent/detect/respond values, in a stable order.

    Anything else the provider invents is dropped rather than stored — these
    values drive the ATT&CK citation buckets, so an unrecognised one would be a
    label nothing can act on.
    """
    if not isinstance(raw, list):
        return ()
    seen = {str(v).strip().lower() for v in raw if v is not None}
    return tuple(f.value for f in SecurityFunction if f.value in seen)


#: Column widths, READ from the model (`models/capability.py`) rather than
#: copied, so a migration that widens a column cannot leave a stale limit here.
#: A longer string is cut to the width and recorded (#834): left alone it crashed
#: the insert on Postgres after the provider call was paid, losing the whole
#: list. Cut rather than refused, because refusing would drop a capability the
#: client pays for.
_STRING_WIDTHS = {
    key: CapabilityItem.__table__.c[key].type.length
    for key in ("name", "vendor", "function", "category")
}
# An unbounded column would give None and fail only after a paid call; refuse
# that at import instead (#878 narrow review).
if not all(isinstance(w, int) for w in _STRING_WIDTHS.values()):
    raise RuntimeError(f"capability item columns need a fixed width: {_STRING_WIDTHS}")
#: `license_count`, `confidence_pct`: Integer (32-bit) columns. The licence and
#: cost bounds are `tech_debt/bounds.py`'s, shared with the item PATCH and the
#: include-row route (#879).
_INT_RANGES = {"license_count": (0, INT_MAX), "confidence_pct": (0, 100)}
#: "1,000" or "1,200.50": comma thousands separators, nothing else.
_THOUSANDS = re.compile(r"^\d{1,3}(,\d{3})+(\.\d+)?$")


def _shown(raw: Any) -> str:
    """The value as an admin reads it in a finding: a string as written (its
    unprintable characters escaped), anything else as `repr`, bounded."""
    if isinstance(raw, str):
        return "".join(c if c.isprintable() else repr(c)[1:-1] for c in raw)[:120]
    return repr(raw)[:120]


def _number(raw: Any, *, money: bool = False) -> float | None:
    """`raw` as a number, or None when it is not one (#833).

    `int(float(v))` was doing this job and is not a validator: `int(True)` is 1
    and `int(2.9)` is 2, each stored as if the model had said it. A bool is
    refused. A whole number written differently ("2", 2.0, "1,000") is accepted.
    `money` also accepts a leading "$" (v3.2: "Accept a dollar sign as USD");
    any other symbol or text ("€1,200", "1200/month") is not a number.
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        try:
            n = float(raw)
        except OverflowError:
            return None
    elif isinstance(raw, str):
        text = raw.strip()
        if money and text.startswith("$"):
            text = text[1:].strip()
        if _THOUSANDS.match(text):
            text = text.replace(",", "")
        try:
            n = float(text)
        except ValueError:
            return None
    else:
        return None
    return n if math.isfinite(n) else None


def _coerce_item(item: dict[str, Any]) -> ExtractedCapability:
    def _opt_str(key: str) -> str | None:
        v = item.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    findings: list[dict[str, Any]] = []
    name_for_record = _opt_str("name") or UNKNOWN_NAME
    # The VALIDATED row index, set below before any other field is read. The raw
    # one can be a NaN or an infinity (json.loads accepts both), which Postgres
    # json rejects at commit -- after the call is paid (#878 review B1).
    row_for_record: int | None = None

    def _record(key: str, reason: str, raw: Any, **extra: Any) -> None:
        findings.append(
            {
                "source_row_index": row_for_record,
                "item_name": name_for_record[:255],
                "field": key,
                "reason": reason,
                "value": _shown(raw),
                **extra,
            }
        )

    def _bounded_str(key: str) -> str | None:
        s = _opt_str(key)
        width = _STRING_WIDTHS[key]
        if s is not None and len(s) > width:
            # `width` travels with the finding, so the screen states the cut
            # from the one table that sets it rather than a copy of it.
            _record(key, "truncated", s, width=width)
            return s[:width]
        return s

    def _opt_int(key: str, low: int, high: int) -> int | None:
        """Range first, then wholeness: `3.9` reports as out of range."""
        v = item.get(key)
        if v is None or v == "":
            return None
        n = _number(v)
        if n is None:
            _record(key, "unparseable", v)
            return None
        if not low <= n <= high:
            _record(key, "out_of_range", v)
            return None
        if n != int(n):
            _record(key, "not_whole", v)
            return None
        return int(n)

    def _opt_cost(key: str) -> float | None:
        """Quantized to cents FIRST, then judged: the column rounds a fractional
        cent anyway, so the range is judged on what it would store, and the
        rounding is recorded rather than left to the database (#878 review A3)."""
        v = item.get(key)
        if v is None or v == "":
            return None
        n = _number(v, money=True)
        if n is None:
            _record(key, "unparseable", v)
            return None
        # The bounds are `tech_debt/bounds.py`'s, which judges range and sign on
        # the exact value before quantizing (#878 narrow review).
        problem = cost_problem(n)
        if problem == OUT_OF_RANGE:
            _record(key, "out_of_range", v)
            return None
        if problem == NOT_WHOLE_CENTS:
            _record(key, "rounded", v)
        return cost_in_cents(n)

    def _opt_bool(key: str) -> bool | None:
        """Tri-state: an absent or unrecognised value stays None, never False.

        None means "the model did not classify this row"; False means "the model
        said no". Collapsing the two would silently convert every unclassified
        row into a negative, which is the one direction that loses tools.
        """
        v = item.get(key)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "yes"):
                return True
            if s in ("false", "no"):
                return False
        return None

    functions = _security_functions(item.get("security_functions"))
    related = _opt_bool("security_related")
    # A named security function contradicts a False flag. Trust the function:
    # it is the more specific claim, and inclusion is the safe direction — a
    # tool wrongly kept costs a review, one wrongly dropped costs a blind spot.
    if functions and related is False:
        related = True

    # The row first, so every finding below carries the validated index. The
    # upper bound needs the number of uploaded rows, which the parser does not
    # have: `with_row_bounds` checks it once the rows are known.
    row = _opt_int("source_row_index", 0, INT_MAX)
    row_for_record = row
    name = _bounded_str("name") or UNKNOWN_NAME
    vendor = _bounded_str("vendor")
    category = _bounded_str("category")
    function = _bounded_str("function")
    cost = _opt_cost("annual_cost_usd")
    licenses = _opt_int("license_count", *_INT_RANGES["license_count"])
    confidence = _opt_int("confidence_pct", *_INT_RANGES["confidence_pct"])
    return ExtractedCapability(
        name=name,
        vendor=vendor,
        category=category,
        function=function,
        annual_cost_usd=cost,
        license_count=licenses,
        notes=_opt_str("notes"),
        confidence_pct=confidence,
        source_row_index=row,
        security_related=related,
        security_functions=functions,
        findings=tuple(findings),
    )


def with_row_bounds(items: list[ExtractedCapability], row_count: int) -> list[ExtractedCapability]:
    """A `source_row_index` that names no uploaded row is refused (#833).

    Stored, it attributed the item to a row it did not come from, and the
    reconciliation then named the wrong rows as excluded. Refused, the item is
    unattributed, which the reconciliation already reports.
    """
    out: list[ExtractedCapability] = []
    for it in items:
        i = it.source_row_index
        if i is None or i < row_count:
            out.append(it)
            continue
        finding = {
            "source_row_index": i,
            "item_name": it.name,
            "field": "source_row_index",
            "reason": "out_of_range",
            "value": _shown(i),
        }
        out.append(replace(it, source_row_index=None, findings=(*it.findings, finding)))
    return out


def with_duplicate_rows(items: list[ExtractedCapability]) -> list[ExtractedCapability]:
    """Two items naming one source row are both kept, and the later is recorded.

    v3.2 asks for one item per row (section 4). A second item on the same row is
    still a capability somebody named, so it is not dropped; it stays in the
    list and in `reconcile_rows`' per-item count, and the record is what says the
    row produced more than one (C6 (6), for #806). The row index is not stored on
    an item, so this is the one flag that cannot be derived later.
    """
    seen: set[int] = set()
    out: list[ExtractedCapability] = []
    for it in items:
        i = it.source_row_index
        if i is None or i not in seen:
            if i is not None:
                seen.add(i)
            out.append(it)
            continue
        finding = {
            "source_row_index": i,
            "item_name": it.name,
            "field": "source_row_index",
            "reason": DUPLICATED,
            "value": _shown(i),
        }
        out.append(replace(it, findings=(*it.findings, finding)))
    return out


def duplicated_source_rows(findings: Iterable[dict[str, Any]]) -> int:
    """How many SOURCE ROWS were turned into more than one item: a row named
    three times is one row."""
    return len(
        {
            f.get("source_row_index")
            for f in findings
            if f.get("field") == "source_row_index" and f.get("reason") == DUPLICATED
        }
    )


def extraction_flags(items: Iterable[object], findings: Iterable[dict[str, Any]]) -> dict[str, int]:
    """What v3.2 closes and a model can still send, each kept as sent and counted.

    Computed once, at extraction, over the items the model returned, and
    recorded in the extraction's audit; the list response reads that record
    (advisor ruling F2, issue 736 comment 6069328834), so a consultant's later
    edit never changes it. `items` are read by attribute.
    """
    values = [
        (getattr(i, "name", None), getattr(i, "confidence_pct", None), getattr(i, "category", None))
        for i in items
    ]
    return {
        "name_missing": sum(1 for name, _, _ in values if name == UNKNOWN_NAME),
        "confidence_off_scale": sum(
            1 for _, conf, _ in values if conf is not None and conf not in CONFIDENCE_SCALE
        ),
        "category_off_list": sum(
            1 for _, _, cat in values if cat is not None and cat not in CATEGORIES
        ),
        "source_row_duplicated": duplicated_source_rows(findings),
    }


def read_inventory(storage: StorageBackend, artifact: Artifact) -> list[dict]:
    """Load and parse the inventory document. Raises UnsupportedInventoryFormat,
    which the route maps to a 415 BEFORE a Run-AI starts (#645): a document the
    parser cannot read is the request's fault, not the run's."""
    raw = _load_artifact_bytes(storage, artifact)
    return parse_inventory(raw, artifact.mime_type)


def extract_from_rows(
    *,
    db: Session,
    rows: list[dict],
    source_filename: str | None,
    source_mime: str,
    requested_by_id: uuid.UUID,
    service_id: uuid.UUID,
    client_id: uuid.UUID,
    client_org_name: str | None,
    name_hints: Iterable[str] = (),
    llm: LLMClient,
) -> ExtractionResult:
    """The model call over rows already parsed. Plain values only, so the
    background job (#645) can call it with nothing from the request."""
    payload: dict[str, Any] = {
        "rows": rows,
        "context": {
            "source_filename": source_filename,
            "source_mime": source_mime,
        },
    }

    # Runs through the AI job registry (Work Order C1); the "tech_debt_extract"
    # job keeps the historical "extract.capabilities" llm purpose.
    from app.ai.engine import run_job
    from app.ai.failures import ai_call_boundary

    # Scoped to the model call only: parsing raises UnsupportedInventoryFormat,
    # which the route maps to a 415 and which must not be rewritten as an AI
    # failure.
    with ai_call_boundary(db, llm, purpose="extract.capabilities"):
        result = run_job(
            db,
            llm,
            "tech_debt_extract",
            inputs=payload,
            requested_by=requested_by_id,
            service_id=service_id,
            client_id=client_id,
            client_org_name=client_org_name,
            name_hints=tuple(name_hints),
        )
    # Bounds first: an index that names no uploaded row is cleared, and a
    # cleared index is not a duplicate of anything.
    items = with_duplicate_rows(with_row_bounds(result.data, len(rows)))
    return ExtractionResult(
        items=items,
        llm_call=result.llm_call,
        reconciliation=reconcile_rows(rows, [i.source_row_index for i in items]),
        findings=[f for i in items for f in i.findings],
    )


def name_hints_for_tenant(db: Session, client_id) -> list[str]:
    """Pull display_name + email-local-parts off every user in this tenant.

    The redactor uses these as a name dictionary so the inventory's
    "owner" / "POC" columns don't leak into the LLM payload. Multi-tenant:
    only the tenant's own user names are leaked into the dictionary so
    one client's names don't end up in another's redaction pass.
    """
    from sqlalchemy import select

    rows = db.execute(
        select(User.display_name, User.email).where(User.client_id == client_id)
    ).all()
    hints: list[str] = []
    for name, email in rows:
        if name:
            hints.append(name)
        if email and "@" in email:
            local = email.split("@", 1)[0]
            if _looks_like_an_account_name(local):
                hints.append(local)
    return [h for h in hints if h and len(h) >= 2]


def _looks_like_an_account_name(local: str) -> bool:
    """Is this email local part a PERSON, or a shared mailbox? (B13)

    The dictionary these hints feed replaces every case-insensitive occurrence
    of each entry with `[NAME]`, so an entry that is an ordinary word destroys
    that word throughout every payload the tenant ever sends. `client@` is not
    hypothetical -- it is the seeded Atlas login -- and it turns

        "The client has no MFA on the client VPN"

    into two `[NAME]` placeholders. Every real deployment has some of
    security@, admin@, it@, ops@, info@, support@, helpdesk@.

    NOT a deny-list of mailbox names: that is an enumeration of what somebody
    thought of, which is the failure this module has been paying for all week.
    The distinguishing property is structural. A generated account identifier
    carries a separator, a digit, or mixed case -- `dana.whitfield`,
    `d_whitfield`, `D.Whitfield`, `jdoe2`. A shared mailbox is a single bare
    lowercase word, because it is a word.

    RESIDUAL, stated with its firing condition: a single-token lowercase login
    like `dwhitfield` is rejected and its owner's name is not caught by THIS
    hint -- the display name still is. Accepted because `dwhitfield` is
    vanishingly unlikely to appear in an inventory's prose, while `security` is
    certain to. Revisit if a tenant is observed using bare-surname logins AND a
    name leak traced to one.

    The same shape one field over is NOT fixed here: a tenant whose `legal_name`
    is `Core`, `Delta` or `Sentinel` still has that common noun destroyed by
    `redact_org_name`. That is a single client-supplied string with no
    structural tell to test -- an org really can be called Core -- so it needs a
    product decision (warn at intake? require confirmation?) rather than a
    predicate. Tracked separately.
    """
    if any(ch.isdigit() or ch in "._-+" for ch in local):
        return True
    return local != local.lower()


def client_org_name_for_tenant(db: Session, client_id) -> str | None:
    """Pull the named tenant's legal name (or None when nobody has named the org)."""
    row = db.get(Client, client_id)
    if row is None:
        return None
    # D-080: NULL is the store's own record that nobody has named this org, so
    # there is no name to hint the redactor with.
    #
    # `not name` rather than `is None`, and the REASON here was wrong when first
    # written. It said the empty-string arm covers "a wizard that clears the
    # field, which writes `""` rather than NULL". Both halves are false: the
    # wizard sends `undefined` (`saveField(..., e.target.value || undefined)`,
    # which `exclude_unset` then drops), and `_apply_patch_to_client` maps `""`
    # and `"   "` to NULL anyway.
    #
    # The arm stays, with the reason it actually has: rows written BEFORE D-080
    # can hold `""` or `"   "`, because `ClientProfilePatch` carries no
    # validator and migration 0049 does not NULL whitespace. Blank is not a
    # name to hint with, and handing one to the redactor would ask it to
    # redact nothing while reporting that it had a name.
    name = row.legal_name
    if not (name or "").strip():
        return None
    return name


# Back-compat shims so callers updated incrementally still resolve.
def name_hints_for_deployment(db: Session) -> list[str]:  # pragma: no cover
    raise RuntimeError(
        "name_hints_for_deployment is removed (multi-tenant). "
        "Use name_hints_for_tenant(db, client_id) instead."
    )


def client_org_name_for_deployment(db: Session) -> str | None:  # pragma: no cover
    raise RuntimeError(
        "client_org_name_for_deployment is removed (multi-tenant). "
        "Use client_org_name_for_tenant(db, client_id) instead."
    )
