"""NO_AVERAGE in the Playbook files: with no subcategory scored there is no
average to state, so the overview says so (approved as proposed, advisor,
#736 6216024281 item 3c; the text is 6209105057's).

Before Option 3 the seed rows read level 1, so an assessment nobody scored
"averaged 1 of 5". Under rules 3/NULL an unscored subcategory has no level and
is in no average, so W3's `averages {x.x} of 5 ({name})` has nothing to say.

Red-on-revert: change `NO_AVERAGE` in `csf/playbook_export.py` and every file
loses the sentence below.

Every expected string is typed here, never imported from the renderer.
"""

from __future__ import annotations

import pytest

from tests.unit.test_csf_playbook_override_every_artifact import (  # noqa: F401
    _export,
    _flat_text,
    app_client,
)
from tests.unit.test_csf_self_reported_and_uncapped import _world

pytestmark = pytest.mark.unit

NO_AVERAGE = "No subcategory has been scored yet, so there is no average level."


def test_an_export_with_nothing_scored_says_there_is_no_average(
    app_client,  # noqa: F811
) -> None:
    c, h = app_client
    svc, _aid = _world(c, h, ["high"])
    files = _export(c, h, svc)
    for kind in ("full_pdf", "full_docx", "exec_pdf", "exec_docx"):
        flat = _flat_text(kind, files[kind])
        assert NO_AVERAGE in flat, (kind, flat[:2000])  # positive first
        assert "averages " not in flat, (kind, flat[:2000])
