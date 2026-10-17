"""The plugin that narrows one Python CI leg to its share of the certified selection.

`scripts/shard_deselect.py` is the only narrowing between `check_ci_selection.py`'s
certified set and what a leg runs (#544's pin is rewritten around it in
`test_ci_selection_gate.py`). These run REAL pytest on a small project, serially
and under xdist, because the claim is about what pytest ran: the two legs
together ran every test once, the plugin deselected exactly the other leg's
ids, and every way of not knowing the deal is exit 2 rather than a smaller run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET  # noqa: S405 - pytest's own junit, from this test's run
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.shard_deselect as deselect

pytestmark = pytest.mark.unit

_API_DIR = Path(__file__).resolve().parents[2]

_PROJECT = {
    "tests/unit/test_a.py": """
        import pytest
        pytestmark = pytest.mark.unit
        def test_one(): pass
        def test_two(): pass
        @pytest.mark.parametrize("v", ["x", "y", "z"])
        def test_param(v): pass
    """,
    "tests/unit/test_b.py": """
        import pytest
        pytestmark = pytest.mark.unit
        class TestGroup:
            def test_in_a_class(self): pass
        def test_three(): pass
    """,
    "tests/unit/test_not_unit.py": """
        def test_unmarked(): pass
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


def _run(
    root: Path, temp: Path, *args: str, index: str | None = "1", of: str | None = "2"
) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    env["PYTHONPATH"] = str(_API_DIR)
    env["RUNNER_TEMP"] = str(temp)
    for name, value in ((deselect.ENV_INDEX, index), (deselect.ENV_OF, of)):
        env.pop(name, None)
        if value is not None:
            env[name] = value
    return subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "scripts.shard_deselect",
            "-m",
            "unit",
            "tests/unit",
            *args,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _certify(root: Path, temp: Path) -> list[str]:
    """Write the certified selection the way CI's gate does, from a real collection."""
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "-m",
            "unit",
            "tests/unit",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    ids = [ln for ln in proc.stdout.splitlines() if "::" in ln]
    # From _PROJECT's own source: two plain and three parameters, one class, one plain.
    assert len(ids) == 7, proc.stdout
    temp.mkdir(parents=True, exist_ok=True)
    (temp / deselect.SELECTION_NAME).write_text("".join(f"{i}\n" for i in ids), encoding="utf-8")
    return ids


def _ran(junit: Path) -> list[str]:
    cases = ET.parse(junit).getroot().iter("testcase")  # noqa: S314 - own output
    return sorted(f"{c.get('classname')}::{c.get('name')}" for c in cases)


# --- the deal ----------------------------------------------------------------


def test_the_legs_of_a_deal_partition_the_ids() -> None:
    ids = [f"t.py::test_{n:03d}" for n in range(11)]
    legs = [deselect.deal(ids, 3, k) for k in (1, 2, 3)]
    assert sorted(i for leg in legs for i in leg) == sorted(ids)
    assert [len(leg) for leg in legs] == [4, 4, 3]


def test_the_deal_does_not_depend_on_the_order_the_ids_arrive_in() -> None:
    ids = [f"t.py::test_{n:03d}" for n in range(25)]
    # A fixed reordering (not a random one): odd positions last-to-first, then evens.
    shuffled = ids[1::2][::-1] + ids[0::2]
    assert shuffled != ids
    assert deselect.deal(shuffled, 2, 1) == deselect.deal(ids, 2, 1)
    assert deselect.deal(shuffled, 2, 2) == deselect.deal(ids, 2, 2)


def test_the_deal_is_round_robin_over_the_sorted_ids() -> None:
    assert deselect.deal(["c", "a", "d", "b"], 2, 1) == ["a", "c"]
    assert deselect.deal(["c", "a", "d", "b"], 2, 2) == ["b", "d"]


@pytest.mark.parametrize(("of", "index"), [(2, 0), (2, 3), (0, 1), (-1, 1)])
def test_a_leg_outside_the_split_is_refused(of: int, index: int) -> None:
    with pytest.raises(deselect.CouldNotDeal):
        deselect.deal(["a", "b"], of, index)


def test_a_selection_naming_a_test_twice_is_refused() -> None:
    with pytest.raises(deselect.CouldNotDeal, match="twice"):
        deselect.deal(["a", "b", "a"], 2, 1)


# --- a real run ----------------------------------------------------------------


@pytest.mark.parametrize("workers", [(), ("-n", "2")], ids=["serial", "xdist"])
def test_two_legs_together_run_every_selected_test_exactly_once(
    tmp_path: Path, workers: tuple[str, ...]
) -> None:
    if workers:
        pytest.importorskip("xdist", reason="pytest-xdist is a pinned dev dependency")
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    ran: dict[str, list[str]] = {}
    for k in ("1", "2"):
        junit = tmp_path / f"junit-{k}.xml"
        proc = _run(root, tmp_path / "temp", f"--junitxml={junit}", *workers, index=k)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        ran[k] = _ran(junit)
        dealt = (tmp_path / "temp" / deselect.DEALT_NAME).read_text(encoding="utf-8").splitlines()
        assert dealt == deselect.deal(ids, 2, int(k)), proc.stdout
        assert f"shard {k} of 2 dealt {len(dealt)} tests" in proc.stdout, proc.stdout
    together = ran["1"] + ran["2"]
    assert len(together) == len(ids) == len(set(together))
    assert not set(ran["1"]) & set(ran["2"])


