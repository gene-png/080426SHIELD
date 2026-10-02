"""The engagement target a client CHOSE at intake: the ONE reader (#352).

The CSF target tier and the ZT target stage live on the service's source
request (`ServiceRequest.csf_target_tier` / `.zt_target_stage`). Every surface
that needs "the target this client chose" calls one of the two functions here:

    routes/csf.py      the admin workspace and finalize (the freeze)
    routes/zt.py       the admin workspace and finalize (the freeze)
    routes/clients.py  the client dashboards and the home value card
    routes/risk.py     the Risk Register's gather

There used to be four copies of this query, two of them "deliberately
duplicated" in `routes/clients.py` so one router would not import another's
private helper. A non-router module removes both the duplication and the
reason for it. Four copies agree only until somebody edits one of them, and
#84 is titled for four sites disagreeing about one client's target.

These return the RAW choice, or None when there is none. Resolving it --
default, out of range, below the floor -- is `csf/gap.py::resolve_target_tier`
and `zt/scoring.py::resolve_target_stage`, which each caller runs itself.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models.service import Service
from app.models.service_request import ServiceRequest


def _source_request(db: Session, service_id: uuid.UUID) -> ServiceRequest | None:
    """The intake request a service was provisioned from, or None.

    The single read both functions below go through, so a test can prove that
    every surface reads the target here and nowhere else.
    """
    svc = db.get(Service, service_id)
    if svc is None or svc.source_request_id is None:
        return None
    return db.get(ServiceRequest, svc.source_request_id)


def client_target_tier(db: Session, service_id: uuid.UUID) -> int | None:
    """The CSF target tier the client chose at intake, raw, or None."""
    sr = _source_request(db, service_id)
    return sr.csf_target_tier if sr is not None else None


def client_target_stage(db: Session, service_id: uuid.UUID) -> int | None:
    """The ZT target stage the client chose at intake, raw, or None."""
    sr = _source_request(db, service_id)
    return sr.zt_target_stage if sr is not None else None
