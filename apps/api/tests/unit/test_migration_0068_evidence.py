"""Migration 0068 and its models: the evidence fields on `artifacts`, the
`evidence_links` table, and `csf_dimension_scores.evidence_basis` (N5, design
note rev 4, sections 5 and 10.1).

Additive: nullable columns and one new table, plus ONE backfill -- Gene's Q9
grace, option A (#736 6126886407): `evidence_basis = MANUAL_TICK_FROZEN` on the
ticked rows of APPROVED and RELEASED CSF assessments, NULL everywhere else. The
downgrade REFUSES while any row records something 0068 added.

The constraint tests write by raw SQL with SQLite foreign keys switched ON.
The expected names, stored spellings and vocabularies are typed here from the
design note and the repo's enum convention, never imported from the code under
test.
"""

from __future__ import annotations

import io
import re
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
    Artifact,
    ArtifactDocStatus,
    ArtifactOrigin,
    Client,
    CsfAssessment,
    CsfAssessmentStatus,
    CsfDimensionScore,
    CsfEvidenceBasis,
    EvidenceLink,
    EvidenceLinkStatus,
    EvidenceTargetKind,
    Service,
    ServiceKind,
    User,
    UserRole,
)

pytestmark = pytest.mark.unit

API_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-10-12 00:00:00"
ARTIFACT_COLUMNS = {"description", "doc_status", "doc_status_set_by", "doc_status_set_at"}


def _cfg(url: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _engine(url: str) -> sa.Engine:
    engine = sa.create_engine(url, future=True)

    @sa.event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _record) -> None:  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


#: One database migrated to 0067, built once per session and copied per test.
_TEMPLATE: dict[str, Path] = {}


@pytest.fixture(autouse=True)
def _template_0067(tmp_path_factory) -> None:
    if "0067" not in _TEMPLATE:
        path = tmp_path_factory.mktemp("tpl0068") / "0067.db"
        command.upgrade(_cfg(f"sqlite:///{path}"), "0067")
        _TEMPLATE["0067"] = path


def _at(tmp_path, name: str, revision: str = "0068") -> tuple[str, sa.Engine]:
    target = tmp_path / name
    shutil.copyfile(_TEMPLATE["0067"], target)
    url = f"sqlite:///{target}"
    command.upgrade(_cfg(url), revision)
    return url, _engine(url)


def _columns(engine: sa.Engine, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


def _parents(engine: sa.Engine) -> dict[str, str]:
    """A client, a user, an artifact and a Working Profile row, by raw SQL, in
    the shape every pre-0068 row has: none of the 0068 columns named."""
    ids = {
        k: str(uuid.uuid4())
        for k in ("client", "user", "service", "artifact", "assessment", "score")
    }
    with engine.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO client (id, created_at, updated_at) VALUES (:id, :n, :n)"),
            {"id": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, role, timezone, is_active, "
                "mfa_enrolled, failed_login_count, created_at, updated_at) VALUES "
                "(:id, :e, 'x', 'CLIENT', 'UTC', 1, 0, 0, :n, :n)"
            ),
            {"id": ids["user"], "e": f"{ids['user']}@atlas.example", "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO artifacts (id, client_id, title, file_storage_key, mime_type, "
                "size_bytes, sha256, origin, stage, uploaded_by, uploaded_at, notes, "
                "created_at, updated_at) VALUES (:id, :c, 'policy.pdf', 'k/policy.pdf', "
                "'application/pdf', 1234, :sha, 'CLIENT_UPLOAD', 'intake', :u, :n, "
                "'older note', :n, :n)"
            ),
            {
                "id": ids["artifact"],
                "c": ids["client"],
                "sha": "a" * 64,
                "u": ids["user"],
                "n": NOW,
            },
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
                "INSERT INTO csf_assessments (id, service_id, client_id, version, status, "
                "documents_stale, created_at, updated_at) VALUES "
                "(:id, :s, :c, 1, 'DRAFT', 0, :n, :n)"
            ),
            {"id": ids["assessment"], "s": ids["service"], "c": ids["client"], "n": NOW},
        )
        conn.execute(
            sa.text(
                "INSERT INTO csf_dimension_scores (id, assessment_id, client_id, tier, "
                "subcategory_code, governance, policy, implementation, monitoring, "
                "improvement, in_scope, has_evidence, evidence_artifact_id, locked, "
                "answer_source, created_at, updated_at) VALUES (:id, :a, :c, 'moderate', "
                "'GV.OC-01', 2, 1, 2, 0, 1, 1, 1, :art, 0, 'consultant', :n, :n)"
            ),
            {
                "id": ids["score"],
                "a": ids["assessment"],
                "c": ids["client"],
                "art": ids["artifact"],
                "n": NOW,
            },
        )
    return ids


