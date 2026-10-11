"""#474 D', ruling R10 (#736 6102665946): a CSF finding needs ONE tier row
that is both scored and targeted.

A Playbook row is one TIER. Before R10 a subcategory raised a finding when any
tier row carried a recorded value, so a score on HIGH beside a target on
MODERATE raised "level 1 of target 4" from a target-only row plus seed
defaults (round 6, F1), and a score on code A beside a target on code B read
`measured` over zero CSF findings (F2). R10:

- a finding needs a code with at least one in-scope tier row carrying BOTH a
  recorded non-target value AND a target; the level stays the roll-up's;
- `measured` needs at least one such code, otherwise `playbook_no_scores`;
- when it measured, every other targeted code is counted, persisted, and
  stated in approved copy on the Inputs panel and in the three files;
- R11 (#736 6103383277): scores and targets that never share a row get their
  own not-measured line; the true no-scores case keeps the original line.

Driven through the real routes: scores through the CSF Run-AI (a registered
provider response), targets through the consultant's target-only PATCH,
approve, then generate. Every expected string is written out.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.llm import LLMResponse
from app.csf.catalog import SUBCATEGORIES
from tests._ai_runs import csf_run_ai, csf_scores_by_batch
from tests.unit.test_risk_baseline_disclosure import _latest
from tests.unit.test_risk_per_service import _export_texts
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _entries_payload,
    _entry,
    _seed_attack_and_zt,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

_GV = [s.code for s in SUBCATEGORIES if s.code.startswith("GV.")]
A, B, C = _GV[0], _GV[1], _GV[2]

NO_SCORES = "NIST CSF was not measured for this register: the CSF Playbook has no scores."
MEASURED = (
    "NIST CSF findings are measured against each subcategory's target level in the CSF " "Playbook."
)
# R11 (#736 6103383277): scores and targets exist but never share a row.
NO_SHARED_ROW = (
    "NIST CSF was not measured for this register: no CSF Playbook row has both a score "
    "and a target."
)
ONE = "1 targeted subcategory has no row with both a score and a target, and raises no " "finding."
TWO = (
    "2 targeted subcategories have no row with both a score and a target, and raise no " "finding."
)


def _world(
    app_client,  # noqa: F811
    *,
    tiers: list[str],
    scored: list[tuple[str, str]],
    targeted: list[tuple[str, str]],
    out_of_scope: list[tuple[str, str]] = (),
) -> tuple[Any, str, str, dict[str, Any]]:
    """A Playbook seeded with `tiers`. `scored`: (tier, code) rows the Run-AI
    scores at governance 2, policy 1. `targeted`: (tier, code) rows given
    target level 4 by a target-only PATCH. `out_of_scope`: (tier, code) rows
    then PATCHed `in_scope: false`, which keeps their values and target.
    Approved, then generated; returns
    the client, bearer, client id and the synthesis payload."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    sid = svc.json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": tiers})
    assert seeded.status_code in (200, 201), seeded.text

    if scored:
        from app.ai.llm import LLMClient
        from app.routes.csf import _llm_dep as csf_llm_dep

        c.app.dependency_overrides[csf_llm_dep] = lambda: LLMClient(provider)
        provider.register(
            "csf_score",
            csf_scores_by_batch(
                [
                    {"tier": t, "subcategory_code": code, "governance": 2, "policy": 1}
                    for t, code in scored
                ],
                tiers=tiers,
                codes=[s.code for s in SUBCATEGORIES],
            ),
        )
        run = csf_run_ai(c, sid, h, serves="offline")
        n = 2 * len(scored)
        assert run["suggestions_received"] == n and run["suggestions_applied"] == n, run

    for tier, code in targeted:
        rows = {
            r["subcategory_code"]: r
            for r in c.get(f"/csf/services/{sid}/profile/{tier}", headers=h).json()["rows"]
        }
        r = c.patch(
            f"/csf/dimension-scores/{rows[code]['id']}", headers=h, json={"target_level": 4}
        )
        assert r.status_code == 200, r.text
        assert r.json()["target_level"] == 4, r.json()
    for tier, code in out_of_scope:
        rows = {
            r["subcategory_code"]: r
            for r in c.get(f"/csf/services/{sid}/profile/{tier}", headers=h).json()["rows"]
        }
        r = c.patch(
            f"/csf/dimension-scores/{rows[code]['id']}", headers=h, json={"in_scope": False}
        )
        assert r.status_code == 200, r.text
        # The PATCH keeps the row's target and score: only scope changes.
        assert (r.json()["in_scope"], r.json()["target_level"]) == (False, 4), r.json()
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


