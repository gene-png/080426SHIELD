"""#1156: which sentence a `changed` input gets, as ONE table (the
specification), after three review rounds each fixing one state of it.

Inputs: the status of the record the register drew on (`was`), the status of
the newest record now (`newest`), and whether that newest record is a DRAFT
sitting directly on the recorded one (`over_was`: discarding it makes the
recorded record the latest again).

Output: the remedy, and whether following the sentence reaches a publishable
register. Publish needs the recorded input RELEASED at generate, and a new
version draws on the newest record and is refused unless that is released.

| was      | newest                  | over_was | following the sentence                  | remedy        |
| released | draft                   | yes      | discard it, publish as is: publishes    | DISCARD_DRAFT |
| released | draft                   | no       | discard leaves another unreleased record| RELEASE_NEWER |
| released | submitted / approved    | any      | release it, generate: publishes         | RELEASE_NEWER |
| released | released / none         | any      | generate: publishes                     | REGENERATE    |
| unreleased | draft/submitted/approved | any    | as is never publishes; generate draws on the unreleased newest: release first | RELEASE_NEWER |
| unreleased | released / none       | any      | generate: publishes                     | REGENERATE    |

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
_UNRELEASED_NEWEST = ("draft", "submitted", "approved")
_RELEASED_OR_NONE_NEWEST = ("released", None)

_ROWS = (
    [("released", "draft", True, DISCARD_DRAFT)]
    + [("released", "draft", False, RELEASE_NEWER)]
    + [("released", n, o, RELEASE_NEWER) for n in ("submitted", "approved") for o in (True, False)]
    + [
        (w, n, o, RELEASE_NEWER)
        for w in ("draft", "submitted", "approved")
        for n in _UNRELEASED_NEWEST
        for o in (True, False)
    ]
    + [(w, n, o, REGENERATE) for w in _WAS for n in _RELEASED_OR_NONE_NEWEST for o in (True, False)]
)


def test_the_table_covers_every_state() -> None:
    keys = {(w, n, o) for (w, n, o, _r) in _ROWS}
    every = {
        (w, n, o)
        for w in _WAS
        for n in (*_UNRELEASED_NEWEST, *_RELEASED_OR_NONE_NEWEST)
        for o in (True, False)
    }
    assert len(_ROWS) == len(keys) == len(every) == 40, (len(_ROWS), len(keys), len(every))
    assert keys == every


@pytest.mark.parametrize(("was", "newest", "over_was", "expected"), _ROWS)
def test_the_remedy_for_every_state(was, newest, over_was, expected) -> None:
    assert (
        changed_remedy(was_status=was, newest_status=newest, drafted_over_was=over_was) == expected
    )


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


@pytest.mark.parametrize(
    "others",
    [
        Blocker("zt", "not_released", "approved"),
        Blocker("zt", "changed", "approved", RELEASE_NEWER),
        Blocker("zt", "changed", "released", REGENERATE),
        Blocker("zt", "not_started", None),
    ],
)
def test_a_discardable_draft_beside_any_other_blocker_is_not_told_to_discard(others) -> None:
    message = _inputs_not_final_message([_DRAFT_OVER_RELEASED, others])
    assert "Discard" not in message, message
    assert "ATT&CK coverage (in progress (draft))" in message, message


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
    message = p.json()["error"]["message"]
    assert "Discard" not in message, message
    assert "ATT&CK coverage (in progress (draft))" in message, message


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
