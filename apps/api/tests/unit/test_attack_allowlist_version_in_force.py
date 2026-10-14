"""For #1012: Run AI's citation allow-list reads the SAME Tech Debt list
versions as the security tool list check that approve applies.

The ruling is R6b (#736 6094994432, landed in #1021): per Tech Debt service,
the newest APPROVED or RELEASED version is in force and its drafts are
ignored; a drafts-only service uses its newest draft; "newest" is the highest
version number. Before this change the allow-list offered every
non-discarded version, so Run AI could confirm a citation of a tool that only
a superseded version, or an open draft beside an approved version, held, and
approve then refused the row (#1012's two mismatches).

Every test drives the routes a consultant reaches: Run AI
(`POST /attack/services/{id}/run-ai`) and the AI-inputs panel
(`GET /attack/services/{id}/ai-inputs`). Each asserts a POSITIVE control
first (a tool the version in force holds is confirmed), so a run that
confirms nothing for an unrelated reason cannot pass the negative half.

Expected values are written from the ruling, never imported from the module
under test: the reason string below is the API contract the panel keys on.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.ai.llm import FixtureProvider, LLMResponse
from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service
from tests._ai_runs import run_ai_and_wait
from tests.unit.test_ai_runs_attack import World, app_parts  # noqa: F401  (fixture)
from tests.unit.test_ai_runs_attack import _world as _runs_world

pytestmark = pytest.mark.unit

V1_TOOL = "CrowdStrike Falcon"  # the world's v1 (APPROVED) holds exactly this
NEW_TOOL = "SentinelOne Singularity"
# The reason the AI-inputs panel keys on for a tool held only by a version
# that is not in force (#1012). A contract string, written out.
NOT_IN_FORCE = "version_not_in_force"


def _cite(w: World, tool: str) -> None:
    """Every batch answers `covered`, crediting `tool` as the detection tool."""
    provider = FixtureProvider()

    def respond(payload: dict) -> LLMResponse:
        sent = set(payload.get("technique_codes") or [])
        techniques = ",".join(
            '{"technique_code": "' + code + '", "status": "covered",'
            ' "detection_tools": ["' + tool + '"], "prevention_tools": [],'
            ' "response_tools": [], "rationale": "Detects."}'
            for code in w.codes
            if code in sent
        )
        return LLMResponse('{"techniques": [' + techniques + "]}")

    # `use_provider` registers the world's default response; ours replaces it.
    w.use_provider(provider)
    provider.register("mitre_map", respond)


def _run(w: World, tool: str) -> dict:
    _cite(w, tool)
    return run_ai_and_wait(w.c, w.run_url, w.h)


def _v1(w: World) -> CapabilityList:
    with w.sessions() as db:
        return db.execute(
            select(CapabilityList)
            .join(Service, CapabilityList.service_id == Service.id)
            .where(Service.client_id == uuid.UUID(w.cid), CapabilityList.version == 1)
        ).scalar_one()


def _add_version(
    w: World, names: list[str], *, status: CapabilityListStatus, version: int = 2
) -> str:
    """Another version of the world's Tech Debt service, holding `names` as
    security rows (no recorded snapshot, so it reads live, as v1 does)."""
    service_id = _v1(w).service_id
    with w.sessions() as db:
        cl = CapabilityList(service_id=service_id, version=version, status=status)
        db.add(cl)
        db.flush()
        for name in names:
            db.add(CapabilityItem(capability_list_id=cl.id, name=name, security_related=True))
        db.commit()
        return str(cl.id)


def _set_v1_status(w: World, status: CapabilityListStatus) -> None:
    with w.sessions() as db:
        cl = db.get(CapabilityList, _v1(w).id)
        cl.status = status
        db.commit()


def _detection_tools(w: World) -> set[str]:
    return {t for code in w.codes for t in (w.row(code).detection_tools or [])}


def _inputs(w: World) -> dict:
    r = w.c.get(f"/attack/services/{w.svc_id}/ai-inputs", headers=w.h)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Mismatch 1: a superseded version
# ---------------------------------------------------------------------------


def test_a_tool_only_a_superseded_approved_version_holds_is_not_citable(
    app_parts,  # noqa: F811
) -> None:
    w = _runs_world(app_parts)
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    positive = _run(w, NEW_TOOL)
    assert positive["citations_confirmed"] == len(w.codes), positive
    assert _detection_tools(w) == {NEW_TOOL}
    result = _run(w, V1_TOOL)
    assert result["citations_confirmed"] == 0, result
    assert result["citations_rejected"] == len(w.codes), result
    assert V1_TOOL not in _detection_tools(w)


def test_a_superseded_versions_tool_is_named_as_withheld_on_the_ai_inputs_panel(
    app_parts,  # noqa: F811
) -> None:
    w = _runs_world(app_parts)
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [NEW_TOOL], body["capabilities"]
    withheld = {d["name"]: d for d in body["not_sent"]}
    assert withheld[V1_TOOL]["reason"] == NOT_IN_FORCE, body["not_sent"]
    assert withheld[V1_TOOL]["source_list_version"] == 1
    assert body["totals"]["withheld_version_not_in_force"] == 1, body["totals"]
    in_force = {s["version"]: s["in_force"] for s in body["sources"]}
    assert in_force == {1: False, 2: True}, body["sources"]


# ---------------------------------------------------------------------------
# Mismatch 2: an open draft beside an approved version (new under R6)
# ---------------------------------------------------------------------------


def test_a_tool_only_an_open_draft_beside_an_approved_version_holds_is_not_citable(
    app_parts,  # noqa: F811
) -> None:
    w = _runs_world(app_parts)
    _add_version(w, [V1_TOOL, NEW_TOOL], status=CapabilityListStatus.DRAFT)
    positive = _run(w, V1_TOOL)
    assert positive["citations_confirmed"] == len(w.codes), positive
    result = _run(w, NEW_TOOL)
    assert result["citations_confirmed"] == 0, result
    assert result["citations_rejected"] == len(w.codes), result
    assert NEW_TOOL not in _detection_tools(w)
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [V1_TOOL], body["capabilities"]
    assert {d["name"]: d["reason"] for d in body["not_sent"]} == {NEW_TOOL: NOT_IN_FORCE}
    in_force = {s["version"]: s["in_force"] for s in body["sources"]}
    assert in_force == {1: True, 2: False}, body["sources"]


# ---------------------------------------------------------------------------
# The drafts-only half of R6b, and the empty-version fallback (C8a/C8b)
# ---------------------------------------------------------------------------


def test_in_a_drafts_only_service_the_open_draft_is_citable(app_parts) -> None:  # noqa: F811
    """The drafts-only half of R6b: with no approved or released version, the
    open draft IS the version in force, so its tools are offered.

    A service holds at most ONE draft (migration 0073,
    `uq_capability_lists_one_draft`; the extract route returns or refuses an
    open draft rather than cutting a second), so "the newest draft" has one
    candidate and two drafts at once are not built here: no writer can
    produce them. The reachable drafts-only service with an older version is
    this one: v1, a draft, discarded through the route before v2 is cut. Its
    tool is withheld because the list was discarded, not as not in force."""
    w = _runs_world(app_parts)
    _set_v1_status(w, CapabilityListStatus.DRAFT)
    v1 = _v1(w).id
    r = w.c.post(f"/tech-debt/capability-lists/{v1}/discard", headers=w.h)
    assert r.status_code == 200, r.text
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.DRAFT)
    positive = _run(w, NEW_TOOL)
    assert positive["citations_confirmed"] == len(w.codes), positive
    assert _detection_tools(w) == {NEW_TOOL}
    result = _run(w, V1_TOOL)
    assert result["citations_confirmed"] == 0, result
    assert result["citations_rejected"] == len(w.codes), result
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [NEW_TOOL], body["capabilities"]
    withheld = {d["name"]: d["reason"] for d in body["not_sent"]}
    assert withheld == {V1_TOOL: "list_discarded"}, body["not_sent"]
    in_force = {s["version"]: s["in_force"] for s in body["sources"]}
    assert in_force == {1: None, 2: True}, body["sources"]


def test_an_approved_version_with_no_security_row_leaves_the_previous_one_in_force(
    app_parts,  # noqa: F811
) -> None:
    """R4 (b), as the security tool list check reads it: a newer approved
    version offering no security row does not vote, the newest earlier one
    that has some does. The allow-list must agree, or Run AI would offer
    nothing while approve accepts v1's tools."""
    w = _runs_world(app_parts)
    _add_version(w, [], status=CapabilityListStatus.APPROVED)
    result = _run(w, V1_TOOL)
    assert result["citations_confirmed"] == len(w.codes), result
    assert _detection_tools(w) == {V1_TOOL}
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [V1_TOOL], body["capabilities"]
    assert body["not_sent"] == [], body["not_sent"]


