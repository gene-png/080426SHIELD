"""#997's `findings` half, through the generate route (#474 E, ruling 6).

`findings` is keyed by `source_id`. A dict key is never redacted, so the key
egresses verbatim, and it is GUARDED instead: each key must be a catalog code.
For a client named "GV" the key is the real "GV.OC-01", where before E the
`source_id` went out as "[CLIENT].OC-01" (measured on main aa099ac0, #997).
The catalog maps sit beside it, sent verbatim and guarded.

Expected codes come from the catalogs' own tables, never from the route.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.llm import LLMResponse
from app.csf.catalog import SUBCATEGORIES
from app.zt.catalog import DOD_CAPABILITIES

from .test_risk_code_lists_redaction import _client_named, _risk_calls, _seed
from .test_risk_register import app_client  # noqa: F401  -- the fixture, used by name below.

pytestmark = pytest.mark.unit

CSF_CODES = [s.code for s in SUBCATEGORIES if s.code.startswith("GV.")][:2]
DOD_CODES = [c.code for c in DOD_CAPABILITIES][:2]


def _spy(provider) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []

    def _record(payload: dict[str, Any]) -> LLMResponse:
        sent.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", _record)
    return sent


@pytest.mark.parametrize("org", ["GV", "DoD"])
def test_the_findings_keys_are_the_real_codes(app_client, org: str) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _client_named(c, org)
    techniques = _seed(c, bearer, cid)
    sent = _spy(provider)
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    keys = {k for payload in sent for k in payload["findings"]}
    assert keys == set(techniques) | set(CSF_CODES) | set(DOD_CODES)
    assert not [k for k in keys if "[CLIENT]" in k]


@pytest.mark.parametrize("field", ["findings", "zt_capability_details"])
def test_a_tampered_key_or_map_is_refused_before_egress(
    app_client, monkeypatch, capsys, field: str  # noqa: F811
) -> None:
    """A `findings` key that is not a code, or a ZT details map that is not the
    catalog's, would egress unredacted: refused, no provider call, no
    `llm_calls` row, and the message never carries the value."""
    from app.routes import risk as risk_routes

    c, provider = app_client
    bearer, cid = _client_named(c, "Acme")
    _seed(c, bearer, cid)
    token = "ZEBRA-PRIVATE-NOTE-7731"
    original = risk_routes._risk_batch_inputs

    def tampered(batch, **kwargs):
        payload = original(batch, **kwargs)
        if field == "findings":
            payload["findings"][token] = {"source": "x", "kind": "zt", "label": "x", "evidence": {}}
        else:
            code = next(iter(payload["zt_capability_details"]))
            payload["zt_capability_details"][code] = {**payload[field][code], "name": token}
        return payload

    monkeypatch.setattr(risk_routes, "_risk_batch_inputs", tampered)
    sent = _spy(provider)
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )

    assert r.status_code == 502, r.text
    detail = r.json()["error"]
    assert detail["reason"] == "ai_call_failed"
    if field == "findings":
        assert "payload field 'findings' key " in detail["message"]
        assert "is not a catalog code before redaction" in detail["message"]
    else:
        assert "payload field 'zt_capability_details' is not the catalog's text" in (
            detail["message"]
        )
    assert token not in r.text
    assert sent == [], "nothing may reach the provider"
    assert _risk_calls() == [], "no llm_calls row is written for a refused payload"
    captured = capsys.readouterr()
    assert token not in captured.out + captured.err
