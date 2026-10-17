"""#1325: the ATT&CK run result carries how many techniques the run ASKED the
model about, so "Mapping done for ... across {n} of {total}" reads its total
from the run, not from whatever catalog the page has loaded since.

The workspace derived {total} from the current catalog; the API asks about the
assessment's own rows (less computed parents). The two agree only while the
assessment's rows equal the current catalog, so a run shown after the catalog
moved read a total it was never asked.

The expected count is what the PROVIDER received, summed over the payloads the
test recorded, never a number read from the module under test. A failed batch
counts: its techniques were asked and are the reason "of {total}" is shown.
"""

from __future__ import annotations

import pytest

from tests.unit.test_attack_run_ai import app_client  # noqa: F401  (fixture)
from tests.unit.test_attack_run_ai_reask import _world

pytestmark = pytest.mark.unit


def test_the_run_result_counts_every_technique_it_asked_about(app_client) -> None:  # noqa: F811
    w = _world(app_client, 2)
    w.respond(fail_first_with=w.code(0))
    result = w.run()
    assert result["batches_failed"] >= 1, "setup: a first-pass batch failed"
    asked_first_pass = {c for batch in w.sent for c in batch}
    assert len(asked_first_pass) > 2, "setup: the run asked about the whole assessment"
    assert result["techniques_asked"] == len(asked_first_pass), result.get("techniques_asked")


def test_a_run_that_answers_everything_reports_the_same_count(app_client) -> None:  # noqa: F811
    w = _world(app_client, 2)
    w.respond()
    result = w.run()
    asked = {c for batch in w.sent for c in batch}
    assert result["batches_failed"] == 0
    assert result["techniques_asked"] == len(asked), result.get("techniques_asked")
