"""The admin Overlap card never calls a partial figure a TOTAL (#781).

`OverlapDashboard.tsx` printed "Total annual cost" whatever the list could
honestly claim, while the deliverable built from the same list says "Annual
cost (may not be complete)" or "Included annual cost" (`tech_debt/exporters.py`
`cost_label`, UX finding #4, #177/#193). The overlap route now sends the
deliverable's own label, so the screen and the document cannot disagree.

One world per state, through the route. Expected labels are the deliverable's
strings, written out here rather than imported from the module under test.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind
from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    env,
)

pytestmark = pytest.mark.unit

TOTAL = "Total annual cost"
INCLUDED = "Included annual cost"
MAY_NOT = "Annual cost (may not be complete)"


def _label(
    env,  # noqa: F811
    *,
    source_rows_total: int | None,
    attribution_complete: bool | None,
    costs: list[float | None],
) -> str:
    c, Sess = env
    admin = _register(c, "admin@example.com")
    bearer = admin["tokens"]["access_token"]
    client_id = c.headers["X-Client-Id"]
    with Sess() as s:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            title="Tech Debt",
            client_id=uuid.UUID(client_id),
            opened_by=uuid.UUID(admin["user"]["id"]),
        )
        s.add(svc)
        s.flush()
        cl = CapabilityList(
            service_id=svc.id,
            version=1,
            status=CapabilityListStatus.DRAFT,
            source_rows_total=source_rows_total,
            attribution_complete=attribution_complete,
        )
        s.add(cl)
        s.flush()
        for i, cost in enumerate(costs):
            s.add(CapabilityItem(capability_list_id=cl.id, name=f"Tool {i}", annual_cost_usd=cost))
        s.commit()
        svc_id = svc.id
    r = c.get(f"/tech-debt/services/{svc_id}/overlap-analysis", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    return r.json()["total_cost_label"]


def test_every_row_accounted_for_and_costed_is_a_total(env) -> None:  # noqa: F811
    assert _label(env, source_rows_total=2, attribution_complete=True, costs=[10, 20]) == TOTAL


def test_rows_excluded_is_the_included_cost(env) -> None:  # noqa: F811
    # 3 rows received, 2 included, attribution complete: 1 row excluded.
    assert _label(env, source_rows_total=3, attribution_complete=True, costs=[10, 20]) == INCLUDED


def test_an_unknown_exclusion_count_may_not_be_complete(env) -> None:  # noqa: F811
    # #193: attribution failed, so "Total" and "Included" are both unclaimable.
    assert _label(env, source_rows_total=2, attribution_complete=False, costs=[10, 20]) == MAY_NOT


def test_no_reconciliation_on_record_may_not_be_complete(env) -> None:  # noqa: F811
    assert _label(env, source_rows_total=None, attribution_complete=None, costs=[10, 20]) == MAY_NOT


def test_an_uncosted_item_may_not_be_complete(env) -> None:  # noqa: F811
    assert _label(env, source_rows_total=2, attribution_complete=True, costs=[10, None]) == MAY_NOT
