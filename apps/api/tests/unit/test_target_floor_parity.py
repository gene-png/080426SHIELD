"""#422: the target floors and the below-floor source are ONE value spelled in
two languages, and this test reads the TypeScript spelling and compares.

Before #422 each side spelled its literal in its own suite and named the other
file in the failure message (`test_intake_target_floor.py` here,
`target-options-are-derived.test.ts` there). That turns a unilateral edit red
on the side that made it; it never proved the two AGREE, so an author who
edited both a number and the assertion beside it was not stopped.

The api container now mounts `apps/web/src/lib/assessment-targets.ts`
read-only at `/web-parity/` (`docker-compose.yml`, the zt-data precedent), and
a CI checkout has the file in place, so this runs in both layouts.

FAILS CLOSED: a file it cannot find, or a constant it cannot parse, is a hard
failure naming the mount, never a skip. A parity check that skipped where it
could not look would be green exactly where nobody looked.

**A LOCAL GREEN FROM A LONG-RUNNING CONTAINER IS NOT EVIDENCE** (#794 review,
A1). The mount is ONE file, and a single-file bind pins its inode: after a
checkout or a rename-on-save the container can keep reading the old content.
CI's fresh checkout is the evidence; `tests/_ts_parity.py` says how to get a
trustworthy local run.

Since #422's second half it also compares #783's default-target notes, the
`TARGET_SOURCE_NOTES` table the dashboards derive from.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.assessment_targets import (
    BELOW_FLOOR,
    MIN_TARGET_STAGE,
    MIN_TARGET_TIER,
    TARGET_SOURCE_NOTES,
)
from tests._paths import find_web_assessment_targets
from tests._ts_parity import ts_const, ts_object, web_targets_source

pytestmark = pytest.mark.unit


def _ts_source() -> str:
    return web_targets_source(Path(__file__))


def test_the_tier_floor_is_the_same_number_in_both_languages() -> None:
    assert ts_const(_ts_source(), "MIN_TARGET_TIER") == MIN_TARGET_TIER


def test_the_stage_floor_is_the_same_number_in_both_languages() -> None:
    assert ts_const(_ts_source(), "MIN_TARGET_STAGE") == MIN_TARGET_STAGE


def test_the_below_floor_source_is_the_same_string_in_both_languages() -> None:
    assert ts_const(_ts_source(), "BELOW_FLOOR_SOURCE") == BELOW_FLOOR


def test_the_default_target_notes_are_the_same_table_in_both_languages() -> None:
    """#783's sentences, which the client reads on the dashboard AND in the
    deliverable. The TS table is the one the dashboards derive from; this is
    what makes Python's copy of it provably the same."""
    assert ts_object(_ts_source(), "TARGET_SOURCE_NOTES") == TARGET_SOURCE_NOTES


# --- the parser fails closed ----------------------------------------------


def test_a_missing_constant_fails_rather_than_passing() -> None:
    with pytest.raises(pytest.fail.Exception, match="not found"):
        ts_const("export const OTHER = 2;", "MIN_TARGET_TIER")


def test_a_non_literal_value_fails_rather_than_guessing() -> None:
    with pytest.raises(pytest.fail.Exception, match="not a literal"):
        ts_const("export const MIN_TARGET_TIER = FLOOR + 1;", "MIN_TARGET_TIER")


def test_a_doc_comment_example_above_the_declaration_is_not_read() -> None:
    """#794 review, A2: an unanchored search took the FIRST `export const`
    text in the file, and a doc comment quoting one as an example comes
    first."""
    src = (
        "/**\n"
        " * e.g. export const MIN_TARGET_TIER = 9;\n"
        " */\n"
        "export const MIN_TARGET_TIER = 2;\n"
    )
    assert ts_const(src, "MIN_TARGET_TIER") == 2


def test_an_object_table_is_read_as_prettier_writes_it() -> None:
    src = (
        '/** export const T = { x: { a: "wrong" } }; */\n'
        "export const T = {\n"
        "  tier: {\n"
        '    default: "no tier: chosen",\n'
        '    "client_out_of_range": "not one, CSF has",\n'
        "  },\n"
        "} as const;\n"
    )
    assert ts_object(src, "T") == {
        "tier": {"default": "no tier: chosen", "client_out_of_range": "not one, CSF has"}
    }


def test_an_object_with_a_non_literal_leaf_fails() -> None:
    src = "export const T = {\n  tier: { default: NOTE },\n};\n"
    with pytest.raises(pytest.fail.Exception, match="not a plain object"):
        ts_object(src, "T")


def test_a_missing_object_fails() -> None:
    with pytest.raises(pytest.fail.Exception, match="not found"):
        ts_object("export const OTHER = {\n};\n", "T")


def test_a_wrapped_string_is_read_whole() -> None:
    src = 'export const NOTE =\n  "a starting point";'
    assert ts_const(src, "NOTE") == "a starting point"


# --- the locator, in both states -------------------------------------------


def _checkout(tmp_path: Path) -> Path:
    here = tmp_path / "apps" / "api" / "tests" / "unit"
    here.mkdir(parents=True)
    return here


def test_a_checkout_finds_the_file_beside_it(tmp_path: Path) -> None:
    here = _checkout(tmp_path)
    ts = tmp_path / "apps" / "web" / "src" / "lib" / "assessment-targets.ts"
    ts.parent.mkdir(parents=True)
    ts.write_text("x", encoding="utf-8")
    found = find_web_assessment_targets(here / "t.py", container_path=tmp_path / "nowhere.ts")
    assert found == ts


def test_the_container_finds_the_mounted_file(tmp_path: Path) -> None:
    here = _checkout(tmp_path)
    mounted = tmp_path / "web-parity" / "assessment-targets.ts"
    mounted.parent.mkdir()
    mounted.write_text("x", encoding="utf-8")
    assert find_web_assessment_targets(here / "t.py", container_path=mounted) == mounted


def test_nothing_anywhere_returns_None(tmp_path: Path) -> None:
    here = _checkout(tmp_path)
    assert (
        find_web_assessment_targets(here / "t.py", container_path=tmp_path / "nowhere.ts") is None
    )
