"""zt_score under the approved prompt (#806): the payload, the parser, the fixture.

- `capability_details` (A2, build requirement 1) reaches the model, after
  redaction, equal to the committed source extraction, for one CISA and one DoD
  assessment with a client `legal_name` set (requirement 3), through the run
  and through `/ai/preview`. Expected values are built from
  `reference-docs/cisa/cisa_ztmm_v2_rows.json` and
  `reference-docs/dod/dod_zt_2025_rows.json`, never from the catalog module.
- Every DoD activity id starts with its capability's DoD number (requirement 2).
- A stray `target` is counted as `unknown_field` and never applied (C2, ruling
  (a) in #736 comment 5963632707).
- The runtime fixture, written from the prompt, answers through the real run:
  rows with notes applied, blank and placeholder notes left alone (A5), DoD
  stages within each capability's own levels (C4), nothing dropped.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.zt_assessment import ZtAnswer
from tests._ai_runs import zt_run_ai
from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

_HERE = Path(__file__).resolve()
_CISA = find_zt_source(_HERE, "cisa") or Path("/nonexistent/reference-docs/cisa")
_DOD = find_zt_source(_HERE, "dod") or Path("/nonexistent/reference-docs/dod")
_LEGAL_NAME = "Atlas Federal Systems"


def _read(path: Path) -> dict:
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the extraction is the catalog's spec.")
    return json.loads(path.read_text(encoding="utf-8"))


def _activity_key(activity_id: str) -> tuple[int, ...]:
    return tuple(int(x) for x in activity_id.split("."))


def _expected_cisa() -> list[dict]:
    """In CISA's order: each row's pillar and name, and no activities."""
    return [
        {"pillar": r["pillar"], "name": r["name"]}
        for r in _read(_CISA / "cisa_ztmm_v2_rows.json")["rows"]
    ]


def _expected_dod() -> dict[str, dict]:
    """By DoD capability number: pillar, name, and the activities under that
    number, sorted by id, each description followed by its outcomes and end
    state as the 2025 roadmap states them."""
    src = _read(_DOD / "dod_zt_2025_rows.json")
    out: dict[str, dict] = {}
    for cap in src["capabilities"]:
        acts = [a for a in src["activities"] if a["id"].startswith(cap["id"] + ".")]
        acts.sort(key=lambda a: _activity_key(a["id"]))
        rendered = []
        for a in acts:
            text = a["description"]
            if a["outcomes"]:
                text += " Outcomes: " + a["outcomes"]
            if a["end_state"]:
                text += " End state: " + a["end_state"]
            rendered.append(
                {"id": a["id"], "name": a["name"], "level": a["level"], "description": text}
            )
        out[cap["id"]] = {"pillar": cap["pillar"], "name": cap["name"], "activities": rendered}
    return out


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str = ""
    answers: list[dict] = field(default_factory=list)

    def service(self, kind: str) -> None:
        svc = self.c.post("/zt/services", headers=self.h, json={"kind": kind, "title": "ZT"})
        assert svc.status_code in (200, 201), svc.text
        self.svc_id = svc.json()["id"]
        a = self.c.post(f"/zt/services/{self.svc_id}/assessments", headers=self.h)
        assert a.status_code in (200, 201), a.text
        self.answers = a.json()["answers"]

    def patch(self, i: int, **fields: Any) -> None:
        r = self.c.patch(f"/zt/answers/{self.answers[i]['id']}", headers=self.h, json=fields)
        assert r.status_code == 200, r.text

    def capture(self, response: dict) -> list[dict]:
        """Register a provider that records the payload it is sent."""
        seen: list[dict] = []

        def respond(payload: dict[str, Any]) -> LLMResponse:
            seen.append(payload)
            return LLMResponse(json.dumps(response))

        self.provider.register("zt_score", respond)
        return seen

    def row(self, code: str) -> ZtAnswer:
        with self.sessions() as s:
            return s.execute(select(ZtAnswer).where(ZtAnswer.capability_code == code)).scalar_one()


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-zt-v2.db'}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    from app.db.session import get_db
    from app.main import create_app
    from app.routes.zt import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
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
            json={"legal_name": _LEGAL_NAME},
        ).json()["id"]
        h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
        yield World(c, sessions, provider, h)


# --- the payload ------------------------------------------------------------


def _sent_details(world: World) -> dict:
    seen = world.capture({"capabilities": []})
    zt_run_ai(world.c, world.svc_id, world.h)
    assert len(seen) == 1, "the provider was not called exactly once"
    return seen[0]["capability_details"]


def test_cisa_capability_details_reach_the_model_as_cisa_states_them(world) -> None:
    world.service("zero_trust_cisa")
    sent = _sent_details(world)
    codes = sorted(a["capability_code"] for a in world.answers)
    assert sorted(sent) == codes
    # Order-independent: CISA's rows, as the source lists them.
    assert sorted(sent.values(), key=json.dumps) == sorted(_expected_cisa(), key=json.dumps)
    assert all("activities" not in entry for entry in sent.values())


def test_dod_capability_details_carry_the_roadmap_activities_sorted(world) -> None:
    from app.zt.catalog import capability_by_code

    world.service("zero_trust_dod")
    sent = _sent_details(world)
    expected = _expected_dod()
    codes = sorted(a["capability_code"] for a in world.answers)
    assert sorted(sent) == codes
    for code in codes:
        # The catalog is used only to find this code's DoD number.
        number = capability_by_code(code).dod_number
        assert sent[code] == expected[number], code
        ids = [a["id"] for a in sent[code]["activities"]]
        assert ids == sorted(ids, key=_activity_key), code
        assert {a["level"] for a in sent[code]["activities"]} <= {"target", "advanced"}, code


def test_every_dod_activity_id_starts_with_its_capabilitys_dod_number(world) -> None:
    """Requirement 2. Checked on what was SENT, against the source's numbering:
    a capability's number is read from the source by its name."""
    world.service("zero_trust_dod")
    sent = _sent_details(world)
    number_by_name = {
        c["name"]: c["id"] for c in _read(_DOD / "dod_zt_2025_rows.json")["capabilities"]
    }
    for code, entry in sent.items():
        number = number_by_name[entry["name"]]
        assert entry["activities"], code
        for act in entry["activities"]:
            assert act["id"].startswith(number + "."), (code, act["id"])


