"""#1120: a revision carries every column, derived from the model.

Two halves:

* STRUCTURE, from `Base.metadata`: every table with a ForeignKey to a record
  table is either copied (it has a `CHILD_NOT_CARRIED` entry in the copier) or
  named here as not carried, with its reason; every column of every copied
  table, record tables included, is in exactly one of `CARRIED` (written here,
  from the design note) and the copier's `NOT_CARRIED`. The copier copies by
  default, so a new column fails here until someone classifies it: a new rule
  stamp would otherwise carry the source's value (ruling item 4).
* VALUES, through the real route: one row of every copied child table is given
  a non-default value in every carried column, generated from the column's
  TYPE, the record is approved and revised, and every carried column of the
  copy, and of the new record, must equal its source.

Limits, stated: type introspection cannot see a polymorphic key without a
ForeignKey (`evidence_links.assessment_id`, copied; `ai_runs.subject_id` and
`audit_entries.target_id`, read through the chain instead) or an integer one
(`deliverables.parent_version`). Those are listed in `LOOSE_KEYS` and the test
asserts the list still names real columns. A floor, not a census.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, select
from sqlalchemy import Enum as SAEnum

from app.db.base import Base
from app.services.revisions import CHILD_NOT_CARRIED, RECORD_NOT_CARRIED
from tests._csf_world import make_world

pytestmark = pytest.mark.unit

RECORD_TABLES = {"attack_assessments", "csf_assessments", "zt_assessments"}

#: FK children of a record table that a revision does NOT copy, and why.
TABLES_NOT_CARRIED = {
    "attack_scenarios": "a what-if is pinned to its base record, which Option A never changes",
}

#: Every column a revision COPIES, per table: the specification the copier's
#: `NOT_CARRIED` maps are checked against (exactly one of the two holds each).
CARRIED: dict[str, frozenset[str]] = {
    "attack_assessments": frozenset({"client_id", "service_id"}),
    "csf_assessments": frozenset({"client_id", "service_id"}),
    "zt_assessments": frozenset({"client_id", "service_id", "framework"}),
    "attack_coverage": frozenset(
        {
            "answered_at",
            "answered_by",
            "client_id",
            "detection_tools",
            "evidence_artifact_id",
            "locked",
            "narrative",
            "notes",
            "prevention_tools",
            "rationale",
            "reason_code",
            "response_tools",
            "reviewed_at",
            "reviewed_by",
            "reviewed_status",
            "status",
            "technique_code",
            "unconfirmed_citations",
        }
    ),
    "csf_answers": frozenset(
        {
            "answered_at",
            "answered_by",
            "client_id",
            "evidence_artifact_id",
            "locked",
            "maturity_tier",
            "notes",
            "subcategory_code",
        }
    ),
    "csf_dimension_scores": frozenset(
        {
            "answer_source",
            "client_id",
            "evidence_artifact_id",
            # Migration 0075: `has_evidence` became the three-valued column.
            "evidence_status",
            "governance",
            "implementation",
            "improvement",
            "in_scope",
            "locked",
            "monitoring",
            "policy",
            "rationale",
            "subcategory_code",
            "target_level",
            "tier",
            "what_we_found",
        }
    ),
    "csf_gap_actions": frozenset(
        {
            "characterization",
            "client_id",
            "deadline",
            "owner",
            "poam_ref",
            "priority_override",
            "resources",
            "subcategory_code",
            "success_criteria",
        }
    ),
    "zt_answers": frozenset(
        {
            "answer_source",
            "answered_at",
            "answered_by",
            "capability_code",
            "client_id",
            "evidence_artifact_id",
            "locked",
            "maturity_stage",
            "notes",
            "target_stage",
        }
    ),
    "evidence_links": frozenset(
        {
            "artifact_id",
            "client_id",
            "confirmed_at",
            "confirmed_by",
            "origin",
            "quote",
            "status",
            "suggested_by_run_id",
            "supports",
            "target_code",
            "target_kind",
            "tier",
        }
    ),
}

#: Keys introspection cannot classify (no ForeignKey), and how each is handled.
LOOSE_KEYS = {
    ("evidence_links", "assessment_id"): "copied, remapped (polymorphic, no FK)",
    ("ai_runs", "subject_id"): "not copied; read through revision_of by the AI stamp",
    ("audit_entries", "target_id"): "not copied; the audit trail stays on its record",
    ("deliverables", "parent_version"): "not copied; a deliverable names its own record",
}

_WHEN = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

#: JSON columns whose API schema reads a structure, not a list of strings.
_JSON_SHAPES = {
    "unconfirmed_citations": [{"tool": "T", "cited": "C", "reason": "carry", "field": None}],
    "supports": ["carry"],
}


@pytest.fixture()
def world(tmp_path):
    yield from make_world(tmp_path)


# --- STRUCTURE ---------------------------------------------------------------


def _fk_children(table: str) -> set[str]:
    return {
        t.name
        for t in Base.metadata.tables.values()
        if t.name != table and any(fk.column.table.name == table for fk in t.foreign_keys)
    }


def test_every_child_table_of_a_record_is_classified() -> None:
    for record in RECORD_TABLES:
        for child in _fk_children(record):
            assert (
                child in CHILD_NOT_CARRIED or child in TABLES_NOT_CARRIED
            ), f"{child} (a child of {record}) is neither copied nor classified"


def test_every_column_of_a_copied_table_is_classified_exactly_once() -> None:
    tables = (*RECORD_TABLES, *CHILD_NOT_CARRIED)
    assert set(CARRIED) == set(tables), set(CARRIED) ^ set(tables)
    for table in tables:
        cols = {c.name for c in Base.metadata.tables[table].columns}
        not_carried = set({**RECORD_NOT_CARRIED, **CHILD_NOT_CARRIED}[table])
        assert CARRIED[table] & not_carried == set(), (table, CARRIED[table] & not_carried)
        assert CARRIED[table] | not_carried == cols, (
            table,
            "unclassified",
            cols - CARRIED[table] - not_carried,
            "not a column",
            (CARRIED[table] | not_carried) - cols,
        )
        for reason in {**RECORD_NOT_CARRIED, **CHILD_NOT_CARRIED}[table].values():
            assert reason.strip(), table


def test_the_loose_keys_still_name_real_columns() -> None:
    for (table, column), reason in LOOSE_KEYS.items():
        assert column in Base.metadata.tables[table].columns, (table, column, reason)
    assert "evidence_links" in CHILD_NOT_CARRIED  # the one loose key that is copied


# --- VALUES ------------------------------------------------------------------


def _value(col, *, refs: dict[str, object]):
    """A non-default value for `col`, from its type; a FK names a real row."""
    for fk in col.foreign_keys:
        return refs[fk.column.table.name]
    t = col.type
    if isinstance(t, SAEnum) and t.enum_class is not None:
        members = list(t.enum_class)
        return members[-1]
    if isinstance(t, Boolean):
        return True
    if isinstance(t, Integer):
        return 3
    if isinstance(t, DateTime):
        return _WHEN
    if isinstance(t, JSON):
        return _JSON_SHAPES.get(col.name, ["carry"])
    if isinstance(t, String):
        if col.name == "tier":
            return "low"
        return f"c-{col.name}"[: (t.length or 64)]
    raise AssertionError(f"no generator for {col.table.name}.{col.name} ({t!r})")


_SKIP = {"id", "created_at", "updated_at", "assessment_id", "client_id"}
#: Columns that identify the row inside its record: kept, used to match.
_KEYS = {
    "attack_coverage": ("technique_code",),
    "csf_answers": ("subcategory_code",),
    "csf_dimension_scores": ("tier", "subcategory_code"),
    "csf_gap_actions": ("subcategory_code",),
    "zt_answers": ("capability_code",),
    "evidence_links": ("target_kind", "target_code", "tier"),
}


def _fill(row, refs: dict[str, object]) -> None:
    table = row.__table__
    not_carried = CHILD_NOT_CARRIED[table.name]
    for col in table.columns:
        if col.name in _SKIP or col.name in _KEYS[table.name] or col.name in not_carried:
            continue
        setattr(row, col.key, _value(col, refs=refs))


def _carried(row) -> dict[str, object]:
    not_carried = CHILD_NOT_CARRIED[row.__table__.name]
    out = {}
    for col in row.__table__.columns:
        if col.name in not_carried or col.name in _SKIP:
            continue
        v = getattr(row, col.key)
        out[col.name] = v.value if isinstance(v, enum.Enum) else v
    return out


def _admin(c) -> tuple[dict, str]:
    r = c.post(
        "/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    return {"Authorization": f"Bearer {r.json()['tokens']['access_token']}"}, r.json()["user"]["id"]


def _artifact(sessions, client_id: str, user_id: str) -> uuid.UUID:
    """A client upload, written directly (storage is not under test)."""
    from app.models.artifact import Artifact, ArtifactOrigin

    with sessions() as s:
        a = Artifact(
            client_id=uuid.UUID(client_id),
            title="e.csv",
            file_storage_key="k/e.csv",
            mime_type="text/csv",
            size_bytes=8,
            sha256="a" * 64,
            origin=ArtifactOrigin.CLIENT_UPLOAD,
            uploaded_by=uuid.UUID(user_id),
            uploaded_at=_WHEN,
        )
        s.add(a)
        s.commit()
        return a.id


#: Per kind: the service body, the evidence-link target kind, and the child
#: table whose row an evidence link names. WHICH child tables are checked is
#: not listed here: it is derived from the model (`_copied_children`), so a
#: new child table fails this test before anyone wires it: with no rows in
#: the setup, at `scalar_one()` (NoResultFound); with rows, at `_KEYS[table]`
#: (KeyError) until its match key is named. A table already wired here that is
#: dropped from the route's `KindPlan` fails the "not copied" assertion below.
_KIND = {
    "attack": ({"title": "ATT&CK"}, "ATTACK_TECHNIQUE", "attack_coverage"),
    "csf": ({"kind": "nist_csf", "title": "CSF"}, "CSF_ROW", "csf_answers"),
    "zt": ({"kind": "zero_trust_cisa", "title": "ZT"}, "ZT_CAPABILITY", "zt_answers"),
}


def _copied_children(kind: str) -> tuple[str, ...]:
    """Every ForeignKey child of the kind's record table that is not named as
    not carried: what a revision must copy (evidence links, keyed without a
    ForeignKey, are checked beside these)."""
    return tuple(sorted(_fk_children(f"{kind}_assessments") - set(TABLES_NOT_CARRIED)))


@pytest.mark.parametrize("kind", sorted(_KIND))
def test_every_carried_column_is_copied(world, kind: str, tmp_path) -> None:
    from app.ai.llm import LLMCallMode
    from app.models.ai_run import AiRun, AiRunStatus
    from app.models.evidence_link import EvidenceLink, EvidenceLinkStatus, EvidenceTargetKind

    c, sessions = world
    h, user_id = _admin(c)
    body, target_kind, link_table = _KIND[kind]
    tables = _copied_children(kind)
    assert link_table in tables, (kind, tables)
    svc = c.post(f"/{kind}/services", headers=h, json=body).json()
    v1 = c.post(f"/{kind}/services/{svc['id']}/assessments", headers=h).json()
    if kind == "csf":
        r = c.post(f"/csf/services/{svc['id']}/profiles/seed", headers=h, json={"tiers": ["low"]})
        assert r.status_code == 200, r.text
        code = next(a["subcategory_code"] for a in v1["answers"])
        assert (
            c.put(f"/csf/services/{svc['id']}/gap-actions/{code}", headers=h, json={}).status_code
            == 200
        )
    artifact_id = _artifact(sessions, c.headers["X-Client-Id"], user_id)

    models = {t: m for m in Base.registry.mappers for t in [m.local_table.name]}
    with sessions() as s:
        now = datetime.now(UTC)
        run = AiRun(
            client_id=uuid.UUID(c.headers["X-Client-Id"]),
            service_id=uuid.UUID(svc["id"]),
            purpose="carry",
            subject_id=uuid.UUID(v1["id"]),
            status=AiRunStatus.COMPLETED,
            mode=LLMCallMode.FIXTURE,
            boot_id="b",
            requested_by=uuid.UUID(user_id),
            started_at=now,
            deadline_at=now + timedelta(minutes=5),
            finished_at=now,
        )
        s.add(run)
        s.flush()
        refs = {
            "users": uuid.UUID(user_id),
            "artifacts": artifact_id,
            "ai_runs": run.id,
        }
        sources: dict[str, dict] = {}
        for table in tables:
            model = models[table].class_
            row = s.execute(
                select(model).where(model.assessment_id == uuid.UUID(v1["id"])).limit(1)
            ).scalar_one()
            _fill(row, refs)
        code_col = {
            "ATTACK_TECHNIQUE": "technique_code",
            "CSF_ROW": "subcategory_code",
            "ZT_CAPABILITY": "capability_code",
        }[target_kind]
        first = s.execute(
            select(models[link_table].class_)
            .where(models[link_table].class_.assessment_id == uuid.UUID(v1["id"]))
            .limit(1)
        ).scalar_one()
        link = EvidenceLink(
            client_id=uuid.UUID(c.headers["X-Client-Id"]),
            artifact_id=refs["artifacts"],
            assessment_id=uuid.UUID(v1["id"]),
            target_kind=EvidenceTargetKind[target_kind],
            target_code=getattr(first, code_col),
            tier="low" if target_kind == "CSF_ROW" else None,
            status=EvidenceLinkStatus.CONFIRMED,
            origin="consultant",
        )
        s.add(link)
        s.flush()
        _fill(link, refs)
        s.commit()
    assert c.post(f"/{kind}/assessments/{v1['id']}/approve", headers=h).status_code == 200
    # The source as it stands when revised: approve may rewrite rows (a
    # computed ATT&CK parent is recomputed), and the copy is of THAT record.
    with sessions() as s:
        for table in (*tables, "evidence_links"):
            model = models[table].class_
            for row in s.execute(
                select(model).where(model.assessment_id == uuid.UUID(v1["id"]))
            ).scalars():
                key = tuple(getattr(row, k) for k in _KEYS[table])
                sources.setdefault(table, {})[key] = _carried(row)

    r = c.post(
        f"/{kind}/services/{svc['id']}/assessments/{v1['id']}/revisions",
        headers=h,
        json={"reason": "carry"},
    )
    assert r.status_code == 201, r.text
    v2 = uuid.UUID(r.json()["id"])

    with sessions() as s:
        for table, by_key in sources.items():
            model = models[table].class_
            copies = {
                tuple(getattr(row, k) for k in _KEYS[table]): _carried(row)
                for row in s.execute(select(model).where(model.assessment_id == v2)).scalars()
            }
            for key, values in by_key.items():
                assert key in copies, (table, key, "not copied")
                assert copies[key] == values, (table, key)
        # The record itself: every carried column equals the source's.
        record_model = models[f"{kind}_assessments"].class_
        old, new = (s.get(record_model, uuid.UUID(str(i))) for i in (v1["id"], v2))
        for col in sorted(CARRIED[f"{kind}_assessments"]):
            assert getattr(new, col) == getattr(old, col), (kind, col)
