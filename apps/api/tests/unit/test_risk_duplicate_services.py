"""#896: the Risk gate names the services behind a duplicate refusal, and the
Risk Register's own archive route clears it.

Since #876 (PR #891), two engaged services of one kind and framework make
Generate refuse with `risk_register_duplicate_inputs`. The only remedy is to
archive one, and #896 puts that control on the duplicate banner (advisor's
rulings on track6's plan, #736 6042801745). The banner needs each service's id
and title to offer one button per service, so the gate gains an additive
`duplicate_services` list, read off the same groups the sentence is built from.

Review round 1 (advisor, #736 6046491381):
- B1: two services can carry the SAME title, so each row also carries what
  tells them apart -- the service's start date and the status and version the
  Inputs panel shows for it.
- B2: the banner archives through a Risk-scoped route that re-checks, in the
  same transaction, that the service is still one of a duplicate group, and
  refuses with a typed 409 otherwise. So two tabs cannot each archive one
  member of a pair and leave the kind unengaged.

Everything goes through the real routes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.models.audit_entry import AuditEntry
from app.models.service import Service
from tests._risk_inputs import release, seed_attack_and_zt
from tests.unit.test_risk_per_service import _generate, _seed_dod
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

# Spelled out from the advisor's approval, not imported: #736 6046491381, with
# its last sentence moved to the screen by 6047873969 (review round 2, F1).
_NOT_IN_GROUP = (
    "{title} is no longer one of several engaged services of the same kind, so it "
    "was not archived."
)


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


def _named(g: dict) -> list[tuple[str, str]]:
    return [(row["service_id"], row["title"]) for row in g["duplicate_services"]]


def _archive(c, bearer: str, cid: str, sid: str):
    return c.post(f"/risk/clients/{cid}/services/{sid}/archive", headers=_h(bearer, cid))


def _service_status(sid: str) -> str:
    with _session() as db:
        svc = db.get(Service, uuid.UUID(sid))
        assert svc is not None
        return str(svc.status.value)


def _archive_audits(sid: str) -> int:
    with _session() as db:
        return (
            db.query(AuditEntry)
            .filter(
                AuditEntry.action == "service.archived",
                AuditEntry.target_id == uuid.UUID(sid),
            )
            .count()
        )


# ---------------------------------------------------------------------------
# The gate's list
# ---------------------------------------------------------------------------


def test_the_gate_names_each_service_in_a_duplicate_pair(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    second = _add_cisa(c, bearer, cid, "ZT 2")
    g = _gate(c, bearer, cid)
    assert g["duplicate_inputs"] is not None, g
    assert _named(g) == [(s.zt_service, "ZT"), (second, "ZT 2")], g


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
    assert _named(_gate(c, bearer, cid)) == [
        (s.attack_service, "A"),
        (a2, "A 2"),
        (s.zt_service, "ZT"),
        (zt2, "ZT 2"),
    ]


def test_equal_titles_are_told_apart_by_start_and_status(app_client) -> None:  # noqa: F811
    """B1: both default title paths build "{org} -- {service type title}", so a
    second service of a kind is titled exactly like the first. Each row then
    carries its start date (the service's created_at) and the status and
    version the Inputs panel shows for that service."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)  # its ZT service is titled "ZT"
    release(c, bearer, cid, "zt", s.zt_service)
    twin = _add_cisa(c, bearer, cid, "ZT")
    # The world, not the outcome: the twin was opened on an earlier day, so a
    # row dated "now" (or from any other timestamp) cannot pass.
    with _session() as db:
        row = db.get(Service, uuid.UUID(twin))
        assert row is not None
        row.created_at = datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
        db.commit()
    g = _gate(c, bearer, cid)
    # Ordered by when each service was opened, so the back-dated twin is first.
    rows = g["duplicate_services"]
    assert [(r["service_id"], r["title"]) for r in rows] == [
        (twin, "ZT"),
        (s.zt_service, "ZT"),
    ], g
    by_id = {r["service_id"]: (r["status"], r["version"]) for r in rows}
    assert by_id == {s.zt_service: ("released", 1), twin: ("draft", 1)}, rows
    # The Inputs panel's own rows for the same two services, read off the same
    # gate response: the duplicate list must say what the panel says.
    panel = [(r["status"], r["version"]) for r in g["inputs"] if r["kind"] == "zt"]
    assert [(r["status"], r["version"]) for r in rows] == panel, g
    with _session() as db:
        created = {
            sid: db.get(Service, uuid.UUID(sid)).created_at  # type: ignore[union-attr]
            for sid in (s.zt_service, twin)
        }
    for r in rows:
        want = created[r["service_id"]]
        want = want if want.tzinfo else want.replace(tzinfo=UTC)
        assert r["started_at"][:10] == want.astimezone(UTC).date().isoformat(), r
    assert rows[0]["started_at"].startswith("2026-10-03T23:30"), rows[0]


# ---------------------------------------------------------------------------
# B2: the Risk-scoped archive route
# ---------------------------------------------------------------------------


def test_archiving_one_of_the_pair_clears_the_refusal(app_client) -> None:  # noqa: F811
    """The remedy the screen offers, through the route the screen calls:
    archive one service of the pair, and the gate and Generate both clear."""
    c, provider = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    second = _add_cisa(c, bearer, cid, "ZT 2")
    seen: list[dict] = []
    refused = _generate(c, provider, bearer, cid, seen)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["reason"] == "risk_register_duplicate_inputs"

    arch = _archive(c, bearer, cid, second)
    assert arch.status_code == 204, arch.text
    assert _service_status(second) == "archived"
    assert _archive_audits(second) == 1

    g = _gate(c, bearer, cid)
    assert g["duplicate_inputs"] is None and g["duplicate_services"] == [], g
    ok = _generate(c, provider, bearer, cid, seen)
    assert ok.status_code in (200, 201), ok.text


def test_two_tabs_cannot_archive_both_of_a_pair(app_client) -> None:  # noqa: F811
    """B2's case: two tabs show the same banner. Tab one archives A; tab two,
    still showing the old list, archives B. The second is refused, typed, B
    stays engaged, and nothing is written for it."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    b = _add_cisa(c, bearer, cid, "ZT 2")

    first = _archive(c, bearer, cid, s.zt_service)
    assert first.status_code == 204, first.text

    second = _archive(c, bearer, cid, b)
    assert second.status_code == 409, second.text
    err = second.json()["error"]
    assert err["reason"] == "service_not_in_duplicate_group", err
    assert err["message"] == _NOT_IN_GROUP.format(title="ZT 2")

    assert _service_status(b) != "archived"
    assert _archive_audits(b) == 0
    zt_rows = [r for r in _gate(c, bearer, cid)["inputs"] if r["kind"] == "zt"]
    assert [r["engaged"] for r in zt_rows] == [True], zt_rows


def test_a_service_in_no_duplicate_group_is_not_archived(app_client) -> None:  # noqa: F811
    """A lone service of its kind is never a duplicate, so the route refuses."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    r = _archive(c, bearer, cid, s.attack_service)
    assert r.status_code == 409, r.text
    assert r.json()["error"]["reason"] == "service_not_in_duplicate_group"
    assert r.json()["error"]["message"] == _NOT_IN_GROUP.format(title="A")
    assert _service_status(s.attack_service) != "archived"
    assert _archive_audits(s.attack_service) == 0


def test_another_clients_service_is_not_found(app_client) -> None:  # noqa: F811
    """The route is scoped to the client in its path: a service of another
    client is a 404, and is not archived."""
    c, _ = app_client
    bearer, cid = _admin(c)
    seed_attack_and_zt(c, bearer, cid)
    _add_cisa(c, bearer, cid, "ZT 2")
    other = c.post(
        "/admin/clients",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"legal_name": "Other"},
    ).json()["id"]
    s2 = seed_attack_and_zt(c, bearer, other)
    _add_cisa(c, bearer, other, "ZT 2")
    r = _archive(c, bearer, cid, s2.zt_service)
    assert r.status_code == 404, r.text
    assert _service_status(s2.zt_service) != "archived"


