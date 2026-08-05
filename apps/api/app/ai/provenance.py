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


def protected_keys(rows: Iterable[tuple[str, str | None]], *, is_fixture: bool) -> set[str]:
    """Keys a fixture run must leave alone.

    ``rows`` is (key, answer_source) pairs. Empty for a live run: overwriting a
    client's self-assessment with real analysis is the consultant workflow, and
    the diff is shown for review.
    """
    if not is_fixture:
        return set()
    return {key for key, source in rows if is_client_sourced(source)}