_LINK = sa.text(
    "INSERT INTO evidence_links (id, client_id, artifact_id, assessment_id, target_kind, "
    "target_code, tier, supports, status, origin, created_at, updated_at) VALUES "
    "(:id, :c, :art, :a, :kind, :code, :tier, '[]', 'SUGGESTED', 'ai', :n, :n)"
)


def _link(conn, p: dict[str, str], kind: str, code: str, tier: str | None, **over: str) -> None:
    conn.execute(
        _LINK,
        {
            "id": str(uuid.uuid4()),
            "c": p["client"],
            "art": over.get("artifact", p["artifact"]),
            "a": over.get("assessment", p["assessment"]),
            "kind": kind,
            "code": code,
            "tier": tier,
            "n": NOW,
        },
    )


# --- upgrade / downgrade ------------------------------------------------------------


def test_0068_adds_its_columns_and_table_and_removes_them_when_empty(tmp_path) -> None:
    url, engine = _at(tmp_path, "m0068.db", "0067")
    assert not ARTIFACT_COLUMNS & _columns(engine, "artifacts")
    assert "evidence_basis" not in _columns(engine, "csf_dimension_scores")
    assert "evidence_links" not in sa.inspect(engine).get_table_names()

    command.upgrade(_cfg(url), "0068")
    assert _columns(engine, "artifacts") >= ARTIFACT_COLUMNS
    assert "evidence_basis" in _columns(engine, "csf_dimension_scores")
    assert _columns(engine, "evidence_links") >= {
        "client_id",
        "artifact_id",
        "assessment_id",
        "target_kind",
        "target_code",
        "tier",
        "supports",
        "status",
        "origin",
        "suggested_by_run_id",
        "quote",
        "confirmed_by",
        "confirmed_at",
    }
    nullable = {c["name"]: c["nullable"] for c in sa.inspect(engine).get_columns("artifacts")}
    assert all(nullable[c] for c in ARTIFACT_COLUMNS), nullable
    basis = next(
        c
        for c in sa.inspect(engine).get_columns("csf_dimension_scores")
        if c["name"] == "evidence_basis"
    )
    assert basis["nullable"] is True
    # Wide enough for the stored NAME `MANUAL_TICK_FROZEN` (18): SQLite ignores
    # a VARCHAR length, Postgres refuses the write.
    assert basis["type"].length >= len("MANUAL_TICK_FROZEN"), basis["type"]

    command.downgrade(_cfg(url), "0067")
    assert not ARTIFACT_COLUMNS & _columns(engine, "artifacts")
    assert "evidence_basis" not in _columns(engine, "csf_dimension_scores")
    assert "evidence_links" not in sa.inspect(engine).get_table_names()
    command.upgrade(_cfg(url), "0068")
    assert _columns(engine, "artifacts") >= ARTIFACT_COLUMNS


def test_a_pre_0068_artifact_and_profile_row_read_unchanged(tmp_path) -> None:
    url, engine = _at(tmp_path, "m0068-older.db", "0067")
    p = _parents(engine)
    with engine.connect() as conn:
        before_art = conn.execute(sa.text("SELECT * FROM artifacts")).mappings().one()
        before_score = conn.execute(sa.text("SELECT * FROM csf_dimension_scores")).mappings().one()

    command.upgrade(_cfg(url), "0068")
    with engine.connect() as conn:
        after_art = conn.execute(sa.text("SELECT * FROM artifacts")).mappings().one()
        after_score = conn.execute(sa.text("SELECT * FROM csf_dimension_scores")).mappings().one()
    # Every column the row had is byte-identical, and every new one is NULL:
    # the row is ticked but its assessment is a DRAFT, so it is not frozen.
    assert {k: after_art[k] for k in before_art} == dict(before_art)
    assert {k: after_art[k] for k in ARTIFACT_COLUMNS} == dict.fromkeys(ARTIFACT_COLUMNS)
    assert {k: after_score[k] for k in before_score} == dict(before_score)
    assert after_score["evidence_basis"] is None

    # And through the models the app uses, undeferring the 0068 columns the
    # way a reader that renders them must (the rows were written by raw SQL,
    # whose UUID spelling a deferred per-row load by primary key would miss).
    with Session(_engine(url)) as db:
        art = db.execute(
            sa.select(Artifact).options(sa.orm.undefer_group("evidence_intake"))
        ).scalar_one()
        assert str(art.id) == p["artifact"]
        assert art.title == "policy.pdf"
        assert art.origin is ArtifactOrigin.CLIENT_UPLOAD
        assert art.notes == "older note"
        assert art.description is None
        assert art.doc_status is None
        assert art.doc_status_set_by is None and art.doc_status_set_at is None
        score = db.execute(
            sa.select(CsfDimensionScore).options(sa.orm.undefer_group("evidence_basis"))
        ).scalar_one()
        assert (score.governance, score.policy, score.implementation) == (2, 1, 2)
        assert score.has_evidence is True
        assert str(score.evidence_artifact_id) == p["artifact"]
        assert score.evidence_basis is None


