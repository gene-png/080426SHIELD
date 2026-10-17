"""#1156: which sentence a `changed` input gets, as ONE table (the
specification), after five review rounds each fixing one state of it.

Two levels, because the discard promise is about the REGISTER:

1. Per input, `changed_remedy(was, newest)`: the status the register drew on
   and the newest record's status give a remedy. DISCARD_DRAFT is only a
   CANDIDATE (the register drew on released work and the newest record is a
   draft).
2. `publish_blockers` KEEPS a candidate only if re-running the same gate with
   the draft removed returns no blockers. So "Discard that draft, then publish
   again" is offered exactly when doing it publishes: not beside any other
   blocker, not when a CSF Playbook fingerprint has drifted, not when the draft
   sits on another unreleased record. The tests FOLLOW the remedy (discard,
   then publish, expect 200) in ZT, CSF (with a seed in between) and Tech Debt.

| was        | newest                   | remedy        |
| released   | draft                    | DISCARD_DRAFT (candidate) |
| any        | submitted / approved     | RELEASE_NEWER |
| unreleased | draft                    | RELEASE_NEWER |
| any        | released / none          | REGENERATE    |

The sentences are the advisor's (#736 6225640724 item 5 and 6228351462 item 4),
typed here from those comments, never read from the code.
"""

from __future__ import annotations

import pytest

from app.risk.inputs import (
    DISCARD_DRAFT,
    REGENERATE,
    RELEASE_NEWER,
    Blocker,
    changed_remedy,
)
from app.routes.risk import _inputs_not_final_message
from tests._risk_inputs import release, seed_attack_and_zt, seed_released
from tests.unit.test_risk_publish_inputs import _blockers, _gen, _publish
from tests.unit.test_risk_register import _admin, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_WAS = ("draft", "submitted", "approved", "released")
_ROWS = (
    [("released", "draft", DISCARD_DRAFT)]
    + [(w, "draft", RELEASE_NEWER) for w in ("draft", "submitted", "approved")]
    + [(w, n, RELEASE_NEWER) for w in _WAS for n in ("submitted", "approved")]
    + [(w, n, REGENERATE) for w in _WAS for n in ("released", None)]
)


def test_the_table_covers_every_state() -> None:
    keys = {(w, n) for (w, n, _r) in _ROWS}
    every = {(w, n) for w in _WAS for n in ("draft", "submitted", "approved", "released", None)}
    assert len(_ROWS) == len(keys) == len(every) == 20, (len(_ROWS), len(keys), len(every))
    assert keys == every


@pytest.mark.parametrize(("was", "newest", "expected"), _ROWS)
def test_the_remedy_for_every_state(was, newest, expected) -> None:
    assert changed_remedy(was_status=was, newest_status=newest) == expected


_DISCARD = (
    "This register can't be published while a newer draft is open. Discard that "
    "draft, then publish again. Or release the draft, then generate a new version "
    "before publishing."
)
_WAITING = (
    "This register can't be published while a newer version of an assessment it "
    "draws on is waiting to be released: Zero Trust ({state}). Release that "
    "version, then generate a new version before publishing."
)
_REGENERATE = (
    "An assessment this register draws on has changed since it was generated: "
    "Zero Trust. Generate a new version before publishing."
)


@pytest.mark.parametrize(
    ("status", "remedy", "sentence"),
    [
        ("draft", DISCARD_DRAFT, _DISCARD),
        ("draft", RELEASE_NEWER, _WAITING.format(state="in progress (draft)")),
        ("submitted", RELEASE_NEWER, _WAITING.format(state="submitted, not yet released")),
        ("approved", RELEASE_NEWER, _WAITING.format(state="approved, not yet released")),
        ("released", REGENERATE, _REGENERATE),
        (None, REGENERATE, _REGENERATE),
    ],
)
def test_each_remedy_reads_as_its_approved_sentence(status, remedy, sentence) -> None:
    assert _inputs_not_final_message([Blocker("zt", "changed", status, remedy)]) == sentence


