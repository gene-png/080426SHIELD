"""Who supplied a self-assessment answer, and what a fixture run may touch.

Run-AI overwrites every unlocked row and stamps ``answered_by`` with the admin
who pressed the button, so provenance was unrecoverable after the first run.
In the 2026-08-04 review a FIXTURE run on the Zero Trust workspace replaced a
real client self-assessment with canned demo values (average maturity 2.14 ->
1.49, Identity 3.00 -> 1) and nothing afterwards could tell the two apart.

The rule this module encodes: **offline (fixture) output never overwrites what
a client submitted.** Fixture mode stays fully usable — D-017 demos and the e2e
suite depend on it — but client-sourced rows are treated exactly like ``locked``
rows for the duration of a fixture run, and the response says how many were
preserved so the skip is visible rather than silent.
"""

from __future__ import annotations

from collections.abc import Iterable

SOURCE_CLIENT = "client"
SOURCE_AI = "ai"
SOURCE_CONSULTANT = "consultant"


def is_client_sourced(answer_source: str | None) -> bool:
    """True only for answers a client submitted. NULL (pre-0035) is not."""
    return answer_source == SOURCE_CLIENT


def protected_keys(rows: Iterable[tuple[str, str | None, bool]], *, is_fixture: bool) -> set[str]:
    """Keys a fixture run must leave alone.

    ``rows`` is (key, answer_source, is_answered) triples. Empty for a live run:
    overwriting a client's self-assessment with real analysis is the consultant
    workflow, and the diff is shown for review.

    During a fixture run the test is "does this row hold an answer the AI did
    not write?" — deliberately two conditions:

    * **Not AI-written.** Keying on ``SOURCE_CLIENT`` alone left a hole: that
      stamp is applied only when the client SUBMITS, so an in-progress draft
      carried NULL and was overwritten. In the 2026-08-07 live run a client had
      answered 5 of 37 Zero Trust capabilities; a fixture Run-AI changed three
      of the values and re-stamped all five ``ai``, unrecoverably. Pre-0035
      rows carry NULL too, and they are someone's real work as well.

    * **Answered.** A fresh assessment is all NULLs — unanswered *and*
      unstamped. Protecting those would stop a fixture run populating an empty
      assessment at all, which is exactly what D-017 demos and the e2e suite
      depend on. There is nothing to protect in an empty row.

    Fixture may still refresh output it wrote itself.
    """
    if not is_fixture:
        return set()
    return {key for key, source, is_answered in rows if is_answered and source != SOURCE_AI}
