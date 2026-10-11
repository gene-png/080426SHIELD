"""#474 D': a CSF Playbook that cannot measure anything says so on every surface.

Risk's CSF findings come from the Playbook. A Playbook with no target levels
set, or with no scores at all, yields no CSF finding, and before this the
register then printed "measured against each subcategory's target level", which
reads as "measured, no gaps". The advisor's ruling (#736 6087786886, item 4):
three Playbook states are recorded at generate, `measured`, `no_targets` and
`no_scores`, and for the last two the CSF target line is REPLACED, on every
surface the source note reaches, by the approved copy below (verbatim).

Every expected string is written out, never imported. Driven through generate
and read on the admin register, the client Risk dashboard and the three files.
"""

from __future__ import annotations

import pytest

from tests._csf_playbook_rows import score_csf_playbook
from tests.unit.test_risk_baseline_disclosure import _client_dashboard, _latest
from tests.unit.test_risk_per_service import _export_texts
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _generate,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

MEASURED = (
    "NIST CSF findings are measured against each subcategory's target level in the CSF Playbook."
)
#: Approved verbatim, #736 6087786886, item 4.
NO_TARGETS = (
    "NIST CSF was not measured for this register: the CSF Playbook has no target levels set."
)
NO_SCORES = "NIST CSF was not measured for this register: the CSF Playbook has no scores."
SOURCE_NOTE = (
    "CSF risks in this register come from Kentro's evidence-based assessment. "
    "They can differ from your self-assessment on the CSF dashboard."
)
LINES = {"measured": MEASURED, "no_targets": NO_TARGETS, "no_scores": NO_SCORES}
TOKENS = {
    "measured": "playbook",
    "no_targets": "playbook_no_targets",
    "no_scores": "playbook_no_scores",
}


def _world(app_client, state: str):  # noqa: F811
    """ATT&CK and ZT (the gate) plus an approved CSF assessment whose Playbook
    is, by state: scored with a target (`measured`); scored with no target
    (`no_targets`); seeded and never written (`no_scores`)."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    code = a.json()["answers"][0]["subcategory_code"]
    if state == "measured":
        score_csf_playbook(c, h, sid, {code: (1, 5)})
    elif state == "no_targets":
        score_csf_playbook(c, h, sid, {code: (3, None)})
    else:
        seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
        assert seeded.status_code in (200, 201), seeded.text
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    return c, bearer, cid


@pytest.mark.parametrize("state", ["measured", "no_targets", "no_scores"])
def test_the_admin_register_records_and_states_the_playbook_state(
    app_client, state: str  # noqa: F811
) -> None:
    c, bearer, cid = _world(app_client, state)
    body = _latest(c, bearer, cid)
    (csf,) = [t for t in body["targets"] if t["kind"] == "csf"]
    assert (csf["target"], csf["source"]) == (None, TOKENS[state])
    # The source note prints only with CSF findings, which only `measured`
    # can have here.
    assert body["csf_source_note"] == (SOURCE_NOTE if state == "measured" else None)


@pytest.mark.parametrize("state", ["measured", "no_targets", "no_scores"])
def test_the_client_dashboard_carries_the_playbook_state(
    app_client, state: str  # noqa: F811
) -> None:
    c, bearer, cid = _world(app_client, state)
    body = _client_dashboard(c, bearer, cid)
    (csf,) = [t for t in body["targets"] if t["kind"] == "csf"]
    assert csf["source"] == TOKENS[state]


@pytest.mark.parametrize("state", ["measured", "no_targets", "no_scores"])
def test_every_file_states_the_playbook_state(app_client, state: str) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, state)
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        assert LINES[state] in text, (fmt, state)  # what must appear, first
        for other, line in LINES.items():
            if other != state:
                assert line not in text, (fmt, state, other)


def test_a_csf_assessment_with_no_playbook_at_all_is_no_scores(app_client) -> None:  # noqa: F811
    """No profile seeded: no rows at all is "no scores", not "measured"."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    a = c.post(f"/csf/services/{svc.json()['id']}/assessments", headers=h)
    assert c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h).status_code == 200
    _generate(c, provider, bearer, cid, _entries_payload(_entry("R")))
    (csf,) = [t for t in _latest(c, bearer, cid)["targets"] if t["kind"] == "csf"]
    assert csf["source"] == "playbook_no_scores"
