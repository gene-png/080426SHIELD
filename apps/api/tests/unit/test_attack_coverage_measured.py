"""#489: "never assessed" and "nothing covered" are different facts.

`analytics._pct` answers 0.0 where nothing is addressable, the same figure an
all-gap tactic earns. The deliverable already says "not measured" there, by
the exporter's `_measured`. The API now emits that same decision as
`coverage_measured`, so a screen never has to work it out for itself.

The expected values come from #489's definition, restated: a tactic (or the
whole assessment) is measured when anything in it is Covered, Partial, Gap or
pending review.
"""

from __future__ import annotations

import pytest

from tests._attack_rows import first_standalone
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    env,
)

pytestmark = pytest.mark.unit


def _by_definition(t: dict) -> bool:
    return t["covered"] + t["partial"] + t["gap"] + t["pending_review"] > 0


def test_the_admin_heatmap_says_which_tactics_were_measured(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)

    blank = c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).json()
    assert blank["coverage_measured"] is False
    assert {t["coverage_measured"] for t in blank["by_tactic"]} == {False}

    # One technique judged a Gap: its tactic reads 0.0%, measured; every other
    # tactic reads 0.0%, NOT measured. The same figure, two facts.
    cov = first_standalone(a["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=_auth(bearer), json={"status": "gap"})
    assert r.status_code == 200, r.text
    heat = c.get(f"/attack/services/{svc}/heatmap", headers=_auth(bearer)).json()

    assert heat["coverage_measured"] is True
    assert heat["coverage_pct"] == 0.0
    for t in heat["by_tactic"]:
        assert t["coverage_measured"] is _by_definition(t), t
    zeros = {t["coverage_measured"] for t in heat["by_tactic"] if t["coverage_pct"] == 0.0}
    assert zeros == {True, False}, "an all-gap tactic and an unassessed one, both at 0.0%"


def test_the_client_dashboard_says_which_tactics_were_measured(env) -> None:  # noqa: F811
    c, _Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    cov = first_standalone(a["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=_auth(bearer), json={"status": "gap"})
    assert r.status_code == 200, r.text
    assert (
        c.post(f"/attack/assessments/{a['id']}/approve", headers=_auth(bearer)).status_code == 200
    )
    deliv = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert deliv.status_code in (200, 201), deliv.text
    rel = c.post(f"/attack/deliverables/{deliv.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text

    client_id = client["user"]["client_id"]
    c.headers["X-Client-Id"] = client_id
    dash = c.get(
        f"/clients/{client_id}/attack/{svc}/dashboard",
        headers=_auth(client["tokens"]["access_token"]),
    )
    assert dash.status_code == 200, dash.text
    rollup = dash.json()["rollup"]
    assert rollup["coverage_measured"] is True
    for t in rollup["by_tactic"]:
        assert t["coverage_measured"] is _by_definition(t), t
    zeros = {t["coverage_measured"] for t in rollup["by_tactic"] if t["coverage_pct"] == 0.0}
    assert zeros == {True, False}
