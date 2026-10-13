"""RR-1 (for #1122), design note §6.1 and §9.1, through the CLIENT's surface:
the published Risk Register dashboard carries what the register was generated
from (copy 8's list), what was left out (9a/9b) and what had no assessment
(9c), or `selection_recorded: false` (copy 11) when it has no usable record.

#1148 review, finding 3: no API test read these four fields on the client
route, so dropping them there would leave every client dashboard printing
copy 11 with the suite green. Each state below is a real published register,
read by a client user. Expected labels are §8's.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse
from tests._risk_inputs import seed_released
from tests.unit.test_risk_per_service import _seed_dod
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

CISA_LABEL = "Zero Trust (CISA ZTMM 2.0)"
DOD_LABEL = "Zero Trust (DoD ZT Reference Architecture)"


def _client_user(c, bearer: str, cid: str) -> dict:
    ah = {"Authorization": f"Bearer {bearer}"}
    r = c.post(f"/admin/clients/{cid}/domains", headers=ah, json={"domain": "acme.example"})
    assert r.status_code in (200, 201), r.text
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    assert user.status_code == 201, user.text
    return {"Authorization": f"Bearer {user.json()['tokens']['access_token']}", "X-Client-Id": cid}


def _generate_and_publish(c, provider, bearer: str, cid: str, include: dict | None) -> None:
    # One rated entry, so the unrated-entry refusal never masks anything.
    provider.register_static("risk_synthesize", LLMResponse(_entries_payload(_entry("R"))))
    kw = {} if include is None else {"json": {"include": include}}
    ah = {"Authorization": f"Bearer {bearer}"}
    gen = c.post(f"/risk/clients/{cid}/register/generate", headers=ah, **kw)
    assert gen.status_code == 201, gen.text
    pub = c.post(f"/risk/clients/{cid}/register/publish", headers=ah)
    assert pub.status_code == 200, pub.text


def _dashboard(c, ch: dict, cid: str) -> dict:
    r = c.get(f"/clients/{cid}/risk/dashboard", headers=ch)
    assert r.status_code == 200, r.text
    return r.json()


def _fields(d: dict) -> tuple:
    return (
        d["selection_recorded"],
        d["covered_inputs"],
        d["deselected_inputs"],
        d["ineligible_inputs"],
    )


def test_a_register_that_left_nothing_out(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    ch = _client_user(c, bearer, cid)
    seed_released(c, bearer, cid)
    _generate_and_publish(c, provider, bearer, cid, None)
    assert _fields(_dashboard(c, ch, cid)) == (
        True,
        ["ATT&CK coverage", "Zero Trust"],
        [],
        [],
    )


def test_a_register_that_left_a_framework_out(app_client) -> None:  # noqa: F811
    """DoD approved (not released) and left out: deselected, so it neither
    blocks publish nor reaches the covered list; two ZT services are
    mentioned, so each is named (§6.2)."""
    c, provider = app_client
    bearer, cid = _admin(c)
    ch = _client_user(c, bearer, cid)
    seed_released(c, bearer, cid)
    _seed_dod(c, bearer, cid)
    _generate_and_publish(c, provider, bearer, cid, {"csf": False, "zero_trust": "cisa_ztmm_2_0"})
    assert _fields(_dashboard(c, ch, cid)) == (
        True,
        ["ATT&CK coverage", CISA_LABEL],
        [DOD_LABEL],
        [],
    )


def test_a_register_with_an_engaged_service_that_had_no_assessment(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    ch = _client_user(c, bearer, cid)
    seed_released(c, bearer, cid)
    ah = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    dod = c.post("/zt/services", headers=ah, json={"kind": "zero_trust_dod", "title": "ZT DoD"})
    assert dod.status_code in (200, 201), dod.text
    _generate_and_publish(c, provider, bearer, cid, None)
    assert _fields(_dashboard(c, ch, cid)) == (
        True,
        ["ATT&CK coverage", CISA_LABEL],
        [],
        [DOD_LABEL],
    )


def test_a_published_register_with_no_usable_selection_says_so(app_client) -> None:  # noqa: F811
    """A register published before RR-1 recorded no `selection`: the client's
    dashboard reports `selection_recorded: false` (copy 11), and lists
    nothing as covered."""
    from app.models.risk_register import RiskRegister

    c, provider = app_client
    bearer, cid = _admin(c)
    ch = _client_user(c, bearer, cid)
    seed_released(c, bearer, cid)
    _generate_and_publish(c, provider, bearer, cid, None)
    assert _fields(_dashboard(c, ch, cid))[0] is True  # the positive state first
    with _session() as s:
        reg = s.execute(
            select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid))
        ).scalar_one()
        prov = dict(reg.provenance)
        prov.pop("selection")
        reg.provenance = prov
        s.commit()
    assert _fields(_dashboard(c, ch, cid)) == (False, [], [], [])