def _seed_at_0066(tmp_path, name: str, statuses: set[str]) -> tuple[str, sa.Engine]:
    """At 0066, through the ORM: one CSF assessment per status, each with a
    ticked (`GV.OC-01`) and an unticked (`GV.OC-02`) Working Profile row, and
    one artifact."""
    url = f"sqlite:///{tmp_path / name}"
    command.upgrade(_cfg(url), "0066")
    engine = sa.create_engine(url, future=True)
    with Session(engine) as db:
        client = Client()
        db.add(client)
        db.flush()
        user = User(email="a@kentro.example", password_hash="x", role=UserRole.ADMIN)
        db.add(user)
        db.flush()
        db.add(
            Artifact(
                client_id=client.id,
                title="policy.pdf",
                file_storage_key="k",
                mime_type="application/pdf",
                size_bytes=1,
                sha256="0" * 64,
                origin=ArtifactOrigin.CLIENT_UPLOAD,
                uploaded_by=user.id,
            )
        )
        for status in sorted(statuses):
            service = Service(
                kind=ServiceKind.NIST_CSF, title=status, client_id=client.id, opened_by=user.id
            )
            db.add(service)
            db.flush()
            assessment = CsfAssessment(
                service_id=service.id, client_id=client.id, status=CsfAssessmentStatus[status]
            )
            db.add(assessment)
            db.flush()
            for ticked in (True, False):
                db.add(
                    CsfDimensionScore(
                        assessment_id=assessment.id,
                        client_id=client.id,
                        tier="moderate",
                        subcategory_code="GV.OC-01" if ticked else "GV.OC-02",
                        has_evidence=ticked,
                    )
                )
        db.commit()
    return url, engine


#: Q9 option A (#736 6126886407), typed from the ruling: frozen exactly when
#: the row is ticked AND its assessment is APPROVED or RELEASED.
_FREEZES = {
    ("DRAFT", True): None,
    ("DRAFT", False): None,
    ("SUBMITTED", True): None,
    ("SUBMITTED", False): None,
    ("APPROVED", True): "MANUAL_TICK_FROZEN",
    ("APPROVED", False): None,
    ("RELEASED", True): "MANUAL_TICK_FROZEN",
    ("RELEASED", False): None,
    ("DISCARDED", True): None,
    ("DISCARDED", False): None,
}


def test_upgrade_from_0066_freezes_only_ticked_rows_on_approved_and_released(
    tmp_path, capsys
) -> None:
    """Seeded through the ORM at 0066, so the stored status spelling is the one
    production writes (0045 froze nothing once because its fixture typed
    `'approved'` by hand)."""
    url, engine = _seed_at_0066(tmp_path, "m0068-backfill.db", {s for s, _ in _FREEZES})
    with engine.connect() as conn:
        stored = set(conn.execute(sa.text("SELECT status FROM csf_assessments")).scalars())
    # Positive first: the fixture wrote the spelling the migration must match.
    assert stored == {s for s, _ in _FREEZES}, stored

    capsys.readouterr()
    command.upgrade(_cfg(url), "0068")
    assert "[0068] froze 2 manually ticked Working Profile row(s)" in capsys.readouterr().out

    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT a.status, s.has_evidence, s.evidence_basis FROM csf_dimension_scores s "
                "JOIN csf_assessments a ON a.id = s.assessment_id"
            )
        ).all()
    got = {(status, bool(ticked)): basis for status, ticked, basis in rows}
    assert len(rows) == len(_FREEZES)
    assert got == _FREEZES

    # And the downgrade refuses, naming the REAL reason when only the backfill
    # blocks it: a re-upgrade would re-freeze against later statuses.
    with pytest.raises(RuntimeError) as refused:
        command.downgrade(_cfg(url), "0067")
    message = str(refused.value)
    assert message.startswith(
        "Refusing to downgrade 0068: 2 Working Profile rows frozen by this migration's backfill."
    ), message
    assert "a re-upgrade would re-freeze them against the statuses at that later time" in message
    assert "Clearing before a downgrade" in message
    assert "what a client said" not in message, message