@pytest.mark.parametrize(
    ("kind", "framework"),
    [("zero_trust_cisa", "cisa"), ("zero_trust_dod", "dod")],
)
def test_ai_preview_shows_the_same_details_unaltered_by_redaction(world, kind, framework) -> None:
    """Requirement 3: with a client `legal_name` set, the redacted details equal
    the source byte for byte, in the preview as in the run."""
    world.service(kind)
    run_details = _sent_details(world)
    r = world.c.post("/ai/preview", headers=world.h, json={"service_id": world.svc_id})
    assert r.status_code == 200, r.text
    preview_details = r.json()["payload"]["capability_details"]
    assert json.dumps(preview_details, sort_keys=True) == json.dumps(run_details, sort_keys=True)
    if framework == "cisa":
        assert sorted(preview_details.values(), key=json.dumps) == sorted(
            _expected_cisa(), key=json.dumps
        )
    else:
        expected = _expected_dod()
        assert sorted(preview_details.values(), key=json.dumps) == sorted(
            expected.values(), key=json.dumps
        )


# --- the parser: current only -------------------------------------------------


def test_a_stray_target_is_counted_as_unknown_field_and_never_applied(world) -> None:
    world.service("zero_trust_cisa")
    code = world.answers[0]["capability_code"]
    world.patch(0, target_stage=3)
    world.capture({"capabilities": [{"code": code, "current": 2, "target": 4}]})

    result = zt_run_ai(world.c, world.svc_id, world.h)

    row = world.row(code)
    assert (row.maturity_stage, row.target_stage) == (2, 3)
    stray = [d for d in result["dropped"] if d["field"] == "target"]
    assert [(d["reason"], d["key"], d["values"]) for d in stray] == [("unknown_field", code, 1)]
    assert result["suggestions_applied"] == 1
    assert result["suggestions_received"] == result["suggestions_applied"] + sum(
        d["values"] for d in result["dropped"]
    )


# --- the runtime fixture, through the run ----------------------------------------

_SUBSTANTIVE = "MFA is enforced for every workforce account."


