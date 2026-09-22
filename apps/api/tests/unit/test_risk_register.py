"""Risk Register: gate, generate, tier-from-code, link validation (Work Order E)."""

from __future__ import annotations

import io
import json
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.risk.exporters import build_context as build_risk_context
from app.risk.exporters import render_docx, render_pdf

# test-integrity: the constant DEFINES the boundary under test — seeding
# `_RISK_BATCH_SIZE + 1` gaps is what forces a second batch, and asserting
# `max(batch_sizes) <= _RISK_BATCH_SIZE` is the invariant itself. Hardcoding a
# literal here would silently stop exercising batching if the constant changed.
from app.routes.risk import _RISK_BATCH_SIZE


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-risk.db'}"
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
    from app.routes.artifacts import _storage_dep
    from app.routes.risk import _llm_dep
    from app.storage.local import LocalFilesystemStorage

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    storage = LocalFilesystemStorage(tmp_path / "storage")
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    app.dependency_overrides[_storage_dep] = lambda: storage
    with TestClient(app) as c:
        yield c, provider


def _session():
    """A read/write session on the SAME database the TestClient is using.

    `app_client` sets `DATABASE_URL` and overrides `get_db` with its own
    factory, so a test that needs to inspect or mutate a row has no handle. It
    opens a second session on that URL rather than re-plumbing the fixture --
    SQLite over a file, so both see the same data.
    """
    import os

    from sqlalchemy.orm import sessionmaker

    engine = create_engine(os.environ["DATABASE_URL"], future=True)
    return sessionmaker(bind=engine, future=True)()


def _admin(c: TestClient) -> tuple[str, str]:
    admin = c.post(
        "/auth/register",
        json={
            "email": "admin@kentro.example",
            "password": "correct horse battery staple!",
            "display_name": "A",
        },
    )
    bearer = admin.json()["tokens"]["access_token"]
    cid = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Acme"},
    ).json()["id"]
    return bearer, cid


def _seed_attack_and_zt(c: TestClient, bearer: str, cid: str) -> tuple[str, str]:
    """Returns (a gap technique_code, a ZT capability_code)."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post(
        "/attack/services",
        headers=h,
        json={"kind": "attack_coverage", "title": "ATT&CK"},
    )
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = a.json()["coverage"][0]
    technique = cov["technique_code"]
    c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})

    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    zans = za.json()["answers"][0]
    capability = zans["capability_code"]
    c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})

    # APPROVE BOTH. Added by #237, and the reason is worth keeping: before that
    # change this helper left both assessments as DRAFTS and every test below
    # generated a Risk Register from them. The suite was exercising the defect
    # on every generate path and reporting green -- synthesis had no provenance
    # filter, so unapproved work flowed into a register that is exported under
    # the client's name.
    #
    # Ten tests went red when the filter landed. That is the two-sided evidence,
    # and it is why this call is here rather than the filter being relaxed.
    ar = c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h)
    assert ar.status_code == 200, ar.text
    zr = c.post(f"/zt/assessments/{za.json()['id']}/approve", headers=h)
    assert zr.status_code == 200, zr.text
    return technique, capability


@pytest.mark.unit
def test_gate_locked_without_attack(app_client) -> None:
    c, _ = app_client
    bearer, cid = _admin(c)
    bh = {"Authorization": f"Bearer {bearer}"}
    g = c.get(f"/risk/clients/{cid}/gate", headers=bh)
    assert g.status_code == 200
    assert g.json()["unlocked"] is False
    # Generate refuses while locked.
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 409


@pytest.mark.unit
def test_generate_derives_tier_in_code_and_validates_links(app_client) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    assert c.get(f"/risk/clients/{cid}/gate", headers=bh).json()["unlocked"] is True

    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Credential theft exposure",'
            ' "description": "EDR gap", "axis": "detection",'
            ' "source": "coverage_finding", "source_id": "' + technique + '",'
            ' "linked_techniques": ["' + technique + '", "T9999"],'
            ' "linked_controls": ["' + capability + '", "BOGUS.XX.01"],'
            ' "likelihood": "high", "impact": "catastrophic",'
            ' "recommended_action": "remediate", "rationale": "...",'
            ' "tier": "low"}]}'  # AI's "tier" must be ignored.
        ),
    )

    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert len(body["entries"]) == 1
    e = body["entries"][0]
    # Tier is code-derived (High + Catastrophic -> Critical), NOT the AI's "low".
    assert e["tier"] == "critical"
    # Invented technique/control dropped; only the real ones remain.
    assert e["linked_techniques"] == [technique]
    assert e["linked_controls"] == [capability]
    assert e["origin"] == "ai_generated"
    assert body["tier_counts"]["critical"] == 1
    assert body["axis_counts"]["detection"] == 1


def _generated_audit(c, bearer: str) -> dict:
    """The `risk_register.generated` row, read through the surface a consultant reaches.

    Deliberately via `/admin/audit-entries` rather than by querying the table:
    the claim this fix makes is that an unresolvable value is REPORTED
    somewhere a person can see, and a test that reads the database proves the
    write and not the claim.
    """
    r = c.get("/admin/audit-entries?limit=50", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200, r.text
    rows = r.json()
    rows = rows["entries"] if isinstance(rows, dict) else rows
    generated = [x for x in rows if x.get("action") == "risk_register.generated"]
    assert generated, f"no risk_register.generated row among {[x.get('action') for x in rows]}"
    return generated[0]["details"]


def _one_entry(technique: str, **over: str) -> str:
    fields = {
        "title": "Credential theft exposure",
        "description": "EDR gap",
        "axis": "detection",
        "source": "coverage_finding",
        "source_id": technique,
        "likelihood": "high",
        "impact": "catastrophic",
        "recommended_action": "remediate",
        "rationale": "...",
    }
    fields.update(over)
    body = ", ".join(f'"{k}": "{v}"' for k, v in fields.items() if v is not None)
    return '{"entries": [{' + body + "}]}"


@pytest.mark.unit
def test_an_unresolvable_enum_value_is_reported_not_dropped(app_client) -> None:
    """#121's reporting half, which nothing exercised.

    The prompt/parser drift is fixed by the prompt and the coercion. This is
    the part that makes a FUTURE drift visible instead of silent.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static(
        "risk_synthesize",
        LLMResponse(_one_entry(technique, likelihood="severe")),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text

    details = _generated_audit(c, bearer)
    assert details["rejected_enum_values"] == {"likelihood": ["severe"]}, details
    # And the outcome, which is what the client would see.
    assert details["entries_without_tier"] == 1, details
    assert details["entries_intended"] == 1, details


@pytest.mark.unit
def test_an_ABSENT_enum_key_still_moves_a_counter(app_client) -> None:
    """The second route to the identical silent zero.

    An adversarial pass found this: the rejection map can only see values that
    were SUPPLIED, so a model that simply omits `likelihood` produces the same
    tier-less entry, the same em dashes and the same dropped matrix cell --
    with `rejected_enum_values` empty and the audit row reading clean.

    `entries_without_tier` is keyed on the OUTCOME for exactly this reason. If
    it ever reads zero while a client sees em dashes, this assertion is where
    that shows up.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static(
        "risk_synthesize",
        # `likelihood` omitted entirely -- not empty, absent.
        LLMResponse(_one_entry(technique, likelihood=None)),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["entries"][0]["tier"] is None
    assert body["entries"][0]["likelihood"] is None

    details = _generated_audit(c, bearer)
    # Nothing was REJECTED -- nothing was supplied to reject.
    assert details["rejected_enum_values"] == {}, details
    # But the run is not clean, and the record must say so.
    assert details["entries_without_tier"] == 1, details


@pytest.mark.unit
def test_coercion_works_THROUGH_generate_not_only_in_isolation(app_client) -> None:
    """The Title-Case form, end to end.

    An adversarial pass found that every existing `register_static` payload in
    this file uses exact snake_case, so `_coerce_enum`'s normalisation branch
    was proven only in isolation and never through the route. Concretely: at
    that point `_record` could have had a no-op body and every test still
    passed.

    This is the literal #121 scenario -- a model obeying the OLD prompt -- and
    it must now produce a real tier rather than an em dash.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static(
        "risk_synthesize",
        LLMResponse(_one_entry(technique, likelihood="Very High", impact="Catastrophic")),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    e = r.json()["entries"][0]
    assert e["likelihood"] == "very_high"
    assert e["impact"] == "catastrophic"
    # Very High x Catastrophic -> critical, by rule 1 of `tier_for`.
    assert e["tier"] == "critical"

    details = _generated_audit(c, bearer)
    assert details["rejected_enum_values"] == {}, "a coerced value is not a rejection"
    assert details["entries_without_tier"] == 0, details


@pytest.mark.unit
def test_a_clean_run_records_zero_rather_than_nothing(app_client) -> None:
    """Absence of a finding must be a stated zero, not a missing key.

    A reader has to be able to tell "nothing went wrong" from "nobody looked",
    and an omitted field cannot carry that distinction.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    details = _generated_audit(c, bearer)
    assert details["rejected_enum_values"] == {}
    assert details["entries_without_tier"] == 0
    assert details["entries_intended"] == 1


@pytest.mark.unit
def test_generate_records_what_it_was_built_from(app_client) -> None:
    """#240. The register now says what it was synthesized from.

    Nothing on `risk_registers` recorded which assessments, versions or
    statuses fed it, so `export` could not have checked provenance even if it
    had wanted to -- which is why #242 could close the generate half of #237
    and not the export half named in its own title.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    reg = (
        _session()
        .execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    assert reg is not None
    prov = reg.provenance
    assert prov is not None, "a generated register must record its inputs"
    kinds = {i["kind"] for i in prov["inputs"]}
    assert "attack" in kinds, prov
    for i in prov["inputs"]:
        assert i["status"] in ("approved", "released"), i
        assert isinstance(i["version"], int)
        assert i["assessment_id"]


@pytest.mark.unit
def test_export_refuses_a_register_built_from_unapproved_work(app_client) -> None:
    """The export half of #237, closed against the SNAPSHOT.

    The status is read from what was recorded at generate, never recomputed --
    recomputing would read TODAY's statuses, so an assessment approved after
    generation would certify a register that never saw it (D-053).

    So this test mutates the stored provenance rather than the assessment.

    **And that is not a testing convenience -- it is the finding.** The guard
    is UNREACHABLE by construction today: `_provenance_snapshot` records only
    what `_finalized_for_synthesis` returns, and that resolver filters
    `status.in_(_FINALIZED)` where `_FINALIZED = ("approved", "released")`. No
    register generated on or after 0047 can carry an unapproved input, so
    mutating the stored row is the only way in.

    The guard is kept as a RATCHET. What makes it unreachable is one WHERE
    clause, and `test_the_synthesis_path_must_filter_on_finalized` is what
    holds that clause in place. If that test is ever removed or weakened, this
    branch stops being decorative.

    Note what this test does NOT cover: the pre-0047 register built from a
    DRAFT ATT&CK mapping -- the hazard #240 opens with -- has NULL provenance
    and is caught by the other branch, in
    `test_export_refuses_a_pre_provenance_register_that_was_never_delivered`.
    Two different registers, two different branches, and conflating them was
    the error this docstring now exists to prevent.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    prov = dict(reg.provenance)
    prov["inputs"] = [{**i, "status": "draft"} for i in prov["inputs"]]
    reg.provenance = prov
    db.add(reg)
    db.commit()

    r = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert r.status_code == 409, r.text
    msg = r.json()["error"]["message"]
    assert "not approved" in msg, msg
    assert "attack" in msg, "the refusal must NAME which input, not just refuse"

    # And nothing was published.
    db.refresh(reg)
    assert reg.finalized_at is None


@pytest.mark.unit
def test_export_refuses_a_pre_provenance_register_that_was_never_delivered(
    app_client,
) -> None:
    """NULL provenance is 'not recorded', not 'nothing was excluded'.

    A register whose inputs were never captured cannot be certified either way,
    so it is refused -- missing data defaults to UNCONFIRMED. The carve-out for
    an ALREADY-finalized register is covered by the next test: blocking a
    re-export protects nobody and breaks a working path.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    reg.provenance = None  # a pre-0047 row
    db.add(reg)
    db.commit()

    r = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert r.status_code == 409, r.text
    assert "predates provenance recording" in r.json()["error"]["message"]


@pytest.mark.unit
def test_export_renders_and_stores_three_files(app_client) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Risk one", "axis": "detection",'
            ' "likelihood": "high", "impact": "catastrophic",'
            ' "recommended_action": "remediate"}]}'
        ),
    )
    c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    r = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["xlsx_filename"].endswith(".xlsx")
    assert body["pdf_filename"].endswith(".pdf")
    assert body["docx_filename"].endswith(".docx")
    # Each downloads as a real file (artifact download is tenant-scoped, so the
    # admin names the active client via X-Client-Id).
    dh = {**bh, "X-Client-Id": cid}
    xlsx = c.get(f"/artifacts/{body['xlsx_artifact_id']}/download", headers=dh)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    pdf = c.get(f"/artifacts/{body['pdf_artifact_id']}/download", headers=dh)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    docx = c.get(f"/artifacts/{body['docx_artifact_id']}/download", headers=dh)
    assert docx.status_code == 200 and docx.content[:2] == b"PK"


# ---------------------------------------------------------------------------
# Exporter content (pure renderers — no DB). The XLSX is already content-tested
# via the download in test_export_renders_and_stores_three_files; here we prove
# the PDF + DOCX carry the title and a known entry (SMOKE §10).
# ---------------------------------------------------------------------------


def _risk_entry() -> SimpleNamespace:
    return SimpleNamespace(
        title="Credential theft exposure",
        description="EDR coverage gap",
        axis="detection",
        source="coverage_finding",
        source_id="T1078",
        linked_techniques=["T1078"],
        linked_controls=["ID.PA.01"],
        likelihood="high",
        impact="catastrophic",
        tier="critical",
        compensating_controls=None,
        residual_risk=None,
        recommended_action="remediate",
        rationale="Primary detection layer absent.",
        origin="ai_generated",
        trust=None,
    )


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    return "".join(page.extract_text() for page in reader.pages)


@pytest.mark.unit
def test_pdf_carries_title_client_and_a_known_entry() -> None:
    ctx = build_risk_context(
        client_legal_name="Atlas Defense Solutions", version=3, entries=[_risk_entry()]
    )
    raw = render_pdf(ctx)
    assert raw.startswith(b"%PDF-")
    text = _pdf_text(raw)
    assert "Risk Register" in text  # document title
    assert "Atlas Defense Solutions" in text  # client name
    assert "Credential theft exposure" in text  # a known register entry


@pytest.mark.unit
def test_docx_carries_title_client_and_a_known_entry() -> None:
    from docx import Document

    ctx = build_risk_context(
        client_legal_name="Atlas Defense Solutions", version=3, entries=[_risk_entry()]
    )
    raw = render_docx(ctx)
    assert raw[:2] == b"PK"  # docx is a zip envelope
    doc = Document(io.BytesIO(raw))
    paras = [p.text for p in doc.paragraphs if p.text]
    assert "Risk Register (v3)" in paras  # title heading
    assert "Atlas Defense Solutions" in paras  # client subtitle
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    assert "Credential theft exposure" in cells  # a known register entry


@pytest.mark.unit
def test_each_generate_is_a_new_version(app_client) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse('{"entries": []}'))

    v1 = c.post(f"/risk/clients/{cid}/register/generate", headers=bh).json()
    v2 = c.post(f"/risk/clients/{cid}/register/generate", headers=bh).json()
    assert v1["version"] == 1
    assert v2["version"] == 2
    latest = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert latest.json()["version"] == 2