def _csf_input(c, bearer: str, cid: str) -> dict[str, Any]:
    g = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"})
    assert g.status_code == 200, g.text
    (inp,) = [r for r in g.json()["inputs"] if r["kind"] == "csf"]
    assert inp["engaged"] is True, inp
    return inp


def _csf_target(body: dict[str, Any]) -> dict[str, Any]:
    (csf,) = [t for t in body["targets"] if t["kind"] == "csf"]
    assert csf["target"] is None, csf
    return csf


def _flat(text: str) -> str:
    return " ".join(text.split())


def _assert_not_measured_and_no_finding(world, *, no_shared_row: bool) -> None:
    """`no_shared_row`: scores and targets exist but never share a row (R11's
    line), rather than no in-scope row having a recorded non-target value
    (the original no-scores line). Both record `playbook_no_scores`."""
    c, bearer, cid, payload = world
    line, other = (NO_SHARED_ROW, NO_SCORES) if no_shared_row else (NO_SCORES, NO_SHARED_ROW)
    # Positive first: the register exists, other services fed findings, and
    # the not-measured state is recorded and stated in all three files.
    body = _latest(c, bearer, cid)
    assert body["entries"], "the register exists and has entries"
    assert any(f["kind"] != "csf" for f in payload["findings"]), payload["findings"]
    assert _csf_target(body)["source"] == "playbook_no_scores"
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        assert line in _flat(texts[fmt]), fmt
    inp = _csf_input(c, bearer, cid)
    assert inp["no_playbook_scores"] is (not no_shared_row), inp
    assert inp["no_shared_playbook_row"] is no_shared_row, inp
    assert inp["unscored_targeted_subcategories"] == 0, inp
    # Then the absences: no CSF finding, and no count sentence in any file.
    assert [f for f in payload["findings"] if f["kind"] == "csf"] == []
    for fmt in ("pdf", "docx", "xlsx"):
        assert MEASURED not in _flat(texts[fmt]), fmt
        assert other not in _flat(texts[fmt]), fmt
        assert "targeted subcategor" not in _flat(texts[fmt]), fmt


def test_a_score_on_one_tier_and_a_target_on_another_raise_no_finding(
    app_client,  # noqa: F811
) -> None:
    """F1: HIGH scored with no target, MODERATE target-only, one code."""
    _assert_not_measured_and_no_finding(
        _world(
            app_client,
            tiers=["high", "moderate"],
            scored=[("high", A)],
            targeted=[("moderate", A)],
        ),
        no_shared_row=True,
    )


def test_a_score_on_code_a_and_a_target_on_code_b_read_not_measured(
    app_client,  # noqa: F811
) -> None:
    """F2: code A scored with no target, code B target-only."""
    _assert_not_measured_and_no_finding(
        _world(app_client, tiers=["high"], scored=[("high", A)], targeted=[("high", B)]),
        no_shared_row=True,
    )


@pytest.mark.parametrize(
    ("target_only", "sentence"),
    [([B], ONE), ([B, C], TWO)],
    ids=["one_target_only_code_singular", "two_target_only_codes_plural"],
)
def test_the_partial_case_raises_the_finding_and_states_the_count(
    app_client, target_only: list[str], sentence: str  # noqa: F811
) -> None:
    """A's HIGH row is scored AND targeted, so A raises its finding; every
    target-only code is counted and the approved sentence is stated."""
    c, bearer, cid, payload = _world(
        app_client,
        tiers=["high"],
        scored=[("high", A)],
        targeted=[("high", A), *(("high", code) for code in target_only)],
    )
    # Positive first: A's finding, the measured state, and the count with the
    # CSF line on the Inputs panel and in all three files.
    csf = [f for f in payload["findings"] if f["kind"] == "csf"]
    assert [f["source_id"] for f in csf] == [A], csf
    assert csf[0]["label"].startswith(f"CSF {A}: level "), csf
    assert csf[0]["label"].endswith(" of target 4"), csf
    body = _latest(c, bearer, cid)
    assert _csf_target(body)["source"] == "playbook"
    inp = _csf_input(c, bearer, cid)
    assert inp["no_playbook_scores"] is False, inp
    assert inp["no_shared_playbook_row"] is False, inp
    assert inp["unscored_targeted_subcategories"] == len(target_only), inp
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        flat = _flat(texts[fmt])
        assert MEASURED in flat, fmt
        assert sentence in flat, fmt
        # With the CSF line: the sentence follows it.
        assert flat.index(sentence) > flat.index(MEASURED), fmt
    # Then the absences: no target-only code raises a finding, and the
    # not-measured line is not printed.
    assert not {f["source_id"] for f in csf} & set(target_only)
    for fmt in ("pdf", "docx", "xlsx"):
        assert NO_SCORES not in _flat(texts[fmt]), fmt
        assert NO_SHARED_ROW not in _flat(texts[fmt]), fmt


