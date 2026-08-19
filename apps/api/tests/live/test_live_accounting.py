"""Opt-in LIVE verification of W1's suggestion accounting (issue #51).

WHAT THIS CLOSES. `tests/live/test_live_ai.py` calls `run_job` directly, so the
accounting loop — the thing W1 built — had **never executed against a real
provider response**. Fixture mode structurally cannot produce a drop, because
the fixture echoes the parser's own keys back with in-range values, so every
drop counter in the product was proven only by synthetic unit tests.

THREE TIERS, labelled per test, because "verified live" would otherwise blur
three very different claims:

* **Tier A — natural.** A real call through the real route. Whatever accounting
  comes back is genuine observation. Nothing is asserted about WHICH reasons
  appear, because that would make a real model's behaviour a test dependency;
  what is asserted is the invariant, against real output.

* **Tier B — corrupt-after-live.** The real provider is called (real cost, real
  latency, real egress, real redaction) and the returned body is mutated before
  the parser sees it. This proves OUR HANDLING against a real response. It does
  NOT prove a real model emits these faults at any rate — that is a different
  claim and this file does not make it.

* **Tier C — impossible live, stated not skipped.** `protected` can never be
  observed against a real provider: `protected_keys()` returns an empty set
  whenever `is_fixture` is false, by construction. It is permanently
  fixture-only, in ZT and CSF alike. Recorded in `test_protected_is_fixture_only`
  so the exemption is asserted rather than remembered.

Usage (inside the api container, live env already present):

    docker compose exec -T api pytest -m live tests/live/test_live_accounting.py -q
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import LLMClient, LLMResponse
from app.config import get_settings


def _live_ready() -> tuple[bool, str]:
    settings = get_settings()
    if settings.shield_llm_mode != "live":
        return False, "SHIELD_LLM_MODE is not 'live'"
    return settings.live_llm_readiness()


_READY, _WHY = _live_ready()

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _READY, reason=f"live AI not configured: {_WHY}"),
]


class CorruptingProvider:
    """Calls the REAL provider, then mutates the body before the parser sees it.

    `name` and `model` are passed through deliberately. `name` must stay the
    real provider's, or `LLMClient.invoke` records the call as FIXTURE mode and
    `protected_keys` starts protecting rows — i.e. faking the provider name
    would quietly change the behaviour under test.
    """

    def __init__(self, inner: Any, mutate: Any) -> None:
        self._inner = inner
        self._mutate = mutate
        self.name = inner.name
        self.model = inner.model

    def complete(self, prompt: str, payload: dict[str, Any]) -> LLMResponse:
        real = self._inner.complete(prompt, payload)
        return LLMResponse(
            self._mutate(real.content),
            input_tokens=real.input_tokens,
            output_tokens=real.output_tokens,
        )


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, Any]]:
    """A real app on a scratch DB. Returns (client, live_provider)."""
    url = f"sqlite:///{tmp_path / 'shield-live-acct.db'}"
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

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    seed = TestSession()
    tenant = _Client(legal_name="Live Tenant")
    seed.add(tenant)
    seed.flush()
    seed.add(_ClientDomain(client_id=tenant.id, domain="example.com"))
    seed.commit()
    cid = str(tenant.id)
    seed.close()

    # The real provider, built exactly as the app builds it.
    with TestSession() as probe:
        live_provider = LLMClient.from_db(probe).provider
    assert live_provider.name != "fixture", "this file must never run on fixtures"

    with TestClient(app, headers={"X-Client-Id": cid}) as c:
        yield c, live_provider


def _admin(c: TestClient) -> tuple[dict, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "live-acct@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "Live",
        },
    )
    bearer = r.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}, cid


def _zt_service(c: TestClient, h: dict) -> tuple[str, str]:
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Live ZT"}
    ).json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    return svc_id, a["answers"][0]["capability_code"]


def _use(c: TestClient, provider: Any) -> None:
    """Point the ZT route's LLM dependency at `provider`."""
    from app.routes.zt import _llm_dep

    c.app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)


def _invariant(body: dict) -> None:
    accounted = body["suggestions_applied"] + sum(d["values"] for d in body["dropped"])
    assert body["suggestions_received"] == accounted, body


# --- Tier A ----------------------------------------------------------------


