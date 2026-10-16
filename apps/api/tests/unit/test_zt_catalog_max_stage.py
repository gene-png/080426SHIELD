"""#922: the catalog serves each capability's own maximum stage, so the stage
pickers can offer only what the API accepts.

The value is the one every write path refuses above (`max_stage_for`, #839).
Expected values are the DoD facts the #839 guard tests pin (1.1 User
Inventory has Target activities only; 1.2 Conditional User Access has
Advanced ones), and the count of DoD capabilities with no Advanced activity
measured at main 2f89930b, not read from the module under test.
"""

from __future__ import annotations

import pytest

from tests.unit.test_zt_routes import _register, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _catalog(c, framework: str) -> dict[str, int]:
    admin = _register(c, "admin@example.com")
    r = c.get(
        f"/zt/catalog?framework={framework}",
        headers={"Authorization": f"Bearer {admin['tokens']['access_token']}"},
    )
    assert r.status_code == 200, r.text
    return {cap["code"]: cap["max_stage"] for p in r.json()["pillars"] for cap in p["capabilities"]}


def test_dod_capabilities_carry_their_own_maximum(app_client) -> None:  # noqa: F811
    caps = _catalog(app_client, "dod_ztra")
    assert caps["DOD.USR.01"] == 2  # Target activities only
    assert caps["DOD.USR.02"] == 3  # has Advanced activities
    assert sum(1 for m in caps.values() if m < 3) == 15, caps
    assert set(caps.values()) <= {2, 3}


def test_cisa_capabilities_reach_the_top_of_the_ladder(app_client) -> None:  # noqa: F811
    caps = _catalog(app_client, "cisa_ztmm_2_0")
    assert len(caps) == 37
    assert set(caps.values()) == {4}
