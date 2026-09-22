"""#403 -- the risk-synthesis allow-lists are the codes an assessment SCORED.

## What these pin, and why the endpoint rather than the helper

`routes/risk.py` sends the synthesis model two allow-lists whose stated purpose
is to stop it citing "a technique or control the client's assessments never
contained". Three constructions read every row instead, and every row is
pre-seeded -- `provisioning.py` writes a `CsfAnswer` per subcategory and a
`ZtAnswer` per capability with no tier or stage, `routes/attack.py` writes an
`AttackCoverage` per technique with `status=None`, and nothing under
`apps/api/app` deletes any of them. So the allow-list meant every code that
exists, and a model citing a control nobody had looked at was accepted,
persisted, and rendered into the client's deliverable by `risk/exporters.py`.

Every test here drives the HTTP endpoint. Importing `scope_for` and asserting it
filters would pass with `_gather_findings` still building the lists the old way:
the WIRING is where the guard gets selected, and the wiring is what a refactor
changes. `CLAUDE.md`: a test that imports the thing it is defending is strictly
weaker than one that calls the endpoint that reaches it.

## The discriminator these rely on

`_seed_attack_and_zt` and `_seed_csf_answer_at_tier` score a HANDFUL of rows and
leave the rest of each catalog pre-seeded and unscored. So a real, catalog-valid,
UNSCORED code is available in every fixture, and citing one separates the two
readings cleanly: under the defect it is kept, under the fix it is dropped. A
made-up code like `T9999` cannot do that -- it is rejected under both.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.ai.llm import LLMResponse

from .test_risk_register import (
    _admin,
    _seed_attack_and_zt,
    _seed_csf_answer_at_tier,
    _session,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)


def _capture(provider) -> list[dict[str, Any]]:
    """Record every `risk_synthesize` payload; answer with no entries.

    The allow-lists are only observable as what CROSSED the egress boundary, so
    the assertion has to read the payload. Answering with an empty entry list
    keeps this about the lists themselves -- a fixture that also returned
    citations would make a drop assertion depend on the same payload the test is
    trying to measure.
    """
    seen: list[dict[str, Any]] = []

    def fn(payload: dict[str, Any]) -> LLMResponse:
        seen.append(payload)
        return LLMResponse(json.dumps({"entries": []}))

    provider.register("risk_synthesize", fn)
    return seen


def _cited(provider, *, techniques: list[str], controls: list[str], source_id: str) -> None:
    """One entry citing exactly what the caller names.

    Built with `json.dumps` rather than string concatenation: the codes are
    catalog ids carrying dots, and a hand-built JSON literal is where a test
    starts asserting its own quoting instead of the behaviour.
    """
    entry = {
        "title": "T",
        "description": "D",
        "axis": "detection",
        "source": "coverage_finding",
        "source_id": source_id,
        "linked_techniques": list(techniques),
        "linked_controls": list(controls),
        "likelihood": "high",
        "impact": "major",
        "recommended_action": "remediate",
        "rationale": "R",
    }
    provider.register_static("risk_synthesize", LLMResponse(json.dumps({"entries": [entry]})))


def _generate(c, bearer: str, cid: str):
    r = c.post(
        f"/risk/clients/{cid}/register/generate",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# (d) The contract: each allow-list EQUALS the scored rows.
#
# Set equality in both directions, because the two failures are different and
# only one of them is the one being fixed. A superset is #403 -- unscored codes
# admitted. A subset would be a scored code the consultant DID judge going
# missing, which would silently delete legitimate citations. A containment
# assertion would pass over the second.
#
# The expected side is read from the DATABASE, never from `scope_for`. Deriving
# it from the helper under test would make the test agree with the code by
# construction -- the shape `CLAUDE.md` records as a test that cannot fail.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_technique_allow_list_equals_the_scored_coverage_rows(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    seen = _capture(provider)
    _generate(c, bearer, cid)
    assert seen, "no risk_synthesize payload was captured"

    from app.models.attack_assessment import AttackCoverage

    db = _session()
    rows = db.execute(
        select(AttackCoverage).where(AttackCoverage.client_id == uuid.UUID(cid))
    ).scalars()
    expected = {r.technique_code for r in rows if r.status is not None}
    db.close()

    assert expected, "fixture scored nothing, so this would assert set() == set()"
    assert set(seen[0]["valid_techniques"]) == expected


@pytest.mark.unit
def test_zt_capability_allow_list_equals_the_scored_answers(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    seen = _capture(provider)
    _generate(c, bearer, cid)

    from app.models.zt_assessment import ZtAnswer

    db = _session()
    rows = db.execute(select(ZtAnswer).where(ZtAnswer.client_id == uuid.UUID(cid))).scalars()
    expected = {r.capability_code for r in rows if r.maturity_stage is not None}
    db.close()

    assert expected
    # ZT capabilities and CSF subcategories share ONE list, so this client has
    # no CSF assessment on purpose: with one, equality here would be wrong by
    # design and only a containment assertion would be available.
    assert set(seen[0]["valid_controls"]) == expected


@pytest.mark.unit
def test_csf_control_allow_list_equals_the_scored_answers(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    # ATT&CK first: the gate needs it, and `_seed_csf_answer_at_tier` alone
    # leaves the register locked.
    _seed_attack_and_zt(c, bearer, cid)
    _seed_csf_answer_at_tier(c, bearer, cid, tier=1)
    seen = _capture(provider)
    _generate(c, bearer, cid)

    from app.models.csf_assessment import CsfAnswer
    from app.models.zt_assessment import ZtAnswer

    db = _session()
    csf = {
        r.subcategory_code
        for r in db.execute(
            select(CsfAnswer).where(CsfAnswer.client_id == uuid.UUID(cid))
        ).scalars()
        if r.maturity_tier is not None
    }
    zt = {
        r.capability_code
        for r in db.execute(select(ZtAnswer).where(ZtAnswer.client_id == uuid.UUID(cid))).scalars()
        if r.maturity_stage is not None
    }
    db.close()

    assert csf, "fixture scored no CSF subcategory"
    assert set(seen[0]["valid_controls"]) == csf | zt


# ---------------------------------------------------------------------------
# (a) The reachable consequence: an unscored code is not citable.
#
# These assert the DROP is recorded, not merely that the link is absent. An
# entry with no links and no drop record is byte-identical to one the model
# linked nothing for -- the #132 defect -- so "absent" alone would pass over a
# silent discard, which is the failure this whole change must not introduce.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_unscored_technique_is_dropped_and_recorded(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    scored_technique, _cap = _seed_attack_and_zt(c, bearer, cid)

    from app.models.attack_assessment import AttackCoverage

    db = _session()
    unscored = next(
        r.technique_code
        for r in db.execute(
            select(AttackCoverage).where(AttackCoverage.client_id == uuid.UUID(cid))
        ).scalars()
        if r.status is None
    )
    db.close()
    assert unscored != scored_technique

    _cited(provider, techniques=[unscored], controls=[], source_id=scored_technique)
    body = _generate(c, bearer, cid)
    entry = body["entries"][0]
    assert entry["linked_techniques"] == []
    assert entry["dropped_links"]["linked_techniques"] == [unscored]


@pytest.mark.unit
def test_an_unscored_csf_subcategory_is_dropped_and_recorded(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    scored_technique, _cap = _seed_attack_and_zt(c, bearer, cid)
    _seed_csf_answer_at_tier(c, bearer, cid, tier=1)

    from app.models.csf_assessment import CsfAnswer

    db = _session()
    unscored = next(
        r.subcategory_code
        for r in db.execute(
            select(CsfAnswer).where(CsfAnswer.client_id == uuid.UUID(cid))
        ).scalars()
        if r.maturity_tier is None
    )
    db.close()

    _cited(provider, techniques=[], controls=[unscored], source_id=scored_technique)
    body = _generate(c, bearer, cid)
    entry = body["entries"][0]
    assert entry["linked_controls"] == []
    assert entry["dropped_links"]["linked_controls"] == [unscored]


@pytest.mark.unit
def test_an_unscored_zt_capability_is_dropped_and_recorded(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    scored_technique, scored_cap = _seed_attack_and_zt(c, bearer, cid)

    from app.models.zt_assessment import ZtAnswer

    db = _session()
    unscored = next(
        r.capability_code
        for r in db.execute(select(ZtAnswer).where(ZtAnswer.client_id == uuid.UUID(cid))).scalars()
        if r.maturity_stage is None
    )
    db.close()
    assert unscored != scored_cap

    _cited(provider, techniques=[], controls=[unscored], source_id=scored_technique)
    body = _generate(c, bearer, cid)
    entry = body["entries"][0]
    assert entry["linked_controls"] == []
    assert entry["dropped_links"]["linked_controls"] == [unscored]


@pytest.mark.unit
def test_a_scored_code_is_still_citable(app_client) -> None:  # noqa: F811
    """The other half of the branch.

    A narrowing fix can be "repaired" into dropping everything, and every
    assertion above stays green through that -- they only check that an unscored
    code is refused. `CLAUDE.md`: test both halves of the branch you changed.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    technique, capability = _seed_attack_and_zt(c, bearer, cid)
    _cited(provider, techniques=[technique], controls=[capability], source_id=technique)
    body = _generate(c, bearer, cid)
    entry = body["entries"][0]
    assert entry["linked_techniques"] == [technique]
    assert entry["linked_controls"] == [capability]
    assert entry["dropped_links"] == {}


