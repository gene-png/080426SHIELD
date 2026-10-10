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

KEYED fields (#997's `findings` half, the advisor's ruling 6 on #736,
6087027524). Some fields are an object whose KEYS are catalog codes and whose
VALUES are client data: Risk's `findings` is keyed by each finding's
`source_id`. `redact_payload` never rewrites a dict key, so the key would
egress verbatim with nothing checking it was a code at all. Such a field is
registered with `register_catalog_keys`: its values are redacted like every
other client value, and each key must rebuild, byte for byte, from the catalog
(before redaction and in the payload that egresses), or nothing is sent. A
field is one or the other, never both: an exempt field's value is not redacted,
and a keyed field's must be.
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


#: A key as the catalog spells it; raises (KeyError, say) for a non-code.
KeyBuilder = Callable[[str], str]

#: Field name -> the builder each of its keys must rebuild through. Register
#: through `register_catalog_keys`. Keyed by the payload key alone, as above.
CATALOG_KEYS: dict[str, KeyBuilder] = {}


def register_catalog_field(field: str, builder: CatalogBuilder) -> None:
    existing = CATALOG_FIELDS.get(field)
    if existing is not None and existing is not builder:
        raise ValueError(f"catalog field {field!r} is already registered with another builder")
    if field in CATALOG_KEYS:
        raise ValueError(f"catalog field {field!r} is already registered for its keys")
    CATALOG_FIELDS[field] = builder


def register_catalog_keys(field: str, builder: KeyBuilder) -> None:
    """Guard `field`'s keys as catalog codes while its values stay redacted."""
    existing = CATALOG_KEYS.get(field)
    if existing is not None and existing is not builder:
        raise ValueError(f"catalog keys {field!r} are already registered with another builder")
    if field in CATALOG_FIELDS:
        raise ValueError(f"catalog field {field!r} is already registered as exempt")
    CATALOG_KEYS[field] = builder


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
    keyed = [k for k in payload if k in CATALOG_KEYS]
    for field in exempt:
        _check(field, payload, payload[field], "before redaction")
    for field in keyed:
        _check_keys(field, payload[field], "before redaction")
    rest = {k: v for k, v in payload.items() if k not in exempt}
    cleaned, counts = redact_payload(
        rest, mode=mode, client_org_name=client_org_name, name_hints=name_hints
    )
    out = {k: (payload[k] if k in exempt else cleaned[k]) for k in payload}
    for field in exempt:
        _check(field, payload, out[field], "after redaction")
    for field in keyed:
        _check_keys(field, out[field], "after redaction")
    if exempt:
        _log.info("ai_payload_catalog_fields_sent_verbatim", fields=exempt)
    if keyed:
        _log.info("ai_payload_catalog_keys_checked", fields=keyed)
    return out, counts


def _check_keys(field: str, value: Any, stage: str) -> None:
    """Every key of `value` rebuilds from the catalog, byte for byte.

    The refusal names the key's POSITION, never its text, for `_where`'s
    reason: a key that is not a code may be client text."""
    if not isinstance(value, dict):
        raise CatalogFieldMismatch(
            field,
            f"payload field {field!r} is not an object {stage} "
            f"(a {type(value).__name__}); nothing was sent",
        )
    builder = CATALOG_KEYS[field]
    for i, key in enumerate(value):
        try:
            same = isinstance(key, str) and builder(key) == key
        except Exception:  # noqa: BLE001 - refused below, without the exception's text
            same = False
        if not same:
            raise CatalogFieldMismatch(
                field,
                f"payload field {field!r} key {i} is not a catalog code {stage}; nothing was sent",
            )