# ---------------------------------------------------------------------------
# Batching. risk_synthesize drafts ONE entry per finding, and a real client
# supplies hundreds: the 2026-08-07 validation client had 509 (472 ATT&CK
# gap/partial + 37 ZT). At ~500 output tokens an entry that is ~250k tokens of
# output, past claude-opus-5's 128k ceiling — so no output budget can make a
# single request work. It is split, exactly as mitre_map was.
# ---------------------------------------------------------------------------


def _seed_many_gaps(c: TestClient, bearer: str, cid: str, count: int) -> tuple[list[str], str]:
    """Seed `count` ATT&CK gaps plus one ZT gap. Returns (technique codes, capability)."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post(
        "/attack/services",
        headers=h,
        json={"kind": "attack_coverage", "title": "ATT&CK"},
    )
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    rows = a.json()["coverage"][:count]
    assert len(rows) == count, f"assessment supplied only {len(rows)} techniques"
    for cov in rows:
        c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})

    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    zans = za.json()["answers"][0]
    c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})
    # Approve both -- #237. Synthesis reads only APPROVED/RELEASED assessments,
    # because what it produces is exported under the client's name. This seed
    # left them DRAFT and the generate below used to succeed.
    assert c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h).status_code == 200
    assert c.post(f"/zt/assessments/{za.json()['id']}/approve", headers=h).status_code == 200
    return [r["technique_code"] for r in rows], zans["capability_code"]


def _entry_per_finding(payload: dict) -> LLMResponse:
    """A response shaped like the real prompt's: one candidate entry per finding."""
    entries = [
        {
            "title": f"Risk for {f['source_id']}",
            "description": "d",
            "axis": "detection",
            "source": f["source"],
            "source_id": f["source_id"],
            "linked_techniques": [],
            "linked_controls": [],
            "likelihood": "high",
            "impact": "major",
            "recommended_action": "remediate",
            "rationale": "r",
        }
        for f in payload.get("findings", [])
    ]
    return LLMResponse(json.dumps({"entries": entries}))


@pytest.mark.unit
def test_generate_splits_large_finding_sets_and_loses_nothing(app_client) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    codes, capability = _seed_many_gaps(c, bearer, cid, _RISK_BATCH_SIZE + 1)
    bh = {"Authorization": f"Bearer {bearer}"}

    batch_sizes: list[int] = []

    def fixture(payload: dict) -> LLMResponse:
        batch_sizes.append(len(payload.get("findings", [])))
        return _entry_per_finding(payload)

    provider.register("risk_synthesize", fixture)

    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    body = r.json()

    # More than one provider call, and the register accounts for every finding
    # that went into them — batching must not quietly drop the tail.
    assert len(batch_sizes) > 1
    assert body["batches_total"] == len(batch_sizes)
    assert body["batches_failed"] == 0
    assert sum(batch_sizes) == len(codes) + 1  # + the ZT gap
    assert {e["source_id"] for e in body["entries"]} == {*codes, capability}
    # No batch may exceed the cap that made splitting necessary in the first place.
    assert max(batch_sizes) <= _RISK_BATCH_SIZE


@pytest.mark.unit
def test_generate_keeps_the_batches_that_succeeded(app_client) -> None:
    """A partial failure must cost the failed slice, not the whole run.

    Discarding everything would also discard the money already spent on the
    batches that came back clean.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_many_gaps(c, bearer, cid, _RISK_BATCH_SIZE + 1)
    bh = {"Authorization": f"Bearer {bearer}"}

    seen = 0

    def flaky(payload: dict) -> LLMResponse:
        nonlocal seen
        seen += 1
        if seen == 1:
            raise RuntimeError("provider exploded on this batch")
        return _entry_per_finding(payload)

    provider.register("risk_synthesize", flaky)

    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["batches_failed"] == 1
    assert body["batches_total"] > 1
    # The surviving batches still produced entries.
    assert len(body["entries"]) > 0


@pytest.mark.unit
def test_generate_fails_loudly_when_every_batch_fails(app_client) -> None:
    """Nothing usable came back, so this is a failure — not an empty register."""
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_many_gaps(c, bearer, cid, _RISK_BATCH_SIZE + 1)
    bh = {"Authorization": f"Bearer {bearer}"}

    def always_fails(_payload: dict) -> LLMResponse:
        raise RuntimeError("provider is down")

    provider.register("risk_synthesize", always_fails)

    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 502, r.text
    # Typed envelope (D-016), not a raw traceback. charged_likely must survive:
    # the admin needs to know whether a retry may cost money a second time.
    err = r.json()["error"]
    assert err["reason"] == "ai_call_failed"
    assert err["message"]
    assert err["charged_likely"] is False  # fixture provider bills nothing
    # And no half-built register was left behind.
    assert c.get(f"/risk/clients/{cid}/register/latest", headers=bh).status_code == 404


@pytest.mark.unit
def test_generate_non_list_entries_is_a_typed_error_not_a_500(app_client) -> None:
    """A non-list `entries` must be a typed 502, not an untyped 500.

    Precisely: the batching loop reads `(data.get("entries") or [])`, so this
    payload did NOT 500 — `0 or []` is `[]`, and the run generated an empty
    register reporting success. (Only a truthy non-iterable reaches a TypeError,
    which then escapes as an untyped 500. Both are wrong, in opposite
    directions.) The guard replaces both with one typed 502, matching csf_score
    and zt_score.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static("risk_synthesize", LLMResponse('{"entries": 0}'))
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"
    assert "drifted apart" in r.json()["error"]["message"]