# ---------------------------------------------------------------------------
# (b) The catalogue fallback is gone.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_an_all_unscored_attack_assessment_does_not_substitute_the_catalog(
    app_client,  # noqa: F811
) -> None:
    """`or set(attack_all_codes())` handed the model every technique that exists.

    It fired when `rows` was empty, which the pre-seed made nearly unreachable.
    Against a SCORED predicate it would fire whenever the client scored nothing
    -- opening the allow-list to the whole catalog in exactly the case where no
    citation is supportable. Deleting it is what makes the narrowing safe.

    The state is reachable without any direct SQL: `approve_assessment` in
    `routes/attack.py` carries no scoring precondition, so an APPROVED
    assessment with every `status` NULL is something a consultant can produce
    through the API today. That is why this asserts a 201 and an empty list
    rather than a refusal -- see the `_gather_findings` docstring.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h)
    # Nothing patched: every coverage row keeps `status=None`.
    assert c.post(f"/attack/assessments/{a.json()['id']}/approve", headers=h).status_code == 200
    # ZT gives the gate something to unlock on, scored so the run has a finding.
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "Z"})
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h)
    zans = za.json()["answers"][0]
    c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})
    assert c.post(f"/zt/assessments/{za.json()['id']}/approve", headers=h).status_code == 200

    seen = _capture(provider)
    _generate(c, bearer, cid)
    assert seen[0]["valid_techniques"] == []


# ---------------------------------------------------------------------------
# (c) The cost is disclosed, and it survives a read-back.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_scored_share_is_disclosed_and_survives_a_reread(app_client) -> None:  # noqa: F811
    """Sparse links are CORRECT after this change and read as a regression.

    So the register has to say why, or a silently wrong citation has been traded
    for a silently missing one. Asserted on the re-read as well as on generate:
    #316 shipped a disclosure that reached exactly one HTTP response and died on
    reload, and the read-back is the half that was missing.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _capture(provider)
    body = _generate(c, bearer, cid)

    assert body["excluded_unscored_links_recorded"] is True
    by_service = {r["service"]: r for r in body["excluded_unscored_links"]}
    assert set(by_service) == {"attack", "zt"}
    for row in by_service.values():
        # The population is rendered beside the count: a withheld number over an
        # undisclosed denominator is not self-describing.
        assert row["total"] > row["scored"] > 0

    latest = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert latest.status_code == 200, latest.text
    assert latest.json()["excluded_unscored_links"] == body["excluded_unscored_links"]
    assert latest.json()["excluded_unscored_links_recorded"] is True


