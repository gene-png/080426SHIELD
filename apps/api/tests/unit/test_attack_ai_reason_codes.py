"""#554 slice 2: the mitre_map prompt asks for the decided reason codes, and the
fixture answers with codes the PROMPT offers.

Expected values are the owner's decision on #554 typed as literals, never
imported from `app.attack.coverage` -- a prompt test reading its expectations
from the module that builds the prompt agrees with it by construction.
"""

from __future__ import annotations

import re

import pytest

from app.ai.fixtures import _fixture_mitre_map
# test-integrity: the prompt TEXT is the thing under test, not a source of
# expected values -- every expectation below is a literal from the owner's
# decision on #554, and the fixture is checked against what this text says.
from app.ai.jobs import _MITRE_MAP_PROMPT

pytestmark = pytest.mark.unit

PARTIAL_REASONS = {
    "missing_control_category",
    "reach_limited",
    "detection_weak",
    "prevention_limited",
    "evasive_variant_uncovered",
    "recovery_absent",
    "periodic_not_continuous",
}


def _offered_partial_codes(prompt: str) -> set[str]:
    """The Partial codes as the PROMPT TEXT lists them, one per bullet."""
    return set(re.findall(r"^\s+- ([a-z_]+): ", prompt, flags=re.MULTILINE))


def test_the_prompt_offers_exactly_the_decided_partial_reasons() -> None:
    assert _offered_partial_codes(_MITRE_MAP_PROMPT) == PARTIAL_REASONS


def test_the_prompt_allows_only_platform_absent_for_not_applicable() -> None:
    flat = " ".join(_MITRE_MAP_PROMPT.split())
    assert "not_applicable: only `platform_absent`" in flat
    # The prohibition the vocabulary exists for, in the prompt's own words.
    assert "If nothing does, that is gap -- never not_applicable." in flat


def test_the_prompts_json_shape_carries_reason_code() -> None:
    assert '"reason_code":' in _MITRE_MAP_PROMPT


def test_every_fixture_reason_is_one_the_prompt_offers() -> None:
    """CLAUDE.md: author fixtures from what the PROMPT says. A fixture reason
    the prompt never offers would agree with the parser and prove nothing."""
    import json

    codes = [f"T{1000 + i}" for i in range(40)]
    body = json.loads(_fixture_mitre_map({"technique_codes": codes}).content)
    offered = _offered_partial_codes(_MITRE_MAP_PROMPT)
    seen: set[tuple[str, str | None]] = set()
    for t in body["techniques"]:
        seen.add((t["status"], t["reason_code"]))
        if t["status"] == "partial":
            assert t["reason_code"] in offered, t
        elif t["status"] == "not_applicable":
            assert t["reason_code"] == "platform_absent", t
        else:
            assert t["reason_code"] is None, t
    # Both reasoned statuses were actually exercised, or the loop proved nothing.
    assert {s for s, _ in seen} >= {"partial", "not_applicable"}
