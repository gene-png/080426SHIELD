"""Catalog-sourced payload fields reach the model as the catalog has them (#984).

`redact_payload` rewrites every string in an AI payload. Some payload fields are
not client data at all: they are fixed public catalog text the prompt tells the
model to read (ATT&CK `technique_details`, CSF `subcategory_definitions`, ZT
`capability_details`). A client whose legal name is a word in that text had it
rewritten before the model read it ("Critical" turned GV.OC-04's outcome into
"[CLIENT] objectives, ..."), and `llm_calls.redacted_counts.client_org` counted
each hit as a client-name removal.

A field REGISTERED here is therefore not redacted, and is GUARDED instead: its
value is rebuilt from the catalog by the builder the service registered, and it
must equal that rebuild byte for byte (as JSON) both before redaction and in the
payload that egresses. Any difference raises `CatalogFieldMismatch` and nothing
is sent. The guard is what keeps the exemption honest: client text placed under
an exempt key, by a builder bug or otherwise, is refused rather than sent
unredacted.

What is NOT exempt: every other key. Registration is opt-in, so a field nobody
registered is redacted exactly as before. Forgetting to register a field fails
toward redaction (the pre-#984 behaviour), never toward a leak.

How a service plugs in, once, beside the function that builds the field:

    register_catalog_field("technique_details", lambda payload, value: ...)

The builder receives the unredacted payload and the field's value, and returns
what the catalog says that value is, for the same keys in the same order. It
must CALL the function the request builder uses, never reimplement it, so the
guard and the payload cannot describe two different things.

Every egress and preview path redacts through `redact_ai_payload`, so the
preview shows exactly what a run sends.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from app.ai.redact import RedactionMode, redact_payload
from app.logging import get_logger

_log = get_logger(__name__)

#: (the unredacted payload, the field's value) -> the catalog's own value.
CatalogBuilder = Callable[[Mapping[str, Any], Any], Any]

#: Field name -> its catalog builder. Register through `register_catalog_field`.
#: Keyed by the payload key alone: a key means one thing across every job, and
#: a second registration with another builder is refused.
CATALOG_FIELDS: dict[str, CatalogBuilder] = {}


class CatalogFieldMismatch(RuntimeError):
    """A registered catalog field is not the catalog's text. Raised before
    anything egresses. `field` names the payload key, never its content."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def register_catalog_field(field: str, builder: CatalogBuilder) -> None:
    existing = CATALOG_FIELDS.get(field)
    if existing is not None and existing is not builder:
        raise ValueError(f"catalog field {field!r} is already registered with another builder")
    CATALOG_FIELDS[field] = builder


def _as_bytes(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _entries(value: Any) -> list[tuple[int, Any, Any]]:
    """(position, a one-entry value of the same shape, the entry) for a list or
    dict field. Empty for any other shape."""
    if isinstance(value, list):
        return [(i, [entry], entry) for i, entry in enumerate(value)]
    if isinstance(value, dict):
        return [(i, {key: entry}, entry) for i, (key, entry) in enumerate(value.items())]
    return []


def _rebuilds(field: str, payload: Mapping[str, Any], value: Any) -> bool:
    """Whether `value` is the catalog's text, byte for byte. A builder that
    raises (an unknown code, say) means it is not."""
    try:
        expected = CATALOG_FIELDS[field](payload, value)
    except Exception:  # noqa: BLE001 - a refusal, reported by the caller
        return False
    return _as_bytes(value) == _as_bytes(expected)


def _where(field: str, payload: Mapping[str, Any], value: Any) -> str:
    """The first entry that is not the catalog's, by POSITION and TYPE only.

    Never its value: if client text ever reached a registered key, the refusal
    would otherwise copy it into the exception, then into Run-AI's user-facing
    reason and the failure log (#985 review)."""
    for i, one, entry in _entries(value):
        if not _rebuilds(field, payload, one):
            return f"entry {i}, a {type(entry).__name__}"
    return f"the whole value, a {type(value).__name__}"


def _check(field: str, payload: Mapping[str, Any], value: Any, stage: str) -> None:
    try:
        expected = CATALOG_FIELDS[field](payload, value)
        failed = False
    except Exception:  # noqa: BLE001 - refused below, without the exception's text
        failed = True
    if failed:
        what = "could not be rebuilt from the catalog"
    elif _as_bytes(value) != _as_bytes(expected):
        what = "is not the catalog's text"
    else:
        return
    # Raised outside the `except`, so no exception carrying the entry's repr
    # (a KeyError naming it, say) is chained onto this one.
    raise CatalogFieldMismatch(
        field,
        f"payload field {field!r} {what} {stage} ({_where(field, payload, value)}); "
        "nothing was sent",
    )


def redact_ai_payload(
    payload: Mapping[str, Any],
    *,
    mode: RedactionMode,
    client_org_name: str | None,
    name_hints: Iterable[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    """`redact_payload` for an AI payload, with registered catalog fields sent
    unredacted and guarded. Returns the payload to send, in the input's key
    order, and the removal counts, which no longer count catalog text."""
    exempt = [k for k in payload if k in CATALOG_FIELDS]
    for field in exempt:
        _check(field, payload, payload[field], "before redaction")
    rest = {k: v for k, v in payload.items() if k not in exempt}
    cleaned, counts = redact_payload(
        rest, mode=mode, client_org_name=client_org_name, name_hints=name_hints
    )
    out = {k: (payload[k] if k in exempt else cleaned[k]) for k in payload}
    for field in exempt:
        _check(field, payload, out[field], "after redaction")
    if exempt:
        _log.info("ai_payload_catalog_fields_sent_verbatim", fields=exempt)
    return out, counts
