"""The synthetic corpus for the #806 live pass, and the measure's input fixes.

Comment 5983938383, section 2 (approved in #736, comment 5984022081, item 8):
the demo seed's notes cannot exercise the new prompts, so the measure gets a
committed synthetic corpus -- `--notes-corpus` for csf_score and zt_score, and a
synthetic XLSX for tech_debt_extract -- and a per-service cost cap from which
the `--max-output-tokens` guard is set.

What these tests pin:

* the corpus holds a row per class the section names, each class checked by its
  own PROPERTY (a duplicate row really equals another row, a total row really
  is one), with the expected classes copied from the section's text;
* the XLSX is the JSON source, read back by the upload's own parser;
* corpus text reaches the provider through the redacting egress client, as any
  input does: the client's name never arrives, `[CLIENT]` does;
* every branch that could exit 0 without having looked exits 2 with its own
  typed reason, before any provider exists;
* `--out` is opened before any paid call (#806 comment 5965052688);
* `charged_likely` follows the `llm_calls` rows the failed calls wrote, not an
  assumption (#806 comments 5965066136 and 5965088703).

Model responses are written from each prompt's JSON shape, never from the
parsers' constants (CLAUDE.md: author AI fixtures from the prompt).
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from scripts.measure_ai_consistency import (
    COST_CAPS_USD,
    Refused,
    load_notes_corpus,
    main,
    measure_attack,
    measure_csf,
    measure_tech_debt,
    measure_zt,
    summarize,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse

pytestmark = pytest.mark.unit

CORPUS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "measure_corpus"
NOTES = CORPUS_DIR / "notes.json"
TD_JSON = CORPUS_DIR / "tech_debt_inventory.json"
TD_XLSX = CORPUS_DIR / "tech_debt_inventory.xlsx"

#: Section 2's notes classes, in its words: "a practice; a negative ("No
#: MFA"); a plan ("planned FY27"); a pilot or partial deployment; a
#: tier-limited statement ("only on high-impact systems"); blank, "N/A" and
#: "TBD"; and a placeholder."
SECTION_2_NOTE_CLASSES = [
    "practice",
    "negative",
    "plan",
    "pilot_or_partial",
    "tier_limited",
    "blank",
    "not_applicable",
    "tbd",
    "placeholder",
]

#: Section 2's XLSX classes: "total and subtotal rows, an exact duplicate, a
#: planned security tool with a cost, a retired row with no cost, "$1,200", a
#: monthly cost, a suite with modules, two products in one row, a `[CLIENT]`
#: name and an off-list category."
SECTION_2_XLSX_CLASSES = {
    "total",
    "subtotal",
    "exact_duplicate",
    "planned_security_tool_with_cost",
    "retired_no_cost",
    "dollar_string",
    "monthly_cost",
    "suite_with_modules",
    "two_products_one_row",
    "client_name",
    "off_list_category",
}


# --- the notes corpus ----------------------------------------------------------


def _notes_doc() -> dict:
    return json.loads(NOTES.read_text(encoding="utf-8"))


def _notes_of(cls: str) -> list[str]:
    return next(c["notes"] for c in _notes_doc()["classes"] if c["class"] == cls)


def test_the_notes_corpus_has_exactly_section_2s_classes_in_order() -> None:
    assert [c["class"] for c in _notes_doc()["classes"]] == SECTION_2_NOTE_CLASSES


def test_each_notes_class_carries_the_text_section_2_names() -> None:
    assert "No MFA." in _notes_of("negative")
    assert any("Planned FY27" in n for n in _notes_of("plan"))
    assert any("only on high-impact systems" in n for n in _notes_of("tier_limited"))
    assert _notes_of("blank") == [""]
    assert _notes_of("not_applicable") == ["N/A"]
    assert _notes_of("tbd") == ["TBD"]
    assert any("Pilot" in n for n in _notes_of("pilot_or_partial"))
    assert any("Partially deployed" in n for n in _notes_of("pilot_or_partial"))
    assert "See interview notes." in _notes_of("placeholder")


def test_the_notes_corpus_names_its_client_only_through_the_placeholder() -> None:
    # The one client reference is the placeholder, so the redactor is handed a
    # REAL client name at measure time; a practice note carries it.
    assert any("{{CLIENT_NAME}}" in n for n in _notes_of("practice"))


def test_the_committed_notes_corpus_loads() -> None:
    corpus = load_notes_corpus(str(NOTES))
    assert [c for c, _ in corpus.classes] == SECTION_2_NOTE_CLASSES
    assert len(corpus.sha256) == 64


# --- the Tech Debt XLSX ----------------------------------------------------------


def _td_doc() -> dict:
    return json.loads(TD_JSON.read_text(encoding="utf-8"))


def _cell(row: list[str], column: str) -> str:
    return row[_td_doc()["header"].index(column)]


def _annual(cost: str) -> int:
    # The sheet's own convention, stated in its `about`: a monthly cost counts
    # twelve times. Parsed here independently of anything the measure does.
    if cost.endswith("/month"):
        return int(cost.removesuffix("/month").lstrip("$").replace(",", "")) * 12
    return int(cost.lstrip("$").replace(",", "")) if cost else 0


def test_the_xlsx_corpus_has_a_row_for_every_section_2_class() -> None:
    classes = _td_doc()["classes"]
    assert set(classes) == SECTION_2_XLSX_CLASSES
    assert all(classes[c] for c in classes), "a class with no row"


def test_each_xlsx_class_row_has_its_property() -> None:
    doc = _td_doc()
    rows, cls = doc["rows"], doc["classes"]

    def at(name: str) -> list[list[str]]:
        return [rows[i] for i in cls[name]]

    (total,) = at("total")
    assert _cell(total, "Product") == "TOTAL"
    subtotals = at("subtotal")
    assert all(_cell(r, "Product").startswith("Subtotal") for r in subtotals)
    assert _annual(_cell(total, "Annual Cost")) == sum(
        _annual(_cell(r, "Annual Cost")) for r in subtotals
    )
    a, b = cls["exact_duplicate"]
    assert a != b and rows[a] == rows[b], "the duplicate is a different row with equal cells"
    (planned,) = at("planned_security_tool_with_cost")
    assert _cell(planned, "Status").startswith("Planned") and _cell(planned, "Annual Cost")
    assert all(
        _cell(r, "Status") == "Retired" and _cell(r, "Annual Cost") == ""
        for r in at("retired_no_cost")
    )
    assert [_cell(r, "Annual Cost") for r in at("dollar_string")] == ["$1,200"]
    assert all(_cell(r, "Annual Cost").endswith("/month") for r in at("monthly_cost"))
    (suite,) = at("suite_with_modules")
    assert "Modules:" in _cell(suite, "Notes")
    (pair,) = at("two_products_one_row")
    assert " + " in _cell(pair, "Product")
    (named,) = at("client_name")
    assert _cell(named, "Product").startswith("{{CLIENT_NAME}} ")
    # v3.2's list is closed (comment 5983938383, C6(3)); this one is on no list.
    assert [_cell(r, "Category") for r in at("off_list_category")] == ["Cyber Misc"]


def test_each_subtotal_sums_the_active_rows_above_it() -> None:
    doc = _td_doc()
    rows, start = doc["rows"], 0
    for i in sorted(doc["classes"]["subtotal"]):
        active = [r for r in rows[start:i] if _cell(r, "Status") == "Active"]
        assert _annual(_cell(rows[i], "Annual Cost")) == sum(
            _annual(_cell(r, "Annual Cost")) for r in active
        )
        start = i + 1


def test_the_xlsx_corpus_is_about_forty_rows() -> None:
    # Section 2's cost row: "one call a run, ~40-row XLSX".
    assert 35 <= len(_td_doc()["rows"]) <= 45


def test_the_committed_xlsx_is_the_json_read_back_by_the_upload_parser() -> None:
    from app.tech_debt.parsers import parse_inventory

    doc = _td_doc()
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    parsed = parse_inventory(TD_XLSX.read_bytes(), mime)
    assert parsed == [dict(zip(doc["header"], r, strict=True)) for r in doc["rows"]]


def test_the_builder_writes_the_same_xlsx_from_the_json(tmp_path) -> None:
    from scripts.build_measure_corpus import write_inventory_xlsx

    from app.tech_debt.parsers import parse_inventory

    out = tmp_path / "rebuilt.xlsx"
    write_inventory_xlsx(TD_JSON, out)
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert parse_inventory(out.read_bytes(), mime) == parse_inventory(TD_XLSX.read_bytes(), mime)


def test_the_corpus_survives_the_redactor_except_the_client_name() -> None:
    """Every corpus string, with the placeholder filled, comes back from strict
    redaction unchanged except the client's name: a corpus the redactor
    garbled would measure the redactor, not the model (comment 5983938383,
    C8's concern, applied to this corpus)."""
    from app.ai.redact import redact_payload

    notes = [n for c in _notes_doc()["classes"] for n in c["notes"]]
    cells = [v for r in _td_doc()["rows"] for v in r]
    sent = [s.replace("{{CLIENT_NAME}}", "Acme Widgets") for s in notes + cells]
    out, _ = redact_payload(
        {"s": sent}, mode="strict", client_org_name="Acme Widgets", name_hints=()
    )
    assert out["s"] == [s.replace("{{CLIENT_NAME}}", "[CLIENT]") for s in notes + cells]


def test_the_corpus_holds_no_address_or_link() -> None:
    import re

    text = NOTES.read_text(encoding="utf-8") + TD_JSON.read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", text), "an email address"
    assert not re.search(r"https?://", text), "a link"


# --- load_notes_corpus: every "could not look" exits 2 with its own reason ------


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        pytest.param(None, "notes_corpus_unreadable", id="missing"),
        pytest.param("", "notes_corpus_empty", id="empty-file"),
        pytest.param("  \n", "notes_corpus_empty", id="whitespace-file"),
        pytest.param("{not json", "notes_corpus_invalid", id="not-json"),
        pytest.param("[]", "notes_corpus_invalid", id="not-an-object"),
        pytest.param('{"corpus": "x"}', "notes_corpus_invalid", id="no-classes"),
        pytest.param('{"corpus": "x", "classes": []}', "notes_corpus_empty", id="no-class"),
        pytest.param(
            '{"corpus": "x", "classes": [{"class": "a", "notes": []}]}',
            "notes_corpus_invalid",
            id="class-with-no-notes",
        ),
        pytest.param(
            '{"corpus": "x", "classes": [{"class": "a", "notes": [1]}]}',
            "notes_corpus_invalid",
            id="note-not-text",
        ),
        pytest.param(
            '{"corpus": "x", "classes": [{"class": "", "notes": ["n"]}]}',
            "notes_corpus_invalid",
            id="class-unnamed",
        ),
        pytest.param(
            '{"corpus": "x", "classes": [{"class": "a", "notes": ["n"]},'
            ' {"class": "a", "notes": ["m"]}]}',
            "notes_corpus_invalid",
            id="class-twice",
        ),
        pytest.param(
            '{"corpus": "x", "classes": [{"class": "a", "notse": ["n"]}]}',
            "notes_corpus_invalid",
            id="misspelt-key",
        ),
        pytest.param(
            '{"classes": [{"class": "a", "notes": ["n"]}]}',
            "notes_corpus_invalid",
            id="unnamed-corpus",
        ),
    ],
)
def test_a_corpus_that_cannot_be_read_is_refused(tmp_path, content, reason) -> None:
    path = tmp_path / "corpus.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(Refused) as exc:
        load_notes_corpus(str(path))
    assert exc.value.reason == reason


