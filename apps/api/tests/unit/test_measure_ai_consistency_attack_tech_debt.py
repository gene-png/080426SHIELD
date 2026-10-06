"""The consistency measure for mitre_map and tech_debt_extract (#806).

The live pass compares each job's runs on TODAY's prompts ("before") with runs
on the approved #806 prompts ("after"), so these two jobs must be measurable
before any prompt changes. The properties pinned are the ones
`test_measure_ai_consistency.py` pins for zt_score and csf_score:

* the production path is CALLED -- `_attack_ai_request_for` and
  `_run_mitre_map_batched`; `parse_inventory` and `extract_from_rows` -- and
  nothing is applied;
* agreement is per field with denominators, and LIST fields are compared as
  sets with a Jaccard, never by order;
* a run with a failed batch is a failed run, never "0% agreement";
* the figure a client would see comes from the engine (`status_from`,
  `reconcile_rows`), not from a copy of it.

Model responses are written from each prompt's own JSON shape -- mitre_map's
`{"techniques": [{"technique_code", "status", "reason_code",
"detection_tools", "prevention_tools", "response_tools", "rationale"}],
"executive_summary", "top_blind_spots"}` and the extraction prompt's
`{"items": [{"name", ..., "source_row_index"}]}` -- not from the parsers'
constants (CLAUDE.md: author AI fixtures from the prompt).
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from scripts.measure_ai_consistency import (
    Refused,
    attack_downstream,
    compare_pair,
    main,
    measure_attack,
    measure_tech_debt,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus

pytestmark = pytest.mark.unit

TOOLS = ["Falcon Sensor", "Sentinel Hub", "Vault Backup"]


# --- compare_pair: list fields are sets --------------------------------------


def _tech(code: str, **fields) -> dict:
    row = {
        "technique_code": code,
        "status": "covered",
        "reason_code": None,
        "detection_tools": [],
        "prevention_tools": [],
        "response_tools": [],
        "rationale": "r",
    }
    row.update(fields)
    return row


def test_tool_lists_in_another_order_are_the_same_answer() -> None:
    a = {"techniques": [_tech("T1", detection_tools=["A", "B"])]}
    b = {"techniques": [_tech("T1", detection_tools=["B", "A"])]}
    d = compare_pair("mitre_map", a, b)["fields"]["detection_tools"]
    assert d["compared"] == 1
    assert d["judged"] == 1
    assert d["equal"] == 1
    assert d["mean_jaccard"] == 1.0
    assert d["not_a_list"] == 0


def test_a_dropped_tool_is_a_partial_overlap_not_a_match() -> None:
    a = {"techniques": [_tech("T1", response_tools=["A"])]}
    b = {"techniques": [_tech("T1", response_tools=["A", "B"])]}
    d = compare_pair("mitre_map", a, b)["fields"]["response_tools"]
    assert d["equal"] == 0
    assert d["mean_jaccard"] == 0.5


def test_a_bare_string_for_a_tool_list_is_counted_never_turned_into_a_set() -> None:
    a = {"techniques": [_tech("T1", prevention_tools="A")]}
    b = {"techniques": [_tech("T1", prevention_tools=["A"])]}
    d = compare_pair("mitre_map", a, b)["fields"]["prevention_tools"]
    assert d["compared"] == 1
    assert d["not_a_list"] == 1
    assert d["equal"] == 0
    assert d["mean_jaccard"] is None


def test_two_empty_tool_lists_are_counted_apart_never_as_agreement() -> None:
    a = {"techniques": [_tech("T1")]}
    d = compare_pair("mitre_map", a, json.loads(json.dumps(a)))["fields"]["detection_tools"]
    assert d["compared"] == 1
    assert d["both_empty"] == 1
    assert d["judged"] == 0
    assert d["equal"] == 0
    assert d["mean_jaccard"] is None


def test_a_prompt_that_cites_fewer_tools_never_scores_as_more_consistent() -> None:
    # Prompt X cites tools on both techniques and its runs half-agree on one.
    x_a = {"techniques": [_tech("T1", detection_tools=["A"]), _tech("T2", detection_tools=["B"])]}
    x_b = {"techniques": [_tech("T1", detection_tools=["A"]), _tech("T2", detection_tools=["C"])]}
    # Prompt Y is worse: it cites nothing on T2 in either run, and the same on T1.
    y_a = {"techniques": [_tech("T1", detection_tools=["A"]), _tech("T2")]}
    y_b = {"techniques": [_tech("T1", detection_tools=["A"]), _tech("T2")]}
    x = compare_pair("mitre_map", x_a, x_b)["fields"]["detection_tools"]
    y = compare_pair("mitre_map", y_a, y_b)["fields"]["detection_tools"]
    # Y's empty row is disclosed, and adds nothing to Y's agreement.
    assert (y["judged"], y["equal"], y["both_empty"]) == (1, 1, 1)
    assert (x["judged"], x["equal"], x["both_empty"]) == (2, 1, 0)
    # Y agrees on 1 of 1 judged where X agrees on 1 of 2: Y's score comes from
    # T1 alone, never from the row it stopped citing.
    assert y["equal"] <= x["equal"]
    y_one = compare_pair(
        "mitre_map",
        {"techniques": [_tech("T1", detection_tools=["A"])]},
        {"techniques": [_tech("T1", detection_tools=["A"])]},
    )["fields"]["detection_tools"]
    assert y["mean_jaccard"] == y_one["mean_jaccard"], "an empty row moved the Jaccard"


def test_a_row_with_no_key_is_unkeyable_never_compared_under_null() -> None:
    def item(name: str, idx) -> dict:
        return {
            "name": name,
            "vendor": None,
            "category": None,
            "function": None,
            "annual_cost_usd": None,
            "license_count": None,
            "notes": None,
            "confidence_pct": 90,
            "source_row_index": idx,
            "security_related": None,
            "security_functions": [],
        }

    a = {"items": [item("Alpha", 0), item("Beta", None)]}
    b = {"items": [item("Alpha", 0), item("Gamma", None)]}
    r = compare_pair("tech_debt_extract", a, b)
    assert r["rows"]["in_both"] == 1, "two unrelated null-keyed items were paired"
    assert (r["rows"]["unkeyable_a"], r["rows"]["unkeyable_b"]) == (1, 1)
    # Non-objects are dropped by the extraction's own parser before this sees
    # them, so the count is not observable here and says so.
    assert r["rows"]["unreadable_a"] is None
    assert r["fields"]["name"]["compared"] == 1


def test_mitre_map_compares_status_and_reason_and_never_the_rationale() -> None:
    a = {"techniques": [_tech("T1", status="partial", reason_code="detection_weak")]}
    b = {"techniques": [_tech("T1", status="gap", rationale="different words")]}
    fields = compare_pair("mitre_map", a, b)["fields"]
    assert fields["status"]["equal"] == 0
    assert fields["reason_code"]["equal"] == 0
    assert "rationale" not in fields


def test_security_functions_are_a_set_and_scalars_are_exact() -> None:
    def item(**kw) -> dict:
        base = {
            "name": "X",
            "vendor": None,
            "category": None,
            "function": "f",
            "annual_cost_usd": 10.0,
            "license_count": 5,
            "notes": "n",
            "confidence_pct": 90,
            "source_row_index": 0,
            "security_related": True,
            "security_functions": ["detect", "respond"],
        }
        base.update(kw)
        return base

    a = {"items": [item()]}
    b = {"items": [item(security_functions=["respond", "detect"], license_count=6, notes="m")]}
    fields = compare_pair("tech_debt_extract", a, b)["fields"]
    assert fields["security_functions"]["equal"] == 1
    assert fields["license_count"]["equal"] == 0
    assert fields["license_count"]["within_one"] == 1
    assert "notes" not in fields and "function" not in fields


# --- attack_downstream: the engine decides the status ------------------------


def _resolver():
    from app.attack.citations import Candidate, CitationResolver

    return CitationResolver([Candidate(name=t) for t in TOOLS])


def _a_code(*, preventable: bool) -> str:
    from app.attack.catalog import NOT_PREVENTABLE, TECHNIQUES

    return next(
        t.id for t in TECHNIQUES if (t.id not in NOT_PREVENTABLE) is preventable and "." not in t.id
    )


def test_all_three_functions_from_listed_tools_compute_covered() -> None:
    code = _a_code(preventable=True)
    data = {
        "techniques": [
            _tech(
                code,
                status="partial",
                detection_tools=["Sentinel Hub"],
                prevention_tools=["Falcon Sensor"],
                response_tools=["Vault Backup"],
            )
        ]
    }
    out = attack_downstream(data, _resolver())
    assert out["computed_status"] == {code: "covered"}
    # The AI said partial; the arrays say covered.
    assert out["ai_status_differs"] == 1


def test_a_tool_not_on_the_list_provides_nothing() -> None:
    code = _a_code(preventable=True)
    data = {
        "techniques": [
            _tech(
                code,
                detection_tools=["Sentinel Hub"],
                prevention_tools=["Some Tool The Client Lacks"],
                response_tools=["Vault Backup"],
            )
        ]
    }
    assert attack_downstream(data, _resolver())["computed_status"] == {code: "partial"}


def test_a_technique_that_cannot_be_prevented_is_judged_on_detect_and_respond() -> None:
    code = _a_code(preventable=False)
    data = {
        "techniques": [
            _tech(code, detection_tools=["Sentinel Hub"], response_tools=["Vault Backup"])
        ]
    }
    assert attack_downstream(data, _resolver())["computed_status"] == {code: "covered"}


def test_an_inferred_citation_is_awaiting_review_not_in_place() -> None:
    # "CrowdStrike" for "CrowdStrike Falcon Enterprise" is resolved but INFERRED
    # (the near miss `test_attack_run_ai.py` pins). A fresh run records it as an
    # uncleared citation, so R3 counts it awaiting review: not in place.
    from app.attack.citations import Candidate, CitationResolver

    resolver = CitationResolver(
        [Candidate(name="CrowdStrike Falcon Enterprise"), Candidate(name="Vault Backup")]
    )
    code = _a_code(preventable=False)
    inferred = {
        "techniques": [
            _tech(code, detection_tools=["CrowdStrike"], response_tools=["Vault Backup"])
        ]
    }
    exact = {
        "techniques": [
            _tech(
                code,
                detection_tools=["CrowdStrike Falcon Enterprise"],
                response_tools=["Vault Backup"],
            )
        ]
    }
    assert attack_downstream(exact, resolver)["computed_status"] == {code: "covered"}
    assert attack_downstream(inferred, resolver)["computed_status"] == {code: "partial"}


def test_no_tools_computes_a_gap() -> None:
    code = _a_code(preventable=True)
    out = attack_downstream({"techniques": [_tech(code, status="gap")]}, _resolver())
    assert out == {"computed_status": {code: "gap"}, "ai_status_differs": 0}


# --- the real paths ----------------------------------------------------------


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


def _admin_client(c: TestClient) -> tuple[dict, str, str]:
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}, cid, me["id"]


def _tech_debt_service(TestSession: sessionmaker, cid: str, uid: str, tools: list[str]) -> str:
    """A Tech Debt service whose approved list holds `tools`, in security scope.
    Returns its id."""
    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=uuid.UUID(cid),
            opened_by=uuid.UUID(uid),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        for name in tools:
            db.add(CapabilityItem(capability_list_id=cl.id, name=name))
        db.commit()
        return str(svc.id)


@pytest.fixture()
def attack_world(world):
    c, TestSession, provider = world
    h, cid, uid = _admin_client(c)
    _tech_debt_service(TestSession, cid, uid, TOOLS)
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    yield c, TestSession, provider


def _cover_every_asked_technique(payload: dict) -> LLMResponse:
    # The prompt: "For each technique you can speak to, suggest a coverage status
    # ... and which listed tools provide detection, prevention, and response".
    techniques = [
        {
            "technique_code": code,
            "status": "covered",
            "reason_code": None,
            "detection_tools": ["Sentinel Hub"],
            "prevention_tools": ["Falcon Sensor"],
            "response_tools": ["Vault Backup"],
            "rationale": "Listed tools address it.",
        }
        for code in payload["technique_codes"]
    ]
    body = {"techniques": techniques, "executive_summary": "s", "top_blind_spots": []}
    return LLMResponse(json.dumps(body), input_tokens=3, output_tokens=5)


def _coverage_rows(db: Session) -> list[tuple]:
    from app.models.attack_assessment import AttackCoverage

    return sorted(
        (
            r.technique_code,
            r.status,
            r.reason_code,
            tuple(r.detection_tools or ()),
            tuple(r.prevention_tools or ()),
            tuple(r.response_tools or ()),
            r.rationale,
            r.updated_at,
        )
        for r in db.execute(select(AttackCoverage)).scalars()
    )


def _llm_call_count(db: Session) -> int:
    from app.models.llm_call import LLMCall

    return db.execute(select(func.count()).select_from(LLMCall)).scalar_one()


def _recording(asked: list[list[str]]):
    """The prompt-shaped answer, recording each batch's codes as SENT. The
    batch sizes are observed from the calls, never read from the route's own
    batch-size constant."""

    def respond(payload: dict) -> LLMResponse:
        asked.append(list(payload["technique_codes"]))
        return _cover_every_asked_technique(payload)

    return respond


def _techniques_the_route_sends(db: Session) -> list[str]:
    # D-094: a computed parent is never sent; everything else is, sorted.
    from app.attack.parents import is_computed_parent
    from app.models.attack_assessment import AttackCoverage

    codes = db.execute(select(AttackCoverage.technique_code)).scalars()
    return sorted(c for c in codes if not is_computed_parent(c))


def test_measure_attack_runs_every_batch_and_applies_nothing(attack_world) -> None:
    _, TestSession, provider = attack_world
    asked: list[list[str]] = []
    provider.register("mitre_map", _recording(asked))
    with TestSession() as db:
        before = _coverage_rows(db)
        expected_codes = _techniques_the_route_sends(db)
        report = measure_attack(db, LLMClient(provider), runs=2)
        db.commit()
    with TestSession() as db:
        assert _coverage_rows(db) == before
        calls = _llm_call_count(db)

    sent = report["techniques_sent"]
    batches = len(asked) // 2
    assert sent == len(expected_codes)
    assert batches > 1, "precondition: more than one batch"
    # Each run asked for every technique exactly once, across its batches.
    assert sorted(c for b in asked for c in b) == sorted(expected_codes * 2)
    assert report["runs_ok"] == 2
    assert report["batches_per_run"] == batches
    assert calls == len(asked)
    pair = report["pairs"][0]
    assert pair["rows"]["in_both"] == sent
    assert pair["fields"]["status"]["equal"] == sent
    assert pair["fields"]["detection_tools"]["mean_jaccard"] == 1.0
    assert pair["computed_status"] == {"compared": sent, "equal": sent}
    # Every tool cited exactly as listed, all three functions present.
    assert report["downstream"][0]["computed_status_counts"] == {"covered": sent}
    assert report["tokens"] == {
        "input": 2 * batches * 3,
        "output": 2 * batches * 5,
        "complete": True,
    }
    assert report["exit_code"] == 0


def test_a_mitre_map_run_with_a_failed_batch_is_a_failed_run(attack_world) -> None:
    from app.models.attack_assessment import AttackAssessment
    from app.models.client import Client
    from app.routes.attack import _attack_ai_request_for

    _, TestSession, provider = attack_world
    with TestSession() as db:
        a = db.execute(select(AttackAssessment)).scalar_one()
        first_code = _attack_ai_request_for(db, a, db.execute(select(Client)).scalar_one())
        first_code = first_code.preview.inputs["technique_codes"][0]
    first_batch_calls: list[int] = []

    def run_twos_first_batch_fails(payload: dict) -> LLMResponse:
        # Batches run concurrently, so a call COUNT does not say which run a
        # call belongs to. The first batch is sent once per run, though: its
        # second sending is run 2's.
        if first_code in payload["technique_codes"]:
            first_batch_calls.append(1)
            if len(first_batch_calls) == 2:
                return LLMResponse("not json at all")
        return _cover_every_asked_technique(payload)

    provider.register("mitre_map", run_twos_first_batch_fails)
    with TestSession() as db:
        report = measure_attack(db, LLMClient(provider), runs=2)
    assert report["runs_ok"] == 1
    assert report["failed_runs"][0]["run"] == 2
    assert report["failed_runs"][0]["failure"].startswith("batches_failed:1/")
    assert report["pairs"] == []
    assert report["exit_code"] == 1


def test_a_mitre_map_probe_sends_only_the_first_batches(attack_world) -> None:
    _, TestSession, provider = attack_world
    asked: list[list[str]] = []
    provider.register("mitre_map", _recording(asked))
    with TestSession() as db:
        expected_codes = _techniques_the_route_sends(db)
        report = measure_attack(db, LLMClient(provider), runs=1, probe_batches=2)
        db.commit()
    with TestSession() as db:
        assert _llm_call_count(db) == 2
    probed = sorted(c for b in asked for c in b)
    assert len(asked) == 2
    # The FIRST batches: a prefix of what a full run sends, and nothing else.
    assert probed == expected_codes[: len(probed)]
    assert len(probed) < len(expected_codes)
    assert report["techniques_sent"] == len(probed)
    assert report["probe"]["batches"] == 2
    assert report["probe"]["of"] > 2
    assert report["exit_code"] == 0


def test_a_probe_as_large_as_a_full_run_is_refused(attack_world) -> None:
    _, TestSession, provider = attack_world
    provider.register("mitre_map", _cover_every_asked_technique)
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_attack(db, LLMClient(provider), runs=1, probe_batches=10_000)
    assert exc.value.reason == "probe_not_smaller"


def test_a_client_with_no_tools_is_refused_before_any_call(world) -> None:
    c, TestSession, provider = world
    h, _, _ = _admin_client(c)
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h)
    provider.register("mitre_map", _cover_every_asked_technique)
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_attack(db, LLMClient(provider), runs=2)
    assert exc.value.reason == "builder_refused"
    with TestSession() as db:
        assert _llm_call_count(db) == 0


# --- tech_debt_extract -------------------------------------------------------

INVENTORY = (
    "Product,Vendor,Annual Cost,Licenses\n"
    "Falcon Sensor,Acme Security,1200,50\n"
    "Payroll Plus,PayCo,800,20\n"
    "Total,,2000,\n"
)


@pytest.fixture()
def td_world(world, tmp_path):
    c, TestSession, provider = world
    _, cid, uid = _admin_client(c)
    sid = _tech_debt_service(TestSession, cid, uid, [])
    inv = tmp_path / "inventory.csv"
    inv.write_text(INVENTORY, encoding="utf-8")
    yield TestSession, provider, str(inv), sid


def _extract(licences: object) -> callable:
    # The prompt's own item shape. Row 2 (the total) gets no item: "Skip a row
    # ONLY when it is a note, a blank, a column header, or a duplicate" -- the
    # model chose to skip it, which the reconciliation must report.
    def respond(payload: dict) -> LLMResponse:
        assert len(payload["rows"]) == 3
        items = [
            {
                "name": "Falcon Sensor",
                "vendor": "Acme Security",
                "category": "EDR",
                "function": "Endpoint protection.",
                "annual_cost_usd": 1200,
                "license_count": licences,
                "notes": None,
                "security_related": True,
                "security_functions": ["prevent", "detect"],
                "confidence_pct": 90,
                "source_row_index": 0,
            },
            {
                "name": "Payroll Plus",
                "vendor": "PayCo",
                "category": "HCM",
                "function": "Payroll.",
                "annual_cost_usd": 800,
                "license_count": 20,
                "notes": None,
                "security_related": False,
                "security_functions": [],
                "confidence_pct": 100,
                "source_row_index": 1,
            },
        ]
        return LLMResponse(json.dumps({"items": items}), input_tokens=4, output_tokens=6)

    return respond


def _item_count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(CapabilityItem)).scalar_one()


def test_measure_tech_debt_extracts_the_inventory_and_applies_nothing(td_world) -> None:
    TestSession, provider, inv, sid = td_world
    provider.register("extract.capabilities", _extract(50))
    with TestSession() as db:
        before = _item_count(db)
        report = measure_tech_debt(db, LLMClient(provider), runs=2, inventory=inv, service_id=sid)
        db.commit()
    with TestSession() as db:
        assert _item_count(db) == before
        assert _llm_call_count(db) == 2

    assert report["rows_sent"] == 3
    assert report["runs_ok"] == 2
    pair = report["pairs"][0]
    assert pair["rows"]["in_both"] == 2
    assert pair["fields"]["license_count"]["equal"] == 2
    # Falcon's functions are judged; Payroll's [] / [] is disclosed, not agreement.
    sf = pair["fields"]["security_functions"]
    assert (sf["judged"], sf["equal"], sf["both_empty"], sf["mean_jaccard"]) == (1, 1, 1, 1.0)
    assert report["downstream"][0] == {
        "run": 1,
        "excluded_row_indexes": [2],
        "attribution_complete": True,
        "security_related": {"false": 1, "true": 1},
    }
    assert report["tokens"] == {"input": 8, "output": 12, "complete": True}
    assert report["exit_code"] == 0


def test_tech_debt_compares_what_the_parser_would_store(td_world) -> None:
    # "1,000" and 1000 are different answers from the model, but the parser
    # stores both as 1000 (`_coerce_item` accepts a whole number written
    # differently, #833); the measure compares what is stored, not what was sent.
    TestSession, provider, inv, sid = td_world
    answers = iter([_extract("1,000"), _extract(1000)])
    provider.register("extract.capabilities", lambda p: next(answers)(p))
    with TestSession() as db:
        report = measure_tech_debt(db, LLMClient(provider), runs=2, inventory=inv, service_id=sid)
    assert report["pairs"][0]["fields"]["license_count"]["equal"] == 2


def test_an_unparseable_extraction_is_a_failed_run(td_world) -> None:
    TestSession, provider, inv, sid = td_world
    provider.register_static("extract.capabilities", LLMResponse('{"items": "nope"}'))
    with TestSession() as db:
        report = measure_tech_debt(db, LLMClient(provider), runs=2, inventory=inv, service_id=sid)
    assert report["runs_ok"] == 0
    assert len(report["failed_runs"]) == 2
    assert report["exit_code"] == 1


def test_an_inventory_in_another_format_is_refused(td_world, tmp_path) -> None:
    TestSession, provider, _, sid = td_world
    other = tmp_path / "inventory.pdf"
    other.write_bytes(b"%PDF")
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_tech_debt(db, LLMClient(provider), runs=2, inventory=str(other), service_id=sid)
    assert exc.value.reason == "inventory_format"


@pytest.mark.parametrize(
    ("service_id", "reason"),
    [(str(uuid.uuid4()), "no_tech_debt_service"), ("not-a-uuid", "service_id_invalid")],
)
def test_a_service_id_naming_no_tech_debt_service_is_refused(
    td_world, service_id: str, reason: str
) -> None:
    TestSession, provider, inv, _ = td_world
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_tech_debt(db, LLMClient(provider), runs=2, inventory=inv, service_id=service_id)
    assert exc.value.reason == reason
    with TestSession() as db:
        assert _llm_call_count(db) == 0


def test_a_service_of_another_kind_is_refused(attack_world, tmp_path) -> None:
    from app.models.service import Service, ServiceKind

    _, TestSession, provider = attack_world
    inv = tmp_path / "inventory.csv"
    inv.write_text(INVENTORY, encoding="utf-8")
    with TestSession() as db:
        attack_sid = str(
            db.execute(select(Service.id).where(Service.kind == ServiceKind.ATTACK_COVERAGE))
            .scalars()
            .one()
        )
        with pytest.raises(Refused) as exc:
            measure_tech_debt(
                db, LLMClient(provider), runs=2, inventory=str(inv), service_id=attack_sid
            )
    assert exc.value.reason == "no_tech_debt_service"


def test_the_inventory_is_redacted_with_the_named_clients_names_not_the_newest(
    world, tmp_path
) -> None:
    """#867 review, blocking: the inventory names no client, so the client
    whose names are redacted must be the one the operator NAMED. Two tenants,
    the named one created FIRST: picking "the newest Tech Debt service" would
    redact Globex's export with Acme's names and send "Globex" in clear."""
    c, TestSession, provider = world
    h, acme_cid, uid = _admin_client(c)
    globex_cid = c.post(
        "/admin/clients",
        headers={"Authorization": h["Authorization"]},
        json={"legal_name": "Globex"},
    ).json()["id"]
    globex_sid = _tech_debt_service(TestSession, globex_cid, uid, [])
    _tech_debt_service(TestSession, acme_cid, uid, [])  # newer, and NOT named
    inv = tmp_path / "inventory.csv"
    inv.write_text("Product,Vendor\nGlobex Portal,Globex\n", encoding="utf-8")
    seen: list[str] = []

    def record(payload: dict) -> LLMResponse:
        seen.append(json.dumps(payload["rows"]))
        return LLMResponse(json.dumps({"items": []}), input_tokens=1, output_tokens=1)

    provider.register("extract.capabilities", record)
    with TestSession() as db:
        report = measure_tech_debt(
            db, LLMClient(provider), runs=2, inventory=str(inv), service_id=globex_sid
        )
    assert seen, "precondition: the provider was called"
    assert all("Globex" not in s for s in seen), "the named client's name was sent in clear"
    assert all("[CLIENT]" in s for s in seen)
    assert report["redaction_client_id"] == globex_cid
    assert report["service_id"] == globex_sid


# --- the command line ----------------------------------------------------------


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

    # Every measurement is replaced by a typed refusal naming itself, so a
    # command line that gets PAST the argument checks ends in a recognisable
    # "measure_reached" -- never in whatever the empty database would raise.
    # That is what lets the refusal tests below fail on their assertions,
    # not on a crash, when a guard is removed.
    import scripts.measure_ai_consistency as m

    def reached(name: str):
        def stub(db, llm, **kw):
            raise Refused(
                "measure_reached",
                f"{name} probe_batches={kw.get('probe_batches')} "
                f"service_id={kw.get('service_id')}",
            )

        return stub

    for name in ("measure_zt", "measure_csf", "measure_attack", "measure_tech_debt"):
        monkeypatch.setattr(m, name, reached(name))
    get_settings.cache_clear()
    yield built, tmp_path
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "argv",
    [
        ["--job", "tech_debt_extract", "--runs", "2", "--service-id", "s"],
        ["--job", "zt_score", "--runs", "2", "--inventory", "x.csv"],
    ],
)
def test_main_requires_an_inventory_for_tech_debt_and_only_for_it(cli, capsys, argv) -> None:
    built, tmp_path = cli
    code = main([*argv, "--out", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    # Refused by the argument check itself: no provider was built and no
    # measurement was reached (`stub_measures` would say so).
    assert "REFUSED (inventory_mismatch)" in err
    assert "measure_reached" not in err
    assert built == []
    assert code == 2


def test_main_refuses_to_reopen_for_tech_debt(cli, capsys) -> None:
    built, tmp_path = cli
    argv = ["--job", "tech_debt_extract", "--runs", "2", "--inventory", "x.csv"]
    argv += ["--service-id", "s"]
    code = main([*argv, "--reopen-released", "--out", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    assert "REFUSED (reopen_not_applicable)" in err
    assert "measure_reached" not in err
    assert built == []
    assert code == 2


def test_main_accepts_a_probe_for_mitre_map(cli, capsys) -> None:
    # Past the argument checks: a provider was built and `measure_attack` was
    # called with the probe -- so the probe flag itself was accepted.
    built, tmp_path = cli
    argv = ["--job", "mitre_map", "--runs", "1", "--probe-batches", "1"]
    code = main([*argv, "--out", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    assert "probe_not_applicable" not in err
    assert "REFUSED (measure_reached): measure_attack probe_batches=1 " in err
    assert built == [1]
    assert code == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--job", "tech_debt_extract", "--runs", "2", "--inventory", "x.csv"],
        ["--job", "zt_score", "--runs", "2", "--service-id", "s"],
    ],
)
def test_main_requires_a_service_id_for_tech_debt_and_only_for_it(cli, capsys, argv) -> None:
    # #867 review (security): the inventory names no client, so whose names are
    # redacted is never guessed.
    built, tmp_path = cli
    code = main([*argv, "--out", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    assert "REFUSED (service_id_mismatch)" in err
    assert "measure_reached" not in err
    assert built == []
    assert code == 2


def test_main_passes_the_named_service_to_the_tech_debt_measure(cli, capsys) -> None:
    built, tmp_path = cli
    argv = ["--job", "tech_debt_extract", "--runs", "2", "--inventory", "x.csv"]
    code = main([*argv, "--service-id", "svc-42", "--out", str(tmp_path / "o.json")])
    err = capsys.readouterr().err
    assert (
        "REFUSED (measure_reached): measure_tech_debt probe_batches=None service_id=svc-42" in err
    )
    assert built == [1]
    assert code == 2


# --- #867 narrow review F1: two nulls are not agreement -------------------------


def _td_item(**kw) -> dict:
    base = {
        "name": "Alpha",
        "vendor": None,
        "category": None,
        "function": None,
        "annual_cost_usd": None,
        "license_count": None,
        "notes": None,
        "confidence_pct": None,
        "source_row_index": 0,
        "security_related": None,
        "security_functions": [],
    }
    base.update(kw)
    return base


def test_two_nulls_on_a_scalar_field_are_counted_apart_never_as_agreement() -> None:
    # A prompt that extracts nothing: every scalar null in both runs.
    nothing = {"items": [_td_item(source_row_index=i) for i in range(3)]}
    fields = compare_pair("tech_debt_extract", nothing, json.loads(json.dumps(nothing)))["fields"]
    for f in ("vendor", "category", "annual_cost_usd", "license_count", "confidence_pct"):
        assert fields[f]["compared"] == 3
        assert fields[f]["both_null"] == 3, f
        assert fields[f]["equal"] == 0, f"{f}: null/null counted as agreement"


def test_extracting_less_never_scores_as_more_consistent() -> None:
    # Prompt X extracts a vendor on both rows and its runs agree on one.
    x_a = {
        "items": [
            _td_item(source_row_index=0, vendor="A"),
            _td_item(source_row_index=1, vendor="B"),
        ]
    }
    x_b = {
        "items": [
            _td_item(source_row_index=0, vendor="A"),
            _td_item(source_row_index=1, vendor="C"),
        ]
    }
    # Prompt Y extracts nothing for row 1 in either run.
    y_a = {"items": [_td_item(source_row_index=0, vendor="A"), _td_item(source_row_index=1)]}
    y_b = {"items": [_td_item(source_row_index=0, vendor="A"), _td_item(source_row_index=1)]}
    x = compare_pair("tech_debt_extract", x_a, x_b)["fields"]["vendor"]
    y = compare_pair("tech_debt_extract", y_a, y_b)["fields"]["vendor"]
    assert (x["equal"], x["both_null"]) == (1, 0)
    # Y's null row is disclosed, and adds nothing to Y's agreement.
    assert (y["equal"], y["both_null"]) == (1, 1)


def test_a_null_reason_code_is_counted_as_both_null_for_mitre_map() -> None:
    # Covered and gap take reason_code null, which IS an answer; it is still
    # reported apart, so the reader sees how much agreement is null/null.
    a = {
        "techniques": [
            _tech("T1", status="covered"),
            _tech("T2", status="partial", reason_code="detection_weak"),
        ]
    }
    r = compare_pair("mitre_map", a, json.loads(json.dumps(a)))["fields"]["reason_code"]
    assert (r["compared"], r["equal"], r["both_null"]) == (2, 1, 1)