@pytest.mark.unit
def test_generate_object_entries_is_refused_not_iterated_as_keys(app_client) -> None:
    """A dict is truthy and iterable, so it did not raise — it iterated KEYS.

    `for raw in {"e1": {...}}` yields the string "e1", which then fails the
    per-entry shape checks and is discarded. The register generates empty and
    reports success.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    provider.register_static("risk_synthesize", LLMResponse('{"entries": {"e1": {"title": "x"}}}'))
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["reason"] == "ai_call_failed"


def _seed_drafts_only(c: TestClient, bearer: str, cid: str) -> None:
    """ATT&CK + ZT assessments that EXIST and are not approved."""
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post(
        "/attack/services",
        headers=h,
        json={"kind": "attack_coverage", "title": "ATT&CK"},
    )
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = a.json()["coverage"][0]
    c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    c.patch(
        f"/zt/answers/{za.json()['answers'][0]['id']}",
        headers=h,
        json={"maturity_stage": 1},
    )


@pytest.mark.unit
def test_the_gate_path_must_not_filter_on_finalized(app_client) -> None:
    """The gate unlocks on EXISTENCE. A draft counts.

    This is half of a two-sided constraint and it has a red state on purpose.
    If someone "tidies" `_exists_for_gate` and `_finalized_for_synthesis` back
    into one helper, one of these two tests fails whichever way they merge it:
    filter the shared helper on finalized and THIS test goes red; stop filtering
    and its sibling below goes red. The types make the merge awkward; these
    tests make it loud.

    Unlock stays on existence deliberately — mapping ATT&CK before the tech-debt
    list is approved is a normal order of work, and requiring
    finalize-everything-first would be a workflow restriction nobody asked for.
    """
    c, _ = app_client
    bearer, cid = _admin(c)
    _seed_drafts_only(c, bearer, cid)
    g = c.get(f"/risk/clients/{cid}/gate", headers={"Authorization": f"Bearer {bearer}"}).json()

    assert g["unlocked"] is True, "a draft must still unlock the gate"
    assert g["has_attack"] is True and g["has_zt"] is True
    assert g["missing"] == [], "nothing is ABSENT -- both assessments exist"


@pytest.mark.unit
def test_the_synthesis_path_must_filter_on_finalized(app_client) -> None:
    """Synthesis refuses unapproved work, and says which input and why.

    The other half. What synthesis produces is exported under the client's name,
    so a DRAFT reaching it is unreviewed content leaving as a deliverable — a
    different and worse failure than a correct number under a wrong label.
    """
    c, _ = app_client
    bearer, cid = _admin(c)
    _seed_drafts_only(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    g = c.get(f"/risk/clients/{cid}/gate", headers=bh).json()
    assert set(g["not_finalized"]) == {
        "the MITRE ATT&CK coverage mapping",
        "the Zero Trust assessment",
    }, "the gate must NAME the unapproved inputs, not merely refuse later"
    assert g["missing"] == [], (
        "'absent' and 'exists but unapproved' are separate fields -- collapsing "
        "them would make the API say an assessment does not exist when it does"
    )

    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 409, "a draft-sourced register must be REFUSED"
    body = r.json()["error"]["message"]
    assert "unapproved" in body and "MITRE ATT&CK" in body
    # NOT an empty register generated successfully, which would read to a client
    # as "no risks found" -- a confident absence in place of unreviewed content.
    #
    # `/register/latest`, NOT `/register`. The first version asserted 404 on
    # `/register`, which IS NOT A ROUTE -- the 404 came from FastAPI's router and
    # passed identically whether or not a register had been created. A vacuous
    # assertion carrying the sentence above it.
    assert c.get(f"/risk/clients/{cid}/register/latest", headers=bh).status_code == 404


@pytest.mark.unit
def test_approving_the_same_inputs_lets_synthesis_through(app_client) -> None:
    """The positive control, on the REAL synthesis call.

    Without it, the refusal above is equally satisfied by a generate endpoint
    that refuses everything. Same client, same assessments, only the approval
    differs — so the two tests bracket the change rather than each proving half.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)  # identical seed, plus approve
    bh = {"Authorization": f"Bearer {bearer}"}

    g = c.get(f"/risk/clients/{cid}/gate", headers=bh).json()
    assert g["unlocked"] is True
    assert g["not_finalized"] == [], "approved inputs must clear the provenance list"

    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Credential theft exposure",'
            ' "description": "EDR gap", "axis": "detection",'
            ' "source": "coverage_finding", "source_id": "' + technique + '",'
            ' "linked_techniques": ["' + technique + '"],'
            ' "linked_controls": ["' + capability + '"],'
            ' "likelihood": "high", "impact": "catastrophic",'
            ' "recommended_action": "remediate", "rationale": "..."}]}'
        ),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, r.text
    assert r.json()["entries"], "the register must actually carry entries"


@pytest.mark.unit
def test_a_draft_sourced_register_is_never_generated(app_client) -> None:
    """No 201 from unapproved inputs, whatever the reason for the refusal.

    This exists to make the two merge directions DISCRIMINABLE, and that gap was
    real: with only the two tests above, direction B's red set was a strict
    SUBSET of direction A's. `synthesis_path` died under both — under A because
    the gate reports the assessments as absent, which is a side effect of the
    gate change rather than an independent signal — so nothing failed under B
    alone. A shared red set cannot tell you which of two merges happened, which
    is the collapse #213 is about, one level up in the evidence rather than in
    the code.

    This one is deliberately indifferent to WHICH refusal fires. Merge the
    helpers so the gate filters on finalized and the register is refused as
    locked: this still passes. Merge them so synthesis stops filtering and a
    draft-sourced register generates: this is the only test that fails.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_drafts_only(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    # A WORKING fixture, and it is what makes the assertion below mean anything.
    # Without it this test registers no `risk_synthesize` response, so if the
    # provenance filter is ever removed the run reaches the provider, every
    # batch raises `KeyError`, and generate returns 502 -- so `!= 201` passed BY
    # CONSTRUCTION under every possible mutation, while carrying the sentence
    # "a register was generated from unapproved assessments". The test could not
    # reach a successful synthesis, which is the one outcome it exists to forbid.
    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Credential theft exposure",'
            ' "description": "EDR gap", "axis": "detection",'
            ' "source": "coverage_finding", "source_id": "T1078",'
            ' "linked_techniques": [], "linked_controls": [],'
            ' "likelihood": "high", "impact": "catastrophic",'
            ' "recommended_action": "remediate", "rationale": "..."}]}'
        ),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code != 201, (
        "a register was generated from unapproved assessments -- its contents "
        "are exported under the client's name"
    )
    # 4xx, not 409 specifically. The docstring says this test is "deliberately
    # indifferent to WHICH refusal fires", and `== 409` contradicted that: under
    # a merge that locks the gate the refusal is still a 409, but pinning the
    # exact code made the claim false of its own assertion.
    assert 400 <= r.status_code < 500, f"expected a refusal, got {r.status_code}"


@pytest.mark.unit
def test_an_unapproved_OPTIONAL_input_does_not_block_generation(app_client) -> None:
    """The refusal must mirror the UNLOCK, not exceed it.

    Unlock is `has_attack and (has_csf or has_zt)` — CSF and ZT are
    ALTERNATIVES. The first version of the provenance refusal blocked on any
    present-but-unapproved input regardless of whether it was needed, so:

        ATT&CK approved + CSF approved + ZT draft  ->  409

    Two assessments that fully satisfy the unlock rule produced nothing, and the
    only remedies were to approve unfinished work — the exact thing this change
    exists to prevent — or discard it.

    Live rather than exotic: `_FINALIZED` deliberately excludes `submitted`, and
    submitted is the routine transient state of a CSF or ZT engagement sitting
    in a consultant's review queue. A client answering their questionnaire would
    have blocked the Risk Register.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)  # both approved
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    bh = {"Authorization": f"Bearer {bearer}"}

    # A THIRD assessment, started and not approved. CSF here, so ATT&CK+ZT
    # already satisfy the unlock rule without it.
    csvc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    c.post(f"/csf/services/{csvc.json()['id']}/assessments", headers=h)

    g = c.get(f"/risk/clients/{cid}/gate", headers=bh).json()
    assert g["unlocked"] is True
    assert (
        "the CSF assessment" in g["not_finalized"]
    ), "an unapproved input must still be REPORTED even when it does not block"

    provider.register_static(
        "risk_synthesize",
        LLMResponse(
            '{"entries": [{"title": "Credential theft exposure",'
            ' "description": "EDR gap", "axis": "detection",'
            ' "source": "coverage_finding", "source_id": "' + technique + '",'
            ' "linked_techniques": ["' + technique + '"],'
            ' "linked_controls": ["' + capability + '"],'
            ' "likelihood": "high", "impact": "catastrophic",'
            ' "recommended_action": "remediate", "rationale": "..."}]}'
        ),
    )
    r = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert r.status_code == 201, (
        "an unapproved OPTIONAL input must not block a register the unlock rule "
        f"already permits -- got {r.status_code}: {r.text}"
    )
    # ...and the exclusion is DISCLOSED rather than silent. Without this the
    # register is a figure over a withheld population, which is the trade this
    # fix must not make: a hard block replaced by a quiet partial.
    assert "the CSF assessment" in r.json()["excluded_inputs"], (
        "a present-but-unapproved assessment contributed nothing and the "
        "register does not say so"
    )