def test_a_client_role_user_cannot_archive(app_client) -> None:  # noqa: F811
    """Review round 2, F2: the route is admin-only. A client-role user of the
    same client gets 403, and nothing is archived or audited."""
    c, _ = app_client
    bearer, cid = _admin(c)
    s = seed_attack_and_zt(c, bearer, cid)
    b = _add_cisa(c, bearer, cid, "ZT 2")
    dom = c.post(
        f"/admin/clients/{cid}/domains",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"domain": "acme.example"},
    )
    assert dom.status_code in (200, 201), dom.text
    user = c.post(
        "/auth/register",
        json={
            "email": "user@acme.example",
            "password": "correct horse battery staple!",
            "display_name": "U",
        },
    )
    assert user.status_code in (200, 201), user.text
    assert user.json()["user"]["role"] == "client", user.json()
    cbearer = user.json()["tokens"]["access_token"]

    r = _archive(c, cbearer, cid, b)
    assert r.status_code == 403, r.text
    assert _service_status(b) != "archived"
    assert _archive_audits(b) == 0
    # Still a pair, as the admin sees it: the refusal changed nothing.
    assert [sid for sid, _t in _named(_gate(c, bearer, cid))] == [s.zt_service, b]


def test_an_unknown_service_is_not_found(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    r = _archive(c, bearer, cid, str(uuid.uuid4()))
    assert r.status_code == 404, r.text
