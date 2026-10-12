"""Migration 0067 and its models: findings reports, recommendations and
integration runs (N4, design note rev 4, section 5).

Additive: three new tables, no existing row touched. The downgrade REFUSES
while any of them holds a row.

The constraint tests write by raw SQL with SQLite foreign keys switched ON:
this is the world the database enforces, not what the app's writers happen to
send. The expected constraint names and stored spellings are typed here, from
the design note and the repo's enum convention, never imported from the code
under test.
"""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session

from app.models import (
    AiRun,
    Artifact,
    ArtifactOrigin,
    Client,
    Deliverable,
    FindingsReport,
    FindingsReportStatus,
    IntegrationRun,
    LLMCallMode,
    Recommendation,
    RecommendationEffectStatus,
    RecommendationKind,
    RecommendationScope,
    RecommendationStatus,
    Service,
    ServiceKind,
    User,
    UserRole,
)

pytestmark = pytest.mark.unit

NEW_TABLES = {"findings_reports", "recommendations", "integration_runs"}
NOW = "2026-10-12 00:00:00"


def _cfg(url: str) -> Config:
    api_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _engine(url: str) -> sa.Engine:
    engine = sa.create_engine(url, future=True)

    @sa.event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record) -> None:  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


#: One database migrated to 0066, built once per session and copied per test:
#: the full chain is slow, and every test here starts from the same world.
_TEMPLATE: dict[str, Path] = {}


@pytest.fixture(autouse=True)
def _template_0066(tmp_path_factory) -> None:
    if "0066" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0067") / "0066.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0066")
        _TEMPLATE["0066"] = path


def _at(tmp_path, name: str, revision: str = "0067") -> tuple[str, sa.Engine]:
    target = tmp_path / name
    shutil.copyfile(_TEMPLATE["0066"], target)
    url = f"sqlite:///{target}"
    command.upgrade(_cfg(url), revision)
    return url, _engine(url)


