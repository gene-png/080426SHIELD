"""The CISA catalog IS CISA ZTMM 2.0 (#838), held to CISA's own text.

The expected values come from `reference-docs/cisa/cisa_ztmm_v2_rows.json`, the
committed extraction of CISA's PDF (its hash is pinned by `test_zt_sources.py`),
never from `app.zt.catalog`'s own constants. Every name, pillar, order, kind,
Optimal text and pillar definition is compared, so a catalog that drifts from
the PDF in one character goes red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.zt.catalog import capabilities, pillars
from app.zt.maturity import ZtFrameworkCode
from tests._paths import find_zt_source

pytestmark = pytest.mark.unit

_CISA = find_zt_source(Path(__file__).resolve(), "cisa") or Path("/nonexistent/reference-docs/cisa")
_FW = ZtFrameworkCode.CISA_ZTMM_2_0


def _source() -> dict:
    path = _CISA / "cisa_ztmm_v2_rows.json"
    if not path.is_file():
        pytest.fail(f"{path} is not readable: the CISA extraction is the catalog's spec (#838).")
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_pillars_are_cisas_five_with_cisas_definitions() -> None:
    src = _source()["pillars"]
    got = pillars(_FW)
    assert [p.name for p in got] == [p["name"] for p in src]
    assert [p.purpose for p in got] == [p["definition"] for p in src]


def test_every_row_is_cisas_row_in_cisas_order() -> None:
    src = _source()["rows"]
    by_code = {p.code: p.name for p in pillars(_FW)}
    got = capabilities(_FW)
    assert len(got) == len(src) == 37
    for cap, row in zip(got, src, strict=True):
        assert cap.name == row["name"], cap.code
        assert by_code[cap.pillar_code] == row["pillar"], cap.code
        assert cap.kind == row["kind"], cap.code
        assert cap.outcome == f"CISA Optimal: {row['optimal']}", cap.code


def test_cross_cutting_rows_use_their_own_codes_never_a_number() -> None:
    # `CISA.ID.05` and `CISA.DV.05` meant other rows before #838; a cross-cutting
    # row reusing a number would silently re-interpret a stored answer.
    for cap in capabilities(_FW):
        suffix = cap.code.rsplit(".", 1)[1]
        if cap.kind == "cross_cutting":
            assert suffix in ("VA", "AO", "GV"), cap.code
        else:
            assert suffix.isdigit(), cap.code
