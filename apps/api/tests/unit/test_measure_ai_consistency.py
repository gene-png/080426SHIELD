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
    Refused,
    RunRecord,
    compare_pair,
    echo_share,
    measure_zt,
    preflight,
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


def test_identical_runs_agree_fully_with_denominators() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, json.loads(json.dumps(a)))
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
    }
    assert r["fields"]["target"]["equal"] == 2


def test_a_moved_value_counts_against_that_field_only() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    b = _caps({"code": "C1", "current": 3, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b)
    assert r["fields"]["current"]["compared"] == 2
    assert r["fields"]["current"]["equal"] == 1
    assert r["fields"]["current"]["within_one"] == 2
    assert r["fields"]["current"]["mean_abs_diff"] == 0.5
    assert r["fields"]["target"]["equal"] == 2


def test_a_row_in_one_run_only_is_counted_not_dropped() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C2", "current": 1, "target": 3})
    b = _caps({"code": "C1", "current": 2, "target": 3}, {"code": "C3", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b)
    assert r["rows"]["in_both"] == 1
    assert r["rows"]["only_in_a"] == 1
    assert r["rows"]["only_in_b"] == 1
    # The field denominators cover only rows present in BOTH runs, and say so.
    assert r["fields"]["current"]["compared"] == 1


def test_a_field_one_run_omitted_is_counted_as_missing() -> None:
    a = _caps({"code": "C1", "current": 2, "target": 3})
    b = _caps({"code": "C1", "current": 2})
    r = compare_pair("zt_score", a, b)
    assert r["fields"]["target"]["compared"] == 0
    assert r["fields"]["target"]["missing_in_b"] == 1
    assert r["fields"]["target"]["missing_in_a"] == 0
    assert r["fields"]["current"]["equal"] == 1


def test_true_and_one_are_not_the_same_answer() -> None:
    # `True == 1` in Python. A model that writes `true` for a stage has not
    # given the same answer as one that writes 1.
    a = _caps({"code": "C1", "current": True, "target": 3})
    b = _caps({"code": "C1", "current": 1, "target": 3})
    r = compare_pair("zt_score", a, b)
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
    r = compare_pair("zt_score", a, b)
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


def test_a_failed_run_is_reported_and_excluded_from_pairs() -> None:
    good = _caps({"code": "C1", "current": 2, "target": 3})
    runs = [
        _ok(good),
        RunRecord(
            ok=False, data=None, failure="AIResponseShapeError", input_tokens=10, output_tokens=None
        ),
        _ok(good),
    ]
    s = summarize("zt_score", runs)
    assert s["runs_requested"] == 3
    assert s["runs_ok"] == 2
    assert s["failed_runs"] == [{"run": 2, "failure": "AIResponseShapeError"}]
    assert [p["pair"] for p in s["pairs"]] == [[1, 3]]
    assert s["exit_code"] == 1


def test_all_runs_ok_exits_zero_and_pairs_every_combination() -> None:
    good = _caps({"code": "C1", "current": 2, "target": 3})
    s = summarize("zt_score", [_ok(good), _ok(good), _ok(good)])
    assert [p["pair"] for p in s["pairs"]] == [[1, 2], [1, 3], [2, 3]]
    assert s["exit_code"] == 0
    assert s["tokens"] == {"input": 30, "output": 60}


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
    assert report["tokens"] == {"input": 200, "output": 80}
    assert report["downstream"][0]["gap_codes"] == [code]
    assert report["input_setup"] == {"reopened_from": None}
    # The fixture's `current` (2) differs from the new assessment's (None).
    assert report["echo"] == [
        {"run": 1, "current": {"sent_and_answered": 0, "echoed": 0, "nothing_sent": 1}},
        {"run": 2, "current": {"sent_and_answered": 0, "echoed": 0, "nothing_sent": 1}},
    ]
    assert report["exit_code"] == 0
