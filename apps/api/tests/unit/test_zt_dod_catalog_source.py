"""The DoD catalog IS the 2025 DoD CIO roadmap (#839), held to its own text.

The expected values come from `reference-docs/dod/dod_zt_2025_rows.json`, the
committed extraction of DoD CIO's 2025 document 25-T-1465 (its hash is pinned by
`test_zt_sources.py`), never from `app.zt.catalog`'s own constants. Every
pillar, capability and activity is compared, so a catalog that drifts from the
PDF in one character goes red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.zt.catalog import capabilities, pillars
from app.zt.maturity import ZtFrameworkCode
from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

_DOD = find_zt_source(Path(__file__).resolve(), "dod") or Path("/nonexistent/reference-docs/dod")
_FW = ZtFrameworkCode.DOD_ZTRA


def _source() -> dict:
    path = _DOD / "dod_zt_2025_rows.json"
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the DoD extraction is the catalog's spec (#839).")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_pillars_are_dods_seven_in_dods_order() -> None:
    src = _source()["capabilities"]
    in_order = list(dict.fromkeys((c["pillar_number"], c["pillar"]) for c in src))
    assert [p.name for p in pillars(_FW)] == [name for _, name in in_order]


def test_every_capability_is_dods_in_dods_order() -> None:
    src = _source()["capabilities"]
    by_code = {p.code: p.name for p in pillars(_FW)}
    got = capabilities(_FW)
    assert len(got) == len(src) == 45
    for cap, row in zip(got, src, strict=True):
        assert cap.dod_number == row["id"], cap.code
        assert cap.code.endswith(f".{int(row['id'].split('.')[1]):02d}"), cap.code
        assert cap.name == row["name"], cap.code
        assert by_code[cap.pillar_code] == row["pillar"], cap.code
        assert cap.outcome == f"DoD: {row['description']}", cap.code


def test_every_activity_is_dods_under_its_capability() -> None:
    src = _source()["activities"]
    got = [(cap, a) for cap in capabilities(_FW) for a in cap.activities]
    assert len(got) == len(src) == 152
    for (cap, act), row in zip(got, src, strict=True):
        assert act.id == row["id"]
        assert act.id.startswith(f"{cap.dod_number}."), (cap.code, act.id)
        assert act.name == row["name"], act.id
        assert act.level == row["level"], act.id
        expected = row["description"]
        if row["outcomes"]:
            expected += " Outcomes: " + row["outcomes"]
        if row["end_state"]:
            expected += " End state: " + row["end_state"]
        assert act.description == expected, act.id


def test_activities_are_sorted_by_id_within_each_capability() -> None:
    for cap in capabilities(_FW):
        ids = [tuple(int(x) for x in a.id.split(".")) for a in cap.activities]
        assert ids == sorted(ids), cap.code
        assert ids, f"{cap.code} has no activities"


def test_cisa_rows_carry_no_activities_and_no_dod_number() -> None:
    for cap in capabilities(ZtFrameworkCode.CISA_ZTMM_2_0):
        assert cap.activities == ()
        assert cap.dod_number is None