@pytest.mark.parametrize("which", ["empty-string", "directory"])
def test_a_corpus_path_naming_no_file_is_refused(tmp_path, which) -> None:
    path = "" if which == "empty-string" else str(tmp_path)
    with pytest.raises(Refused) as exc:
        load_notes_corpus(path)
    assert exc.value.reason == "notes_corpus_unreadable"


# --- the real paths: the corpus reaches the provider, redacted ------------------


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


def _admin(c: TestClient, legal_name: str = "Acme") -> tuple[dict, str, str]:
    bearer = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "Kentro Admin",
        },
    ).json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": legal_name},
    ).json()["id"]
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}, cid, me["id"]


def _zt(c: TestClient) -> str:
    h, cid, _ = _admin(c)
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "T"})
    assert c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h).status_code in (
        200,
        201,
    )
    return cid


def _zt_stages(db: Session) -> list[tuple]:
    from app.models.zt_assessment import ZtAnswer

    return sorted(
        (r.capability_code, r.maturity_stage, r.target_stage)
        for r in db.execute(select(ZtAnswer)).scalars()
    )


def _zt_recorder(seen: list[dict]):
    # `_ZT_SCORE_PROMPT`'s shape: {"capabilities": [{"code", "current", "target"}]}.
    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        rows = [{"code": code, "current": 1, "target": 2} for code in payload["capabilities"]]
        return LLMResponse(json.dumps({"capabilities": rows}), input_tokens=3, output_tokens=5)

    return respond


def _all_corpus_notes(client: str) -> set[str]:
    return {
        n.replace("{{CLIENT_NAME}}", client) for c in _notes_doc()["classes"] for n in c["notes"]
    }


def test_zt_sends_the_corpus_notes_redacted_and_says_so(world) -> None:
    c, TestSession, provider = world
    _zt(c)
    seen: list[dict] = []
    provider.register("zt_score", _zt_recorder(seen))
    corpus = load_notes_corpus(str(NOTES))
    with TestSession() as db:
        before = _zt_stages(db)
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2, notes_corpus=corpus)
        db.commit()
    with TestSession() as db:
        assert _zt_stages(db) == before, "the corpus changes notes, never a stage"

    assert len(seen) == 2
    for payload in seen:
        notes = [a["notes"] for a in payload["answers"].values()]
        blob = json.dumps(payload)
        assert "Acme" not in blob, "the client's name reached the provider"
        assert "{{CLIENT_NAME}}" not in blob, "the placeholder was sent unfilled"
        assert "[CLIENT] security team runs this daily" in blob
        # Every note sent is a corpus note, as the redactor leaves it.
        assert set(notes) <= _all_corpus_notes("[CLIENT]")
        assert {"No MFA.", "N/A", "TBD", ""} <= set(notes)
    setup = report["input_setup"]["notes_corpus"]
    assert setup["corpus"] == "measure-notes-v1"
    assert setup["sha256"] == corpus.sha256
    assert list(setup["classes"]) == SECTION_2_NOTE_CLASSES
    rows = len(seen[0]["capabilities"])
    assert setup["rows"] == rows
    assert sum(v["rows"] for v in setup["classes"].values()) == rows
    # ZT sends every row it builds, so every row a class landed on was sent.
    assert all(v["rows"] >= 1 and v["sent"] == v["rows"] for v in setup["classes"].values())
    assert setup["client_name_substituted"] >= 1
    assert report["runs_ok"] == 2


def test_without_a_corpus_the_report_records_none(world) -> None:
    c, TestSession, provider = world
    _zt(c)
    provider.register("zt_score", _zt_recorder([]))
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=2)
    assert "notes_corpus" not in report["input_setup"]


def test_a_placeholder_with_no_client_name_is_refused_before_any_call(world) -> None:
    from app.models.client import Client

    c, TestSession, provider = world
    cid = _zt(c)
    with TestSession() as db:
        db.get(Client, uuid.UUID(cid)).legal_name = None
        db.commit()
    provider.register("zt_score", _zt_recorder([]))
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_zt(
            db,
            LLMClient(provider),
            framework="cisa",
            runs=2,
            notes_corpus=load_notes_corpus(str(NOTES)),
        )
    assert exc.value.reason == "client_name_missing"
    with TestSession() as db:
        assert _llm_call_count(db) == 0


def _corpus_file(tmp_path: Path, classes: int, note: str = "Documented.") -> str:
    path = tmp_path / f"c{classes}.json"
    body = {
        "corpus": "test",
        "classes": [{"class": f"k{i}", "notes": [note]} for i in range(classes)],
    }
    path.write_text(json.dumps(body), encoding="utf-8")
    return str(path)


def test_more_classes_than_rows_is_refused(world, tmp_path) -> None:
    # Section 2 asks for "a row per class": a class that lands on no row would
    # be in the corpus and absent from every payload, unremarked.
    c, TestSession, provider = world
    _zt(c)
    provider.register("zt_score", _zt_recorder([]))
    with TestSession() as db:
        rows = len(_zt_stages(db))
    corpus = load_notes_corpus(_corpus_file(tmp_path, rows + 1))
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_zt(db, LLMClient(provider), framework="cisa", runs=2, notes_corpus=corpus)
    assert exc.value.reason == "notes_corpus_classes_unplaced"
    with TestSession() as db:
        assert _llm_call_count(db) == 0


