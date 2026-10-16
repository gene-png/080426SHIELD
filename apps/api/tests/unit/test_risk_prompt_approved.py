"""#806 / #474 E: the `risk_synthesize` prompt is the approved text, pinned.

Until this file no test pinned the Risk prompt: the record plus both E hunks
were put into `_RISK_SYNTHESIZE_PROMPT` in a scratch copy and 51 Risk, AI, LLM
and measure test files stayed green (#736 comment 6085441609).

The approved text is ASSEMBLED, by script, from three #736 comments, each an
exact replacement asserted to match once:

* the record, #736 comment 5982727504, its fenced `text` block (11664 bytes,
  sha256 5ded5cc98025c605a1708ee621ffa72a5b3bad8b1c221ba2fee5f5c7ac40341a);
* ruling 6's payload amendment (#736 comment 6086417594, approved as written in
  6087027524), replacing the record's INPUT list from "- `findings`:" to the
  `valid_techniques` line, and its ONE ENTRY sentence. Its `attack` line reads
  "as in the record, minus `name`", which is the record's `attack` line with
  "`name` (the technique name), " removed and nothing else changed;
* ruling 4's provenance sentence (same two comments), replacing the record's
  text from "None of it is independent verification:" to "Never describe a
  practice as verified.".

Every expected value below is a literal from that assembly, never read from
the module that builds the prompt.
"""

from __future__ import annotations

import hashlib

import pytest

from app.ai.engine import get_job

pytestmark = pytest.mark.unit

#: v2, the assembled text above: 12406 ASCII bytes, sha256 9927b960730b468f
#: 8e6605cc012befb440b43c783fa2a68f175283f0a675bd48. v3 (ruling #736
#: 6105137014): v2 with `STATUS_BASIS_SENTENCE` appended, after one space, to
#: the `attack` evidence item's last line, "`rationale` and `notes` from the
#: assessment (each possibly null);": 12650 bytes, sha256 66f73a5bc39a5ca6c46
#: 47227cb86665682b1bd50a457057c2829a58ed1476bb2. v4 (ruling #736
#: 6105759625): v3 with "as SHIELD computed it" replaced by "as SHIELD
#: recorded it", and `STORED_RESIDUAL_SENTENCE` appended, after one space, to
#: "unmitigated when it shows none.". Derived by script from v3 and the two
#: edits, not read from the module: 12763 ASCII bytes, 106 lines, no trailing
#: newline.
APPROVED_SHA256 = "c9bdb3fe865d68c07f6bd9adc1c1021243bb912c0c33ad4c72faa8f27c55a797"
APPROVED_BYTES = 12763


def _prompt() -> str:
    return get_job("risk_synthesize").prompt


def test_the_risk_prompt_is_the_approved_text() -> None:
    raw = _prompt().encode("utf-8")
    assert len(raw) == APPROVED_BYTES
    assert hashlib.sha256(raw).hexdigest() == APPROVED_SHA256


def test_the_risk_job_is_prompt_version_v4() -> None:
    """C9 (#806 5983938383): `llm_calls` tells each approved prompt's runs
    apart. v2 was the assembly above; v3 adds ruling #736 6105137014's
    `status_basis` sentence; v4 makes ruling #736 6105759625's two edits."""
    assert get_job("risk_synthesize").prompt_version == "v4"


#: Ruling #736 6105759625, edit 2, verbatim.
STORED_RESIDUAL_SENTENCE = (
    "For a stored status, judge mitigation from the rationale and notes only; a stored "
    "`partial` is partly mitigated."
)


def test_v4_says_recorded_not_computed_in_the_attack_item() -> None:
    """Ruling #736 6105759625, edit 1."""
    prompt = " ".join(_prompt().split())
    assert "`status` (`gap` or `partial`, as SHIELD recorded it)" in prompt
    assert "as SHIELD computed it" not in prompt


def test_v4_adds_the_stored_residual_sentence_after_unmitigated() -> None:
    """Ruling #736 6105759625, edit 2: directly after the sentence containing
    "substantially unmitigated when it shows none"."""
    prompt = " ".join(_prompt().split())
    assert prompt.count(STORED_RESIDUAL_SENTENCE) == 1
    assert ("substantially unmitigated when it shows none. " + STORED_RESIDUAL_SENTENCE) in prompt


#: Ruling #736 6105137014 (finding 1, option (a)), verbatim.
STATUS_BASIS_SENTENCE = (
    "`status_basis` is `computed` when SHIELD derived the status from the function "
    "states given, and `stored` when the status was recorded directly, with no function "
    "states; treat a stored status as given and do not infer missing functions from it."
)


def test_the_status_basis_sentence_is_the_ruling_and_follows_missing_functions() -> None:
    prompt = " ".join(_prompt().split())
    assert prompt.count(STATUS_BASIS_SENTENCE) == 1
    attack = prompt.index("- `attack`: `status`")
    csf = prompt.index("- `csf`: `enterprise_level`")
    # Where `missing_functions` is described: inside the `attack` evidence item.
    assert attack < prompt.index("`missing_functions` (each required function") < csf
    assert attack < prompt.index(STATUS_BASIS_SENTENCE) < csf


def test_the_label_example_stays_the_attack_one() -> None:
    """Ruling 7 (#736 6085510246): the prompt keeps "ATT&CK T1003: gap"; the
    CSF level wording lives only in code."""
    prompt = _prompt()
    assert 'label` (for example "ATT&CK T1003: gap")' in prompt
    assert "level 2 of target 3" not in prompt
    # The label's wording since #736 6216024281 item 3c.
    assert "below target" not in prompt


def test_the_provenance_sentence_is_ruling_4() -> None:
    """Ruling 4 (#736 6086417594, approved in 6087027524), both halves."""
    prompt = " ".join(_prompt().split())
    assert (
        "CSF levels are computed by SHIELD from dimension scores that may have been "
        "drafted by AI and edited by a consultant, and are capped where evidence was "
        "not recorded"
    ) in prompt
    assert (
        "Zero Trust stages may have been entered by the client in a self-assessment, "
        "set by a consultant, or drafted by AI"
    ) in prompt
    # The record's sentence it replaces is gone.
    assert "CSF and Zero Trust ratings and notes may have been entered" not in prompt