def test_the_backfill_matches_status_case_insensitively(tmp_path, capsys) -> None:
    """A pre-existing database can hold a status in another case (0009's
    server default is lowercase `'draft'`); written by SQL, as such a row
    would have been."""
    url, engine = _seed_at_0066(tmp_path, "m0068-case.db", {"APPROVED", "RELEASED", "DRAFT"})
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE csf_assessments SET status = 'approved' WHERE status = 'APPROVED'")
        )
        conn.execute(
            sa.text("UPDATE csf_assessments SET status = 'Released' WHERE status = 'RELEASED'")
        )
        conn.execute(sa.text("UPDATE csf_assessments SET status = 'draft' WHERE status = 'DRAFT'"))
        # Positive first: the odd spellings really are what is stored.
        stored = set(conn.execute(sa.text("SELECT status FROM csf_assessments")).scalars())
    assert stored == {"approved", "Released", "draft"}

    capsys.readouterr()
    command.upgrade(_cfg(url), "0068")
    assert "[0068] froze 2 manually ticked Working Profile row(s)" in capsys.readouterr().out
    with engine.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT a.status, s.has_evidence, s.evidence_basis FROM csf_dimension_scores s "
                "JOIN csf_assessments a ON a.id = s.assessment_id"
            )
        ).all()
    assert {(status, bool(t)): basis for status, t, basis in rows} == {
        ("approved", True): "MANUAL_TICK_FROZEN",
        ("approved", False): None,
        ("Released", True): "MANUAL_TICK_FROZEN",
        ("Released", False): None,
        ("draft", True): None,
        ("draft", False): None,
    }


def test_the_documented_clearing_procedure_lets_the_downgrade_through(tmp_path) -> None:
    """Ruling #736 6128447366 (c): the docstring states what to run before a
    downgrade. Run exactly those statements, read from the docstring."""
    url, engine = _seed_at_0066(tmp_path, "m0068-clear.db", {"APPROVED", "DRAFT"})
    command.upgrade(_cfg(url), "0068")
    with engine.begin() as conn:
        conn.execute(sa.text("UPDATE artifacts SET description = 'x', doc_status = 'DRAFT'"))
        frozen = conn.execute(
            sa.text("SELECT COUNT(*) FROM csf_dimension_scores WHERE evidence_basis IS NOT NULL")
        ).scalar_one()
    assert frozen == 1
    with pytest.raises(RuntimeError, match="Refusing to downgrade 0068"):
        command.downgrade(_cfg(url), "0067")

    statements = _clearing_statements()
    # Asserted first: a section the extractor could not find would pass the rest.
    assert len(statements) == 3, statements
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))
    command.downgrade(_cfg(url), "0067")
    assert "evidence_links" not in sa.inspect(engine).get_table_names()


def _clearing_statements() -> list[str]:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_cfg("sqlite://")).get_revision("0068")
    doc = script.module.__doc__
    section = doc.split("## Clearing before a downgrade", 1)[1].split("\n## ", 1)[0]
    return [line.strip() for line in section.splitlines() if line.startswith("    ")]


# --- the migration as Postgres receives it (offline, postgresql dialect) ----------

_PG_SQL: dict[str, str] = {}


def _postgres_sql() -> str:
    if "sql" not in _PG_SQL:
        buf = io.StringIO()
        cfg = Config(str(API_ROOT / "alembic.ini"), output_buffer=buf)
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        cfg.set_main_option("sqlalchemy.url", "postgresql+psycopg://u:p@localhost/x")
        command.upgrade(cfg, "0067:0068", sql=True)
        _PG_SQL["sql"] = buf.getvalue()
    return _PG_SQL["sql"]


@pytest.mark.parametrize(
    ("index", "columns", "where"),
    [
        (
            "uq_evidence_links_untiered",
            "artifact_id, assessment_id, target_kind, target_code",
            "tier IS NULL",
        ),
        (
            "uq_evidence_links_tiered",
            "artifact_id, assessment_id, target_kind, target_code, tier",
            "tier IS NOT NULL",
        ),
    ],
)
def test_postgres_receives_both_unique_indexes_as_partial(index, columns, where) -> None:
    """SQLite is what CI's unit job runs; this is the migration's
    `postgresql_where`, which nothing else here exercises. Without it Postgres
    gets a plain UNIQUE, and one file linked to a CSF row at two tiers fails."""
    sql = _postgres_sql()
    assert "CREATE TABLE evidence_links" in sql  # positive first: it rendered 0068
    expected = f"CREATE UNIQUE INDEX {index} ON evidence_links ({columns}) WHERE {where};"
    assert expected in sql, [line for line in sql.splitlines() if index in line]