# ---------------------------------------------------------------------------
# #132 -- a risk entry that LOST its links must be distinguishable from one
# that had none.
#
# `routes/risk.py` filtered the model's proposed links with a bare
# comprehension:
#
#     techs = [t for t in (raw.get("linked_techniques") or []) if t in valid_techniques]
#
# Every non-matching value was discarded with no counter, no reason and no
# example. That is `_validate_tools` as it looked before the ATT&CK work
# rewrote it, surviving in a REIMPLEMENTATION -- `risk.py` never calls the
# ATT&CK resolver, so a complete call-site sweep reported clean over it.
#
# The harm is not bookkeeping. An entry whose every technique link was dropped
# is persisted with `linked_techniques = []`, byte-identical to an entry the
# model linked nothing for. Risk is the synthesized service the client reads
# last, so a silently unlinked register reads as "the AI found no ATT&CK
# relevance" when the truth may be "the AI proposed five techniques and all
# five were misspelled".
#
# These tests read the RESPONSE and the AUDIT ROW, not the database: the claim
# is that a drop is reported somewhere a person can see, and a test that
# queries the table proves the write and not the claim. They live in this file
# rather than their own because `app_client` and `_seed_attack_and_zt` are
# local to it -- a second copy of the seed is a second world for the two files
# to disagree about, and #242 is on record for what a divergent seed costs.
# ---------------------------------------------------------------------------


def _entries_payload(*entries: str) -> str:
    return '{"entries": [' + ", ".join(entries) + "]}"


def _entry(title: str, **fields: str) -> str:
    base = {
        "title": title,
        "description": "d",
        "axis": "detection",
        "source": "coverage_finding",
        "likelihood": "high",
        "impact": "catastrophic",
        "recommended_action": "remediate",
        "rationale": "r",
    }
    base.update({k: v for k, v in fields.items() if v is not None})
    scalars = ", ".join(f'"{k}": "{v}"' for k, v in base.items())
    return "{" + scalars + "}"


def _generate(c, provider, bearer, cid, payload: str) -> dict:
    provider.register_static("risk_synthesize", LLMResponse(payload))
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _by_title(body: dict) -> dict:
    return {e["title"]: e for e in body["entries"]}


@pytest.mark.unit
def test_the_two_states_that_used_to_be_the_same_bytes(app_client) -> None:
    """THE HEADLINE. Two entries, identical `linked_techniques`, different facts.

    "Lost every link it proposed" and "proposed none" both render as an empty
    list. This asserts the register can now tell them apart -- and asserts the
    thing they still have in COMMON, so a fix that merely started keeping the
    bogus links would fail here rather than pass.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Lost them all", source_id=technique)[:-1]
        + ', "linked_techniques": ["T9999"], "linked_controls": ["BOGUS.XX.01"]}',
        _entry("Offered none", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}',
    )
    body = _generate(c, provider, bearer, cid, payload)
    entries = _by_title(body)

    lost, none_offered = entries["Lost them all"], entries["Offered none"]
    # What they still share -- the bogus links are NOT kept.
    assert lost["linked_techniques"] == [] and lost["linked_controls"] == []
    assert none_offered["linked_techniques"] == []
    # And what now separates them.
    assert lost["dropped_links"] == {
        "linked_techniques": ["T9999"],
        "linked_controls": ["BOGUS.XX.01"],
    }
    assert none_offered["dropped_links"] == {}, (
        "an entry that proposed nothing must record the POSITIVE claim that "
        "nothing was dropped -- `None` is reserved for pre-0048 rows and means "
        "nobody was counting"
    )
    assert body["entries_with_dropped_links"] == 1
    assert body["entries_unlinked_after_drops"] == 1
    assert body["entries_links_not_recorded"] == 0
    assert technique and capability  # the seed is real, not a stub


@pytest.mark.unit
def test_an_entry_that_kept_one_link_is_not_counted_as_unlinked(app_client) -> None:
    """The discriminator for the OUTCOME counter.

    `entries_with_dropped_links` and `entries_unlinked_after_drops` answer
    different questions, and a single counter would collapse them: an entry that
    proposed four techniques and kept one has a spelling problem worth seeing
    and NO client-visible absence. Counting it in the outcome would inflate the
    number a consultant acts on.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Kept one", source_id=technique)[:-1]
        + f', "linked_techniques": ["{technique}", "T9999"], "linked_controls": []}}'
    )
    body = _generate(c, provider, bearer, cid, payload)
    entry = body["entries"][0]

    assert entry["linked_techniques"] == [technique]
    assert entry["dropped_links"] == {"linked_techniques": ["T9999"]}
    assert body["entries_with_dropped_links"] == 1
    assert body["entries_unlinked_after_drops"] == 0


@pytest.mark.unit
def test_one_long_value_repeated_is_recorded_once(app_client) -> None:
    """Dedup on the TRUNCATED form, not the original (#132 review).

    The first version tested membership of the untruncated value against a list
    of truncated ones, so a repeated value longer than 64 characters -- a model
    citing a technique by its full descriptive name -- was appended twice and
    inflated the number a consultant acts on.

    Truncation stays AFTER the universe test: truncating first would let a
    64-character member of the allow-list start matching longer non-members,
    which turns a reporting bug into a wrong link.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    long_value = "T" + "x" * 80

    payload = _entries_payload(
        _entry("Repeats itself", source_id=technique)[:-1]
        + f', "linked_techniques": ["{long_value}", "{long_value}"], '
        + '"linked_controls": []}'
    )
    body = _generate(c, provider, bearer, cid, payload)
    dropped = body["entries"][0]["dropped_links"]["linked_techniques"]

    assert len(dropped) == 1, dropped
    assert len(dropped[0]) == 64, "and it is stored truncated"


@pytest.mark.unit
def test_the_audit_row_names_what_to_fix_and_what_was_seen(app_client) -> None:
    """The map names the values; the counters name the outcome.

    Both, for the reason the `rejected_enum_values` / `entries_without_tier`
    pair one block up records: a map of supplied values cannot see an outcome,
    and a count cannot tell anyone what to correct.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("A", source_id=technique)[:-1]
        + ', "linked_techniques": ["T9999", "T8888"], "linked_controls": []}',
        _entry("B", source_id=technique)[:-1]
        + ', "linked_techniques": ["T9999"], "linked_controls": ["NOPE.01"]}',
    )
    _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert details["dropped_link_values"]["linked_techniques"] == ["T9999", "T8888"], (
        "deduped ACROSS entries and in first-seen order -- T9999 appears in both "
        "entries and must be listed once"
    )
    assert details["dropped_link_values"]["linked_controls"] == ["NOPE.01"]
    assert details["entries_offered_links"] == 2
    assert details["entries_unlinked_after_drops"] == 2


@pytest.mark.unit
def test_an_unknown_source_id_is_dropped_and_recorded(app_client) -> None:
    """`source_id` was stored with no validation at all.

    An entry could claim provenance from a finding that does not exist, and the
    register carried a dangling reference as if it were traceability. Dropping
    it silently would be this issue's own defect committed while fixing it, so
    it is dropped AND recorded.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Invented provenance", source_id="NOT-A-FINDING")[:-1]
        + ', "linked_techniques": [], "linked_controls": []}'
    )
    body = _generate(c, provider, bearer, cid, payload)
    entry = body["entries"][0]

    assert entry["source_id"] is None
    assert entry["dropped_links"] == {"source_id": ["NOT-A-FINDING"]}
    # NOT counted as an unlinked entry: a dropped source_id does not change what
    # linkage the consultant sees on the row.
    assert body["entries_unlinked_after_drops"] == 0
    assert body["entries_with_dropped_links"] == 1


@pytest.mark.unit
def test_a_real_source_id_survives(app_client) -> None:
    """The passing state for the new validation.

    Without it the test above proves only that SOMETHING was rejected, which a
    validator that rejects everything also satisfies.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Real provenance", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}'
    )
    body = _generate(c, provider, bearer, cid, payload)
    entry = body["entries"][0]

    assert entry["source_id"] == technique
    assert entry["dropped_links"] == {}


@pytest.mark.unit
def test_a_scalar_where_a_list_belongs_is_not_reported_as_nothing_offered(
    app_client,
) -> None:
    """A payload shape the prompt did not ask for is a FINDING, not an absence.

    `raw.get("linked_techniques") or []` turned a bare string into an empty
    list, so a model answering `"T1078"` instead of `["T1078"]` looked exactly
    like a model that proposed nothing -- the same collapse one level up, in the
    line that was supposed to be reading the payload.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Scalar links", source_id=technique)[:-1]
        + f', "linked_techniques": "{technique}", "linked_controls": []}}'
    )
    body = _generate(c, provider, bearer, cid, payload)
    entry = body["entries"][0]

    assert entry["linked_techniques"] == []
    assert entry["dropped_links"] == {"linked_techniques": [technique]}, (
        "the value must be REPORTED even though it names a real technique -- "
        "the shape is wrong, and silently unwrapping it would be a second "
        "undeclared transformation"
    )


@pytest.mark.unit
def test_the_counters_still_read_true_when_the_register_is_fetched_later(
    app_client,
) -> None:
    """What the migration bought, and the reason a counter alone was not enough.

    The drop counters are derived from the stored entries, so the consultant
    who opens the register a week later gets the same answer to "was linkage
    proposed and lost?" as the run did.

    **This docstring used to end by contrasting them with `batches_*`, which it
    said "describe a RUN and are 0 on a read-back".** That was true of the
    design when it was written and #372 changed it: a `0` on a read-back is a
    positive claim that nothing failed, made about a run nobody recorded, and
    it was destroying the partial-synthesis warning on export and reload. The
    tally is persisted now and read back by `_serialize`, so BOTH pairs survive
    the fetch and the contrast this test was built around no longer exists.

    The assertion below was changed rather than deleted, and it is STRONGER
    than the one it replaces: it now pins the read-back instead of pinning the
    absence of one. CI caught it -- three local attempts at this file were lost
    or reaped, and the merge gate is what actually ran it.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    payload = _entries_payload(
        _entry("Lost them all", source_id=technique)[:-1]
        + ', "linked_techniques": ["T9999"], "linked_controls": []}'
    )
    generated = _generate(c, provider, bearer, cid, payload)

    later = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert later.status_code == 200, later.text
    body = later.json()

    assert body["entries_with_dropped_links"] == generated["entries_with_dropped_links"] == 1
    assert body["entries_unlinked_after_drops"] == generated["entries_unlinked_after_drops"] == 1
    assert body["entries"][0]["dropped_links"] == {"linked_techniques": ["T9999"]}
    # And the batch tally survives the read-back too, since #372 persisted it.
    # One run, one batch: `latest` must report it rather than defaulting to a
    # claim that nothing failed.
    assert body["batches_total"] == generated["batches_total"] == 1
    assert body["batches_failed"] == generated["batches_failed"] == 0