def _fixture_world(world: World, kind: str) -> tuple[set[str], set[str]]:
    """Notes on the first four rows, A5 placeholders on the next three, the
    rest left null. Returns (codes with notes, codes without a scoreable note)."""
    from app.ai.fixtures import _fixture_zt_score

    world.service(kind)
    for i in range(4):
        world.patch(i, notes=_SUBSTANTIVE)
    for i, placeholder in zip(range(4, 7), ("N/A", "  TBD ", "see interview"), strict=True):
        world.patch(i, notes=placeholder)
    world.provider.register("zt_score", _fixture_zt_score)
    noted = {world.answers[i]["capability_code"] for i in range(4)}
    rest = {a["capability_code"] for a in world.answers} - noted
    return noted, rest


def test_the_fixture_scores_noted_rows_only_on_cisa(world) -> None:
    noted, rest = _fixture_world(world, "zero_trust_cisa")
    result = zt_run_ai(world.c, world.svc_id, world.h)
    assert result["dropped"] == [], result["dropped"]
    assert result["suggestions_applied"] == len(noted)
    for code in noted:
        assert 1 <= world.row(code).maturity_stage <= 4, code  # A9, CISA
    for code in rest:
        assert world.row(code).maturity_stage is None, code


def test_the_fixture_respects_each_dod_capabilitys_levels(world) -> None:
    """Every DoD row carries notes, so every capability is scored, including
    the ones with no Target or no Advanced activity, which C4 constrains."""
    from app.ai.fixtures import _fixture_zt_score
    from app.zt.catalog import capability_by_code

    world.service("zero_trust_dod")
    for i in range(len(world.answers)):
        world.patch(i, notes=_SUBSTANTIVE)
    world.provider.register("zt_score", _fixture_zt_score)

    result = zt_run_ai(world.c, world.svc_id, world.h)

    assert result["dropped"] == [], result["dropped"]
    assert result["suggestions_applied"] == len(world.answers)
    levels_by_number = {
        number: {a["level"] for a in entry["activities"]}
        for number, entry in _expected_dod().items()
    }
    no_target = 0
    for a in world.answers:
        code = a["capability_code"]
        stage = world.row(code).maturity_stage
        levels = levels_by_number[capability_by_code(code).dod_number]
        assert 1 <= stage <= 3, code
        if "advanced" not in levels:
            assert stage <= 2, code  # C4: never 3
        if "target" not in levels:
            no_target += 1
            assert stage != 2, code  # C4: never 2
    # The C4 branch was exercised, not vacuously skipped.
    assert no_target > 0


@pytest.mark.parametrize("position", [0, 1])
def test_the_fixture_never_gives_2_to_a_capability_with_no_target_activity(position: int) -> None:
    """C4, directly: a payload in A2's shape, with the no-Target capability at
    each position, since the fixture's stage alternates by position."""
    from app.ai.fixtures import _fixture_zt_score

    advanced_only = {
        "pillar": "User",
        "name": "Advanced only",
        "activities": [{"id": "9.9.1", "name": "a", "level": "advanced", "description": "d"}],
    }
    with_target = {
        "pillar": "User",
        "name": "Has target",
        "activities": [{"id": "9.8.1", "name": "t", "level": "target", "description": "d"}],
    }
    codes = ["DOD.X.01", "DOD.X.02"]
    details = {codes[position]: advanced_only, codes[1 - position]: with_target}
    payload = {
        "framework": "dod_ztra",
        "capabilities": codes,
        "capability_details": details,
        "answers": {c: {"notes": _SUBSTANTIVE, "current": None} for c in codes},
    }
    rows = json.loads(_fixture_zt_score(payload).content)["capabilities"]
    by_code = {r["code"]: r["current"] for r in rows}
    assert set(by_code) == set(codes)
    assert by_code[codes[position]] != 2


def test_rows_the_fixture_leaves_out_are_counted_as_omitted(world) -> None:
    """A5 makes "no result" a by-design outcome; #840's accounting must see
    every such row through the real run. Expected sets come from the setup:
    the four noted rows are answered, the three placeholders are omitted with
    notes, and every other row is omitted with blank notes."""
    noted, rest = _fixture_world(world, "zero_trust_cisa")
    placeholders = {world.answers[i]["capability_code"] for i in range(4, 7)}

    result = zt_run_ai(world.c, world.svc_id, world.h)

    omitted = {o["capability_code"]: o for o in result["omitted_capabilities"]}
    assert set(omitted) == rest
    assert result["omitted_count"] == len(rest)
    assert {c for c, o in omitted.items() if not o["notes_blank"]} == placeholders
    assert all(o["kept_stage"] is None for o in omitted.values())
