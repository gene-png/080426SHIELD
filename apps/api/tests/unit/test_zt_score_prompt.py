"""The zt_score prompt IS the approved text (#806), and its own rules hold.

The text is Gene's combined prompt, #806 comment 5982427179, with B2 replaced
by the advisor's sentence in #806 comment 5982919007, and A9 and Part D item 2
replaced by the amendment approved verbatim in #736 comment 6068587667. It was
assembled by script from those comment bodies. Every expected value below is
read from the prompt text or from the committed source extraction, never from
the parser's constants.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from app.ai.engine import get_job
from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

# sha256 of the approved text: 5982427179 + B2 from 5982919007 + A9 and D2
# from 6068587667. A one-byte drift turns this red.
ZT_SCORE_PROMPT_SHA256 = "654ffe5ba9b35256afefb784f13ed7e9ebc17e8f0d6bb89bc3c73a365bea0caa"
# Its length in UTF-8 bytes, beside the hash (#981 ruling).
ZT_SCORE_PROMPT_BYTES = 14353

_CISA = find_zt_source(Path(__file__).resolve(), "cisa") or Path("/nonexistent/reference-docs/cisa")


def _prompt() -> str:
    return get_job("zt_score").prompt


def test_the_prompt_is_the_approved_text() -> None:
    encoded = _prompt().encode("utf-8")
    assert len(encoded) == ZT_SCORE_PROMPT_BYTES
    assert hashlib.sha256(encoded).hexdigest() == ZT_SCORE_PROMPT_SHA256


def test_the_prompt_is_plain_ascii_with_no_control_characters() -> None:
    bad = sorted(
        {hex(ord(ch)) for ch in _prompt() if ord(ch) > 126 or (ord(ch) < 32 and ch != "\n")}
    )
    assert bad == [], bad


def test_the_job_records_the_new_prompt_version() -> None:
    # C9: old and new runs must differ in `llm_calls.prompt_version`. The v1
    # text was every zt_score call before #806.
    assert get_job("zt_score").prompt_version == "v2"


def test_the_first_json_example_is_the_capabilities_object() -> None:
    first = _prompt().index('{"')
    assert _prompt()[first:].startswith('{"capabilities"')


def test_b2_names_the_cisa_pillars_as_cisa_names_them() -> None:
    """B2 per 5982919007: the pillar names the model is told are the names the
    payload's `pillar` strings carry, which come from CISA's PDF extraction."""
    match = re.search(r"one of the five pillars \(([^)]*)\)", _prompt())
    assert match is not None
    in_prompt = [p.strip() for p in match.group(1).split(",")]
    path = _CISA / "cisa_ztmm_v2_rows.json"
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the CISA extraction is the catalog's spec.")
    source = json.loads(path.read_text(encoding="utf-8"))
    assert in_prompt == [p["name"] for p in source["pillars"]]


def test_the_a9_example_is_an_answer_the_run_reads_in_full() -> None:
    """The A9 example's row keys, read from the prompt, are exactly the keys
    the apply path reads: a row key plus the value fields, nothing left over."""
    # test-integrity: the parser's constants are what is checked AGAINST the prompt's own example, which supplies the expected keys
    from app.routes.zt import _ROW_KEY_FIELDS, _ZT_ROW_FIELDS

    match = re.search(r'\{"capabilities": \[(\{[^\]]*\})\]\}', _prompt())
    assert match is not None
    example_row = json.loads(match.group(1))
    assert set(example_row) == set(_ROW_KEY_FIELDS) | set(_ZT_ROW_FIELDS)


def test_the_prompt_asks_for_no_target() -> None:
    """A6 and A9: no `target` field. The apply path takes `current` only."""
    assert "Do not return a `target` field." in _prompt()
    assert '"target"' not in _prompt()
