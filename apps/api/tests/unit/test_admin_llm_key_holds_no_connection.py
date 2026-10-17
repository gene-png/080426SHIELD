"""#1363, a #1025 holder-2 twin outside `invoke`: `POST /admin/llm-key`
validates the pasted key with a real provider call (`live_validate_key`).
The request's read (the admin's own row) ends before it, so the pool holds no
connection while the provider answers; 1 with the route's
`end_read_transaction(db, where="admin.set_llm_key")` removed."""

from __future__ import annotations

import pytest

from tests._pool_count import pool_count
from tests.unit.test_admin_llm_key import GOOD_KEY, _admin, app_client  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit


def test_validating_a_key_holds_no_connection_while_the_provider_answers(
    app_client,  # noqa: F811
) -> None:
    from app.ai.keystore import get_key_validator

    c, _ = app_client
    h = _admin(c)
    held: list[int] = []
    with pool_count() as live:

        def sampling_validator():
            def _validate(provider: str, model: str, api_key: str) -> tuple[bool, str]:
                held.append(live[0])
                return True, f"Validated against {provider}/{model}."

            return _validate

        c.app.dependency_overrides[get_key_validator] = sampling_validator
        r = c.post("/admin/llm-key", headers=h, json={"api_key": GOOD_KEY})
    assert r.status_code == 200, r.text
    assert held == [0], held
