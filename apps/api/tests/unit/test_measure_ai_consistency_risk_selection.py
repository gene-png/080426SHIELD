"""RR-1 (for #1122), design note §7: `measure_risk` runs the route's own
`_select`, so a measurement draws on the same services a register would.

#1148 review, finding 4: that path had no test. Pinned here:
* both Zero Trust frameworks and no `--risk-zero-trust`: refused with the
  route's own copy 6, never measured over a guess;
* a named framework: only that framework's findings are asked;
* `--risk-zero-trust none` on a client with no CSF: refused with copy 5c;
* one framework and no flag: the absent-body default measures it.

A new file rather than an edit to `test_measure_ai_consistency_risk.py`, which
exists on main; it borrows that file's helpers. Expected messages are §8's.
"""

from __future__ import annotations

import pytest
from scripts.measure_ai_consistency import Refused, measure_risk

from app.ai.llm import LLMClient

from .test_measure_ai_consistency_attack_tech_debt import (  # noqa: F401 -- fixtures
    _admin_client,
    world,
)
from .test_measure_ai_consistency_risk import _answer_every_finding, _approved_gaps

pytestmark = pytest.mark.unit

COPY_6 = "This client has both Zero Trust frameworks. Choose one for this register."
COPY_5C_CISA = (
    "Include Zero Trust (CISA ZTMM 2.0). ATT&CK coverage alone is not enough for a register."
)


def _approved_dod(c, h: dict) -> str:
    """A DoD ZT service with one capability at stage 1, approved."""
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT DoD"})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h).json()
    ans = a["answers"][0]
    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
    assert r.status_code == 200, r.text
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).status_code == 200
    return ans["capability_code"]


def test_both_frameworks_and_no_flag_is_refused_with_copy_6(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 2)
    _approved_dod(c, h)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db, pytest.raises(Refused) as caught:
        measure_risk(db, LLMClient(provider), runs=1)
    assert caught.value.reason == "builder_refused"
    assert str(caught.value) == COPY_6
    assert asked == [], "nothing is sent to the model"


@pytest.mark.parametrize("framework, prefix", [("dod_ztra", "DOD."), ("cisa_ztmm_2_0", "CISA.")])
def test_a_named_framework_measures_only_that_framework(
    framework, prefix, world  # noqa: F811
) -> None:
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 2)
    _approved_dod(c, h)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db:
        report = measure_risk(db, LLMClient(provider), runs=1, zero_trust=framework)
        db.commit()
    keys = [k for batch in asked for k in batch]
    zt_keys = [k for k in keys if k.startswith(("CISA.", "DOD."))]
    assert zt_keys, keys  # the positive state first: a ZT finding was asked
    assert all(k.startswith(prefix) for k in zt_keys), zt_keys
    assert report["runs_ok"] == 1


def test_zero_trust_none_without_csf_is_refused_with_copy_5c(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 2)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db, pytest.raises(Refused) as caught:
        measure_risk(db, LLMClient(provider), runs=1, zero_trust="none")
    assert caught.value.reason == "builder_refused"
    assert str(caught.value) == COPY_5C_CISA
    assert asked == []


def test_one_framework_and_no_flag_measures_it(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 2)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db:
        report = measure_risk(db, LLMClient(provider), runs=1)
        db.commit()
    keys = [k for batch in asked for k in batch]
    assert [k for k in keys if k.startswith("CISA.")], keys
    assert report["runs_ok"] == 1