def _revise(c, bearer, cid, zt_service, from_id, *, approve: bool) -> str:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.post(
        f"/zt/services/{zt_service}/assessments/{from_id}/revisions",
        headers=h,
        json={"reason": "Client asked for a correction."},
    )
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["status"] == "draft", new["status"]
    if approve:
        ok = c.post(f"/zt/assessments/{new['id']}/approve", headers=h)
        assert ok.status_code == 200, ok.text
    return new["id"]


def test_unreleased_at_generate_with_an_approved_newer_version_says_release_it(
    app_client,  # noqa: F811
) -> None:
    # Review round 3 F1': ZT was only APPROVED at generate, then a revision is
    # approved. A new version would draw on that unreleased v2 and be refused.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)
    _gen(c, provider, bearer, cid)
    _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=True)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "approved"}]
    assert r.json()["error"]["message"] == _WAITING.format(state="approved, not yet released")


def test_a_draft_over_an_unreleased_version_is_not_told_to_discard_it(
    app_client,  # noqa: F811
) -> None:
    # Review round 3 F5: v1 released, generate, v2 approved (not released), v3
    # drafted on v2. Discarding v3 leaves v2, still not the recorded v1.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    v2 = _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=True)
    _revise(c, bearer, cid, s.zt_service, v2, approve=False)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "draft"}]
    assert r.json()["error"]["message"] == _WAITING.format(state="in progress (draft)")


def test_a_draft_directly_over_the_recorded_released_version_says_discard(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "draft"}]
    assert r.json()["error"]["message"] == _DISCARD


def test_unreleased_at_generate_with_a_revision_draft_is_not_told_to_discard_it(
    app_client,  # noqa: F811
) -> None:
    # Review round 3 F1: ZT was only APPROVED at generate, then a revision
    # draft is opened. Discarding it cannot publish this register (it drew on
    # unreleased work); releasing v1 later still meets `changed`.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)  # ZT stays approved
    _gen(c, provider, bearer, cid)
    _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "draft"}]
    message = r.json()["error"]["message"]
    assert message == _WAITING.format(state="in progress (draft)"), message
    assert "Discard" not in message, message


# The unit of the specification is the REGISTER: the whole set of blockers.
# "Discard that draft, then publish again" is true only when EVERY blocker is a
# discardable draft; beside any other blocker the publish after the discard is
# still refused, so the draft reads as "waiting to be released".
_DRAFT_OVER_RELEASED = Blocker("attack", "changed", "draft", DISCARD_DRAFT)


_DRAFT_WAITING = (
    "This register can't be published while a newer version of an assessment it "
    "draws on is waiting to be released: ATT&CK coverage (in progress (draft)). "
    "Release that version, then generate a new version before publishing."
)


@pytest.mark.parametrize(
    ("others", "expected"),
    [
        (
            Blocker("zt", "not_released", "approved"),
            "This register cannot be published until every assessment it draws on is "
            "released: Zero Trust (approved, not yet released). " + _DRAFT_WAITING,
        ),
        (
            Blocker("zt", "changed", "approved", RELEASE_NEWER),
            "This register can't be published while newer versions of assessments it "
            "draws on are waiting to be released: ATT&CK coverage (in progress (draft)); "
            "Zero Trust (approved, not yet released). Release those versions, then "
            "generate a new version before publishing.",
        ),
        (
            Blocker("zt", "changed", "released", REGENERATE),
            _DRAFT_WAITING + " An assessment this register draws on has changed since it "
            "was generated: Zero Trust. Generate a new version before publishing.",
        ),
        (
            Blocker("zt", "not_started", None),
            "This register cannot be published until every assessment it draws on is "
            "released: Zero Trust (not started). " + _DRAFT_WAITING,
        ),
    ],
)
def test_a_discardable_draft_beside_any_other_blocker_reads_as_waiting(others, expected) -> None:
    assert _inputs_not_final_message([_DRAFT_OVER_RELEASED, others]) == expected


