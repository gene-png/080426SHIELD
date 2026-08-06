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
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.ai.llm import LLMClient
from app.models.artifact import Artifact
from app.models.capability import SecurityFunction
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


@dataclass
class ExtractionResult:
    items: list[ExtractedCapability]
    llm_call: LLMCall
    # How the uploaded rows map onto `items`. Since prompt v2 the extraction is
    # portfolio-wide, so exclusions should now be rare — notes, headers and
    # duplicates rather than whole categories of software. The reconciliation
    # stays because "rare" is not "never" (UX finding 4 / E2E F-5).
    reconciliation: Reconciliation


def _load_artifact_bytes(storage: StorageBackend, artifact: Artifact) -> bytes:
    """Read the raw artifact bytes through the storage protocol.

    Uses the backend-agnostic `get()` so extraction works identically against
    the local FS (tests, keyless dev) and MinIO/S3 (compose, prod). Raises
    FileNotFoundError if the object is missing (fail loudly)."""
    return storage.get(artifact.file_storage_key)


def _parse_response(content: str) -> list[ExtractedCapability]:
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError as exc:
        # Some providers wrap the JSON in prose despite the instruction.
        # Strip everything outside the outermost {...} and retry once.
        first = content.find("{")
        last = content.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise ValueError(f"LLM response was not parseable JSON: {exc}") from exc
        decoded = json.loads(content[first : last + 1])

    raw_items = decoded.get("items", []) if isinstance(decoded, dict) else []
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


def _coerce_item(item: dict[str, Any]) -> ExtractedCapability:
    def _opt_str(key: str) -> str | None:
        v = item.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s or None

    def _opt_int(key: str) -> int | None:
        v = item.get(key)
        if v is None or v == "":
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    def _opt_float(key: str) -> float | None:
        v = item.get(key)
        if v is None or v == "":
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

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

    return ExtractedCapability(
        name=(_opt_str("name") or "Unknown capability"),
        vendor=_opt_str("vendor"),
        category=_opt_str("category"),
        function=_opt_str("function"),
        annual_cost_usd=_opt_float("annual_cost_usd"),
        license_count=_opt_int("license_count"),
        notes=_opt_str("notes"),
        confidence_pct=_opt_int("confidence_pct"),
        source_row_index=_opt_int("source_row_index"),
        security_related=related,
        security_functions=functions,
    )


def extract_capabilities(
    *,
    db: Session,
    storage: StorageBackend,
    artifact: Artifact,
    requested_by: User,
    service_id: uuid.UUID,
    client_id: uuid.UUID,
    client_org_name: str | None,
    name_hints: Iterable[str] = (),
    llm: LLMClient,
) -> ExtractionResult:
    """Top-level entry point used by the ingest route."""
    raw = _load_artifact_bytes(storage, artifact)
    rows = parse_inventory(raw, artifact.mime_type)

    payload: dict[str, Any] = {
        "rows": rows,
        "context": {
            "source_filename": artifact.title,
            "source_mime": artifact.mime_type,
        },
    }

    # Runs through the AI job registry (Work Order C1); the "tech_debt_extract"
    # job keeps the historical "extract.capabilities" llm purpose.
    from app.ai.engine import run_job
    from app.ai.failures import ai_call_boundary

    # Scoped to the model call only: parsing above raises
    # UnsupportedInventoryFormat, which the route maps to a 415 and which must
    # not be rewritten as an AI failure.
    with ai_call_boundary(db, llm, purpose="extract.capabilities"):
        result = run_job(
            db,
            llm,
            "tech_debt_extract",
            inputs=payload,
            requested_by=requested_by.id,
            service_id=service_id,
            client_id=client_id,
            client_org_name=client_org_name,
            name_hints=tuple(name_hints),
        )
    items = result.data
    return ExtractionResult(
        items=items,
        llm_call=result.llm_call,
        reconciliation=reconcile_rows(rows, [i.source_row_index for i in items]),
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
            hints.append(email.split("@", 1)[0])
    return [h for h in hints if h and len(h) >= 2]


def client_org_name_for_tenant(db: Session, client_id) -> str | None:
    """Pull the named tenant's legal name (or None for placeholders)."""
    row = db.get(Client, client_id)
    if row is None:
        return None
    name = row.legal_name
    if not name or name == "(pending intake)":
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
