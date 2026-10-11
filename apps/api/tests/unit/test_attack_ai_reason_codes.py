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

#: #806 M3 (Gene, comment 5982555899): the three Partial reasons the AI may
#: give. The other four (`reach_limited`, `evasive_variant_uncovered`,
#: `periodic_not_continuous`, `detection_weak`) stay a consultant's.
PARTIAL_REASONS = {
    "prevention_limited",
    "recovery_absent",
    "missing_control_category",
}


def _offered_partial_codes(prompt: str) -> set[str]:
    """The Partial codes as the PROMPT TEXT lists them in section 8, one per
    bullet: "- `code`: ..." at the start of a line. Section 2 lists the
    payload's fields in the same form, so only section 8 is read."""
    section = prompt[prompt.index("\n8. Reason codes\n") : prompt.index("\n9. Rationale\n")]
    return set(re.findall(r"^- `([a-z_]+)`: ", section, flags=re.MULTILINE))


def test_the_prompt_offers_exactly_the_decided_partial_reasons() -> None:
    assert _offered_partial_codes(_MITRE_MAP_PROMPT) == PARTIAL_REASONS


def test_the_prompt_forbids_not_applicable() -> None:
    """#806: the AI may not return N/A at all, since the payload carries no
    asset inventory that could show a platform absent. The test this replaces
    pinned `platform_absent` as the one N/A reason offered, which is wrong
    under the approved prompt."""
    flat = " ".join(_MITRE_MAP_PROMPT.split())
    # The prohibition, in the prompt's own words.
    assert "Never return `not_applicable`" in flat
    # No N/A reason is offered, and N/A is not among the statuses it allows.
    assert "platform_absent" not in flat
    assert "`status` is `covered`, `partial`, or `gap`." in flat


def test_the_prompts_json_shape_carries_reason_code() -> None:
    assert '"reason_code":' in _MITRE_MAP_PROMPT


def test_every_fixture_reason_is_one_the_prompt_offers() -> None:
    """CLAUDE.md: author fixtures from what the PROMPT says. A fixture reason
    the prompt never offers would agree with the parser and prove nothing."""
    import json

    codes = [f"T{1000 + i}" for i in range(40)]
    payload = {
        "technique_codes": codes,
        # The fields the #806 prompt says the payload carries. Without tools
        # every row would be a gap and no reason would be exercised.
        "technique_details": {
            c: {"name": c, "not_preventable": i % 3 == 0} for i, c in enumerate(codes)
        },
        "capability_list": [{"name": "Tool A"}, {"name": "Tool B"}],
    }
    body = json.loads(_fixture_mitre_map(payload).content)
    offered = _offered_partial_codes(_MITRE_MAP_PROMPT)
    seen: set[tuple[str, str | None]] = set()
    for t in body["techniques"]:
        seen.add((t["status"], t["reason_code"]))
        if t["status"] == "partial":
            assert t["reason_code"] in offered, t
        else:
            assert t["reason_code"] is None, t
    # The reasoned status was actually exercised, or the loop proved nothing.
    assert {s for s, _ in seen} >= {"partial"}
    # #841: the AI may not write N/A, so the fixture must not suggest it.
    assert "not_applicable" not in {s for s, _ in seen}
