"""The checker behind the advisor's mechanical pre-approval of literal-only test edits.

#736 6234238148 item 1: a test edit that changes only expected literals on existing
assertion lines, following a behaviour change the advisor already approved, may
merge without waiting when a checker passes. It must fail closed and must refuse:
any removed assertion; any changed assertion subject, matcher or operator; any new,
renamed or deleted test; any change outside literals; a literal edit with no
approved behaviour change cited.

Every refusal has its own test, and the clean cases are here so that "refuses" is
not one broken path. The trees mode (`--old-tree` / `--new-tree`) is what these and
the fixtures use; the git mode is exercised against a real throwaway repository,
and skipped where there is no git (the api container has none).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_literal_test_edits as lit

pytestmark = pytest.mark.unit

TEST_PATH = "apps/api/tests/unit/test_dash.py"
CITED = "Approved-behavior-comment: 6229125629\n"

OLD = """\
import pytest

pytestmark = pytest.mark.unit


def test_percentage():
    result = compute(2, 4)
    assert result.pct == 50.0
    assert "50%" in result.text


@pytest.mark.parametrize("tier", [1, 2, 3], ids=["one", "two", "three"])
def test_tiers(tier):
    assert label(tier) == f"tier {tier}"
"""


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8", newline="\n")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _check(
    tmp_path: Path,
    old: dict[str, str],
    new: dict[str, str],
    capsys,
    body: str | None = CITED,
) -> tuple[int, str]:
    args = ["check_literal_test_edits", "--old-tree", str(_tree(tmp_path / "old", old))]
    args += ["--new-tree", str(_tree(tmp_path / "new", new))]
    if body is not None:
        (tmp_path / "body.md").write_text(body, encoding="utf-8")
        args += ["--body", str(tmp_path / "body.md")]
    code = lit.main(args)
    return code, capsys.readouterr().out


def _edit(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


# --- clean ------------------------------------------------------------------------


def test_expected_numbers_and_strings_changed_on_existing_lines_is_clean(tmp_path, capsys) -> None:
    new = _edit(_edit(OLD, "== 50.0", "== 33.3"), '"50%"', '"33.3%"')
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys)
    assert code == 0, out
    assert "clean -- 2 literal edit(s) in 1 test file(s)" in out, out
    assert f"{TEST_PATH}:8: 50.0 -> 33.3" in out, out  # the audit trail names each edit


def test_a_docstring_is_a_literal_and_may_change(tmp_path, capsys) -> None:
    old = 'def test_a():\n    """50 percent."""\n    assert f() == 1\n'
    code, out = _check(
        tmp_path,
        {TEST_PATH: old},
        {TEST_PATH: _edit(old, "50 percent", "a third")},
        capsys,
    )
    assert code == 0, out


def test_a_reflowed_bracket_is_not_a_change_outside_literals(tmp_path, capsys) -> None:
    old = "def test_a():\n    assert f(\n        1,\n        2,\n    ) == 3\n"
    new = "def test_a():\n    assert f(1, 2,) == 4\n"
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: new}, capsys)
    assert code == 0, out


def test_a_file_that_is_not_a_test_is_the_behaviour_change_and_is_not_judged(
    tmp_path, capsys
) -> None:
    new = _edit(OLD, "== 50.0", "== 33.3")
    code, out = _check(
        tmp_path,
        {TEST_PATH: OLD, "apps/api/app/dash.py": "X = 1\n"},
        {TEST_PATH: new, "apps/api/app/dash.py": "X = 2\n"},
        capsys,
    )
    assert code == 0, out
    assert "apps/api/app/dash.py" not in out, out


# --- refused: each of the advisor's list --------------------------------------------


def test_a_removed_assertion_is_refused(tmp_path, capsys) -> None:
    new = _edit(OLD, '    assert "50%" in result.text\n', "")
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert f"{TEST_PATH}: a change outside literals" in out, out


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("result.pct == 50.0", "result.pct >= 50.0"),
        ("result.pct == 50.0", "result.pct != 50.0"),
        ("result.pct == 50.0", "result.rate == 50.0"),
        ("assert result.pct == 50.0", "assert result.pct == 50.0 or True"),
        ('"50%" in result.text', '"50%" not in result.text'),
        ("compute(2, 4)", "compute(2, 4, strict=False)"),
    ],
    ids=["matcher", "operator", "subject", "added-or", "negated", "added-argument"],
)
def test_a_changed_subject_matcher_or_operator_is_refused(tmp_path, capsys, old, new) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, old, new)}, capsys)
    assert code == 1, out
    assert "a change outside literals" in out, out


def test_a_renamed_test_is_refused(tmp_path, capsys) -> None:
    new = _edit(OLD, "def test_percentage", "def test_share")
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert "a change outside literals" in out, out


def test_a_new_test_in_an_existing_file_is_refused(tmp_path, capsys) -> None:
    new = OLD + "\n\ndef test_extra():\n    assert f() == 1\n"
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert "a change outside literals" in out, out


def test_a_new_test_file_is_refused(tmp_path, capsys) -> None:
    code, out = _check(
        tmp_path, {TEST_PATH: OLD}, {TEST_PATH: OLD, "apps/api/tests/unit/test_new.py": OLD}, capsys
    )
    assert code == 1, out
    assert "apps/api/tests/unit/test_new.py: a new test file" in out, out


def test_a_deleted_test_file_is_refused(tmp_path, capsys) -> None:
    other = "apps/api/tests/unit/test_other.py"
    new = _edit(OLD, "== 50.0", "== 33.3")
    code, out = _check(tmp_path, {TEST_PATH: OLD, other: OLD}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert f"{other}: a deleted test file" in out, out


def test_a_comment_edit_is_a_change_outside_literals(tmp_path, capsys) -> None:
    old = "def test_a():\n    # the old reason\n    assert f() == 1\n"
    code, out = _check(
        tmp_path, {TEST_PATH: old}, {TEST_PATH: _edit(old, "old reason", "new reason")}, capsys
    )
    assert code == 1, out
    assert "a change outside literals" in out, out


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('ids=["one", "two", "three"]', 'ids=["uno", "two", "three"]'),
        ('"tier", [1, 2, 3]', '"level", [1, 2, 3]'),
    ],
    ids=["param-ids", "param-names"],
)
def test_a_literal_that_renames_a_test_or_its_parameter_is_refused(
    tmp_path, capsys, old, new
) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, old, new)}, capsys)
    assert code == 1, out
    assert "renames a parametrized test" in out, out


def test_a_string_made_empty_is_refused_because_an_empty_needle_always_matches(
    tmp_path, capsys
) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, '"50%"', '""')}, capsys)
    assert code == 1, out
    assert "made empty" in out, out


@pytest.mark.parametrize(
    ("old", "new"),
    [("== 50.0", "== None"), ("== 50.0", "== True"), ("== 50.0", '== "50"')],
    ids=["none", "bool", "number-to-string"],
)
def test_a_literal_of_another_kind_is_not_a_literal_edit(tmp_path, capsys, old, new) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, old, new)}, capsys)
    assert code == 1, out


def test_a_test_file_that_is_not_python_is_refused_as_not_machine_checkable(
    tmp_path, capsys
) -> None:
    path = "apps/web/src/components/x.test.tsx"
    code, out = _check(
        tmp_path, {path: 'expect(x).toBe("a");\n'}, {path: 'expect(x).toBe("b");\n'}, capsys
    )
    assert code == 1, out
    assert f"{path}: not machine-checkable" in out, out


def test_no_approved_behaviour_change_cited_is_refused(tmp_path, capsys) -> None:
    new = _edit(OLD, "== 50.0", "== 33.3")
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys, body="No marker.\n")
    assert code == 1, out
    assert "no approved behavior change is cited" in out, out


@pytest.mark.parametrize(
    "body",
    [
        "Approved-behavior-comment: 12\n",
        "Approved-behavior-comment: abc\n",
        "approved-behavior-comment: 6229125629 extra\n",
        "> Approved-behavior-comment: 6229125629\n",
    ],
    ids=["too-short", "not-digits", "trailing-text", "quoted"],
)
def test_a_malformed_citation_is_not_a_citation(tmp_path, capsys, body) -> None:
    new = _edit(OLD, "== 50.0", "== 33.3")
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: new}, capsys, body=body)
    assert code == 1, out
    assert "no approved behavior change is cited" in out, out


# --- could not look: never clean on an empty or unreadable read -----------------------


def test_nothing_changed_is_could_not_look_not_clean(tmp_path, capsys) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: OLD}, capsys)
    assert code == 2, out
    assert "no test file differs" in out, out


def test_only_non_test_files_changing_is_could_not_look_not_clean(tmp_path, capsys) -> None:
    code, out = _check(
        tmp_path, {"apps/api/app/x.py": "A = 1\n"}, {"apps/api/app/x.py": "A = 2\n"}, capsys
    )
    assert code == 2, out
    assert "no test file differs" in out, out


def test_a_test_file_that_does_not_parse_is_could_not_look(tmp_path, capsys) -> None:
    code, out = _check(
        tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, "def test_percentage", "def (")}, capsys
    )
    assert code == 2, out
    assert "could not look" in out, out


def test_a_missing_body_file_is_could_not_look(tmp_path, capsys) -> None:
    new = _edit(OLD, "== 50.0", "== 33.3")
    args = ["x", "--old-tree", str(_tree(tmp_path / "old", {TEST_PATH: OLD}))]
    args += ["--new-tree", str(_tree(tmp_path / "new", {TEST_PATH: new}))]
    args += ["--body", str(tmp_path / "nope.md")]
    assert lit.main(args) == 2
    assert "cannot read the PR body" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["x"],
        ["x", "--body", "b"],
        ["x", "--old-tree", "a", "--body", "b"],
        ["x", "--old-tree", "a", "--new-tree", "b", "--base", "c", "--body", "b"],
        ["x", "--base", "a", "--body", "b"],
        ["x", "--old-tree", "a", "--new-tree", "b", "--body", "b", "--extra", "1"],
        ["x", "--old-tree"],
    ],
)
def test_a_bad_command_line_is_could_not_look(argv, capsys) -> None:
    assert lit.main(argv) == 2
    assert "could not look" in capsys.readouterr().out


def test_a_missing_tree_is_could_not_look(tmp_path, capsys) -> None:
    (tmp_path / "body.md").write_text(CITED, encoding="utf-8")
    argv = ["x", "--old-tree", str(tmp_path / "a"), "--new-tree", str(tmp_path / "b")]
    assert lit.main([*argv, "--body", str(tmp_path / "body.md")]) == 2
    assert "is not a directory" in capsys.readouterr().out


# --- the git mode, against a real repository ------------------------------------------


_GIT = shutil.which("git") or "git"  # resolved once, so the argv below is not a partial path


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, a throwaway repository
        [_GIT, "-C", str(repo), "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    if shutil.which("git") is None:
        pytest.skip(
            "no git here (the api image has none); CI's python job runs on a runner that does"
        )
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    path = root / TEST_PATH
    path.parent.mkdir(parents=True)
    path.write_text(OLD, encoding="utf-8", newline="\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "checkout", "-q", "-b", "pr")
    return root


def _run_git(repo: Path, tmp_path: Path, capsys, body: str = CITED) -> tuple[int, str]:
    (tmp_path / "gbody.md").write_text(body, encoding="utf-8")
    code = lit.main(
        [
            "x",
            "--repo",
            str(repo),
            "--base",
            "main",
            "--head",
            "pr",
            "--body",
            str(tmp_path / "gbody.md"),
        ]
    )
    return code, capsys.readouterr().out


def test_git_mode_reads_the_merge_base_so_main_moving_is_not_a_change(
    repo: Path, tmp_path: Path, capsys
) -> None:
    _git(repo, "checkout", "-q", "main")
    (repo / "apps/api/tests/unit/test_main_only.py").write_text("def test_m():\n    assert 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main moves")
    _git(repo, "checkout", "-q", "pr")
    (repo / TEST_PATH).write_text(_edit(OLD, "== 50.0", "== 33.3"), encoding="utf-8", newline="\n")
    _git(repo, "commit", "-q", "-am", "pr")
    code, out = _run_git(repo, tmp_path, capsys)
    assert code == 0, out
    assert "test_main_only" not in out, out


def test_git_mode_refuses_a_removed_assertion(repo: Path, tmp_path: Path, capsys) -> None:
    (repo / TEST_PATH).write_text(
        _edit(OLD, '    assert "50%" in result.text\n', ""), encoding="utf-8", newline="\n"
    )
    _git(repo, "commit", "-q", "-am", "pr")
    code, out = _run_git(repo, tmp_path, capsys)
    assert code == 1, out


def test_git_mode_refuses_a_new_test_file(repo: Path, tmp_path: Path, capsys) -> None:
    (repo / "apps/api/tests/unit/test_new.py").write_text(OLD, encoding="utf-8", newline="\n")
    (repo / TEST_PATH).write_text(_edit(OLD, "== 50.0", "== 33.3"), encoding="utf-8", newline="\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "pr")
    code, out = _run_git(repo, tmp_path, capsys)
    assert code == 1, out
    assert "a new test file" in out, out


def test_git_mode_with_no_diff_is_could_not_look(repo: Path, tmp_path: Path, capsys) -> None:
    code, out = _run_git(repo, tmp_path, capsys)
    assert code == 2, out


def test_git_mode_with_an_unknown_ref_is_could_not_look(repo: Path, tmp_path: Path, capsys) -> None:
    (tmp_path / "gbody.md").write_text(CITED, encoding="utf-8")
    code = lit.main(
        [
            "x",
            "--repo",
            str(repo),
            "--base",
            "nope",
            "--head",
            "pr",
            "--body",
            str(tmp_path / "gbody.md"),
        ]
    )
    assert code == 2
    assert "could not look" in capsys.readouterr().out
