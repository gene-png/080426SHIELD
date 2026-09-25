"""The CI-selection gate (#540): a test that exists but CI never runs is a finding.

Written BEFORE the gate. Both instances turned up in one day: the #535/#536
leak tests shipped unmarked, so CI's `pytest -m unit tests/unit` would have
selected 0 of their 61 tests, and local runs that named the file directly
passed; and #483, Playwright specs gated on environment variables no workflow
sets. `check_test_integrity.py` catches tests that cannot fail; nothing caught
tests that never run.
"""

from __future__ import annotations

import json
import pathlib
import textwrap
from pathlib import Path

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py for why a
# bare `from scripts import ...` sorts differently in the container and in CI.
import scripts.check_ci_selection as gate
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    """A throwaway pytest project with the `unit` marker registered."""
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8")
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body), encoding="utf-8")
    return tmp_path


MARKED = """
    import pytest
    pytestmark = pytest.mark.unit
    def test_a(): pass
    def test_b(): pass
"""
UNMARKED = """
    def test_c(): pass
    def test_d(): pass
    def test_e(): pass
"""
U = "tests/unit/test_u.py"


def _baseline(tmp_path: Path, entries: dict) -> Path:
    p = tmp_path / "baseline.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def _run(root: Path, base: Path, capsys) -> tuple[int, str]:
    code = gate.main(["gate", "--root", str(root), "--baseline", str(base)])
    return code, capsys.readouterr().out


# --- the verdict ------------------------------------------------------------------


def test_an_unmarked_test_is_a_finding_naming_it(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED, U: UNMARKED})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert f"{U}::test_c: CI never runs it" in out, out


def test_all_marked_is_clean_and_says_what_it_counted(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "CI selects 2 of 2" in out, out


def _entry(*names: str) -> dict:
    return {U: {"reason": "#500: unmarked", "tests": [f"{U}::{n}" for n in names]}}


def test_baselined_tests_pass_and_are_still_printed(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED, U: UNMARKED})
    code, out = _run(root, _baseline(tmp_path, _entry("test_c", "test_d", "test_e")), capsys)
    assert code == 0, out
    assert U in out and "#500: unmarked" in out, out


def test_a_new_never_run_test_cannot_hide_behind_a_baselined_count(tmp_path, capsys) -> None:
    # Review of e8424dd: with a per-file COUNT, marking one old test and adding
    # one new unmarked test kept the count and passed. Node ids name each test.
    root = _project(tmp_path, {U: "def test_c(): pass\ndef test_new(): pass\n"})
    code, out = _run(root, _baseline(tmp_path, _entry("test_c", "test_d")), capsys)
    assert code == 1, out
    assert f"{U}::test_new: CI never runs it" in out, out


def test_a_baselined_test_now_gone_is_a_finding_so_the_backlog_ratchets(tmp_path, capsys) -> None:
    root = _project(tmp_path, {U: "def test_c(): pass\n"})
    code, out = _run(root, _baseline(tmp_path, _entry("test_c", "test_gone")), capsys)
    assert code == 1, out
    assert f"{U}::test_gone: baselined, but no longer exists" in out, out


def test_a_baselined_test_now_selected_is_a_finding(tmp_path, capsys) -> None:
    marked_c = "import pytest\npytestmark = pytest.mark.unit\ndef test_c(): pass\n"
    root = _project(tmp_path, {U: marked_c})
    code, out = _run(root, _baseline(tmp_path, _entry("test_c")), capsys)
    assert code == 1, out
    assert f"{U}::test_c: baselined, but now selected" in out, out


@pytest.mark.parametrize(
    "entry",
    [
        {U: {"reason": "  ", "tests": [f"{U}::test_c"]}},
        {U: {"reason": "r", "tests": []}},
        {U: {"reason": "r", "tests": [True]}},
        {U: {"reason": "r", "tests": ["tests/unit/other.py::test_c"]}},
        {U: {"reason": "r", "unselected": 3}},
    ],
    ids=["blank-reason", "empty-list", "non-string", "wrong-file", "old-count-shape"],
)
def test_a_malformed_baseline_entry_is_refused(tmp_path, capsys, entry: dict) -> None:
    root = _project(tmp_path, {U: UNMARKED})
    code, out = _run(root, _baseline(tmp_path, entry), capsys)
    assert code == 2, out


# --- could not look: never clean (D-090) -------------------------------------------


def test_the_wrong_directory_is_could_not_look_not_clean(tmp_path, capsys) -> None:
    code, out = _run(tmp_path, _baseline(tmp_path, {}), capsys)
    assert code == 2, out
    # The BRANCH, not only the code: exit 2 is also what pytest's own failure
    # to collect produces, so a code-only check passes with this guard deleted.
    assert "does not exist -- wrong directory?" in out, out


