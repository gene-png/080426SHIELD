"""Rows kept on ID.AM-09, which CSF 2.0 does not have, are read and disclosed (#852).

The catalog no longer has `ID.AM-09` (NIST CSWP 29 has no such subcategory),
and the migration KEEPS every row an assessment stored under it, answered or
not, as 0063 did for CISA and 0064 does for DoD (#925). The writer of the
state seeded here is provisioning under the OLD catalog, which made one answer row and
one Working Profile row per tier for every code it held: the rows are inserted
after the assessment exists, exactly as an assessment that predates #852 holds
them.

Each test goes through the surface a person reaches: the routes, the files a
person downloads, the client's dashboard, the AI preview that shows what would
egress. The expected sentences are the approved copy (#736 comment
6054419744), written out literally.
"""

from __future__ import annotations

import io
import uuid

import pytest
from openpyxl import load_workbook

from app.models.csf_assessment import CsfAnswer, CsfAssessment
from app.models.csf_profile import CsfDimensionScore, CsfGapAction
from tests._ai_mode import docx_text, env_sessions, pdf_text
from tests.unit.test_csf_dashboard import (  # noqa: F401  (fixture)
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

RETIRED = "ID.AM-09"

S1_ONE = (
    "1 recorded answer belongs to ID.AM-09, a subcategory NIST CSF 2.0 does not have, "
    "so it is not scored."
)
S2_ONE_WITH_ACTION = (
    "1 recorded Working Profile row belongs to ID.AM-09, a subcategory NIST CSF 2.0 "
    "does not have, so it is not scored or rolled up. 1 action plan recorded for it is "
    "kept and not listed."
)
S2_TWO = (
    "2 recorded Working Profile rows belong to ID.AM-09, a subcategory NIST CSF 2.0 "
    "does not have, so they are not scored or rolled up."
)


def _service(c) -> tuple[dict, str, dict]:
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    h = {"Authorization": f"Bearer {bearer}"}
    svc_id = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=h).json()
    return h, svc_id, a


def _seed_profiles(c, h: dict, svc_id: str) -> None:
    r = c.post(
        f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high", "moderate"]}
    )
    assert r.status_code == 200, r.text


def _keep_answer(assessment_id: str, *, tier: int | None = 1, notes: str | None = None) -> None:
    with env_sessions()() as db:
        a = db.get(CsfAssessment, uuid.UUID(assessment_id))
        db.add(
            CsfAnswer(
                assessment_id=a.id,
                client_id=a.client_id,
                subcategory_code=RETIRED,
                maturity_tier=tier,
                notes=notes,
            )
        )
        db.commit()


def _keep_profile_rows(
    assessment_id: str, *, scored_tiers: tuple[str, ...], untouched_tiers: tuple[str, ...] = ()
) -> None:
    """A scored row per `scored_tiers` (a consultant wrote it, and set a target
    so it is a gap); a seeded, never-touched row per `untouched_tiers`."""
    with env_sessions()() as db:
        a = db.get(CsfAssessment, uuid.UUID(assessment_id))
        for tier in scored_tiers:
            db.add(
                CsfDimensionScore(
                    assessment_id=a.id,
                    client_id=a.client_id,
                    tier=tier,
                    subcategory_code=RETIRED,
                    governance=1,
                    target_level=3,
                    answer_source="consultant",
                )
            )
        for tier in untouched_tiers:
            db.add(
                CsfDimensionScore(
                    assessment_id=a.id, client_id=a.client_id, tier=tier, subcategory_code=RETIRED
                )
            )
        db.commit()


def _keep_gap_action(assessment_id: str) -> None:
    with env_sessions()() as db:
        a = db.get(CsfAssessment, uuid.UUID(assessment_id))
        db.add(
            CsfGapAction(
                assessment_id=a.id, client_id=a.client_id, subcategory_code=RETIRED, owner="Ops"
            )
        )
        db.commit()


# ---------------------------------------------------------------------------
# The Working Profile: the reader that raised KeyError on a kept row.
# ---------------------------------------------------------------------------


def test_the_enterprise_profile_reads_an_assessment_holding_a_kept_row(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=("high",))
    r = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h)
    assert r.status_code == 200, r.text
    codes = [s["subcategory_code"] for s in r.json()["subcategories"]]
    assert "RC.CO-04" in codes
    assert RETIRED not in codes


def test_a_tier_profile_lists_only_catalog_rows(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=("high",))
    r = c.get(f"/csf/services/{svc_id}/profile/high", headers=h)
    assert r.status_code == 200, r.text
    codes = [row["subcategory_code"] for row in r.json()["rows"]]
    assert "GV.OC-01" in codes
    assert RETIRED not in codes


def test_the_gap_action_list_reads_with_a_kept_action(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=("high",))
    _keep_gap_action(a["id"])
    r = c.get(f"/csf/services/{svc_id}/gap-actions", headers=h)
    assert r.status_code == 200, r.text
    assert RETIRED not in [x["subcategory_code"] for x in r.json()["actions"]]


