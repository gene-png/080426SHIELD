"""#101 + #102 end to end: a flag survives the reload, and the score knows about it.

The analytics half (`test_attack_pending_review.py`) and the rule half
(`test_attack_pending_matrix.py`) are both pure-function tests. Neither can see
the failure both issues actually describe, which is a WIRING failure: the
resolver made the confirmed/inferred distinction and then dropped it on the floor
at the end of the request, so `citations.py` calling it "queued for a human" was
false in the only way that matters -- there was no queue, and nothing scored on
it.

So every test here goes through HTTP and, where the claim is persistence, reads
the value back from a SECOND request. Asserting the run response alone would
re-test exactly the thing that was already true and already useless.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.ai.llm import FixtureProvider, LLMClient, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus


@pytest.fixture()
def app_client(tmp_path) -> Iterator[tuple[TestClient, sessionmaker, FixtureProvider]]:
    url = f"sqlite:///{tmp_path / 'shield-attackpending.db'}"
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
    from app.routes.attack import _llm_dep

    def override_get_db() -> Iterator[Session]:
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    provider = FixtureProvider()
    app = create_app()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[_llm_dep] = lambda: LLMClient(provider)
    with TestClient(app) as c:
        yield c, TestSession, provider


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


def _seed_tools(TestSession: sessionmaker, cid: str, user_id: str, tools: list[str]) -> None:
    import uuid as _uuid

    with TestSession() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(service_id=svc.id, version=1, status=CapabilityListStatus.APPROVED)
        db.add(cl)
        db.flush()
        for name in tools:
            db.add(CapabilityItem(capability_list_id=cl.id, name=name))
        db.commit()


def _service(c: TestClient, h: dict) -> tuple[str, list[str]]:
    svc_id = c.post(
        "/attack/services", headers=h, json={"kind": "attack_coverage", "title": "Acme ATT&CK"}
    ).json()["id"]
    a = c.post(f"/attack/services/{svc_id}/assessments", headers=h)
    return svc_id, [row["technique_code"] for row in a.json()["coverage"]]


def _row(payload: dict, code: str) -> dict:
    return next(t for t in payload["coverage"] if t["technique_code"] == code)


@pytest.mark.unit
def test_an_inferred_citation_survives_the_reload(app_client) -> None:
    """#101's entire complaint, asserted on a SECOND request.

    "Queued for a human" was neither queued nor retrievable: the list lived in
    the transient run response and in React state, so a consultant who ran AI on
    Monday and approved on Tuesday could not get it back at all. The assertion
    that matters is therefore the GET, not the POST.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    # "CrowdStrike" is not the approved name. The resolver rescues it by
    # substring -- an INFERENCE, so `needs_review`, not `confirmed`.
    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    run = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert run.status_code == 200, run.text
    # Asserted on the DEDUPED tool list, not on `citations_needs_review`. The run
    # is batched and a registered fixture answers every batch identically, so the
    # raw counter reads 26 here -- an artifact of the harness, not of the code.
    # The tool list is deduped run-wide and says the thing under test: this
    # citation was an inference.
    assert run.json()["citations_needs_review_tools"] == ["CrowdStrike Falcon"]
    assert run.json()["pending_review_rows"] == 1

    reloaded = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h)
    assert reloaded.status_code == 200, reloaded.text
    row = _row(reloaded.json(), code)
    assert row["detection_tools"] == ["CrowdStrike Falcon"], "the citation is APPLIED, not dropped"
    assert row["unconfirmed_citations"] == [
        {
            "tool": "CrowdStrike Falcon",
            # What the model wrote, kept beside what it was resolved to. The
            # resolved name alone cannot tell a consultant WHY the citation
            # needed rescuing.
            "cited": "CrowdStrike",
            "reason": "substring",
            "field": "detection_tools",
            "cleared_at": None,
        }
    ]
    assert row["pending_review"] is True


