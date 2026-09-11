"""Risk Register: gate, generate, tier-from-code, link validation (Work Order E)."""

from __future__ import annotations

import io
import json
import os
import uuid
from collections.abc import Iterator
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
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
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
    assert details["entries_total"] == 1, details


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
    assert details["entries_total"] == 1


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
def test_export_refuses_a_pre_provenance_register_that_was_never_delivered(app_client) -> None:
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
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
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
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "ATT&CK"}
    )
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    cov = a.json()["coverage"][0]
    c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    c.patch(f"/zt/answers/{za.json()['answers'][0]['id']}", headers=h, json={"maturity_stage": 1})


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

    `batches_total` and `batches_failed` describe a RUN and are 0 on a read-back
    -- the schema says so. The drop is not like that: the consultant opens the
    register a week later and the question "was linkage proposed and lost?" is
    exactly as live as it was at generate time. Because the drop is PERSISTED,
    these counters are derived from the stored entries and survive the fetch.
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
    # And the run-scoped pair is 0 here, which is what makes the contrast real
    # rather than asserted: these two behave differently on a read-back ON
    # PURPOSE, and the difference is the point of migration 0048.
    assert body["batches_total"] == 0
