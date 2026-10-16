"""risk_synthesize v5's `csf` evidence on an assessment approved under Options 1
and 3 (Gene, #736 6205956728; the section 7 amendment in 6204492978).

`evidence` carries each scored tier's three-valued `evidence_status`, and
`evidence_capped` is NOT sent: no level of a rules-3 assessment was lowered by
the former cap, so the key would only ever say false. The frozen case, where it
is sent, is `test_risk_evidence.py::test_csf_evidence_is_the_playbook_per_tier`.

The world is `test_risk_evidence.py`'s, with its one rules-2 step skipped, so
the two tests differ in exactly the rule. Expected values are typed here from
the world's setup (high: level 2 with evidence on file; moderate: level-4
dimensions with no evidence, uncapped, so level 4), never read from the code.
"""

from __future__ import annotations

import pytest

from tests.unit import test_risk_evidence as world_module
from tests.unit.test_risk_evidence import CSF_A, _findings, _generate, _world
from tests.unit.test_risk_register import app_client  # noqa: F401  (the fixture)

pytestmark = pytest.mark.unit

V5_KEYS = {"enterprise_level", "target_level", "tier_levels", "evidence", "tier_notes"}


def test_a_rules_3_assessment_sends_evidence_and_no_evidence_capped(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    monkeypatch.setattr(world_module, "_approved_before_option_3", lambda _aid: None)
    c, provider, bearer, cid = _world(app_client)
    evidence = _findings(_generate(c, provider, bearer, cid))[CSF_A]["evidence"]
    assert evidence["evidence"] == {"high": "on_file", "moderate": "neither"}  # positive first
    assert set(evidence) == V5_KEYS, sorted(evidence)
    assert "evidence_capped" not in evidence
    # Uncapped: the moderate tier's level-4 dimensions read level 4, so the
    # enterprise level is the high tier's 2.
    assert evidence["tier_levels"] == {"high": 2, "moderate": 4}
