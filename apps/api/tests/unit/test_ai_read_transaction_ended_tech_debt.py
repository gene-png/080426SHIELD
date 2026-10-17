"""#1025 holder 2, the Tech Debt extraction: no pooled connection is held
while the provider is called (see `test_ai_read_transaction_ended.py`); 1
with `end_read_transaction(db, where="tech_debt.extract")` removed."""

from __future__ import annotations

import pytest

from tests._ai_runs import tech_debt_extract
from tests._pool_count import sampling_provider_calls
from tests.unit.test_ai_runs_tech_debt import world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_the_extraction_holds_no_connection_during_its_call(
    world,  # noqa: F811
    monkeypatch,
) -> None:
    doc = world.upload()
    with sampling_provider_calls(monkeypatch) as samples:
        tech_debt_extract(world.c, world.svc_id, world.h, doc)
    assert samples and set(samples) == {0}, samples
