"""#806: the ATT&CK `mitre_map` prompt Gene approved, and the fixture written from it.

The prompt is #806 comment 5982555899's fenced text block, approved by Gene on
2026-10-04 (M1 to M3). It is pinned by its sha256, not derived from the
vocabulary (the advisor's ruling C5, #736 comment 5984022081), so what it names
is checked against the vocabulary here instead.

Every expected value below is a literal copied from the approved text or from
the rulings, never imported from the module that builds the prompt or the
fixture.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from app.ai.engine import get_job
from app.attack.catalog import SOURCE_VERSION
from app.attack.coverage import reason_codes_for

pytestmark = pytest.mark.unit

#: #806 comment 5982555899, the fenced `text` block, extracted by script from
#: the live comment with the fence markers removed and nothing else changed:
#: 9982 ASCII bytes, 91 lines, no trailing newline. The coordinator confirmed
#: the same bytes and hash independently.
APPROVED_SHA256 = "322f93b8a3ddc249acd98a3a4e8cbf13930b21c6fa14c52cfb05af8540f34ab7"
APPROVED_BYTES = 9982

#: Section 8 of the approved text: the partial reasons the AI may give.
OFFERED = {"prevention_limited", "recovery_absent", "missing_control_category"}
#: Section 8 of the approved text: the partial reasons the AI may not give.
FORBIDDEN = {
    "reach_limited",
    "evasive_variant_uncovered",
    "periodic_not_continuous",
    "detection_weak",
}


def _prompt() -> str:
    return get_job("mitre_map").prompt


def test_the_mitre_map_prompt_is_the_approved_text() -> None:
    raw = _prompt().encode("utf-8")
    assert len(raw) == APPROVED_BYTES
    assert hashlib.sha256(raw).hexdigest() == APPROVED_SHA256


def test_the_mitre_map_job_is_prompt_version_v2() -> None:
    """D1 (#736 comment 5986064696): `llm_calls` tells the new prompt's runs
    from the old prompt's, which ran as the engine default "v1"."""
    assert get_job("mitre_map").prompt_version == "v2"


def _offered_in_text(prompt: str) -> set[str]:
    """Section 8's bullets: "- `code`: ..." at the start of a line. Section 2
    lists the payload's fields in the same form, so only section 8 is read."""
    section = prompt[prompt.index("\n8. Reason codes\n") : prompt.index("\n9. Rationale\n")]
    return set(re.findall(r"^- `([a-z_]+)`: ", section, flags=re.MULTILINE))


def _forbidden_in_text(prompt: str) -> set[str]:
    (line,) = [ln for ln in prompt.splitlines() if ln.startswith("Do not use `")]
    return set(re.findall(r"`([a-z_]+)`", line))


def test_every_partial_reason_the_prompt_offers_is_a_vocabulary_partial_code() -> None:
    offered = _offered_in_text(_prompt())
    assert offered == OFFERED
    # A renamed code in the vocabulary turns this red: the prompt would offer a
    # code the PATCH and the apply loop no longer accept.
    assert offered <= set(reason_codes_for("partial"))


def test_the_reasons_the_prompt_forbids_are_real_partial_codes() -> None:
    forbidden = _forbidden_in_text(_prompt())
    assert forbidden == FORBIDDEN
    # Forbidding a code that does not exist would forbid nothing.
    assert forbidden <= set(reason_codes_for("partial"))
    # Offered and forbidden together are the whole Partial vocabulary, so a new
    # Partial code arrives as a decision about this prompt, not as a silence.
    assert _offered_in_text(_prompt()) | forbidden == set(reason_codes_for("partial"))


def test_the_prompts_attack_version_is_the_catalogs() -> None:
    match = re.search(r"MITRE ATT&CK Enterprise Version (\d+(?:\.\d+)*)\.", _prompt())
    assert match is not None, "the prompt names no ATT&CK version"
    assert match.group(1) == SOURCE_VERSION


# ---------------------------------------------------------------------------
# The fixture, judged by the prompt's own rules (sections 6 to 8 and 11)
# ---------------------------------------------------------------------------

_ROW_KEYS = {
    "technique_code",
    "status",
    "reason_code",
    "detection_tools",
    "prevention_tools",
    "response_tools",
    "rationale",
}
TOOLS = ["CrowdStrike Falcon", "Splunk Enterprise", "Veeam Backup"]


def _payload(n: int, *, tools: list[str] = TOOLS) -> dict:
    """`n` codes, every other one not preventable. The codes are synthetic, so
    the fixture can only learn `not_preventable` from `technique_details`.
    Every other, not every third: the fixture's partial rows recur every 15
    codes, so a stride of three would never put a not-preventable code on the
    row where it would choose `prevention_limited`."""
    codes = [f"T{1000 + i}" for i in range(n)]
    return {
        "technique_codes": codes,
        "technique_details": {
            c: {"name": f"Technique {c}", "not_preventable": i % 2 == 0}
            for i, c in enumerate(codes)
        },
        "capability_list": [{"name": t, "vendor": "V", "category": "C"} for t in tools],
    }


def _expected_status(row: dict, not_preventable: bool) -> str:
    """Section 7, from the arrays."""
    d, p, r = (bool(row[k]) for k in ("detection_tools", "prevention_tools", "response_tools"))
    required = [d, r] if not_preventable else [d, p, r]
    if all(required):
        return "covered"
    if d or p or r:
        return "partial"
    return "gap"


def _allowed_reasons(row: dict, not_preventable: bool) -> set[str]:
    """Section 8: the code names the function that makes the row partial."""
    missing = {
        f
        for f, key in (
            ("detection", "detection_tools"),
            ("prevention", "prevention_tools"),
            ("response", "response_tools"),
        )
        if not row[key] and not (f == "prevention" and not_preventable)
    }
    if missing == {"prevention"}:
        return {"prevention_limited"}
    if missing == {"response"}:
        # `recovery_absent` only where recovery is materially relevant, which
        # is the model's judgement; otherwise `missing_control_category`.
        return {"recovery_absent", "missing_control_category"}
    return {"missing_control_category"}


def _fixture(payload: dict) -> dict:
    from app.ai.fixtures import _fixture_mitre_map

    return json.loads(_fixture_mitre_map(payload).content)


def test_the_fixture_answers_in_the_prompts_shape_and_nothing_else() -> None:
    payload = _payload(30)
    body = _fixture(payload)
    # Section 11: no other fields at the top level (`executive_summary` and
    # `top_blind_spots` were removed) or in a row.
    assert set(body) == {"techniques"}
    assert [t["technique_code"] for t in body["techniques"]] == payload["technique_codes"]
    for t in body["techniques"]:
        assert set(t) == _ROW_KEYS, t
        for key in ("detection_tools", "prevention_tools", "response_tools"):
            assert set(t[key]) <= set(TOOLS), t
            assert len(t[key]) == len(set(t[key])), t


def test_every_fixture_row_follows_the_prompts_status_and_reason_rules() -> None:
    payload = _payload(50)
    details = payload["technique_details"]
    seen_status: set[str] = set()
    seen_reason: set[str] = set()
    np_covered = 0
    for t in _fixture(payload)["techniques"]:
        np = details[t["technique_code"]]["not_preventable"]
        assert t["status"] == _expected_status(t, np), t
        seen_status.add(t["status"])
        if np:
            assert t["prevention_tools"] == [], t
        if t["status"] == "partial":
            assert t["reason_code"] in _allowed_reasons(t, np), t
            seen_reason.add(t["reason_code"])
        else:
            assert t["reason_code"] is None, t
        if np and t["status"] == "covered":
            np_covered += 1
    # Every status and every offered reason exercised, or the loop proved
    # nothing about the ones it never met.
    assert seen_status == {"covered", "partial", "gap"}
    assert seen_reason == OFFERED
    assert np_covered > 0, "no not-preventable row was covered on Detect and Respond"


def test_the_fixture_with_no_tools_answers_gap_everywhere() -> None:
    """Section 7: all three arrays empty is a gap. A status the arrays cannot
    support is what the old fixture wrote."""
    body = _fixture(_payload(10, tools=[]))
    assert {(t["status"], t["reason_code"]) for t in body["techniques"]} == {("gap", None)}


def test_the_fixture_reads_not_preventable_from_the_payload() -> None:
    """The same code answered as preventable and as not preventable: only
    `technique_details` differs, so a fixture ignoring it cannot pass."""
    base = _payload(1)
    code = base["technique_codes"][0]
    rows = {}
    for flag in (False, True):
        payload = {**base, "technique_details": {code: {"name": "X", "not_preventable": flag}}}
        (rows[flag],) = _fixture(payload)["techniques"]
    assert rows[False]["status"] == rows[True]["status"] == "covered"
    assert rows[False]["prevention_tools"] != []
    assert rows[True]["prevention_tools"] == []