@pytest.mark.unit
def test_an_exact_citation_persists_an_empty_list_not_null(app_client) -> None:
    """`[]` and NULL are different answers and this is where the difference is written.

    NULL means "nobody ever resolved this row's citations" and scores as pending.
    A row this run DID resolve, and found nothing to infer on, must say so
    explicitly -- otherwise every clean row reads as unchecked and the whole
    assessment sits in review forever.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["crowdstrike falcon"]}]}'
        ),
    )
    run = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert run.json()["citations_needs_review_tools"] == []
    assert run.json()["citations_rejected_examples"] == []
    assert run.json()["pending_review_rows"] == 0

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["unconfirmed_citations"] == []
    assert row["pending_review"] is False


@pytest.mark.unit
def test_a_hand_curated_status_is_not_held_for_review(app_client) -> None:
    """A consultant setting a status by hand is the AUTHOR of the claim.

    5.1 is about whether the resolver's INFERENCES may score. A human typing
    `covered` into the matrix has made no inference -- and the first
    implementation of this rule withheld those rows anyway, because "no confirmed
    tool backs this" was read without asking whether anything had been offered.
    `test_heatmap_reflects_coverage_after_patches` reported 0 covered and 0%
    coverage over ten hand-curated techniques, with nothing anywhere in the
    product that could ever clear it.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, codes[0])["id"]
    patched = c.patch(f"/attack/coverage/{row_id}", headers=h, json={"status": "covered"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["pending_review"] is False
    assert patched.json()["unconfirmed_citations"] == []

    body = c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()
    assert body["covered"] == 1
    assert body["pending_review"] == 0
    assert body["coverage_pct"] == 100.0


@pytest.mark.unit
def test_taking_authorship_of_a_row_clears_its_flags_but_keeps_the_record(app_client) -> None:
    """The escape hatch, and the reason cleared entries are stamped not deleted.

    A run leaves a technique pending. The consultant looks at it and sets the
    status themselves -- that is 5.1's second definition of confirmed ("a human
    cleared it"), so the row scores. The entry STAYS, with a timestamp: "a human
    accepted this" is a different answer to "why does this technique count" than
    "nobody ever cited anything", and an auditor needs to be able to tell them
    apart.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()["pending_review"] == 1

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, code)["id"]
    patched = c.patch(f"/attack/coverage/{row_id}", headers=h, json={"status": "covered"})
    assert patched.status_code == 200, patched.text

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["pending_review"] is False
    assert len(row["unconfirmed_citations"]) == 1, "the record was deleted, not stamped"
    assert row["unconfirmed_citations"][0]["cleared_at"] is not None
    assert row["unconfirmed_citations"][0]["cited"] == "CrowdStrike"
    assert c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()["pending_review"] == 0


@pytest.mark.unit
def test_editing_a_note_does_not_clear_the_review_queue(app_client) -> None:
    """Scoped to the fields that ARE the claim.

    Clearing a review queue as a side effect of fixing a typo would be a silent
    loss of the disclosure -- the same shape as #101 itself, where the flag
    existed and then quietly stopped existing.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, code)["id"]
    c.patch(f"/attack/coverage/{row_id}", headers=h, json={"notes": "chased with the SOC lead"})

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["unconfirmed_citations"][0]["cleared_at"] is None
    assert row["pending_review"] is True


@pytest.mark.unit
def test_a_technique_whose_every_citation_was_rejected_is_pending(app_client) -> None:
    """The plan's "related defect", which arrives by a different route.

    > A technique can currently read `covered` with EMPTY tool lists -- when
    > every citation for it was dropped, the status survives untouched.

    Nothing is written to `unconfirmed_citations` for a rejection: a rejected
    citation resolved to no tool, so there is no name to store. It needs none.
    The rejection leaves the tool lists EMPTY, and an empty tool list under a
    `covered` status is unbacked by the same predicate -- one rule, not two.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["Qradar"]}]}'
        ),
    )
    run = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert run.json()["citations_rejected_examples"] == ["Qradar"]
    assert run.json()["pending_review_rows"] == 1

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["status"] == "covered", "the status survives -- it is the SCORE that withholds"
    assert row["detection_tools"] == []
    # A rejection resolves to no tool, so `tool` is null and the string the model
    # sent is what is kept. Without this record the row would be byte-identical
    # to one nobody ever cited anything for, which must NOT be withheld -- see
    # `test_a_hand_curated_status_is_not_held_for_review`.
    assert row["unconfirmed_citations"] == [
        {
            "tool": None,
            "cited": "Qradar",
            "reason": "rejected_unknown",
            "field": "detection_tools",
            "cleared_at": None,
        }
    ]
    assert row["pending_review"] is True


@pytest.mark.unit
def test_the_heatmap_withholds_a_pending_technique_and_says_how_many(app_client) -> None:
    """The score is the point of #102. A flag nothing reads is #101 again."""
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    inferred, gapped = codes[0], codes[1]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": ['
            '{"technique_code": "' + inferred + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]},'
            '{"technique_code": "' + gapped + '", "status": "gap",'
            ' "detection_tools": []}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    hm = c.get(f"/attack/services/{svc_id}/heatmap", headers=h)
    assert hm.status_code == 200, hm.text
    body = hm.json()
    assert body["pending_review"] == 1
    assert body["covered"] == 0, "an unconfirmed claim was counted as covered"
    assert body["gap"] == 1, "the pending technique was collapsed into gap"
    # One gap, nothing addressable-and-confirmed above it.
    assert body["coverage_pct"] == 0.0
    assert (
        body["scored_count"] + body["unscored_count"]
        == body["total_techniques"] + body["total_sub_techniques"]
    )
    touched = [t for t in body["by_tactic"] if t["pending_review"] > 0]
    assert touched, "the per-tactic breakdown dropped the pending count"


