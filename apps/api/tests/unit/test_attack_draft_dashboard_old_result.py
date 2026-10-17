"""#1337: the draft dashboard reads a stored run result through
`AttackRunAiResponse`, whose `omitted_count` defaults to 0. A run stored before
#853 never measured it, so its draft said "nothing omitted", a value the run
did not report. Missing data is UNCONFIRMED, not zero (CLAUDE.md): the draft
carries None for that run, and a number for a run that did measure it.

The old result is the stored shape of a run before #853: the key is not there.
The test builds it by removing the key from a real run's stored result, which
is the world, not the step under test (the step is the draft's read).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.ai_run import AiRun
from tests.unit.test_attack_draft_dashboard import _answer_only, _draft, _run, _setup
from tests.unit.test_attack_run_ai import app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def _drop_stored_key(sessions, key: str) -> None:
    with sessions() as db:
        run = db.execute(select(AiRun)).scalars().one()
        assert key in run.result, "setup: a new run stores the key"
        run.result = {k: v for k, v in run.result.items() if k != key}
        db.commit()


def test_a_run_stored_without_omitted_count_reports_it_as_not_measured(
    app_client,  # noqa: F811
) -> None:
    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    _run(c, h, svc_id)
    _drop_stored_key(app_client[1], "omitted_count")
    body = _draft(c, h, svc_id).json()
    # Positive first: the draft was built from that run.
    assert body["batches_failed"] == 0 and body["service_id"] == svc_id
    assert body["omitted_count"] is None, body["omitted_count"]


def test_a_run_that_measured_omitted_count_still_reports_the_number(
    app_client,  # noqa: F811
) -> None:
    c, provider, h, svc_id, rows = _setup(app_client)
    _answer_only(provider, {rows[0]["technique_code"]: "gap"})
    _run(c, h, svc_id)
    body = _draft(c, h, svc_id).json()
    # The provider answered one technique and left the rest out through the
    # re-ask as well: a measured, non-None count that is not zero.
    assert isinstance(body["omitted_count"], int) and body["omitted_count"] > 0, body[
        "omitted_count"
    ]
