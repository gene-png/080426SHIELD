"""The required Python check's aggregate holds both legs to one certified selection.

`scripts/check_python_shards.py` reads what each leg uploaded -- its selection,
its dealt list and its junit -- and is the only thing that turns two legs'
results into the one required `Python (ruff + black + pytest + bandit)` verdict.
Every refusal has its own test, because a branch that exits 0 on input it could
not read is the failure this gate exists to prevent (D-090): a missing leg, a
second selection, a gap, a duplicate across junits, a leg that ran something it
was not dealt, and every unreadable input.

The junits are written by hand here in pytest's own shape (classname + name from
`junit_id`), so each case builds exactly the world it names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_python_shards as shards
from scripts.check_junit_counts import junit_id

pytestmark = pytest.mark.unit

IDS = [f"tests/unit/test_{c}.py::test_{n}" for c in "abc" for n in range(4)]
LEG1, LEG2 = IDS[0::2], IDS[1::2]


def _selection(path: Path, ids: list[str]) -> None:
    path.write_text("".join(f"{i}\n" for i in ids), encoding="utf-8")


def _junit(path: Path, ids: list[str], *, seconds: float = 100.0, skipped: tuple[str, ...] = ()):
    cases = []
    for nodeid in ids:
        classname, name = junit_id(nodeid)
        body = '<skipped type="pytest.skip" message="s"/>' if nodeid in skipped else ""
        cases.append(
            f'<testcase classname="{classname}" name="{name}" time="0.01">{body}</testcase>'
        )
    path.write_text(
        f'<?xml version="1.0"?><testsuites><testsuite name="pytest" time="{seconds}">'
        + "".join(cases)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )


def _legs(
    root: Path,
    *,
    selections: tuple[list[str], list[str]] = (IDS, IDS),
    dealt: tuple[list[str], list[str]] = (LEG1, LEG2),
    ran: tuple[list[str], list[str]] = (LEG1, LEG2),
    seconds: tuple[float, float] = (100.0, 110.0),
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for k in (1, 2):
        _selection(root / f"selection-{k}.txt", selections[k - 1])
        _selection(root / f"dealt-{k}.txt", dealt[k - 1])
        _junit(root / f"junit-{k}.xml", ran[k - 1], seconds=seconds[k - 1])
    return root


def _check(root: Path, capsys, of: int = 2) -> tuple[int, str]:
    code = shards.main(["check_python_shards", "--dir", str(root), "--of", str(of)])
    return code, capsys.readouterr().out


def test_two_legs_that_split_one_selection_and_ran_it_once_are_clean(tmp_path, capsys) -> None:
    code, out = _check(_legs(tmp_path / "d"), capsys)
    assert code == 0, out
    assert "leg 1: dealt 6, junit reports 6 (6 passed" in out, out
    assert "leg 2: dealt 6, junit reports 6 (6 passed" in out, out
    assert "clean -- 2 legs, one certified selection, every test ran once" in out, out


def test_a_skipped_test_is_counted_and_not_a_finding(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    _junit(root / "junit-1.xml", LEG1, skipped=(LEG1[0],))
    code, out = _check(root, capsys)
    assert code == 0, out
    assert "1 skipped" in out, out


def test_the_artifacts_may_sit_in_per_leg_folders(tmp_path, capsys) -> None:
    # actions/download-artifact without merge-multiple nests each upload in its own folder.
    root = tmp_path / "d"
    for k in (1, 2):
        _legs(tmp_path / "flat")
        (root / f"python-shard-{k}").mkdir(parents=True)
        for kind, suffix in (("selection", "txt"), ("dealt", "txt"), ("junit", "xml")):
            src = tmp_path / "flat" / f"{kind}-{k}.{suffix}"
            (root / f"python-shard-{k}" / src.name).write_bytes(src.read_bytes())
    code, out = _check(root, capsys)
    assert code == 0, out


def test_a_selection_that_differs_between_the_legs_is_a_finding(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d", selections=(IDS, IDS[:-1]))
    code, out = _check(root, capsys)
    assert code == 1, out
    assert "the legs certified DIFFERENT selections" in out, out


def test_selections_that_differ_only_in_bytes_are_still_different(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    (root / "selection-2.txt").write_bytes((root / "selection-2.txt").read_bytes() + b"\n")
    code, out = _check(root, capsys)
    assert code == 1, out
    assert "DIFFERENT selections" in out, out


def test_a_test_dealt_to_no_leg_is_a_finding_naming_it(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d", dealt=(LEG1, LEG2[:-1]), ran=(LEG1, LEG2[:-1]))
    code, out = _check(root, capsys)
    assert code == 1, out
    assert f"selected but ran in no shard: {LEG2[-1]}" in out, out
    assert f"all legs together: selected but never reported: {LEG2[-1]}" in out, out


def test_a_test_dealt_to_both_legs_is_a_finding_naming_it(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d", dealt=(LEG1 + [LEG2[0]], LEG2), ran=(LEG1 + [LEG2[0]], LEG2))
    code, out = _check(root, capsys)
    assert code == 1, out
    assert f"ran in 2 shards: {LEG2[0]}" in out, out
    assert f"all legs together: reported 2 times: {LEG2[0]}" in out, out


def test_a_test_in_both_junits_is_a_duplicate_even_when_the_dealt_lists_are_clean(
    tmp_path, capsys
) -> None:
    # The dealt lists partition, but leg 2's run also reported one of leg 1's tests.
    root = _legs(tmp_path / "d", ran=(LEG1, LEG2 + [LEG1[0]]))
    code, out = _check(root, capsys)
    assert code == 1, out
    assert f"all legs together: reported 2 times: {LEG1[0]}" in out, out
    assert (
        f"leg 2: reported but not selected: {junit_id(LEG1[0])[0]}::{junit_id(LEG1[0])[1]}" in out
    )


def test_a_leg_that_lost_a_dealt_test_is_a_finding_for_that_leg(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d", ran=(LEG1[:-1], LEG2))
    code, out = _check(root, capsys)
    assert code == 1, out
    assert f"leg 1: selected but never reported: {LEG1[-1]}" in out, out


def test_a_failed_dealt_test_is_a_finding(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    classname, name = junit_id(LEG2[0])
    text = (root / "junit-2.xml").read_text(encoding="utf-8")
    old = f'<testcase classname="{classname}" name="{name}" time="0.01"></testcase>'
    assert text.count(old) == 1
    (root / "junit-2.xml").write_text(
        text.replace(old, old.replace("></testcase>", '><failure message="x"/></testcase>')),
        encoding="utf-8",
    )
    code, out = _check(root, capsys)
    assert code == 1, out
    assert "leg 2: passed + skipped + xfailed is 5, short of the 6 selected (1 failed" in out, out


def test_legs_far_apart_in_time_are_noted_and_not_a_finding(tmp_path, capsys) -> None:
    code, out = _check(_legs(tmp_path / "d", seconds=(300.0, 520.0)), capsys)
    assert code == 0, out
    assert "NOTE: the legs differ by 220s" in out, out


def test_legs_close_in_time_carry_no_note(tmp_path, capsys) -> None:
    code, out = _check(_legs(tmp_path / "d", seconds=(300.0, 410.0)), capsys)
    assert code == 0, out
    assert "NOTE" not in out, out


@pytest.mark.parametrize("kind", ["selection-2.txt", "dealt-2.txt", "junit-2.xml"])
def test_a_missing_leg_file_is_could_not_look(tmp_path, capsys, kind: str) -> None:
    root = _legs(tmp_path / "d")
    (root / kind).unlink()
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "could not look" in out and "expected exactly 2" in out, out


def test_a_third_leg_file_is_could_not_look(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    _selection(root / "dealt-3.txt", IDS)
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "found indexes [1, 2, 3]" in out, out


def test_a_misnamed_file_is_could_not_look(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    _selection(root / "selection-two.txt", IDS)
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "is not named selection-<index>.txt" in out, out


def test_two_files_for_one_index_are_could_not_look(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    (root / "again").mkdir()
    _selection(root / "again" / "dealt-1.txt", IDS)
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "two dealt files for one index" in out, out


@pytest.mark.parametrize("name", ["selection-1.txt", "dealt-2.txt"])
def test_an_empty_list_is_could_not_look(tmp_path, capsys, name: str) -> None:
    root = _legs(tmp_path / "d")
    (root / name).write_text("\n", encoding="utf-8")
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "is empty" in out, out


def test_a_junit_with_no_testcase_is_could_not_look(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    (root / "junit-1.xml").write_text("<testsuites><testsuite time='1'/></testsuites>")
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "holds no testcase" in out, out


def test_unparseable_junit_is_could_not_look(tmp_path, capsys) -> None:
    root = _legs(tmp_path / "d")
    (root / "junit-2.xml").write_text("<testsuites><", encoding="utf-8")
    code, out = _check(root, capsys)
    assert code == 2, out
    assert "cannot read the junit XML" in out, out


def test_a_directory_that_does_not_exist_is_could_not_look(tmp_path, capsys) -> None:
    code, out = _check(tmp_path / "nope", capsys)
    assert code == 2, out
    assert "is not a directory" in out, out


@pytest.mark.parametrize(
    "argv",
    [
        ["x"],
        ["x", "--dir", "d"],
        ["x", "--of", "2"],
        ["x", "--dir", "d", "--of", "0"],
        ["x", "--dir", "d", "--of", "two"],
        ["x", "--dir", "d", "--of", "2", "--extra", "1"],
        ["x", "--dir"],
    ],
)
def test_a_bad_command_line_is_could_not_look(argv: list[str], capsys) -> None:
    assert shards.main(argv) == 2
    assert "could not look" in capsys.readouterr().out
