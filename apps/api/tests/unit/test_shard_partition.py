"""The verifier the E2E aggregate runs: the shard lists partition the suite.

`scripts/shard_partition.py verify` is what turns four Playwright `--list`
outputs into one verdict for the required `E2E (Playwright smoke suite)`
check. These pin it directly: a partition passes, and a gap, a duplicate, an
id outside the full list, and every could-not-look input are each refused
with their own code. Moved here from `test_pytest_shard.py` when the unit
suite stopped being sharded (it now runs under xdist on one runner); the
verifier tests are unchanged but for the clean line, which now says the
tests are LISTED in a shard, since a list is a selection and not a run (#689).
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.shard_partition as partition

pytestmark = pytest.mark.unit


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
    assert "4 of 4 selected tests are in exactly one of 2 shard lists" in capsys.readouterr().out


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
