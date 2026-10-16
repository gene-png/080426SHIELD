"""The world the #552 redaction-isolation tests share: one tenant on SQLite with
an admin, a recording fixture provider wired into Tech Debt, CSF and Risk, and
a redaction budget too generous to be met by ordinary work (`ROOM_TO_REDACT_S`),
plus the helpers the test files use. A test that exercises the budget, or
quotes the "0.5-second" copy, sets `OVER_BUDGET_S` itself (`set_budget`). A module
rather than a conftest so the fixture is imported by name where it is used
(`_world`, requested as `world`)."""

from __future__ import annotations

import io
import threading
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityList
from app.models.llm_call import LLMCall
from app.storage.local import LocalFilesystemStorage
from tests._ai_runs import get_run
from tests._csf_notes import note_every_answer

_PASSWORD = "correct horse battery staple!"

#: The hang guard every test uses. A HANG GUARD, never a latency assertion: the
#: work under test is stopped at 0.5 s to a few seconds, so this fails only
#: when a budget or a release is missing altogether.
HANG_GUARD_S = 60

#: The budget the world gives every test that does not set its own (#1143).
#: The budget is wall clock from the child's start, and under pytest each child
#: first re-runs the `pytest` script as `__mp_main__` before it redacts: about
#: 0.1 s idle, 0.6 to 1.8 s on one CPU shared eight ways. At 0.5 s that failed
#: CI on real redactions in tests that never meant to touch the budget. Kept
#: under the hang guard, so a child that never ends still fails the test.
ROOM_TO_REDACT_S = "10"

#: The budget a test sets EXPLICITLY, with `set_budget`, when it exercises the
#: budget (a child that spins until it is stopped) or quotes the approved copy
#: with "0.5-second" in it. Short, so a deliberate overrun costs half a second.
OVER_BUDGET_S = "0.5"

#: apps/api: where a stand-in api process must start, so `app` and `tests` import.
API_DIR = Path(__file__).resolve().parent.parent


class LiveLookingProvider(FixtureProvider):
    """Serves canned output but REPORTS itself live, the way a provider built
    from a stored key does. Everything mode-dependent keys on `provider.name`,
    so a run through it is a LIVE run: `charged_likely` means something."""

    name = "anthropic"


@pytest.fixture(name="world")
def _world(tmp_path, monkeypatch) -> Iterator[dict[str, Any]]:
    """A tenant with an admin, a recording provider, and the redaction budget at
    `ROOM_TO_REDACT_S`. Settings are read through `get_settings()`, so its
    cache is cleared on the way in and out. On the way out, every place and
    slot must be free: a test that leaked one would otherwise poison the next."""
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", ROOM_TO_REDACT_S)
    monkeypatch.setenv("SHIELD_REDACTION_MAX_CHILDREN", "2")
    monkeypatch.setenv("SHIELD_REDACTION_MAX_RUNS", "4")
    monkeypatch.setenv("SHIELD_REDACTION_SLOT_WAIT_SECONDS", "5")
    get_settings.cache_clear()

    url = f"sqlite:///{tmp_path / 'shield-iso.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    api_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")
    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")

    sent: list[dict] = []
    lock = threading.Lock()

    def _recorder(answer: str) -> Callable[[dict], LLMResponse]:
        def _record(payload: dict) -> LLMResponse:
            with lock:
                sent.append(payload)
            return LLMResponse(answer, input_tokens=1, output_tokens=1)

        return _record

    from app.db.session import get_db
    from app.main import create_app
    from app.routes import csf as csf_routes
    from app.routes import risk as risk_routes
    from app.routes import tech_debt as tech_debt_routes
    from app.routes.artifacts import _storage_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_storage_dep] = lambda: storage

    def use_provider(provider: FixtureProvider) -> FixtureProvider:
        provider.register("extract.capabilities", _recorder('{"items": []}'))
        provider.register("csf_score", _recorder('{"scores": []}'))
        provider.register("risk_synthesize", _recorder('{"entries": []}'))
        for dep in (tech_debt_routes._llm_dep, csf_routes._llm_dep, risk_routes._llm_dep):
            app.dependency_overrides[dep] = lambda p=provider: LLMClient(p)
        return provider

    seed = TestSession()
    from app.models.client import Client
    from app.models.client_domain import ClientDomain

    tenant = Client(legal_name="Test Tenant")
    seed.add(tenant)
    seed.flush()
    seed.add(ClientDomain(client_id=tenant.id, domain="example.com"))
    seed.commit()
    tenant_id = tenant.id
    seed.close()

    w: dict[str, Any] = {
        "app": app,
        "Session": TestSession,
        "tenant_id": tenant_id,
        "sent": sent,
        "tmp": tmp_path,
    }
    w["provider"] = use_provider(FixtureProvider())
    w["use_provider"] = use_provider
    with TestClient(app, headers={"X-Client-Id": str(tenant_id)}) as c:
        r = c.post(
            "/auth/register",
            json={
                "email": "admin@kentro-consulting.com",
                "password": _PASSWORD,
                "display_name": "Kentro Admin",
            },
        )
        assert r.status_code == 201, r.text
        w["bearer"] = r.json()["tokens"]["access_token"]
        w["c"] = c
        w["h"] = {"Authorization": f"Bearer {w['bearer']}"}
        yield w
    try:
        wait_until_idle()
    finally:
        # Always, and the environment BEFORE the cache (#1143). A test that
        # fails holding a place makes `wait_until_idle` raise; that used to
        # skip the cache clear, so this test's cached settings outlived it and
        # every later test without a world of its own (Risk's `app_client`
        # clears nothing) ran under them. Reproduced: with
        # `test_one_call_runs_never_push_...` failing that way, the next file,
        # `test_risk_attack_evidence_stored_status.py`, failed on the
        # "0.5-second" budget it never sets -- the pair CI #1159 failed.
        # Restoring the environment first means nothing in the gap can
        # re-cache this test's values.
        monkeypatch.undo()
        get_settings.cache_clear()


