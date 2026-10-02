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
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.assessment_targets import BELOW_FLOOR, MIN_TARGET_STAGE, MIN_TARGET_TIER
from tests._paths import WEB_PARITY_TARGETS, find_web_assessment_targets

pytestmark = pytest.mark.unit


def _ts_source() -> str:
    found = find_web_assessment_targets(Path(__file__))
    if found is None:
        pytest.fail(
            "apps/web/src/lib/assessment-targets.ts is not readable: no checkout "
            f"above this file and nothing at {WEB_PARITY_TARGETS}. The api service "
            "mounts it there read-only (docker-compose.yml); recreate the api "
            "container if the mount is newer than it. NOT a skip: #422."
        )
    return found.read_text(encoding="utf-8")


def ts_const(source: str, name: str) -> object:
    """The value of `export const NAME = <number or string>;`, which may wrap.
    Anything else is a parse failure, never a guess."""
    m = re.search(rf"export const {name}\s*=\s*(.+?);", source, re.S)
    if m is None:
        pytest.fail(f"`export const {name}` not found in assessment-targets.ts")
    raw = m.group(1).strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail(f"`{name}` is not a literal number or string: {raw!r}")
    if not isinstance(value, (int, str)) or isinstance(value, bool):
        pytest.fail(f"`{name}` is not a literal number or string: {raw!r}")
    return value


def test_the_tier_floor_is_the_same_number_in_both_languages() -> None:
    assert ts_const(_ts_source(), "MIN_TARGET_TIER") == MIN_TARGET_TIER


def test_the_stage_floor_is_the_same_number_in_both_languages() -> None:
    assert ts_const(_ts_source(), "MIN_TARGET_STAGE") == MIN_TARGET_STAGE


def test_the_below_floor_source_is_the_same_string_in_both_languages() -> None:
    assert ts_const(_ts_source(), "BELOW_FLOOR_SOURCE") == BELOW_FLOOR


# --- the parser fails closed ----------------------------------------------


def test_a_missing_constant_fails_rather_than_passing() -> None:
    with pytest.raises(pytest.fail.Exception, match="not found"):
        ts_const("export const OTHER = 2;", "MIN_TARGET_TIER")


def test_a_non_literal_value_fails_rather_than_guessing() -> None:
    with pytest.raises(pytest.fail.Exception, match="not a literal"):
        ts_const("export const MIN_TARGET_TIER = FLOOR + 1;", "MIN_TARGET_TIER")


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