def test_the_working_profile_states_the_kept_row_and_its_action(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    # One scored row and one seeded-only row: only the scored one is an answer.
    _keep_profile_rows(a["id"], scored_tiers=("high",), untouched_tiers=("moderate",))
    _keep_gap_action(a["id"])
    body = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h).json()
    assert body["retired_rows"] == 1
    assert body["retired_rows_note"] == S2_ONE_WITH_ACTION


S2_ACTION_ONLY = (
    "1 action plan recorded for ID.AM-09, a subcategory NIST CSF 2.0 does not have, "
    "is kept and not listed."
)


def test_an_action_plan_with_no_recorded_row_is_stated(app_client) -> None:  # noqa: F811
    """An action plan on ID.AM-09 whose Working Profile rows nobody wrote.

    Reachable before #852: `PUT /csf/services/{id}/gap-actions/{code}`
    accepts any catalog code, gap or not (`_effective_priority` says so), and
    ID.AM-09 was a catalog code. That route now refuses the code, so the row is
    inserted directly, exactly as such a PUT left it, beside a seeded row
    nobody touched. The sentence is approved (#736 comment 6056012075); this pins
    its punctuation and that it is said at all."""
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=(), untouched_tiers=("high",))
    _keep_gap_action(a["id"])
    r = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["subcategories"]) > 0
    assert body["retired_rows"] == 0
    assert body["retired_rows_note"] == S2_ACTION_ONLY


def test_two_kept_rows_read_in_the_plural_with_no_action_tail(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=("high", "moderate"))
    body = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h).json()
    assert body["retired_rows"] == 2
    assert body["retired_rows_note"] == S2_TWO


def test_nothing_kept_means_no_working_profile_sentence(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=(), untouched_tiers=("high",))
    body = c.get(f"/csf/services/{svc_id}/enterprise-profile", headers=h).json()
    assert len(body["subcategories"]) > 0
    assert body["retired_rows"] == 0
    assert body["retired_rows_note"] is None


def _export(c, h: dict, svc_id: str) -> dict[str, bytes]:
    r = c.post(f"/csf/services/{svc_id}/playbook/export", headers=h)
    assert r.status_code == 200, r.text
    out = {}
    for art in r.json()["artifacts"]:
        dl = c.get(f"/artifacts/{art['artifact_id']}/download", headers=h)
        assert dl.status_code == 200, dl.text
        out[art["kind"]] = dl.content
    return out


def test_every_playbook_file_states_the_kept_row_and_lists_none(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=("high",), untouched_tiers=("moderate",))
    _keep_gap_action(a["id"])
    files = _export(c, h, svc_id)
    assert set(files) == {"xlsx", "exec_pdf", "exec_docx", "full_pdf", "full_docx"}

    wb = load_workbook(io.BytesIO(files["xlsx"]))
    about = [str(v) for row in wb["About"].iter_rows(values_only=True) for v in row if v]
    assert S2_ONE_WITH_ACTION in about
    every_cell = [
        str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v
    ]
    assert "GV.OC-01" in every_cell
    assert RETIRED not in every_cell

    assert S2_ONE_WITH_ACTION in pdf_text(files["exec_pdf"])
    assert S2_ONE_WITH_ACTION in pdf_text(files["full_pdf"])
    assert S2_ONE_WITH_ACTION in docx_text(files["exec_docx"])
    assert S2_ONE_WITH_ACTION in docx_text(files["full_docx"])


# ---------------------------------------------------------------------------
# The assessment answers: workspace, self-assessment, deliverable, dashboard.
# ---------------------------------------------------------------------------


