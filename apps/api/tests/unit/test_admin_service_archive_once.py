"""#906 (in #896, advisor #736 6046491381): `DELETE /admin/services/{id}` on a
service that is already ARCHIVED refuses with a typed 409 and writes no audit
row. It used to answer 204 and write a second `service.archived` row, a record
of an action that did not happen.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.audit_entry import AuditEntry
from tests.unit.test_risk_register import (  # noqa: F401  (app_client is a fixture)
    _admin,
    _session,
    app_client,
)

pytestmark = pytest.mark.unit

# Spelled out from the advisor's approval, not imported.
_ALREADY = "This service is already archived. Nothing was changed."


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


def test_archiving_an_archived_service_is_refused_and_not_audited(app_client) -> None:  # noqa: F811
    c, _ = app_client
    bearer, cid = _admin(c)
    auth = {"Authorization": f"Bearer {bearer}"}
    svc = c.post(
        "/csf/services",
        headers={**auth, "X-Client-Id": cid},
        json={"kind": "nist_csf", "title": "x"},
    )
    assert svc.status_code == 201, svc.text
    sid = svc.json()["id"]

    first = c.delete(f"/admin/services/{sid}", headers=auth)
    assert first.status_code == 204, first.text
    assert _archive_audits(sid) == 1

    again = c.delete(f"/admin/services/{sid}", headers=auth)
    assert again.status_code == 409, again.text
    err = again.json()["error"]
    assert err["reason"] == "service_already_archived", err
    assert err["message"] == _ALREADY
    assert _archive_audits(sid) == 1
