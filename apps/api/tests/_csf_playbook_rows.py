"""Score CSF Working Profile (Playbook) rows through the API, for Risk tests.

Since #474 D' (Gene, #736 5984218862) a Risk CSF finding is the Playbook
Enterprise level below the Playbook `target_level`, so a test that needs one
scores a Working Profile row, never a questionnaire `maturity_tier`.

The dimension scores for each level come from the spec's table (CSF_Flow_Spec
section 8: a total of 0-2 is Level 1, 3-5 Level 2, 6-7 Level 3, 8-9 Level 4, 10
Level 5), written out here and never imported from `app.csf.playbook`. Every
row is written with evidence, so the evidence cap changes nothing, and on the
`high` tier only, so the Enterprise level is that one tier's level.
"""

from __future__ import annotations

#: (governance, policy, implementation, monitoring, improvement) per level.
DIMS_FOR_LEVEL = {
    1: (0, 0, 0, 0, 0),
    2: (2, 1, 0, 0, 0),
    3: (2, 2, 2, 0, 0),
    4: (2, 2, 2, 2, 0),
    5: (2, 2, 2, 2, 2),
}


def score_csf_playbook(c, h: dict, svc_id: str, levels: dict[str, tuple[int, int | None]]) -> None:
    """Seed the service's `high` profile, then write `code -> (level, target)`
    for each named subcategory. The assessment must still be a draft; the
    caller approves it."""
    seeded = c.post(f"/csf/services/{svc_id}/profiles/seed", headers=h, json={"tiers": ["high"]})
    assert seeded.status_code in (200, 201), seeded.text
    rows = c.get(f"/csf/services/{svc_id}/profile/high", headers=h).json()["rows"]
    by_code = {r["subcategory_code"]: r["id"] for r in rows}
    for code, (level, target) in levels.items():
        g, p, i, m, imp = DIMS_FOR_LEVEL[level]
        body = {
            "governance": g,
            "policy": p,
            "implementation": i,
            "monitoring": m,
            "improvement": imp,
            "has_evidence": True,
            "in_scope": True,
            "target_level": target,
        }
        r = c.patch(f"/csf/dimension-scores/{by_code[code]}", headers=h, json=body)
        assert r.status_code == 200, r.text