def test_every_targeted_code_scored_and_targeted_states_no_count(
    app_client,  # noqa: F811
) -> None:
    """n = 0: the sentence appears only when some targeted code is unscored."""
    c, bearer, cid, payload = _world(
        app_client, tiers=["high"], scored=[("high", A)], targeted=[("high", A)]
    )
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        assert MEASURED in _flat(texts[fmt]), fmt
    assert _csf_input(c, bearer, cid)["unscored_targeted_subcategories"] == 0
    for fmt in ("pdf", "docx", "xlsx"):
        assert "targeted subcategor" not in _flat(texts[fmt]), fmt


def test_an_out_of_scope_scored_and_targeted_row_measures_nothing(
    app_client,  # noqa: F811
) -> None:
    """Round 7, F1: A's only scored-and-targeted row is set out of scope. The
    roll-up skips it, so it must not make the Playbook read measured. No
    in-scope row then has a recorded value: the TRUE no-scores case, so the
    original line (R11 keeps it)."""
    world = _world(
        app_client,
        tiers=["high"],
        scored=[("high", A)],
        targeted=[("high", A)],
        out_of_scope=[("high", A)],
    )
    _assert_not_measured_and_no_finding(world, no_shared_row=False)


def _store_no_shared_row(cid: str, value: object, *, present: bool) -> None:
    """Rewrite the stored record as another writer left it. `present=False`:
    the provenance an older (pre-R11) generate wrote, every key but
    `csf_no_shared_row`. Otherwise the key holds `value` as stored."""
    import uuid

    from sqlalchemy import select

    from app.models.risk_register import RiskRegister

    with _session() as s:
        reg = s.execute(
            select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid))
        ).scalar_one()
        prov = dict(reg.provenance)
        assert prov["csf_no_shared_row"] is True, prov  # the world is the A/B case
        if present:
            prov["csf_no_shared_row"] = value
        else:
            del prov["csf_no_shared_row"]
        reg.provenance = prov
        s.commit()


def _old_register_world(app_client):  # noqa: F811
    """The A/B case (scores and targets on different rows), generated."""
    return _world(app_client, tiers=["high"], scored=[("high", A)], targeted=[("high", B)])


def _assert_original_no_scores_line(c, bearer: str, cid: str) -> None:
    # Positive first: the register reads not measured, and the files print
    # the ORIGINAL no-scores line; then the R11 line is absent.
    assert _csf_target(_latest(c, bearer, cid))["source"] == "playbook_no_scores"
    texts = _export_texts(c, bearer, cid)
    for fmt in ("pdf", "docx", "xlsx"):
        assert NO_SCORES in _flat(texts[fmt]), fmt
    for fmt in ("pdf", "docx", "xlsx"):
        assert NO_SHARED_ROW not in _flat(texts[fmt]), fmt


def test_a_pre_r11_register_keeps_the_original_no_scores_line(
    app_client, capsys  # noqa: F811
) -> None:
    """A register whose provenance has no `csf_no_shared_row` key, as every
    register generated before R11 has: no claim either way, so the line it
    always printed, and no error logged (absence is not a fault)."""
    c, bearer, cid, _payload = _old_register_world(app_client)
    _store_no_shared_row(cid, None, present=False)
    capsys.readouterr()
    _assert_original_no_scores_line(c, bearer, cid)
    assert "risk.csf_no_shared_row.unreadable" not in capsys.readouterr().out


def test_an_unreadable_no_shared_row_value_keeps_the_original_line_and_is_logged(
    app_client, capsys  # noqa: F811
) -> None:
    """A non-bool stored value (the string "true") is unreadable: the original
    line, never the R11 one read from truthiness, and the fault is logged.
    `capsys`: structlog renders to stdout (`test_risk_link_scope.py`)."""
    c, bearer, cid, _payload = _old_register_world(app_client)
    _store_no_shared_row(cid, "true", present=True)
    capsys.readouterr()
    _assert_original_no_scores_line(c, bearer, cid)
    out = capsys.readouterr().out
    assert "risk.csf_no_shared_row.unreadable" in out, out[-2000:]
    assert '"got": "str"' in out, out[-2000:]
