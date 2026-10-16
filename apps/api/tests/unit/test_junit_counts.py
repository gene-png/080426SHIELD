"""CI's unit run is held to the certified selection through pytest's junit XML.

`check_junit_counts.py` matches each selected node id to the testcase pytest
writes for it. That identity is pytest's, not ours, so these run REAL pytest on
a small project -- a plain test, a class, a parametrized id, a skip and an
xfail -- and require the gate to account for every one: serially, and under
xdist with two workers, as CI runs it with four. The finding and could-not-look
branches are pinned by the fixtures in `tests/gates/check_junit_counts/`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_junit_counts as counts

pytestmark = pytest.mark.unit

_PROJECT = {
    "tests/unit/test_plain.py": """
        import pytest
        pytestmark = pytest.mark.unit
        def test_passes(): pass
        def test_skips(): pytest.skip("not here")
        @pytest.mark.xfail(reason="known", strict=False)
        def test_xfails(): assert False
    """,
    "tests/unit/sub/test_shapes.py": """
        import pytest
        pytestmark = pytest.mark.unit
        class TestGroup:
            def test_in_a_class(self): pass
        @pytest.mark.parametrize("v", ["a.b", "c/d", "e[f]", "x::y"])
        def test_param(v): pass
    """,
}


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    for rel, body in _PROJECT.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body), encoding="utf-8")
    (root / "pytest.ini").write_text("[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8")
    return root


def _pytest(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    return subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-m", "unit", "tests/unit", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _selection(root: Path, out: Path) -> Path:
    proc = _pytest(root, "--collect-only", "-q")
    ids = [ln for ln in proc.stdout.splitlines() if "::" in ln]
    # From _PROJECT's own source: three plain, one class, four parameters.
    assert len(ids) == 8, proc.stdout
    out.write_text("".join(f"{i}\n" for i in ids), encoding="utf-8")
    return out


def _check(root: Path, tmp_path: Path, *run_args: str, capsys) -> tuple[int, str]:
    selected = _selection(root, tmp_path / "selected.txt")
    junit = tmp_path / "junit.xml"
    proc = _pytest(root, f"--junitxml={junit}", *run_args)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    code = counts.main(["check_junit_counts", "--junit", str(junit), "--selected", str(selected)])
    return code, capsys.readouterr().out


def test_a_real_serial_run_is_accounted_for_test_by_test(tmp_path: Path, capsys) -> None:
    code, out = _check(_project(tmp_path), tmp_path, capsys=capsys)
    assert code == 0, out
    assert "8 selected; junit reports 8: 6 passed, 1 skipped, 1 xfailed, 0 failed" in out, out
    assert "skipped, did not run: tests.unit.test_plain::test_skips" in out, out


def test_a_real_xdist_run_is_accounted_for_test_by_test(tmp_path: Path, capsys) -> None:
    pytest.importorskip("xdist", reason="pytest-xdist is a pinned dev dependency; CI installs it")
    code, out = _check(_project(tmp_path), tmp_path, "-n", "2", capsys=capsys)
    assert code == 0, out
    assert "8 selected; junit reports 8: 6 passed, 1 skipped, 1 xfailed, 0 failed" in out, out


@pytest.mark.parametrize(
    ("nodeid", "expected"),
    [
        ("tests/unit/test_a.py::test_b", ("tests.unit.test_a", "test_b")),
        ("tests/unit/test_a.py::TestX::test_y", ("tests.unit.test_a.TestX", "test_y")),
        ("tests/unit/test_a.py::test_p[a.b-c/d]", ("tests.unit.test_a", "test_p[a.b-c/d]")),
    ],
)
def test_the_identity_is_the_one_pytest_writes(nodeid: str, expected: tuple[str, str]) -> None:
    """Written from pytest's own examples of `mangle_test_address`, not from the
    function under test; the real runs above are what prove it matches."""
    assert counts.junit_id(nodeid) == expected
