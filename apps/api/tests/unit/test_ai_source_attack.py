"""#646 through ATT&CK's surfaces: the workspace's assessment, the deliverable
files, and the client dashboard all say which mode drafted the assessment, in
the same words, from ONE derivation (`app.mode_stamp.ai_mode_for`).

The population is the assessment, never the service: a run on a discarded
earlier draft says nothing about the next one (the parked draft's bug, #646
review). The unit is the run, not the call.
"""

from __future__ import annotations

import pytest

from app.models.llm_call import LLMCallMode
from tests._ai_mode import (
    FIXTURE,
    LIVE,
    NONE,
    UNKNOWN,
    docx_text,
    mixed,
    pdf_text,
    seed_run,
    seed_unattributed_call,
    xlsx_ai_sheet,
)
from tests._attack_rows import first_standalone
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit


def _source(c, bearer: str, svc: str) -> dict:
    r = c.get(f"/attack/services/{svc}/assessments/latest", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    return r.json()["ai_source"]


def test_the_workspace_the_files_and_the_dashboard_say_the_same(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    cov = first_standalone(a["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=_auth(bearer), json={"status": "gap"})
    assert r.status_code == 200, r.text
    seed_run(
        Sess, service_id=svc, subject_id=a["id"], purpose="mitre_map", mode=LLMCallMode.FIXTURE
    )

    workspace = _source(c, bearer, svc)
    assert workspace == {"state": "fixture", "sentence": FIXTURE, "live_runs": 0, "fixture_runs": 1}

    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    fin = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert fin.status_code in (200, 201), fin.text
    body = fin.json()

    def _bytes(key: str) -> bytes:
        dl = c.get(f"/artifacts/{body[key]}/download", headers=_auth(bearer))
        assert dl.status_code == 200, dl.text
        return dl.content

    assert FIXTURE in pdf_text(_bytes("pdf_artifact_id"))
    assert FIXTURE in docx_text(_bytes("docx_artifact_id"))
    sheet = xlsx_ai_sheet(_bytes("xlsx_artifact_id"))
    assert sheet[0][:2] == ["AI source", "fixture"]
    assert sheet[1][0] == FIXTURE

    rel = c.post(f"/attack/deliverables/{body['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text
    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    assert dash.json()["ai_source"] == workspace


def test_a_discarded_drafts_fixture_run_does_not_make_the_next_version_mixed(
    env,  # noqa: F811
) -> None:
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, v1 = _service_and_assessment(c, bearer)
    seed_run(
        Sess, service_id=svc, subject_id=v1["id"], purpose="mitre_map", mode=LLMCallMode.FIXTURE
    )
    assert _source(c, bearer, svc)["state"] == "fixture"

    d = c.post(f"/attack/assessments/{v1['id']}/discard", headers=_auth(bearer))
    assert d.status_code == 200, d.text
    v2 = c.post(f"/attack/services/{svc}/assessments", headers=_auth(bearer))
    assert v2.status_code == 201, v2.text
    assert v2.json()["id"] != v1["id"]
    seed_run(
        Sess, service_id=svc, subject_id=v2.json()["id"], purpose="mitre_map", mode=LLMCallMode.LIVE
    )

    assert _source(c, bearer, svc) == {
        "state": "live",
        "sentence": LIVE,
        "live_runs": 1,
        "fixture_runs": 0,
    }


def test_the_five_states(env) -> None:  # noqa: F811
    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)

    assert _source(c, bearer, svc)["sentence"] == NONE

    # A failed run applied nothing, so it says nothing about the assessment.
    from app.models.ai_run import AiRunStatus

    seed_run(
        Sess,
        service_id=svc,
        subject_id=a["id"],
        purpose="mitre_map",
        mode=LLMCallMode.FIXTURE,
        status=AiRunStatus.FAILED,
    )
    assert _source(c, bearer, svc)["state"] == "none"

    seed_run(Sess, service_id=svc, subject_id=a["id"], purpose="mitre_map", mode=LLMCallMode.LIVE)
    assert _source(c, bearer, svc)["sentence"] == LIVE
    seed_run(
        Sess, service_id=svc, subject_id=a["id"], purpose="mitre_map", mode=LLMCallMode.FIXTURE
    )
    seed_run(Sess, service_id=svc, subject_id=a["id"], purpose="mitre_map", mode=LLMCallMode.LIVE)
    assert _source(c, bearer, svc) == {
        "state": "mixed",
        "sentence": mixed(1, 3),
        "live_runs": 2,
        "fixture_runs": 1,
    }

    # A pre-#756 call no run accounts for: nothing says which mode drafted it.
    seed_unattributed_call(Sess, service_id=svc, purpose="mitre_map")
    assert _source(c, bearer, svc)["sentence"] == UNKNOWN


def test_a_call_made_before_the_assessment_does_not_make_it_unknown(env) -> None:  # noqa: F811
    """#778 review F2: the `since` bound. A pre-#756 call made before this
    assessment existed cannot have drafted it, so it says nothing about it."""
    import uuid
    from datetime import timedelta

    from app.models.attack_assessment import AttackAssessment

    c, Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    with Sess() as s:
        created = s.get(AttackAssessment, uuid.UUID(a["id"])).created_at
    seed_unattributed_call(
        Sess, service_id=svc, purpose="mitre_map", created_at=created - timedelta(days=1)
    )
    assert _source(c, bearer, svc)["state"] == "none"
    # The same call made after it does.
    seed_unattributed_call(Sess, service_id=svc, purpose="mitre_map")
    assert _source(c, bearer, svc)["state"] == "unknown"
