"""#588: the client engagement list says when an ATT&CK report is withheld.

Since #556 a report released over an assessment scored against another catalog
is withheld from the client: its dashboard refuses, its files are withheld, and
the home page says "Report withheld". The Assessments page reads this list,
which carried only the lifecycle status, so it still called the report
released. The entry now carries `withheld`, by the rule the home page applies
to the deliverables list: a service whose released reports are ALL withheld.
"""

from __future__ import annotations

import pytest

from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    _service_and_assessment,
    _set_version,
    env,
)

pytestmark = pytest.mark.unit


def _release(c, bearer: str, svc: str, assessment_id: str) -> None:
    ok = c.post(f"/attack/assessments/{assessment_id}/approve", headers=_auth(bearer))
    assert ok.status_code == 200, ok.text
    deliv = c.post(f"/attack/services/{svc}/deliverables/finalize", headers=_auth(bearer))
    assert deliv.status_code in (200, 201), deliv.text
    rel = c.post(f"/attack/deliverables/{deliv.json()['id']}/release", headers=_auth(bearer))
    assert rel.status_code == 200, rel.text


def _entry(c, client: dict, svc: str) -> dict:
    c.headers["X-Client-Id"] = client["user"]["client_id"]
    r = c.get("/intake/engagements", headers=_auth(client["tokens"]["access_token"]))
    assert r.status_code == 200, r.text
    (entry,) = [e for e in r.json() if e["service_id"] == svc]
    return entry


def test_a_withheld_attack_report_is_withheld_on_the_engagement_list(env) -> None:  # noqa: F811
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _release(c, bearer, svc, a["id"])

    readable = _entry(c, client, svc)
    assert readable["withheld"] is False

    # The catalog it was scored against is no longer known: #556's stale case,
    # the one the deliverables list, the dashboard and downloads withhold.
    _set_version(Sess, a["id"], None)
    withheld = _entry(c, client, svc)
    assert withheld["withheld"] is True
    # Only readability moved; the lifecycle fields read as before.
    assert withheld["status"] == readable["status"]
    deliverables = c.get(
        f"/clients/{client['user']['client_id']}/deliverables",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()["items"]
    assert [d["withheld"] for d in deliverables if d["service_id"] == svc] == [True]


def _deliverables_list_says_withheld(c, client: dict, svc: str) -> bool:
    """The home page's derivation (`HomeDashboard.tsx`, `withheldServiceIds`),
    from the deliverables list: released reports exist, and none is readable."""
    items = c.get(
        f"/clients/{client['user']['client_id']}/deliverables",
        headers=_auth(client["tokens"]["access_token"]),
    ).json()["items"]
    mine = [d["withheld"] for d in items if d["service_id"] == svc]
    return bool(mine) and all(mine)


def test_the_engagement_entry_agrees_with_the_deliverables_list(env) -> None:  # noqa: F811
    """Two derivations of one fact: the engagement entry's `withheld` and the
    home page's, from the deliverables list. Asserted equal in both states so
    the two cannot drift apart silently."""
    c, Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    bearer = admin["tokens"]["access_token"]
    svc, a = _service_and_assessment(c, bearer)
    _release(c, bearer, svc, a["id"])

    readable = _entry(c, client, svc)["withheld"]
    assert readable is _deliverables_list_says_withheld(c, client, svc) is False

    _set_version(Sess, a["id"], None)
    withheld = _entry(c, client, svc)["withheld"]
    assert withheld is _deliverables_list_says_withheld(c, client, svc) is True


def test_an_unreleased_service_is_not_withheld(env) -> None:  # noqa: F811
    c, _Sess = env
    admin = _register(c, "admin@example.com")
    client = _register(c, "client@example.com")
    svc, _a = _service_and_assessment(c, admin["tokens"]["access_token"])
    assert _entry(c, client, svc)["withheld"] is False