def test_two_discardable_drafts_still_read_as_the_approved_discard_sentence() -> None:
    message = _inputs_not_final_message(
        [_DRAFT_OVER_RELEASED, Blocker("zt", "changed", "draft", DISCARD_DRAFT)]
    )
    assert message == _DISCARD, message


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def test_an_attack_draft_beside_an_unreleased_zt_is_not_told_to_discard_and_publish(
    app_client,  # noqa: F811
) -> None:
    # ATT&CK released, ZT only approved at generate; then an ATT&CK revision.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)
    _gen(c, provider, bearer, cid)
    r = c.post(
        f"/attack/services/{s.attack_service}/assessments/{s.attack_assessment}/revisions",
        headers=_h(bearer, cid),
        json={"reason": "Client asked for a correction."},
    )
    assert r.status_code == 201, r.text
    p = _publish(c, bearer, cid)
    assert {b["input"] for b in _blockers(p)} == {"attack", "zt"}
    assert p.json()["error"]["message"] == (
        "This register cannot be published until every assessment it draws on is "
        "released: Zero Trust (approved, not yet released). " + _DRAFT_WAITING
    )


def test_following_discard_publishes(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    v2 = _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    assert _publish(c, bearer, cid).json()["error"]["message"] == _DISCARD
    d = c.post(f"/zt/assessments/{v2}/discard", headers=_h(bearer, cid))
    assert d.status_code == 200, d.text
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


def test_following_discard_after_a_version_gap_publishes(app_client) -> None:  # noqa: F811
    # v2 drafted then discarded, v3 drafted on v1: the version has a gap, and
    # the draft is still directly on the recorded v1.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    v2 = _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    assert c.post(f"/zt/assessments/{v2}/discard", headers=_h(bearer, cid)).status_code == 200
    v3 = _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    assert _publish(c, bearer, cid).json()["error"]["message"] == _DISCARD
    assert c.post(f"/zt/assessments/{v3}/discard", headers=_h(bearer, cid)).status_code == 200
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


def test_following_release_then_generate_publishes(app_client) -> None:  # noqa: F811
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=True)
    assert "waiting to be released" in _publish(c, bearer, cid).json()["error"]["message"]
    release(c, bearer, cid, "zt", s.zt_service)
    _gen(c, provider, bearer, cid)
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


def test_csf_after_a_playbook_seed_is_not_told_to_discard(app_client) -> None:  # noqa: F811
    # CSF v1 released with no Playbook rows, generate, then the one writer an
    # approved record keeps (the seed) moves its fingerprint, then a revision
    # draft. Discarding the draft would leave v1 `changed` (the fingerprint), so
    # the discard sentence is not offered; release-then-generate publishes.
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    h = _h(bearer, cid)
    sid = c.post("/csf/services", headers=h, json={"kind": "nist_csf", "title": "CSF"}).json()["id"]
    a = c.post(f"/csf/services/{sid}/assessments", headers=h).json()
    assert c.post(f"/csf/assessments/{a['id']}/approve", headers=h).status_code == 200
    release(c, bearer, cid, "csf", sid)
    _gen(c, provider, bearer, cid)
    seeded = c.post(f"/csf/services/{sid}/profiles/seed", headers=h, json={"tiers": ["low"]})
    assert seeded.status_code == 200, seeded.text
    rev = c.post(
        f"/csf/services/{sid}/assessments/{a['id']}/revisions",
        headers=h,
        json={"reason": "Client asked for a correction."},
    )
    assert rev.status_code == 201, rev.text
    p = _publish(c, bearer, cid)
    assert _blockers(p) == [{"input": "csf", "reason": "changed", "status": "draft"}]
    assert p.json()["error"]["message"] == (
        "This register can't be published while a newer version of an assessment it "
        "draws on is waiting to be released: NIST CSF (in progress (draft)). Release "
        "that version, then generate a new version before publishing."
    )
    assert c.post(f"/csf/assessments/{rev.json()['id']}/approve", headers=h).status_code == 200
    release(c, bearer, cid, "csf", sid)
    _gen(c, provider, bearer, cid)
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


