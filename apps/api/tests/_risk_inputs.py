"""Seed a Risk Register's inputs through the real routes, released or not (#737).

Publication needs every engaged input RELEASED, which in this repo is a
deliverable finalize then release, flipping the parent to RELEASED (W4). These
helpers drive exactly those endpoints, so a test's "released" is the product's.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests._attack_rows import first_standalone


@dataclass
class Seeded:
    attack_service: str
    attack_assessment: str
    technique: str
    zt_service: str
    zt_assessment: str
    capability: str


def _h(bearer: str, cid: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}


def seed_attack_and_zt(c, bearer: str, cid: str) -> Seeded:
    """An ATT&CK gap and a low ZT answer, both APPROVED (not released)."""
    h = _h(bearer, cid)
    asvc = c.post("/attack/services", headers=h, json={"kind": "attack_coverage", "title": "A"})
    assert asvc.status_code in (200, 201), asvc.text
    a = c.post(f"/attack/services/{asvc.json()['id']}/assessments", headers=h).json()
    cov = first_standalone(a["coverage"])
    r = c.patch(f"/attack/coverage/{cov['id']}", headers=h, json={"status": "gap"})
    assert r.status_code == 200, r.text
    zsvc = c.post("/zt/services", headers=h, json={"kind": "zero_trust_cisa", "title": "ZT"})
    assert zsvc.status_code in (200, 201), zsvc.text
    za = c.post(f"/zt/services/{zsvc.json()['id']}/assessments", headers=h).json()
    zans = za["answers"][0]
    r = c.patch(f"/zt/answers/{zans['id']}", headers=h, json={"maturity_stage": 1})
    assert r.status_code == 200, r.text
    assert c.post(f"/attack/assessments/{a['id']}/approve", headers=h).status_code == 200
    assert c.post(f"/zt/assessments/{za['id']}/approve", headers=h).status_code == 200
    return Seeded(
        asvc.json()["id"],
        a["id"],
        cov["technique_code"],
        zsvc.json()["id"],
        za["id"],
        zans["capability_code"],
    )


def release(c, bearer: str, cid: str, prefix: str, service_id: str) -> None:
    """Finalize then release `service_id`'s deliverable (prefix: attack | zt)."""
    h = _h(bearer, cid)
    fin = c.post(f"/{prefix}/services/{service_id}/deliverables/finalize", headers=h)
    assert fin.status_code in (200, 201), fin.text
    rel = c.post(f"/{prefix}/deliverables/{fin.json()['id']}/release", headers=h)
    assert rel.status_code == 200, rel.text


def seed_released(c, bearer: str, cid: str) -> Seeded:
    s = seed_attack_and_zt(c, bearer, cid)
    release(c, bearer, cid, "attack", s.attack_service)
    release(c, bearer, cid, "zt", s.zt_service)
    return s