# ---------------------------------------------------------------------------
# #122 -- the audit row counted the INPUT and never the output.
#
#     details = {"findings": len(findings), "batches_total": ..., ...}
#
# A run that received 137 findings and persisted zero entries wrote a row
# indistinguishable from one that persisted 137. CLAUDE.md: a success record
# must be written where the success is; this one was written where the input
# is. It compounds with the enum drift filed alongside it -- when a live run
# stores entries with no likelihood, impact or tier, the audit row is the record
# that would have to disagree with reality for anyone to notice, and it could
# not, because it never measured the output.
#
# Read through `/admin/audit-entries` for the reason `_generated_audit` gives:
# the claim is that a discard is REPORTED somewhere a person reaches, and a test
# that queries the table proves the write and not the claim.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_audit_row_says_what_was_written_not_only_what_arrived(app_client) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Kept", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}',
        '{"description": "no title at all", "axis": "detection"}',
    )
    body = _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert details["entries_received"] == 2
    assert details["entries_written"] == 1
    assert details["discarded_entries"] == {"no_title": 1}
    assert len(body["entries"]) == 1


@pytest.mark.unit
def test_a_run_that_persisted_nothing_is_distinguishable_from_one_that_did(
    app_client,
) -> None:
    """THE HEADLINE, and the two halves have to be asserted together.

    `findings` alone cannot separate them: it is the same number either way.
    What separates them is `entries_written`, and the discard map is what says
    WHY -- a run that wrote nothing because the model sent nothing and a run
    that wrote nothing because every entry was malformed are different faults
    with different fixes.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        '{"description": "one", "axis": "detection"}',
        '{"description": "two", "axis": "detection"}',
    )
    body = _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert body["entries"] == []
    assert details["findings"] > 0, "the INPUT is non-zero, which is the whole point"
    assert details["entries_received"] == 2
    assert details["entries_written"] == 0
    assert details["discarded_entries"] == {"no_title": 2}


@pytest.mark.unit
def test_a_non_object_entry_is_counted_under_its_own_reason(app_client) -> None:
    """Two causes, kept apart, because they are different things to fix.

    A payload shape the prompt did not ask for is a prompt problem. An entry
    that is shaped right and has no title is a content problem. Collapsing them
    into one number tells a consultant neither.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload('"just a string"', '{"description": "no title"}')
    _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert details["discarded_entries"] == {"not_an_object": 1, "no_title": 1}
    assert details["entries_received"] == 2
    assert details["entries_written"] == 0
    # The non-object is dropped at the BATCH MERGE, a layer above the per-entry
    # loop, which is why `entries_received` is seeded from the merge's tally
    # rather than counted from the loop alone. Without that seeding this reads
    # 1 of 1 accounted for, over a run where the model sent two things.
    assert details["entries_received"] == details["entries_written"] + sum(
        details["discarded_entries"].values()
    ), "every entry the model sent must be either written or counted as discarded"


@pytest.mark.unit
def test_a_clean_run_records_no_discards_rather_than_omitting_the_key(
    app_client,
) -> None:
    """THE PASSING STATE. An empty map is a positive claim; a missing key is not.

    Without this the counters are only ever observed non-zero, and a reader
    cannot tell "nothing was discarded" from "this run predates the counting".
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Clean", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}'
    )
    _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert details["discarded_entries"] == {}
    assert details["entries_received"] == details["entries_written"] == 1
    assert details["entries_received"] == details["entries_written"] + sum(
        details["discarded_entries"].values()
    ), "the invariant must hold on a clean run too, not only where something was lost"


@pytest.mark.unit
def test_a_row_dropped_between_add_and_flush_is_recorded(app_client) -> None:
    """The read-back must READ, and the mismatch must be loud.

    This is the test the first version of the read-back did not have, and its
    absence was the finding: substituting `entries_written = entries_total` --
    a tally computed in the same loop three blocks above -- left all four tests
    above green, because each of them asserts a run where the two agree. The
    accounting was pinned; the SOURCE of `entries_written` was not, so an
    "avoid a round trip" refactor could have removed the whole point of it
    without turning anything red.

    It also settles the reachability question rather than arguing it. The
    read-back's comment says no current writer can lose a row between the
    `db.add` and the flush, and names a `before_flush` listener on `RiskEntry`
    as one of the ordinary changes that would make it reachable again. This
    installs exactly that listener. The state is constructible; nothing in the
    application constructs it today; and the guard fires when it happens.

    The listener is attached to the `Session` CLASS, which is every session in
    the process, so it is guarded to one entry and removed in a `finally` --
    an escaped listener would silently drop a row from every later test in the
    file, which is a worse defect than the one under test.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session as OrmSession

    from app.models.risk_register import RiskEntry as _RiskEntry

    dropped: list[object] = []

    def _drop_one_before_flush(session, flush_context, instances) -> None:
        if dropped:
            return
        for obj in list(session.new):
            if isinstance(obj, _RiskEntry):
                session.expunge(obj)
                dropped.append(obj)
                return

    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Kept", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}',
        _entry("Lost", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}',
    )

    event.listen(OrmSession, "before_flush", _drop_one_before_flush)
    try:
        body = _generate(c, provider, bearer, cid, payload)
    finally:
        event.remove(OrmSession, "before_flush", _drop_one_before_flush)

    assert dropped, "the listener never fired; this test proved nothing"

    # #330, THROUGH THE SURFACE. The assertions below read the AUDIT ROW, which
    # is fed from the local `entries_total` variable and never touches
    # provenance -- so deleting the provenance write and the `_serialize`
    # read-back left every one of them GREEN. Measured, not argued.
    #
    # That is #244 instance 1 verbatim, and this file documents it twenty lines
    # down: "the only assertion touching `excluded_inputs` was on the POST
    # /generate response -- the one path that passes the value in explicitly
    # and never reaches the new code."
    #
    # The RESPONSE is the only thing the persistence exists to produce, so it
    # is what gets asserted.
    assert body["entries_total"] == 1, body
    assert body["entries_intended"] == 2, (
        "the generate response must carry the INTENDED tally; it is the "
        "operand the client-facing banner divides by, and without it a "
        "register that lost a row reads as complete"
    )

    # AND ON RELOAD, because the value is persisted precisely so a register
    # read back next week says the same thing. A generate-response assertion
    # alone would pass over a value that never reached storage.
    latest = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert latest.status_code == 200, latest.text
    assert latest.json()["entries_intended"] == 2, latest.json()
    assert latest.json()["entries_total"] == 1, latest.json()

    details = _generated_audit(c, bearer)
    assert details["entries_intended"] == 2, "the loop intended two rows"
    assert details["entries_written"] == 1, (
        "entries_written must come from the TABLE. It reports "
        f"{details['entries_written']} for a run where one of two adds was "
        "expunged before the flush — which is the value the loop's own tally "
        "carries, not the value the database holds."
    )
    assert details["entries_write_check"] == "MISMATCH", (
        "a disagreement between what was added and what landed must be stated "
        "in the audit row, not left for a reader to compute from two numbers."
    )


@pytest.mark.unit
def test_a_run_where_nothing_was_lost_says_so_rather_than_staying_silent(
    app_client,
) -> None:
    """The other half. "They agreed" and "nobody compared" must not be the
    same absence — an audit row carrying no verdict reads as the first and
    means the second, which is the shape this whole issue is about.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)

    payload = _entries_payload(
        _entry("Clean", source_id=technique)[:-1]
        + ', "linked_techniques": [], "linked_controls": []}'
    )
    _generate(c, provider, bearer, cid, payload)
    details = _generated_audit(c, bearer)

    assert details["entries_write_check"] == "agreed"
    assert details["entries_intended"] == details["entries_written"] == 1


# ---------------------------------------------------------------------------
# #244 instance 1 -- the read-back, and the fail-closed default.
#
# These exist because the review found the PR's actual fix had NO test at any
# level. `_serialize`'s `"excluded" in stored` branch could be deleted and the
# whole suite stayed green, because the only assertion touching
# `excluded_inputs` was on the POST /generate response -- the one path that
# passes the value in explicitly and never reaches the new code. The vitest
# that covers the false state supplies the flag directly in a mock, so it never
# reaches `_serialize` either.
#
# CLAUDE.md: an assertion that goes red when the guard is deleted, EXERCISED
# THROUGH THE SURFACE THE CLIENT ACTUALLY REACHES. For this fix that surface is
# `GET .../register/latest`, because the defect was that a reload returned `[]`.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_withheld_set_survives_a_reload(app_client) -> None:
    """THE HEADLINE. `latest` must return what storage holds.

    The defect was that `excluded_inputs` reached exactly one HTTP response and
    died on reload. Asserting it on `generate` proves nothing -- that handler
    passes the list in directly, so it is green whether or not `_serialize`
    reads anything back.

    The stored provenance is MUTATED here rather than produced at generate.
    **An earlier version of this docstring justified that with "the resolver
    filters on approved/released, so no register generated today carries a
    non-empty `excluded`", and that is FALSE.** It is true of `inputs`;
    `excluded` is a separate argument sourced from `g.not_finalized` and passes
    through no resolver at all --
    `test_an_unapproved_OPTIONAL_input_does_not_block_generation` generates
    exactly such a register. The sentence was imported wholesale from
    `test_export_refuses_a_register_built_from_unapproved_work`, where it IS
    true, and in doing so argued away the test that would have closed the loop.

    The real reason to keep this one is that it pins the READ in isolation, on
    a value no generate produced -- two exact literals that appear nowhere else
    in the pairing, so it cannot be satisfied by `inputs`, by a wholesale dict
    (which fails `list[str]` validation) or by a stale copy. Writing the row is
    building the WORLD; the step under test is the read-back.

    The WRITE half is covered by
    `test_the_withheld_set_is_persisted_by_generate_not_just_returned`, which
    is the one the false sentence talked me out of.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    stored = dict(reg.provenance or {})
    stored["excluded"] = ["the CSF assessment", "the Tech Debt review"]
    reg.provenance = stored
    db.add(reg)
    db.commit()

    r = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excluded_inputs"] == ["the CSF assessment", "the Tech Debt review"], (
        "the reload lost the withheld set -- `_serialize` is not reading "
        "`provenance['excluded']` back, which is #244 instance 1 verbatim"
    )
    assert body["excluded_inputs_recorded"] is True, (
        "the server looked and found a record, so it must say so; reporting "
        "False here is indistinguishable from a register that predates 0047"
    )


