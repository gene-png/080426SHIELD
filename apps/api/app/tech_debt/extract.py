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
from decimal import ROUND_HALF_UP, Decimal
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
from app.tech_debt.parsers import parse_inventory
from app.tech_debt.reconcile import Reconciliation, reconcile_rows

# v2 (2026-08-05): portfolio scope. v1 kept only security capabilities and
# silently dropped the rest, so the workspace presented the survivors as the
# whole inventory. v2 keeps every row and classifies it instead.
PROMPT_VERSION = "v2"

PROMPT = """You extract a structured capability list from a raw software \
inventory.

The inventory covers the organization's ENTIRE software portfolio, not only its \
security tooling. For each row in the JSON `rows` array, decide if it \
represents a capability the organization is paying for (tool, platform, \
service, subscription). Keep it if so, whatever its purpose - finance, HR, \
collaboration, engineering and security all belong in the list. Skip a row ONLY \
when it is a note, a blank, a column header, or a duplicate of a row you have \
already returned.

Classify every capability you keep:

  - `security_related`: true if the capability's purpose includes defending the \
organization (preventing, detecting or responding to threats), false otherwise. \
Judge the capability's actual purpose - a payroll system that happens to have a \
login is not security-related.
  - `security_functions`: when `security_related` is true, which of "prevent", \
"detect" and "respond" it serves. Return every one that applies - an endpoint \
detection and response platform typically serves all three. Return an empty \
list when `security_related` is false.

Return ONLY a JSON object of the form:

  {
    "items": [
      {
        "name": "<short name>",
        "vendor": "<vendor or null>",
        "category": "<category like CNAPP, EDR, SIEM, IAM, GRC, ERP, HCM, \
Productivity, or null>",
        "function": "<one-line function the capability serves, or null>",
        "annual_cost_usd": <number or null>,
        "license_count": <integer or null>,
        "notes": "<short note, or null>",
        "security_related": <true or false>,
        "security_functions": ["prevent"|"detect"|"respond", ...],
        "confidence_pct": <integer 0-100>,
        "source_row_index": <integer index into rows[]>
      },
      ...
    ]
  }

Do not include any text outside the JSON object. Set confidence_pct \
honestly - 100 for unambiguous rows, lower when the row needs human \
review."""


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
    # Prompt v2. None when the provider omitted the field (an older prompt, or a
    # response that dropped it) — never coerced to False, because False is a
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
#: `annual_cost_usd` is Numeric(14, 2): at most 999,999,999,999.99, judged on
#: the value as stored -- quantized to cents (#878 review A3).
_COST_LIMIT = Decimal(10**12)
_CENT = Decimal("0.01")
#: `license_count`, `confidence_pct`: Integer (32-bit) columns.
_INT_MAX = 2**31 - 1
_INT_RANGES = {"license_count": (0, _INT_MAX), "confidence_pct": (0, 100)}
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
    name_for_record = _opt_str("name") or "Unknown capability"
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
        exact = Decimal(repr(n))
        cents = exact.quantize(_CENT, rounding=ROUND_HALF_UP)
        if not 0 <= cents < _COST_LIMIT:
            _record(key, "out_of_range", v)
            return None
        if cents != exact:
            _record(key, "rounded", v)
        return float(cents)

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
    row = _opt_int("source_row_index", 0, _INT_MAX)
    row_for_record = row
    name = _bounded_str("name") or "Unknown capability"
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
    items = with_row_bounds(result.data, len(rows))
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
