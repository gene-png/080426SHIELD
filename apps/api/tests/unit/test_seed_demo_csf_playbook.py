"""#474: the demo seed gives Atlas's CSF assessments Playbook rows, so a Risk
Register regenerated on Atlas draws CSF findings the way the product now works.

The advisor's rulings on #736: 6087027524 item 6 ("seed Playbook rows, as a
small `seed_demo.py` PR ... The demo should regenerate the way the product now
works"); 6091824874 (keep the published v1 register as is); 6096877058 (its
own PR, after D').

Runs the whole `main()` against SQLite, so the rows checked are the rows the
Demo CI job seeds. Expected codes are written from the hand-built register's
CSF entries (the four `questionnaire_response` rows: PR.AA-01, DE.AE-02,
ID.AM-01, RS.MA-02) and from the seed's documented plan (v2 closes RS.MA-02,
every row targets level 2, a gap scores level 1), never read from the seed.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.csf_assessment import CsfAssessment
from app.models.csf_profile import CsfDimensionScore
from app.models.risk_register import RiskEntry, RiskRegister
from app.storage.local import LocalFilesystemStorage

pytestmark = pytest.mark.unit

V1_GAPS = {"PR.AA-01", "DE.AE-02", "ID.AM-01", "RS.MA-02"}
V2_GAPS = {"PR.AA-01", "DE.AE-02", "ID.AM-01"}
SOURCE_NOTE = (
    "CSF risks in this register come from Kentro's evidence-based assessment. "
    "They can differ from your self-assessment on the CSF dashboard."
)


@pytest.fixture()
def seeded(tmp_path, monkeypatch) -> Iterator[tuple[str, LocalFilesystemStorage]]:
    from scripts import seed_demo

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    storage = LocalFilesystemStorage(tmp_path / "storage")
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(seed_demo, "get_storage", lambda: storage)
    seed_demo.main()
    yield url, storage


def _playbook(db: Session, version: int) -> list[CsfDimensionScore]:
    a = db.execute(select(CsfAssessment).where(CsfAssessment.version == version)).scalar_one()
    return list(
        db.execute(select(CsfDimensionScore).where(CsfDimensionScore.assessment_id == a.id))
        .scalars()
        .all()
    )


def test_both_csf_versions_carry_a_measured_playbook(seeded) -> None:
    from app.csf.catalog import SUBCATEGORIES
    from app.csf.enterprise import enterprise_subcategories
    from app.risk.csf_source import csf_playbook_measure

    url, _storage = seeded
    with Session(create_engine(url, future=True)) as db:
        for version, gaps in ((1, V1_GAPS), (2, V2_GAPS)):
            rows = _playbook(db, version)
            # Positive first: one `high` row per catalog subcategory, each
            # scored AND targeted at level 2.
            assert len(rows) == len(SUBCATEGORIES), version
            assert {r.tier for r in rows} == {"high"}, version
            assert {r.target_level for r in rows} == {2}, version
            measure = csf_playbook_measure(rows)
            assert measure.state == "measured", (version, measure)
            assert measure.unscored_targeted == 0, (version, measure)
            assert set(measure.finding_codes) == {r.subcategory_code for r in rows}, version
            # The product's own roll-up reports exactly the planned gaps.
            a = db.execute(
                select(CsfAssessment).where(CsfAssessment.version == version)
            ).scalar_one()
            ents, _tiers = enterprise_subcategories(db, a)
            gap_rows = {e.subcategory_code: e for e in ents if e.gap}
            assert set(gap_rows) == gaps, (version, sorted(gap_rows))
            assert {(e.enterprise_level, e.target_level) for e in gap_rows.values()} == {(1, 2)}


def test_a_regenerate_on_atlas_draws_csf_findings_from_the_playbook(seeded) -> None:
    from app.ai.fixtures import build_runtime_provider
    from app.ai.llm import LLMClient, LLMResponse
    from app.db.session import get_db
    from app.main import create_app
    from app.routes.artifacts import _storage_dep
    from app.routes.risk import _llm_dep

    url, storage = seeded
    engine = create_engine(url, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    runtime = build_runtime_provider()
    seen: list[dict] = []

    class _Capture:
        model = runtime.model

        def complete(self, prompt: str, payload: dict) -> LLMResponse:
            if payload.get("findings") is not None:
                seen.append(payload)
            return runtime.complete(prompt, payload)

        def __getattr__(self, name):
            return getattr(runtime, name)

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(_Capture())
    app.dependency_overrides[_storage_dep] = lambda: storage
    with TestClient(app) as c:
        login = c.post(
            "/auth/login", json={"email": "admin@kentro.example", "password": "DemoPass!2026"}
        )
        assert login.status_code == 200, login.text
        h = {"Authorization": f"Bearer {login.json()['access_token']}"}
        with Session(engine) as db:
            cid = str(db.execute(select(RiskRegister.client_id)).scalar_one())
        # RR-1 (#1122): seeded Atlas has both Zero Trust frameworks, so an
        # absent body is refused as ambiguous; name the seed's own selection.
        gen = c.post(
            f"/risk/clients/{cid}/register/generate",
            headers=h,
            json={"include": {"csf": True, "zero_trust": "cisa_ztmm_2_0"}},
        )
        assert gen.status_code == 201, gen.text
        latest = c.get(f"/risk/clients/{cid}/register/latest", headers=h)
        assert latest.status_code == 200, latest.text
        body = latest.json()

    # Positive first: v2 is the regenerated register, measured from the
    # Playbook, with the CSF source note.
    assert body["version"] == 2, body["version"]
    (csf,) = [t for t in body["targets"] if t["kind"] == "csf"]
    assert (csf["target"], csf["source"]) == (None, "playbook"), csf
    assert body["csf_source_note"] == SOURCE_NOTE
    assert seen, "no risk_synthesize payload was captured"
    csf_findings = {
        sid: f["label"]
        for payload in seen
        for sid, f in payload["findings"].items()
        if f["kind"] == "csf"
    }
    assert csf_findings == {code: f"CSF {code}: level 1 of target 2" for code in V2_GAPS}
    # And the regenerated register's entries carry them (the drafted entries,
    # one per finding, as the fixture answers). Zero Trust entries share the
    # `questionnaire_response` source, so CSF ones are told apart by code.
    from app.csf.catalog import SUBCATEGORIES

    csf_codes = {sc.code for sc in SUBCATEGORIES}
    entry_ids = {e["source_id"] for e in body["entries"] if e["source_id"] in csf_codes}
    assert entry_ids == V2_GAPS, sorted(entry_ids)


def test_the_published_v1_register_is_left_as_hand_built(seeded) -> None:
    """6091824874: the published v1 register records no generate, so it
    carries no generate-time provenance (`targets`, `csf_findings`) and its CSF
    entries stay the four hand-built ones. Its `current_inputs` CSF record's
    `playbook_fingerprint` does legitimately change with this seed: v1's
    Playbook rows are written before the register's input snapshot, so the
    snapshot now fingerprints them."""
    url, _storage = seeded
    with Session(create_engine(url, future=True)) as db:
        reg = db.execute(select(RiskRegister)).scalar_one()
        assert reg.version == 1 and reg.finalized_at is not None
        assert "targets" not in reg.provenance and "csf_findings" not in reg.provenance
        csf_ids = set(
            db.execute(
                select(RiskEntry.source_id).where(
                    RiskEntry.register_id == reg.id,
                    RiskEntry.source == "questionnaire_response",
                )
            ).scalars()
        )
        assert csf_ids == V1_GAPS


def test_a_second_seed_run_still_skips_and_adds_no_playbook_rows(seeded) -> None:
    """The seed's existing guard ("Services already present; skipping
    seeding.") is unchanged: a second run writes nothing, Playbook included."""
    from scripts import seed_demo

    url, _storage = seeded
    with Session(create_engine(url, future=True)) as db:
        before = db.execute(select(func.count()).select_from(CsfDimensionScore)).scalar_one()
    assert before > 0
    seed_demo.main()
    with Session(create_engine(url, future=True)) as db:
        after = db.execute(select(func.count()).select_from(CsfDimensionScore)).scalar_one()
    assert after == before


def test_the_seed_refuses_a_playbook_whose_roll_up_disagrees_with_its_plan(
    tmp_path, monkeypatch
) -> None:
    """The seed's self-check, observed firing on a fresh DB. Every planned gap
    row is written at target (the "below target" scores patched to the "at
    target" ones), so `csf_playbook_measure` still reads `measured` with no
    unscored code, and it is the LAST guard, the comparison of
    `enterprise_subcategories`' gaps with the plan, that refuses."""
    from scripts import seed_demo

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        seed_demo, "get_storage", lambda: LocalFilesystemStorage(tmp_path / "storage")
    )
    monkeypatch.setattr(
        seed_demo, "_CSF_PLAYBOOK_BELOW_TARGET", dict(seed_demo._CSF_PLAYBOOK_AT_TARGET)
    )
    with pytest.raises(RuntimeError) as raised:
        seed_demo.main()
    assert str(raised.value) == (
        "seed_demo: CSF Playbook v1 gaps are [], expected "
        "['DE.AE-02', 'ID.AM-01', 'PR.AA-01', 'RS.MA-02']"
    )
