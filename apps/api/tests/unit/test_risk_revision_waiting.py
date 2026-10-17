"""#1156, review round 2 F1: a register generated from released inputs, after
which one input's newer version reaches SUBMITTED or APPROVED but not released.

Publish refuses the register as `changed` (it drew on v1, the current record
is v2). "Generate a new version before publishing" alone names a remedy that
cannot publish: the new register would draw on the unreleased v2 and be
refused as not released. Discard is not offered either: an approved or
submitted version cannot be discarded. So the sentence names the input and
its state, and says to release that version first.

The copy is the advisor's, approved verbatim (#736 6228351462 item 4). Every
expected value is typed from the scenario,
never read from the code.
"""

from __future__ import annotations

import pytest

from app.risk.inputs import REGENERATE, RELEASE_NEWER, Blocker
from app.routes.risk import _inputs_not_final_message
from tests._risk_inputs import seed_released
from tests.unit.test_risk_publish_inputs import _blockers, _gen, _publish
from tests.unit.test_risk_register import _admin, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _approve_a_zt_revision(c, bearer: str, cid: str, zt_service: str, zt_assessment: str) -> None:
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    r = c.post(
        f"/zt/services/{zt_service}/assessments/{zt_assessment}/revisions",
        headers=h,
        json={"reason": "Client asked for a correction."},
    )
    assert r.status_code == 201, r.text
    v2 = r.json()
    assert v2["status"] == "draft", v2["status"]
    ok = c.post(f"/zt/assessments/{v2['id']}/approve", headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved", ok.json()["status"]


def test_an_approved_newer_version_names_the_input_and_says_release_it(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    bearer, cid = _admin(c)
    s = seed_released(c, bearer, cid)
    _gen(c, provider, bearer, cid)
    _approve_a_zt_revision(c, bearer, cid, s.zt_service, s.zt_assessment)
    r = _publish(c, bearer, cid)
    assert _blockers(r) == [{"input": "zt", "reason": "changed", "status": "approved"}]
    message = r.json()["error"]["message"]
    assert message == (
        "This register can't be published while a newer version of an assessment it "
        "draws on is waiting to be released: Zero Trust (approved, not yet released). "
        "Release that version, then generate a new version before publishing."
    ), message
    assert "has changed since it was generated" not in message, message


# The SUBMITTED state is reached through the client's self-assessment submit,
# which this harness does not drive; the sentence is pinned at the function,
# and the route test above pins that the function is what publish uses.
def test_a_submitted_newer_version_reads_the_same_with_its_state() -> None:
    message = _inputs_not_final_message([Blocker("csf", "changed", "submitted", RELEASE_NEWER)])
    assert message == (
        "This register can't be published while a newer version of an assessment it "
        "draws on is waiting to be released: NIST CSF (submitted, not yet released). "
        "Release that version, then generate a new version before publishing."
    ), message


def test_two_waiting_versions_are_both_named() -> None:
    message = _inputs_not_final_message(
        [
            Blocker("csf", "changed", "submitted", RELEASE_NEWER),
            Blocker("zt", "changed", "approved", RELEASE_NEWER),
        ]
    )
    assert message == (
        "This register can't be published while newer versions of assessments it "
        "draws on are waiting to be released: NIST CSF (submitted, not yet released); "
        "Zero Trust (approved, not yet released). Release those versions, then "
        "generate a new version before publishing."
    ), message


def test_a_released_or_archived_change_keeps_the_generate_sentence() -> None:
    message = _inputs_not_final_message(
        [Blocker("attack", "changed", "released", REGENERATE), Blocker("zt", "changed", None)]
    )
    assert message == (
        "An assessment this register draws on has changed since it was generated: "
        "ATT&CK coverage; Zero Trust. Generate a new version before publishing."
    ), message
