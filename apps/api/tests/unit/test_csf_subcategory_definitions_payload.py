"""csf_score sends each subcategory's NIST outcome text (#806 D2).

The approved prompt (#806 comment 5982122270, section 1) reads
`subcategory_definitions`: "a map of Subcategory code to its NIST CSF 2.0
outcome text", and section 4 makes it the first assessment basis. D2 says what
it holds: code to `catalog.Subcategory.outcome`, limited per batch to that
batch's codes, through the same redacting egress, and shown in the preview.

Every test goes through the endpoints a consultant reaches (`/ai/preview` and
Run AI), never the request builder. The expected text is the catalog's, read
through its public accessor: the catalog is checked against NIST CSWP 29 by
`test_csf_catalog_cswp29.py`, so it is the spec here, not the thing under test.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.csf.catalog import subcategory_by_code
from app.models.llm_call import LLMCall
from tests._ai_runs import csf_run_ai

pytestmark = pytest.mark.unit

_TIERS = ["high", "low", "moderate"]


@dataclass
class World:
    c: TestClient
    sessions: sessionmaker
    provider: FixtureProvider
    h: dict
    svc_id: str


def _world(tmp_path: Path, legal_name: str) -> Iterator[World]:
    url = f"sqlite:///{tmp_path / 'shield-csfdefs.db'}"
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
    from app.models.client import Client
    from app.models.client_domain import ClientDomain
    from app.routes.csf import _llm_dep

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
    with sessions() as seed:
        tenant = Client(legal_name=legal_name)
        seed.add(tenant)
        seed.flush()
        seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
        seed.commit()
        cid = str(tenant.id)
    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        bearer = c.post(
            "/auth/register",
            json={
                "email": "admin@example.com",
                "password": "correct horse battery staple!",
                "display_name": "A",
            },
        ).json()["tokens"]["access_token"]
        h = {"Authorization": f"Bearer {bearer}"}
        svc_id = c.post(
            "/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}
        ).json()["id"]
        a = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
        assert a.status_code in (200, 201), a.text
        seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": _TIERS})
        assert seeded.status_code in (200, 201), seeded.text
        yield World(c, sessions, provider, h, svc_id)


@pytest.fixture()
def world(tmp_path) -> Iterator[World]:
    yield from _world(tmp_path, "Test Tenant")


@pytest.fixture()
def critical(tmp_path) -> Iterator[World]:
    """A client whose legal name is a whole word in NIST's outcome text:
    GV.OC-04 begins "Critical objectives", and ID.RA-10 "Critical suppliers"."""
    yield from _world(tmp_path, "Critical")


class _Recorder:
    """Records every payload the provider receives, from every batch thread,
    and answers with no rows, so the run writes nothing."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, payload: dict[str, Any]) -> LLMResponse:
        with self._lock:
            self.payloads.append(payload)
        return LLMResponse('{"scores": []}')


def _preview(w: World) -> dict[str, Any]:
    r = w.c.post("/ai/preview", json={"service_id": w.svc_id}, headers=w.h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["purpose"] == "csf_score"
    return body["payload"]


def _outcomes(codes: list[str]) -> dict[str, str]:
    return {code: subcategory_by_code(code).outcome for code in codes}


def _note(w: World, code: str, notes: str) -> None:
    latest = w.c.get(f"/csf/services/{w.svc_id}/assessments/latest", headers=w.h)
    assert latest.status_code == 200, latest.text
    answer = next(a for a in latest.json()["answers"] if a["subcategory_code"] == code)
    saved = w.c.patch(f"/csf/answers/{answer['id']}", json={"notes": notes}, headers=w.h)
    assert saved.status_code == 200, saved.text


def test_the_preview_shows_every_subcategorys_nist_outcome(world) -> None:
    """D2: "the preview shows it". Every code the request asks about has its
    outcome text, in the order the codes are asked about."""
    payload = _preview(world)
    codes = payload["subcategories"]
    assert len(codes) == 106, "the Working Profile this test is about"
    definitions = payload["subcategory_definitions"]
    assert list(definitions) == codes
    assert definitions == _outcomes(codes)
    # A literal anchor from NIST's own text, so the comparison above cannot
    # pass over two empty strings.
    assert definitions["GV.OC-01"].startswith("The organizational mission is understood")


def test_each_batch_sends_only_its_own_subcategories_definitions(world) -> None:
    """D2: "limited per batch to that batch's codes". A batch carrying every
    definition would resend 106 outcomes on each of 33 calls."""
    rec = _Recorder()
    world.provider.register("csf_score", rec)
    csf_run_ai(world.c, world.svc_id, world.h)
    assert len(rec.payloads) > 1, "a batched run egresses more than one payload"
    for p in rec.payloads:
        codes = p["subcategories"]
        assert 0 < len(codes) < 106
        assert list(p["subcategory_definitions"]) == codes, p["tiers"]
        assert p["subcategory_definitions"] == _outcomes(codes)
    sent = {c for p in rec.payloads for c in p["subcategory_definitions"]}
    assert len(sent) == 106


def test_a_client_named_critical_gets_nists_text_and_its_name_is_still_redacted(
    critical,
) -> None:
    """#984 (option (a), #985): catalog text reaches the model unredacted and
    guarded, while the client's name in the notes is still replaced."""
    _note(critical, "GV.OC-04", "Critical's CISO reviews this list every quarter.")
    gv_oc_04 = subcategory_by_code("GV.OC-04").outcome
    assert gv_oc_04.startswith("Critical objectives"), "the collision this test is about"

    payload = _preview(critical)
    assert payload["subcategory_definitions"]["GV.OC-04"] == gv_oc_04
    notes = payload["answers"]["GV.OC-04"]["notes"]
    assert "Critical" not in notes
    assert "[CLIENT]" in notes

    rec = _Recorder()
    critical.provider.register("csf_score", rec)
    csf_run_ai(critical.c, critical.svc_id, critical.h)
    with_code = [p for p in rec.payloads if "GV.OC-04" in p["subcategory_definitions"]]
    assert len(with_code) == len(_TIERS), "one batch per tier asks about GV.OC-04"
    for p in with_code:
        assert p["subcategory_definitions"]["GV.OC-04"] == gv_oc_04
        assert "Critical" not in p["answers"]["GV.OC-04"]["notes"]


def test_a_run_records_the_v2_prompt_in_llm_calls(world) -> None:
    """C9: an llm_calls row from a run says which prompt produced it."""
    world.provider.register("csf_score", _Recorder())
    csf_run_ai(world.c, world.svc_id, world.h)
    with world.sessions() as db:
        versions = (
            db.execute(select(LLMCall.prompt_version).where(LLMCall.purpose == "csf_score"))
            .scalars()
            .all()
        )
    assert versions, "the run wrote no llm_calls row"
    assert set(versions) == {"v2"}