def _llm_call_count(db: Session) -> int:
    from app.models.llm_call import LLMCall

    return db.execute(select(func.count()).select_from(LLMCall)).scalar_one()


# --- csf_score -----------------------------------------------------------------


@pytest.fixture()
def csf_world(world):
    c, TestSession, provider = world
    h, _, _ = _admin(c)
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "C"}).json()[
        "id"
    ]
    assert c.post(f"/csf/services/{svc_id}/assessments", headers=h).status_code in (200, 201)
    seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    yield c, TestSession, provider


def _csf_answer_all(seen: list[dict]):
    # `_CSF_SCORE_PROMPT`'s shape: {"scores": [{"tier", "subcategory_code",
    # five dimensions, "what_we_found"}]}.
    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        dims = ("governance", "policy", "implementation", "monitoring", "improvement")
        scores = [
            {"tier": t, "subcategory_code": code, **dict.fromkeys(dims, 1), "what_we_found": "x"}
            for t in payload["tiers"]
            for code in payload["subcategories"]
        ]
        return LLMResponse(json.dumps({"scores": scores}), input_tokens=7, output_tokens=11)

    return respond


def _set_csf_tiers(TestSession: sessionmaker, tier: int | None) -> None:
    from app.models.csf_assessment import CsfAnswer

    with TestSession() as db:
        for a in db.execute(select(CsfAnswer)).scalars():
            a.maturity_tier = tier
        db.commit()


def test_csf_sends_the_corpus_notes_redacted_and_counts_what_was_sent(csf_world) -> None:
    c, TestSession, provider = csf_world
    # The demo seed scores every answer; a scored answer is sent whatever its
    # notes say, so every class is sent.
    _set_csf_tiers(TestSession, 2)
    seen: list[dict] = []
    provider.register("csf_score", _csf_answer_all(seen))
    with TestSession() as db:
        report = measure_csf(
            db, LLMClient(provider), runs=2, notes_corpus=load_notes_corpus(str(NOTES))
        )
    assert seen, "precondition: the provider was called"
    for payload in seen:
        blob = json.dumps(payload["answers"])
        assert "Acme" not in blob, "the client's name reached the provider"
        assert "{{CLIENT_NAME}}" not in blob
        assert "[CLIENT] security team runs this daily" in blob
        notes = {a["notes"] for a in payload["answers"].values()}
        assert {"No MFA.", "N/A", "TBD"} <= notes
    setup = report["input_setup"]["notes_corpus"]
    assert list(setup["classes"]) == SECTION_2_NOTE_CLASSES
    assert all(v["sent"] == v["rows"] >= 1 for v in setup["classes"].values())
    assert report["runs_ok"] == 2


def test_csf_counts_a_class_the_route_does_not_send(csf_world) -> None:
    # The route sends only answers "with actual signal": with no tier and no
    # evidence, a blank note is not sent. The report says so per class rather
    # than claiming the class was measured.
    c, TestSession, provider = csf_world
    _set_csf_tiers(TestSession, None)
    provider.register("csf_score", _csf_answer_all([]))
    with TestSession() as db:
        report = measure_csf(
            db, LLMClient(provider), runs=2, notes_corpus=load_notes_corpus(str(NOTES))
        )
    classes = report["input_setup"]["notes_corpus"]["classes"]
    assert classes["blank"]["rows"] >= 1
    assert classes["blank"]["sent"] == 0
    assert classes["negative"]["sent"] == classes["negative"]["rows"]


def test_a_corpus_the_route_sends_none_of_is_refused(csf_world, tmp_path) -> None:
    c, TestSession, provider = csf_world
    _set_csf_tiers(TestSession, None)
    provider.register("csf_score", _csf_answer_all([]))
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_csf(
            db,
            LLMClient(provider),
            runs=2,
            notes_corpus=load_notes_corpus(_corpus_file(tmp_path, 2, note="")),
        )
    assert exc.value.reason == "notes_corpus_nothing_sent"
    with TestSession() as db:
        assert _llm_call_count(db) == 0


# --- tech_debt_extract: the committed XLSX ---------------------------------------


def _td_service(TestSession: sessionmaker, cid: str, uid: str) -> str:
    from app.models.service import Service, ServiceKind, ServiceStatus

    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=uuid.UUID(cid),
            opened_by=uuid.UUID(uid),
        )
        db.add(svc)
        db.commit()
        return str(svc.id)


def test_the_xlsx_corpus_reaches_the_provider_redacted(world) -> None:
    c, TestSession, provider = world
    _, cid, uid = _admin(c)
    sid = _td_service(TestSession, cid, uid)
    seen: list[dict] = []

    def respond(payload: dict) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"items": []}), input_tokens=1, output_tokens=1)

    provider.register("extract.capabilities", respond)
    with TestSession() as db:
        report = measure_tech_debt(
            db, LLMClient(provider), runs=2, inventory=str(TD_XLSX), service_id=sid
        )
    assert len(seen) == 2
    for payload in seen:
        blob = json.dumps(payload["rows"])
        assert "Acme" not in blob, "the client's name reached the provider"
        assert "{{CLIENT_NAME}}" not in blob
        assert "[CLIENT] SOC Platform" in blob
        assert len(payload["rows"]) == len(_td_doc()["rows"])
    assert report["input_setup"]["client_name_substituted"] == 1
    assert report["rows_sent"] == len(_td_doc()["rows"])


def test_an_inventory_placeholder_with_no_client_name_is_refused(world) -> None:
    from app.models.client import Client

    c, TestSession, provider = world
    _, cid, uid = _admin(c)
    sid = _td_service(TestSession, cid, uid)
    with TestSession() as db:
        db.get(Client, uuid.UUID(cid)).legal_name = None
        db.commit()
    provider.register("extract.capabilities", lambda p: LLMResponse('{"items": []}'))
    with TestSession() as db, pytest.raises(Refused) as exc:
        measure_tech_debt(db, LLMClient(provider), runs=2, inventory=str(TD_XLSX), service_id=sid)
    assert exc.value.reason == "client_name_missing"
    with TestSession() as db:
        assert _llm_call_count(db) == 0


# --- charged_likely follows the rows, never an assumption -------------------------


def _fail_before_the_provider(monkeypatch, *, which: set[int]) -> None:
    """Make the `which`-th `invoke` calls (1-based) raise before `invoke`
    writes its `llm_calls` row -- the shape of the CSF baseline's SQLite lock
    (comment 5965066136): the batch died inserting its RUNNING row, and no
    provider was ever called."""
    original = LLMClient.invoke
    lock = threading.Lock()
    count = [0]

    def invoke(self, db, **kw):
        with lock:
            count[0] += 1
            n = count[0]
        if n in which:
            raise RuntimeError("database is locked")
        return original(self, db, **kw)

    monkeypatch.setattr(LLMClient, "invoke", invoke)


def test_a_csf_batch_that_never_reached_the_provider_is_not_charged(csf_world, monkeypatch) -> None:
    c, TestSession, provider = csf_world
    provider.register("csf_score", _csf_answer_all([]))
    _fail_before_the_provider(monkeypatch, which={3})
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2)
    assert report["failed_runs"] == [
        {"run": 1, "failure": "batches_failed:1/11", "cause": None, "charged_likely": None}
    ]


def test_a_csf_run_whose_batches_all_failed_at_the_provider_is_charged(csf_world) -> None:
    # #800: a total failure is a `RunFailed`, which carries no `charged_likely`;
    # every batch wrote its row and reached the provider, so it is True.
    c, TestSession, provider = csf_world

    def refuse(payload: dict) -> LLMResponse:
        raise RuntimeError("provider closed the connection")

    provider.register("csf_score", refuse)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2, stop_on_failure=True)
    assert report["failed_runs"][0] == {
        "run": 1,
        "failure": "ai_call_failed",
        "cause": "RuntimeError",
        "charged_likely": True,
    }


