"""The demo seed stores only DoD stages a capability can reach (#839).

The advisor's ruling (#736 comment 6049667540): fix the seed in this PR. It
wrote DoD stages from one fixed pattern shared with CISA, which put stage 4 on
six DoD rows (outside DoD's three-stage ladder; PRE-EXISTING on main) and stage
3 on six capabilities with no DoD Advanced activities, which every write path
now refuses (#839 F1): DOD.DEV.05, APP.03, NET.01, AUT.03, VIS.03 and VIS.05.
The seed writes the store directly, so nothing refused them, and the demo would
have shown the stage-above-maximum disclosure over data no user could enter.

Runs the whole `main()` against SQLite, so the rows checked are the rows the
Demo CI job seeds. Expected codes are copied from the ruling's request
(6049167247), never derived from the code under test.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.zt_assessment import ZtAnswer, ZtAssessment
from app.storage.local import LocalFilesystemStorage

pytestmark = pytest.mark.unit

#: The six over-cap 3s the request named.
OVER_CAP_THREES = {
    "DOD.DEV.05",
    "DOD.APP.03",
    "DOD.NET.01",
    "DOD.AUT.03",
    "DOD.VIS.03",
    "DOD.VIS.05",
}


def _seeded(tmp_path, monkeypatch) -> dict[str, dict[str, int | None]]:
    from scripts import seed_demo

    url = f"sqlite:///{tmp_path / 'seed.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(
        seed_demo, "get_storage", lambda: LocalFilesystemStorage(tmp_path / "storage")
    )
    seed_demo.main()
    out: dict[str, dict[str, int | None]] = {}
    with Session(create_engine(url, future=True)) as db:
        rows = db.execute(
            select(ZtAssessment.framework, ZtAnswer.capability_code, ZtAnswer.maturity_stage).join(
                ZtAssessment, ZtAnswer.assessment_id == ZtAssessment.id
            )
        ).all()
    for fw, code, stage in rows:
        out.setdefault(str(getattr(fw, "value", fw)), {})[code] = stage
    return out


def test_the_seed_stores_only_reachable_dod_stages(tmp_path, monkeypatch) -> None:
    from app.zt.maturity import ZtFrameworkCode
    from app.zt.target_caps import stages_above_capability_max

    seeded = _seeded(tmp_path, monkeypatch)
    dod = seeded["dod_ztra"]
    # The positive state first: the DoD assessment is seeded and answered.
    assert len(dod) == 45
    assert all(stage is not None for stage in dod.values())
    # Nothing outside DoD's three-stage ladder (the six PRE-EXISTING 4s).
    assert set(dod.values()) <= {1, 2, 3}, sorted(dod.items())
    # None of the six named over-cap 3s is stored at 3.
    assert {c: dod[c] for c in OVER_CAP_THREES if dod[c] == 3} == {}
    # And no row anywhere is above its own capability's maximum.
    assert stages_above_capability_max(ZtFrameworkCode.DOD_ZTRA, dod) == ()


def test_the_seed_leaves_the_cisa_pattern_unchanged(tmp_path, monkeypatch) -> None:
    """CISA defines every stage of its four-stage ladder for every capability,
    so the fix must not move a CISA row: the pattern's 4s are still there."""
    seeded = _seeded(tmp_path, monkeypatch)
    cisa = seeded["cisa_ztmm_2_0"]
    assert len(cisa) == 37
    assert sorted(cisa.values()).count(4) == 5  # pattern indexes 6 and 14, over 37 rows