def test_an_empty_collection_is_could_not_look(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/__init__.py": ""})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 2, out


def test_a_missing_baseline_is_could_not_look(tmp_path, capsys) -> None:
    root = _project(tmp_path, {"tests/unit/test_m.py": MARKED})
    code, out = _run(root, tmp_path / "absent.json", capsys)
    assert code == 2, out


def test_an_unknown_argument_is_could_not_look(capsys) -> None:
    assert gate.main(["gate", "--baselin", "x"]) == 2


# --- the selector is CI's EXACT line, not a substring that can drift -----------


def test_the_gates_selector_is_exactly_the_one_ci_runs() -> None:
    # Review of e8424dd: a substring pin stayed green if CI appended `-k` or
    # `--deselect`, narrowing CI while the gate certified the wider set. Parse
    # the workflow; require the ONE pytest-over-tests/unit step to be equal.
    #
    # Skipped ONLY with no `.github/workflows` above this file at all -- the
    # api container, which mounts apps/api alone. A checkout that has the
    # directory but not ci.yml fails loudly below (the pattern
    # test_audit_gate_collects_only_this_branch.py records).
    if _WORKFLOWS_DIR is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    ci = yaml.safe_load((_WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8"))
    runs = [
        str(step.get("run", "")).strip()
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
        if str(step.get("run", "")).strip().startswith("pytest ")
        and "tests/unit" in str(step.get("run", ""))
    ]
    assert runs == [f"pytest {' '.join(gate.CI_SELECTOR)}"], runs


# --- config is pytest's to apply, wherever it lives (reviews of 324dc15, adaf082) --


def _with_ini_addopts(root: Path, addopts: str) -> None:
    ini = root / "pytest.ini"
    ini.write_text(ini.read_text(encoding="utf-8") + f"addopts = {addopts}\n", encoding="utf-8")


M = "tests/unit/test_m.py"


@pytest.mark.parametrize(
    ("addopts", "dropped"),
    [
        (f"--deselect {M}::test_a", ["test_a"]),
        ("-k 'not test_b'", ["test_b"]),
        (f"--ignore={M}", ["test_a", "test_b"]),
    ],
    ids=["deselect", "k-filter", "ignore"],
)
def test_selecting_addopts_narrow_the_selected_set_and_are_findings(
    tmp_path, capsys, addopts: str, dropped: list[str]
) -> None:
    root = _project(tmp_path, {M: MARKED})
    _with_ini_addopts(root, addopts)
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    for name in dropped:
        assert f"{M}::{name}: CI never runs it" in out, out


def test_pytest_addopts_in_the_environment_narrows_only_the_selected_set(
    tmp_path, capsys, monkeypatch
) -> None:
    # Review of 701f032: `-o addopts=` does not reach PYTEST_ADDOPTS, so the
    # "everything" run inherited the same --deselect and the gate stayed clean.
    root = _project(tmp_path, {M: MARKED})
    monkeypatch.setenv("PYTEST_ADDOPTS", f"--deselect {M}::test_a")
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert f"{M}::test_a: CI never runs it" in out, out


def test_a_config_file_nearer_the_tests_is_the_one_pytest_applies(tmp_path, capsys) -> None:
    # Review of adaf082: pytest walks up from `tests/unit` and the first config
    # file wins, so a `tests/pytest.ini` beats the root one. A gate that read
    # named files at the root would certify the wider set.
    root = _project(tmp_path, {M: MARKED})
    (root / "tests" / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    unit: fast\naddopts = -k 'not test_a'\n", encoding="utf-8"
    )
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    # That file is pytest's rootdir now, so node ids are relative to `tests/`.
    assert "  unit/test_m.py::test_a: CI never runs it" in out, out


@pytest.mark.skipif(
    int(pytest.__version__.split(".")[0]) < 9, reason="native [tool.pytest] is pytest 9+"
)
def test_native_toml_addopts_are_applied(tmp_path, capsys) -> None:
    # Review of adaf082: `[tool.pytest]` (not `ini_options`) was unread.
    (tmp_path / "tests" / "unit").mkdir(parents=True)
    (tmp_path / M).write_text(textwrap.dedent(MARKED), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest]\nmarkers = ["unit: fast"]\n'
        f'addopts = ["-q", "--deselect", "{M}::test_b"]\n',
        encoding="utf-8",
    )
    code, out = _run(tmp_path, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert f"{M}::test_b: CI never runs it" in out, out


def test_reporting_only_addopts_are_clean(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED})
    _with_ini_addopts(root, "-ra -q")
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "CI selects 2 of 2" in out, out


def test_a_broken_conftest_is_could_not_look(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED, "tests/unit/conftest.py": "raise RuntimeError('x')\n"})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 2, out


# --- #543: a file that removes itself at collection is a finding, not a smaller denominator --

SKIPPED_MODULE = """
    import pytest
    pytest.skip("not here", allow_module_level=True)
    pytestmark = pytest.mark.unit
    def test_x(): pass
"""
S = "tests/unit/test_skipped.py"


def test_a_file_that_skips_at_module_level_is_a_finding(tmp_path, capsys) -> None:
    # It is absent from BOTH collections, so the node-id comparison could never
    # see it: "CI selects 2 of 2" read clean over a file CI never runs (#543).
    root = _project(tmp_path, {M: MARKED, S: SKIPPED_MODULE})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert f"{S}: never collected" in out, out


def test_a_file_removed_by_collect_ignore_is_a_finding(tmp_path, capsys) -> None:
    root = _project(
        tmp_path,
        {
            M: MARKED,
            "tests/unit/test_ignored.py": MARKED,
            "tests/unit/conftest.py": 'collect_ignore = ["test_ignored.py"]\n',
        },
    )
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert "tests/unit/test_ignored.py: never collected" in out, out


def test_an_uncollected_file_can_be_baselined_with_a_reason(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED, S: SKIPPED_MODULE})
    base = _baseline(tmp_path, {S: {"reason": "#999: needs a service", "uncollected_file": True}})
    code, out = _run(root, base, capsys)
    assert code == 0, out
    assert S in out and "#999: needs a service" in out, out


