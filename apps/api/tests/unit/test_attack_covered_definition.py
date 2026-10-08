"""The consultant's definition of Covered follows R3 (for #842).

R3 (Gene, 2026-10-02, relayed on #554): Covered is Detect AND Prevent AND
Respond, or Detect and Respond where MITRE ATT&CK lists no preventive control.
The definition the catalog served still read "Detection + response controls are
in place". The new text is the one the advisor approved on #736 (comment
6053562002), copied here, never imported.
"""

from __future__ import annotations

import pytest

from tests.unit.test_attack_catalog_version_guard import (  # noqa: F401  (fixture)
    _auth,
    _register,
    env,
)

pytestmark = pytest.mark.unit

COVERED = (
    "Detect, Prevent and Respond are all in place for this technique, or Detect and "
    "Respond where MITRE ATT&CK lists no preventive control. In place means at least "
    "one confirmed tool provides it."
)


def test_the_catalog_defines_covered_as_r3_does(env) -> None:  # noqa: F811
    c, _Sess = env
    bearer = _register(c, "admin@example.com")["tokens"]["access_token"]
    r = c.get("/attack/catalog", headers=_auth(bearer))
    assert r.status_code == 200, r.text
    (covered,) = [d for d in r.json()["coverage_definitions"] if d["status"] == "covered"]
    assert covered["short_label"] == "Covered"
    assert covered["description"] == COVERED
