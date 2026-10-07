"""#896: the Risk gate names the services behind a duplicate refusal, and
archiving one of them through the admin route clears the refusal.

Since #876 (PR #891), two engaged services of one kind and framework make
Generate refuse with `risk_register_duplicate_inputs`. The only remedy is to
archive one, and #896 puts that control on the duplicate banner (advisor's
rulings on track6's plan, #736 6042801745). The banner needs each service's id
and title to offer one button per service, so the gate gains an additive
`duplicate_services` list, read off the same groups the sentence is built from.

Everything goes through the real routes: services are created through the
service routes, the gate is read through `/risk/clients/{cid}/gate`, and the
archive is `DELETE /admin/services/{id}`, the route the screen's proxy calls.
"""

from __future__ import annotations

import pytest

from tests._risk_inputs import seed_attack_and_zt
from tests.unit.test_risk_per_service import _generate, _seed_dod
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    app_client,
)

pytestmark = pytest.mark.unit


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def _add_cisa(c, bearer: str, cid: str, title: str) -> str:
    h = _h(bearer, cid)
    svc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": title})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/zt/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return svc.json()["id"]


def _add_attack(c, bearer: str, cid: str, title: str) -> str:
    h = _h(bearer, cid)
    svc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": title})
    assert svc.status_code in (200, 201), svc.text
    a = c.post(f"/attack/services/{svc.json()['id']}/assessments", headers=h)
    assert a.status_code in (200, 201), a.text
    return svc.json()["id"]


def _gate(c, bearer: str, cid: str) -> dict:
    r = c.get(f"/risk/clients/{cid}/gate", headers=_h(bearer, cid))
    assert r.status_code == 200, r.text
    return r.json()


def test_the_gate_names_each_service_in_a_duplicate_pair(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    second = _add_cisa(c, bearer, cid, "ZT 2")
    g = _gate(c, bearer, cid)
    assert g["duplicate_inputs"] is not None, g
    assert g["duplicate_services"] == [
        {"service_id": s.zt_service, "title": "ZT"},
        {"service_id": second, "title": "ZT 2"},
    ], g


def test_no_duplicate_names_no_service(app_client) -> None:  # noqa: F811
    """One service per kind and framework -- CISA beside DoD is not a pair."""
    c, _ = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    _seed_dod(c, bearer, cid)
    g = _gate(c, bearer, cid)
    assert g["duplicate_inputs"] is None and g["duplicate_services"] == [], g


def test_only_the_duplicate_group_is_named(app_client) -> None:  # noqa: F811
    """A DoD service beside a CISA pair is not part of the refusal, so it gets
    no archive button."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    dod, _code = _seed_dod(c, bearer, cid)
    second = _add_cisa(c, bearer, cid, "ZT 2")
    ids = [row["service_id"] for row in _gate(c, bearer, cid)["duplicate_services"]]
    assert ids == [s.zt_service, second]
    assert dod not in ids


def test_two_duplicate_groups_name_all_four_services(app_client) -> None:  # noqa: F811
    """In the order the sentences name them: one group, then the next."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    zt2 = _add_cisa(c, bearer, cid, "ZT 2")
    a2 = _add_attack(c, bearer, cid, "A 2")
    g = _gate(c, bearer, cid)
    assert g["duplicate_services"] == [
        {"service_id": s.attack_service, "title": "A"},
        {"service_id": a2, "title": "A 2"},
        {"service_id": s.zt_service, "title": "ZT"},
        {"service_id": zt2, "title": "ZT 2"},
    ], g


def test_archiving_one_of_the_pair_clears_the_refusal(app_client) -> None:  # noqa: F811
    """The remedy the screen offers, through the route the screen's proxy calls:
    archive one service of the pair, and the gate and Generate both clear."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    second = _add_cisa(c, bearer, cid, "ZT 2")
    seen: list[dict] = []
    refused = _generate(c, provider, bearer, cid, seen)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["reason"] == "risk_register_duplicate_inputs"

    arch = c.delete(f"/admin/services/{second}", headers={"Authorization": f"Bearer {bearer}"})
    assert arch.status_code == 204, arch.text

    g = _gate(c, bearer, cid)
    assert g["duplicate_inputs"] is None and g["duplicate_services"] == [], g
    ok = _generate(c, provider, bearer, cid, seen)
    assert ok.status_code in (200, 201), ok.text
