"""#997's `findings` half: a KEYED catalog field (the advisor's ruling 6, #736
6087027524). Its keys must rebuild from the catalog byte for byte, while its
values are redacted like any other client value.

Exercised on `redact_ai_payload` directly with a field registered for the test
only, so the mechanism is pinned apart from Risk; the Risk registration is
pinned through the generate route in `test_risk_findings_keys_guard.py`.
"""

from __future__ import annotations

import pytest

from app.ai import catalog_fields
from app.ai.catalog_fields import (
    CatalogFieldMismatch,
    redact_ai_payload,
    register_catalog_field,
    register_catalog_keys,
)

pytestmark = pytest.mark.unit

FIELD = "test_keyed_field"
CODES = {"GV.OC-01", "GV.OC-02"}


def _code(key: str) -> str:
    if key not in CODES:
        raise KeyError(key)
    return key


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(catalog_fields, "CATALOG_KEYS", dict(catalog_fields.CATALOG_KEYS))
    monkeypatch.setattr(catalog_fields, "CATALOG_FIELDS", dict(catalog_fields.CATALOG_FIELDS))
    register_catalog_keys(FIELD, _code)


def _send(value, org: str = "GV"):
    return redact_ai_payload(
        {FIELD: value}, mode="strict", client_org_name=org, name_hints=("Dana Whitfield",)
    )


def test_keys_go_out_verbatim_and_values_are_redacted(keyed) -> None:
    out, counts = _send({"GV.OC-01": {"note": "Reviewed with Dana Whitfield at GV."}})
    # What must appear first: the real code, as the key.
    assert list(out[FIELD]) == ["GV.OC-01"]
    note = out[FIELD]["GV.OC-01"]["note"]
    assert note == "Reviewed with [NAME] at [CLIENT]."
    assert counts


def test_a_key_that_is_not_a_catalog_code_is_refused_without_its_text(keyed) -> None:
    with pytest.raises(CatalogFieldMismatch) as err:
        _send({"GV.OC-01": {}, "ZEBRA-PRIVATE-NOTE-7731": {}}, org="Acme")
    assert err.value.field == FIELD
    assert str(err.value) == (
        f"payload field '{FIELD}' key 1 is not a catalog code before redaction; nothing was sent"
    )
    assert "ZEBRA" not in str(err.value)


def test_a_keyed_field_that_is_not_an_object_is_refused(keyed) -> None:
    with pytest.raises(CatalogFieldMismatch) as err:
        _send([{"source_id": "GV.OC-01"}], org="Acme")
    assert str(err.value) == (
        f"payload field '{FIELD}' is not an object before redaction (a list); nothing was sent"
    )


def test_a_field_is_exempt_or_keyed_never_both(keyed) -> None:
    with pytest.raises(ValueError, match="already registered for its keys"):
        register_catalog_field(FIELD, lambda _p, v: v)
    register_catalog_field("test_exempt_field", lambda _p, v: v)
    with pytest.raises(ValueError, match="already registered as exempt"):
        register_catalog_keys("test_exempt_field", _code)
