"""The csf_score prompt IS the approved text (#806), and its own rules hold.

The text is Gene's CSF scoring prompt, #806 comment 5982122270 (approved
2026-10-04, never edited: its `updated_at` equals its `created_at`), the body
of its ```text block placed verbatim. The build was approved as A1 to A5 in
#736 comment 6075712436. v3 (#1046, C-1) applies the two section-12 edits the
advisor approved verbatim in #736 comment 6115773247, and nothing else. v4
(CSF Option 1, D-114) applies the seven-hunk diff in #736 comment 6204461502
section 1, approved verbatim by Gene in 6205956728, and nothing else. Every
expected value below is read from the prompt text, never from the parser's
constants, except where a test checks the parser AGAINST the prompt and says
so.
"""

from __future__ import annotations

import hashlib
import json
import re

import pytest

from app.ai.engine import get_job
from app.csf.maturity import TIER_DEFINITIONS

pytestmark = pytest.mark.unit

# sha256 of the ```text block in #806 comment 5982122270 with the two edits of
# #736 comment 6115773247 applied (v3: 13871 bytes, sha256 523fee871b04876829d5
# 603f8f21013ee56ace543fe53d7db78aee2640d7404a), then the seven hunks of #736
# comment 6204461502 section 1 (v4), with no trailing newline. Derived by
# script from main's v3 text and the comment's diff, each hunk asserted to
# match once, not read from the module. A one-byte drift turns this red.
CSF_SCORE_PROMPT_SHA256 = "c4ac59b7668d04b1eb143eb754ab784580a47e4e004bec20243e4909920bdfc8"
# Its length in UTF-8 bytes, beside the hash.
CSF_SCORE_PROMPT_BYTES = 13977


def _prompt() -> str:
    return get_job("csf_score").prompt


def test_the_prompt_is_the_approved_text() -> None:
    encoded = _prompt().encode("utf-8")
    assert len(encoded) == CSF_SCORE_PROMPT_BYTES
    assert hashlib.sha256(encoded).hexdigest() == CSF_SCORE_PROMPT_SHA256


def test_the_prompt_is_plain_ascii_with_no_control_characters() -> None:
    bad = sorted(
        {hex(ord(ch)) for ch in _prompt() if ord(ch) > 126 or (ord(ch) < 32 and ch != "\n")}
    )
    assert bad == [], bad


def test_the_job_records_the_new_prompt_version() -> None:
    # C9: old and new runs must differ in `llm_calls.prompt_version`. The v1
    # text was every csf_score call before #806; v2 every call before #1046;
    # v3 every call before CSF Option 1 (D-114).
    assert get_job("csf_score").prompt_version == "v4"


def test_the_first_json_example_is_the_scores_object() -> None:
    first = _prompt().index('{"')
    assert _prompt()[first:].startswith('{"scores"')


def test_the_output_example_is_an_answer_the_run_reads_in_full() -> None:
    """Section 12's example row keys, read from the prompt, are exactly the
    keys the apply path reads: the row key plus the value fields."""
    # test-integrity: the parser's constants are what is checked AGAINST the prompt's own example, which supplies the expected keys
    from app.routes.csf import _ROW_KEY_FIELDS, _RUN_FIELDS

    match = re.search(r'\{"scores": \[(\{[^\]]*\})\]\}', _prompt())
    assert match is not None
    example_row = json.loads(match.group(1))
    assert set(example_row) == set(_ROW_KEY_FIELDS) | set(_RUN_FIELDS)


def test_the_prompt_asks_for_no_executive_summary() -> None:
    """Section 12: no other fields. The v1 prompt asked for one; nothing
    persisted it."""
    assert "executive_summary" not in _prompt()
    assert "Do not add a confidence, rationale, or any other key, at the top level or in a row" in (
        _prompt()
    )


def test_every_rating_label_the_prompt_names_is_a_shield_tier_label() -> None:
    """Section 7's required sentences name each tier by its short label. Each
    label, read from the prompt, is the label SHIELD shows for that tier."""
    named = dict(re.findall(r"The recorded maturity rating is Tier (\d) \(([^)]+)\)\.", _prompt()))
    assert sorted(named) == ["1", "2", "3", "4"], named
    shield = {str(int(d.tier)): d.short_label for d in TIER_DEFINITIONS}
    assert named == shield
