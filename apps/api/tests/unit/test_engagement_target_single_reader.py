"""ONE reader of "the target this client chose at intake" (#352).

There were four copies of one query: `routes/csf.py::_client_target_tier`,
`routes/zt.py::_client_target_stage`, and the "deliberately duplicated"
`routes/clients.py::_csf_client_target_tier` / `_zt_client_target_stage`, with
`routes/risk.py` importing the first two. Four copies agree only until somebody
edits one of them -- #84 is titled for four sites disagreeing about one
client's target. They now all call `app/services/engagement_targets.py`.

Two halves:

* BEHAVIOUR PRESERVATION, through every surface that reads the target, for a
  chosen target (4), none at all, and a below-floor 1 (#85): the admin
  workspace's raw `client_target_*`, finalize's frozen value, the client
  dashboard reading LIVE (nothing frozen), the home value card, and the Risk
  gather (ZT only for Risk since #474 D': its CSF half reads the Playbook's
  per-subcategory targets, so it must NOT read the engagement tier). Expected
  values are written out from the spec, not imported.
* ONE READER: patch the helper's single read and every surface sees the
  patched value. A divergent copy left anywhere reads the database instead,
  and that surface goes red.
"""

from __future__ import annotations

import types
import uuid

import pytest

from tests.unit.test_frozen_engagement_target import (  # noqa: F401  (fixture)
    _csf_dashboard,
    _deliverable_freeze,
    _overwrite_freeze,
    _register,
    _session,
    _set_intake_target,
    _zt_dashboard,
    _zt_finalize_release,
    _zt_score_approve,
    _zt_service,
    app_client,
)

pytestmark = pytest.mark.unit

#: (chosen, resolved target, resolved source, value-card tally) per world.
#: The default is the spec's Tier/Stage 3; #85 reads a stored 1 as below the floor.
WORLDS = [
    pytest.param(4, 4, "client", "neither", id="chosen"),
    pytest.param(None, 3, "default", "defaulted", id="none"),
    pytest.param(1, 3, "client_below_floor", "unusable", id="below-floor"),
]


def _admin_and_client(c):
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    return (
        {"Authorization": f"Bearer {admin['tokens']['access_token']}"},
        {"Authorization": f"Bearer {client['tokens']['access_token']}"},
        client["user"]["client_id"],
    )


def _csf_world(c, chosen: int | None) -> tuple[dict, dict, str, str]:
    ah, ch, client_id = _admin_and_client(c)
    svc_id = c.post("/csf/services", headers=ah, json={"kind": "nist_csf", "title": "CSF"}).json()[
        "id"
    ]
    _set_intake_target(svc_id, csf_tier=chosen)
    a = c.post(f"/csf/services/{svc_id}/assessments", headers=ah).json()
    for ans in a["answers"]:
        c.patch(f"/csf/answers/{ans['id']}", headers=ah, json={"maturity_tier": 2})
    assert c.post(f"/csf/assessments/{a['id']}/approve", headers=ah).status_code == 200
    return ah, ch, client_id, svc_id


def _zt_world(c, chosen: int | None) -> tuple[dict, dict, str, str]:
    ah, ch, client_id = _admin_and_client(c)
    bearer = ah["Authorization"].removeprefix("Bearer ")
    svc_id = _zt_service(c, bearer)
    _set_intake_target(svc_id, zt_stage=chosen)
    _zt_score_approve(c, bearer, svc_id)
    return ah, ch, client_id, svc_id


def _risk_targets(client_id: str) -> dict:
    from app.routes.risk import _gather_findings

    with _session() as db:
        _f, _t, _c, targets, _scopes = _gather_findings(db, uuid.UUID(client_id))
    return targets


def _value_card(c, ch: dict, client_id: str) -> dict:
    r = c.get(f"/clients/{client_id}/value-summary", headers=ch)
    assert r.status_code == 200, r.text
    return r.json()


# --- behaviour preservation -----------------------------------------------------


@pytest.mark.parametrize(("chosen", "target", "source", "tally"), WORLDS)
def test_every_csf_surface_reads_the_same_target(
    app_client, chosen, target, source, tally  # noqa: F811
) -> None:
    c = app_client
    ah, ch, client_id, svc_id = _csf_world(c, chosen)

    # The admin workspace: the RAW choice.
    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=ah).json()
    assert latest["client_target_tier"] == chosen, latest.get("client_target_tier")

    # The Risk gather does NOT read the engagement tier for CSF (#474 D',
    # Gene, #736 5984218862): its CSF findings use the Playbook targets. This
    # world scores the questionnaire and never the Playbook, so the Playbook
    # state is `no_scores` (#736 6087786886, item 4) whatever the tier.
    assert _risk_targets(client_id)["csf"] == {"target": None, "source": "playbook_no_scores"}

    # Finalize freezes the RAW choice.
    deliv = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=ah).json()
    assert _deliverable_freeze(svc_id) == (chosen, "finalize")
    assert c.post(f"/csf/deliverables/{deliv['id']}/release", headers=ah).status_code == 200

    # The client dashboard and the home value card reading LIVE: a deliverable
    # with no freeze on record, as one finalized before migration 0051.
    _overwrite_freeze(svc_id, value=None, source=None)
    c.headers["X-Client-Id"] = client_id
    bearer = ch["Authorization"].removeprefix("Bearer ")
    dash = _csf_dashboard(c, bearer, client_id, svc_id)
    assert dash["target_frozen_at"] is None, dash
    assert (dash["target_tier"], dash["target_tier_source"]) == (target, source)
    card = _value_card(c, ch, client_id)
    assert card["csf_targets_computed_live"] == 1, card
    assert (card["csf_targets_defaulted"], card["csf_targets_unusable"]) == (
        int(tally == "defaulted"),
        int(tally == "unusable"),
    ), card