@pytest.mark.unit
def test_a_row_the_run_never_touched_stays_null_and_scores_as_pending(app_client) -> None:
    """Fail-closed on absence, which is migration 0044's central decision.

    The row is written STRAIGHT TO THE COLUMN rather than through `patch_coverage`,
    and that is the point rather than a shortcut: patching a status is a human
    authoring the claim, which confirms the row. What this test needs is the one
    state no endpoint can produce any more -- a `covered` status whose citations
    were never resolved at all. That is precisely the shape every ATT&CK draft
    written before the resolver is in, and reading it as confirmed because nothing
    on record contradicts it is the fail-open shape D-054 rejected one layer up.

    It is also locked, so `run_ai` skips it: a locked pre-resolver row cannot be
    repaired by re-running AI, which is why the escape hatch has to be the human
    one (`test_taking_authorship_of_a_row_clears_its_flags_but_keeps_the_record`).
    """
    import uuid as _uuid

    from app.models.attack_assessment import AttackCoverage

    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, code)["id"]
    with TestSession() as db:
        stored = db.get(AttackCoverage, _uuid.UUID(row_id))
        stored.status = "covered"
        stored.detection_tools = ["CrowdStrike Falcon"]
        stored.locked = True
        assert stored.unconfirmed_citations is None, "the fixture is not the pre-resolver state"
        db.commit()

    provider.register_static("mitre_map", LLMResponse('{"techniques": []}'))
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    with TestSession() as db:
        assert (
            db.get(AttackCoverage, _uuid.UUID(row_id)).unconfirmed_citations is None
        ), "run_ai wrote to a LOCKED row"

    body = c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()
    assert body["pending_review"] == 1, (
        "a status whose citations were never resolved read as confirmed because "
        "nothing on record contradicted it"
    )
    assert body["covered"] == 0


