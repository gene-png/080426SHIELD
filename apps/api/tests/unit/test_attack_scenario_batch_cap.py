"""A what-if batch fits every adapter's output cap three times over (#846 F4).

The advisor's rule (2026-10-03) is that a cap is at least 3x the largest
observed call, and the ruling on #846 (option c) applies it to the 8,192 the
NON-STREAMED adapters send for this purpose. The output scales with the
techniques in a batch, so the guard is on the batch size, from a live figure:
the densest batch measured on 2026-10-04 was 3,052 output tokens for 8
techniques, an average of about 382 a technique (the arithmetic is beside
`BATCH_SIZE`).

What it enforces: 3 x 382 x `BATCH_SIZE` stays within the non-streamed cap. A
batch of 8 or more turns it red, and so does lowering that cap; a batch of 7
(3 x 382 x 7 = 8,022) still passes, with no headroom to speak of.
"""

from __future__ import annotations

import pytest

from app.ai.llm import non_streamed_output_cap
from app.attack import scenario

pytestmark = pytest.mark.unit

#: Measured live, 2026-10-04: 3,052 output tokens for a batch of 8, averaged a
#: technique and rounded up.
DENSEST_TECHNIQUE_OUTPUT = 382


def test_three_times_a_dense_batch_fits_the_non_streamed_cap() -> None:
    worst_batch = DENSEST_TECHNIQUE_OUTPUT * scenario.BATCH_SIZE
    cap = non_streamed_output_cap("attack_scenario_delta")
    assert cap == 8192  # what the non-streamed adapters send; the ruling's figure
    assert 3 * worst_batch <= cap, (
        f"a batch of {scenario.BATCH_SIZE} may need ~{worst_batch} output tokens; "
        f"3x that is over the {cap} the non-streamed adapters send"
    )