def _tables(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _parents(engine: sa.Engine) -> dict[str, str]:
    """A client, a user, a service and a deliverable, by raw SQL."""
    ids = {k: str(uuid.uuid4()) for k in ("client", "user", "service", "deliverable")}
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO client (id, created_at, updated_at) VALUES (:id, :n, :n)"),
            {"id": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, role, timezone, is_active, "
                "mfa_enrolled, failed_login_count, created_at, updated_at) VALUES "
                "(:id, :e, 'x', 'ADMIN', 'UTC', 1, 0, 0, :n, :n)"
            ),
            {"id": ids["user"], "e": f"{ids['user']}@kentro.example", "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO services (id, kind, status, title, opened_by, client_id, "
                "created_at, updated_at) VALUES "
                "(:id, 'NIST_CSF', 'DRAFT', 'CSF', :u, :c, :n, :n)"
            ),
            {"id": ids["service"], "u": ids["user"], "c": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO deliverables (id, service_id, title, version, created_at, "
                "updated_at) VALUES (:id, :s, 'D', 1, :n, :n)"
            ),
            {"id": ids["deliverable"], "s": ids["service"], "n": NOW},
        )
    return ids


_REC_INSERT = sa.text(
    "INSERT INTO recommendations (id, scope, client_id, service_id, deliverable_id, kind, "
    "text, origin, status, created_at, updated_at) VALUES "
    "(:id, :scope, :c, :s, :d, 'GENERAL', 'Do the thing.', :origin, 'PENDING', :n, :n)"
)


def _rec(
    conn, p: dict[str, str], scope: str, *, service: bool, deliverable: bool, origin: str = "ai"
) -> None:
    conn.execute(
        _REC_INSERT,
        {
            "id": str(uuid.uuid4()),
            "scope": scope,
            "c": p["client"],
            "s": p["service"] if service else None,
            "d": p["deliverable"] if deliverable else None,
            "origin": origin,
            "n": NOW,
        },
    )


# --- upgrade / downgrade --------------------------------------------------------


def test_0067_creates_the_three_tables_and_drops_them_when_empty(tmp_path) -> None:
    url, engine = _at(tmp_path, "m0067.db", "0066")
    assert not NEW_TABLES & _tables(engine)

    command.upgrade(_cfg(url), "0067")
    assert _tables(engine) >= NEW_TABLES
    inspector = sa.inspect(engine)
    rec_columns = {c["name"] for c in inspector.get_columns("recommendations")}
    assert {
        "scope",
        "client_id",
        "service_id",
        "deliverable_id",
        "integration_run_id",
        "finding_id",
        "kind",
        "text",
        "rationale",
        "tool",
        "axis",
        "configuration",
        "expected_effect",
        "effect_status",
        "priority_inputs",
        "priority_rank",
        "origin",
        "status",
        "reviewed_by",
        "reviewed_at",
        "ai_run_id",
    } <= rec_columns
    # Section 5: "No artifact column."
    assert not {c for c in rec_columns if "artifact" in c}, rec_columns
    report_columns = {c["name"] for c in inspector.get_columns("findings_reports")}
    assert {
        "service_id",
        "deliverable_id",
        "sections",
        "cross_facts",
        "prompt_version",
        "ai_run_id",
        "status",
        "approved_by",
        "approved_at",
        "pdf_artifact_id",
        "docx_artifact_id",
    } <= report_columns
    run_columns = {c["name"] for c in inspector.get_columns("integration_runs")}
    assert {
        "client_id",
        "created_at",
        "created_by",
        "inputs",
        "crosswalks",
        "findings",
        "ai_run_id",
    } <= run_columns

    command.downgrade(_cfg(url), "0066")
    assert not NEW_TABLES & _tables(engine)
    command.upgrade(_cfg(url), "0067")
    assert _tables(engine) >= NEW_TABLES


@pytest.mark.parametrize("table", ["findings_reports", "recommendations", "integration_runs"])
def test_0067_downgrade_refuses_while_any_table_holds_a_row(tmp_path, table) -> None:
    url, engine = _at(tmp_path, f"m0067-refuse-{table}.db")
    p = _parents(engine)
    with engine.begin() as conn:
        if table == "findings_reports":
            conn.execute(
                sa.text(
                    "INSERT INTO findings_reports (id, service_id, deliverable_id, status, "
                    "created_at, updated_at) VALUES (:id, :s, :d, 'DRAFT', :n, :n)"
                ),
                {"id": str(uuid.uuid4()), "s": p["service"], "d": p["deliverable"], "n": NOW},
            )
        elif table == "recommendations":
            _rec(conn, p, "SERVICE", service=True, deliverable=True)
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO integration_runs (id, client_id, created_at, updated_at) "
                    "VALUES (:id, :c, :n, :n)"
                ),
                {"id": str(uuid.uuid4()), "c": p["client"], "n": NOW},
            )

    with pytest.raises(
        RuntimeError, match=rf"Refusing to downgrade 0067: rows exist \(1 in {table}\)"
    ):
        command.downgrade(_cfg(url), "0066")
    assert _tables(engine) >= NEW_TABLES


# --- the scope CHECKs -----------------------------------------------------------