def test_following_discard_publishes_for_tech_debt(app_client) -> None:  # noqa: F811
    import uuid

    from app.models.capability import CapabilityList, CapabilityListStatus
    from tests.unit.test_risk_register import _session

    c, provider = app_client
    bearer, cid = _admin(c)
    seed_released(c, bearer, cid)
    h = _h(bearer, cid)
    td = c.post("/tech-debt/services", headers=h, json={"kind": "tech_debt", "title": "TD"})
    assert td.status_code in (200, 201), td.text
    service_id = uuid.UUID(td.json()["id"])
    with _session() as db:
        db.add(
            CapabilityList(service_id=service_id, version=1, status=CapabilityListStatus.RELEASED)
        )
        db.commit()
    _gen(c, provider, bearer, cid)
    with _session() as db:
        draft = CapabilityList(service_id=service_id, version=2, status=CapabilityListStatus.DRAFT)
        db.add(draft)
        db.commit()
        draft_id = str(draft.id)
    p = _publish(c, bearer, cid)
    assert _blockers(p) == [{"input": "tech_debt", "reason": "changed", "status": "draft"}]
    assert p.json()["error"]["message"] == _DISCARD
    d = c.post(f"/tech-debt/capability-lists/{draft_id}/discard", headers=h)
    assert d.status_code == 200, d.text
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


def _attack_revision(c, bearer, cid, s) -> str:
    r = c.post(
        f"/attack/services/{s.attack_service}/assessments/{s.attack_assessment}/revisions",
        headers=_h(bearer, cid),
        json={"reason": "Client asked for a correction."},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_following_discard_of_two_drafts_in_two_services_publishes(
    app_client,  # noqa: F811
) -> None:
    # Both ATT&CK and ZT have a draft directly over the released record the
    # register drew on. Discarding BOTH publishes, so the discard sentence is
    # kept; the counterfactual must remove every candidate, not only the first.
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    attack_draft = _attack_revision(c, bearer, cid, s)
    zt_draft = _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    p = _publish(c, bearer, cid)
    assert {b["input"] for b in _blockers(p)} == {"attack", "zt"}
    assert p.json()["error"]["message"] == _DISCARD
    h = _h(bearer, cid)
    assert c.post(f"/attack/assessments/{attack_draft}/discard", headers=h).status_code == 200
    assert _publish(c, bearer, cid).status_code == 409  # one draft left: still refused
    assert c.post(f"/zt/assessments/{zt_draft}/discard", headers=h).status_code == 200
    ok = _publish(c, bearer, cid)
    assert ok.status_code == 200, ok.text


class _Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def info(self, event: str, **kw) -> None:
        self.events.append((event, kw))

    def __getattr__(self, _name):
        return self.info


def test_one_refusal_logs_the_real_blockers_once_and_the_discard_decision(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    # ATT&CK draft over released, ZT only approved at generate: the counterfactual
    # pass must not log its imagined blockers as a refusal, and the kept-or-demoted
    # decision is logged once.
    import app.risk.inputs as inputs

    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)  # ZT stays approved
    _gen(c, provider, bearer, cid)
    _attack_revision(c, bearer, cid, s)
    recorder = _Recorder()
    monkeypatch.setattr(inputs, "_log", recorder)
    assert _publish(c, bearer, cid).status_code == 409
    blocked = [kw for (e, kw) in recorder.events if e == "risk_publish_inputs_blocked"]
    assert [sorted(k for k, _r in kw["blockers"]) for kw in blocked] == [["attack", "zt"]], blocked
    decisions = [kw for (e, kw) in recorder.events if e == "risk_publish_discard_decision"]
    assert len(decisions) == 1, decisions
    assert (decisions[0]["kept"], decisions[0]["demoted"]) == ([], ["attack"]), decisions


def test_a_kept_discard_is_logged_as_kept_with_the_blocker_logged_once(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    # Everything released, then a ZT revision draft: discarding it makes publish
    # pass the input gate, so the decision line says kept, not demoted.
    import app.risk.inputs as inputs

    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _revise(c, bearer, cid, s.zt_service, s.zt_assessment, approve=False)
    recorder = _Recorder()
    monkeypatch.setattr(inputs, "_log", recorder)
    assert _publish(c, bearer, cid).status_code == 409
    blocked = [kw for (e, kw) in recorder.events if e == "risk_publish_inputs_blocked"]
    assert [sorted(k for k, _r in kw["blockers"]) for kw in blocked] == [["zt"]], blocked
    decisions = [kw for (e, kw) in recorder.events if e == "risk_publish_discard_decision"]
    assert len(decisions) == 1, decisions
    assert (decisions[0]["kept"], decisions[0]["demoted"]) == (["zt"], []), decisions