def test_offline_mode_emits_the_backfill_with_literal_statuses(capsys) -> None:
    _PG_SQL.clear()
    capsys.readouterr()
    sql = _postgres_sql()
    assert (
        "UPDATE csf_dimension_scores SET evidence_basis = 'MANUAL_TICK_FROZEN' "
        "WHERE has_evidence = true AND assessment_id IN "
        "(SELECT id FROM csf_assessments WHERE UPPER(status) IN ('APPROVED', 'RELEASED'));"
    ) in sql
    assert "[0068] offline mode: the MANUAL_TICK_FROZEN backfill is in the script" in (
        capsys.readouterr().out
    )


def test_the_models_still_insert_and_select_against_a_pre_0068_schema(tmp_path) -> None:
    """The migration tests that pin an older revision use these models. A new
    column named in an ORM SELECT or INSERT against a schema that lacks it
    breaks every one of them (0066's lesson): the columns are deferred and an
    unset one is left out of the INSERT."""
    url, fk_engine = _at(tmp_path, "m0068-compat.db", "0067")
    p = _parents(fk_engine)
    # Foreign keys OFF here: the parents were written by raw SQL, whose UUID
    # spelling the ORM's does not match on SQLite. This test is about which
    # COLUMNS the ORM names, and the FK behaviour has its own tests.
    engine = sa.create_engine(url, future=True)
    with Session(engine) as db:
        db.add(
            Artifact(
                client_id=uuid.UUID(p["client"]),
                title="second.pdf",
                file_storage_key="k2",
                mime_type="application/pdf",
                size_bytes=2,
                sha256="b" * 64,
                origin=ArtifactOrigin.CLIENT_UPLOAD,
                uploaded_by=uuid.UUID(p["user"]),
            )
        )
        db.add(
            CsfDimensionScore(
                assessment_id=uuid.UUID(p["assessment"]),
                client_id=uuid.UUID(p["client"]),
                tier="high",
                subcategory_code="GV.OC-02",
            )
        )
        db.commit()
    with Session(engine) as db:
        titles = sorted(db.execute(sa.select(Artifact.title)).scalars())
        assert titles == ["policy.pdf", "second.pdf"]
        assert len(db.execute(sa.select(Artifact)).scalars().all()) == 2
        codes = sorted(
            r.subcategory_code for r in db.execute(sa.select(CsfDimensionScore)).scalars()
        )
        assert codes == ["GV.OC-01", "GV.OC-02"]
    assert "evidence_basis" not in _columns(engine, "csf_dimension_scores")
    assert not ARTIFACT_COLUMNS & _columns(engine, "artifacts")


@pytest.mark.parametrize(
    ("what", "write", "message"),
    [
        ("link", "LINK", "1 evidence links"),
        ("description", "UPDATE artifacts SET description = 'x'", "1 artifacts with a"),
        ("doc_status", "UPDATE artifacts SET doc_status = 'DRAFT'", "1 artifacts with a"),
        (
            "doc_status_set_at",
            "UPDATE artifacts SET doc_status_set_at = '2026-10-12 00:00:00'",
            "1 artifacts with a",
        ),
        (
            "evidence_basis",
            "UPDATE csf_dimension_scores SET evidence_basis = 'LINKED'",
            "1 Working Profile rows with another evidence basis",
        ),
    ],
)
def test_0068_downgrade_refuses_while_anything_it_added_is_recorded(
    tmp_path, what, write, message
) -> None:
    url, engine = _at(tmp_path, f"m0068-refuse-{what}.db")
    p = _parents(engine)
    with engine.begin() as conn:
        if write == "LINK":
            _link(conn, p, "ZT_CAPABILITY", "IDE.01", None)
        else:
            conn.execute(sa.text(write))
    with pytest.raises(RuntimeError, match=f"Refusing to downgrade 0068: {message}"):
        command.downgrade(_cfg(url), "0067")
    assert "evidence_links" in sa.inspect(engine).get_table_names()


# --- the tier CHECK -----------------------------------------------------------------