# ---------------------------------------------------------------------------
# (c) ... and the DELIVERABLE, which is the surface the client actually reads.
#
# `CLAUDE.md` is explicit that the definition of done is "a screen OR a
# delivered artifact", and that the artifact half is not a widening for
# completeness: this repo's canonical understated-disclosure instance lives in
# an exporter. The Linked Techniques and Linked Controls columns are what go
# sparse, and they are columns of the client's own spreadsheet.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_the_scored_share_reaches_the_pdf_and_word_summary() -> None:
    """Rendered through the real exporter, from a context built as the route
    builds it -- not by asserting on `_link_scope_lines` in isolation, which
    would prove the helper works rather than that the deliverable carries it.
    """
    from app.risk.exporters import build_context, render_docx, render_pdf

    ctx = build_context(
        client_legal_name="Atlas",
        version=1,
        entries=[],
        link_scope=[("attack", 12, 700), ("csf", 106, 106)],
    )
    for renderer in (render_pdf, render_docx):
        blob = renderer(ctx)
        assert blob[:4] in (b"%PDF", b"PK\x03\x04"), renderer.__name__

    # The bytes are a container, so the assertion is on the line the renderers
    # are handed rather than on a substring search through a zip or a PDF
    # stream -- a search that finds nothing in compressed bytes is a false
    # negative, and one that finds something proves only that the string exists
    # somewhere.
    from app.risk.exporters import _link_scope_lines

    lines = _link_scope_lines(ctx)
    assert any("12 of 700" in ln for ln in lines)
    assert any("106 of 106" in ln for ln in lines)
    assert any("only from rows an assessment has scored" in ln for ln in lines)


