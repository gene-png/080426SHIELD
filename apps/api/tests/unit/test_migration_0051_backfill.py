"""Migration 0051's backfill, against rows the PRODUCT built (#209).

## Why the world is built through the API and then the migration is REWOUND

The obvious construction -- stop at 0050, hand-insert rows, upgrade -- builds
the fixture from the migration author's idea of what a deliverable and a
finalize audit row look like. That is the shape `CLAUDE.md` warns about twice
over: a fixture authored from what the parser expects agrees with the parser by
construction, and a fixture that builds a state no writer can reach is testing a
different system.

So instead: drive the real finalize route, then `downgrade 0051 -> 0050` (which
drops the two columns and with them everything finalize stamped) and
`upgrade 0050 -> 0051` again. The backfill is now reading the SAME audit rows
production would, and the assertion is that it RECOVERS WHAT FINALIZE WROTE.
Those two values are produced by different code from different inputs, so
agreement between them is evidence rather than tautology.

It exercises the downgrade for free, which is the half a round-trip smoke test
proves only for an empty database.
"""

from __future__ import annotations

import os
import uuid as _uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.storage.local import LocalFilesystemStorage


@pytest.fixture()
def ctx(tmp_path) -> Iterator[tuple[TestClient, Config]]:
    db_path = tmp_path / "shield-0051.db"
    url = f"sqlite:///{db_path}"
    os.environ["DATABASE_URL"] = url
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    engine = create_engine(url, future=True)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    storage = LocalFilesystemStorage(tmp_path / "storage")

    from app.db.session import get_db
    from app.main import create_app
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

    from app.models.client import Client as _Client
    from app.models.client_domain import ClientDomain as _ClientDomain

    _seed = TestSession()
    _tenant = _Client(legal_name="Test Tenant")
    _seed.add(_tenant)
    _seed.flush()
    _seed.add(_ClientDomain(client_id=_tenant.id, domain="example.com"))
    _seed.commit()
    _cid = str(_tenant.id)
    _seed.close()

    with TestClient(app, headers={"X-Client-Id": _cid}) as c:
        yield c, cfg


def _session():
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    return sessionmaker(bind=eng, future=True)()


def _build_released_zt(c: TestClient, *, stage: int | None) -> str:
    """A released ZT service on `stage`, built entirely through the API."""
    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "admin",
        },
    )
    assert r.status_code == 201, r.text
    h = {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}

    svc_id = c.post(
        "/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Atlas - ZT"}
    ).json()["id"]

    with _session() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = _SR(
            client_id=svc.client_id,
            service_type=svc.kind.value,
            requested_by=svc.opened_by,
            zt_target_stage=stage,
        )
        s.add(sr)
        s.flush()
        svc.source_request_id = sr.id
        s.commit()

    assessment = c.post(f"/zt/services/{svc_id}/assessments", headers=h).json()
    for ans in assessment["answers"]:
        c.patch(f"/zt/answers/{ans['id']}", headers=h, json={"maturity_stage": 2})
    c.post(f"/zt/assessments/{assessment['id']}/approve", headers=h)
    deliv_id = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    assert c.post(f"/zt/deliverables/{deliv_id}/release", headers=h).status_code == 200
    return svc_id


def _admin_token(c: TestClient) -> str:
    """The admin bearer, re-issued. `_build_released_zt` registers the user."""
    r = c.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "correct horse battery staple!"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # `/auth/login` returns a bare `TokenPairResponse`; `/auth/register` nests it
    # under `tokens`. Both shapes are handled rather than guessed, because the
    # first version of this helper assumed the register shape and died with
    # `KeyError: 'tokens'`.
    return body["access_token"] if "access_token" in body else body["tokens"]["access_token"]


def _freeze(svc_id: str) -> tuple[int | None, str | None]:
    from app.models.deliverable import Deliverable

    with _session() as s:
        d = s.execute(
            select(Deliverable)
            .where(Deliverable.service_id == _uuid.UUID(svc_id))
            .order_by(Deliverable.version.desc())
            .limit(1)
        ).scalar_one()
        return d.frozen_target, d.frozen_target_source


def _rewind(cfg: Config) -> None:
    """0051 -> 0050 -> 0051. The columns are dropped and rebuilt, so whatever
    finalize stamped is gone and only the backfill can put it back."""
    command.downgrade(cfg, "0050")
    command.upgrade(cfg, "0051")


