"""#1000's `no_notes` guard, now the SECOND guard (CSF Option 1, D-114), where
it still decides something: a sent row with no notes that the model leaves out
is counted as no-notes, never alerted as omitted (`_omitted_keys`'s
`- no_notes`).

Since Option 1 a blank-notes row is left out of the payload before egress, so
the guard is reachable only under P1's literal reading
(`LEAVE_OUT_EVERY_BLANK_NOTES = False`), which still sends a blank-notes
subcategory a consultant scored. #1203's review found that, with the leave-out
in place, `test_csf_run_ai_no_notes.py::
test_an_omitted_row_with_no_notes_is_counted_not_alerted` passes through the
leave-out and no longer exercises the subtraction. This test does. Red on
revert: drop `- no_notes` from `_omitted_keys` and the scored blank row is
reported omitted.

The world and helpers are `test_csf_run_ai_no_notes.py`'s; the expected
counts are worked out here from the world, never read from the code.
"""

from __future__ import annotations

import pytest

from tests.unit.test_csf_run_ai_no_notes import (  # noqa: F401  (app_client is a fixture)
    _go_live,
    _notes,
    _run,
    _send_scored_blank_rows,
    _service,
    _type_score,
    app_client,
)

pytestmark = pytest.mark.unit


def test_a_sent_row_with_no_notes_left_out_by_the_model_is_counted_not_omitted(
    app_client,  # noqa: F811
    monkeypatch,
) -> None:
    c, provider, h = app_client
    svc, answers, codes = _service(c, h)
    noted, bare = codes[0], codes[1]
    _notes(c, h, answers[noted], "Asset inventory is reconciled monthly.")
    _type_score(c, h, svc, bare, governance=2)  # scored, no notes: sent under P1's literal reading
    _send_scored_blank_rows(monkeypatch)
    _go_live(provider, monkeypatch)

    body = _run(c, provider, h, svc, codes, [])  # the model answers nothing at all

    # The noted row was asked and left out: a re-run can answer it, so it is
    # an omitted row (positive first).
    assert body["omitted_rows"] == [{"tier": "high", "subcategory_code": noted}], body[
        "omitted_rows"
    ]
    assert body["omitted_count"] == 1
    # The scored blank row was sent too, and left out, but no re-run can give
    # it an answer: it is counted with the rows the leave-out kept back, all
    # of them but the noted one.
    assert body["no_notes_count"] == len(codes) - 1, body["no_notes_count"]