def set_budget(monkeypatch, seconds: str) -> None:
    """Set the redaction budget for this test, e.g. `OVER_BUDGET_S`, and drop
    the cached settings so the next redaction reads it."""
    from app.config import get_settings

    monkeypatch.setenv("SHIELD_REDACTION_BUDGET_SECONDS", seconds)
    get_settings.cache_clear()


def wait_until_idle() -> None:
    """Every place and every child slot free, within the hang guard. A child
    a test left running (a deliberate holder) is stopped by its budget; this
    waits for that rather than leaving it to the next test."""
    from app.ai import isolation

    for _ in range(HANG_GUARD_S * 20):
        if isolation.places_in_use() == 0 and isolation.slots_in_use() == 0:
            return
        threading.Event().wait(0.05)
    raise AssertionError(
        f"redaction state never went idle: places={isolation.places_in_use()} "
        f"slots={isolation.slots_in_use()}"
    )


def use_live_provider(w: dict) -> FixtureProvider:
    """Swap every route onto a provider that reports itself live."""
    w["provider"] = w["use_provider"](LiveLookingProvider())
    return w["provider"]


def add_tenant_user(w: dict, email: str, display_name: str) -> None:
    from app.models.user import User, UserRole

    with w["Session"]() as db:
        db.add(
            User(
                email=email,
                password_hash="x",
                role=UserRole.CLIENT,
                display_name=display_name,
                client_id=w["tenant_id"],
            )
        )
        db.commit()


def control_dir(w: dict) -> Path:
    """A directory a stand-in child target can find through the channels that
    reach the child besides the payload (see `_isolation_targets._control_dir`):
    the hint set, as a tenant user whose display name is `__ctl__:<dir>` (Tech
    Debt), and the client's name, as the tenant's legal name (CSF and Risk)."""
    from app.models.client import Client

    d = w["tmp"] / "ctl"
    d.mkdir()
    add_tenant_user(w, "ctl@example.com", f"__ctl__:{d}")
    with w["Session"]() as db:
        db.get(Client, w["tenant_id"]).legal_name = f"__ctl__:{d}"
        db.commit()
    return d


def service_and_artifact(w: dict, csv_text: str) -> tuple[str, str]:
    c, h = w["c"], w["h"]
    r = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD"})
    assert r.status_code == 201, r.text
    svc_id = r.json()["id"]
    r = c.post(
        "/artifacts",
        headers=h,
        files={"file": ("inv.csv", io.BytesIO(csv_text.encode()), "text/csv")},
    )
    assert r.status_code == 201, r.text
    return svc_id, r.json()["id"]


