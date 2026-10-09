"""#984: ATT&CK's `technique_details` reaches the model as the catalogue has
it, through the run and through `/ai/preview`, for a client named "Cloud".

"Cloud" is a whole word in 33 technique names (measured on main 2f701f5b with
plain `redact_payload`), so before #984 the run sent "[CLIENT] Accounts" for
T1078.004 and counted each hit as a client-name removal. The client's own data
(here, a tool named after the client) is still redacted.

Expected names come from the catalogue's public accessors, never from the
route's `_technique_details`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from app.ai.redact import redact_payload
from app.models.client import Client
from app.models.llm_call import LLMCall
from tests._ai_runs import attack_run_ai
from tests._attack_rows import first_standalone
from tests.unit.test_attack_run_ai import (  # noqa: F401  (fixture)
    _admin,
    _seed_tech_debt_tools,
    app_client,
)

pytestmark = pytest.mark.unit

_ORG = "Cloud"
_TOOL = "Cloud Backup Vault"


def _catalogue_details(code: str) -> dict:
    from app.attack.catalog import not_preventable_basis, technique_by_id

    return {
        "name": technique_by_id(code).name,
        "not_preventable": not_preventable_basis(code) is not None,
    }


def _service_for_cloud(c, TestSession) -> tuple[dict, str]:
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tech_debt_tools(TestSession, cid, me["id"], [_TOOL])
    with TestSession() as db:
        db.get(Client, uuid.UUID(cid)).legal_name = _ORG
        db.commit()
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    ).json()["id"]
    first_standalone(c.post(f"/attack/services/{svc_id}/assessments", headers=h).json()["coverage"])
    return h, svc_id


def _colliding(details: dict[str, dict]) -> list[str]:
    out, _ = redact_payload(details, mode="strict", client_org_name=_ORG)
    return [code for code in details if out[code] != details[code]]


def test_the_run_sends_every_technique_name_unchanged_and_still_redacts_the_client(
    app_client,  # noqa: F811
) -> None:
    c, TestSession, provider = app_client
    h, svc_id = _service_for_cloud(c, TestSession)
    sent: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"techniques": []}')

    provider.register("mitre_map", _spy)
    attack_run_ai(c, svc_id, h)

    details = {code: d for p in sent for code, d in p["technique_details"].items()}
    catalogue = {code: _catalogue_details(code) for code in details}
    assert len(_colliding(catalogue)) > 0, "the client name must collide for this to test anything"
    for code, d in details.items():
        assert d == _catalogue_details(code), code
    for p in sent:
        names = [cap["name"] for cap in p["capability_list"]]
        assert names == ["[CLIENT] Backup Vault"], "the client's own data is still redacted"
    with TestSession() as db:
        counts = [r.redacted_counts for r in db.execute(select(LLMCall)).scalars().all()]
    assert counts and all(c_ == {"client_org": 1} for c_ in counts), counts


def test_the_preview_shows_the_same_unchanged_names_and_counts(app_client) -> None:  # noqa: F811
    c, TestSession, _provider = app_client
    h, svc_id = _service_for_cloud(c, TestSession)

    r = c.post("/ai/preview", headers=h, json={"service_id": svc_id})
    assert r.status_code == 200, r.text
    body = r.json()

    details = body["payload"]["technique_details"]
    assert len(_colliding({code: _catalogue_details(code) for code in details})) > 0
    for code, d in details.items():
        assert d == _catalogue_details(code), code
    assert body["removed_counts"] == {"client_org": 1}


def test_a_catalog_mismatch_in_the_preview_is_a_typed_refusal(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """D-016: the preview refuses with {reason, message}, naming the field and
    never its content, not the global untyped 500."""
    from app.ai.catalog_fields import CATALOG_FIELDS

    c, TestSession, _provider = app_client
    h, svc_id = _service_for_cloud(c, TestSession)
    monkeypatch.setitem(
        CATALOG_FIELDS,
        "technique_details",
        lambda _payload, value: {
            code: {**d, "name": "Not the catalogue"} for code, d in value.items()
        },
    )

    r = c.post("/ai/preview", headers=h, json={"service_id": svc_id})

    assert r.status_code == 500, r.text
    error = r.json()["error"]
    assert {k: error[k] for k in ("reason", "message")} == {
        "reason": "catalog_field_mismatch",
        "message": (
            "The technique_details SHIELD would send to the AI does not match its "
            "catalog, so the preview was not built and nothing was sent."
        ),
    }
    assert "Cloud Services" not in r.text and "Not the catalogue" not in r.text
