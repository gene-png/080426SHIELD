"""#806 Risk record, item 4: the fixture is written from the approved prompt.

Two of its rules are pinned here, through the generate route in fixture mode,
with expected values written from the prompt's text:

* COMPENSATING CONTROLS: "Identify only compensating controls the evidence
  shows ... confirmed tools in an ATT&CK finding's `in_place` functions", and
  "If none are identified, return exactly 'None identified in the supplied
  information.'" The fixture used to say "Interim monitoring in place." for
  every entry: an invented control, which the record forbids.
* `other_axes`: "For an ATT&CK finding, each function in `missing_functions`
  is directly affected", never repeating `axis`, ordered detection,
  prevention, response.

The record's third fixture item, at least one null rating, is NOT built here:
publish refuses an unrated entry, so it changes the demo and e2e flows, and it
is held for a ruling (see the E report).
"""

from __future__ import annotations

import pytest

from app.ai.fixtures import build_runtime_provider

from .test_risk_evidence import NOT_PREVENTABLE, PREVENTABLE, _seed_attack, _seed_zt
from .test_risk_register import (
    _admin,
    _generated_audit,
    app_client,  # noqa: F401  -- the fixture, used by name below.
)

pytestmark = pytest.mark.unit

NONE_SENTENCE = "None identified in the supplied information."
ORDER = ["detection", "prevention", "response"]


def test_the_fixture_names_only_evidenced_controls_and_affected_axes(
    app_client,  # noqa: F811
) -> None:
    c, provider = app_client
    # The fixture-mode answer, as `SHIELD_LLM_MODE=fixture` serves it.
    runtime = build_runtime_provider()
    provider.register("risk_synthesize", lambda payload: runtime.complete("", payload))
    bearer, cid = _admin(c)
    h = {"Authorization": f"Bearer {bearer}", "X-Client-Id": cid}
    _seed_attack(c, h)
    _seed_zt(c, h)
    r = c.post(
        f"/risk/clients/{cid}/register/generate", headers={"Authorization": f"Bearer {bearer}"}
    )
    assert r.status_code == 201, r.text
    by_sid = {e["source_id"]: e for e in r.json()["entries"]}
    # What must appear first: both ATT&CK findings drafted.
    assert {PREVENTABLE, NOT_PREVENTABLE} <= set(by_sid)

    # Detect is in place by the confirmed "Tool D"; Respond's "Tool R" is only
    # cited, so it is no control.
    preventable = by_sid[PREVENTABLE]
    assert "Tool D" in preventable["compensating_controls"]
    assert "Tool R" not in preventable["compensating_controls"]
    assert preventable["other_axes"] == [
        a for a in ORDER if a in ("prevention", "response") and a != preventable["axis"]
    ]
    # Nothing in place: the exact sentence.
    assert by_sid[NOT_PREVENTABLE]["compensating_controls"] == NONE_SENTENCE
    assert by_sid[NOT_PREVENTABLE]["other_axes"] == [
        a for a in ORDER if a in ("detection", "response") and a != by_sid[NOT_PREVENTABLE]["axis"]
    ]
    # Zero Trust evidence names no control and no function.
    zt = [e for e in by_sid.values() if e["source_id"].startswith("DOD.")]
    assert zt and all(e["compensating_controls"] == NONE_SENTENCE for e in zt)
    assert all(e["other_axes"] == [] for e in zt)
    assert "Interim monitoring" not in r.text
    # The fixture's other_axes are valid, so nothing was dropped.
    assert _generated_audit(c, bearer)["other_axes_dropped"] == {}