@pytest.mark.unit
def test_the_downgrade_actually_removes_the_columns(ctx) -> None:
    """The precondition every other test here depends on.

    If the downgrade quietly left the columns populated, every assertion below
    would pass while testing nothing -- the revert-did-not-land shape, at the
    schema level. So this is checked directly rather than assumed.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=4)
    assert _freeze(svc_id) == (4, "finalize")

    command.downgrade(cfg, "0050")
    with _session() as s:
        cols = {r[1] for r in s.execute(text("PRAGMA table_info(deliverables)"))}
    assert "frozen_target" not in cols, cols
    assert "frozen_target_source" not in cols, cols

    command.upgrade(cfg, "0051")
    with _session() as s:
        cols = {r[1] for r in s.execute(text("PRAGMA table_info(deliverables)"))}
    assert {"frozen_target", "frozen_target_source"} <= cols


@pytest.mark.unit
@pytest.mark.parametrize("stage", [4, 2])
def test_the_audit_backfill_recovers_the_stage_finalize_stamped(ctx, stage) -> None:
    """Two independent producers of one value, required to agree.

    Finalize writes the CHOSEN stage to the column directly. The backfill reads
    the RESOLVED stage back out of the audit payload and infers the choice from
    `target_stage_source == "client"`. Different code, different input, same
    answer -- which is why this is evidence and not a tautology.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=stage)
    assert _freeze(svc_id) == (stage, "finalize")

    _rewind(cfg)

    assert _freeze(svc_id) == (
        stage,
        "audit",
    ), "the backfill did not recover the stage the finalize audit row records"


@pytest.mark.unit
def test_the_audit_backfill_recovers_an_ABSENT_choice_as_an_exact_freeze(ctx) -> None:
    """`default` means the resolver was handed NULL, which is recoverable.

    The mutant this kills: skipping any row whose source is not `client`. That
    leaves the commonest engagement -- no target chosen at intake -- unfrozen
    forever, so the fix ships and does nothing for most clients.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=None)
    assert _freeze(svc_id) == (None, "finalize")

    _rewind(cfg)

    value, source = _freeze(svc_id)
    assert source == "audit", (
        "a deliverable whose client chose nothing was left UNFROZEN by the "
        "backfill, so it falls back to a live read forever"
    )
    assert value is None


@pytest.mark.unit
def test_an_out_of_range_choice_is_recovered_VERBATIM_by_the_updated_at_arm(ctx) -> None:
    """The two arms have DIFFERENT information, and this is where it shows.

    A stored 9 is out of range on CISA's ladder. The audit row records the
    RESOLVED stage -- the framework default -- with source `client_out_of_range`,
    so the audit arm cannot recover the 9 and declines rather than freezing the
    default under a label that would read as "the client chose nothing". The
    `updated_at` arm reads the raw column and CAN recover it, so it freezes 9
    verbatim, which is exactly what finalize stamped.

    **`source == "updated_at"` IS THE EVIDENCE THE AUDIT ARM DECLINED.** The
    audit row is present and is consulted first; had it not declined, this would
    read `audit`.

    This corrects what the first version of this test asserted -- `(None, None)`,
    on the theory that an unusable choice ends unfrozen. That was wrong and the
    test is what found it: freezing 9 reproduces the released report exactly,
    because the resolver is deterministic and turns 9 into the same default and
    the same `client_out_of_range` source every time. Declining here would throw
    away a recoverable fact and hand the client a live read instead.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=9)
    assert _freeze(svc_id) == (9, "finalize")

    _rewind(cfg)

    assert _freeze(svc_id) == (9, "updated_at"), (
        "either the audit arm relabelled an out-of-range choice instead of "
        "declining it (source would be 'audit'), or the fallback failed to "
        "recover a value it can read directly"
    )


@pytest.mark.unit
def test_an_out_of_range_choice_with_BOTH_arms_declining_stays_unfrozen(ctx) -> None:
    """Fail closed when neither arm can recover the choice.

    Audit declines (it holds only the resolved default); `updated_at` declines
    (the intake row has been written since the deliverable froze, so its value
    may have drifted). Nothing is known, so nothing is asserted: the dashboard
    computes live and says so.

    The write below changes the value to a DIFFERENT one on purpose. A
    same-value assignment leaves the row clean, SQLAlchemy emits no UPDATE, and
    `onupdate` never fires -- which is how the first version of this setup
    silently failed to move `updated_at` at all.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=9)

    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    with _session() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = s.get(_SR, svc.source_request_id)
        sr.zt_target_stage = 8
        s.add(sr)
        s.commit()

    _rewind(cfg)

    assert _freeze(svc_id) == (None, None), "a choice neither arm can recover was frozen anyway"


@pytest.mark.unit
def test_the_updated_at_fallback_freezes_an_untouched_intake_row(ctx) -> None:
    """Source 2, reached by deleting the audit row the finalize route wrote.

    This is the only way to exercise the fallback against product-built data:
    with an audit row present source 1 always wins, which is the intended
    precedence and is asserted by the tests above.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=4)

    with _session() as s:
        n = s.execute(
            text("DELETE FROM audit_entries WHERE action LIKE '%deliverable.finalized'")
        ).rowcount
        s.commit()
    assert n >= 1, "no finalize audit row was found to delete -- the setup is wrong"

    _rewind(cfg)

    assert _freeze(svc_id) == (4, "updated_at"), (
        "the fallback did not freeze an intake row that has not been written "
        "since the deliverable was finalized"
    )


