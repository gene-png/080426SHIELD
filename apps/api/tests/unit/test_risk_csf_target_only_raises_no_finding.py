"""#474 D': a target-only Playbook row raises no CSF Risk finding.

Gene's ruling (#736 6101751588, option (a), on the truth table in 6090645729):
a finding needs a recorded value other than its target, the predicate
`measured` uses. Before it, one row with a target and nothing else scored
read "not measured" AND listed "CSF GV.OC-02: level 1 of target 4", with the
source note beside it. Such a row is counted and disclosed as before: the
`no_scores` state, the "not measured" CSF line and the Inputs panel's
`no_playbook_scores`.

Driven through the real routes: a seeded Playbook, one target-only PATCH,
approve, then generate. Every expected string is written out.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.llm import LLMResponse
from tests.unit.test_risk_baseline_disclosure import _client_dashboard, _latest
from tests.unit.test_risk_per_service import _export_texts
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

NO_SCORES = "NIST CSF was not measured for this register: the CSF Playbook has no scores."
SOURCE_NOTE = (
    "CSF risks in this register come from Kentro's evidence-based assessment. "
    "They can differ from your self-assessment on the CSF dashboard."
)


def _target_only_world(app_client) -> tuple[Any, str, str, dict[str, Any]]:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    row = c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"][0]
    r = c.patch(f"/csf/dimension-scores/{row['id']}", headers=h, json={"target_level": 4})
    assert r.status_code == 200, r.text
    assert r.json()["target_level"] == 4, r.json()
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text

    seen: list[dict[str, Any]] = []

    def capture(payload: dict[str, Any]) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(_entries_payload(_entry("R")))

    provider.register("risk_synthesize", capture)
    gen = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert gen.status_code == 201, gen.text
    assert seen, "no risk_synthesize payload was captured"
    return c, bearer, cid, seen[0]


def test_a_target_only_row_raises_no_csf_finding_and_reads_not_measured(
    app_client,  # noqa: F811
) -> None:
    c, bearer, cid, payload = _target_only_world(app_client)

    # Positive first: the register exists, the other services fed findings,
    # and the not-measured state is recorded and stated.
    body = _latest(c, bearer, cid)
    assert body["entries"], "the register exists and has entries"
    # #474 E: `findings` is keyed by `source_id` (ruling 6).
    assert any(f["kind"] != "csf" for f in payload["findings"].values()), payload["findings"]
    (csf,) = [t for t in body["targets"] if t["kind"] == "csf"]
    assert (csf["target"], csf["source"]) == (None, "playbook_no_scores"), csf
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        assert NO_SCORES in " ".join(texts[fmt].split()), fmt
    g = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"})
    assert g.status_code == 200, g.text
    (inp,) = [r for r in g.json()["inputs"] if r["kind"] == "csf"]
    assert inp["engaged"] is True
    assert inp["no_playbook_scores"] is True

    # Then the absences: no CSF finding, so no source note on any surface.
    assert [sid for sid, f in payload["findings"].items() if f["kind"] == "csf"] == []
    assert body["csf_source_note"] is None
    for fmt in ("pdf", "docx", "xlsx"):
        assert SOURCE_NOTE not in " ".join(texts[fmt].split()), fmt
    assert _client_dashboard(c, bearer, cid)["csf_source_note"] is None