def test_a_csf_run_whose_batches_all_failed_before_the_provider_is_not_charged(
    csf_world, monkeypatch
) -> None:
    c, TestSession, provider = csf_world
    provider.register("csf_score", _csf_answer_all([]))
    _fail_before_the_provider(monkeypatch, which=set(range(1, 12)))
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2, stop_on_failure=True)
    assert report["failed_runs"][0]["failure"] == "ai_call_failed"
    assert report["failed_runs"][0]["charged_likely"] is None


def test_a_zt_call_that_never_reached_the_provider_is_not_charged(world, monkeypatch) -> None:
    c, TestSession, provider = world
    _zt(c)
    provider.register("zt_score", _zt_recorder([]))
    _fail_before_the_provider(monkeypatch, which={2})
    with TestSession() as db:
        report = measure_zt(db, LLMClient(provider), framework="cisa", runs=3)
    assert report["failed_runs"] == [
        {"run": 2, "failure": "ai_call_failed", "cause": "RuntimeError", "charged_likely": None}
    ]


TOOLS = ["Falcon Sensor", "Sentinel Hub", "Vault Backup"]


@pytest.fixture()
def attack_world(world):
    from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus

    c, TestSession, provider = world
    h, cid, uid = _admin(c)
    sid = _td_service(TestSession, cid, uid)
    with TestSession() as db:
        cl = CapabilityList(
            service_id=uuid.UUID(sid), version=1, status=CapabilityListStatus.APPROVED
        )
        db.add(cl)
        db.flush()
        for name in TOOLS:
            db.add(CapabilityItem(capability_list_id=cl.id, name=name))
        db.commit()
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    yield c, TestSession, provider


def _cover_every_asked_technique(payload: dict) -> LLMResponse:
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


def test_a_mitre_batch_that_never_reached_the_provider_is_not_charged(
    attack_world, monkeypatch
) -> None:
    # The twin of the csf_score case: the same `batches_failed` branch.
    c, TestSession, provider = attack_world
    provider.register("mitre_map", _cover_every_asked_technique)
    _fail_before_the_provider(monkeypatch, which={2})
    with TestSession() as db:
        report = measure_attack(db, LLMClient(provider), runs=2)
    (failed,) = report["failed_runs"]
    assert failed["run"] == 1
    assert failed["failure"].startswith("batches_failed:1/")
    assert failed["charged_likely"] is None


def test_a_mitre_batch_that_failed_at_the_provider_is_charged(attack_world) -> None:
    c, TestSession, provider = attack_world
    calls = [0]
    lock = threading.Lock()

    def flaky(payload: dict) -> LLMResponse:
        with lock:
            calls[0] += 1
            n = calls[0]
        if n == 2:
            raise RuntimeError("provider closed the connection")
        return _cover_every_asked_technique(payload)

    provider.register("mitre_map", flaky)
    with TestSession() as db:
        report = measure_attack(db, LLMClient(provider), runs=2)
    (failed,) = report["failed_runs"]
    assert failed["failure"].startswith("batches_failed:1/")
    assert failed["charged_likely"] is True


def test_a_mitre_run_whose_batches_all_failed_at_the_provider_is_charged(attack_world) -> None:
    # The twin of the csf_score `RunFailed` case (#800).
    c, TestSession, provider = attack_world

    def refuse(payload: dict) -> LLMResponse:
        raise RuntimeError("provider closed the connection")

    provider.register("mitre_map", refuse)
    with TestSession() as db:
        report = measure_attack(db, LLMClient(provider), runs=2, stop_on_failure=True)
    assert report["failed_runs"][0]["failure"] == "ai_call_failed"
    assert report["failed_runs"][0]["charged_likely"] is True


def _td_world(world) -> tuple[sessionmaker, FixtureProvider, str]:
    c, TestSession, provider = world
    _, cid, uid = _admin(c)
    return TestSession, provider, _td_service(TestSession, cid, uid)


def test_a_failure_that_reached_the_provider_keeps_its_typed_value(world) -> None:
    # The call completed and its response was refused: the row says the
    # provider was reached, so the boundary's own typed value stands -- False
    # here, because a fixture provider bills nothing (`ai_call_boundary`).
    TestSession, provider, sid = _td_world(world)
    provider.register_static("extract.capabilities", LLMResponse('{"items": "nope"}'))
    with TestSession() as db:
        report = measure_tech_debt(
            db, LLMClient(provider), runs=2, inventory=str(TD_XLSX), service_id=sid
        )
    assert [f["charged_likely"] for f in report["failed_runs"]] == [False, False]


def test_an_extraction_that_never_reached_the_provider_is_not_charged(world, monkeypatch) -> None:
    TestSession, provider, sid = _td_world(world)
    provider.register_static("extract.capabilities", LLMResponse('{"items": []}'))
    _fail_before_the_provider(monkeypatch, which={1})
    with TestSession() as db:
        report = measure_tech_debt(
            db, LLMClient(provider), runs=2, inventory=str(TD_XLSX), service_id=sid
        )
    assert report["failed_runs"] == [
        {"run": 1, "failure": "ai_call_failed", "cause": "RuntimeError", "charged_likely": None}
    ]


# --- main: refusals before any provider, --out before any paid call -------------


@pytest.fixture()
def cli(monkeypatch, tmp_path):
    """`from_db` records whether `--out` already existed when the provider was
    built; every measurement is a stub that records its keyword arguments and
    whether `--out` existed when it was reached, then refuses as
    `measure_reached` (or returns `cli.report` when one is set)."""
    from app.ai.llm import LLMClient as _Client
    from app.config import get_settings

    out = tmp_path / "o.json"
    state: dict = {"built": [], "reached": [], "report": None}

    def recording_from_db(cls, db, settings=None):
        state["built"].append(out.exists())
        return _Client(FixtureProvider())

    monkeypatch.setattr(_Client, "from_db", classmethod(recording_from_db))
    monkeypatch.setenv("SHIELD_LLM_MODE", "live")
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setenv("SHIELD_REDACTION_MODE", "strict")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")

    import scripts.measure_ai_consistency as m

    def reached(name: str):
        def stub(db, llm, **kw):
            state["reached"].append((name, kw, out.exists()))
            if state["report"] is not None:
                return state["report"]
            raise Refused("measure_reached", name)

        return stub

    for name in ("measure_zt", "measure_csf", "measure_attack", "measure_tech_debt"):
        monkeypatch.setattr(m, name, reached(name))
    get_settings.cache_clear()
    yield state, out
    get_settings.cache_clear()


def test_main_refuses_a_notes_corpus_flag_with_no_value(cli, capsys) -> None:
    state, out = cli
    with pytest.raises(SystemExit) as exc:
        main(["--job", "zt_score", "--runs", "2", "--out", str(out), "--notes-corpus"])
    assert exc.value.code == 2
    assert "--notes-corpus: expected one argument" in capsys.readouterr().err
    assert state["built"] == []


@pytest.mark.parametrize("job", ["mitre_map", "tech_debt_extract"])
def test_main_refuses_a_notes_corpus_for_a_job_that_reads_no_notes(cli, capsys, job) -> None:
    # Ignoring it would report a corpus run that never used the corpus.
    state, out = cli
    argv = ["--job", job, "--runs", "2", "--out", str(out), "--notes-corpus", str(NOTES)]
    if job == "tech_debt_extract":
        argv += ["--inventory", str(TD_XLSX), "--service-id", "s"]
    assert main(argv) == 2
    assert "REFUSED (notes_corpus_not_applicable)" in capsys.readouterr().err
    assert state["built"] == []
    assert not out.exists()


def test_main_refuses_an_unreadable_notes_corpus_before_building_a_provider(cli, capsys) -> None:
    state, out = cli
    missing = str(out.parent / "missing.json")
    argv = ["--job", "zt_score", "--runs", "2", "--out", str(out), "--notes-corpus", missing]
    assert main(argv) == 2
    assert "REFUSED (notes_corpus_unreadable)" in capsys.readouterr().err
    assert state["built"] == []
    assert not out.exists()


@pytest.mark.parametrize(
    ("job", "measure"), [("zt_score", "measure_zt"), ("csf_score", "measure_csf")]
)
def test_main_passes_the_loaded_corpus_to_the_measure(cli, capsys, job, measure) -> None:
    state, out = cli
    argv = ["--job", job, "--runs", "2", "--out", str(out), "--notes-corpus", str(NOTES)]
    assert main(argv) == 2
    ((name, kw, _),) = state["reached"]
    assert name == measure
    assert kw["notes_corpus"].corpus == "measure-notes-v1"


