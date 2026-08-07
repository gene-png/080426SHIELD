"""A fixture run must not overwrite a client's IN-PROGRESS answers.

`answer_source` is stamped SOURCE_CLIENT only when the client SUBMITS
(routes/zt.py::submit_self_assessment) — deliberately, to capture "the set the
client stands behind". The consequence was that a draft carried NULL provenance
and `protected_keys` skipped it, so an offline Run-AI could overwrite work a
client was part-way through.

Reproduced live 2026-08-07: a client answered 5 of 37 Zero Trust capabilities,
an admin ran fixture-mode Run-AI, and three of the five values changed (3 -> 1)
with all five re-stamped `ai`. The client's own answers were unrecoverable.

The rule: during a FIXTURE run, anything the AI did not itself write is
protected. Fixture may still refresh its own prior output, so D-017 demos and
the e2e suite keep working.
"""

from __future__ import annotations

import pytest

from app.ai.provenance import SOURCE_AI, SOURCE_CLIENT, protected_keys


@pytest.mark.unit
def test_fixture_run_protects_unsubmitted_draft_answers() -> None:
    rows = [
        ("CISA.ID.01", None, True),  # draft: client answered, not yet submitted
        ("CISA.ID.02", SOURCE_CLIENT, True),  # submitted
        ("CISA.ID.03", SOURCE_AI, True),  # previous AI draft
        ("CISA.ID.04", None, False),  # never answered — nothing to protect
    ]
    protected = protected_keys(rows, is_fixture=True)

    assert "CISA.ID.01" in protected, "an in-progress client answer must be protected"
    assert "CISA.ID.02" in protected, "a submitted answer must stay protected"
    assert "CISA.ID.03" not in protected, "fixture may refresh its own prior output"
    assert "CISA.ID.04" not in protected, (
        "an unanswered row must stay writable or a fixture run cannot populate "
        "an empty assessment — D-017 demos and the e2e suite depend on that"
    )


@pytest.mark.unit
def test_live_run_protects_nothing() -> None:
    """Unchanged: drafting over a client's self-assessment with REAL analysis is
    the consultant workflow, and the diff is shown for review."""
    rows = [("CISA.ID.01", None, True), ("CISA.ID.02", SOURCE_CLIENT, True)]
    assert protected_keys(rows, is_fixture=False) == set()
