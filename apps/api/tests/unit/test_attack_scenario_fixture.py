"""Fixture mode can run every registered AI job, the what-if included (#802).

Shipping the `attack_scenario_delta` prompt registered its job unconditionally,
and fixture mode (dev, demo, CI's e2e) then had no canned answer for it: every
batch of a what-if failed with `MissingFixtureError`. Two checks:

* every registered job's purpose has a runtime fixture, or an exemption named
  here with its reason. Derived from the registry, so the next job cannot
  ship without one by accident;
* the what-if fixture answers as the PROMPT asks. The batch below is written
  in the prompt's own field names, the expected rows are worked out from the
  prompt's rules by hand, and the answer must then clear `parse_delta` with
  nothing dropped.
"""

from __future__ import annotations

import json

import pytest

from app.ai.engine import get_job, registered_jobs
from app.ai.fixtures import build_runtime_provider
from app.attack import scenario

pytestmark = pytest.mark.unit

#: A registered job whose purpose has no runtime fixture, and why. Empty: every
#: job runs in fixture mode.
EXEMPT: dict[str, str] = {}


def test_every_registered_job_has_a_runtime_fixture_or_a_stated_exemption() -> None:
    fixtures = set(build_runtime_provider()._fixtures)
    names = registered_jobs()
    assert "attack_scenario_delta" in names  # the registry is the one under test
    missing = sorted(
        name for name in names if get_job(name).call_purpose not in fixtures and name not in EXEMPT
    )
    assert missing == [], f"registered jobs with no runtime fixture: {missing}"


# One batch, in the prompt's field names. EDR Suite is removed; it detected and
# responded on T1003 and detected on T1059. T1059's prevention is open (nobody
# prevents it today), and Shield XDR, an added tool, declares detect + prevent.
BATCH = {
    "technique_codes": ["T1003", "T1059"],
    "frozen_rows": [
        {
            "technique_code": "T1003",
            "detection_tools": ["SIEM Core"],
            "prevention_tools": [],
            "response_tools": [],
        },
        {
            "technique_code": "T1059",
            "detection_tools": [],
            "prevention_tools": [],
            "response_tools": [],
        },
    ],
    "lost_functions": {"T1003": ["detection", "response"], "T1059": ["detection"]},
    "open_functions": {"T1003": [], "T1059": ["prevention"]},
    "removed_tools": ["EDR Suite"],
    "added_tools": [
        {
            "name": "Shield XDR",
            "vendor": None,
            "category": "XDR",
            "security_functions": ["detect", "prevent"],
        }
    ],
    "available_tools": [
        {
            "name": "NGFW Gate",
            "vendor": "V",
            "category": "Firewall",
            "security_functions": ["prevent"],
        },
        {
            "name": "SIEM Core",
            "vendor": "V",
            "category": "SIEM",
            "security_functions": ["detect"],
        },
        {
            "name": "SOAR Hub",
            "vendor": "V",
            "category": "SOAR",
            "security_functions": ["respond"],
        },
        {
            "name": "Shield XDR",
            "vendor": None,
            "category": "XDR",
            "security_functions": ["detect", "prevent"],
        },
    ],
}

# By hand, from the prompt's rules:
# T1003 detection (lost): SIEM Core is already listed, so the next tool that
#   declares detect is Shield XDR. T1003 response (lost): SOAR Hub.
# T1059 detection (lost): SIEM Core, not listed there.
# T1059 prevention (open): only an added tool, so not NGFW Gate, a kept tool
#   that declares prevent and is listed first; Shield XDR declares prevent.
EXPECTED = {
    ("T1003", "Shield XDR"): (True, False, False),
    ("T1003", "SOAR Hub"): (False, False, True),
    ("T1059", "SIEM Core"): (True, False, False),
    ("T1059", "Shield XDR"): (False, True, False),
}


def _answer() -> dict:
    raw = (
        build_runtime_provider()
        .complete("", {**BATCH, "__purpose__": "attack_scenario_delta"})
        .content
    )
    return get_job("attack_scenario_delta").parser(raw)


def test_the_what_if_fixture_answers_as_the_prompt_asks() -> None:
    rows = _answer()["rows"]
    got = {
        (r["technique_code"], r["tool"]): (r["detection"], r["prevention"], r["response"])
        for r in rows
    }
    assert got == EXPECTED
    assert len(rows) == len(EXPECTED)  # one row per (technique, tool)
    assert all(isinstance(r["rationale"], str) and r["rationale"] for r in rows)


def test_the_what_if_fixture_clears_the_contract_with_nothing_dropped() -> None:
    added = [scenario.AddedTool.from_stored(t) for t in BATCH["added_tools"]]
    parsed = scenario.parse_delta(
        _answer(),
        asked=BATCH["technique_codes"],
        # The kept tools and the added ones, as the route passes `remaining`.
        available=[t["name"] for t in BATCH["available_tools"]],
        lost=BATCH["lost_functions"],
        opened=BATCH["open_functions"],
        added=added,
    )
    assert parsed.dropped == {}
    assert len(parsed.accepted) == len(EXPECTED)
    assert parsed.lists["T1059"]["prevention_tools"] == ["Shield XDR"]
    assert json.dumps(parsed.lists["T1003"]["response_tools"]) == '["SOAR Hub"]'
