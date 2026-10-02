"""#646 on the CSF, Zero Trust and Tech Debt client dashboards: each states the
AI source of the RELEASED subject, from the one derivation the deliverables
call. ATT&CK's is in `test_ai_source_attack.py`, Risk's in
`test_ai_source_risk_deliverable.py`.

The world is `test_value_summary.py`'s: released services built straight in
the database, as finalize leaves them.
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import select

from app.models.llm_call import LLMCallMode
from tests._ai_mode import FIXTURE, LIVE, env_sessions, seed_run, seed_unattributed_call
from tests.unit.test_value_summary import (  # noqa: F401  (fixture)
    _csf_codes,
    _make_released_csf,
    _make_released_tech_debt,
    _make_released_zt,
    _register,
    _session,
    _zt_cisa_codes,
    app_client,
)

pytestmark = pytest.mark.unit


def _world(c):
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    cid = client["user"]["client_id"]
    db = _session(c)
    _make_released_csf(
        db, _uuid.UUID(cid), _uuid.UUID(admin["user"]["id"]), gap_codes=_csf_codes(2)
    )
    _make_released_zt(
        db, _uuid.UUID(cid), _uuid.UUID(admin["user"]["id"]), gap_codes=_zt_cisa_codes(2)
    )
    _make_released_tech_debt(db, _uuid.UUID(cid), _uuid.UUID(admin["user"]["id"]), cut_costs=[1000])
    db.commit()
    db.close()
    return cid, {"Authorization": f"Bearer {client['tokens']['access_token']}"}


def _subjects(Sess) -> dict[str, tuple[str, str]]:
    """service kind -> (service id, subject id)."""
    from app.models.capability import CapabilityList
    from app.models.csf_assessment import CsfAssessment
    from app.models.zt_assessment import ZtAssessment

    with Sess() as s:
        csf = s.execute(select(CsfAssessment)).scalar_one()
        zt = s.execute(select(ZtAssessment)).scalar_one()
        cl = s.execute(select(CapabilityList)).scalar_one()
        return {
            "csf": (str(csf.service_id), str(csf.id)),
            "zt": (str(zt.service_id), str(zt.id)),
            "tech-debt": (str(cl.service_id), str(cl.id)),
        }


def test_each_dashboard_states_its_released_subjects_ai_source(app_client) -> None:  # noqa: F811
    c = app_client
    cid, h = _world(c)
    Sess = env_sessions()
    subj = _subjects(Sess)
    seed_run(
        Sess,
        service_id=subj["csf"][0],
        subject_id=subj["csf"][1],
        purpose="csf_score",
        mode=LLMCallMode.FIXTURE,
    )
    seed_run(
        Sess,
        service_id=subj["zt"][0],
        subject_id=subj["zt"][1],
        purpose="zt_score",
        mode=LLMCallMode.LIVE,
    )
    # Tech Debt: the run's subject is the uploaded document; its stored result
    # names the list it wrote.
    seed_run(
        Sess,
        service_id=subj["tech-debt"][0],
        subject_id=str(_uuid.uuid4()),
        purpose="tech_debt_extract",
        mode=LLMCallMode.FIXTURE,
        result={"capability_list_id": subj["tech-debt"][1]},
    )

    def _dash(kind: str) -> dict:
        r = c.get(f"/clients/{cid}/{kind}/{subj[kind][0]}/dashboard", headers=h)
        assert r.status_code == 200, r.text
        return r.json()["ai_source"]

    assert _dash("csf")["sentence"] == FIXTURE
    assert _dash("zt")["sentence"] == LIVE
    td = _dash("tech-debt")
    assert td["state"] == "fixture"
    assert "in this capability list" in td["sentence"]


def test_a_released_subject_with_no_run_says_none(app_client) -> None:  # noqa: F811
    c = app_client
    cid, h = _world(c)
    subj = _subjects(env_sessions())
    r = c.get(f"/clients/{cid}/csf/{subj['csf'][0]}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ai_source"]["state"] == "none"


def test_a_tech_debt_list_counts_only_the_run_that_wrote_it(app_client) -> None:  # noqa: F811
    """Another extraction's run -- one that wrote a different list -- says
    nothing about this one."""
    c = app_client
    cid, h = _world(c)
    Sess = env_sessions()
    svc, list_id = _subjects(Sess)["tech-debt"]
    seed_run(
        Sess,
        service_id=svc,
        subject_id=str(_uuid.uuid4()),
        purpose="tech_debt_extract",
        mode=LLMCallMode.FIXTURE,
        result={"capability_list_id": str(_uuid.uuid4())},
    )
    seed_run(
        Sess,
        service_id=svc,
        subject_id=str(_uuid.uuid4()),
        purpose="tech_debt_extract",
        mode=LLMCallMode.LIVE,
        result={"capability_list_id": list_id},
    )
    r = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ai_source"]["state"] == "live"


def test_a_list_extracted_before_756_says_not_recorded(app_client) -> None:  # noqa: F811
    """#778 review F1. A completed extraction call with no run (made before
    #756), and no run naming this list: nothing says which mode wrote it, so
    the client is told "not recorded" -- never "No AI suggestions were used"."""
    c = app_client
    cid, h = _world(c)
    Sess = env_sessions()
    svc, _list_id = _subjects(Sess)["tech-debt"]
    seed_unattributed_call(Sess, service_id=svc, purpose="extract.capabilities")
    r = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    src = r.json()["ai_source"]
    assert src["state"] == "unknown"
    assert src["sentence"] == (
        "It is not recorded whether the AI suggestions in this capability list came "
        "from a live AI model or from offline test data."
    )


def test_a_run_naming_the_list_wins_over_an_older_unattributed_call(
    app_client,  # noqa: F811
) -> None:
    """The rule: a list is written by exactly one extraction, so a completed run
    that names it IS the record of what wrote it; an unattributed call belongs
    to some other, older extraction of the service."""
    c = app_client
    cid, h = _world(c)
    Sess = env_sessions()
    svc, list_id = _subjects(Sess)["tech-debt"]
    seed_unattributed_call(Sess, service_id=svc, purpose="extract.capabilities")
    seed_run(
        Sess,
        service_id=svc,
        subject_id=str(_uuid.uuid4()),
        purpose="tech_debt_extract",
        mode=LLMCallMode.LIVE,
        result={"capability_list_id": list_id},
    )
    r = c.get(f"/clients/{cid}/tech-debt/{svc}/dashboard", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["ai_source"]["state"] == "live"