def test_a_tool_on_the_version_in_force_and_a_superseded_one_is_sent_not_withheld(
    app_parts,  # noqa: F811
) -> None:
    """A name citable through the version in force is never ALSO reported
    withheld because an older version holds it too."""
    w = _runs_world(app_parts)
    _add_version(w, [V1_TOOL, NEW_TOOL], status=CapabilityListStatus.APPROVED)
    body = _inputs(w)
    assert sorted(c["name"] for c in body["capabilities"]) == sorted([V1_TOOL, NEW_TOOL])
    assert body["not_sent"] == [], body["not_sent"]
    sent_v = {c["name"]: c["source_list_version"] for c in body["capabilities"]}
    assert sent_v == {V1_TOOL: 2, NEW_TOOL: 2}, sent_v


def test_the_version_in_force_decides_why_a_tool_is_withheld(app_parts) -> None:  # noqa: F811
    """v2 (in force) holds the v1 tool confirmed NOT security; v1 holds it in
    scope. It is withheld because a consultant ruled it out of scope on the
    version in force, not because an older version is not in force."""
    w = _runs_world(app_parts)
    v2 = _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    with w.sessions() as db:
        db.add(
            CapabilityItem(
                capability_list_id=uuid.UUID(v2),
                name=V1_TOOL,
                security_related=False,
                security_class_confirmed=True,
            )
        )
        db.commit()
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [NEW_TOOL], body["capabilities"]
    withheld = {d["name"]: (d["reason"], d["source_list_version"]) for d in body["not_sent"]}
    assert withheld == {V1_TOOL: ("security_scope", 2)}, body["not_sent"]