@pytest.mark.parametrize(("chosen", "target", "source", "tally"), WORLDS)
def test_every_zt_surface_reads_the_same_target(
    app_client, chosen, target, source, tally  # noqa: F811
) -> None:
    c = app_client
    ah, ch, client_id, svc_id = _zt_world(c, chosen)

    latest = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=ah).json()
    assert latest["client_target_stage"] == chosen, latest.get("client_target_stage")

    assert _risk_targets(client_id)["zt"] == {"target": target, "source": source}

    _zt_finalize_release(c, ah["Authorization"].removeprefix("Bearer "), svc_id)
    assert _deliverable_freeze(svc_id) == (chosen, "finalize")

    _overwrite_freeze(svc_id, value=None, source=None)
    c.headers["X-Client-Id"] = client_id
    bearer = ch["Authorization"].removeprefix("Bearer ")
    dash = _zt_dashboard(c, bearer, client_id, svc_id)
    assert dash["target_frozen_at"] is None, dash
    assert (dash["target_stage"], dash["target_stage_source"]) == (target, source)
    card = _value_card(c, ch, client_id)
    assert card["zt_targets_computed_live"] == 1, card
    assert (card["zt_targets_defaulted"], card["zt_targets_unusable"]) == (
        int(tally == "defaulted"),
        int(tally == "unusable"),
    ), card


# --- one reader -------------------------------------------------------------------


def _patch_the_one_read(monkeypatch, *, tier: int, stage: int) -> None:
    """Every caller reaches the source request through this one function."""
    from app.services import engagement_targets

    monkeypatch.setattr(
        engagement_targets,
        "_source_request",
        lambda db, service_id: types.SimpleNamespace(csf_target_tier=tier, zt_target_stage=stage),
    )


def test_every_csf_surface_reads_through_the_one_helper(
    app_client, monkeypatch  # noqa: F811
) -> None:
    """The database says 4; the one read says 2. Every surface must say 2."""
    c = app_client
    ah, ch, client_id, svc_id = _csf_world(c, 4)
    _patch_the_one_read(monkeypatch, tier=2, stage=2)

    latest = c.get(f"/csf/services/{svc_id}/assessments/latest", headers=ah).json()
    assert latest["client_target_tier"] == 2, "workspace"
    assert _risk_targets(client_id)["csf"] == {
        "target": None,
        "source": "playbook_no_scores",
    }, "risk gather: the Playbook, never the engagement tier (#474 D')"
    deliv = c.post(f"/csf/services/{svc_id}/deliverables/finalize", headers=ah).json()
    assert _deliverable_freeze(svc_id) == (2, "finalize"), "finalize"
    assert c.post(f"/csf/deliverables/{deliv['id']}/release", headers=ah).status_code == 200
    _overwrite_freeze(svc_id, value=None, source=None)
    c.headers["X-Client-Id"] = client_id
    dash = _csf_dashboard(c, ch["Authorization"].removeprefix("Bearer "), client_id, svc_id)
    assert dash["target_tier"] == 2, "client dashboard"
    card = _value_card(c, ch, client_id)
    # Tier 2 everywhere: no gap at the patched target 2; at the database's 4,
    # every subcategory would be one.
    assert card["csf_gap_count"] == 0, ("value card", card)


def test_every_zt_surface_reads_through_the_one_helper(
    app_client, monkeypatch  # noqa: F811
) -> None:
    c = app_client
    ah, ch, client_id, svc_id = _zt_world(c, 4)
    _patch_the_one_read(monkeypatch, tier=2, stage=2)

    latest = c.get(f"/zt/services/{svc_id}/assessments/latest", headers=ah).json()
    assert latest["client_target_stage"] == 2, "workspace"
    assert _risk_targets(client_id)["zt"]["target"] == 2, "risk gather"
    _zt_finalize_release(c, ah["Authorization"].removeprefix("Bearer "), svc_id)
    assert _deliverable_freeze(svc_id) == (2, "finalize"), "finalize"
    _overwrite_freeze(svc_id, value=None, source=None)
    c.headers["X-Client-Id"] = client_id
    dash = _zt_dashboard(c, ch["Authorization"].removeprefix("Bearer "), client_id, svc_id)
    assert dash["target_stage"] == 2, "client dashboard"
    card = _value_card(c, ch, client_id)
    assert card["zt_gap_count"] == 0, ("value card", card)
