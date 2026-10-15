"""#981 x #985: ZT's `capability_details` goes through the catalog guard.

The field is catalog text (each capability's pillar and name, and for DoD its
roadmap activities), so it egresses unredacted and guarded, like ZT's
`capabilities`: rebuilt from the catalog before and after redaction and
compared byte for byte, or the run fails before anything is sent.

Both tests go through the ZT Run-AI (`/zt/services/{id}/run-ai`), the egress
path a consultant reaches, not the guard helper alone. Expected details come
from the catalog's public accessors, never from the route's
`_zt_capability_details`. Each collision test first proves the client name
really collides (plain `redact_payload` rewrites the details), so it cannot
pass vacuously; it mirrors #985's per-service tests in
`test_catalog_fields_redaction.py` ("DoD" and "Data" for DoD).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.ai.redact import redact_payload
from app.models.client import Client
from app.models.llm_call import LLMCall
from tests._ai_runs import run_ai_expecting_failure, zt_run_ai
from tests.unit.test_zt_run_ai_v2 import World, world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _catalog_details(framework: str, codes: list[str]) -> dict[str, dict]:
    """What the catalog says each code's entry is, from its public accessors."""
    from app.zt.catalog import capability_by_code, pillar_by_code
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode(framework)
    out: dict[str, dict] = {}
    for code in codes:
        cap = capability_by_code(code)
        entry: dict[str, Any] = {
            "pillar": pillar_by_code(fw, cap.pillar_code).name,
            "name": cap.name,
        }
        if fw == ZtFrameworkCode.DOD_ZTRA:
            entry["activities"] = [
                {"id": a.id, "name": a.name, "level": a.level, "description": a.description}
                for a in cap.activities
            ]
        out[code] = entry
    return out


def _name_the_client(world: World, org: str) -> None:  # noqa: F811
    cid = world.h["X-Client-Id"]
    with world.sessions() as db:
        db.get(Client, uuid.UUID(cid)).legal_name = org
        db.commit()


def _llm_calls(world: World) -> list[LLMCall]:  # noqa: F811
    with world.sessions() as db:
        return list(db.execute(select(LLMCall)).scalars().all())


@pytest.mark.parametrize(
    ("kind", "framework", "org"),
    [
        ("zero_trust_dod", "dod_ztra", "DoD"),
        ("zero_trust_dod", "dod_ztra", "Data"),
        ("zero_trust_cisa", "cisa_ztmm_2_0", "Identity"),
    ],
)
def test_a_client_named_a_catalog_word_does_not_rewrite_capability_details(
    world, kind, framework, org  # noqa: F811
) -> None:
    world.service(kind)
    _name_the_client(world, org)
    world.patch(0, notes=f"{org} staff run this weekly.")
    noted = world.answers[0]["capability_code"]
    seen = world.capture({"capabilities": []})

    zt_run_ai(world.c, world.svc_id, world.h)

    assert len(seen) == 1, "the provider was not called exactly once"
    sent = seen[0]
    codes = sorted(a["capability_code"] for a in world.answers)
    expected = _catalog_details(framework, codes)
    assert _collides(expected, org), "the client name must collide for this to test anything"
    assert json.dumps(sent["capability_details"]) == json.dumps(expected)
    assert sent["answers"][noted]["notes"] == "[CLIENT] staff run this weekly."
    # Catalog text is not counted as a client-name removal; the notes hit is.
    assert [r.redacted_counts for r in _llm_calls(world)] == [{"client_org": 1}]


def _collides(details: dict[str, dict], org: str) -> bool:
    out, _ = redact_payload({"capability_details": details}, mode="strict", client_org_name=org)
    return out["capability_details"] != details


_TOKEN = "ZEBRA-PRIVATE-NOTE-4417"


def test_a_tampered_capability_details_entry_is_refused_before_any_provider_call(
    world, monkeypatch  # noqa: F811
) -> None:
    """Client text under the exempt key would egress unredacted, so the run
    refuses it before the provider is called or an `llm_calls` row is
    written, and the refusal names the field, never the entry's value."""
    import app.routes.zt as zt_routes

    real = zt_routes._zt_ai_request_for

    def _tampered(db, a, client):  # type: ignore[no-untyped-def]
        req = real(db, a, client)
        details = req.preview.inputs["capability_details"]
        first = next(iter(details))
        details[first] = {**details[first], "name": _TOKEN}
        return req

    monkeypatch.setattr(zt_routes, "_zt_ai_request_for", _tampered)
    world.service("zero_trust_cisa")
    seen = world.capture({"capabilities": []})

    run = run_ai_expecting_failure(world.c, f"/zt/services/{world.svc_id}/run-ai", world.h)

    assert seen == [], "the provider must not be called"
    assert _llm_calls(world) == [], "no llm_calls row may be written"
    assert run["error_reason"] == "ai_call_failed", run
    assert run["error_message"] == (
        "The AI call failed and nothing was applied. (CatalogFieldMismatch: payload "
        "field 'capability_details' is not the catalog's text before redaction "
        "(entry 0, a dict); nothing was sent)"
    ), run["error_message"]
    assert _TOKEN not in json.dumps(run)