@pytest.mark.unit
def test_a_model_claim_with_no_citation_at_all_is_pending(app_client) -> None:
    """The plan's related defect in its most literal form.

    > A technique can currently read `covered` with EMPTY tool lists.

    The rejected-citation route is covered above. This is the other one: the
    model returns `status: covered` and simply does not cite anything. Nothing is
    rejected, nothing is inferred, and the tool lists are empty because there was
    never anything to put in them -- so on the stored shape alone this row is
    indistinguishable from a consultant's hand-curated `covered`, which must NOT
    be withheld.

    What separates them is who authored the claim, and `run_ai` is the only one
    of the two that knows. So it records the omission at the moment it happens,
    as an entry naming no tool and no citation. A guard that recorded nothing
    here would be a guard against counting the case it exists for -- CLAUDE.md's
    "make the false branch emit something".
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    claimed, gapped = codes[0], codes[1]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": ['
            '{"technique_code": "' + claimed + '", "status": "covered",'
            ' "rationale": "The EDR handles this."},'
            '{"technique_code": "' + gapped + '", "status": "gap"}]}'
        ),
    )
    run = c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    assert run.status_code == 200, run.text
    assert run.json()["pending_review_rows"] == 1

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row = _row(latest, claimed)
    assert row["status"] == "covered"
    assert row["unconfirmed_citations"] == [
        {
            "tool": None,
            "cited": None,
            "reason": "no_citation",
            "field": None,
            "cleared_at": None,
        }
    ]
    assert row["pending_review"] is True

    # A `gap` cited nothing either, and that is exactly what a gap means. It is
    # never withheld -- withholding an absence claim deletes a finding and raises
    # the coverage ratio.
    assert _row(latest, gapped)["unconfirmed_citations"] == []
    assert _row(latest, gapped)["pending_review"] is False


@pytest.mark.unit
def test_confirming_a_rows_citations_is_a_first_class_action(app_client) -> None:
    """#101 asked for a QUEUE, and a queue needs a way to work through it.

    Until this endpoint existed the only way to clear a flag was to re-set the
    technique's status to the value it already had, and have `patch_coverage`
    stamp the entries as a side effect. That works and is exactly the wrong shape
    to hand a consultant: the action they want ("I checked this citation and it
    is right") is spelled as an edit to something else.

    The distinction it preserves is the one 5.1 turns on. Confirming says *the
    model's inference was correct*; setting the status says *here is my own
    answer*. Both make the row score, and an auditor asking why should be able to
    see which happened.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, code)["id"]

    r = c.post(f"/attack/coverage/{row_id}/confirm-citations", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending_review"] is False
    assert body["status"] == "covered", "confirming must not touch the status"
    assert body["detection_tools"] == ["CrowdStrike Falcon"], "nor the applied tools"
    assert len(body["unconfirmed_citations"]) == 1, "the record was deleted, not stamped"
    assert body["unconfirmed_citations"][0]["cleared_at"] is not None

    assert c.get(f"/attack/services/{svc_id}/heatmap", headers=h).json()["covered"] == 1


@pytest.mark.unit
def test_confirming_a_row_with_nothing_outstanding_is_refused(app_client) -> None:
    """A no-op that returns 200 reads as "confirmed" in the audit trail.

    The row is already clean, so there is nothing a human could have looked at.
    Writing an `attack.coverage.citations_confirmed` audit row for it would put a
    human's name against a review that did not happen -- the same class of lie as
    a ledger row recording a success above the commit that makes it true.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)

    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, codes[0])["id"]

    r = c.post(f"/attack/coverage/{row_id}/confirm-citations", headers=h)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "nothing_to_confirm"


@pytest.mark.unit
def test_confirming_is_refused_on_a_locked_assessment(app_client) -> None:
    """Same guard as every other write to a coverage row.

    An APPROVED or RELEASED assessment's numbers have been signed off; raising
    its coverage afterwards by clearing a queue would change a delivered figure
    without a new version.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    latest = c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json()
    row_id = _row(latest, code)["id"]
    approved = c.post(f"/attack/assessments/{latest['id']}/approve", headers=h)
    assert approved.status_code == 200, approved.text

    r = c.post(f"/attack/coverage/{row_id}/confirm-citations", headers=h)
    assert r.status_code == 409, r.text


@pytest.mark.unit
def test_a_rerun_that_omits_a_tool_field_does_not_erase_its_flags(app_client) -> None:
    """A partial suggestion must not silently confirm what it did not re-check.

    `run_ai` overwrites a row's tool lists only for the fields the model actually
    sent -- so a rerun that returns `{technique_code, status}` and nothing else
    leaves the previous run's tools in place. Writing `[]` over the citation
    record in that case would say "resolved, nothing outstanding" about tools this
    run never looked at, and the row would flip from withheld to scoring with no
    human anywhere in the loop.

    That is the exact fail-open this change exists to close, arriving through the
    change itself: the guard against a stale record became a guard that erased the
    record. CLAUDE.md has this shape twice already -- "a guard against
    DOUBLE-counting will quietly become a guard against counting at all".
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    first = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert first["pending_review"] is True

    # Second run: a status and nothing else. The detection tool stays on the row.
    provider.register_static(
        "mitre_map",
        LLMResponse('{"techniques": [{"technique_code": "' + code + '", "status": "covered"}]}'),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["detection_tools"] == ["CrowdStrike Falcon"], "the tool survived the rerun"
    assert (
        row["unconfirmed_citations"] == first["unconfirmed_citations"]
    ), "the flag for a tool this run never re-resolved was erased"
    assert row["pending_review"] is True


@pytest.mark.unit
def test_a_rerun_replaces_only_the_fields_it_resolved(app_client) -> None:
    """Per-field, not per-row. The other half of the same rule.

    A rerun that re-resolves `detection_tools` says nothing about a flag raised
    against `response_tools`, whose contents it left untouched.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon", "Splunk Enterprise"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike"], "response_tools": ["Splunk"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    first = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert {e["field"] for e in first["unconfirmed_citations"]} == {
        "detection_tools",
        "response_tools",
    }

    # Re-resolve detection only, and cleanly this time.
    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["CrowdStrike Falcon"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    fields = {e["field"] for e in row["unconfirmed_citations"]}
    assert fields == {"response_tools"}, (
        "detection's flag should be gone (it re-resolved cleanly) and response's "
        "should remain (this run never looked at it)"
    )
    # Detection now carries a CONFIRMED tool, so the row is backed and scores --
    # even though response_tools still has an outstanding flag.
    assert row["pending_review"] is False


@pytest.mark.unit
def test_a_later_citation_clears_the_no_citation_marker(app_client) -> None:
    """The row-level marker is re-derived, never carried.

    `no_citation` describes the whole row ("the model claimed this and named
    nothing"), not one field, so it has no field to be scoped by. Carrying it
    across a rerun that DID cite something would leave the panel telling a
    consultant no tool was named while a tool sits in the Detection row above it.
    """
    c, TestSession, provider = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _seed_tools(TestSession, cid, me["id"], ["CrowdStrike Falcon"])
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    svc_id, codes = _service(c, h)
    code = codes[0]

    provider.register_static(
        "mitre_map",
        LLMResponse('{"techniques": [{"technique_code": "' + code + '", "status": "covered"}]}'),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)
    first = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert [e["reason"] for e in first["unconfirmed_citations"]] == ["no_citation"]

    provider.register_static(
        "mitre_map",
        LLMResponse(
            '{"techniques": [{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["crowdstrike falcon"]}]}'
        ),
    )
    c.post(f"/attack/services/{svc_id}/run-ai", headers=h)

    row = _row(c.get(f"/attack/services/{svc_id}/assessments/latest", headers=h).json(), code)
    assert row["detection_tools"] == ["CrowdStrike Falcon"]
    assert row["unconfirmed_citations"] == [], "the row-level marker outlived the omission"
    assert row["pending_review"] is False