def test_one_link_of_each_kind_in_the_right_shape_is_accepted(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-shape-ok.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _link(conn, p, "CSF_ROW", "GV.OC-01", "moderate")
        _link(conn, p, "ZT_CAPABILITY", "IDE.01", None)
        _link(conn, p, "ATTACK_TECHNIQUE", "T1003", None)
        n = conn.execute(sa.text("SELECT COUNT(*) FROM evidence_links")).scalar_one()
    assert n == 3


@pytest.mark.parametrize(
    ("kind", "code", "tier"),
    [
        ("CSF_ROW", "GV.OC-01", None),
        ("ZT_CAPABILITY", "IDE.01", "moderate"),
        ("ATTACK_TECHNIQUE", "T1003", "high"),
    ],
)
def test_tier_check_refuses(tmp_path, kind, code, tier) -> None:
    _, engine = _at(tmp_path, f"m0068-tier-{kind}.db")
    p = _parents(engine)
    with (
        pytest.raises(sa.exc.IntegrityError, match="ck_evidence_links_tier_iff_csf_row"),
        engine.begin() as conn,
    ):
        _link(conn, p, kind, code, tier)


@pytest.mark.parametrize("tier", ["High", "MODERATE", "medium", "", "Low "])
def test_tier_vocabulary_check_refuses_anything_but_the_stored_spelling(tmp_path, tier) -> None:
    """`csf_dimension_scores.tier` stores `high` / `moderate` / `low` (the
    `app.csf.playbook.Tier` values); a link's `tier` must match it exactly."""
    _, engine = _at(tmp_path, f"m0068-tiervocab-{tier.strip() or 'empty'}-{len(tier)}.db")
    p = _parents(engine)
    with (
        pytest.raises(sa.exc.IntegrityError, match="ck_evidence_links_tier_vocabulary"),
        engine.begin() as conn,
    ):
        _link(conn, p, "CSF_ROW", "GV.OC-01", tier)


def test_tier_vocabulary_accepts_each_stored_tier(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-tiervocab-ok.db")
    p = _parents(engine)
    with engine.begin() as conn:
        for tier in ("high", "moderate", "low"):
            _link(conn, p, "CSF_ROW", "GV.OC-01", tier)
        n = conn.execute(sa.text("SELECT COUNT(*) FROM evidence_links")).scalar_one()
    assert n == 3


# --- the partial unique indexes -------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "code", "tier"),
    [
        ("ZT_CAPABILITY", "IDE.01", None),
        ("ATTACK_TECHNIQUE", "T1003", None),
        ("CSF_ROW", "GV.OC-01", "moderate"),
    ],
)
def test_a_duplicate_link_is_refused(tmp_path, kind, code, tier) -> None:
    _, engine = _at(tmp_path, f"m0068-dup-{kind}.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _link(conn, p, kind, code, tier)
    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE"), engine.begin() as conn:
        _link(conn, p, kind, code, tier)


def test_links_differing_in_one_key_column_are_both_kept(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-distinct.db")
    p = _parents(engine)
    with engine.begin() as conn:
        _link(conn, p, "CSF_ROW", "GV.OC-01", "moderate")
        _link(conn, p, "CSF_ROW", "GV.OC-01", "high")
        _link(conn, p, "CSF_ROW", "GV.OC-02", "moderate")
        _link(conn, p, "ZT_CAPABILITY", "IDE.01", None)
        _link(conn, p, "ZT_CAPABILITY", "IDE.01", None, assessment=str(uuid.uuid4()))
        n = conn.execute(sa.text("SELECT COUNT(*) FROM evidence_links")).scalar_one()
    assert n == 5


def test_the_unique_indexes_are_partial_in_the_stored_schema(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-ddl.db")
    with engine.connect() as conn:
        ddl = dict(
            conn.execute(
                sa.text(
                    "SELECT name, sql FROM sqlite_master WHERE type = 'index' "
                    "AND tbl_name = 'evidence_links' AND name LIKE 'uq_%'"
                )
            ).all()
        )
    assert set(ddl) == {"uq_evidence_links_untiered", "uq_evidence_links_tiered"}
    assert re.search(r"WHERE\s+tier IS NULL\s*$", ddl["uq_evidence_links_untiered"]), ddl
    assert re.search(r"WHERE\s+tier IS NOT NULL\s*$", ddl["uq_evidence_links_tiered"]), ddl


# --- NOT NULL and foreign keys ----------------------------------------------------


@pytest.mark.parametrize(
    "column",
    ["client_id", "artifact_id", "assessment_id", "target_kind", "target_code", "status", "origin"],
)
def test_required_link_column_refuses_null(tmp_path, column) -> None:
    _, engine = _at(tmp_path, f"m0068-nn-{column}.db")
    p = _parents(engine)
    values = {
        "id": str(uuid.uuid4()),
        "client_id": p["client"],
        "artifact_id": p["artifact"],
        "assessment_id": p["assessment"],
        "target_kind": "ZT_CAPABILITY",
        "target_code": "IDE.01",
        "status": "SUGGESTED",
        "origin": "ai",
        "created_at": NOW,
        "updated_at": NOW,
    }
    table = sa.table("evidence_links", *map(sa.column, values))
    with engine.begin() as conn:
        conn.execute(table.insert().values(**values))
    values = {**values, "id": str(uuid.uuid4()), "target_code": "IDE.02", column: None}
    with pytest.raises(sa.exc.IntegrityError, match="NOT NULL"), engine.begin() as conn:
        conn.execute(table.insert().values(**values))


def test_foreign_keys_and_their_delete_rules(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-fk.db")
    inspector = sa.inspect(engine)
    links = {
        fk["constrained_columns"][0]: (fk["referred_table"], fk["options"].get("ondelete"))
        for fk in inspector.get_foreign_keys("evidence_links")
    }
    # No entry for assessment_id: three assessment tables, no single referent.
    assert links == {
        "client_id": ("client", "CASCADE"),
        "artifact_id": ("artifacts", "CASCADE"),
        "suggested_by_run_id": ("ai_runs", "SET NULL"),
        "confirmed_by": ("users", "SET NULL"),
    }
    artifact_fks = {
        fk["constrained_columns"][0]: (fk["referred_table"], fk["options"].get("ondelete"))
        for fk in inspector.get_foreign_keys("artifacts")
    }
    assert artifact_fks["doc_status_set_by"] == ("users", "SET NULL")


def test_a_link_to_a_missing_artifact_is_refused_and_deleting_one_takes_its_links(
    tmp_path,
) -> None:
    _, engine = _at(tmp_path, "m0068-cascade.db")
    p = _parents(engine)
    with pytest.raises(sa.exc.IntegrityError, match="FOREIGN KEY"), engine.begin() as conn:
        _link(conn, p, "ZT_CAPABILITY", "IDE.01", None, artifact=str(uuid.uuid4()))
    with engine.begin() as conn:
        _link(conn, p, "ZT_CAPABILITY", "IDE.01", None)
        conn.execute(sa.text("DELETE FROM csf_dimension_scores"))
        conn.execute(sa.text("DELETE FROM artifacts WHERE id = :a"), {"a": p["artifact"]})
        n = conn.execute(sa.text("SELECT COUNT(*) FROM evidence_links")).scalar_one()
    assert n == 0


# --- ORM round trip -------------------------------------------------------------------


def test_each_model_round_trips_and_stores_member_names(tmp_path) -> None:
    url, engine = _at(tmp_path, "m0068-orm.db")
    set_at = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)
    with Session(engine) as db:
        client = Client()
        db.add(client)
        db.flush()
        user = User(email="c@atlas.example", password_hash="x", role=UserRole.CLIENT)
        db.add(user)
        db.flush()
        art = Artifact(
            client_id=client.id,
            title="policy.pdf",
            file_storage_key="k",
            mime_type="application/pdf",
            size_bytes=1,
            sha256="0" * 64,
            origin=ArtifactOrigin.CLIENT_UPLOAD,
            uploaded_by=user.id,
            description="Our access control policy.",
            doc_status=ArtifactDocStatus.NOT_SURE,
            doc_status_set_by=user.id,
            doc_status_set_at=set_at,
        )
        service = Service(
            kind=ServiceKind.NIST_CSF, title="CSF", client_id=client.id, opened_by=user.id
        )
        db.add_all([art, service])
        db.flush()
        assessment = CsfAssessment(service_id=service.id, client_id=client.id)
        db.add(assessment)
        db.flush()
        score = CsfDimensionScore(
            assessment_id=assessment.id,
            client_id=client.id,
            tier="moderate",
            subcategory_code="PR.AA-01",
            evidence_basis=CsfEvidenceBasis.MANUAL_TICK_FROZEN,
        )
        csf = EvidenceLink(
            client_id=client.id,
            artifact_id=art.id,
            assessment_id=score.assessment_id,
            target_kind=EvidenceTargetKind.CSF_ROW,
            target_code="PR.AA-01",
            tier="moderate",
            supports=["policy", "implementation"],
            origin="ai",
            quote="Access is reviewed quarterly.",
        )
        attack = EvidenceLink(
            client_id=client.id,
            artifact_id=art.id,
            assessment_id=uuid.uuid4(),
            target_kind=EvidenceTargetKind.ATTACK_TECHNIQUE,
            target_code="T1003",
            supports=["detect"],
            status=EvidenceLinkStatus.CONFIRMED,
            origin="consultant",
            confirmed_by=user.id,
            confirmed_at=set_at,
        )
        db.add_all([score, csf, attack])
        db.commit()
        ids = (art.id, score.id, csf.id, attack.id)

    with Session(_engine(url)) as db:
        art = db.get(Artifact, ids[0])
        assert art.description == "Our access control policy."
        assert art.doc_status is ArtifactDocStatus.NOT_SURE
        assert art.doc_status_set_at.replace(tzinfo=UTC) == set_at
        assert (
            db.get(CsfDimensionScore, ids[1]).evidence_basis is CsfEvidenceBasis.MANUAL_TICK_FROZEN
        )
        csf = db.get(EvidenceLink, ids[2])
        assert csf.status is EvidenceLinkStatus.SUGGESTED
        assert (csf.target_kind, csf.target_code, csf.tier) == (
            EvidenceTargetKind.CSF_ROW,
            "PR.AA-01",
            "moderate",
        )
        assert csf.supports == ["policy", "implementation"]
        assert csf.quote == "Access is reviewed quarterly."
        attack = db.get(EvidenceLink, ids[3])
        assert attack.tier is None
        assert attack.status is EvidenceLinkStatus.CONFIRMED
        assert attack.origin == "consultant"

    with engine.connect() as conn:
        links = conn.execute(
            sa.text("SELECT target_kind, status FROM evidence_links ORDER BY target_kind")
        ).all()
        doc_status = conn.execute(sa.text("SELECT doc_status FROM artifacts")).scalar_one()
        basis = conn.execute(
            sa.text("SELECT evidence_basis FROM csf_dimension_scores")
        ).scalar_one()
    # The repo's enum convention: the stored value is the member NAME.
    assert [tuple(r) for r in links] == [
        ("ATTACK_TECHNIQUE", "CONFIRMED"),
        ("CSF_ROW", "SUGGESTED"),
    ]
    assert doc_status == "NOT_SURE"
    assert basis == "MANUAL_TICK_FROZEN"


def test_the_model_declares_what_the_migration_creates(tmp_path) -> None:
    _, engine = _at(tmp_path, "m0068-parity.db")
    inspector = sa.inspect(engine)
    created_checks = {c["name"] for c in inspector.get_check_constraints("evidence_links")}
    created_indexes = {
        i["name"]: bool(i["unique"]) for i in inspector.get_indexes("evidence_links")
    }
    table = EvidenceLink.__table__
    declared_checks = {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    declared_indexes = {i.name: bool(i.unique) for i in table.indexes}
    assert created_checks == {
        "ck_evidence_links_tier_iff_csf_row",
        "ck_evidence_links_tier_vocabulary",
    }
    assert declared_checks == created_checks
    assert created_indexes == {
        "ix_evidence_links_client_id": False,
        "ix_evidence_links_artifact_id": False,
        "ix_evidence_links_assessment_id": False,
        "uq_evidence_links_untiered": True,
        "uq_evidence_links_tiered": True,
    }
    assert declared_indexes == created_indexes
    for name, where in (
        ("uq_evidence_links_untiered", "tier IS NULL"),
        ("uq_evidence_links_tiered", "tier IS NOT NULL"),
    ):
        index = next(i for i in table.indexes if i.name == name)
        for dialect in ("sqlite", "postgresql"):
            clause = index.dialect_options[dialect]["where"]
            assert clause is not None and str(clause) == where, (name, dialect)


def test_nothing_outside_the_models_reads_evidence_basis() -> None:
    """The column lands and is backfilled (Q9 option A), but nothing reads it,
    for scoring or otherwise, until the R1-R3 change says how (it waits on the
    N3 blast-radius measurement)."""
    app_dir = API_ROOT / "app"
    readers = sorted(
        str(path.relative_to(API_ROOT))
        for path in app_dir.rglob("*.py")
        if "evidence_basis" in path.read_text(encoding="utf-8")
    )
    # Positive first: the search could see the declaring module.
    assert "app/models/csf_profile.py" in readers, readers
    assert readers == ["app/models/csf_profile.py"]