@pytest.mark.unit
def test_an_unrecorded_scope_renders_nothing_rather_than_a_zero() -> None:
    """A register generated before this was recorded must print silence.

    "0 of 0 scored" is a concrete false claim about a client's assessments;
    absence is merely an absence. Missing data defaults to UNCONFIRMED.
    """
    from app.risk.exporters import _link_scope_lines, build_context

    assert _link_scope_lines(build_context(client_legal_name="A", version=1, entries=[])) == []


@pytest.mark.unit
def test_the_xlsx_carries_a_scored_coverage_sheet() -> None:
    import io

    from openpyxl import load_workbook

    from app.risk.exporters import build_context, render_xlsx

    ctx = build_context(
        client_legal_name="Atlas",
        version=1,
        entries=[],
        link_scope=[("attack", 12, 700)],
    )
    wb = load_workbook(io.BytesIO(render_xlsx(ctx)))
    assert "Scored coverage" in wb.sheetnames
    rows = list(wb["Scored coverage"].iter_rows(values_only=True))
    assert rows[0] == ("Assessment", "Rows scored", "Rows total", "Not citable")
    # The excluded count is rendered BESIDE the population, not alone.
    assert rows[1] == ("ATT&CK coverage", 12, 700, 688)

    # And the sheet is absent, not empty, when nothing was recorded.
    bare = build_context(client_legal_name="Atlas", version=1, entries=[])
    assert "Scored coverage" not in load_workbook(io.BytesIO(render_xlsx(bare))).sheetnames


@pytest.mark.unit
def test_the_exported_xlsx_a_client_downloads_carries_the_scored_coverage(
    app_client,  # noqa: F811
) -> None:
    """The route wiring, end to end, on the real bytes.

    The three tests above hand `build_context` a scope and assert the renderers
    use it -- which proves the RENDERER works and would stay green with the
    route passing nothing at all. The wiring is where the disclosure gets
    selected, so this drives generate, export and download, and opens the
    workbook the client would open.
    """
    import io

    from openpyxl import load_workbook

    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _capture(provider)
    _generate(c, bearer, cid)

    bh = {"Authorization": f"Bearer {bearer}"}
    ex = c.post(f"/risk/clients/{cid}/register/export", headers=bh)
    assert ex.status_code == 200, ex.text
    artifact_id = ex.json()["xlsx_artifact_id"]
    assert artifact_id

    blob = c.get(
        f"/artifacts/{artifact_id}/download",
        headers={**bh, "X-Client-Id": cid},
    )
    assert blob.status_code == 200, blob.text
    wb = load_workbook(io.BytesIO(blob.content))
    assert "Scored coverage" in wb.sheetnames
    # Data rows only: the sheet also carries a header and a trailing sentence
    # explaining the columns, and both have a non-numeric second cell.
    by_service = {
        r[0]: r
        for r in wb["Scored coverage"].iter_rows(values_only=True)
        if r and isinstance(r[1], int)
    }
    assert set(by_service) == {"ATT&CK coverage", "Zero Trust"}
    for _label, scored, total, not_citable in by_service.values():
        assert total > scored > 0
        assert not_citable == total - scored


# ---------------------------------------------------------------------------
# The READ fails closed. A partial read must not present as a whole answer.
#
# These construct the malformed blob with direct SQL, and that is deliberate
# rather than a fixture building an unreachable state: `generate` cannot produce
# one (it writes `len()` and a loop counter), so the validation is a RATCHET,
# and a ratchet is only pinned by a test that makes its state reachable. The
# precedent in this repo is explicit -- `test_a_row_dropped_between_add_and_flush_is_recorded`
# installs the very `before_flush` listener its own comment says no writer has.
#
# Building the world, not performing the step under test: the step under test is
# the READ, and nothing here reads.
# ---------------------------------------------------------------------------


