"""`scripts/measure_evidence_blast_radius.py`: a READ-ONLY measure of what the
evidence scoring rules (design note rev 4, section 10.4: R1-R3 and the ZT
`evidenced_stage` rule, Q10 ruled "lowest stage plus one") would move at launch.

Every row in the world below is written by a product WRITER, named at the
call. The one state no route sets directly is RELEASED, which is written by
`app/deliverable_release.py`'s UPDATE (`values(status=...RELEASED)`) from
APPROVED; the test performs that same UPDATE on an APPROVED assessment rather
than driving a whole deliverable render.

The expected values are derived from the SPEC (section 10.4's rule and
`maturity_level`'s documented bands, restated per row below), never from the
script's own constants.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus
from scripts import measure_evidence_blast_radius as m
from tests.unit.test_zt_run_ai import _admin_service, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]
_SCRIPT = _API / "scripts" / "measure_evidence_blast_radius.py"
_ALL_TWO = {"governance": 2, "policy": 2, "implementation": 2, "monitoring": 2, "improvement": 2}


def _run(url: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    if url is not None:
        env["DATABASE_URL"] = url
    return subprocess.run(  # noqa: S603 -- this interpreter, the repo's own script
        [sys.executable, str(_SCRIPT)], cwd=_API, env=env, capture_output=True, text=True
    )


def _json(stdout: str) -> dict:
    return json.loads(stdout.split(m.JSON_MARKER, 1)[1])


def _db_path(url: str) -> Path:
    return Path(url.removeprefix("sqlite:///"))


def _csf_service(c, h, title: str) -> tuple[str, str, list[dict]]:
    """Writers: POST /csf/services, POST /csf/services/{id}/assessments, and
    POST /csf/services/{id}/profiles/seed (`seed_profiles`), HIGH tier only."""
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": title}).json()["id"]
    aid = c.post(f"/csf/services/{svc}/assessments", headers=h).json()["id"]
    assert c.post(
        f"/csf/services/{svc}/profiles/seed", headers=h, json={"tiers": ["high"]}
    ).is_success
    rows = c.get(f"/csf/services/{svc}/profile/high", headers=h).json()["rows"]
    assert len(rows) > 4  # the selector selected something before it is read
    return svc, aid, rows


def _patch_row(c, h, row: dict, body: dict) -> None:
    """Writer: PATCH /csf/dimension-scores/{id} (`patch_dimension_score`), the
    editor's scores, scope, target and "Evidence on file" tick."""
    res = c.patch(f"/csf/dimension-scores/{row['id']}", headers=h, json=body)
    assert res.status_code == 200, res.text


def _zt_assessment(c, h, svc: str) -> tuple[str, dict[str, str]]:
    """Writer: POST /zt/services/{id}/assessments, which pre-creates one NULL
    answer row per catalog capability."""
    a = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    return a["id"], {x["capability_code"]: x["id"] for x in a["answers"]}


def _zt_stage(c, h, answer_id: str, stage: int) -> None:
    """Writer: PATCH /zt/answers/{id} (`patch_answer`)."""
    res = c.patch(f"/zt/answers/{answer_id}", headers=h, json={"maturity_stage": stage})
    assert res.status_code == 200, res.text


def _second_client(c, h) -> dict:
    """Writer: POST /admin/clients, as the same admin."""
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": h["Authorization"]},
        json={"legal_name": "Beta"},
    ).json()["id"]
    return {"Authorization": h["Authorization"], "X-Client-Id": cid}