@pytest.mark.live
def test_live_zt_run_ai_accounting_holds_against_a_real_response(app_client) -> None:
    """TIER A. The accounting loop, executed against real provider output.

    This is the gap #51 named: every prior live test called `run_job` directly,
    so this loop had never seen a real response. Nothing is asserted about WHICH
    reasons appear — a real model's behaviour must not be a test dependency —
    only that the invariant holds and the run is reportable.
    """
    c, live = app_client
    h, _ = _admin(c)
    _use(c, live)
    svc_id, _code = _zt_service(c, h)

    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    _invariant(body)
    assert body["suggestions_received"] > 0, "a live run that received nothing proves nothing"
    # Recorded for the issue: what a real model actually did.
    by_reason = {d["reason"]: d["values"] for d in body["dropped"]}
    received = body["suggestions_received"]
    applied = body["suggestions_applied"]
    print(f"[live] ZT natural accounting: {received=} {applied=} {by_reason=}")


# --- Tier B ----------------------------------------------------------------


def _corrupt_zt(mutation: Any) -> Any:
    """Mutate the parsed `capabilities` of a real response, then re-serialize."""

    def _mutate(content: str) -> str:
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            pytest.skip("real response was not JSON; nothing to corrupt")
        caps = data.get("capabilities")
        if not isinstance(caps, list) or not caps:
            pytest.skip("real response carried no capabilities to corrupt")
        data["capabilities"] = mutation(caps)
        return json.dumps(data)

    return _mutate


@pytest.mark.parametrize(
    ("name", "mutation", "reason"),
    [
        ("out_of_range", lambda caps: [{**caps[0], "current": 9}], "out_of_range"),
        ("unparseable", lambda caps: [{**caps[0], "current": "not-a-stage"}], "unparseable"),
        ("unknown_field", lambda caps: [{**caps[0], "maturity_level": 2}], "unknown_field"),
        ("unknown_key", lambda caps: [{**caps[0], "code": "NOPE-1"}], "unknown_key"),
        ("entry_shape", lambda caps: ["not-a-dict"], "entry_shape"),
        ("superseded", lambda caps: [caps[0], caps[0]], "superseded"),
    ],
)
@pytest.mark.live
def test_live_zt_drop_reason_after_a_real_call(app_client, name, mutation, reason) -> None:
    """TIER B. A REAL call, then the body is corrupted before parsing.

    Proves our handling against a real response — not that a model produces
    this. Each parametrization costs one real call.
    """
    c, live = app_client
    h, _ = _admin(c)
    _use(c, CorruptingProvider(live, _corrupt_zt(mutation)))
    svc_id, _code = _zt_service(c, h)

    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()

    assert reason in {d["reason"] for d in body["dropped"]}, (name, body["dropped"])
    _invariant(body)


@pytest.mark.live
def test_live_zt_non_list_capabilities_is_a_typed_502_after_a_real_call(app_client) -> None:
    """TIER B. The shape guard, against a real call.

    `parse_json_object_with_list("capabilities")` shipped in D-048 and had only
    synthetic coverage.
    """
    c, live = app_client
    h, _ = _admin(c)

    def _scalar(content: str) -> str:
        return json.dumps({"capabilities": 0})

    _use(c, CorruptingProvider(live, _scalar))
    svc_id, _code = _zt_service(c, h)

    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"
    assert "drifted apart" in r.json()["error"]["message"]


@pytest.mark.live
def test_live_zt_locked_row_is_reported_after_a_real_call(app_client) -> None:
    """TIER B. `locked` needs an API-seeded lock plus a real call.

    Not reachable through the ZT workspace, which has no lock control (#40).
    """
    c, live = app_client
    h, _ = _admin(c)
    _use(c, live)
    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Live ZT lock"}
    ).json()["id"]
    a = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in a["answers"]:
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"locked": True})

    r = c.post(f"/zt/services/{svc_id}/run-ai", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "locked" in {d["reason"] for d in body["dropped"]}, body["dropped"]
    _invariant(body)


# --- Tier C ----------------------------------------------------------------


@pytest.mark.live
def test_protected_is_fixture_only_and_can_never_be_observed_live(app_client) -> None:
    """TIER C. Asserted rather than remembered.

    `protected_keys` returns an empty set whenever `is_fixture` is false, so the
    `protected` reason is unreachable against any real provider — in ZT and, since
    D-048, in CSF too. This is a definitional property, not a coverage gap, and
    #51 should not carry it as outstanding forever.
    """
    from app.ai.provenance import protected_keys

    rows = [("CISA.ID.01", "client", True), ("CISA.ID.02", "consultant", True)]
    assert protected_keys(rows, is_fixture=True), "fixture must protect non-AI answers"
    assert protected_keys(rows, is_fixture=False) == set(), (
        "a live run must never protect — if this fails, `protected` became "
        "live-reachable and #51's scope needs rewriting"
    )