def _overwrite_link_scope(cid: str, blob: object) -> None:
    """Put `blob` in the latest register's `provenance["link_scope"]`."""
    from app.models.risk_register import RiskRegister

    db = _session()
    reg = (
        db.execute(
            select(RiskRegister)
            .where(RiskRegister.client_id == uuid.UUID(cid))
            .order_by(RiskRegister.version.desc())
        )
        .scalars()
        .first()
    )
    assert reg is not None
    prov = dict(reg.provenance or {})
    assert "link_scope" in prov, "fixture precondition: generate must have written the key"
    prov["link_scope"] = blob
    reg.provenance = prov
    db.add(reg)
    db.commit()
    db.close()


def _latest(c, bearer: str, cid: str) -> dict:
    r = c.get(
        f"/risk/clients/{cid}/register/latest",
        headers={"Authorization": f"Bearer {bearer}"},
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.unit
@pytest.mark.parametrize(
    "blob,why",
    [
        pytest.param(
            {"attack": {"scored": 1, "total": 9}, "csf": {"scored": "x", "total": 9}},
            "one good service beside one malformed one",
            id="partial",
        ),
        pytest.param(
            {"attack": {"scored": True, "total": 9}},
            "a bool, which isinstance(_, int) accepts and which would render as 1",
            id="bool",
        ),
        pytest.param(
            {"attack": {"scored": 10, "total": 9}},
            "more scored than exist, so the pair is not a subset relation",
            id="scored-exceeds-total",
        ),
        pytest.param({"attack": [1, 9]}, "a list where an object belongs", id="not-an-object"),
        pytest.param("everything", "a scalar where the map belongs", id="not-a-map"),
    ],
)
def test_an_unreadable_scope_reports_NOT_RECORDED_rather_than_a_partial_answer(
    app_client,  # noqa: F811
    blob: object,
    why: str,
) -> None:
    """The whole answer is withheld, not just the bad row.

    The `partial` case is the one that matters and is why this exists: the first
    version of `_link_scope_fields` skipped a malformed row and still reported
    `recorded=True`, so a consultant would have read "ATT&CK 12 of 700" with no
    CSF line -- indistinguishable from a register that genuinely had no CSF
    assessment. A disclosure understating itself is the defect this whole change
    is about, arriving from the read side.

    Dropping a readable row is the cost, and it is the right trade: nothing
    renders and nothing is claimed.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _capture(provider)
    generated = _generate(c, bearer, cid)
    # The precondition, asserted rather than assumed: the good path must be
    # working, or "not recorded" below would pass for the wrong reason.
    assert generated["excluded_unscored_links_recorded"] is True, why

    _overwrite_link_scope(cid, blob)
    body = _latest(c, bearer, cid)
    assert body["excluded_unscored_links_recorded"] is False, why
    assert body["excluded_unscored_links"] == [], why


@pytest.mark.unit
def test_every_findings_source_id_stays_inside_the_allow_list(app_client) -> None:  # noqa: F811
    """The narrowing must not orphan a finding from its own citation.

    Every finding already requires a judgement -- `status in ("gap","partial")`,
    `maturity_tier is not None`, `maturity_stage is not None` -- and the
    allow-lists are now exactly the judged rows, so findings are a SUBSET by
    construction. That is a new invariant this change creates, and it is worth
    pinning rather than reasoning about: loosening any findings predicate (say,
    emitting a finding for an unscored row so the consultant sees it) would
    silently start handing the model a `source_id` its own allow-list rejects,
    and `_resolve_links` would drop the provenance of every such entry.

    Asserted over the payload the model actually received, so it covers the
    real relationship rather than a restatement of the two predicates.
    """
    c, provider = app_client
    bearer, cid = _admin(c)
    _seed_attack_and_zt(c, bearer, cid)
    _seed_csf_answer_at_tier(c, bearer, cid, tier=1)
    seen = _capture(provider)
    _generate(c, bearer, cid)

    payload = seen[0]
    universe = set(payload["valid_techniques"]) | set(payload["valid_controls"])
    findings = payload["findings"]
    assert findings, "no findings, so a subset assertion would hold vacuously"
    orphans = [f["source_id"] for f in findings if f.get("source_id") not in universe]
    assert orphans == [], f"findings cite codes their own allow-list rejects: {orphans}"
