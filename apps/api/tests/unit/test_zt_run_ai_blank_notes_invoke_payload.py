"""#1084, closing evidence: the payload handed to `LLMClient.invoke` for a ZT
Run AI leaves out a capability with blank notes.

`test_zt_run_ai_blank_notes_not_sent.py` records the payload at the PROVIDER
(what egresses). This pins the earlier hand-off, the `payload` argument of
`LLMClient.invoke` itself, so a change that filters later (or only in the
provider shim) still fails here. It asserts on the payload, never on the
response: fixture mode echoes the keys it is given, so a response check proves
nothing. No live call is made; no live measurement was run.

Expected codes come from which rows the test gave notes.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.llm import LLMClient
from tests.unit.test_zt_run_ai_blank_notes_not_sent import World, world  # noqa: F401  (fixture)

pytestmark = pytest.mark.unit

_NOTE = "Phishing-resistant MFA is enforced for every workforce account."


def test_the_payload_handed_to_invoke_omits_blank_note_capabilities(
    world: World,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world.patch(0, notes=_NOTE)
    world.patch(1, notes="N/A")  # not blank: A5, not code, judges it, so it IS sent
    world.patch(2, notes="")
    world.patch(3, notes="   \n\t ")
    with_notes = {world.code(0), world.code(1)}
    blank = {world.code(2), world.code(3)}
    world.respond()

    handed: list[dict[str, Any]] = []
    real_invoke = LLMClient.invoke

    def spy(self, db, **kwargs):  # type: ignore[no-untyped-def]
        if kwargs["purpose"] == "zt_score":
            handed.append(kwargs["payload"])
        return real_invoke(self, db, **kwargs)

    monkeypatch.setattr(LLMClient, "invoke", spy)

    world.run()

    assert len(handed) == 1, handed  # positive first: the run reached invoke once
    payload = handed[0]
    assert with_notes <= set(payload["capabilities"]), payload["capabilities"]
    assert not blank & set(payload["capabilities"]), payload["capabilities"]
    assert not blank & set(payload["capability_details"]), sorted(payload["capability_details"])
    assert not blank & set(payload["answers"]), sorted(payload["answers"])
