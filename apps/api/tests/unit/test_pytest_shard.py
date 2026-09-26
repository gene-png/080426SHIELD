"""CI's unit suite runs in shards, and the shards must PARTITION it.

The split is derived from collection: every selected test is dealt to exactly
one shard. A shard that loses a test is a test CI never runs -- the failure
#540 exists for, reached a new way -- so the aggregate job checks the union of
what the shards ran against the full selection. These tests pin both halves:
the assignment itself, the plugin end to end with real pytest, and the verifier
that the aggregate job runs.

Written before the plugin and the verifier.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from collections import Counter
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.pytest_shard as shard
import scripts.shard_partition as partition

pytestmark = pytest.mark.unit

_API = Path(__file__).resolve().parents[2]


# --- the spec --------------------------------------------------------------------


@pytest.mark.parametrize(("spec", "expected"), [("1/4", (1, 4)), ("4/4", (4, 4)), ("1/1", (1, 1))])
def test_a_shard_spec_parses(spec: str, expected: tuple[int, int]) -> None:
    assert partition.parse_spec(spec) == expected


@pytest.mark.parametrize(
    "spec", ["", "0/4", "5/4", "1/0", "a/4", "1/", "/4", "1-4", " 1/4", "1/4 ", "01/4"]
)
def test_a_bad_shard_spec_is_refused(spec: str) -> None:
    with pytest.raises(partition.ShardSpecError):
        partition.parse_spec(spec)


# --- the assignment --------------------------------------------------------------


def _ids(per_file: dict[str, int]) -> list[str]:
    return [f"{f}::test_{i}" for f, n in per_file.items() for i in range(n)]


@pytest.mark.parametrize("n", [1, 2, 3, 4, 7])
def test_every_test_is_assigned_exactly_one_shard_in_range(n: int) -> None:
    ids = _ids({"tests/unit/test_a.py": 11, "tests/unit/test_b.py": 1, "tests/unit/test_c.py": 6})
    assigned = partition.assign(ids, n)
    assert sorted(assigned) == sorted(ids)
    assert set(assigned.values()) <= set(range(1, n + 1))


def test_one_large_file_is_spread_evenly_across_shards() -> None:
    """The measured case: one file held most of the selection, so dealing by
    FILE cannot balance. Its tests are dealt round-robin instead."""
    ids = _ids({"tests/unit/test_big.py": 10})
    counts = Counter(partition.assign(ids, 4).values())
    assert sorted(counts.values()) == [2, 2, 3, 3], counts


def test_single_test_files_do_not_all_land_on_shard_one() -> None:
    ids = _ids({f"tests/unit/test_{c}.py": 1 for c in "abcdefgh"})
    counts = Counter(partition.assign(ids, 4).values())
    assert sorted(counts.values()) == [2, 2, 2, 2], counts


def test_the_assignment_does_not_depend_on_input_order() -> None:
    ids = _ids({"tests/unit/test_a.py": 5, "tests/unit/test_b.py": 3})
    assert partition.assign(ids, 3) == partition.assign(list(reversed(ids)), 3)


# --- the plugin, end to end with real pytest --------------------------------------

_MARKED = """
    import pytest
    pytestmark = pytest.mark.unit
    @pytest.mark.parametrize("i", range({n}))
    def test_p(i): pass
"""
_UNMARKED = """
    def test_never_selected(): pass
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "tests" / "unit").mkdir(parents=True)
    (root / "pytest.ini").write_text("[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8")
    for name, body in {
        "test_big.py": _MARKED.format(n=9),
        "test_small.py": _MARKED.format(n=2),
        "test_plain.py": _UNMARKED,
    }.items():
        (root / "tests" / "unit" / name).write_text(textwrap.dedent(body), encoding="utf-8")
    return root


def _run_shard(root: Path, spec: str | None, record: Path | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in (shard.SHARD_ENV, shard.RECORD_ENV)}
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(_API), env.get("PYTHONPATH")]))
    env.pop("PYTEST_ADDOPTS", None)
    if spec is not None:
        env[shard.SHARD_ENV] = spec
    if record is not None:
        env[shard.RECORD_ENV] = str(record)
    return subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-p", "scripts.pytest_shard",
         "-q", "-m", "unit", "tests/unit"],  # fmt: skip
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _selected(root: Path) -> set[str]:
    return {f"tests/unit/test_big.py::test_p[{i}]" for i in range(9)} | {
        f"tests/unit/test_small.py::test_p[{i}]" for i in range(2)
    }


def test_the_shards_run_every_selected_test_exactly_once(tmp_path: Path) -> None:
    root = _project(tmp_path)
    ran: list[str] = []
    for k in (1, 2, 3):
        record = tmp_path / f"ran-{k}.txt"
        proc = _run_shard(root, f"{k}/3", record)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        ran += [ln for ln in record.read_text(encoding="utf-8").splitlines() if ln]
    assert Counter(ran).most_common(1)[0][1] == 1, "a test ran in two shards"
    assert set(ran) == _selected(root), set(ran) ^ _selected(root)