def test_a_leg_does_not_run_a_test_the_other_leg_was_dealt(tmp_path: Path) -> None:
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    proc = _run(root, tmp_path / "temp", "-v", index="2")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for nodeid in deselect.deal(ids, 2, 1):
        assert f"{nodeid} PASSED" not in proc.stdout, nodeid
    for nodeid in deselect.deal(ids, 2, 2):
        assert f"{nodeid} PASSED" in proc.stdout, nodeid


@pytest.mark.parametrize(
    ("index", "of"),
    [(None, "2"), ("1", None), ("0", "2"), ("3", "2"), ("one", "2"), ("1", "-2"), ("", "2")],
    ids=["no-index", "no-of", "index-0", "index-over", "not-a-number", "negative-of", "empty"],
)
def test_a_leg_that_does_not_know_its_share_is_exit_2_not_a_smaller_run(
    tmp_path: Path, index: str | None, of: str | None
) -> None:
    root = _project(tmp_path)
    _certify(root, tmp_path / "temp")
    proc = _run(root, tmp_path / "temp", index=index, of=of)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "could not deal" in proc.stdout + proc.stderr
    assert "passed" not in proc.stdout


def test_a_missing_selection_is_exit_2(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (tmp_path / "temp").mkdir()
    proc = _run(root, tmp_path / "temp")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "cannot read the certified selection" in proc.stdout + proc.stderr


def test_an_empty_selection_is_exit_2(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (tmp_path / "temp").mkdir()
    (tmp_path / "temp" / deselect.SELECTION_NAME).write_text("\n", encoding="utf-8")
    proc = _run(root, tmp_path / "temp")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "is empty" in proc.stdout + proc.stderr


def test_a_leg_dealt_nothing_is_exit_2_never_a_pass(tmp_path: Path) -> None:
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    # One test, two legs: leg 2 is dealt none of it.
    (tmp_path / "temp" / deselect.SELECTION_NAME).write_text(ids[0] + "\n", encoding="utf-8")
    proc = _run(root, tmp_path / "temp", index="2")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "was dealt none of the 1 selected tests" in proc.stdout + proc.stderr


def test_a_dealt_test_that_is_not_collected_fails_the_run(tmp_path: Path) -> None:
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    selection = tmp_path / "temp" / deselect.SELECTION_NAME
    selection.write_text(
        "".join(f"{i}\n" for i in [*ids, "tests/unit/test_gone.py::test_x"]), encoding="utf-8"
    )
    proc = _run(root, tmp_path / "temp", index="2")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "were not collected" in proc.stdout + proc.stderr


def test_the_plugin_reads_nothing_but_the_certified_selection(tmp_path: Path) -> None:
    # No command-line list: deselection is driven by RUNNER_TEMP's selection file alone.
    root = _project(tmp_path)
    _certify(root, tmp_path / "temp")
    proc = _run(root, tmp_path / "temp", "--collect-only", "-q", index="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    listed = [ln for ln in proc.stdout.splitlines() if "::" in ln]
    assert len(listed) == 4  # ceil(7 / 2)


def test_a_collected_test_no_leg_was_dealt_fails_the_run_not_dropped(tmp_path: Path) -> None:
    # The gate certified a selection; this run collects a marked test that is NOT in it
    # (a collection that differs between the gate's --collect-only and the run's).
    # Dropping it silently would hide it from check_junit_counts, which used to
    # report "reported but not selected". It must fail the run, whichever leg.
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    left_out = ids[0]
    selection = tmp_path / "temp" / deselect.SELECTION_NAME
    selection.write_text("".join(f"{i}\n" for i in ids[1:]), encoding="utf-8")
    for k in ("1", "2"):
        proc = _run(root, tmp_path / "temp", index=k)
        assert proc.returncode != 0, (k, proc.stdout + proc.stderr)
        out = proc.stdout + proc.stderr
        assert "not in the certified selection" in out and left_out in out, out


def test_a_collected_test_no_leg_was_dealt_fails_under_xdist_too(tmp_path: Path) -> None:
    pytest.importorskip("xdist", reason="pytest-xdist is a pinned dev dependency")
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    (tmp_path / "temp" / deselect.SELECTION_NAME).write_text(
        "".join(f"{i}\n" for i in ids[1:]), encoding="utf-8"
    )
    proc = _run(root, tmp_path / "temp", "-n", "2", index="1")
    # xdist reports a worker's collection error in its own words, so what is pinned
    # is the exit status and that nothing ran, not the plugin's sentence.
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "no tests ran" in proc.stdout and " passed" not in proc.stdout, proc.stdout


def test_a_dealt_test_that_is_not_collected_fails_under_xdist_too(tmp_path: Path) -> None:
    pytest.importorskip("xdist", reason="pytest-xdist is a pinned dev dependency")
    root = _project(tmp_path)
    ids = _certify(root, tmp_path / "temp")
    (tmp_path / "temp" / deselect.SELECTION_NAME).write_text(
        "".join(f"{i}\n" for i in [*ids, "tests/unit/test_gone.py::test_x"]), encoding="utf-8"
    )
    proc = _run(root, tmp_path / "temp", "-n", "2", index="2")
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "no tests ran" in proc.stdout and " passed" not in proc.stdout, proc.stdout
