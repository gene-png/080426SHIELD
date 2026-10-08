"""The CSF catalog holds CSF 2.0's subcategories, not a stand-in (#852).

NIST CSWP 29 (CSF 2.0, February 2024) has no `ID.AM-09` and has `RC.CO-04`.
The catalog had it the other way round, and its total still read 106, so a
count could not see it. The expected values below are written out from the
ruling on #852 (advisor, #736 comment 6054419744) and the Kentro Working
Profile toolkit's Reference Data sheet, never read from the catalog itself.

NOT YET PINNED TO THE NIST PDF: the source test that compares every code with
CSWP 29 waits on the PDF, which could not be fetched here. #852 stays open
until it lands.
"""

from __future__ import annotations

import pytest

from app.csf.catalog import (
    SUBCATEGORIES,
    Alignment,
    CoreClass,
    all_codes,
    ig_metadata_for,
    min_profile_for_category,
    subcategory_by_code,
)

pytestmark = pytest.mark.unit


def test_id_am_09_is_not_in_the_catalog() -> None:
    assert "ID.AM-09" not in all_codes()


def test_rc_co_04_is_in_the_catalog_with_the_nist_outcome() -> None:
    sc = subcategory_by_code("RC.CO-04")
    assert sc.category == "RC.CO"
    assert sc.name == "Public recovery updates"
    assert sc.outcome == (
        "Public updates on incident recovery are shared using approved methods and messaging."
    )


def test_rc_co_03_is_named_for_what_it_says() -> None:
    # Its old short name, "Public updates", described RC.CO-04.
    assert subcategory_by_code("RC.CO-03").name == "Recovery progress communicated"


def test_rc_co_04_follows_its_category_profile_and_ig_class() -> None:
    assert min_profile_for_category(subcategory_by_code("RC.CO-04").category) == "MOD"
    meta = ig_metadata_for("RC.CO-04")
    assert meta is not None
    assert (meta.core_class, meta.alignment) == (CoreClass.CORE, Alignment.SUPPORTING)


def test_every_catalog_code_has_ig_metadata() -> None:
    # ID.AM-09 had none, which is what a code outside the toolkit looks like.
    missing = [s.code for s in SUBCATEGORIES if ig_metadata_for(s.code) is None]
    assert missing == []