@pytest.mark.unit
def test_a_register_that_predates_provenance_says_nobody_looked(app_client) -> None:
    """The OTHER half, and the one that must not fail open.

    A NULL `provenance` is a fact about what was recorded. Defaulting it to
    `True` would render a pre-0047 register identically to one where the server
    looked and found nothing excluded -- a clean bill of health over the one
    population nobody can re-check. Missing data defaults to UNCONFIRMED.

    Asserted through the route rather than against `_serialize` directly: the
    claim is about what a consultant's page receives.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    reg.provenance = None  # a pre-0047 row
    db.add(reg)
    db.commit()

    r = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excluded_inputs_recorded"] is False, (
        "a NULL provenance must report that nothing is on file, not that "
        "nothing was excluded -- those are different claims and only one of "
        "them is about the assessments"
    )
    assert body["excluded_inputs"] == []


@pytest.mark.unit
def test_the_withheld_set_is_persisted_by_generate_not_just_returned(
    app_client,
) -> None:
    """The WRITE half, which had no test and whose absence was argued for.

    `generate` used to compute `g.not_finalized`, store it via
    `_provenance_snapshot`, AND pass the same expression to `_serialize`. Two
    answers to one question. Every assertion on the generate response was green
    off the parameter, so the third argument to `_provenance_snapshot` was
    replaceable with `[]` and nothing went red — and the resulting reload
    reported `excluded_inputs: []` with `excluded_inputs_recorded=True`. A
    positive certificate that the server looked and nothing was withheld is
    WORSE than the empty list #244 was filed for.

    `_serialize` no longer takes the parameter, so this asserts the same
    property twice over: the generate response is itself a read-back, and
    `latest` reads it again in a new request.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}

    # A THIRD assessment, started and not approved. CSF here, because ATT&CK +
    # ZT already satisfy the unlock rule without it -- so generation proceeds
    # and the CSF assessment is withheld and NAMED. Same setup as
    # `test_an_unapproved_OPTIONAL_input_does_not_block_generation`.
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    csvc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    c.post(f"/csf/services/{csvc.json()['id']}/assessments", headers=h)

    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    gen = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert gen.status_code == 201, gen.text
    withheld = gen.json()["excluded_inputs"]
    assert withheld, (
        "this test needs a run that actually withheld something -- if the "
        "fixture stopped producing an unfinalized input it proves nothing"
    )

    r = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert r.status_code == 200, r.text
    assert r.json()["excluded_inputs"] == withheld, (
        "generate reported a withheld set that was never STORED -- the "
        "snapshot's third argument is not carrying it"
    )
    assert r.json()["excluded_inputs_recorded"] is True


@pytest.mark.unit
def test_export_allows_the_seeded_shape_a_finalized_register_with_no_inputs_key(
    app_client,
) -> None:
    """THE SEEDED REGISTER'S OWN SHAPE, and the one no other test generates.

    `seed_demo.py` writes `provenance={"excluded": []}` -- a dict, with no
    `inputs` key, deliberately, because it does not go through
    `_provenance_snapshot`. Every OTHER register in the system is either NULL
    (pre-0047) or carries a full snapshot, so this third shape exists exactly
    once and only on the demo path.

    That is why it needs its own test rather than being caught in passing: an
    input that exists in exactly one place, written by a script no spec drives,
    is the input no test generates by accident. `s8` downloads the artifacts
    the seed wrote and never POSTs export; `s30` generates a fresh register
    first, so it always has a full snapshot. The only register with the broken
    shape was the one nothing exercised, and CI was green over it.

    The defect this pins: the `finalized_at` carve-out was nested INSIDE the
    `_prov is None` branch, so a dict lacking `inputs` never reached it and a
    finalized, already-delivered register began refusing its own re-export with
    409 `register_predates_provenance`. The comment above the guard asserted
    the opposite -- "the seeded register is finalized, so it exports through
    the carve-out above either way and the blast radius is zero" -- which was
    true of the NULL case and false of this one.

    Re-exporting an already-finalized register protects nobody: the certificate
    was issued when it was finalized, and refusing now only breaks a working
    path. That is the same reasoning the NULL branch already applies; this
    makes the two agree.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    # Exactly what the seed writes -- a dict, `excluded` present, `inputs` absent.
    reg.provenance = {"excluded": []}
    reg.finalized_at = datetime.now(UTC)
    db.add(reg)
    db.commit()

    r = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert r.status_code == 200, (
        "a FINALIZED register whose provenance dict lacks `inputs` -- the shape "
        "`seed_demo.py` writes -- must still re-export. It was already "
        "delivered; refusing now breaks the demo path and certifies nothing. "
        f"got {r.status_code}: {r.text}"
    )


@pytest.mark.unit
def test_export_still_refuses_that_shape_when_it_was_never_finalized(
    app_client,
) -> None:
    """THE OTHER HALF, without which the test above is a hole rather than a fix.

    The carve-out is for a register that was ALREADY delivered. An UNFINALIZED
    register whose provenance records what was excluded but not what was used
    still cannot be certified, and must still be refused -- otherwise widening
    the branch above would turn a real guard into a pass for every register
    that omits `inputs`.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    reg.provenance = {"excluded": []}
    reg.finalized_at = None
    db.add(reg)
    db.commit()

    r = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "register_inputs_not_recorded", r.text