def test_a_baselined_uncollected_file_that_now_collects_is_a_finding(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED, S: MARKED})
    base = _baseline(tmp_path, {S: {"reason": "#999", "uncollected_file": True}})
    code, out = _run(root, base, capsys)
    assert code == 1, out
    assert f"{S}: baselined as never collected, but now collected" in out, out


def test_a_baselined_uncollected_file_that_is_gone_is_a_finding(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED})
    base = _baseline(tmp_path, {S: {"reason": "#999", "uncollected_file": True}})
    code, out = _run(root, base, capsys)
    assert code == 1, out
    assert f"{S}: baselined as never collected, but no longer exists" in out, out


@pytest.mark.parametrize(
    "entry",
    [
        {S: {"reason": " ", "uncollected_file": True}},
        {S: {"reason": "r", "uncollected_file": "yes"}},
        {S: {"reason": "r", "uncollected_file": True, "tests": [f"{S}::test_x"]}},
    ],
    ids=["blank-reason", "not-true", "both-shapes"],
)
def test_a_malformed_uncollected_entry_is_refused(tmp_path, capsys, entry: dict) -> None:
    root = _project(tmp_path, {M: MARKED, S: SKIPPED_MODULE})
    code, out = _run(root, _baseline(tmp_path, entry), capsys)
    assert code == 2, out


def test_the_clean_line_counts_the_files_it_compared(tmp_path, capsys) -> None:
    root = _project(tmp_path, {M: MARKED, "tests/unit/sub/test_n.py": MARKED})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "2 of 2 test files on disk collected" in out, out


# --- #544: the gate's step must see CI's pytest step's environment -----------------


def _ci_steps() -> tuple[str, dict, dict]:
    """(job name, the pytest -m unit step, the check_ci_selection step)."""
    ci = yaml.safe_load((_WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8"))
    found = []
    for name, job in ci["jobs"].items():
        steps = job.get("steps", [])
        pyt = [
            s
            for s in steps
            if str(s.get("run", "")).strip() == f"pytest {' '.join(gate.CI_SELECTOR)}"
        ]
        chk = [s for s in steps if "scripts.check_ci_selection" in str(s.get("run", ""))]
        if pyt or chk:
            found.append((name, pyt, chk))
    assert len(found) == 1, f"the pytest step and the gate step must sit in ONE job: {found}"
    name, pyt, chk = found[0]
    assert len(pyt) == 1 and len(chk) == 1, (pyt, chk)
    return name, pyt[0], chk[0]


def test_the_gate_step_runs_with_the_pytest_steps_environment() -> None:
    # #544: CI_SELECTOR pins the `run:` line only. An `env: PYTEST_ADDOPTS:
    # --deselect ...` on the pytest step would narrow CI and not the gate, with
    # every existing pin green. Job- and workflow-level env reach both steps
    # because they share a job (asserted); step-level env and the working
    # directory must be identical.
    if _WORKFLOWS_DIR is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    _, pyt, chk = _ci_steps()
    assert pyt.get("env") == chk.get("env"), (pyt.get("env"), chk.get("env"))
    assert pyt.get("working-directory") == chk.get("working-directory")


def test_files_match_when_pytests_rootdir_is_below_the_root(tmp_path, capsys) -> None:
    # A `tests/pytest.ini` makes node ids read `unit/test_m.py`, not
    # `tests/unit/test_m.py`. An equality match would call every file
    # "never collected" in that layout.
    root = _project(tmp_path, {M: MARKED})
    (root / "tests" / "pytest.ini").write_text(
        "[pytest]\nmarkers =\n    unit: fast\n", encoding="utf-8"
    )
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "1 of 1 test files on disk collected" in out, out
