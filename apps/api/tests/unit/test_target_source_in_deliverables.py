"""#783: a CSF or ZT deliverable built on a target the client did not choose
says so, beside the target, in the dashboard's own words.

Finalize resolves `(target, source)` and used to render only the number, so a
document built on a default or a fallen-back target read exactly like one built
on the client's choice. The client dashboard already said which it was
(`targetFaultNote` / `targetFault`). Every test here goes through finalize and
reads the STORED bytes of all three artifacts, plus the stored summary that
`/results` shows, because those are what the client keeps.

THIS TABLE IS DUPLICATED, word for word, in
`apps/web/src/lib/dashboards/target-source-sentences.test.ts`. The TS and
Python sentences are synchronised, not derived: a fixture both runners could
read would close the window, and it needs the compose mount tracked in #422.
Change a sentence here and you must change it there.
"""

from __future__ import annotations

import io
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.unit.test_export_targets import (  # noqa: F401  (fixture)
    _attach_intake_target,
    _register,
    app_client,
)

pytestmark = pytest.mark.unit

TIER = {
    "default": "Default target — no tier chosen at intake.",
    "client_out_of_range": "Default target — the tier on file is not one CSF has.",
    "client_below_floor": "Default target — the tier on file is a starting point, not a target.",
    "client_unparseable": "Default target — the tier on file could not be read.",
    "unrecognised": "Default target — the tier on file was not usable.",
}
STAGE = {
    "default": "Default target — no stage chosen at intake.",
    "client_out_of_range": "Default target — the stage on file is not one this framework has.",
    "client_below_floor": "Default target — the stage on file is a starting point, not a target.",
    "client_unparseable": "Default target — the stage on file could not be read.",
    "unrecognised": "Default target — the stage on file was not usable.",
}


def _flat(s: str) -> str:
    return " ".join(s.split())


def _pdf(raw: bytes) -> str:
    from pypdf import PdfReader

    return _flat(" ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(raw)).pages))


def _docx(raw: bytes) -> str:
    from docx import Document

    return _flat(" ".join(p.text for p in Document(io.BytesIO(raw)).paragraphs))


def _xlsx(raw: bytes) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(raw))
    return _flat(
        " ".join(
            str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row
        )
    )


def _store_raw_target(svc_id: str, column: str, value: object) -> None:
    """Write a stored target no current route accepts (intake refuses it since
    #85, and Postgres' SMALLINT cannot hold a fraction). The resolver has an
    arm for each, and the deliverable must not be silent when one is reached,
    so the world is built below the API."""
    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        res = s.execute(
            text(
                f"UPDATE service_requests SET {column} = :v WHERE id = "  # noqa: S608
                "(SELECT source_request_id FROM services WHERE id = :sid)"
            ),
            {"v": value, "sid": uuid.UUID(svc_id).hex},
        )
        assert res.rowcount == 1, "the raw target did not land"
        s.commit()


def _surfaces(c, h, fin: dict) -> dict[str, str]:
    from app.models.deliverable import Deliverable

    def _get(key: str) -> bytes:
        return c.get(f"/artifacts/{fin[key]}/download", headers=h).content

    eng = create_engine(os.environ["DATABASE_URL"], future=True)
    with sessionmaker(bind=eng, future=True)() as s:
        summary = s.get(Deliverable, uuid.UUID(fin["id"])).summary or ""
    return {
        "pdf": _pdf(_get("pdf_artifact_id")),
        "docx": _docx(_get("docx_artifact_id")),
        "xlsx": _xlsx(_get("xlsx_artifact_id")),
        "summary": _flat(summary),
    }


def _admin(c) -> dict:
    admin = _register(c, "admin@example.com")
    return {"Authorization": f"Bearer {admin['tokens']['access_token']}"}