@pytest.mark.unit
def test_a_null_excluded_value_is_not_read_as_nothing_was_withheld(app_client) -> None:
    """THE FOURTH STATE, and the mirror of the export guard in this same PR.

    `export` was taught that a provenance dict with no `inputs` key is NOT
    "recorded, all approved" -- it is a state the enumeration did not cover.
    `_serialize` still did the mirror-image thing for `excluded`: the key
    PRESENT but null satisfied `"excluded" in stored`, and `or []` collapsed it
    to an empty list with `excluded_inputs_recorded=True`.

    That is a positive certificate -- "the server looked and nothing was
    withheld" -- manufactured out of a value that records nothing. This PR's
    own comment calls that outcome worse than the bare `[]` #244 was filed for,
    and then left the branch that produces it one function below.

    The key-ABSENT case was already fail-closed. Only key-present-but-null was
    not, so the two halves of one dict disagreed about what absence means.

    UNREACHABLE TODAY, and said so rather than dressed up: `_provenance_snapshot`
    always writes a list and the seed writes `[]`. No current writer produces
    this. It is kept as a RATCHET for the same reason the export guard beside it
    is -- the seed is proof that hand-written provenance dicts are ordinary here,
    and the seed is what produced the export defect this PR just fixed.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    reg.provenance = {"excluded": None, "inputs": []}
    db.add(reg)
    db.commit()

    body = c.get(f"/risk/clients/{cid}/register/latest", headers=bh).json()
    assert body["excluded_inputs_recorded"] is False, (
        "a null `excluded` records nothing, so it must report that nobody "
        "looked -- not that the server looked and withheld nothing. Those are "
        "different claims and only one of them is about the assessments."
    )
    assert body["excluded_inputs"] == []


def _seed_csf_answer_at_tier(c, bearer: str, cid: str, *, tier: int) -> str:
    """One APPROVED CSF assessment with a single subcategory at `tier`.

    Approved deliberately: `_finalized_for_synthesis` filters on approved or
    released, so a draft contributes no findings at all and every assertion
    below would pass over an empty list.
    """
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"})
    assert svc.status_code in (200, 201), svc.text
    svc_id = svc.json()["id"]
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    ans = latest["answers"][0]
    r = c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": tier})
    assert r.status_code == 200, r.text

    # A SECOND subcategory, deliberately at tier 1 -- below every target the
    # intake schema allows (`ge=2`). It exists so the finding set is never
    # EMPTY, which is what lets a `not in` assertion mean "this code was
    # excluded" rather than "nothing was produced".
    #
    # Measured, and this is why it is here: without it,
    # `test_a_control_at_the_clients_target_is_not_a_finding` asserted
    # `code not in []` and passed over a run that produced no findings at all.
    floor = latest["answers"][1]
    r2 = c.patch(f"/csf/answers/{floor['id']}", headers=h, json={"maturity_tier": 1})
    assert r2.status_code == 200, r2.text
    ap = c.post(f"/csf/assessments/{a.json()['id']}/approve", headers=h)
    assert ap.status_code == 200, ap.text
    return ans["subcategory_code"]


# ---------------------------------------------------------------------------
# #84 -- the findings baseline.
#
# Every finding is "current is below target", so the TARGET decides whether a
# row exists at all. It was a hardcoded 3 for CSF and a hardcoded fallback of 3
# for ZT, regardless of what the client engaged for -- so a client targeting
# tier 2 was handed findings for controls already AT their goal, and one
# targeting tier 4 got a register that stopped looking one tier early.
#
# A register built on the wrong baseline is not visibly wrong. It has the right
# shape, plausible counts, and nothing a reader can use to tell which tier it
# measured against. That is why these assert the FINDING SET changes with the
# target, rather than asserting the target is stored somewhere.
# ---------------------------------------------------------------------------


def _set_csf_target(cid: str, tier: object) -> None:
    """Write the client's engagement target straight onto the ServiceRequest.

    Direct SQL rather than driving intake: the intake route is a different
    surface with its own validation, and what is under test here is which
    number `_gather_findings` COMPARES AGAINST. Building the world, not
    performing the step under test.
    """
    from app.models.client import Client
    from app.models.service import Service
    from app.models.service_request import ServiceRequest

    db = _session()
    svc = (
        db.execute(
            select(Service).where(Service.client_id == uuid.UUID(cid), Service.kind == "nist_csf")
        )
        .scalars()
        .first()
    )
    assert svc is not None, "no CSF service on this client"
    if svc.source_request_id is None:
        from app.models.user import User

        client = db.get(Client, uuid.UUID(cid))
        requester = db.execute(select(User).limit(1)).scalars().first()
        assert requester is not None, "no user to attribute the request to"
        sr = ServiceRequest(
            client_id=client.id,
            service_type="NIST_CSF",
            requested_by=requester.id,
        )
        db.add(sr)
        db.flush()
        svc.source_request_id = sr.id
    sr = db.get(ServiceRequest, svc.source_request_id)
    sr.csf_target_tier = tier
    db.add(sr)
    db.add(svc)
    db.commit()


def _all_findings(cid: str) -> list[dict]:
    """Every finding, regardless of kind -- so a `not in` assertion can prove
    the thing is EXCLUDED rather than that nothing was produced."""
    from app.routes.risk import _gather_findings

    db = _session()
    findings, _t, _c, _targets, _scopes = _gather_findings(db, uuid.UUID(cid))
    return findings


def _csf_finding_codes(cid: str) -> list[str]:
    from app.routes.risk import _gather_findings

    db = _session()
    findings, _techs, _controls, _targets, _scopes = _gather_findings(db, uuid.UUID(cid))
    return [f["source_id"] for f in findings if f["kind"] == "csf"]


def _csf_targets(cid: str) -> dict:
    from app.routes.risk import _gather_findings

    db = _session()
    _f, _t, _c, targets, _scopes = _gather_findings(db, uuid.UUID(cid))
    return targets.get("csf", {})


@pytest.mark.unit
def test_a_control_at_the_clients_target_is_not_a_finding(app_client) -> None:
    """THE DEFECT, from the side a client feels.

    A subcategory answered at tier 2, for a client who engaged for tier 2, is
    AT its goal. The old code compared against a hardcoded 3 and reported it as
    a gap -- a finding in the client's Risk Register for work they never
    committed to doing.

    Goes RED against the old baseline: `2 < 3` is true, so the code appears.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    code = _seed_csf_answer_at_tier(c, bearer, cid, tier=2)

    _set_csf_target(cid, 2)
    # APPEAR before ABSENT. The `not in` below is genuinely discriminating --
    # if the target failed to write, it would resolve to the default 3, `2 < 3`
    # would put the code back in the list and this goes red -- but that
    # reasoning is invisible at the site, so it is asserted rather than
    # inferred.
    assert _csf_targets(cid) == {"target": 2, "source": "client"}
    # APPEAR BEFORE ABSENT. `not in` is satisfied by an EMPTY list, so it
    # would pass over a `_gather_findings` that returned nothing at all --
    # measured, by forcing `return []` and watching this test stay green while
    # its positive twin went red. The ATT&CK gap and the stage-1 ZT capability
    # that `_seed_attack_and_zt` creates are unaffected by the CSF target, so
    # findings MUST exist; what must not is this code among them.
    all_codes = [f["source_id"] for f in _all_findings(cid)]
    assert all_codes, "no findings at all -- the absence below would be vacuous"
    assert code not in _csf_finding_codes(cid), (
        "a control AT the client's engagement target is not a gap; it was "
        "reported as one because the comparison used a hardcoded tier 3"
    )


@pytest.mark.unit
def test_a_control_below_a_higher_target_is_still_a_finding(app_client) -> None:
    """THE OTHER HALF, without which the fix above is just 'report less'.

    Same stored answer, a client targeting tier 4. The control IS below goal
    and must appear. The old code stopped at 3 and missed the tier-3 shortfall
    entirely for every client aiming higher than the hardcode.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    code = _seed_csf_answer_at_tier(c, bearer, cid, tier=3)

    _set_csf_target(cid, 4)
    assert code in _csf_finding_codes(cid), (
        "a control BELOW the client's target must be reported; the old "
        "hardcoded 3 could never see a tier-3 answer as a gap"
    )


@pytest.mark.unit
def test_the_target_and_its_source_are_recorded_beside_the_findings(app_client) -> None:
    """The baseline is recorded, so the next wrong one is falsifiable.

    Asserts the SOURCE too, not just the number: "the client chose nothing" and
    "the client's choice could not be used" resolve to the same number and are
    different facts. A run that fell back to the engine default must not be
    indistinguishable from one that honoured a client's explicit choice.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_csf_answer_at_tier(c, bearer, cid, tier=1)

    _set_csf_target(cid, 2)
    assert _csf_targets(cid) == {"target": 2, "source": "client"}

    _set_csf_target(cid, None)
    fell_back = _csf_targets(cid)
    # The literal 3, taken from the SPEC -- CSF's engine default is Tier 3
    # (Repeatable) -- and not imported from `DEFAULT_TARGET_TIER`. A test that
    # reads its expected value out of the module under test agrees with it by
    # construction, and `check_test_integrity` flags exactly that import.
    #
    # A first draft wrote `assert fell_back["target"] != 2 or fell_back["source"]
    # == "default"`. The right operand was asserted TRUE on the line above, so
    # the whole thing was a tautology -- it passed for `None`, for `2`, for a
    # string. It was the only assertion on the fallback NUMBER and it asserted
    # nothing about it.
    assert fell_back == {"target": 3, "source": "default"}, fell_back


@pytest.mark.unit
def test_an_unusable_stored_target_is_named_rather_than_silently_defaulted(
    app_client,
) -> None:
    """A stored value that is not a tier is a THIRD state.

    `resolve_target_tier` separates "chose nothing" from "chose something
    unusable" because the second is answerable by re-asking the client. If this
    collapses to `default`, that distinction is lost at the one place it was
    recorded -- and the register silently uses a target nobody picked.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_csf_answer_at_tier(c, bearer, cid, tier=1)

    _set_csf_target(cid, 99)
    assert _csf_targets(cid)["source"] == "client_out_of_range"


@pytest.mark.unit
def test_the_baseline_reaches_the_audit_row_a_consultant_reads(app_client) -> None:
    """#84's disclosure, asserted through the surface rather than the tuple.

    The three tests above read `target_sources` out of `_gather_findings`
    directly. That proves the value is COMPUTED and says nothing about whether
    it is RECORDED -- delete `"targets": target_sources` from the audit
    `details` and every one of them still passes, because none of them looks
    at the audit row.

    This repo's rule: an assertion that goes red when the guard is deleted,
    exercised through the surface someone actually reaches. For a disclosure
    that surface is `/admin/audit-entries`, which is what `_generated_audit`
    reads -- and its own docstring makes this argument: a test that reads the
    database proves the write and not the claim.

    Asserts the SOURCE as well as the number, because a run that fell back to
    the engine default must not be indistinguishable from one that honoured a
    client's explicit choice.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    details = _generated_audit(c, bearer)
    assert "targets" in details, (
        "the baseline every finding was compared against must be recorded "
        "beside the findings, or the next wrong one is not falsifiable"
    )
    zt = details["targets"].get("zt")
    assert zt is not None, details["targets"]
    assert set(zt) == {"target", "source"}, zt
    assert isinstance(zt["target"], int), zt
    assert zt["source"] in (
        "client",
        "default",
        "client_out_of_range",
        "client_unparseable",
    ), zt


def _set_zt_stage(cid: str, capability: str, stage: int) -> None:
    """A capability's CURRENT stage, set through the session.

    Not through `PATCH /zt/answers/{id}`: `_seed_attack_and_zt` APPROVES the
    assessment, and an approved one refuses the patch with 409. Approval is
    load-bearing for these tests -- `_finalized_for_synthesis` filters on it,
    so a draft contributes no findings and every assertion would pass over an
    empty list.
    """
    from app.models.zt_assessment import ZtAnswer, ZtAssessment

    db = _session()
    ans = (
        db.execute(
            select(ZtAnswer)
            .join(ZtAssessment, ZtAnswer.assessment_id == ZtAssessment.id)
            .where(ZtAnswer.capability_code == capability)
            .order_by(ZtAssessment.version.desc())
        )
        .scalars()
        .first()
    )
    assert ans is not None, f"no answer for {capability}"
    ans.maturity_stage = stage
    db.add(ans)
    db.commit()


def _set_zt_target(cid: str, stage: object, *, kind: str = "zero_trust_cisa") -> None:
    """The client's ZT engagement target, written onto the ServiceRequest."""
    from app.models.client import Client
    from app.models.service import Service
    from app.models.service_request import ServiceRequest
    from app.models.user import User

    db = _session()
    svc = (
        db.execute(select(Service).where(Service.client_id == uuid.UUID(cid), Service.kind == kind))
        .scalars()
        .first()
    )
    assert svc is not None, f"no {kind} service on this client"
    if svc.source_request_id is None:
        client = db.get(Client, uuid.UUID(cid))
        requester = db.execute(select(User).limit(1)).scalars().first()
        sr = ServiceRequest(
            client_id=client.id,
            service_type=kind.upper(),
            requested_by=requester.id,
        )
        db.add(sr)
        db.flush()
        svc.source_request_id = sr.id
    sr = db.get(ServiceRequest, svc.source_request_id)
    sr.zt_target_stage = stage
    db.add(sr)
    db.add(svc)
    db.commit()