def test_service_and_client_scope_rows_that_follow_the_rule_are_accepted(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0067-scope-ok.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _rec(conn, p, "SERVICE", service=True, deliverable=True)
        _rec(conn, p, "SERVICE", service=True, deliverable=False)
        _rec(conn, p, "CLIENT", service=False, deliverable=False)
        n = conn.execute(sa.text("SELECT COUNT(*) FROM recommendations")).scalar_one()
    assert n == 3


@pytest.mark.parametrize(
    ("scope", "service", "deliverable", "constraint"),
    [
        ("CLIENT", True, False, "ck_recommendations_client_scope_has_no_service"),
        ("CLIENT", False, True, "ck_recommendations_client_scope_has_no_service"),
        ("CLIENT", True, True, "ck_recommendations_client_scope_has_no_service"),
        ("SERVICE", False, False, "ck_recommendations_service_scope_has_service"),
        ("SERVICE", False, True, "ck_recommendations_service_scope_has_service"),
    ],
)
def test_scope_check_refuses(tmp_path, scope, service, deliverable, constraint) -> None:
    _, engine = _at(tmp_path, f"m0067-scope-{scope}-{service}-{deliverable}.db")
    p = _parents(engine)
    with pytest.raises(sa.exc.IntegrityError, match=constraint), engine.begin() as conn:
        _rec(conn, p, scope, service=service, deliverable=deliverable)


# --- the origin vocabulary (ruling #736 6128447366, (d)) -------------------------


@pytest.mark.parametrize("origin", ["ai", "edited", "consultant"])
def test_origin_accepts_the_ruled_vocabulary(tmp_path, origin) -> None:
    _, engine = _at(tmp_path, f"m0067-origin-{origin}.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _rec(conn, p, "CLIENT", service=False, deliverable=False, origin=origin)
        stored = conn.execute(sa.text("SELECT origin FROM recommendations")).scalar_one()
    assert stored == origin


@pytest.mark.parametrize("origin", ["AI", "human", "", "Edited"])
def test_origin_check_refuses_anything_else(tmp_path, origin) -> None:
    _, engine = _at(tmp_path, f"m0067-origin-bad-{origin or 'empty'}.db")
    p = _parents(engine)
    with (
        pytest.raises(sa.exc.IntegrityError, match="ck_recommendations_origin_vocabulary"),
        engine.begin() as conn,
    ):
        _rec(conn, p, "CLIENT", service=False, deliverable=False, origin=origin)


# --- NOT NULL ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("recommendations", "scope"),
        ("recommendations", "client_id"),
        ("recommendations", "kind"),
        ("recommendations", "text"),
        ("recommendations", "origin"),
        ("recommendations", "status"),
        ("recommendations", "effect_status"),
        ("findings_reports", "service_id"),
        ("findings_reports", "deliverable_id"),
        ("findings_reports", "status"),
        ("integration_runs", "client_id"),
    ],
)
def test_required_column_refuses_null(tmp_path, table, column) -> None:
    _, engine = _at(tmp_path, f"m0067-nn-{table}-{column}.db")
    p = _parents(engine)
    full = {
        "recommendations": {
            "scope": "SERVICE",
            "client_id": p["client"],
            "service_id": p["service"],
            "kind": "GENERAL",
            "text": "Do the thing.",
            "origin": "ai",
            "status": "PENDING",
        },
        "findings_reports": {
            "service_id": p["service"],
            "deliverable_id": p["deliverable"],
            "status": "DRAFT",
        },
        "integration_runs": {"client_id": p["client"]},
    }[table]
    values = {"id": str(uuid.uuid4()), "created_at": NOW, "updated_at": NOW, **full}
    # Positive first: the full row is accepted.
    with engine.begin() as conn:
        conn.execute(sa.table(table, *map(sa.column, values)).insert().values(**values))
    values = {**values, "id": str(uuid.uuid4()), column: None}
    with pytest.raises(sa.exc.IntegrityError, match="NOT NULL"), engine.begin() as conn:
        conn.execute(sa.table(table, *map(sa.column, values)).insert().values(**values))


# --- foreign keys -------------------------------------------------------------------


def _fks(engine: sa.Engine, table: str) -> dict[str, tuple[str, str | None]]:
    return {
        fk["constrained_columns"][0]: (fk["referred_table"], fk["options"].get("ondelete"))
        for fk in sa.inspect(engine).get_foreign_keys(table)
    }