def start_extract(w: dict, svc_id: str, artifact_id: str, *, serves: str = "offline") -> str:
    r = w["c"].post(
        f"/tech-debt/services/{svc_id}/capability-lists/extract",
        headers=w["h"],
        json={"artifact_id": artifact_id, "serves": serves},
    )
    assert r.status_code == 202, r.text
    return r.json()["run_id"]


def extract(w: dict, svc_id: str, artifact_id: str, *, serves: str = "offline") -> dict:
    """POST the extraction and return the run as it ENDED. Starlette's
    TestClient runs the background job before `post()` returns, so the run read
    here is terminal; the assert says so if it is not."""
    run = get_run(w["c"], start_extract(w, svc_id, artifact_id, serves=serves), w["h"])
    assert run["status"] != "running", f"run {run['id']} is still RUNNING: {run!r}"
    return run


def csf_service(w: dict) -> str:
    c, h = w["c"], w["h"]
    r = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert r.status_code == 201, r.text
    svc_id = r.json()["id"]
    assert c.post(f"/csf/services/{svc_id}/assessments", headers=h).status_code < 300
    r = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert r.status_code < 300, r.text
    # CSF Option 1 (D-114): only answers with notes are sent, and these runs
    # need a full profile's batches.
    note_every_answer(svc_id)
    return svc_id


def csf_run(w: dict, svc_id: str) -> dict:
    """POST a CSF Run-AI (batched, 5-way fan-out) and return the ended run."""
    r = w["c"].post(f"/csf/services/{svc_id}/run-ai", headers=w["h"], json={"serves": "offline"})
    assert r.status_code == 202, r.text
    run = get_run(w["c"], r.json()["run_id"], w["h"])
    assert run["status"] != "running", f"run {run['id']} is still RUNNING: {run!r}"
    return run


def csf_scored_rows(w: dict, svc_id: str) -> int:
    """Rows of this service's assessment carrying any AI-applied value."""
    from app.models.csf_assessment import CsfAssessment
    from app.models.csf_profile import CsfDimensionScore

    with w["Session"]() as db:
        return db.execute(
            select(func.count())
            .select_from(CsfDimensionScore)
            .join(CsfAssessment, CsfAssessment.id == CsfDimensionScore.assessment_id)
            .where(
                CsfAssessment.service_id == uuid.UUID(svc_id),
                CsfDimensionScore.what_we_found.is_not(None),
            )
        ).scalar_one()


def post_within(seconds: float, fn) -> Any:
    """Run `fn` in a thread and fail if it has not returned in `seconds`. A HANG
    GUARD, not a latency assertion: a missing budget would otherwise hold the
    suite for minutes and then report something unrelated."""
    box: dict[str, Any] = {}

    def _go() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised below, in the test thread
            box["error"] = exc

    t = threading.Thread(target=_go, daemon=True)
    t.start()
    t.join(seconds)
    assert not t.is_alive(), f"no answer within {seconds} s: a budget or a release is missing"
    if "error" in box:
        raise box["error"]
    return box["value"]


def wait_for_file(path: Path) -> None:
    """Until a stand-in child has written `path` (its PID), within the guard."""
    for _ in range(HANG_GUARD_S * 20):
        if path.is_file() and path.read_text():
            return
        threading.Event().wait(0.05)
    raise AssertionError(f"{path} never appeared: the stand-in child never ran")


def lists_for(w: dict, svc_id: str) -> int:
    with w["Session"]() as db:
        return db.execute(
            select(func.count())
            .select_from(CapabilityList)
            .where(CapabilityList.service_id == uuid.UUID(svc_id))
        ).scalar_one()


def llm_rows(w: dict) -> int:
    with w["Session"]() as db:
        return db.execute(select(func.count()).select_from(LLMCall)).scalar_one()


def assert_gone(pid: int) -> None:
    """The PID names no process: not running, and not a zombie either, since a
    zombie still answers signal 0."""
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    raise AssertionError(f"child PID {pid} still exists after the redaction ended")


def is_running(pid: int) -> bool:
    """The PID names a live process: not gone, and not a zombie either."""
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii") as f:
            state = f.read().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state != "Z"


def assert_running(pid: int) -> None:
    if not is_running(pid):
        raise AssertionError(f"child PID {pid} is not running, so this proves nothing")