def test_a_shard_runs_only_its_own_tests_and_says_how_many(tmp_path: Path) -> None:
    root = _project(tmp_path)
    record = tmp_path / "ran.txt"
    proc = _run_shard(root, "2/3", record)
    kept = [ln for ln in record.read_text(encoding="utf-8").splitlines() if ln]
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 0 < len(kept) < len(_selected(root))
    assert f"{len(kept)} passed" in proc.stdout, proc.stdout
    assert f"shard 2/3 kept {len(kept)} of {len(_selected(root))}" in proc.stdout, proc.stdout


@pytest.mark.parametrize(
    ("spec", "record"),
    [(None, True), ("2/3", False), ("3/2", True), ("", True)],
    ids=["no-shard-env", "no-record-env", "k-above-n", "empty-spec"],
)
def test_a_missing_or_bad_setting_fails_rather_than_running_everything(
    tmp_path: Path, spec: str | None, record: bool
) -> None:
    root = _project(tmp_path)
    proc = _run_shard(root, spec, tmp_path / "ran.txt" if record else None)
    assert proc.returncode != 0, proc.stdout
    assert "passed" not in proc.stdout, "it ran tests with no shard to run"


def test_a_shard_with_nothing_to_run_fails(tmp_path: Path) -> None:
    """More shards than selected tests leaves one empty. A selector that
    selects nothing passes, so an empty shard is refused, not green."""
    root = _project(tmp_path)
    proc = _run_shard(root, "12/12", tmp_path / "ran.txt")
    assert proc.returncode != 0, proc.stdout
    assert "selected no tests" in proc.stdout + proc.stderr


# --- the verifier the aggregate job runs ------------------------------------------


def _write(path: Path, ids: list[str]) -> Path:
    path.write_text("".join(f"{i}\n" for i in ids), encoding="utf-8")
    return path


FULL = ["t.py::a", "t.py::b", "t.py::c", "u.py::d"]


def _verify(tmp_path: Path, shards: list[list[str]], full: list[str] = FULL, of: int | None = None):
    argv = ["shard_partition", "verify", "--full", str(_write(tmp_path / "full.txt", full))]
    if of is not None:
        argv += ["--of", str(of)]
    argv += ["--ran"] + [str(_write(tmp_path / f"ran-{i}.txt", s)) for i, s in enumerate(shards, 1)]
    return partition.main(argv)


def test_a_true_partition_verifies(tmp_path: Path, capsys) -> None:
    assert _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b", "t.py::c"]], of=2) == 0
    assert "4 of 4 selected tests ran in exactly one of 2 shards" in capsys.readouterr().out


def test_a_gap_is_a_finding_naming_the_test(tmp_path: Path, capsys) -> None:
    assert _verify(tmp_path, [["t.py::a", "u.py::d"], ["t.py::b"]], of=2) == 1
    assert "t.py::c" in capsys.readouterr().out


def test_a_duplicate_is_a_finding_naming_the_test(tmp_path: Path, capsys) -> None:
    assert _verify(tmp_path, [["t.py::a", "u.py::d", "t.py::b"], ["t.py::b", "t.py::c"]], of=2) == 1
    assert "t.py::b" in capsys.readouterr().out


def test_a_test_outside_the_selection_is_a_finding(tmp_path: Path, capsys) -> None:
    assert _verify(tmp_path, [["t.py::a", "u.py::d", "x.py::z"], ["t.py::b", "t.py::c"]], of=2) == 1
    assert "x.py::z" in capsys.readouterr().out


def test_the_wrong_number_of_shard_records_is_could_not_look(tmp_path: Path) -> None:
    assert _verify(tmp_path, [FULL], of=2) == 2


@pytest.mark.parametrize("which", ["empty-full", "empty-shard", "missing-shard"])
def test_an_empty_or_missing_input_is_could_not_look(tmp_path: Path, which: str) -> None:
    if which == "empty-full":
        assert _verify(tmp_path, [FULL], full=[], of=1) == 2
    elif which == "empty-shard":
        assert _verify(tmp_path, [FULL, []], of=2) == 2
    else:
        argv = ["shard_partition", "verify", "--full", str(_write(tmp_path / "f.txt", FULL)),
                "--of", "1", "--ran", str(tmp_path / "nope.txt")]  # fmt: skip
        assert partition.main(argv) == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["shard_partition"],
        ["shard_partition", "bogus"],
        ["shard_partition", "verify"],
        # #680 round 1: the separate collector is gone; the gate writes the set.
        ["shard_partition", "collect", "--out", "x"],
    ],
)
def test_a_bad_invocation_is_could_not_look(argv: list[str]) -> None:
    assert partition.main(argv) == 2
