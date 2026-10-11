"""The consistency measure for risk_synthesize (#474 E, ruling 8: after-only).

The properties `test_measure_ai_consistency_attack_tech_debt.py` pins for
mitre_map, pinned here for Risk:

* the production path is CALLED -- `_gather_findings` and
  `_run_risk_synthesize_batched` -- and nothing is stored: no register, no entry;
* agreement is per field with denominators, compared as `generate` would STORE
  each value, so a token typed two ways agrees and a link off the allow-list is
  no link;
* LIST fields are sets with a Jaccard, and two empty lists are no agreement;
* a run with a failed batch is a failed run, never "0% agreement";
* the figure a client would see, the tier, comes from `tier_for`.

Model responses are written from the approved prompt's JSON shape (`{"entries":
[{"title", ..., "axis", "other_axes", "linked_techniques", "linked_controls",
"likelihood", "impact", ..., "source", "source_id"}]}`), not from the parser.
Nothing here is live: the provider is the fixture provider.
"""

from __future__ import annotations

import json

import pytest
from scripts.measure_ai_consistency import RiskScope, compare_pair, main, measure_risk
from sqlalchemy import func, select

from app.ai.llm import LLMClient, LLMResponse
from app.models.risk_register import RiskEntry, RiskRegister
from tests._attack_rows import standalone_rows

from .test_measure_ai_consistency_attack_tech_debt import (  # noqa: F401 -- fixtures
    _admin_client,
    _llm_call_count,
    cli,
    world,
)

pytestmark = pytest.mark.unit

_S = RiskScope(
    source_ids=frozenset({"T1", "T2"}),
    valid_techniques=frozenset({"T1", "T2"}),
    valid_controls=frozenset({"GV.OC-01"}),
)


def _entry(sid: str, **over: object) -> dict:
    e: dict[str, object] = {
        "title": "t",
        "description": "d",
        "axis": "detection",
        "other_axes": [],
        "linked_techniques": [sid],
        "linked_controls": [],
        "likelihood": "high",
        "impact": "major",
        "compensating_controls": "None identified in the supplied information.",
        "residual_risk": "r",
        "recommended_action": "remediate",
        "rationale": "r",
        "source": "coverage_finding",
        "source_id": sid,
    }
    e.update(over)
    return e


def test_a_token_typed_two_ways_is_one_stored_value() -> None:
    a = {"entries": [_entry("T1", likelihood="Very High")]}
    b = {"entries": [_entry("T1", likelihood="very_high")]}
    d = compare_pair("risk_synthesize", a, b, context=_S)["fields"]["likelihood"]
    assert (d["compared"], d["equal"], d["one_absent"], d["both_absent"]) == (1, 1, 0, 0)


def test_an_unresolvable_token_is_refused_never_agreement() -> None:
    a = {"entries": [_entry("T1", impact="severe")]}
    b = {"entries": [_entry("T1", impact="severe")]}
    d = compare_pair("risk_synthesize", a, b, context=_S)["fields"]["impact"]
    assert (d["compared"], d["equal"], d["both_absent"]) == (1, 0, 1)


def test_links_are_compared_as_stored_sets() -> None:
    # T9 is not on the allow-list, so generate keeps only T1 on both sides.
    a = {"entries": [_entry("T1", linked_techniques=["T1", "T9"])]}
    b = {"entries": [_entry("T1", linked_techniques=["T1"])]}
    d = compare_pair("risk_synthesize", a, b, context=_S)["fields"]["linked_techniques"]
    assert (d["judged"], d["equal"], d["mean_jaccard"]) == (1, 1, 1.0)
    # Every link off the list: nothing stored, so refused, not agreement.
    c = {"entries": [_entry("T1", linked_techniques=["T9"])]}
    d = compare_pair("risk_synthesize", c, c, context=_S)["fields"]["linked_techniques"]
    assert (d["judged"], d["equal"], d["both_absent"]) == (0, 0, 1)


def test_other_axes_are_sets_and_two_empty_lists_are_not_agreement() -> None:
    a = {"entries": [_entry("T1", other_axes=["response", "prevention"]), _entry("T2")]}
    b = {"entries": [_entry("T1", other_axes=["prevention", "response"]), _entry("T2")]}
    d = compare_pair("risk_synthesize", a, b, context=_S)["fields"]["other_axes"]
    assert (d["compared"], d["judged"], d["equal"], d["both_absent"]) == (2, 1, 1, 1)
    assert d["mean_jaccard"] == 0.5


