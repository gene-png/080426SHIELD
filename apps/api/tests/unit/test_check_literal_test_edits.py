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

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_literal_test_edits as lit
import yaml

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


def test_a_docstring_is_not_an_expected_value_and_is_refused(tmp_path, capsys) -> None:
    # Item 1 is "expected literals on existing assertion lines". A docstring is neither.
    old = 'def test_a():\n    """50 percent."""\n    assert f() == 1\n'
    new = old.replace("50 percent", "a third")
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out, out


def test_an_f_string_text_is_an_expected_value_but_its_expression_is_not(tmp_path, capsys) -> None:
    old = 'def test_a(t):\n    assert label(t) == f"tier {t}" and label(2) == f"tier {2}"\n'
    new = old.replace("tier {t}", "level {t}")
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: new}, capsys)
    assert code == 0, out
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: old.replace("{2}", "{3}")}, capsys)
    assert code == 1, out


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
    # Named, so the advisor audit sees what was NOT judged.
    assert "not judged (not a test file): apps/api/app/dash.py" in out, out


@pytest.mark.parametrize(
    "path",
    [
        "apps/api/pyproject.toml",
        "apps/api/pytest.ini",
        "apps/api/.pytest.ini",
        "apps/api/pytest.toml",
        "apps/api/.pytest.toml",
        "apps/web/vitest.workspace.ts",
        "apps/web/src/app/admin/clients/fake-api.testkit.ts",
        "apps/web/src/components/__mocks__/api.ts",
        "apps/web/src/test-utils/render.tsx",
        "apps/web/src/testing/server.ts",
        "apps/web/src/lib/fixtures/clients.ts",
        ".github/ci-selection-baseline.json",
        ".github/e2e-env-gate-exemptions.json",
        "pnpm-lock.yaml",
        "apps/api/scripts/__init__.py",
        "apps/api/scripts/seed_demo.py",
        "apps/web/vitest.config.ts",
        "apps/web/playwright.config.ts",
        ".github/workflows/ci.yml",
        "apps/api/scripts/check_plan_totals.py",
        "apps/api/scripts/shard_deselect.py",
        "apps/api/scripts/preflight_plan.py",
        "apps/api/scripts/mutation_sweep.py",
        "apps/api/scripts/leave_row_oracle.py",
        "apps/web/package.json",
        "package.json",
        "tests/gates/prettier_hook.sh",
        "scripts/red-on-revert.sh",
        "apps/api/setup.cfg",
        "apps/api/tox.ini",
        "apps/api/conftest.py",
        "apps/web/vitest.setup.ts",
    ],
)
def test_a_file_that_decides_what_tests_run_is_refused(tmp_path, capsys, path) -> None:
    # A literal-only test edit plus an `addopts = --deselect ...` would pass a checker
    # that judged test files only. These are not "the behavior change".
    new = _edit(OLD, "== 50.0", "== 33.3")
    code, out = _check(
        tmp_path, {TEST_PATH: OLD, path: "a = 1\n"}, {TEST_PATH: new, path: "a = 2\n"}, capsys
    )
    assert code == 1, out
    assert f"{path}: a file that decides what tests run" in out, out


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
    assert "is not an expected value in an `assert`" in out, out


@pytest.mark.parametrize(
    ("body", "old", "new"),
    [
        # Each is a literal-only edit that neuters a test; the review of #1469 built them.
        (
            "import pytest\n\n\ndef test_x():\n    pytest.importorskip('xdist', reason='r')\n",
            "'xdist'",
            "'xdistx'",
        ),
        (
            "@pytest.mark.skipif(sys.version_info < (3, 0), reason='r')\ndef test_x():\n    assert f() == 1\n",
            "(3, 0)",
            "(3, 99)",
        ),
        (
            "def test_x():\n    for i in range(10):\n        assert f(i) == 1\n",
            "range(10)",
            "range(0)",
        ),
        ("def test_x():\n    assert rows[:5] == [1]\n", "[:5]", "[:0]"),
        ("def test_x():\n    assert 'passed' not in out\n", "'passed'", "'never-printed'"),
        ("def test_x():\n    assert code != 0\n", "!= 0", "!= 7"),
        ("def test_x():\n    assert elapsed < 10\n", "< 10", "< 1e999"),
        ("def test_x():\n    assert v == pytest.approx(1, abs=1e-9)\n", "1e-9", "1e9"),
        (
            "def test_x():\n    with pytest.raises(ValueError, match='cannot read'):\n        f()\n",
            "'cannot read'",
            "'.'",
        ),
        ("def test_x():\n    assert 'of 3 gaps' in blob\n", "'of 3 gaps'", "' '"),
        ("def test_x():\n    assert f(2) == 4\n", "f(2)", "f(3)"),
    ],
    ids=[
        "importorskip",
        "skipif",
        "range",
        "slice",
        "not-in",
        "not-equal",
        "bound",
        "tolerance",
        "match",
        "blank-needle",
        "call-argument",
    ],
)
def test_a_literal_edit_that_is_not_an_expected_value_is_refused(
    tmp_path, capsys, body, old, new
) -> None:
    assert body.count(old) == 1, old
    code, out = _check(tmp_path, {TEST_PATH: body}, {TEST_PATH: body.replace(old, new)}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out or "made empty or blank" in out, out


def test_a_value_inside_a_parametrize_list_is_refused_even_on_another_line(
    tmp_path, capsys
) -> None:
    # Dropping a case by editing a value, with the ids line untouched.
    old = (
        "@pytest.mark.parametrize(\n"
        '    ("index", "of"),\n'
        '    [(None, "2"), ("0", "2"), ("", "2")],\n'
        '    ids=["a", "b", "c"],\n'
        ")\ndef test_x(index, of):\n    assert index != of\n"
    )
    new = old.replace('("", "2")', '("0", "2")')
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out, out


def test_a_triple_quoted_source_string_cannot_be_edited(tmp_path, capsys) -> None:
    old = 'SRC = """\ndef test_two(): pass\n"""\n\n\ndef test_x():\n    assert SRC\n'
    new = old.replace("test_two(): pass", "test_two(): 1/0")
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: new}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out, out


