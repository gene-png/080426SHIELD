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

#: The assembled text: 12406 ASCII bytes, 106 lines, no trailing newline.
APPROVED_SHA256 = "9927b960730b468f8e6605cc012befb440b43c783fa2a68f175283f0a675bd48"
APPROVED_BYTES = 12406


def _prompt() -> str:
    return get_job("risk_synthesize").prompt


def test_the_risk_prompt_is_the_approved_text() -> None:
    raw = _prompt().encode("utf-8")
    assert len(raw) == APPROVED_BYTES
    assert hashlib.sha256(raw).hexdigest() == APPROVED_SHA256


def test_the_risk_job_is_prompt_version_v2() -> None:
    """C9 (#806 5983938383): `llm_calls` tells the approved prompt's runs from
    the previous prompt's, which ran as the engine default "v1"."""
    assert get_job("risk_synthesize").prompt_version == "v2"


def test_the_label_example_stays_the_attack_one() -> None:
    """Ruling 7 (#736 6085510246): the prompt keeps "ATT&CK T1003: gap"; the
    CSF level wording lives only in code."""
    prompt = _prompt()
    assert 'label` (for example "ATT&CK T1003: gap")' in prompt
    assert "level 2 of target 3" not in prompt


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