@pytest.fixture
def world(app_client):  # noqa: F811
    """Acme: two CSF assessments (DRAFT, RELEASED). Beta: ZT CISA (DRAFT) and
    ZT DoD (APPROVED). Returns ids the assertions need."""
    c, _ = app_client
    h, zt_cisa_svc, acme = _admin_service(c, "zero_trust_cisa")

    # --- CSF, DRAFT. Section 10.4 R1 at launch = today's cap for every row,
    # because no CONFIRMED Current link exists at launch (10.6).
    _, draft_aid, rows = _csf_service(c, h, "CSF draft")
    r0, r1, r2, r3 = rows[0], rows[1], rows[2], rows[3]
    # r0: ticked, all 2. Today total 10 -> L5. Launch: implementation 1, total
    # 9 -> L4, then level <= 2 -> L2. MOVES. Target 3: no gap today, a gap at launch.
    _patch_row(c, h, r0, {**_ALL_TWO, "has_evidence": True, "target_level": 3})
    # r1: not ticked, all 2. Capped today (L2) and at launch (L2). Unchanged.
    _patch_row(c, h, r1, {**_ALL_TWO, "has_evidence": False})
    # r2: ticked, governance 1 only. Total 1 -> L1 both ways. Ticked, unchanged.
    _patch_row(c, h, r2, {"governance": 1, "has_evidence": True})
    # r3: ticked, all 2, but OUT of scope: not counted in scope at all.
    _patch_row(c, h, r3, {**_ALL_TWO, "has_evidence": True, "in_scope": False})

    # --- CSF, RELEASED. One ticked all-2 row: MOVES (L5 -> L2).
    _, rel_aid, rel_rows = _csf_service(c, h, "CSF released")
    _patch_row(c, h, rel_rows[0], {**_ALL_TWO, "has_evidence": True})
    assert c.post(
        f"/csf/assessments/{rel_aid}/approve", headers=h
    ).is_success  # `approve_assessment`
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url, future=True)
    with Session(engine) as db:
        # `app/deliverable_release.py`'s own UPDATE, from APPROVED.
        db.execute(
            update(CsfAssessment)
            .where(
                CsfAssessment.id == uuid.UUID(rel_aid),
                CsfAssessment.status == CsfAssessmentStatus.APPROVED,
            )
            .values(status=CsfAssessmentStatus.RELEASED)
        )
        db.commit()
    engine.dispose()

    # --- ZT, Beta.
    hb = _second_client(c, h)
    cisa = c.post("/zt/services", headers=hb, json={"kind": "zero_trust_cisa", "title": "C"})
    cisa_aid, cisa_ans = _zt_assessment(c, hb, cisa.json()["id"])
    codes = sorted(cisa_ans)
    # Q10: above the lowest stage (1) without a Current file -> lowest + 1 = 2.
    _zt_stage(c, hb, cisa_ans[codes[0]], 4)  # 4 -> 2: MOVES
    _zt_stage(c, hb, cisa_ans[codes[1]], 2)  # 2 -> 2: unchanged
    _zt_stage(c, hb, cisa_ans[codes[2]], 1)  # 1 -> 1: unchanged
    dod = c.post("/zt/services", headers=hb, json={"kind": "zero_trust_dod", "title": "D"})
    dod_aid, dod_ans = _zt_assessment(c, hb, dod.json()["id"])
    _zt_stage(c, hb, dod_ans["DOD.USR.01"], 2)  # max 2 (no Advanced activity): unchanged
    _zt_stage(c, hb, dod_ans["DOD.USR.02"], 3)  # 3 -> 2: MOVES
    assert c.post(f"/zt/assessments/{dod_aid}/approve", headers=hb).is_success
    # The unused `zt_cisa_svc` on Acme has no assessment: nothing to read there.
    del zt_cisa_svc

    return {
        "url": url,
        "acme": acme,
        "beta": hb["X-Client-Id"],
        "csf_rows_per_assessment": len(rows),
        "cisa_capabilities": len(cisa_ans),
        "dod_capabilities": len(dod_ans),
    }


def test_known_answer_and_no_write(world) -> None:
    url = world["url"]
    before = _db_path(url).read_bytes()
    r = _run(url)
    after = _db_path(url).read_bytes()
    assert r.returncode == 0, r.stdout + r.stderr
    assert after == before, "the measurement wrote to the database"
    report = _json(r.stdout)
    n = world["csf_rows_per_assessment"]

    # CSF tier rows, Python path, per status. DRAFT: n-1 in scope (r3 out),
    # one move (r0), two ticked in scope (r0, r2). RELEASED: n in scope, one
    # move, one ticked.
    tiers = report["csf_tier_rows"]["by_status"]
    assert tiers["draft"] == {
        "rows_read": n,
        "rows_in_scope": n - 1,
        "rows_level_moves": 1,
        "rows_ticked_today": 2,
    }
    assert tiers["released"] == {
        "rows_read": n,
        "rows_in_scope": n,
        "rows_level_moves": 1,
        "rows_ticked_today": 1,
    }
    assert tiers["approved"]["rows_read"] == 0
    # The section 10.6 SQL path agrees, per status and per client.
    assert report["paths_agree"] is True
    assert report["csf_tier_rows_sql"]["by_status"]["draft"]["rows_level_moves"] == 1
    assert report["csf_tier_rows_sql"]["by_status"]["released"]["rows_level_moves"] == 1
    acme = report["csf_tier_rows"]["by_client"][world["acme"]]["by_status"]
    assert acme["draft"]["rows_level_moves"] == 1

    # CSF Enterprise (HIGH tier only, so each subcategory is its one row):
    # r0 L5 -> L2 against target 3 opens one gap on DRAFT; RELEASED moves a
    # level, no target, no gap.
    ent = report["csf_enterprise"]["by_status"]
    assert ent["draft"]["subcategory_level_moves"] == 1
    assert ent["draft"]["gaps_today"] == 0
    assert ent["draft"]["gaps_launch"] == 1
    assert ent["draft"]["gaps_opened"] == 1
    assert ent["draft"]["gaps_closed"] == 0
    assert ent["released"]["subcategory_level_moves"] == 1
    assert ent["released"]["gaps_opened"] == 0
    assert report["csf_enterprise"]["not_evaluable"] == []

    # The CSF deliverable reads CsfAnswer.maturity_tier: stated, not measured.
    assert report["csf_deliverable"]["rows_moved"] == 0
    assert "maturity_tier" in report["csf_deliverable"]["basis"]

    # ZT answers. DRAFT (CISA): 3 evaluated, 1 move (4 -> 2), the rest NULL,
    # counted as NOT EVALUABLE (unscored), never as unchanged.
    zt = report["zt_answers"]["by_status"]
    assert zt["draft"]["answers_evaluated"] == 3
    assert zt["draft"]["stage_moves"] == 1
    assert zt["draft"]["unchanged"] == 2
    assert zt["draft"]["not_evaluable"] == {"unscored": world["cisa_capabilities"] - 3}
    assert zt["approved"]["answers_evaluated"] == 2
    assert zt["approved"]["stage_moves"] == 1
    assert zt["approved"]["unchanged"] == 1
    assert zt["approved"]["not_evaluable"] == {"unscored": world["dod_capabilities"] - 2}

    # ZT deliverable: CISA default target 3. Today: stages 4, 2, 1 -> two gaps.
    # Launch: 2, 2, 1 -> three gaps. Average (4+2+1)/3 -> (2+2+1)/3 moves.
    za = report["zt_assessments"]["by_status"]
    assert za["draft"]["assessments_evaluated"] == 1
    assert za["draft"]["gaps_today"] == 2
    assert za["draft"]["gaps_launch"] == 3
    assert za["draft"]["average_stage_moves"] == 1
    assert report["zt_assessments"]["not_evaluable"] == []
    beta = report["zt_answers"]["by_client"][world["beta"]]["by_status"]
    assert beta["draft"]["stage_moves"] == 1