def test_foreign_keys_and_their_delete_rules(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0067-fk.db")
    assert _fks(engine, "findings_reports") == {
        "service_id": ("services", "CASCADE"),
        "deliverable_id": ("deliverables", "CASCADE"),
        "ai_run_id": ("ai_runs", "SET NULL"),
        "approved_by": ("users", "SET NULL"),
        "pdf_artifact_id": ("artifacts", "SET NULL"),
        "docx_artifact_id": ("artifacts", "SET NULL"),
    }
    assert _fks(engine, "recommendations") == {
        "client_id": ("client", "CASCADE"),
        "service_id": ("services", "CASCADE"),
        "deliverable_id": ("deliverables", "CASCADE"),
        "integration_run_id": ("integration_runs", "SET NULL"),
        "reviewed_by": ("users", "SET NULL"),
        "ai_run_id": ("ai_runs", "SET NULL"),
    }
    assert _fks(engine, "integration_runs") == {
        "client_id": ("client", "CASCADE"),
        "created_by": ("users", "SET NULL"),
        "ai_run_id": ("ai_runs", "SET NULL"),
    }


def test_a_report_without_a_real_deliverable_is_refused(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0067-fk-refuse.db")
    p = _parents(engine)
    insert = sa.text(
        "INSERT INTO findings_reports (id, service_id, deliverable_id, status, created_at, "
        "updated_at) VALUES (:id, :s, :d, 'DRAFT', :n, :n)"
    )
    with engine.begin() as conn:
        conn.execute(
            insert, {"id": str(uuid.uuid4()), "s": p["service"], "d": p["deliverable"], "n": NOW}
        )
    with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"), engine.begin() as conn:
        conn.execute(
            insert, {"id": str(uuid.uuid4()), "s": p["service"], "d": str(uuid.uuid4()), "n": NOW}
        )


def test_deleting_the_deliverable_takes_its_report_and_service_recommendations(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0067-cascade.db")
    p = _parents(engine)
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO findings_reports (id, service_id, deliverable_id, status, "
                "created_at, updated_at) VALUES (:id, :s, :d, 'DRAFT', :n, :n)"
            ),
            {"id": str(uuid.uuid4()), "s": p["service"], "d": p["deliverable"], "n": NOW},
        )
        _rec(conn, p, "SERVICE", service=True, deliverable=True)
        _rec(conn, p, "CLIENT", service=False, deliverable=False)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM deliverables WHERE id = :d"), {"d": p["deliverable"]})
        reports = conn.execute(sa.text("SELECT COUNT(*) FROM findings_reports")).scalar_one()
        scopes = conn.execute(sa.text("SELECT scope FROM recommendations")).scalars().all()
    assert reports == 0
    assert scopes == ["CLIENT"]


# --- ORM round trip ---------------------------------------------------------------


def test_each_model_round_trips_and_stores_member_names(tmp_path) -> None:
    url, engine = _at(tmp_path, "m0067-orm.db")
    with Session(engine) as db:
        client = Client()
        db.add(client)
        db.flush()
        user = User(email="a@kentro.example", password_hash="x", role=UserRole.ADMIN)
        db.add(user)
        db.flush()
        service = Service(
            kind=ServiceKind.NIST_CSF, title="CSF", client_id=client.id, opened_by=user.id
        )
        db.add(service)
        db.flush()
        pdf = Artifact(
            client_id=client.id,
            title="r.pdf",
            file_storage_key="k",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="0" * 64,
            origin=ArtifactOrigin.AUTOMATED_DRAFT,
            uploaded_by=user.id,
        )
        deliverable = Deliverable(service_id=service.id, title="D", version=1)
        db.add_all([pdf, deliverable])
        db.flush()
        run = AiRun(
            client_id=client.id,
            service_id=service.id,
            purpose="report.generate",
            subject_id=deliverable.id,
            mode=LLMCallMode.FIXTURE,
            boot_id="b",
            requested_by=user.id,
            deadline_at=datetime.now(UTC),
        )
        db.add(run)
        db.flush()
        integration = IntegrationRun(
            client_id=client.id,
            created_by=user.id,
            inputs={"nist_csf": {"not_included": "not approved yet"}},
            crosswalks=[{"id": "X1", "version": "16.1", "sha256": "ab"}],
            findings=[],
            ai_run_id=run.id,
        )
        db.add(integration)
        db.flush()
        report = FindingsReport(
            service_id=service.id,
            deliverable_id=deliverable.id,
            sections={"F1": {"text": "t", "origin": "ai", "refused_numbers": []}},
            cross_facts=[{"text": "f", "integration_run_id": str(integration.id)}],
            prompt_version="p1-r4",
            ai_run_id=run.id,
            pdf_artifact_id=pdf.id,
        )
        service_rec = Recommendation(
            scope=RecommendationScope.SERVICE,
            client_id=client.id,
            service_id=service.id,
            deliverable_id=deliverable.id,
            finding_id="F1",
            kind=RecommendationKind.OWNED_TOOL,
            text="Turn on the feature.",
            rationale="Because.",
            tool="Tool A",
            axis="detect",
            configuration="setting",
            expected_effect=[{"type": "technique_covered", "code": "T1003", "axis": "detect"}],
            effect_status=RecommendationEffectStatus.SUGGESTED,
            priority_inputs={"severity": "High", "corroborated_by": "not checked"},
            priority_rank=1,
            ai_run_id=run.id,
        )
        client_rec = Recommendation(
            scope=RecommendationScope.CLIENT,
            client_id=client.id,
            integration_run_id=integration.id,
            kind=RecommendationKind.CROSS_SERVICE,
            text="Across services.",
            origin="consultant",
        )
        db.add_all([report, service_rec, client_rec])
        db.commit()
        ids = (report.id, service_rec.id, client_rec.id, integration.id)

    with Session(_engine(url)) as db:
        report = db.get(FindingsReport, ids[0])
        assert report.status is FindingsReportStatus.DRAFT
        assert report.sections == {"F1": {"text": "t", "origin": "ai", "refused_numbers": []}}
        assert report.prompt_version == "p1-r4"
        assert report.docx_artifact_id is None
        rec = db.get(Recommendation, ids[1])
        assert rec.scope is RecommendationScope.SERVICE
        assert rec.kind is RecommendationKind.OWNED_TOOL
        assert rec.status is RecommendationStatus.PENDING
        assert rec.origin == "ai"
        assert rec.effect_status is RecommendationEffectStatus.SUGGESTED
        assert rec.expected_effect == [
            {"type": "technique_covered", "code": "T1003", "axis": "detect"}
        ]
        assert rec.priority_inputs == {"severity": "High", "corroborated_by": "not checked"}
        assert rec.priority_rank == 1
        crec = db.get(Recommendation, ids[2])
        assert crec.service_id is None and crec.deliverable_id is None
        assert crec.integration_run_id == ids[3]
        # NULL is "not recorded", and reads back as None, never [] or {}.
        assert crec.expected_effect is None and crec.priority_inputs is None
        # Missing data is UNCONFIRMED: an effect nobody has confirmed reads
        # SUGGESTED, never NULL.
        assert crec.effect_status is RecommendationEffectStatus.SUGGESTED
        run = db.get(IntegrationRun, ids[3])
        assert run.inputs == {"nist_csf": {"not_included": "not approved yet"}}
        assert run.findings == []

    with engine.connect() as conn:
        stored = conn.execute(
            sa.text("SELECT scope, kind, status, effect_status FROM recommendations ORDER BY scope")
        ).all()
        report_status = conn.execute(sa.text("SELECT status FROM findings_reports")).scalar_one()
    # The repo's enum convention: the stored value is the member NAME.
    assert [tuple(r) for r in stored] == [
        ("CLIENT", "CROSS_SERVICE", "PENDING", "SUGGESTED"),
        ("SERVICE", "OWNED_TOOL", "PENDING", "SUGGESTED"),
    ]
    assert report_status == "DRAFT"


def test_an_effect_status_left_unset_is_stored_as_suggested(tmp_path) -> None:
    """CLAUDE.md: missing data defaults to UNCONFIRMED. A writer that never
    names `effect_status` (raw SQL here, so it is the DATABASE default that is
    tested, not only the model's) gets SUGGESTED, the member NAME."""
    url, engine = _at(tmp_path, "m0067-effect-default.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _rec(conn, p, "CLIENT", service=False, deliverable=False)
        stored = conn.execute(sa.text("SELECT effect_status FROM recommendations")).scalar_one()
    assert stored == "SUGGESTED"
    # And through the model (its Python-side default). Foreign keys OFF for this
    # half: the parent was written by raw SQL, whose UUID spelling the ORM's
    # does not match on SQLite; this is about the default, not the FK.
    with Session(sa.create_engine(url, future=True)) as db:
        db.add(
            Recommendation(
                scope=RecommendationScope.CLIENT, client_id=uuid.UUID(p["client"]), text="orm"
            )
        )
        db.commit()
    with engine.connect() as conn:
        values = conn.execute(sa.text("SELECT effect_status FROM recommendations")).scalars().all()
    assert values == ["SUGGESTED", "SUGGESTED"]


def test_the_orm_refuses_a_scope_outside_the_vocabulary(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0067-enum.db")
    with Session(engine) as db:
        db.add(
            Recommendation(
                scope="EVERYONE",
                client_id=uuid.uuid4(),
                kind=RecommendationKind.GENERAL,
                text="x",
            )
        )
        with pytest.raises(sa.exc.StatementError, match="EVERYONE"):
            db.flush()


def test_not_recorded_json_is_sql_null_only_when_unset_or_written_as_sa_null(tmp_path) -> None:
    """The models' "NULL is not recorded" needs SQL NULL. A plain `JSON` column
    writes Python None as the JSON text 'null' (`risk_register.py`, 655184cc
    F3), so a writer that means "not recorded" leaves the attribute unset or
    writes `sqlalchemy.null()`, never None."""
    _, engine = _at(tmp_path, "m0067-json-null.db")
    with Session(engine) as db:
        client = Client()
        db.add(client)
        db.flush()
        rows = {
            "unset": Recommendation(
                scope=RecommendationScope.CLIENT, client_id=client.id, text="unset"
            ),
            "sa_null": Recommendation(
                scope=RecommendationScope.CLIENT,
                client_id=client.id,
                text="sa_null",
                expected_effect=sa.null(),
                priority_inputs=sa.null(),
            ),
            "none": Recommendation(
                scope=RecommendationScope.CLIENT,
                client_id=client.id,
                text="none",
                expected_effect=None,
                priority_inputs=None,
            ),
        }
        db.add_all(rows.values())
        db.commit()
    with engine.connect() as conn:
        got = {
            text: (bool(effect_null), bool(inputs_null))
            for text, effect_null, inputs_null in conn.execute(
                sa.text(
                    "SELECT text, expected_effect IS NULL, priority_inputs IS NULL "
                    "FROM recommendations"
                )
            )
        }
    assert got == {
        "unset": (True, True),
        "sa_null": (True, True),
        # The trap the docstrings warn about: the JSON text 'null', not NULL.
        "none": (False, False),
    }


def _sql(text: str) -> str:
    return " ".join(str(text).split())


def test_the_model_declares_the_same_checks_the_migration_creates(tmp_path) -> None:
    """Names AND the SQL each CHECK enforces, whitespace-normalised: a model and
    a migration that agree on a name but not on the predicate would pass a
    name-only comparison."""
    _, engine = _at(tmp_path, "m0067-parity.db")
    created = {
        c["name"]: _sql(c["sqltext"])
        for c in sa.inspect(engine).get_check_constraints("recommendations")
    }
    declared = {
        c.name: _sql(c.sqltext)
        for c in Recommendation.__table__.constraints
        if isinstance(c, sa.CheckConstraint)
    }
    assert set(created) == {
        "ck_recommendations_client_scope_has_no_service",
        "ck_recommendations_service_scope_has_service",
        "ck_recommendations_origin_vocabulary",
    }
    # Positive first: each reflected predicate is a real, non-empty text.
    assert all(created.values()), created
    assert declared == created