def test_main_passes_no_corpus_when_none_was_given(cli) -> None:
    state, out = cli
    main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    ((_, kw, _),) = state["reached"]
    assert kw["notes_corpus"] is None


def test_main_opens_the_report_before_building_a_provider(cli) -> None:
    # #806 comment 5965052688: a bad --out must fail BEFORE money is spent.
    state, out = cli
    main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    assert state["built"] == [True]
    assert [r[2] for r in state["reached"]] == [True]


def test_main_refuses_an_unwritable_out_before_building_a_provider(cli, capsys) -> None:
    state, out = cli
    bad = out.parent / "no-such-dir" / "o.json"
    assert main(["--job", "zt_score", "--runs", "2", "--out", str(bad)]) == 2
    assert "REFUSED (out_unwritable)" in capsys.readouterr().err
    assert state["built"] == []
    assert state["reached"] == []


def test_main_never_overwrites_an_earlier_report(cli, capsys) -> None:
    # An earlier report is a paid run's only record.
    state, out = cli
    out.write_text('{"earlier": "paid run"}', encoding="utf-8")
    assert main(["--job", "zt_score", "--runs", "2", "--out", str(out)]) == 2
    assert "REFUSED (out_exists)" in capsys.readouterr().err
    assert out.read_text(encoding="utf-8") == '{"earlier": "paid run"}'
    assert state["built"] == []


def test_a_refused_measurement_leaves_no_empty_report(cli, capsys) -> None:
    state, out = cli
    assert main(["--job", "zt_score", "--runs", "2", "--out", str(out)]) == 2
    assert "REFUSED (measure_reached)" in capsys.readouterr().err
    assert not out.exists()


def test_main_writes_the_report_into_the_file_it_opened(cli) -> None:
    state, out = cli
    state["report"] = summarize("zt_score", [])
    code = main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["job"] == "zt_score"
    assert written["cost_cap"]["service_cap_usd"] == 3
    assert code == 1  # no run succeeded


# --- the per-service cost cap: a projected dollar guard (#952 review F1) -----------


def test_the_cost_caps_are_section_2s_table_and_total_the_approved_25() -> None:
    # Section 2's table, row by row; the total approved in #736 item 8: "$25".
    assert COST_CAPS_USD == {
        "tech_debt_extract": 3,
        "csf_score": 8,
        "zt_score": 3,
        "mitre_map": 6,
        "risk_synthesize": 5,
    }
    assert sum(COST_CAPS_USD.values()) == 25


def test_count_calls_reads_the_retries_from_the_real_anthropic_client(monkeypatch) -> None:
    """#952 round 4, F2: through `count_calls` on a real `AnthropicProvider`
    whose client does not exist yet (it is built lazily). The client is built
    then, with no network: any attempt to open a socket fails this test."""
    import socket
    from pathlib import Path as _Path

    import anthropic
    from scripts.measure_ai_consistency import _ReportFile

    from app.ai.llm import AnthropicProvider, LLMClient

    def no_network(*a, **kw):
        raise AssertionError("building the client opened a connection")

    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    provider = AnthropicProvider(model="claude-opus-5", api_key="test-not-a-key")
    assert provider._client is None, "precondition: the client is built lazily"
    rf = _ReportFile(
        _Path("unused.json"),
        "zt_score",
        1.5,
        {"provider": "anthropic", "model": "claude-opus-5", "usd_per_mtok": OPUS5},
        {"query": {}, "sqlite_timeout": None},
    )
    rf.count_calls(LLMClient(provider))
    assert rf.sdk_retries == {
        "provider": "anthropic",
        "max_retries": anthropic.DEFAULT_MAX_RETRIES,
        "source": "client",
    }


def test_sdk_retries_reports_an_override_on_the_client_and_none_without_an_sdk() -> None:
    import anthropic
    from scripts.measure_ai_consistency import sdk_retries

    from app.ai.llm import AnthropicProvider

    provider = AnthropicProvider(model="claude-opus-5", api_key="test-not-a-key")
    provider._client = anthropic.Anthropic(api_key="test-not-a-key", max_retries=7)
    assert sdk_retries(provider)["max_retries"] == 7
    assert sdk_retries(FixtureProvider()) == {
        "provider": "fixture",
        "max_retries": None,
        "source": "no_sdk",
    }


def test_the_price_table_holds_only_cited_prices() -> None:
    # The Claude API skill's model table, cached 2026-10-06: claude-opus-5
    # "$5.00 | $25.00", claude-sonnet-5 "$2.00 | $10.00" (input | output per 1M).
    from scripts.measure_ai_consistency import PRICES_USD_PER_MTOK

    assert PRICES_USD_PER_MTOK == {
        ("anthropic", "claude-opus-5"): {"input": 5, "output": 25},
        ("anthropic", "claude-sonnet-5"): {"input": 2, "output": 10},
    }


def test_main_refuses_a_model_with_no_known_price(cli, monkeypatch, capsys) -> None:
    from app.config import get_settings

    state, out = cli
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-imaginary-9")
    get_settings.cache_clear()
    assert main(["--job", "zt_score", "--runs", "2", "--out", str(out)]) == 2
    assert "REFUSED (price_unknown_for_model)" in capsys.readouterr().err
    assert state["built"] == []
    assert not out.exists()


def test_the_report_records_the_model_and_price_it_used(cli, monkeypatch) -> None:
    from app.config import get_settings

    state, out = cli
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-sonnet-5")
    get_settings.cache_clear()
    state["report"] = summarize("zt_score", [])
    main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["cost_cap"]["price_basis"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "usd_per_mtok": {"input": 2, "output": 10},
    }


#: claude-opus-5's list price, USD per million tokens, from the Claude API
#: skill's model table (cached 2026-10-06), as section 2 of #806 comment
#: 5983938383 quotes it ("$5 / $25 per MTok").
OPUS5 = {"input": 5, "output": 25}


def _usd_run(input_tokens, output_tokens, calls: int = 1, started: int | None = None):
    from scripts.measure_ai_consistency import RunRecord

    started = calls if started is None else started
    return RunRecord(True, {}, None, input_tokens, output_tokens, calls=calls, started=started)


def test_the_guard_refuses_to_start_a_run_the_largest_so_far_would_take_over_the_cap() -> None:
    from scripts.measure_ai_consistency import run_loop

    # 40,000 output tokens at $25 per million is $1.00 a run. Before run 2:
    # $1 spent + $1 (the largest run) = $2 <= $2.50. Before run 3: $2 + $1 =
    # $3 > $2.50, so run 3 is not started.
    started: list[int] = []

    def one(n: int):
        started.append(n)
        return _usd_run(0, 40_000)

    records = run_loop(3, one, max_output_tokens=None, max_usd=2.5, price=OPUS5)
    assert started == [1, 2]
    assert [r.failure for r in records] == [None, None, "stopped_budget"]


def test_the_guard_counts_input_tokens_too() -> None:
    from scripts.measure_ai_consistency import run_loop

    # 200,000 input tokens at $5 per million is $1.00, with no output at all:
    # a guard on output alone would start all three.
    started: list[int] = []

    def one(n: int):
        started.append(n)
        return _usd_run(200_000, 0)

    run_loop(3, one, max_output_tokens=None, max_usd=2.5, price=OPUS5)
    assert started == [1, 2]


def test_the_first_run_always_starts_and_is_reported_unbounded() -> None:
    from scripts.measure_ai_consistency import run_loop

    records = run_loop(
        2, lambda n: _usd_run(0, 400_000), max_output_tokens=None, max_usd=1.5, price=OPUS5
    )
    assert [r.failure for r in records] == [None, "stopped_budget"]
    s = summarize("zt_score", records, context=ZT_SCOPE_FOR_SUMMARY, max_usd=1.5, price=OPUS5)
    assert s["budget_usd"] == {
        "max_usd": 1.5,
        "spent_usd": 10.0,
        "per_run_usd": [10.0, 0.0],
        "complete": True,
        "first_run_bounded": False,
        "overrun": True,
    }


def test_unknown_spend_stops_further_runs_under_the_dollar_guard() -> None:
    from scripts.measure_ai_consistency import run_loop

    records = run_loop(
        2,
        lambda n: _usd_run(5, 100) if n > 1 else _usd_run(5, None),
        max_output_tokens=None,
        max_usd=100.0,
        price=OPUS5,
    )
    assert [r.failure for r in records] == [None, "stopped_unknown_spend"]


