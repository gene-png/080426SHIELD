"""The run-to-run consistency measure (#806 step 1).

The measure runs one AI job N times on the same input and reports how far the
runs agree. These tests pin the four properties the issue asked for:

* it REFUSES anything but SQLite + live mode + strict redaction, so a run can
  never reach the shared Postgres or egress unredacted;
* it APPLIES NOTHING -- the answer rows are byte-identical after a measurement;
* agreement is reported PER FIELD and PER PAIR, every share with its
  denominator, and a row present in only one run is counted, never dropped;
* a FAILED run is reported as failed, never folded into "0% agreement".

The model responses below are written from `_ZT_SCORE_PROMPT`'s own JSON shape
(`{"capabilities": [{"code": "...", "current": int, "target": int}]}`), not
from the parser's constants (CLAUDE.md: author AI fixtures from the prompt).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from scripts.measure_ai_consistency import (
    MAX_RUNS,
    Refused,
    RunRecord,
    compare_pair,
    csf_levels,
    echo_share,
    main,
    measure_csf,
    measure_zt,
    preflight,
    run_loop,
    summarize,
    zt_downstream,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse

pytestmark = pytest.mark.unit


# --- preflight -------------------------------------------------------------


def test_preflight_accepts_sqlite_live_strict() -> None:
    preflight(database_url="sqlite:////tmp/m.db", llm_mode="live", redaction_mode="strict")


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://shield:shield@db:5432/shield",
        "postgresql://localhost/shield",
        "",
    ],
)
def test_preflight_refuses_any_database_but_sqlite(database_url: str) -> None:
    with pytest.raises(Refused, match="SQLite") as exc:
        preflight(database_url=database_url, llm_mode="live", redaction_mode="strict")
    assert exc.value.reason == "database_not_sqlite"


def test_preflight_refuses_fixture_mode() -> None:
    # A fixture run "agrees" with itself by construction: measuring it would
    # report 100% consistency about nothing.
    with pytest.raises(Refused, match="live") as exc:
        preflight(database_url="sqlite:///m.db", llm_mode="fixture", redaction_mode="strict")
    assert exc.value.reason == "llm_mode_not_live"


@pytest.mark.parametrize("redaction_mode", ["standard", "off"])
def test_preflight_refuses_redaction_weaker_than_strict(redaction_mode: str) -> None:
    with pytest.raises(Refused, match="strict") as exc:
        preflight(database_url="sqlite:///m.db", llm_mode="live", redaction_mode=redaction_mode)
    assert exc.value.reason == "redaction_not_strict"


# --- compare_pair ----------------------------------------------------------


def _caps(*rows: dict) -> dict:
    return {"capabilities": list(rows)}


#: zt_score's measure context: the framework's top stage, which the apply
#: path's `_validated_stage` judges range against. CISA ZTMM 2.0 has four.
CISA_MAX = 4


def test_identical_runs_agree_fully_with_denominators() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, json.loads(json.dumps(a)), context=CISA_MAX)
    assert r["rows"] == {
        "in_both": 2,
        "only_in_a": 0,
        "only_in_b": 0,
        "unreadable_a": 0,
        "unreadable_b": 0,
        "duplicate_keys_a": 0,
        "duplicate_keys_b": 0,
    }
    assert r["fields"]["current"] == {
        "compared": 2,
        "equal": 2,
        "within_one": 2,
        "mean_abs_diff": 0.0,
        "missing_in_a": 0,
        "missing_in_b": 0,
        "both_absent": 0,
        "one_absent": 0,
    }
    assert r["fields"]["target"]["equal"] == 2


def test_a_moved_value_counts_against_that_field_only() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    b = _caps({"code": "C1", "current": 3, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b, context=CISA_MAX)
    assert r["fields"]["current"]["compared"] == 2
    assert r["fields"]["current"]["equal"] == 1
    assert r["fields"]["current"]["within_one"] == 2
    assert r["fields"]["current"]["mean_abs_diff"] == 0.5
    assert r["fields"]["target"]["equal"] == 2


def test_a_row_in_one_run_only_is_counted_not_dropped() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    b = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C3", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b, context=CISA_MAX)
    assert r["rows"]["in_both"] == 1
    assert r["rows"]["only_in_a"] == 1
    assert r["rows"]["only_in_b"] == 1
    # The field denominators cover only rows present in BOTH runs, and say so.
    assert r["fields"]["current"]["compared"] == 1


def test_a_field_one_run_omitted_is_counted_as_missing() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3})
    b = _caps({"code": "C1", "current": 2})
    r = compare_pair("zt_score", a, b, context=CISA_MAX)
    assert r["fields"]["target"]["compared"] == 1
    assert r["fields"]["target"]["one_absent"] == 1
    assert r["fields"]["target"]["equal"] == 0
    assert r["fields"]["target"]["missing_in_b"] == 1
    assert r["fields"]["target"]["missing_in_a"] == 0
    assert r["fields"]["current"]["equal"] == 1


def test_true_and_one_are_not_the_same_answer() -> None:
    # `True == 1` in Python. A model that writes `true` for a stage has not
    # given the same answer as one that writes 1.
    a = _caps({"code": "C1", "current": True, "target": 3})
    b = _caps({"code": "C1", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b, context=CISA_MAX)
    assert r["fields"]["current"]["compared"] == 1
    assert r["fields"]["current"]["equal"] == 0
    # Not a whole-number stage on one side, so it cannot be "within one".
    assert r["fields"]["current"]["within_one"] == 0


def test_unreadable_and_duplicate_rows_are_counted() -> None:
    a = _caps(
        {"code": "C1", "current": 2, "target": 3},
        "not an object",
        {"code": "C1", "current": 1, "target": 3},
    )
    b = _caps({"code": "C1", "current": 2, "target": 3})
    r = compare_pair("zt_score", a, b, context=CISA_MAX)
    assert r["rows"]["unreadable_a"] == 1
    assert r["rows"]["duplicate_keys_a"] == 1
    # A duplicated key is ambiguous, so it is compared in neither run.
    assert r["rows"]["in_both"] == 0
    assert r["rows"]["only_in_b"] == 1


# --- zt_downstream: the number the client sees ------------------------------


def test_downstream_counts_gaps_through_the_engine() -> None:
    from app.zt.catalog import all_codes
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    c1, c2 = sorted(all_codes(fw))[:2]
    data = _caps(
        {"code": c1, "current": 2, "target": 3},  # 2 < 3: a gap
        {"code": c2, "current": 3, "target": 2},  # 3 >= 2: none, though below S3
    )
    d = zt_downstream(fw, engagement_stage=3, data=data)
    assert d["gap_codes"] == [c1]
    assert d["total_gap_count"] == 1
    # Every other capability got no `current` from the model.
    assert d["unscored_count"] == len(all_codes(fw)) - 2
    assert d["non_integer_values"] == 0


def test_downstream_lists_every_gap_not_the_engines_top_twenty() -> None:
    # `analyze_gaps` truncates `gaps` to DEFAULT_TOP_N unless told otherwise
    # (#75); a gap list compared across runs must be the whole list.
    from app.zt.catalog import all_codes
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    codes = sorted(all_codes(fw))
    assert len(codes) > 20, "precondition: more capabilities than the engine's top-N"
    data = _caps(*({"code": c, "current": 1, "target": 3} for c in codes))
    d = zt_downstream(fw, engagement_stage=3, data=data)
    assert d["total_gap_count"] == len(codes)
    assert d["gap_codes"] == codes


def test_downstream_never_coerces_a_non_integer_stage() -> None:
    from app.zt.catalog import all_codes
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    c1, c2, c3 = sorted(all_codes(fw))[:3]
    data = _caps(
        {"code": c1, "current": True, "target": 3},
        {"code": c2, "current": "2", "target": 3},
        {"code": c3, "current": 1, "target": 2.5},
    )
    d = zt_downstream(fw, engagement_stage=3, data=data)
    # c1 and c2 are unscored rather than read as 1 and 2; c3's current is
    # whole, and its fractional target falls back to the engagement stage.
    assert d["gap_codes"] == [c3]
    assert d["non_integer_values"] == 3


# --- echo_share: did the model judge, or repeat what it was sent? ----------


def _zt_inputs(answers: dict) -> dict:
    # The shape `routes/zt.py::_zt_ai_request_for` sends.
    return {"framework": "cisa_ztmm_2_0", "capabilities": sorted(answers), "answers": answers}


def test_echo_share_counts_values_equal_to_what_was_sent() -> None:
    inputs = _zt_inputs(
        {
            "C1": {"notes": "n", "current": 2},
            "C2": {"notes": "n", "current": 2},
            "C3": {"notes": "n", "current": None},
        }
    )
    data = _caps(
        {"code": "C1", "current": 2, "target": 3},  # repeated the input
        {"code": "C2", "current": 3, "target": 3},  # moved off it
        {"code": "C3", "current": 1, "target": 3},  # nothing was sent to repeat
    )
    e = echo_share("zt_score", inputs, data)
    assert e == {"current": {"sent_and_answered": 2, "echoed": 1, "nothing_sent": 1}}


def test_echo_share_is_type_strict_and_skips_unanswered_rows() -> None:
    inputs = _zt_inputs({"C1": {"current": 1}, "C2": {"current": 2}})
    data = _caps({"code": "C1", "current": True, "target": 3}, {"code": "C2", "target": 3})
    e = echo_share("zt_score", inputs, data)
    # `true` is not a repeat of 1; C2 answered no `current`, so it is not counted.
    assert e == {"current": {"sent_and_answered": 1, "echoed": 0, "nothing_sent": 0}}


# --- summarize: failed runs ------------------------------------------------


def _ok(data: dict) -> RunRecord:
    return RunRecord(ok=True, data=data, failure=None, input_tokens=10, output_tokens=20)


def test_all_runs_ok_exits_zero_and_pairs_every_combination() -> None:
    good = _caps({"code": "C1", "current": 2, "target": 3})
    s = summarize("zt_score", [_ok(good), _ok(good), _ok(good)], context=CISA_MAX)
    assert [p["pair"] for p in s["pairs"]] == [[1, 2], [1, 3], [2, 3]]
    assert s["exit_code"] == 0
    assert s["tokens"] == {"input": 30, "output": 60, "complete": True}


def test_fewer_than_two_good_runs_is_a_failure_not_a_result() -> None:
    good = _caps({"code": "C1", "current": 2, "target": 3})
    s = summarize("zt_score", [_ok(good), RunRecord(False, None, "Boom", None, None)])
    assert s["pairs"] == []
    assert s["exit_code"] == 1


# --- measure_zt: the real path, applying nothing ---------------------------


@pytest.fixture()
def world(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'measure.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c, TestSession, FixtureProvider()


def _zt_assessment(c: TestClient) -> str:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "T"})
    a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h)
    return a.json()["answers"][0]["capability_code"]


def _answer_rows(db: Session) -> list[tuple]:
    from app.models.zt_assessment import ZtAnswer

    rows = db.execute(select(ZtAnswer).order_by(ZtAnswer.capability_code)).scalars().all()
    return [
        (r.capability_code, r.maturity_stage, r.target_stage, r.answer_source, r.updated_at)
        for r in rows
    ]


def _release_all_zt(TestSession: sessionmaker) -> None:
    # The demo seed's state: every ZT assessment RELEASED, which the route's
    # own builder refuses as locked.
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus

    with TestSession() as db:
        for a in db.execute(select(ZtAssessment)).scalars():
            a.status = ZtAssessmentStatus.RELEASED
        db.commit()


def test_a_released_assessment_is_refused_unless_reopening_was_asked_for(world) -> None:
    c, TestSession, provider = world
    _zt_assessment(c)
    _release_all_zt(TestSession)
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
    assert exc.value.reason == "no_editable_assessment"


def test_reopening_a_released_assessment_measures_its_answers_and_says_so(world) -> None:
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus

    c, TestSession, provider = world
    code = _zt_assessment(c)
    _release_all_zt(TestSession)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 3}]}'),
    )
    with TestSession() as db:
        before = _answer_rows(db)
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2, reopen_released=True)
        db.commit()
    with TestSession() as db:
        assert _answer_rows(db) == before
        status_now = db.execute(select(ZtAssessment.status)).scalar_one()
    assert status_now == ZtAssessmentStatus.DRAFT
    assert report["input_setup"] == {"reopened_from": "released"}
    assert report["runs_ok"] == 2


def test_measure_zt_runs_the_job_n_times_and_applies_nothing(world) -> None:
    c, TestSession, provider = world
    code = _zt_assessment(c)
    provider.register_static(
        "zt_score",
        LLMResponse(
            '{"capabilities": [{"code": "' + code + '", "current": 2, "target": 4}]}',
            input_tokens=100,
            output_tokens=40,
        ),
    )
    with TestSession() as db:
        before = _answer_rows(db)
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
        db.commit()
    with TestSession() as db:
        after = _answer_rows(db)

    # The model suggested current=2 / target=4 for `code`; NONE of it landed.
    assert after == before
    assert report["runs_ok"] == 2
    assert report["pairs"][0]["rows"]["in_both"] == 1
    assert report["pairs"][0]["fields"]["current"]["equal"] == 1
    assert report["tokens"] == {"input": 200, "output": 80, "complete": True}
    assert report["downstream"][0]["gap_codes"] == [code]
    assert report["input_setup"] == {"reopened_from": None}
    # The fixture's `current` (2) differs from the new assessment's (None).
    assert report["echo"] == [
        {"run": 1, "current": {"sent_and_answered": 0, "echoed": 0, "nothing_sent": 1}},
        {"run": 2, "current": {"sent_and_answered": 0, "echoed": 0, "nothing_sent": 1}},
    ]
    assert report["exit_code"] == 0


# --- csf_score -------------------------------------------------------------
# Rows below follow `_CSF_SCORE_PROMPT`'s own example:
# {"scores": [{"tier": "high", "subcategory_code": "GV.OC-01", "governance": 0,
#  "policy": 0, "implementation": 0, "monitoring": 0, "improvement": 0,
#  "what_we_found": "..."}], "executive_summary": "..."}


def _csf_row(tier: str, code: str, dims: tuple, found: str = "x") -> dict:
    g, p, i, m, c = dims
    return {
        "tier": tier,
        "subcategory_code": code,
        "governance": g,
        "policy": p,
        "implementation": i,
        "monitoring": m,
        "improvement": c,
        "what_we_found": found,
    }


def test_csf_rows_are_keyed_by_tier_and_subcategory_and_compare_the_five_dimensions() -> None:
    a = {"scores": [_csf_row("high", "GV.OC-01", (1, 1, 1, 1, 1), "first wording")]}
    b = {
        "scores": [
            _csf_row("high", "GV.OC-01", (1, 2, 1, 1, 1), "other wording"),
            _csf_row("low", "GV.OC-01", (0, 0, 0, 0, 0)),
        ]
    }
    r = compare_pair("csf_score", a, b)
    assert r["rows"]["in_both"] == 1
    assert r["rows"]["only_in_b"] == 1  # same code, different tier: a different row
    assert sorted(r["fields"]) == [
        "governance",
        "implementation",
        "improvement",
        "monitoring",
        "policy",
    ]
    assert r["fields"]["policy"]["equal"] == 0
    assert r["fields"]["governance"]["equal"] == 1
    # The narrative is never compared: wording differs on every run.
    assert "what_we_found" not in r["fields"]


def test_csf_levels_go_through_the_engine_and_apply_the_evidence_cap() -> None:
    data = {
        "scores": [
            _csf_row("high", "A", (2, 2, 2, 2, 2)),  # total 10 -> L5
            _csf_row("high", "B", (2, 2, 2, 2, 2)),  # same, but no evidence -> L2
            _csf_row("high", "C", (0, 1, 0, 1, 0)),  # total 2 -> L1
        ]
    }
    levels = csf_levels(data, has_evidence={"high|A": True, "high|B": False, "high|C": True})
    assert levels == {
        "levels": {"high|A": 5, "high|B": 2, "high|C": 1},
        "unscoreable_keys": [],
        "not_scoreable": 0,
        # B scored a total of 10 and was capped to Level 2 for want of evidence.
        "evidence_capped": 1,
    }


def test_csf_levels_never_clamp_or_coerce_a_bad_dimension() -> None:
    # The engine's `clamped()` would read 3 as 2 and `true` as 1; the apply
    # path (`_validated_dimension`) refuses both, so neither row is scored.
    #
    # This test used to put "2" among the refused values. That was WRONG
    # against the apply path, which stores "2" as 2 (#867 narrow review B-3):
    # the measure restated the rule and disagreed with it. "2" now scores
    # exactly as 2 does (row C against row F below).
    data = {
        "scores": [
            _csf_row("high", "A", (3, 1, 1, 1, 1)),
            _csf_row("high", "B", (True, 1, 1, 1, 1)),
            _csf_row("high", "C", ("2", 1, 1, 1, 1)),
            {"tier": "high", "subcategory_code": "D", "governance": 1},  # four missing
            _csf_row("high", "E", (1, 1, 1, 1, 1)),
            _csf_row("high", "F", (2, 1, 1, 1, 1)),
            _csf_row("high", "G", (2.0, 1, 1, 1, 1)),
            _csf_row("high", "H", (1.5, 1, 1, 1, 1)),
        ]
    }
    levels = csf_levels(data, has_evidence={f"high|{k}": True for k in "ABCDEFGH"})
    assert sorted(levels["levels"]) == ["high|C", "high|E", "high|F", "high|G"]
    assert levels["levels"]["high|E"] == 2
    assert levels["levels"]["high|C"] == levels["levels"]["high|F"], '"2" scores as 2'
    assert levels["levels"]["high|G"] == levels["levels"]["high|F"], "2.0 scores as 2"
    assert levels["unscoreable_keys"] == ["high|A", "high|B", "high|D", "high|H"]
    assert (levels["not_scoreable"], levels["evidence_capped"]) == (4, 0)


def test_a_row_unscoreable_in_either_run_is_compared_without_agreement() -> None:
    """#867 narrow review B-3: 100 rows; run B leaves 90 of them unscoreable.
    Intersecting the two runs' SCORED rows read that as 10 of 10 agreeing --
    a run that scored less looked perfectly consistent."""
    from scripts.measure_ai_consistency import csf_level_agreement

    has_evidence = {f"high|R{i}": True for i in range(100)}
    a = {"scores": [_csf_row("high", f"R{i}", (1, 1, 1, 1, 1)) for i in range(100)]}
    b = {
        "scores": [
            _csf_row("high", f"R{i}", (1, 1, 1, 1, 1) if i < 10 else ("N/A", 1, 1, 1, 1))
            for i in range(100)
        ]
    }
    la, lb = csf_levels(a, has_evidence=has_evidence), csf_levels(b, has_evidence=has_evidence)
    assert (len(la["levels"]), len(lb["levels"])) == (100, 10), "precondition"
    d = csf_level_agreement(la, lb, has_evidence)
    assert d["compared"] == 100, "the unscoreable rows left the denominator"
    assert d["equal"] == 10
    assert (d["one_unscoreable"], d["both_unscoreable"]) == (90, 0)
    # And the same unscoreable rows in both runs: still no agreement.
    both = csf_level_agreement(lb, lb, has_evidence)
    assert (both["compared"], both["equal"], both["both_unscoreable"]) == (100, 10, 90)


# --- run_loop: the output-token budget ---------------------------------------


def test_run_loop_stops_starting_runs_once_the_output_budget_is_spent() -> None:
    calls: list[int] = []

    def one(n: int) -> RunRecord:
        calls.append(n)
        return RunRecord(True, {"capabilities": []}, None, 10, 600)

    records = run_loop(3, one, max_output_tokens=1000)
    # Run 2 takes the total to 1200 > 1000, so run 3 never starts.
    assert calls == [1, 2]
    assert [r.failure for r in records] == [None, None, "stopped_output_budget"]
    assert summarize("zt_score", records, context=CISA_MAX)["exit_code"] == 1


def test_run_loop_without_a_budget_runs_them_all() -> None:
    records = run_loop(3, lambda n: RunRecord(True, {}, None, 1, 10**9), max_output_tokens=None)
    assert [r.ok for r in records] == [True, True, True]


# --- measure_csf: the real batched path, applying nothing -------------------


@pytest.fixture()
def csf_world(world) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider, dict, str]]:
    c, TestSession, provider = world
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "C"}).json()[
        "id"
    ]
    assert c.post(f"/csf/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
    seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    yield c, TestSession, provider, h, svc_id


def _answer_every_asked_row(payload: dict) -> LLMResponse:
    # "for every subcategory code emit one row per tier listed in tiers"
    scores = [
        _csf_row(t, code, (1, 1, 1, 1, 1))
        for t in payload["tiers"]
        for code in payload["subcategories"]
    ]
    return LLMResponse(json.dumps({"scores": scores}), input_tokens=7, output_tokens=11)


def _dimension_rows(db: Session) -> list[tuple]:
    from app.models.csf_profile import CsfDimensionScore

    rows = db.execute(select(CsfDimensionScore)).scalars().all()
    return sorted(
        (
            r.tier,
            r.subcategory_code,
            r.governance,
            r.policy,
            r.implementation,
            r.monitoring,
            r.improvement,
            r.what_we_found,
            r.updated_at,
        )
        for r in rows
    )


def test_measure_csf_runs_every_batch_and_applies_nothing(csf_world) -> None:
    c, TestSession, provider, h, _ = csf_world
    provider.register("csf_score", _answer_every_asked_row)
    with TestSession() as db:
        before = _dimension_rows(db)
        report = measure_csf(db, LLMClient(provider), runs=2)
        db.commit()
    with TestSession() as db:
        assert _dimension_rows(db) == before

    assert len(before) == 106, "precondition: one seeded tier of 106 subcategories"
    assert report["runs_ok"] == 2
    assert report["batches_per_run"] == 11  # 106 rows in tens
    assert report["pairs"][0]["rows"]["in_both"] == 106
    assert report["pairs"][0]["fields"]["governance"]["equal"] == 106
    # Tokens are every batch's, read from the llm_calls rows each batch wrote.
    assert report["tokens"] == {"input": 2 * 11 * 7, "output": 2 * 11 * 11, "complete": True}
    # Seeded rows carry no evidence, so every compared level is capped at L2.
    assert report["pairs"][0]["level"] == {
        "compared": 106,
        "equal": 106,
        "one_unscoreable": 0,
        "both_unscoreable": 0,
        "no_evidence_rows": 106,
    }


def test_a_csf_run_with_a_failed_batch_is_a_failed_run(csf_world) -> None:
    c, TestSession, provider, h, _ = csf_world
    seen: list[int] = []

    def flaky(payload: dict) -> LLMResponse:
        seen.append(1)
        if len(seen) == 3:  # one batch of the first run
            raise RuntimeError("provider closed the connection")
        return _answer_every_asked_row(payload)

    provider.register("csf_score", flaky)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2)
        db.commit()
    assert report["runs_ok"] == 1
    assert report["failed_runs"] == [
        {"run": 1, "failure": "batches_failed:1/11", "cause": None, "charged_likely": True}
    ]
    assert report["pairs"] == []
    assert report["exit_code"] == 1
    # The failed batch's llm_calls row has no token counts; the total must say
    # it is incomplete rather than quietly summing what is left.
    assert report["tokens"]["complete"] is False


def test_measure_csf_reports_level_disagreement_between_runs(csf_world) -> None:
    c, TestSession, provider, h, _ = csf_world
    calls: list[int] = []

    def drifting(payload: dict) -> LLMResponse:
        calls.append(1)
        dims = (1, 1, 1, 1, 1) if len(calls) <= 11 else (0, 0, 0, 0, 0)  # run 2 differs
        scores = [
            _csf_row(t, code, dims) for t in payload["tiers"] for code in payload["subcategories"]
        ]
        return LLMResponse(json.dumps({"scores": scores}))

    provider.register("csf_score", drifting)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2)
        db.commit()
    # Total 5 is Level 2 and total 0 is Level 1: every row's level moved.
    assert report["pairs"][0]["level"] == {
        "compared": 106,
        "equal": 0,
        "one_unscoreable": 0,
        "both_unscoreable": 0,
        "no_evidence_rows": 106,
    }
    assert report["pairs"][0]["fields"]["governance"]["equal"] == 0


# --- B2: a stage the framework does not have is counted, not hidden ---------


def test_downstream_counts_an_out_of_range_current_instead_of_calling_it_unscored() -> None:
    from app.zt.catalog import all_codes
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode.CISA_ZTMM_2_0  # stages 1-4
    codes = sorted(all_codes(fw))
    data = _caps(*({"code": c, "current": 9, "target": 3} for c in codes))
    d = zt_downstream(fw, engagement_stage=3, data=data)
    assert d["out_of_range_values"] == len(codes)
    assert d["unscored_count"] == len(codes)
    assert d["total_gap_count"] == 0


def test_downstream_reports_targets_the_engine_could_not_use() -> None:
    from app.zt.catalog import all_codes
    from app.zt.maturity import ZtFrameworkCode

    fw = ZtFrameworkCode.CISA_ZTMM_2_0
    codes = sorted(all_codes(fw))
    data = _caps(*({"code": c, "current": 1, "target": 9} for c in codes))
    d = zt_downstream(fw, engagement_stage=3, data=data)
    assert d["out_of_range_values"] == len(codes)
    assert d["unusable_target_codes"] == codes
    # The engagement stage (3) applied instead, so every capability at 1 is a gap.
    assert d["total_gap_count"] == len(codes)


# --- B3: a failed run, through the real path --------------------------------


def test_a_non_json_response_is_a_failed_run_through_the_real_path(world) -> None:
    c, TestSession, provider = world
    code = _zt_assessment(c)
    good = '{"capabilities": [{"code": "' + code + '", "current": 2, "target": 3}]}'
    calls: list[int] = []

    def second_is_prose(payload: dict) -> LLMResponse:
        calls.append(1)
        if len(calls) == 2:
            return LLMResponse("Sorry, here is my answer in prose.", 5, 6)
        return LLMResponse(good, 5, 6)

    provider.register("zt_score", second_is_prose)
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=3)
        db.commit()
    assert report["runs_ok"] == 2
    assert report["failed_runs"] == [
        # The boundary's typed reason is a constant; the cause names what went
        # wrong (stdlib json's error for a non-JSON body), and a fixture
        # provider charges nothing.
        {"run": 2, "failure": "ai_call_failed", "cause": "JSONDecodeError", "charged_likely": False}
    ]
    assert [p["pair"] for p in report["pairs"]] == [[1, 3]]
    # The failed call's tokens are read from its llm_calls row, not zeroed.
    assert report["tokens"] == {"input": 15, "output": 18, "complete": True}
    assert report["exit_code"] == 1


def test_measure_zt_counts_a_stage_the_run_refuses_as_no_agreement(world) -> None:
    """#867 narrow review B-4, through `measure_zt`: a stage off CISA's 1..4
    ladder, answered identically twice, is refused by the apply path both
    times -- no agreement -- while its in-range sibling agrees."""
    c, TestSession, provider = world
    code = _zt_assessment(c)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 9, "target": 3}]}'),
    )
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
        db.commit()
    fields = report["pairs"][0]["fields"]
    assert (fields["current"]["compared"], fields["current"]["equal"]) == (1, 0)
    assert fields["current"]["both_absent"] == 1
    assert (fields["target"]["compared"], fields["target"]["equal"]) == (1, 1)


# --- B1: main() refuses before it builds a provider -------------------------


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    from app.ai.llm import LLMClient as _Client
    from app.config import get_settings

    built: list[int] = []

    def recording_from_db(cls, db, settings=None):
        built.append(1)
        return _Client(FixtureProvider())

    monkeypatch.setattr(_Client, "from_db", classmethod(recording_from_db))
    monkeypatch.setenv("SHIELD_LLM_MODE", "live")
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setenv("SHIELD_REDACTION_MODE", "strict")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    yield built, tmp_path
    get_settings.cache_clear()


def test_main_refuses_a_postgres_database_before_building_a_provider(
    cli, monkeypatch, capsys
) -> None:
    from app.config import get_settings

    built, tmp_path = cli
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://shield:shield@db:5432/shield")
    get_settings.cache_clear()
    code = main(["--job", "zt_score", "--runs", "2", "--out", str(tmp_path / "o.json")])
    assert code == 2
    assert built == []
    assert "REFUSED (database_not_sqlite)" in capsys.readouterr().err


def test_main_refuses_a_job_with_no_measure_before_building_a_provider(cli, capsys) -> None:
    from scripts.measure_ai_consistency import _IMPLEMENTED_JOBS

    # The example must be a job that really has no measure. It was
    # tech_debt_extract until #806 measured it; if risk_synthesize is ever
    # measured, this says so instead of failing for a confusing reason.
    assert "risk_synthesize" not in _IMPLEMENTED_JOBS, (
        "this test's premise has expired: risk_synthesize is now measured -- pick "
        "another unmeasured job as the example"
    )
    built, tmp_path = cli
    code = main(["--job", "risk_synthesize", "--runs", "2", "--out", str(tmp_path / "o.json")])
    assert code == 2
    assert built == []
    assert "REFUSED (job_not_implemented)" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("runs", "reason"), [("1", "runs_below_two"), (str(MAX_RUNS + 1), "runs_above_max")]
)
def test_main_refuses_a_run_count_outside_two_to_max(cli, capsys, runs: str, reason: str) -> None:
    built, tmp_path = cli
    code = main(["--job", "zt_score", "--runs", runs, "--out", str(tmp_path / "o.json")])
    assert code == 2
    assert built == []
    assert f"REFUSED ({reason})" in capsys.readouterr().err


def test_main_refuses_a_probe_for_a_job_that_is_not_batched(cli, capsys) -> None:
    built, tmp_path = cli
    code = main(
        ["--job", "zt_score", "--runs", "1", "--probe-batches", "1", "--out", str(tmp_path / "o")]
    )
    assert code == 2
    assert built == []
    assert "REFUSED (probe_not_applicable)" in capsys.readouterr().err


# --- A1: reopening is guarded, and happens only after the admin check -------


def test_reopening_refuses_a_session_not_bound_to_sqlite(world, monkeypatch) -> None:
    # SQLAlchemy queries through the session's own bind, so the dialect READ is
    # replaced here rather than the bind.
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus

    c, TestSession, provider = world
    _zt_assessment(c)
    _release_all_zt(TestSession)
    monkeypatch.setattr("scripts.measure_ai_consistency._session_dialect", lambda db: "postgresql")
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_zt(db, LLMClient(provider), framework="cisa", runs=2, reopen_released=True)
    assert exc.value.reason == "state_change_needs_sqlite"
    with TestSession() as db:
        assert db.execute(select(ZtAssessment.status)).scalar_one() == ZtAssessmentStatus.RELEASED


def test_no_admin_user_is_refused_before_anything_is_reopened(world) -> None:
    from app.models.user import User, UserRole
    from app.models.zt_assessment import ZtAssessment, ZtAssessmentStatus

    c, TestSession, provider = world
    _zt_assessment(c)
    _release_all_zt(TestSession)
    with TestSession() as db:
        for u in db.execute(select(User)).scalars():
            u.role = UserRole.CLIENT
        db.commit()
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_zt(db, LLMClient(provider), framework="cisa", runs=2, reopen_released=True)
    assert exc.value.reason == "no_admin_user"
    with TestSession() as db:
        assert db.execute(select(ZtAssessment.status)).scalar_one() == ZtAssessmentStatus.RELEASED


def test_the_report_names_the_assessment_it_measured(world) -> None:
    from app.models.zt_assessment import ZtAssessment

    c, TestSession, provider = world
    code = _zt_assessment(c)
    provider.register_static(
        "zt_score",
        LLMResponse('{"capabilities": [{"code": "' + code + '", "current": 1, "target": 3}]}'),
    )
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
        db.commit()
        assert report["assessment_id"] == str(db.execute(select(ZtAssessment.id)).scalar_one())


# --- csf_score on an assessment with no Working Profile ---------------------


@pytest.fixture()
def unseeded_csf(world):
    c, TestSession, provider = world
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "C"}).json()[
        "id"
    ]
    assert c.post(f"/csf/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
    yield TestSession, provider


def test_an_unseeded_profile_is_refused_without_the_seed_flag(unseeded_csf) -> None:
    TestSession, provider = unseeded_csf
    provider.register("csf_score", _answer_every_asked_row)
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(db, LLMClient(provider), runs=2)
    assert exc.value.reason == "builder_refused"


def test_the_seed_flag_seeds_the_named_tiers_through_the_route_and_says_so(unseeded_csf) -> None:
    TestSession, provider = unseeded_csf
    provider.register("csf_score", _answer_every_asked_row)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2, seed_profile_tiers=["high"])
        db.commit()
    assert report["input_setup"] == {"reopened_from": None, "profile_seeded_tiers": ["high"]}
    assert report["rows"] == 106
    assert report["runs_ok"] == 2


def test_stop_on_failure_starts_no_run_after_a_failed_one() -> None:
    # A rate-limited or failing provider is not retried into: once a run fails,
    # the rest are recorded as not started.
    calls: list[int] = []

    def one(n: int) -> RunRecord:
        calls.append(n)
        if n == 1:
            return RunRecord(False, None, "ai_call_failed", 5, None, "RateLimitError", True)
        return RunRecord(True, {}, None, 5, 5)

    records = run_loop(3, one, max_output_tokens=None, stop_on_failure=True)
    assert calls == [1]
    assert [r.failure for r in records] == [
        "ai_call_failed",
        "stopped_after_failure",
        "stopped_after_failure",
    ]
    # Runs that never started made no call, so they do not make tokens incomplete;
    # run 1 did call and reported no output, so the total is incomplete.
    assert summarize("zt_score", records, context=CISA_MAX)["tokens"]["complete"] is False


# --- review 2: the budget fails closed, and says what it spent ----------------


def test_unknown_spend_stops_further_runs_under_a_budget() -> None:
    calls: list[int] = []

    def one(n: int) -> RunRecord:
        calls.append(n)
        return RunRecord(True, {}, None, 5, None)  # the provider reported no output

    records = run_loop(3, one, max_output_tokens=10**6)
    assert calls == [1]
    assert [r.failure for r in records] == [None, "stopped_unknown_spend", "stopped_unknown_spend"]


def test_a_run_with_an_uncounted_call_also_stops_the_budget() -> None:
    calls: list[int] = []

    def one(n: int) -> RunRecord:
        calls.append(n)
        # Some of its calls were counted, one was not.
        return RunRecord(True, {}, None, 5, 100, tokens_complete=False)

    records = run_loop(2, one, max_output_tokens=10**6)
    assert calls == [1]
    assert records[1].failure == "stopped_unknown_spend"


def test_the_report_carries_the_budget_and_an_overrun_on_the_last_run() -> None:
    records = run_loop(2, lambda n: RunRecord(True, {}, None, 1, 600), max_output_tokens=1000)
    # Run 2 started at 600 <= 1000 and finished at 1200: an overrun, reported.
    s = summarize("zt_score", records, max_output_tokens=1000, context=CISA_MAX)
    assert s["budget"] == {
        "max_output_tokens": 1000,
        "spent_output_tokens": 1200,
        "overrun": True,
        "complete": True,
    }


# --- review 2: the seed path is guarded and pinned ---------------------------


def _profile_row_count(TestSession: sessionmaker) -> int:
    from sqlalchemy import func

    from app.models.csf_profile import CsfDimensionScore

    with TestSession() as db:
        return db.execute(select(func.count()).select_from(CsfDimensionScore)).scalar_one()


def test_seeding_refuses_a_session_not_bound_to_sqlite(unseeded_csf, monkeypatch) -> None:
    TestSession, provider = unseeded_csf
    monkeypatch.setattr("scripts.measure_ai_consistency._session_dialect", lambda db: "postgresql")
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(db, LLMClient(provider), runs=2, seed_profile_tiers=["high"])
    assert exc.value.reason == "state_change_needs_sqlite"
    assert _profile_row_count(TestSession) == 0


def test_seeding_refuses_when_the_route_would_seed_another_assessment(unseeded_csf) -> None:
    # The route's handler seeds the service's HIGHEST-version assessment; the
    # measure picks the newest editable one. They can only differ on a state no
    # route produces (an older draft beside a newer approved version), so the
    # state is built directly: this pins the guard as a ratchet against the two
    # rules drifting apart.
    from app.models.csf_assessment import CsfAssessment, CsfAssessmentStatus

    TestSession, provider = unseeded_csf
    with TestSession() as db:
        v1 = db.execute(select(CsfAssessment)).scalar_one()
        db.add(
            CsfAssessment(
                service_id=v1.service_id,
                client_id=v1.client_id,
                version=v1.version + 1,
                status=CsfAssessmentStatus.APPROVED,
            )
        )
        db.commit()
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(db, LLMClient(provider), runs=2, seed_profile_tiers=["high"])
    assert exc.value.reason == "profile_seed_target_mismatch"
    assert _profile_row_count(TestSession) == 0


# --- the CSF cost probe --------------------------------------------------------


def test_a_probe_runs_only_the_first_batches_and_reports_its_cost(csf_world) -> None:
    c, TestSession, provider, h, _ = csf_world
    asked: list[int] = []

    def answer(payload: dict) -> LLMResponse:
        asked.append(1)
        return _answer_every_asked_row(payload)

    provider.register("csf_score", answer)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=1, probe_batches=1)
        db.commit()
    assert asked == [1]
    assert report["probe"] == {"batches": 1, "of": 11}
    assert report["runs_ok"] == 1
    assert report["pairs"] == []
    assert report["tokens"] == {"input": 7, "output": 11, "complete": True}
    assert report["exit_code"] == 0
    # The first of the route's batches: ten of the 106 rows, not all of them.
    assert report["rows_sent"] == 10


# --- review 3 -----------------------------------------------------------------


def test_a_probe_prints_the_rows_it_sent_not_the_whole_profile(csf_world, capsys) -> None:
    from scripts.measure_ai_consistency import _print_table

    c, TestSession, provider, h, _ = csf_world
    provider.register("csf_score", _answer_every_asked_row)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=1, probe_batches=1)
        db.commit()
    _print_table(report)
    out = capsys.readouterr().out
    # One batch's tokens beside one batch's rows; 106 here would mis-size the
    # full run about tenfold.
    assert "rows asked per run: 10\n" in out
    assert "PROBE: 1 of 11 batches" in out


def test_a_probe_must_be_smaller_than_a_full_run(csf_world) -> None:
    c, TestSession, provider, h, _ = csf_world
    asked: list[int] = []
    provider.register("csf_score", lambda p: asked.append(1) or _answer_every_asked_row(p))
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(db, LLMClient(provider), runs=1, probe_batches=11)
    assert exc.value.reason == "probe_not_smaller"
    assert asked == []


def test_main_refuses_a_probe_of_more_than_one_run(cli, capsys) -> None:
    built, tmp_path = cli
    code = main(
        ["--job", "csf_score", "--runs", "2", "--probe-batches", "1", "--out", str(tmp_path / "o")]
    )
    assert code == 2
    assert built == []
    assert "REFUSED (probe_runs_not_one)" in capsys.readouterr().err


def test_a_csf_deadline_leaves_the_spend_incomplete(csf_world, monkeypatch) -> None:
    # `run_batches` on its deadline path: batches already finished have written
    # their rows; one still inside a provider call has not, and will later.
    # Built from what that path does (`app/ai/batching.py`): finished rows
    # committed, then `RunFailed(RUN_DEADLINE_EXCEEDED)`.
    from app.ai.engine import run_job
    from app.ai.runs import RUN_DEADLINE_EXCEEDED, RunFailed

    c, TestSession, provider, h, _ = csf_world
    provider.register("csf_score", _answer_every_asked_row)

    def deadline_after_one_batch(db, llm, job_name, batch_inputs, **kw):
        session = Session(bind=db.get_bind())
        run_job(
            session,
            llm,
            job_name,
            inputs=batch_inputs[0],
            requested_by=kw["requested_by"],
            service_id=kw["service_id"],
            client_id=kw["client_id"],
            client_org_name=kw["client_org_name"],
            name_hints=kw["name_hints"],
        )
        session.commit()
        session.close()
        raise RunFailed(RUN_DEADLINE_EXCEEDED, kw["deadline_message"])

    monkeypatch.setattr("app.ai.batching.run_batches", deadline_after_one_batch)
    with TestSession() as db:
        report = measure_csf(
            db, LLMClient(provider), runs=2, max_output_tokens=10**6, stop_on_failure=False
        )
        db.commit()
    assert report["failed_runs"][0]["failure"] == RUN_DEADLINE_EXCEEDED
    # The finished batch's tokens ARE counted ...
    assert report["tokens"]["output"] == 11
    # ... and the total says it is not the whole spend.
    assert report["tokens"]["complete"] is False
    # Run 2 does not start. Since the deadline stop (round 4), that is the
    # deadline's doing whatever the budget; it used to be the budget's
    # `stopped_unknown_spend`, which needed a budget to be set.
    assert report["failed_runs"][1]["failure"] == "stopped_after_deadline"
    # The budget block says so too: "no overrun" over an incomplete count is no claim.
    assert report["budget"]["complete"] is False


def test_a_zt_call_that_failed_without_tokens_leaves_the_spend_incomplete(world) -> None:
    c, TestSession, provider = world
    code = _zt_assessment(c)
    calls: list[int] = []

    def second_raises(payload: dict) -> LLMResponse:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("provider closed the connection")
        return LLMResponse(
            '{"capabilities": [{"code": "' + code + '", "current": 2, "target": 3}]}', 5, 6
        )

    provider.register("zt_score", second_raises)
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=3)
        db.commit()
    assert report["failed_runs"][0]["run"] == 2
    assert report["tokens"]["output"] == 12
    assert report["tokens"]["complete"] is False
    # Named per run: the failed run's own count is the incomplete one.
    assert [r["tokens_complete"] for r in report["runs"]] == [True, False, True]


def test_a_deadline_stops_every_later_run_even_with_no_budget() -> None:
    # A batch still inside a provider call after the deadline writes its row
    # later, into whichever run is counting then. So no later run may start,
    # with or without a budget, with or without --stop-on-failure.
    from app.ai.runs import RUN_DEADLINE_EXCEEDED

    calls: list[int] = []

    def one(n: int) -> RunRecord:
        calls.append(n)
        return RunRecord(False, None, RUN_DEADLINE_EXCEEDED, 10, 20, tokens_complete=False)

    records = run_loop(3, one, max_output_tokens=None, stop_on_failure=False)
    assert calls == [1]
    assert [r.failure for r in records] == [
        RUN_DEADLINE_EXCEEDED,
        "stopped_after_deadline",
        "stopped_after_deadline",
    ]


def test_a_csf_deadline_with_no_budget_starts_no_second_run(csf_world, monkeypatch) -> None:
    from app.ai.runs import RUN_DEADLINE_EXCEEDED, RunFailed

    c, TestSession, provider, h, _ = csf_world
    started: list[int] = []

    def deadline(db, llm, job_name, batch_inputs, **kw):
        started.append(1)
        raise RunFailed(RUN_DEADLINE_EXCEEDED, kw["deadline_message"])

    monkeypatch.setattr("app.ai.batching.run_batches", deadline)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2)
        db.commit()
    assert started == [1]
    assert [r["failure"] for r in report["failed_runs"]] == [
        RUN_DEADLINE_EXCEEDED,
        "stopped_after_deadline",
    ]
    # Run 2 never started, so its window holds no straggler's tokens.
    assert report["runs"][1]["output_tokens"] == 0