def _zt_finding_codes(cid: str) -> list[str]:
    from app.routes.risk import _gather_findings

    db = _session()
    findings, _t, _c, _targets, _scopes = _gather_findings(db, uuid.UUID(cid))
    return [f["source_id"] for f in findings if f["kind"] == "zt"]


def _zt_targets(cid: str) -> dict:
    from app.routes.risk import _gather_findings

    db = _session()
    _f, _t, _c, targets, _scopes = _gather_findings(db, uuid.UUID(cid))
    return targets.get("zt", {})


@pytest.mark.unit
def test_a_zt_capability_below_a_higher_client_target_is_a_finding(app_client) -> None:
    """THE ZT HALF, which reverting left entirely green.

    `_seed_attack_and_zt` sets one capability to stage 1 and stores no
    engagement target, so `resolve_target_stage(fw, None)` returns
    `(3, "default")` -- byte-identical to the old hardcoded 3. Every existing
    register test is blind to this half of the fix: MEASURED, by reverting
    `else zt_target` to `else 3` and watching the whole file stay green.

    This engages for stage 4 on CISA, whose ladder has four, with a capability
    at 3. The old code stopped at 3 and could never see it.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    _technique, capability = _seed_attack_and_zt(c, bearer, cid)

    # Put the capability AT the old hardcoded target, so only a higher client
    # target can make it a finding.
    _set_zt_stage(cid, capability, 3)

    _set_zt_target(cid, 4)
    assert _zt_targets(cid) == {"target": 4, "source": "client"}
    assert capability in _zt_finding_codes(cid), (
        "a capability BELOW the client's stage-4 target must be reported; the "
        "old hardcoded 3 could never see a stage-3 answer as a gap"
    )


@pytest.mark.unit
def test_a_zt_capability_at_the_client_target_is_not_a_finding(app_client) -> None:
    """THE OTHER DIRECTION, without which the above is just 'report more'."""
    c, _provider = app_client
    bearer, cid = _admin(c)
    _technique, capability = _seed_attack_and_zt(c, bearer, cid)

    _set_zt_stage(cid, capability, 2)

    _set_zt_target(cid, 2)
    assert _zt_targets(cid) == {"target": 2, "source": "client"}
    # APPEAR BEFORE ABSENT -- same reasoning as the CSF twin. The ATT&CK gap
    # is independent of the ZT target, so the finding set cannot be empty.
    assert _all_findings(cid), "no findings at all -- the absence below would be vacuous"
    assert capability not in _zt_finding_codes(cid), (
        "a capability AT the client's target is not a gap; the old hardcoded 3 "
        "reported it as one"
    )


@pytest.mark.unit
def test_a_stored_stage_the_framework_does_not_have_is_named_not_used(app_client) -> None:
    """THE FRAMEWORK ARGUMENT, which the commit calls load-bearing.

    CISA ZTMM has four stages; DoD ZTRA has three. A stored 4 is a legitimate
    CISA target and is not a stage DoD has at all -- so the SAME integer must
    resolve differently depending on which framework asks, and that is the
    whole reason `resolve_target_stage` takes the framework.

    It also pins the enum conversion. `ZtAssessment.framework` is `ZtFramework`
    and the engine takes `ZtFrameworkCode` -- two StrEnum classes whose values
    coincide today. If someone converts `stage_definitions`' `==` to `is`, DoD
    silently gets the CISA ladder, a stored 4 resolves `client` instead of
    out-of-range, and this test goes red.
    """
    c, _provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}

    # A DoD service alongside, and a stage-4 target it cannot honour.
    dsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_dod", "title": "ZT DoD"})
    assert dsvc.status_code in (200, 201), dsvc.text
    da = c.post(f"/zt/services/{dsvc.json()['id']}/assessments", headers=h)
    assert da.status_code in (200, 201), da.text
    assert c.post(f"/zt/assessments/{da.json()['id']}/approve", headers=h).status_code == 200

    _set_zt_target(cid, 4, kind="zero_trust_dod")
    resolved = _zt_targets(cid)
    assert resolved["source"] == "client_out_of_range", (
        "stage 4 is not a stage DoD ZTRA has, so it must be NAMED as unusable "
        f"rather than silently applied. got {resolved}"
    )
    assert resolved["target"] == 3, resolved


@pytest.mark.unit
def test_the_batch_tally_is_persisted_by_generate_not_just_returned(app_client) -> None:
    """THE WRITE HALF (#372).

    The tally reached exactly one HTTP response for one revision, which is
    `excluded_inputs`' defect repeated four fields away from its own
    postmortem. Asserting it on the `generate` RESPONSE proves nothing: that
    handler passes the numbers straight into `_serialize`, so it is green
    whether or not anything was stored.

    So this reads the DATABASE, not the response. Writing the row is not the
    step under test here -- `generate` doing the write is exactly the claim.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    recorded = (reg.provenance or {}).get("batches")
    assert isinstance(recorded, dict), (
        "generate did not persist the batch tally, so `export` and `latest` "
        "have nothing to read back and the INCOMPLETE banner dies with the "
        "response -- #372, and #244 instance 1 verbatim"
    )
    assert isinstance(recorded.get("total"), int)
    assert isinstance(recorded.get("failed"), int)


@pytest.mark.unit
def test_the_batch_tally_survives_a_reload_and_an_export(app_client) -> None:
    """THE READ HALF, on BOTH paths that erased it.

    `export` is the one that mattered: the component assigns its response to
    state wholesale, so a response lacking the tally destroyed the "this
    register is INCOMPLETE -- regenerate before exporting" warning at the exact
    moment the consultant produced the deliverable. `latest` lost it on a
    reload.

    The stored value is MUTATED here rather than produced by a failing batch,
    for the reason the withheld-set test gives: a literal that no generate in
    this suite produces cannot be satisfied by a stale copy or by the caller's
    own arguments. Building the world is not performing the step.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    stored = dict(reg.provenance or {})
    stored["batches"] = {"total": 17, "failed": 5}
    reg.provenance = stored
    db.add(reg)
    db.commit()

    r = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert r.status_code == 200, r.text
    assert (r.json()["batches_total"], r.json()["batches_failed"]) == (17, 5), (
        "the reload lost the tally -- `_serialize` is not reading " "`provenance['batches']` back"
    )

    e = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert e.status_code in (200, 201), e.text
    assert (e.json()["batches_total"], e.json()["batches_failed"]) == (17, 5), (
        "EXPORT lost the tally, which is the defect itself: the admin page "
        "assigns this response to state, so the INCOMPLETE banner is erased "
        "by the very click it warns against"
    )


@pytest.mark.unit
def test_a_register_with_no_recorded_tally_says_nobody_counted(app_client) -> None:
    """The half that must not fail open.

    A register generated before the tally was persisted has no record. The
    first revision of this field defaulted it to `0`, which reports "zero
    batches failed" -- a POSITIVE claim about a run nobody observed, over the
    one population that cannot be re-checked. Missing data defaults to
    UNCONFIRMED.

    `null` is what the wire must carry, and it can: no `exclude_none` exists
    anywhere in `apps/api`, so the key is serialised rather than omitted, and a
    consumer can tell "nobody counted" from "counted, none failed".
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))
    assert c.post(f"/risk/clients/{cid}/register/generate", headers=bh).status_code == 201

    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(select(RiskRegister).where(RiskRegister.client_id == uuid.UUID(cid)))
        .scalars()
        .first()
    )
    stored = dict(reg.provenance or {})
    stored.pop("batches", None)
    reg.provenance = stored
    db.add(reg)
    db.commit()

    body = c.get(f"/risk/clients/{cid}/register/latest", headers=bh).json()
    assert body["batches_total"] is None, (
        "a register with no recorded tally reported a number, so a run nobody "
        "observed is being described as complete"
    )
    assert body["batches_failed"] is None
    assert "batches_total" in body, (
        "the key must be PRESENT and null -- an omitted key cannot be "
        "distinguished from an old client, and the web type is `number | null`"
    )


@pytest.mark.unit
def test_the_batch_keys_are_always_present_on_the_wire(app_client) -> None:
    """THE TYPE AND THE WIRE, PINNED TO EACH OTHER (#372).

    The admin banner's predicate is `batches_failed !== null && > 0`. That is
    correct against `number | null`, and the `| null` was chosen by measuring
    that no `exclude_none` exists anywhere in `apps/api`.

    But the predicate is SHAPED like a presence test, and a presence test is
    what made #317 invisible: if these keys ever stop being serialised,
    `undefined > 0` is false and the INCOMPLETE banner disappears in silence on
    a register that really did lose entries. The measurement that licensed the
    type would still be true of the code and false of the response.

    So this asserts PRESENCE, separately from value, on every path a consumer
    reads -- generate, export and latest. A `response_model_exclude_none`, an
    `exclude_unset`, or a hand-rolled projection on any one of them turns this
    red instead of turning the banner off.

    Deliberately NOT merged into the value assertions above. A test that checks
    presence and value together passes for either reason, and the failure this
    guards is exactly the one where the value would have been right had the key
    survived.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, _ = _seed_attack_and_zt(c, bearer, cid)
    bh = {"Authorization": f"Bearer {bearer}"}
    provider.register_static("risk_synthesize", LLMResponse(_one_entry(technique)))

    gen = c.post(f"/risk/clients/{cid}/register/generate", headers=bh)
    assert gen.status_code == 201, gen.text
    latest = c.get(f"/risk/clients/{cid}/register/latest", headers=bh)
    assert latest.status_code == 200, latest.text
    export = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert export.status_code in (200, 201), export.text

    for label, resp in (("generate", gen), ("latest", latest), ("export", export)):
        body = resp.json()
        for key in ("batches_total", "batches_failed"):
            assert key in body, (
                f"{label} omitted {key!r} from the serialised payload. The web "
                "type is `number | null` and the banner reads "
                "`batches_failed !== null`, so an ABSENT key makes the "
                "INCOMPLETE disclosure vanish on a register that lost entries "
                "-- silently, and #317 is the recorded instance of exactly this"
            )