def test_a_run_that_started_no_call_spent_nothing_and_stops_nothing() -> None:
    # A failure before `invoke` was ever entered: no call, so $0, KNOWN.
    from scripts.measure_ai_consistency import RunRecord, run_loop

    def one(n: int):
        if n == 1:
            return RunRecord(
                False,
                None,
                "ai_call_failed",
                None,
                None,
                "RuntimeError",
                None,
                False,
                calls=0,
                started=0,
            )
        return _usd_run(1, 1)

    records = run_loop(2, one, max_output_tokens=None, max_usd=1.0, price=OPUS5)
    assert [r.failure for r in records] == ["ai_call_failed", None]
    s = summarize("zt_score", records, context=ZT_SCOPE_FOR_SUMMARY, max_usd=1.0, price=OPUS5)
    assert s["budget_usd"]["per_run_usd"][0] == 0.0
    assert s["budget_usd"]["complete"] is True
    assert s["tokens"]["complete"] is True


def test_a_started_call_with_no_row_is_unknown_spend_and_stops_later_runs() -> None:
    # #952 narrow review 1: a call was started and wrote no row -- it may have
    # billed (a deadline in flight, a failed commit). Unknown, never $0.
    from scripts.measure_ai_consistency import RunRecord, run_loop

    def one(n: int):
        return RunRecord(
            False,
            None,
            "ai_call_failed",
            None,
            None,
            "RuntimeError",
            None,
            False,
            calls=0,
            started=1,
        )

    records = run_loop(2, one, max_output_tokens=None, max_usd=100.0, price=OPUS5)
    assert [r.failure for r in records] == ["ai_call_failed", "stopped_unknown_spend"]
    s = summarize("zt_score", records, context=ZT_SCOPE_FOR_SUMMARY, max_usd=100.0, price=OPUS5)
    assert s["budget_usd"]["per_run_usd"][0] is None
    assert s["budget_usd"]["complete"] is False
    assert s["tokens"]["complete"] is False


def test_fewer_rows_than_calls_started_is_unknown_even_with_tokens() -> None:
    # Ten batches' rows, eleven calls started: the rows that exist carry
    # tokens, and the missing one is still spend nobody can see.
    from scripts.measure_ai_consistency import run_loop

    records = run_loop(
        2,
        lambda n: _usd_run(10, 10, calls=10, started=11),
        max_output_tokens=None,
        max_usd=100.0,
        price=OPUS5,
    )
    assert records[1].failure == "stopped_unknown_spend"


def test_runs_never_started_are_known_not_to_have_charged() -> None:
    # #952 review F4: a `stopped_*` run made no call, so False, not None.
    from scripts.measure_ai_consistency import run_loop

    records = run_loop(
        3, lambda n: _usd_run(0, 400_000), max_output_tokens=None, max_usd=1.0, price=OPUS5
    )
    s = summarize("zt_score", records, context=ZT_SCOPE_FOR_SUMMARY)
    assert [(f["failure"], f["charged_likely"]) for f in s["failed_runs"]] == [
        ("stopped_budget", False),
        ("stopped_budget", False),
    ]


def test_the_table_prints_charged_likely_for_a_failed_run(capsys) -> None:
    from scripts.measure_ai_consistency import RunRecord, _print_table

    records = [RunRecord(False, None, "ai_call_failed", 1, 1, "RuntimeError", True)]
    _print_table(summarize("zt_score", records, context=ZT_SCOPE_FOR_SUMMARY))
    assert "run 1 FAILED: ai_call_failed (charged_likely: True)" in capsys.readouterr().out


def test_main_passes_each_job_half_its_service_cap(cli) -> None:
    state, out = cli
    for job, extra, side in [
        ("zt_score", [], 1.5),
        ("csf_score", [], 4.0),
        ("mitre_map", [], 3.0),
        ("tech_debt_extract", ["--inventory", "x.xlsx", "--service-id", "s"], 1.5),
    ]:
        state["reached"].clear()
        main(["--job", job, "--runs", "2", "--out", str(out), *extra])
        ((_, kw, _),) = state["reached"]
        assert kw["max_usd"] == side, job


def test_main_keeps_max_output_tokens_optional_and_as_given(cli) -> None:
    state, out = cli
    main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    assert state["reached"][-1][1]["max_output_tokens"] is None
    out2 = out.parent / "o2.json"
    main(["--job", "zt_score", "--runs", "2", "--out", str(out2), "--max-output-tokens", "9"])
    assert state["reached"][-1][1]["max_output_tokens"] == 9


@pytest.mark.parametrize(
    ("url", "query", "timeout"),
    [
        pytest.param("sqlite:///{db}?timeout=900", {"timeout": "900"}, "900", id="with-timeout"),
        pytest.param("sqlite:///{db}", {}, None, id="without"),
    ],
)
def test_the_report_records_the_database_url_parameters_only(
    cli, monkeypatch, capsys, url, query, timeout
) -> None:
    # The advisor's ruling (#736 comment 6068587667): the live run sets
    # ?timeout=900 by hand, so the report records exactly that parameter.
    from app.config import get_settings

    state, out = cli
    monkeypatch.setenv("DATABASE_URL", url.format(db=out.parent / "x.db"))
    get_settings.cache_clear()
    state["report"] = summarize("zt_score", [])
    main(["--job", "zt_score", "--runs", "2", "--out", str(out)])
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["database_url"] == {"query": query, "sqlite_timeout": timeout}
    assert "x.db" not in json.dumps(written["database_url"]), "the path is not a parameter"
    printed = capsys.readouterr().out
    if timeout is None:
        assert "DATABASE_URL sets no ?timeout=" in printed


from scripts.measure_ai_consistency import ZtScope  # noqa: E402

ZT_SCOPE_FOR_SUMMARY = ZtScope(max_stage=4, codes=frozenset())


# --- main, end to end on the real path: the report survives (#952 review F2) ------


@pytest.fixture()
def main_world(world, monkeypatch, tmp_path):
    """`main` against the world's database with a fixture provider: settings
    say live + strict + SQLite, `SessionLocal` is the world's, and `from_db`
    returns the world's provider. Yields what the tests need."""
    from app.ai.llm import LLMClient as _Client
    from app.config import get_settings

    c, TestSession, provider = world
    _zt(c)
    monkeypatch.setenv("SHIELD_LLM_MODE", "live")
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setenv("SHIELD_REDACTION_MODE", "strict")
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-opus-5")
    get_settings.cache_clear()
    monkeypatch.setattr("app.db.session.SessionLocal", TestSession)
    monkeypatch.setattr(_Client, "from_db", classmethod(lambda cls, db, s=None: _Client(provider)))
    yield TestSession, provider, tmp_path / "report.json"
    get_settings.cache_clear()


def _zt_tokens(output_tokens: int, calls: list[int], on_call=None):
    def respond(payload: dict) -> LLMResponse:
        calls.append(1)
        if on_call is not None:
            on_call(len(calls))
        rows = [{"code": code, "current": 1, "target": 2} for code in payload["capabilities"]]
        return LLMResponse(
            json.dumps({"capabilities": rows}), input_tokens=10, output_tokens=output_tokens
        )

    return respond


ZT_ARGV = ["--job", "zt_score", "--framework", "cisa"]


def test_main_does_not_start_a_run_the_guard_projects_over_the_side_cap(main_world) -> None:
    # zt_score's side cap is $1.50. Run 1 spends just over $1 (40,000 output
    # tokens plus 10 input), so run 2 would take the side past it: not started.
    TestSession, provider, out = main_world
    calls: list[int] = []
    provider.register("zt_score", _zt_tokens(40_000, calls))
    code = main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert calls == [1]
    assert report["failed_runs"] == [
        {"run": 2, "failure": "stopped_budget", "cause": None, "charged_likely": False}
    ]
    assert report["budget_usd"]["max_usd"] == 1.5
    assert code == 1