def _csf_finalized(c, h, *, tier: object, raw: bool = False) -> dict[str, str]:
    svc = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    _attach_intake_target(svc, csf_tier=None if raw else tier)
    if raw:
        _store_raw_target(svc, "csf_target_tier", tier)
    a = c.post(f"/csf/services/{svc}/assessments", headers=h).json()
    for ans in a["answers"][:3]:
        c.patch(f"/csf/answers/{ans['id']}", headers=h, json={"maturity_tier": 2})
    assert c.post(f"/csf/assessments/{a['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/csf/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    return _surfaces(c, h, fin.json())


def _zt_finalized(
    c,
    h,
    *,
    stage: object,
    kind: str = "zero_trust_cisa",
    raw: bool = False,
    override_every_row: bool = False,
) -> dict[str, str]:
    svc = c.post("/zt/services", headers=h, json={"kind": kind, "title": "ZT"}).json()["id"]
    _attach_intake_target(svc, zt_stage=None if raw else stage)
    if raw:
        _store_raw_target(svc, "zt_target_stage", stage)
    a = c.post(f"/zt/services/{svc}/assessments", headers=h).json()
    for ans in a["answers"]:
        body: dict = {"maturity_stage": 1}
        if override_every_row:
            body["target_stage"] = 2
        r = c.patch(f"/zt/answers/{ans['id']}", headers=h, json=body)
        assert r.status_code == 200, r.text
    assert c.post(f"/zt/assessments/{a['id']}/approve", headers=h).status_code == 200
    fin = c.post(f"/zt/services/{svc}/deliverables/finalize", headers=h)
    assert fin.status_code == 201, fin.text
    return _surfaces(c, h, fin.json())


def _says_on_every_surface(got: dict[str, str], sentence: str) -> None:
    for surface, body in got.items():
        assert sentence in body, f"{surface} does not say {sentence!r}: {body[-400:]!r}"


def _says_nothing_on_any_surface(got: dict[str, str]) -> None:
    for surface, body in got.items():
        assert "Default target" not in body, f"{surface}: {body[-400:]!r}"


# --- CSF -------------------------------------------------------------------


def test_csf_the_clients_own_tier_adds_nothing(app_client) -> None:  # noqa: F811
    """The positive control: a guard that disclosed on every source would pass
    every test below."""
    got = _csf_finalized(app_client, _admin(app_client), tier=3)
    assert "at target T3" in got["summary"]
    _says_nothing_on_any_surface(got)


@pytest.mark.parametrize(
    ("tier", "raw", "source"),
    [
        (None, False, "default"),
        (9, True, "client_out_of_range"),
        (1, True, "client_below_floor"),
    ],
)
def test_csf_a_target_the_client_did_not_choose_says_so(
    app_client, tier, raw, source  # noqa: F811
) -> None:
    got = _csf_finalized(app_client, _admin(app_client), tier=tier, raw=raw)
    _says_on_every_surface(got, TIER[source])
    # Beside the target, not somewhere later: the caption and the summary
    # state the target, and the sentence follows it directly.
    assert f"gap(s) at target T3. {TIER[source]}" in got["summary"]
    for surface in ("pdf", "docx", "xlsx"):
        assert f"at target T3. {TIER[source]}" in got[surface], surface


# --- ZT --------------------------------------------------------------------


def test_zt_the_clients_own_stage_adds_nothing(app_client) -> None:  # noqa: F811
    got = _zt_finalized(app_client, _admin(app_client), stage=3)
    assert "at target S3" in got["summary"]
    _says_nothing_on_any_surface(got)


@pytest.mark.parametrize(
    ("stage", "kind", "raw", "source"),
    [
        (None, "zero_trust_cisa", False, "default"),
        # DoD has three stages, so a stored 4 is a real stage the framework
        # does not have.
        (4, "zero_trust_dod", True, "client_out_of_range"),
        (1, "zero_trust_cisa", True, "client_below_floor"),
    ],
)
def test_zt_a_target_the_client_did_not_choose_says_so(
    app_client, stage, kind, raw, source  # noqa: F811
) -> None:
    got = _zt_finalized(app_client, _admin(app_client), stage=stage, kind=kind, raw=raw)
    _says_on_every_surface(got, STAGE[source])
    assert f"gap(s) at target S3. {STAGE[source]}" in got["summary"]
    for surface in ("pdf", "docx", "xlsx"):
        assert ("each row shows the target applied to that capability. " f"{STAGE[source]}") in got[
            surface
        ], surface


def test_zt_a_default_that_decided_no_capability_is_not_mentioned(
    app_client,  # noqa: F811
) -> None:
    """Every capability carries its own target, so the engagement target
    decided nothing. "No stage chosen at intake" is not a fault and not
    actionable then, and the dashboard's `targetNote` omits it for that
    reason."""
    got = _zt_finalized(app_client, _admin(app_client), stage=None, override_every_row=True)
    _says_nothing_on_any_surface(got)


def test_zt_a_failed_choice_is_stated_even_when_it_decided_no_capability(
    app_client,  # noqa: F811
) -> None:
    """...but a choice the client MADE that could not be used is still stated:
    it is the one state a consultant can act on, by re-asking."""
    got = _zt_finalized(
        app_client,
        _admin(app_client),
        stage=4,
        kind="zero_trust_dod",
        raw=True,
        override_every_row=True,
    )
    _says_on_every_surface(got, STAGE["client_out_of_range"])


# --- the sources no stored value can reach through the API -----------------
#
# `client_unparseable` needs a fraction or a non-number in a SMALLINT column,
# and an unrecognised source needs a resolver this build does not have. No
# writer produces either: the column refuses the first in Postgres, and every
# assessment response validates the stored target as an int (a raw 2.5 in
# SQLite 500s the assessment route before finalize is reached). The arms exist
# and are copy a client would read, so the resolver's VERDICT is substituted
# inside finalize and everything after it -- the context, the renderers, the
# stored bytes and the summary -- is real.


@pytest.mark.parametrize("source", ["client_unparseable", "unrecognised"])
def test_csf_an_unreachable_source_is_still_stated(
    app_client, monkeypatch, source  # noqa: F811
) -> None:
    import app.routes.csf as csf_routes

    monkeypatch.setattr(csf_routes, "resolve_target_tier", lambda _chosen: (3, source))
    got = _csf_finalized(app_client, _admin(app_client), tier=3)
    _says_on_every_surface(got, TIER[source])


@pytest.mark.parametrize("source", ["client_unparseable", "unrecognised"])
def test_zt_an_unreachable_source_is_still_stated(
    app_client, monkeypatch, source  # noqa: F811
) -> None:
    import app.routes.zt as zt_routes

    monkeypatch.setattr(zt_routes, "resolve_target_stage", lambda _fw, _chosen: (3, source))
    got = _zt_finalized(app_client, _admin(app_client), stage=3)
    _says_on_every_surface(got, STAGE[source])


# --- the one function ------------------------------------------------------


@pytest.mark.parametrize(("rung", "table"), [("tier", TIER), ("stage", STAGE)])
def test_every_source_has_its_sentence(rung, table) -> None:
    from app.assessment_targets import target_source_sentence

    assert target_source_sentence(rung, "client") is None
    for source, sentence in table.items():
        assert target_source_sentence(rung, source) == sentence, source