@pytest.mark.unit
def test_arm_2_picks_the_column_by_SERVICE_KIND_not_by_coalesce(ctx) -> None:
    """A ZT service carrying a stray CSF tier must freeze the STAGE.

    THIS IS A REGRESSION TEST FOR A MEASURED DEFECT, not a hypothetical. Arm 2
    read `COALESCE(sr.csf_target_tier, sr.zt_target_stage)` under a comment
    claiming COALESCE "picks whichever the service kind populated". It does not:
    `routes/intake.py::_validate_targets` records that `submit_intake` WRITES
    BOTH COLUMNS for every item regardless of `service_type`, asking presence per
    type but range for every value. So a ZT item carrying an in-range
    `csf_target_tier` is accepted and both are stored, and CSF is first in the
    COALESCE.

    Measured on postgres:16-alpine before the fix: a ZT deliverable froze
    `frozen_target=4, source=updated_at` for a client who contracted stage 2 --
    MORE gaps than the released PDF lists, under a non-null `target_frozen_at`
    whose entire meaning is "these figures agree with your report". #209's harm,
    produced by #209's fix.

    The audit row is deleted so arm 2 is the arm under test; arm 1 always wins
    where it can, which the tests above assert.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=2)

    # The stray tier, written the way intake writes it: alongside the stage, on
    # the same row, for a service whose kind does not use it.
    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    with _session() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = s.get(_SR, svc.source_request_id)
        sr.csf_target_tier = 4
        s.add(sr)
        s.commit()
        # `updated_at` moved, so predicate 2 would now decline this deliverable.
        # Re-finalizing is what puts a fresh deliverable after the write.
        finalized_after = sr.updated_at

    h = {"Authorization": f"Bearer {_admin_token(c)}"}
    deliv_id = c.post(f"/zt/services/{svc_id}/deliverables/finalize", headers=h).json()["id"]
    assert c.post(f"/zt/deliverables/{deliv_id}/release", headers=h).status_code == 200
    assert finalized_after is not None

    with _session() as s:
        s.execute(
            text(
                "UPDATE audit_entries SET target_type = 'deliverable_disabled'"
                " WHERE action LIKE '%deliverable.finalized'"
            )
        )
        s.commit()

    _rewind(cfg)

    value, source = _freeze(svc_id)
    assert source == "updated_at", (
        f"arm 2 is not the arm under test (source={source!r}); the audit rows "
        f"were not neutralised"
    )
    assert value == 2, (
        f"arm 2 froze {value!r} onto a ZERO TRUST deliverable. The client "
        f"contracted stage 2; 4 is the stray `csf_target_tier` on the same intake "
        f"row, which COALESCE reaches first. The column must be chosen by "
        f"`services.kind`."
    )


@pytest.mark.unit
def test_a_row_written_AFTER_finalize_is_left_unfrozen(ctx) -> None:
    """The under-backfill direction, asserted rather than described.

    `updated_at > finalized_at` means the stored target may have moved since the
    report was rendered, so the safe answer is NO FREEZE -- compute live and say
    so. Freezing here would stamp a drifted value as though it were original,
    which is #209 with a provenance column asserting it is not.
    """
    c, cfg = ctx
    svc_id = _build_released_zt(c, stage=4)

    with _session() as s:
        s.execute(text("DELETE FROM audit_entries WHERE action LIKE '%deliverable.finalized'"))
        s.commit()

    from app.models.service import Service as _Service
    from app.models.service_request import ServiceRequest as _SR

    with _session() as s:
        svc = s.get(_Service, _uuid.UUID(svc_id))
        sr = s.get(_SR, svc.source_request_id)
        sr.zt_target_stage = 2
        s.add(sr)
        s.commit()

    _rewind(cfg)

    assert _freeze(svc_id) == (None, None), (
        "an intake row written after finalize was frozen anyway, so a drifted "
        "target is now recorded as the one the report was rendered against"
    )
