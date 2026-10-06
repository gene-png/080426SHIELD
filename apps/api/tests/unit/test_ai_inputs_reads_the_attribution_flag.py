"""#177 through ATT&CK's AI-inputs endpoint: `_excluded_attribution` reads the
persisted `attribution_complete`, so a clean extraction that excluded nothing
reports `complete` with a true zero -- the case the empty list could never
answer. NULL (a list written before 0058) keeps the reading it had: a named
drop proves completeness, an empty list proves nothing. The NULL half is
pinned, unchanged, by `test_attack_ai_inputs.py`.
"""

from __future__ import annotations

import uuid as _uuid

import pytest

from app.models.capability import CapabilityItem, CapabilityList, CapabilityListStatus
from app.models.service import Service, ServiceKind, ServiceStatus
from tests.unit.test_attack_ai_inputs import (  # noqa: F401  (fixture)
    _admin,
    _attack_service,
    app_client,
)

pytestmark = pytest.mark.unit


def _list(Sess, cid: str, user_id: str, *, flag: bool | None, excluded_rows: list) -> None:
    with Sess() as db:
        svc = Service(
            kind=ServiceKind.TECH_DEBT,
            status=ServiceStatus.IN_PROGRESS,
            title="Acme Tech Debt",
            client_id=_uuid.UUID(cid),
            opened_by=_uuid.UUID(user_id),
        )
        db.add(svc)
        db.flush()
        cl = CapabilityList(
            service_id=svc.id,
            version=1,
            status=CapabilityListStatus.APPROVED,
            source_rows_total=5,
            excluded_rows=excluded_rows,
            attribution_complete=flag,
        )
        db.add(cl)
        db.flush()
        db.add(
            CapabilityItem(
                capability_list_id=cl.id,
                name="Splunk",
                security_related=None,
                security_class_confirmed=False,
            )
        )
        db.commit()


@pytest.mark.parametrize(
    ("flag", "excluded_rows", "expected"),
    [
        # A clean run: attribution complete and nothing named because nothing
        # was excluded. Before 0058 this read `unknown`.
        (True, [], "complete"),
        (True, [{"index": 3, "summary": "row 3"}], "complete"),
        # Attribution failed: the rows cannot be named or counted.
        (False, [], "unknown"),
    ],
)
def test_the_reader_takes_the_recorded_flag(
    app_client, flag, excluded_rows, expected  # noqa: F811
) -> None:
    c, Sess = app_client
    bearer, cid = _admin(c)
    me = c.get("/auth/me", headers={"Authorization": f"Bearer {bearer}"}).json()
    _list(Sess, cid, me["id"], flag=flag, excluded_rows=excluded_rows)
    sid = _attack_service(c, bearer, cid)
    r = c.get(
        f"/attack/services/{sid}/ai-inputs",
        headers={"Authorization": f"Bearer {bearer}", "X-Client-Id": cid},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sources"][0]["excluded_attribution"] == expected
    assert body["totals"]["lists_with_unknown_exclusions"] == (1 if expected == "unknown" else 0)