def test_a_superseded_versions_approved_snapshot_is_withheld_too(app_parts) -> None:  # noqa: F811
    """The post-0043 path: v1 approved THROUGH THE ROUTE, so its membership is
    the recorded snapshot (`from_snapshot`), not its live rows. Superseded by
    an approved v2, its snapshot entry is withheld, not offered."""
    from app.models.capability import CapabilityDisposition

    w = _runs_world(app_parts)
    v1 = _v1(w)
    with w.sessions() as db:
        cl = db.get(CapabilityList, v1.id)
        cl.status = CapabilityListStatus.DRAFT
        for item in db.execute(
            select(CapabilityItem).where(CapabilityItem.capability_list_id == v1.id)
        ).scalars():
            item.disposition = CapabilityDisposition.KEEP
            item.security_related = True
        db.commit()
    r = w.c.post(f"/tech-debt/capability-lists/{v1.id}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    with w.sessions() as db:
        snapshot = db.get(CapabilityList, v1.id).approved_membership
    assert [e["name"] for e in snapshot] == [V1_TOOL], snapshot  # the snapshot path
    positive = _inputs(w)
    assert [c["name"] for c in positive["capabilities"]] == [V1_TOOL], positive
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [NEW_TOOL], body["capabilities"]
    assert {d["name"]: d["reason"] for d in body["not_sent"]} == {V1_TOOL: NOT_IN_FORCE}
    sources = {
        s["version"]: (s["in_force"], s["membership_from_snapshot"]) for s in body["sources"]
    }
    assert sources == {1: (False, True), 2: (True, False)}, body["sources"]
    result = _run(w, V1_TOOL)
    assert result["citations_confirmed"] == 0, result
    assert result["citations_rejected"] == len(w.codes), result


LATE_TOOL = "Darktrace Enterprise"


def _v1_approved_through_the_route_with_a_late_row(w: World) -> None:
    """v1 approved THROUGH THE ROUTE (its snapshot holds V1_TOOL), then a
    security row added to it after approval, so the live row is absent from
    the snapshot."""
    from app.models.capability import CapabilityDisposition

    v1 = _v1(w)
    with w.sessions() as db:
        cl = db.get(CapabilityList, v1.id)
        cl.status = CapabilityListStatus.DRAFT
        for item in db.execute(
            select(CapabilityItem).where(CapabilityItem.capability_list_id == v1.id)
        ).scalars():
            item.disposition = CapabilityDisposition.KEEP
            item.security_related = True
        db.commit()
    r = w.c.post(f"/tech-debt/capability-lists/{v1.id}/approve", headers=w.h)
    assert r.status_code == 200, r.text
    with w.sessions() as db:
        db.add(CapabilityItem(capability_list_id=v1.id, name=LATE_TOOL, security_related=True))
        db.commit()
        snapshot = db.get(CapabilityList, v1.id).approved_membership
    assert [e["name"] for e in snapshot] == [V1_TOOL], snapshot


def test_a_late_row_on_a_version_in_force_reads_absent_from_the_snapshot(
    app_parts,  # noqa: F811
) -> None:
    """The POSITIVE control for the test below: while v1 IS in force, its
    late row is withheld as absent from the snapshot, which re-approving v1
    does clear."""
    w = _runs_world(app_parts)
    _v1_approved_through_the_route_with_a_late_row(w)
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [V1_TOOL], body["capabilities"]
    assert {d["name"]: d["reason"] for d in body["not_sent"]} == {
        LATE_TOOL: "not_in_approved_snapshot"
    }, body["not_sent"]


def test_a_late_row_on_a_version_not_in_force_is_withheld_as_not_in_force(
    app_parts,  # noqa: F811
) -> None:
    """v1 and v2 are both APPROVED, so v2 is in force. A tool added to v1
    after its approval is absent from v1's snapshot, but re-approving v1
    would change nothing: v1 is not in force. The reason is the version, not
    the snapshot, so the panel never tells the consultant to re-approve v1."""
    w = _runs_world(app_parts)
    _v1_approved_through_the_route_with_a_late_row(w)
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    body = _inputs(w)
    assert [c["name"] for c in body["capabilities"]] == [NEW_TOOL], body["capabilities"]
    withheld = {d["name"]: (d["reason"], d["source_list_version"]) for d in body["not_sent"]}
    assert withheld == {V1_TOOL: (NOT_IN_FORCE, 1), LATE_TOOL: (NOT_IN_FORCE, 1)}, body["not_sent"]
    assert body["totals"]["withheld_not_in_approved_snapshot"] == 0, body["totals"]
    assert body["totals"]["withheld_version_not_in_force"] == 2, body["totals"]


def test_a_late_tool_on_two_versions_out_of_force_is_withheld_as_not_in_force(
    app_parts,  # noqa: F811
) -> None:
    """The late tool sits on v1 (not in force, absent from v1's snapshot) and
    on v3 (an open draft beside approved versions: not in force) and nowhere
    on v2. Both lists are out of force, so the tool is withheld as not in
    force whichever list is read first, never as absent from a snapshot."""
    w = _runs_world(app_parts)
    _v1_approved_through_the_route_with_a_late_row(w)
    _add_version(w, [NEW_TOOL], status=CapabilityListStatus.APPROVED)
    _add_version(w, [LATE_TOOL], status=CapabilityListStatus.DRAFT, version=3)
    body = _inputs(w)
    reasons = {d["name"]: d["reason"] for d in body["not_sent"]}
    assert reasons == {V1_TOOL: NOT_IN_FORCE, LATE_TOOL: NOT_IN_FORCE}, body["not_sent"]


# ---------------------------------------------------------------------------
# The precedence between two reports of one withheld tool, as a table
# ---------------------------------------------------------------------------

# Written from the rule, not read from the module: between lists equally in
# force, absent-from-snapshot beats not-in-force beats discarded beats
# out-of-scope; the same reason twice keeps the first report.
_SNAP, _NIF, _DISC, _SCOPE = (
    "not_in_approved_snapshot",
    "version_not_in_force",
    "list_discarded",
    "security_scope",
)
_KEPT = {
    (_SNAP, _SNAP): "held",
    (_SNAP, _NIF): "held",
    (_SNAP, _DISC): "held",
    (_SNAP, _SCOPE): "held",
    (_NIF, _SNAP): "later",
    (_NIF, _NIF): "held",
    (_NIF, _DISC): "held",
    (_NIF, _SCOPE): "held",
    (_DISC, _SNAP): "later",
    (_DISC, _NIF): "later",
    (_DISC, _DISC): "held",
    (_DISC, _SCOPE): "held",
    (_SCOPE, _SNAP): "later",
    (_SCOPE, _NIF): "later",
    (_SCOPE, _DISC): "later",
    (_SCOPE, _SCOPE): "held",
}


def _report(reason: str, list_id: uuid.UUID):
    from app.routes.attack import WithheldCapability

    return WithheldCapability(
        name="Tool", vendor=None, reason=reason, capability_list_id=list_id, list_version=1
    )


def test_the_precedence_table_covers_every_pair() -> None:
    # test-integrity: only the module table's KEYS are read, and they are
    # compared to `_KEPT`, written from the ruling; the kept VALUES are judged
    # through `_withheld_replaces` below, never read from the table.
    from app.routes.attack import _WITHHELD_PRECEDENCE

    reasons = {_SNAP, _NIF, _DISC, _SCOPE}
    assert set(_KEPT) == {(a, b) for a in reasons for b in reasons}
    assert set(_WITHHELD_PRECEDENCE) == set(_KEPT), set(_KEPT) ^ set(_WITHHELD_PRECEDENCE)


@pytest.mark.parametrize(("held", "later"), sorted(_KEPT))
def test_between_lists_equally_in_force_the_table_decides(held: str, later: str) -> None:
    from app.routes.attack import _withheld_replaces

    a, b = uuid.uuid4(), uuid.uuid4()
    for in_force in (frozenset({a, b}), frozenset()):
        replaced = _withheld_replaces(_report(held, a), _report(later, b), in_force)
        assert replaced is (_KEPT[(held, later)] == "later"), (held, later, in_force)


@pytest.mark.parametrize(("held", "later"), sorted(_KEPT))
def test_a_report_from_the_list_in_force_always_wins(held: str, later: str) -> None:
    from app.routes.attack import _withheld_replaces

    a, b = uuid.uuid4(), uuid.uuid4()
    assert _withheld_replaces(_report(held, a), _report(later, b), frozenset({b})) is True
    assert _withheld_replaces(_report(held, a), _report(later, b), frozenset({a})) is False