def test_the_workspace_and_the_self_assessment_state_the_kept_answer(
    app_client,  # noqa: F811
) -> None:
    c = app_client
    h, svc_id, a = _service(c)
    _keep_answer(a["id"], tier=1)
    for path in ("assessments/latest", "self-assessment"):
        r = c.get(f"/csf/services/{svc_id}/{path}", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == a["id"]
        assert body["retired_answers"] == 1, path
        assert body["retired_answers_note"] == S1_ONE, path


def test_a_blank_kept_row_is_not_an_answer(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _keep_answer(a["id"], tier=None, notes="   ")
    body = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=h).json()
    assert body["id"] == a["id"]
    assert body["retired_answers"] == 0
    assert body["retired_answers_note"] is None


def _approve_and_finalize(c, h: dict, svc_id: str, a: dict) -> dict:
    for ans in a["answers"]:
        r = c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 3})
        assert r.status_code == 200, r.text
    _keep_answer(a["id"], tier=1)
    assert c.post(f"/csf/assessments/{a['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    return fin.json()


def test_every_finalized_file_states_the_kept_answer(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    fin = _approve_and_finalize(c, h, svc_id, a)

    def _bytes(key: str) -> bytes:
        dl = c.get(f"/artifacts/{fin[key]}/download", headers=h)
        assert dl.status_code == 200, dl.text
        return dl.content

    wb = load_workbook(io.BytesIO(_bytes("xlsx_artifact_id")))
    summary = [list(r)[:2] for r in wb["Score Summary"].iter_rows(values_only=True)]
    assert ["Not scored", S1_ONE] in summary
    assert S1_ONE in pdf_text(_bytes("pdf_artifact_id"))
    assert S1_ONE in docx_text(_bytes("docx_artifact_id"))


def test_the_client_dashboard_states_the_kept_answer(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    client = _register(c, "client@example.com")
    client_id = client["user"]["client_id"]
    fin = _approve_and_finalize(c, h, svc_id, a)
    rel = c.post(f"/csf/deliverables/{fin['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text

    c.headers["X-Client-Id"] = client_id
    r = c.get(
        f"/clients/{client_id}/csf/{svc_id}/dashboard",
        headers={"Authorization": f"Bearer {client['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["functions"]) == 6
    assert body["retired_answers"] == 1
    assert body["retired_answers_note"] == S1_ONE


# ---------------------------------------------------------------------------
# Run-AI: what would egress.
# ---------------------------------------------------------------------------


def test_the_ai_payload_carries_no_kept_row(app_client) -> None:  # noqa: F811
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    first = a["answers"][0]
    r = c.patch(f"/csf/answers/{first['id']}", headers=h, json={"maturity_tier": 2})
    assert r.status_code == 200, r.text
    _keep_answer(a["id"], tier=1)
    _keep_profile_rows(a["id"], scored_tiers=("high",))
    prev = c.post("/ai/preview", json={"service_id": svc_id}, headers=h)
    assert prev.status_code == 200, prev.text
    inputs = prev.json()["payload"]
    assert first["subcategory_code"] in inputs["answers"]
    assert "GV.OC-01" in inputs["subcategories"]
    assert RETIRED not in inputs["subcategories"]
    assert RETIRED not in inputs["answers"]


# ---------------------------------------------------------------------------
# The action-only sentence, approved with commas (#736 comment 6056012075).
# ---------------------------------------------------------------------------

S2_ACTIONS_ONE_CODE = (
    "2 action plans recorded for ID.AM-09, a subcategory NIST CSF 2.0 does not have, "
    "are kept and not listed."
)
S2_ACTIONS_TWO_CODES = (
    "2 action plans recorded for ID.AM-09, ID.AM-10, subcategories NIST CSF 2.0 does "
    "not have, are kept and not listed."
)


def test_the_action_only_sentence_reaches_the_playbook_workbook(app_client) -> None:  # noqa: F811
    """The singular form, through the export route and the downloaded XLSX.
    The gap action is inserted directly for the reason given on
    `test_an_action_plan_with_no_recorded_row_is_stated`."""
    c = app_client
    h, svc_id, a = _service(c)
    _seed_profiles(c, h, svc_id)
    _keep_profile_rows(a["id"], scored_tiers=(), untouched_tiers=("high",))
    _keep_gap_action(a["id"])
    files = _export(c, h, svc_id)
    wb = load_workbook(io.BytesIO(files["xlsx"]))
    about = [str(v) for row in wb["About"].iter_rows(values_only=True) for v in row if v]
    assert "SHIELD by Kentro — CSF 2.0 Full Playbook" in about
    assert S2_ACTION_ONLY in about


def _action(code: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        subcategory_code=code,
        characterization=None,
        priority_override=None,
        owner="Ops",
        deadline=None,
        resources=None,
        success_criteria=None,
        poam_ref=None,
    )


def test_the_plural_action_only_sentence_with_one_code() -> None:
    """NOT REACHABLE through any route, and built at the function level for that
    reason: `CsfGapAction` is unique per (assessment, code), so one assessment
    holds at most one plan per code, and ID.AM-09 is the only retired code. The
    approved plural must still read correctly the day either changes."""
    from app.csf.retired import working_profile_sentence

    out = working_profile_sentence([], [_action("ID.AM-09"), _action("ID.AM-09")])
    assert out == S2_ACTIONS_ONE_CODE


def test_the_plural_action_only_sentence_with_two_codes() -> None:
    """Also unreachable (see above): `ID.AM-10` is not a CSF code of any
    edition, used only as a second code the catalog does not have."""
    from app.csf.retired import working_profile_sentence

    out = working_profile_sentence([], [_action("ID.AM-10"), _action("ID.AM-09")])
    assert out == S2_ACTIONS_TWO_CODES


def test_the_plural_action_only_sentence_reaches_the_workbook_cover() -> None:
    """The file level: what `export_playbook` passes, rendered into the XLSX
    About sheet. Built from the function for the reason above."""
    from app.csf import playbook_export
    from app.csf.retired import working_profile_sentence

    note = working_profile_sentence([], [_action("ID.AM-09"), _action("ID.AM-09")])
    raw = playbook_export.render_xlsx(
        approved=False,
        client_name="Acme",
        version=1,
        enterprise_rows=[],
        tier_profiles={},
        retired_note=note,
    )
    wb = load_workbook(io.BytesIO(raw))
    about = [str(v) for row in wb["About"].iter_rows(values_only=True) for v in row if v]
    assert "Client: Acme" in about
    assert S2_ACTIONS_ONE_CODE in about