def test_main_counts_a_run_that_started_no_call_as_no_spend(main_world, monkeypatch) -> None:
    # The failure is raised before `invoke` is entered, so no call started.
    import app.ai.engine as engine

    TestSession, provider, out = main_world
    provider.register("zt_score", _zt_tokens(5, []))
    original, seen = engine.run_job, []

    def first_fails(*a, **kw):
        seen.append(1)
        if len(seen) == 1:
            raise RuntimeError("failed before any provider call")
        return original(*a, **kw)

    monkeypatch.setattr(engine, "run_job", first_fails)
    code = main([*ZT_ARGV, "--runs", "3", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [f["failure"] for f in report["failed_runs"]] == ["ai_call_failed"]
    assert report["runs_ok"] == 2
    assert report["budget_usd"]["per_run_usd"][0] == 0.0
    assert code == 1


def test_main_stops_after_a_started_call_left_no_row(main_world, monkeypatch) -> None:
    # Inside `invoke`, before its row lands (the SQLite-lock shape): the call
    # was started, so the spend is unknown and no later run starts.
    TestSession, provider, out = main_world
    provider.register("zt_score", _zt_tokens(5, []))
    _fail_before_the_provider(monkeypatch, which={1})
    code = main([*ZT_ARGV, "--runs", "3", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [f["failure"] for f in report["failed_runs"]] == [
        "ai_call_failed",
        "stopped_unknown_spend",
        "stopped_unknown_spend",
    ]
    assert report["budget_usd"]["complete"] is False
    assert report["cost_cap"]["estimate_complete"] is False
    assert code == 1


def test_the_real_run_deadline_with_a_call_in_flight_is_unknown_spend(
    csf_world, monkeypatch
) -> None:
    """Scenario (a) on the REAL path: `run_batches`' thread pool and its
    deadline, with RUN_DEADLINE shortened and one batch's provider call held
    past it. The held call has entered `invoke` and its row is not committed
    when the run is counted.

    NOTE what this covers and what it does not: `measure_csf` ALSO marks a
    deadline run incomplete on its own (`RUN_DEADLINE_EXCEEDED`), so this test
    would pass with the `calls < started` rule deleted. The rule itself is
    pinned by the next test."""
    import time
    from datetime import timedelta

    from app.ai.runs import RUN_DEADLINE_EXCEEDED
    from app.models.llm_call import LLMCall

    c, TestSession, provider = csf_world
    release = threading.Event()
    answer = _csf_answer_all([])
    held: list[int] = []
    lock = threading.Lock()

    def respond(payload: dict) -> LLMResponse:
        with lock:
            first = not held
            held.append(1)
        if first:
            release.wait(10)
        return answer(payload)

    provider.register("csf_score", respond)
    monkeypatch.setattr("app.ai.runs.RUN_DEADLINE", timedelta(seconds=1))
    try:
        with TestSession() as db:
            report = measure_csf(db, LLMClient(provider), runs=2, max_usd=100.0, price=OPUS5)
    finally:
        release.set()
    assert report["failed_runs"][0]["failure"] == RUN_DEADLINE_EXCEEDED
    assert report["failed_runs"][1]["failure"] == "stopped_after_deadline"
    assert report["budget_usd"]["per_run_usd"][0] is None
    assert report["budget_usd"]["complete"] is False
    assert report["budget"]["complete"] is False
    # Let the straggler land its row before the database goes away.
    deadline = time.monotonic() + 10
    with TestSession() as db:
        while time.monotonic() < deadline:
            db.expire_all()
            if db.query(LLMCall).filter(LLMCall.status != "running").count() >= len(held):
                break
            time.sleep(0.05)


def test_a_started_call_whose_row_never_landed_is_unknown_even_in_a_successful_run(
    csf_world, monkeypatch
) -> None:
    """The `calls < started` rule on its own. This FAKES `run_batches`: it runs
    the real batches (every row committed, tokens complete), then enters
    `invoke` once more in a session that is never committed -- the in-flight
    straggler's shape -- and returns success. Nothing else marks the run
    incomplete, so only the rule can make its spend unknown. It does not drive
    the deadline path; the test above does."""
    from sqlalchemy.orm import Session as _Session

    import app.ai.batching as batching
    from app.ai.engine import run_job

    c, TestSession, provider = csf_world
    provider.register("csf_score", _csf_answer_all([]))
    real = batching.run_batches

    def with_a_lost_row(db, llm, job_name, batch_inputs, **kw):
        result = real(db, llm, job_name, batch_inputs, **kw)
        lost = _Session(bind=db.get_bind())
        run_job(
            lost,
            llm,
            job_name,
            inputs=batch_inputs[0],
            requested_by=kw["requested_by"],
            service_id=kw["service_id"],
            client_id=kw["client_id"],
            client_org_name=kw["client_org_name"],
            name_hints=kw["name_hints"],
        )
        lost.close()
        return result

    monkeypatch.setattr("app.ai.batching.run_batches", with_a_lost_row)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2, max_usd=100.0, price=OPUS5)
    assert report["runs"][0]["ok"] is True
    assert report["runs"][0]["tokens_complete"] is True, "precondition: only the rule"
    assert report["budget_usd"]["per_run_usd"][0] is None
    assert report["budget_usd"]["complete"] is False
    assert report["budget"]["complete"] is False
    assert report["failed_runs"] == [
        {"run": 2, "failure": "stopped_unknown_spend", "cause": None, "charged_likely": False}
    ]


def test_a_batch_whose_commit_failed_after_the_call_is_unknown_spend(
    csf_world, monkeypatch
) -> None:
    # Scenario (b): the provider call returned (and billed), then the
    # worker's `session.commit()` failed, so its row never landed.
    from sqlalchemy.orm import Session as _Session

    c, TestSession, provider = csf_world
    provider.register("csf_score", _csf_answer_all([]))
    lock, chosen = threading.Lock(), []

    class FailingCommit(_Session):
        def commit(self):
            with lock:
                if not chosen:
                    chosen.append(id(self))
                mine = chosen[0] == id(self)
            if mine:
                raise RuntimeError("commit failed")
            return super().commit()

    monkeypatch.setattr("app.ai.batching.Session", FailingCommit)
    with TestSession() as db:
        report = measure_csf(db, LLMClient(provider), runs=2, max_usd=100.0, price=OPUS5)
    assert report["failed_runs"][0]["failure"] == "batches_failed:1/11"
    assert report["failed_runs"][1]["failure"] == "stopped_unknown_spend"
    assert report["budget_usd"]["complete"] is False
    # #952 round 3, finding 2: the output-token block says the same.
    assert report["budget"]["complete"] is False


def _dump_failing(monkeypatch, statuses: dict[str, str]):
    """`_dump_json` that writes half a document and raises, for the report
    statuses named, with the message given; any other status is written."""
    import scripts.measure_ai_consistency as m

    real = m._dump_json

    def dump(obj, fh):
        status = obj.get("status")
        if status in statuses:
            fh.write('{"job": "zt_score", "status": ')
            raise RuntimeError(statuses[status])
        real(obj, fh)

    monkeypatch.setattr(m, "_dump_json", dump)


def test_a_failed_final_write_leaves_the_last_whole_report(main_world, monkeypatch) -> None:
    # #952 narrow review 2: a dump that dies midway never reaches `--out`,
    # and when the abort record cannot be written either, the last
    # in-progress report stays -- whole -- and the ORIGINAL error is raised.
    TestSession, provider, out = main_world
    provider.register("zt_score", _zt_tokens(5, []))
    _dump_failing(monkeypatch, {"complete": "disk full", "aborted": "disk full again"})
    with pytest.raises(RuntimeError, match="^disk full$"):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "in_progress"
    assert [r["run"] for r in report["runs"]] == [1, 2]
    assert [p.name for p in out.parent.iterdir() if p.name.endswith(".tmp")] == []


def test_a_failed_final_write_is_recorded_as_an_abort(main_world, monkeypatch) -> None:
    # The final write is inside the handler: its failure is an abort like
    # any other, recorded with every completed run.
    TestSession, provider, out = main_world
    provider.register("zt_score", _zt_tokens(5, []))
    _dump_failing(monkeypatch, {"complete": "disk full"})
    with pytest.raises(RuntimeError, match="^disk full$"):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "aborted"
    assert report["aborted"]["exception"] == "RuntimeError"
    assert [r["run"] for r in report["runs"]] == [1, 2]


def test_main_writes_each_completed_run_before_the_next_starts(main_world) -> None:
    TestSession, provider, out = main_world
    seen: list[dict] = []

    def look(n: int) -> None:
        if n == 2:
            seen.append(json.loads(out.read_text(encoding="utf-8")))

    provider.register("zt_score", _zt_tokens(5, [], on_call=look))
    main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    (during,) = seen
    assert during["status"] == "in_progress"
    assert [r["run"] for r in during["runs"]] == [1]
    assert during["runs"][0]["ok"] is True


def test_an_interrupt_after_a_paid_run_keeps_that_run(main_world) -> None:
    TestSession, provider, out = main_world

    def stop(n: int) -> None:
        if n == 2:
            raise KeyboardInterrupt

    provider.register("zt_score", _zt_tokens(5, [], on_call=stop))
    with pytest.raises(KeyboardInterrupt):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "aborted"
    assert report["aborted"]["exception"] == "KeyboardInterrupt"
    # #952 round 4, F1: queued batches can still start, and bill, after an
    # interrupt, so the count here is a lower bound, and the report says so.
    bound = report["aborted"]["invoke_calls_started_is_a_lower_bound"]
    assert "lower bound" in bound
    assert "queued batches can still start" in bound
    assert [r["run"] for r in report["runs"]] == [1]
    assert report["runs"][0]["output_tokens"] == 5
    assert report["invoke_calls_started"] == 2


def test_an_interrupt_before_any_call_leaves_no_file(main_world, monkeypatch) -> None:
    TestSession, provider, out = main_world
    provider.register("zt_score", _zt_tokens(5, []))

    def interrupted(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr("app.routes.zt._zt_ai_request_for", interrupted)
    with pytest.raises(KeyboardInterrupt):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    assert not out.exists()


def test_a_crash_inside_the_first_call_keeps_a_report(main_world) -> None:
    # The call was started, so it may have billed: the file is kept, and says so.
    TestSession, provider, out = main_world

    def boom(n: int) -> None:
        raise KeyboardInterrupt

    provider.register("zt_score", _zt_tokens(5, [], on_call=boom))
    with pytest.raises(KeyboardInterrupt):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "aborted"
    assert report["runs"] == []
    assert report["invoke_calls_started"] == 1
    # #952 round 3, finding 1: a call was started and no run completed, so
    # the spend is NOT "$0, complete".
    assert report["spent_usd"] == 0.0
    assert report["spent_usd_complete"] is False
    assert report["price_basis"]["model"] == "claude-opus-5"
    assert report["sdk_retries"]["provider"] == "fixture"


def test_an_interrupt_mid_run_after_a_completed_run_is_not_complete(main_world) -> None:
    # Run 1 completed; run 2 started a call and was interrupted inside it.
    TestSession, provider, out = main_world

    def stop(n: int) -> None:
        if n == 2:
            raise KeyboardInterrupt

    provider.register("zt_score", _zt_tokens(5, [], on_call=stop))
    with pytest.raises(KeyboardInterrupt):
        main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [r["run"] for r in report["runs"]] == [1]
    assert report["spent_usd_complete"] is False


def test_an_in_progress_report_between_runs_is_complete(main_world) -> None:
    # Between runs every started call belongs to a completed run.
    TestSession, provider, out = main_world
    seen: list[dict] = []

    def look(n: int) -> None:
        if n == 2:
            seen.append(json.loads(out.read_text(encoding="utf-8")))

    provider.register("zt_score", _zt_tokens(5, [], on_call=look))
    main([*ZT_ARGV, "--runs", "2", "--out", str(out)])
    (during,) = seen
    assert during["spent_usd_complete"] is True
    assert during["price_basis"]["usd_per_mtok"] == {"input": 5, "output": 25}


def _main_env(monkeypatch, TestSession, provider) -> None:
    """`main` against a world's database and provider (see `main_world`)."""
    from app.ai.llm import LLMClient as _Client
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_LLM_MODE", "live")
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setenv("SHIELD_REDACTION_MODE", "strict")
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-opus-5")
    get_settings.cache_clear()
    monkeypatch.setattr("app.db.session.SessionLocal", TestSession)
    monkeypatch.setattr(_Client, "from_db", classmethod(lambda cls, db, s=None: _Client(provider)))


def test_a_batched_job_refused_in_setup_leaves_no_file(cli, capsys) -> None:
    # A typed refusal is raised in a measure's setup, before any batch is
    # queued, so nothing can bill: the reserved file goes, batched or not.
    state, out = cli
    assert main(["--job", "csf_score", "--runs", "2", "--out", str(out)]) == 2
    assert "REFUSED (measure_reached)" in capsys.readouterr().err
    assert state["built"] == [True]
    assert not out.exists()


def test_a_batched_job_interrupted_before_the_provider_exists_leaves_no_file(
    cli, monkeypatch
) -> None:
    # No provider was built, so nothing can have been queued or billed.
    from app.ai.llm import LLMClient as _Client

    state, out = cli

    def interrupted(cls, db, settings=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(_Client, "from_db", classmethod(interrupted))
    with pytest.raises(KeyboardInterrupt):
        main(["--job", "mitre_map", "--runs", "2", "--out", str(out)])
    assert not out.exists()


def test_a_batched_interrupt_before_any_invoke_keeps_the_report(
    csf_world, monkeypatch, tmp_path
) -> None:
    """#952 round 5: Ctrl-C after csf_score's batches are submitted and before
    any worker has entered `invoke` (workers do session and `run_job` setup
    first). Zero calls started, yet the queued batches can still bill, so the
    report is KEPT, aborted, with the lower-bound note -- never unlinked."""
    from app.config import get_settings

    c, TestSession, provider = csf_world
    provider.register("csf_score", _csf_answer_all([]))
    _main_env(monkeypatch, TestSession, provider)

    def interrupted(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr("app.ai.batching.run_batches", interrupted)
    out = tmp_path / "csf.json"
    try:
        with pytest.raises(KeyboardInterrupt):
            main(["--job", "csf_score", "--runs", "2", "--out", str(out)])
    finally:
        get_settings.cache_clear()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["status"] == "aborted"
    assert report["invoke_calls_started"] == 0
    assert report["spent_usd_complete"] is False
    assert "lower bound" in report["aborted"]["invoke_calls_started_is_a_lower_bound"]


# --- the ATT&CK probe, compared (#736 comment 6068587667) ---------------------------


def test_main_compares_two_mitre_map_probe_runs_of_the_same_batches(
    attack_world, monkeypatch, tmp_path
) -> None:
    from app.ai.llm import LLMClient as _Client
    from app.config import get_settings

    c, TestSession, provider = attack_world
    asked: list[list[str]] = []

    def respond(payload: dict) -> LLMResponse:
        asked.append(list(payload["technique_codes"]))
        return _cover_every_asked_technique(payload)

    provider.register("mitre_map", respond)
    monkeypatch.setenv("SHIELD_LLM_MODE", "live")
    monkeypatch.setenv("SHIELD_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    monkeypatch.setenv("SHIELD_REDACTION_MODE", "strict")
    monkeypatch.setenv("SHIELD_LLM_MODEL", "claude-opus-5")
    get_settings.cache_clear()
    monkeypatch.setattr("app.db.session.SessionLocal", TestSession)
    monkeypatch.setattr(_Client, "from_db", classmethod(lambda cls, db, s=None: _Client(provider)))
    out = tmp_path / "probe.json"
    try:
        code = main(
            ["--job", "mitre_map", "--runs", "2", "--probe-batches", "2", "--out", str(out)]
        )
    finally:
        get_settings.cache_clear()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert report["probe"]["batches"] == 2
    # Both runs asked for exactly the same techniques.
    half = len(asked) // 2
    assert half == 2
    assert sorted(sum(asked[:half], [])) == sorted(sum(asked[half:], []))
    (pair,) = report["pairs"]
    sent = report["techniques_sent"]
    assert pair["rows"]["in_both"] == sent
    assert pair["fields"]["status"]["equal"] == sent
    assert pair["fields"]["reason_code"]["compared"] == sent
    assert pair["computed_status"]["equal"] == sent
    assert report["budget_usd"]["max_usd"] == 3.0


def test_main_still_refuses_a_csf_probe_of_two_runs(cli, capsys) -> None:
    state, out = cli
    argv = ["--job", "csf_score", "--runs", "2", "--probe-batches", "1", "--out", str(out)]
    assert main(argv) == 2
    assert "REFUSED (probe_runs_not_one)" in capsys.readouterr().err