def test_a_string_made_empty_is_refused_because_an_empty_needle_always_matches(
    tmp_path, capsys
) -> None:
    code, out = _check(tmp_path, {TEST_PATH: OLD}, {TEST_PATH: _edit(OLD, '"50%"', '""')}, capsys)
    assert code == 1, out
    assert "made empty or blank" in out, out


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


# --- the CI job: a near-miss declaration must not turn into a green that checked nothing ---


def _job_step() -> str:
    from tests._paths import find_workflows_dir

    wf = find_workflows_dir(Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    job = yaml.safe_load((wf / "audit-gate.yml").read_text(encoding="utf-8"))["jobs"]
    (step,) = [s for s in job["literal-only-test-edits"]["steps"] if "run" in s]
    run = step["run"]
    line = [
        ln
        for ln in run.splitlines()
        if ln.lstrip().startswith("python apps/api/scripts/check_literal")
    ]
    assert len(line) == 1, line
    return run.replace(line[0], "echo CHECKER-RAN")


def _run_step(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash here")
    env = {**os.environ, "PR_BODY": body, "RUNNER_TEMP": str(tmp_path)}
    return subprocess.run(  # noqa: S603 - the workflow's own step, fixture inputs
        [bash, "--noprofile", "--norc", "-e", "-c", _job_step()],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_the_job_runs_the_checker_for_the_exact_declaration(tmp_path) -> None:
    proc = _run_step(tmp_path, "Summary\nsomething\nLiteral-only-test-edits: yes\nmore\n")
    assert proc.returncode == 0 and "CHECKER-RAN" in proc.stdout, proc.stdout + proc.stderr


def test_the_job_says_not_run_when_the_body_never_mentions_it(tmp_path) -> None:
    proc = _run_step(tmp_path, "A PR body.\nIt has no declaration.\n")
    assert proc.returncode == 0 and "NOT RUN" in proc.stdout, proc.stdout
    assert "CHECKER-RAN" not in proc.stdout


def test_a_prose_mention_exits_2_unless_the_exact_line_is_also_there(tmp_path) -> None:
    # Any mention of the phrase without the exact line is red (reword the prose): a quoted
    # declaration is the near miss the first versions greened.
    prose = "The job runs for a body with `Literal-only-test-edits: yes` on its own line.\n"
    proc = _run_step(tmp_path, prose)
    assert proc.returncode == 2 and "CHECKER-RAN" not in proc.stdout, proc.stdout + proc.stderr
    proc = _run_step(tmp_path, prose + "Literal-only-test-edits: yes\n")
    assert proc.returncode == 0 and "CHECKER-RAN" in proc.stdout, proc.stdout + proc.stderr


@pytest.mark.parametrize(
    "line",
    [
        "- Literal-only-test-edits: yes",
        "Literal-only-test-edits: Yes",
        "**Literal-only-test-edits:** yes",
        "Literal-only-test-edits: yes.",
        "literal-only-test-edits: yes",
        "> Literal-only-test-edits: yes",
        "Literal-only-test-edits : yes",
        "Literal-only-test-edit: yes",
        "1. Literal-only-test-edits: yes",
        "- [x] Literal-only-test-edits: yes",
        "| Literal-only-test-edits | yes |",
        "Literal only test edits: yes",
        "Literal_only_test_edits: yes",
        "Literal only  test edits: yes",
        "Literal-only test	 edits: yes",
        "Literal only test edits: yes",
        "Literal‑only‑test‑edits: yes",
        "Declaration: Literal-only-test-edits: yes",
    ],
)
def test_a_near_miss_declaration_fails_the_job_and_never_greens_silently(tmp_path, line) -> None:
    # The first version exited 0 "NOT RUN" for all of these: a green check named for the
    # checker that never ran, over a PR whose author believed they had declared.
    proc = _run_step(tmp_path, f"Body\n{line}\n")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "CHECKER-RAN" not in proc.stdout and "NOT RUN" not in proc.stdout


# --- review round 2 --------------------------------------------------------------------


def test_a_non_ascii_character_before_a_literal_does_not_shift_the_judgement(
    tmp_path, capsys
) -> None:
    # ast columns are UTF-8 BYTES and tokenize columns are characters; the `1` below sits
    # inside the string's BYTE span if the columns are compared unconverted.
    old = 'def test_x():\n    assert "' + "é" * 10 + '" == f(1)\n'
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: old.replace("f(1)", "f(2)")}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out, out


def test_an_expected_value_after_non_ascii_text_is_still_an_expected_value(
    tmp_path, capsys
) -> None:
    old = 'def test_x():\n    assert f("é") == "a"\n'
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: old.replace('"a"', '"b"')}, capsys)
    assert code == 0, out


def test_a_form_feed_in_a_comment_does_not_move_the_line_a_literal_is_judged_against(
    tmp_path, capsys
) -> None:
    # str.splitlines splits on a form feed and the tokenizer does not: the call argument below
    # would be judged against the comment line and pass.
    old = (
        "def test_x():\n    # a"
        + chr(12)
        + "x" * 20
        + '\n    assert "expected-output-string" == run(limit=10)\n'
    )
    code, out = _check(tmp_path, {TEST_PATH: old}, {TEST_PATH: old.replace("10", "0")}, capsys)
    assert code == 1, out
    assert "is not an expected value in an `assert`" in out, out
