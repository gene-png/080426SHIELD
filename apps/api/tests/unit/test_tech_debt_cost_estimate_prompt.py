"""TD-5 (for #1060): the cost-estimate prompt is the approved text, byte for byte.

P-TD5 was approved verbatim on #736 (6205600298), with one addition to rule 2
ruled in 6206818759 item 5. The sha256 below was computed from the text as
built and posted on #736 for the advisor to check against the approval; the
sentences below are typed from the approved comment, never from the module, so
a drift says WHICH rule moved rather than only that the hash did.
"""

from __future__ import annotations

import hashlib

import pytest

from app.tech_debt.cost_estimate import PROMPT

pytestmark = pytest.mark.unit

APPROVED_SHA256 = "b89cef74881f0d1620a61bc8a2e5c173707da009bef04b1ee8d56c2228e13741"


def test_the_prompt_is_the_approved_text() -> None:
    assert hashlib.sha256(PROMPT.encode()).hexdigest() == APPROVED_SHA256


@pytest.mark.parametrize(
    "sentence",
    [
        # Rule 2, with the ruled addition inside its null condition.
        "2. If you do not recognise the product, or cannot estimate it with reasonable "
        "confidence, including when the product has no published price, return null for "
        "`annual_cost_usd`. Do not guess.",
        "3. `annual_cost_usd` is a whole number of dollars: no commas, currency signs, "
        "ranges, or text.",
        "5. Do not assume discounts, government pricing, or bundling with other tools "
        "unless `notes` says so.",
        '{"estimates": [{"ref": "T1", "annual_cost_usd": 12000, "basis": "One sentence."}]}',
    ],
    ids=["rule-2", "rule-3", "rule-5", "shape"],
)
def test_the_approved_rules_are_present(sentence: str) -> None:
    assert sentence in PROMPT
