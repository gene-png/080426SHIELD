"""#984, #986: a ZT run asks the model about the real capability codes, even for
a client named "DoD" or "CISA", and still redacts the client's own notes.

Before this fix strict redaction rewrote every code in the payload's
`capabilities` list for such a client (all 45 DoD codes for "DoD", all 37 CISA
codes for "CISA", measured on main 2f701f5b), so the model was asked about
codes that do not exist, such as "[CLIENT].USR.01". Through the run and
`/ai/preview`. Expected codes come from the assessment the API returns.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from app.ai.redact import redact_payload
from tests._ai_runs import zt_run_ai
from tests.unit.test_zt_run_ai import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

#: (service kind, colliding client name, a code of that framework the model answers)
CASES = [
    ("zero_trust_dod", "DoD", "DOD.USR.02"),
    ("zero_trust_cisa", "CISA", "CISA.ID.02"),
]


def _service_for(c, kind: str, org: str) -> tuple[dict, str, list[dict]]:
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients", headers={"Authorization": f"Bearer {bearer}"}, json={"legal_name": org}
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post("/zt/services", headers=h, json={"kind": kind, "title": "ZT"}).json()["id"]
    answers = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()["answers"]
    notes = f"{org} staff review this capability weekly."
    r = c.patch(f"/zt/answers/{answers[0]['id']}", headers=h, json={"notes": notes})
    assert r.status_code == 200, r.text
    return h, svc_id, answers


@pytest.mark.parametrize(("kind", "org", "answered"), CASES)
def test_the_run_asks_about_the_real_codes_and_redacts_the_notes(
    app_client, kind, org, answered  # noqa: F811
) -> None:
    c, provider = app_client
    h, svc_id, answers = _service_for(c, kind, org)
    codes = sorted(a["capability_code"] for a in answers)
    out, _ = redact_payload({"capabilities": codes}, mode="strict", client_org_name=org)
    assert out["capabilities"] != codes, "the client name must collide for this to test anything"
    sent: list[dict] = []

    def _spy(payload: dict) -> LLMResponse:
        sent.append(payload)
        return LLMResponse('{"capabilities": [{"code": "' + answered + '", "current": 2}]}')

    provider.register("zt_score", _spy)
    body = zt_run_ai(c, svc_id, h)

    assert sent[0]["capabilities"] == codes
    first = answers[0]["capability_code"]
    assert sent[0]["answers"][first]["notes"] == "[CLIENT] staff review this capability weekly."
    row = next(x for x in body["answers"] if x["capability_code"] == answered)
    assert row["maturity_stage"] == 2, "a code the model was shown round-trips"


@pytest.mark.parametrize(("kind", "org", "answered"), CASES)
def test_the_preview_shows_the_real_codes_and_counts_only_the_notes(
    app_client, kind, org, answered  # noqa: F811
) -> None:
    c, _provider = app_client
    h, svc_id, answers = _service_for(c, kind, org)

    r = c.post("/ai/preview", headers=h, json={"service_id": svc_id})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["payload"]["capabilities"] == sorted(a["capability_code"] for a in answers)
    assert body["removed_counts"] == {"client_org": 1}