def test_an_entry_naming_no_finding_is_refused() -> None:
    a = {"entries": [_entry("T7")]}
    d = compare_pair("risk_synthesize", a, a, context=_S)["fields"]["axis"]
    assert (d["compared"], d["equal"], d["both_absent"]) == (1, 0, 1)


def test_a_comparison_without_a_risk_scope_is_refused() -> None:
    with pytest.raises(TypeError, match="risk_synthesize needs a RiskScope"):
        compare_pair("risk_synthesize", {"entries": []}, {"entries": []}, context=None)


# --- measure_risk, through the route's own findings and batching ------------


def _approved_gaps(c, h: dict, n: int) -> list[str]:
    """`n` ATT&CK gaps and one ZT finding, both approved: an unlocked register."""
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h).json()
    codes = []
    for cov in standalone_rows(a["coverage"], n):
        r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
        assert r.status_code == 200, r.text
        codes.append(cov["technique_code"])
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h).json()
    ans = za["answers"][0]
    r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 1})
    assert r.status_code == 200, r.text
    assert c.post(f"/zt/assessments/{za['id']}/approve", headers=h).status_code == 200
    return codes


def _answer_every_finding(asked: list[list[str]], *, fail_second_batch: bool = False):
    """One prompt-shaped entry per key of `findings`, recording what was asked."""

    def respond(payload: dict) -> LLMResponse:
        asked.append(list(payload["findings"]))
        if fail_second_batch and len(asked) == 2:
            raise RuntimeError("provider down")
        entries = [
            _entry(sid, source=f["source"], linked_techniques=[], other_axes=["response"])
            for sid, f in payload["findings"].items()
        ]
        return LLMResponse(json.dumps({"entries": entries}), input_tokens=3, output_tokens=5)

    return respond


def _register_rows(db) -> tuple[int, int]:
    regs = db.execute(select(func.count()).select_from(RiskRegister)).scalar_one()
    ents = db.execute(select(func.count()).select_from(RiskEntry)).scalar_one()
    return regs, ents


def test_measure_risk_runs_every_batch_and_stores_nothing(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    codes = _approved_gaps(c, h, 21)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db:
        report = measure_risk(db, LLMClient(provider), runs=2)
        db.commit()
    with TestSession() as db:
        assert _register_rows(db) == (0, 0), "a measurement stores no register"
        calls = _llm_call_count(db)

    batches = len(asked) // 2
    assert batches > 1, "precondition: more than one batch"
    # Every finding asked once per run: the 21 gaps and the one ZT capability.
    assert report["findings_sent"] == 22
    assert sorted(set(codes) - {k for b in asked for k in b}) == []
    assert report["runs_ok"] == 2
    assert report["batches_per_run"] == batches
    assert calls == len(asked)
    pair = report["pairs"][0]
    assert pair["rows"]["in_both"] == 22
    assert pair["fields"]["likelihood"]["equal"] == 22
    assert pair["fields"]["other_axes"]["mean_jaccard"] == 1.0
    # high x major, by the 5x5 matrix: what the client would see, every finding.
    assert pair["tier"] == {
        "compared": 22,
        "judged": 22,
        "equal": 22,
        "both_unrated": 0,
        "one_unrated": 0,
    }
    assert report["exit_code"] == 0


def test_a_risk_run_with_a_failed_batch_is_a_failed_run(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 21)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked, fail_second_batch=True))
    with TestSession() as db:
        report = measure_risk(db, LLMClient(provider), runs=2)
    assert report["failed_runs"][0]["run"] == 1
    assert report["failed_runs"][0]["failure"].startswith("batches_failed:1/")
    assert report["exit_code"] == 1


def test_a_risk_probe_sends_only_the_first_batch(world) -> None:  # noqa: F811
    c, TestSession, provider = world
    h, _cid, _uid = _admin_client(c)
    _approved_gaps(c, h, 21)
    asked: list[list[str]] = []
    provider.register("risk_synthesize", _answer_every_finding(asked))
    with TestSession() as db:
        report = measure_risk(db, LLMClient(provider), runs=2, probe_batches=1)
    assert len(asked) == 2, "one batch per run"
    assert report["probe"]["batches"] == 1 and report["probe"]["of"] > 1
    assert report["findings_sent"] == len(asked[0])
    assert report["exit_code"] == 0


def test_main_refuses_to_reopen_for_risk(cli, capsys) -> None:  # noqa: F811
    built, tmp_path = cli
    argv = ["--job", "risk_synthesize", "--runs", "2", "--reopen-released"]
    code = main([*argv, "--out", str(tmp_path / "o.json")])
    assert "REFUSED (reopen_not_applicable)" in capsys.readouterr().err
    assert code == 2
