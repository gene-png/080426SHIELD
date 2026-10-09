"""#474 D': Risk's CSF findings come from the Playbook, and every surface says so.

Gene (#736 5984218862) moved Risk's CSF findings from the questionnaire
`maturity_tier` to the Playbook Enterprise level against the Playbook target,
and (5984256202) kept the client's CSF dashboard on the self-assessment, so
the register states its CSF source wherever its CSF findings are shown: the
admin register, the client Risk dashboard and the three files. Only when the
register HAS CSF findings.

Also here, because they are the same change's other surfaces:

- the Inputs panel's CSF row says when the CSF record has no in-scope Playbook
  rows (it then feeds no CSF finding), and only CSF rows carry that flag;
- a CSF code is citable when an in-scope Playbook row has `answer_source` set
  (a pre-seeded 0 is "nobody wrote this", not a score).

Every expected string is the approved text, written out, never imported.
"""

from __future__ import annotations

import pytest

from app.ai.llm import LLMResponse
from tests._csf_playbook_rows import score_csf_playbook
from tests.unit.test_risk_baseline_disclosure import _client_dashboard, _latest, _world
from tests.unit.test_risk_per_service import _export_texts
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _seed_attack_and_zt,
    app_client,
)

pytestmark = pytest.mark.unit

#: Approved verbatim, #736 comment 5984256202.
SOURCE_NOTE = (
    "CSF risks in this register come from Kentro's evidence-based assessment. "
    "They can differ from your self-assessment on the CSF dashboard."
)


# --- the source note ------------------------------------------------------------


def test_the_admin_register_states_the_csf_source(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf=True)
    assert _latest(c, bearer, cid)["csf_source_note"] == SOURCE_NOTE


def test_a_register_with_no_csf_findings_states_no_csf_source(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf=False)
    body = _latest(c, bearer, cid)
    assert body["entries"], "the register exists and has entries"  # positive first
    assert body["csf_source_note"] is None


def test_the_client_dashboard_states_the_csf_source(app_client) -> None:  # noqa: F811
    c, bearer, cid = _world(app_client, csf=True)
    assert _client_dashboard(c, bearer, cid)["csf_source_note"] == SOURCE_NOTE


@pytest.mark.parametrize("csf", [True, False])
def test_every_file_states_the_csf_source_only_with_csf_findings(
    app_client, csf: bool  # noqa: F811
) -> None:
    c, bearer, cid = _world(app_client, csf=csf)
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        text = " ".join(texts[fmt].split())
        # The file rendered its summary: the Zero Trust target line is in
        # every file of this world. Positive first.
        assert "Zero Trust findings are measured against" in text, fmt
        assert (SOURCE_NOTE in text) is csf, (fmt, csf)


# --- the Inputs panel ---------------------------------------------------------


def _csf_service(c, bearer: str, cid: str) -> tuple[dict, str, str]:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return h, sid, a.json()["answers"][0]["subcategory_code"]


def _gate_rows(c, bearer: str, cid: str) -> list[dict]:
    g = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"})
    assert g.status_code == 200, g.text
    return g.json()["inputs"]


def test_a_csf_record_with_no_playbook_rows_is_flagged(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _csf_service(c, bearer, cid)
    rows = _gate_rows(c, bearer, cid)
    (csf,) = [r for r in rows if r["kind"] == "csf"]
    assert csf["engaged"] is True and csf["status"] == "draft", csf  # positive first
    assert csf["no_playbook_scores"] is True
    # Only CSF carries it: no other kind has a Playbook.
    assert all("no_playbook_scores" not in r for r in rows if r["kind"] != "csf"), rows


def test_a_csf_record_with_playbook_rows_is_not_flagged(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h, sid, code = _csf_service(c, bearer, cid)
    score_csf_playbook(c, h, sid, {code: (1, 5)})
    (csf,) = [r for r in _gate_rows(c, bearer, cid) if r["kind"] == "csf"]
    assert csf["no_playbook_scores"] is False


def test_a_seeded_but_unscored_playbook_is_flagged(app_client) -> None:  # noqa: F811
    """Seeded rows nobody scored are "no Playbook scores", the register's own
    `no_scores` state (#736 6087786886, item 4), not a Playbook that has them."""
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h, sid, _code = _csf_service(c, bearer, cid)
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    (csf,) = [r for r in _gate_rows(c, bearer, cid) if r["kind"] == "csf"]
    assert csf["engaged"] is True  # positive first
    assert csf["no_playbook_scores"] is True


def test_an_unengaged_csf_row_carries_no_flag(app_client) -> None:  # noqa: F811
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    (csf,) = [r for r in _gate_rows(c, bearer, cid) if r["kind"] == "csf"]
    assert csf["engaged"] is False  # positive first
    assert "no_playbook_scores" not in csf


# --- the citable rule ---------------------------------------------------------


def test_a_written_out_of_scope_playbook_row_is_not_citable(app_client) -> None:  # noqa: F811
    """`answer_source` alone is not enough: the row must be in scope. One row
    written in scope is citable; another written OUT of scope is not."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h, sid, code = _csf_service(c, bearer, cid)
    score_csf_playbook(c, h, sid, {code: (1, 5)})
    profile = c.get(f"/csf/services/{sid}/profile/high", headers=h).json()["rows"]
    other = next(r for r in profile if r["subcategory_code"] != code)
    r = c.patch(
        f"/csf/dimension-scores/{other['id']}",
        headers=h,
        json={"in_scope": False, "governance": 2},
    )
    assert r.status_code == 200, r.text
    a = c.get(f"/csf/services/{sid}/assessments/latest", headers=h).json()
    ap = c.post(f"/csf/assessments/{a['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text

    seen: list[dict] = []

    def capture(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse('{"entries": []}')

    provider.register("risk_synthesize", capture)
    gen = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert gen.status_code == 201, gen.text
    assert seen, "no risk_synthesize payload was captured"
    controls = set(seen[0]["valid_controls"])
    assert code in controls, controls  # the written in-scope row: positive first
    assert other["subcategory_code"] not in controls, controls


# --- the baseline reader ------------------------------------------------------

_E = {"origin": "live_at_generate"}


def test_the_reader_reads_a_playbook_csf_record() -> None:
    from app.risk.baseline import targets_used

    rows, recorded = targets_used(
        {
            "targets": {
                "csf": {
                    **_E,
                    "kind": "csf",
                    "framework": None,
                    "target": None,
                    "source": "playbook",
                }
            }
        }
    )
    assert recorded is True
    assert [(r.kind, r.target, r.source) for r in rows] == [("csf", None, "playbook")]


@pytest.mark.parametrize(
    "entry",
    [
        # Only CSF measures against the Playbook.
        {"kind": "zt", "framework": "dod_ztra", "target": None, "source": "playbook"},
        # A Playbook record names no single target...
        {"kind": "csf", "framework": None, "target": 3, "source": "playbook"},
        # ...and no other source may omit one.
        {"kind": "csf", "framework": None, "target": None, "source": "client"},
    ],
    ids=["zt-playbook", "csf-playbook-with-target", "csf-no-target-not-playbook"],
)
def test_a_playbook_record_out_of_shape_is_unreadable(entry: dict, capsys) -> None:
    from app.risk.baseline import targets_used

    assert targets_used({"targets": {"x": {**_E, **entry}}}) == ([], False)
    assert "risk_register_targets_unreadable" in capsys.readouterr().out