def test_the_proposed_zt_rule_never_rescues_an_out_of_ladder_stage() -> None:
    """A stored stage outside the framework's ladder is unscored to the engine
    (`_validated`). The retired DoD stage 0 was written by the pre-#839 DoD
    writer; capping it to "lowest plus one" would turn junk into a scored 2."""
    from app.zt.maturity import ZtFrameworkCode

    dod = ZtFrameworkCode.DOD_ZTRA
    assert m.proposed_launch_stage(dod, 0) == 0
    assert m.proposed_launch_stage(dod, 4) == 4
    assert m.proposed_launch_stage(dod, 3) == 2
    assert m.proposed_launch_stage(dod, 1) == 1
    assert m.proposed_launch_stage(ZtFrameworkCode.CISA_ZTMM_2_0, 4) == 2
    assert m.proposed_launch_stage(dod, None) is None


def test_the_readonly_engine_refuses_a_write(world) -> None:
    engine = m.open_readonly(world["url"])
    try:
        with engine.connect() as conn, pytest.raises(OperationalError, match="readonly"):
            conn.execute(text("CREATE TABLE should_not_exist (a INTEGER)"))
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        (None, "DATABASE_URL is not set"),
        ("sqlite:////nonexistent/shield.db", "no SQLite file"),
    ],
)
def test_unreadable_input_exits_2_and_names_the_cause(url, reason) -> None:
    r = _run(url)
    assert r.returncode == 2, r.stdout + r.stderr
    assert reason in r.stderr
    assert m.JSON_MARKER not in r.stdout


def test_a_database_without_the_tables_exits_2(tmp_path) -> None:
    empty = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{empty}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE unrelated (a INTEGER)"))
    engine.dispose()
    r = _run(f"sqlite:///{empty}")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "could not read" in r.stderr


def test_paths_disagreeing_exits_1_loudly(world, monkeypatch, capsys) -> None:
    real = m.csf_tier_rows_sql

    def off_by_one(conn):
        out = real(conn)
        key = next(iter(out))
        out[key] = {**out[key], "rows_level_moves": out[key]["rows_level_moves"] + 1}
        return out

    monkeypatch.setattr(m, "csf_tier_rows_sql", off_by_one)
    monkeypatch.setenv("DATABASE_URL", world["url"])
    assert m.main() == 1
    out = capsys.readouterr()
    assert "PATHS DISAGREE" in out.out + out.err
    assert _json(out.out)["paths_agree"] is False


def test_a_refactor_that_bypasses_the_patched_score_tier_exits_2(
    world, monkeypatch, capsys
) -> None:
    """If `enterprise_subcategories` stops calling `score_tier` through its
    module global, the launch rule is silently not applied and every
    Enterprise level reads "unchanged". The call count catches it."""
    from app.csf import enterprise, playbook

    real_entry = enterprise.enterprise_subcategories

    def refactored(db, a):
        saved = enterprise.score_tier
        enterprise.score_tier = playbook.score_tier
        try:
            return real_entry(db, a)
        finally:
            enterprise.score_tier = saved

    monkeypatch.setattr(enterprise, "enterprise_subcategories", refactored)
    monkeypatch.setenv("DATABASE_URL", world["url"])
    assert m.main() == 2
    assert "was not applied" in capsys.readouterr().err
