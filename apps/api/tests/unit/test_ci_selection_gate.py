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
    #
    # Sharded since the CI-speed PR (coordinator's verdict): the ONE step running
    # pytest over tests/unit runs it through the shard plugin, and its argv is
    # otherwise exactly CI_SELECTOR -- a `-k` or `--deselect` is still refused.
    runs = [
        str(step.get("run", "")).strip()
        for job in ci["jobs"].values()
        for step in job.get("steps", [])
        if _runs_pytest_over_tests_unit(step)
    ]
    assert runs == [f"python -m pytest -p scripts.pytest_shard {' '.join(gate.CI_SELECTOR)}"], runs


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


# --- The shard pin (replaces #544's adjacency pin; CI sharding, coordinator's verdict) ---
#
# #544 pinned CI's pytest step to sit IMMEDIATELY after this gate's step, in the
# same job, with the same step env, working-directory and shell, so every
# environment reaching one reached the other. Sharding moves pytest into its own
# matrix job, so that cannot hold. What replaces it is stronger: the shards each
# record the node ids they RAN, and the aggregate job fails unless their union
# is exactly the selection this gate certifies, each test once
# (`scripts/shard_partition.py verify`). An environment difference that narrows
# a shard now shows up as a gap in what ran, not as a text difference in a step.
# The pins removed, each with what replaces it:
#   ONE_JOB, NOT_ADJACENT      -> the union check (a narrowed shard is a gap)
#   ENV/WD/SHELL_DIFFERS       -> the union check, plus the shard step's env is
#                                 pinned to exactly the two shard keys
#   EXPRESSION                 -> the union check (it measures what ran, so an
#                                 expression's value cannot hide behind its text)
#   GATE_RUN                   -> kept: the gate step's run is still exact

SHARD_RUN = f"python -m pytest -p scripts.pytest_shard {' '.join(gate.CI_SELECTOR)}"
SHARD_ENV_KEYS = {"PYTEST_SHARD", "PYTEST_SHARD_RECORD"}
REQUIRED_PYTHON = "Python (ruff + black + pytest + bandit)"

ONE_PYTEST_STEP = "exactly one step must run pytest over tests/unit"
PYTEST_RUN = f"the pytest step's run must be exactly `{SHARD_RUN}`"
SHARD_ENV_ONLY = "the pytest step's env must carry exactly PYTEST_SHARD and PYTEST_SHARD_RECORD"
SHARD_MATRIX = "the pytest step's job must be a matrix over shard: [1..N]"
SHARD_SPEC = "PYTEST_SHARD must be `${{ matrix.shard }}/N` with N the matrix length"
GATE_RUN = "the gate step's run must be exactly `python -m scripts.check_ci_selection`"
AGGREGATE = f"the job named `{REQUIRED_PYTHON}` must aggregate the shards"
AGG_ALWAYS = "the aggregate must run `if: always()`"
AGG_VERIFY = "the aggregate must verify the partition with `--of N`"


def _runs_pytest_over_tests_unit(step: dict) -> bool:
    """A step whose run STARTS with pytest and names tests/unit -- the rule this
    pin always used (`startswith("pytest ")`), extended to the shard form. A
    heredoc that runs one named test (the size-gate canary step) is not the
    selection and is not matched. What this cannot see -- pytest invoked some
    other way -- is exactly what the aggregate's union check measures anyway."""
    run = str(step.get("run", "")).strip()
    first = run.splitlines()[0] if run else ""
    return first.startswith(("pytest ", "python -m pytest ")) and "tests/unit" in run


def _pytest_steps(ci: dict) -> list[tuple[str, dict, dict]]:
    return [
        (name, job, step)
        for name, job in ci["jobs"].items()
        for step in job.get("steps", [])
        if _runs_pytest_over_tests_unit(step)
    ]


def shard_pin_violations(ci: dict) -> list[str]:
    """Why CI's sharded unit run could differ from what this gate certifies.
    Empty means the shards are pinned to the gate's selection."""
    found = _pytest_steps(ci)
    if len(found) != 1:
        return [f"{ONE_PYTEST_STEP}: found {[(f[0], f[2].get('run')) for f in found]}"]
    job_name, job, step = found[0]
    out: list[str] = []
    if str(step.get("run", "")).strip() != SHARD_RUN:
        out.append(PYTEST_RUN)
    env = step.get("env") or {}
    if set(env) != SHARD_ENV_KEYS:
        out.append(f"{SHARD_ENV_ONLY}: got {sorted(env)}")
    shards = ((job.get("strategy") or {}).get("matrix") or {}).get("shard")
    n = len(shards) if isinstance(shards, list) else 0
    if not n or shards != list(range(1, n + 1)):
        out.append(f"{SHARD_MATRIX}: got {shards!r}")
    if env.get("PYTEST_SHARD") != f"${{{{ matrix.shard }}}}/{n}":
        out.append(f"{SHARD_SPEC}: got {env.get('PYTEST_SHARD')!r}")
    gates = [
        name
        for name, j in ci["jobs"].items()
        for st in j.get("steps", [])
        if str(st.get("run", "")).strip() == "python -m scripts.check_ci_selection"
    ]
    if len(gates) != 1:
        out.append(f"{GATE_RUN}: found in {gates}")
    aggs = [(name, j) for name, j in ci["jobs"].items() if j.get("name") == REQUIRED_PYTHON]
    if len(aggs) != 1:
        return out + [f"{AGGREGATE}: found {[a[0] for a in aggs]}"]
    _, agg = aggs[0]
    needs = agg.get("needs") or []
    needs = [needs] if isinstance(needs, str) else needs
    if job_name not in needs or (gates and gates[0] not in needs):
        out.append(f"{AGGREGATE}: needs {needs}, not both `{job_name}` and the gate's job")
    if agg.get("if") != "always()":
        out.append(AGG_ALWAYS)
    verify = [
        str(st.get("run", ""))
        for st in agg.get("steps", [])
        if "scripts.shard_partition verify" in str(st.get("run", ""))
    ]
    if len(verify) != 1 or f"--of {n}" not in verify[0]:
        out.append(AGG_VERIFY)
    return out


def test_ci_pins_the_sharded_run_to_the_gates_selection() -> None:
    if _WORKFLOWS_DIR is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    ci = yaml.safe_load((_WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8"))
    assert shard_pin_violations(ci) == []


def _shard_workflow(**overrides) -> dict:
    """A minimal workflow that satisfies the pin; each test breaks one part."""
    step = {
        "name": "pytest -m unit (shard)",
        "working-directory": "apps/api",
        "env": {
            "PYTEST_SHARD": "${{ matrix.shard }}/3",
            "PYTEST_SHARD_RECORD": "${{ runner.temp }}/pytest-shard-${{ matrix.shard }}.txt",
        },
        "run": SHARD_RUN,
    }
    step.update(overrides.pop("step", {}))
    shard_job = {"strategy": {"matrix": {"shard": [1, 2, 3]}}, "steps": [step]}
    shard_job.update(overrides.pop("shard_job", {}))
    checks = {"steps": [{"run": "python -m scripts.check_ci_selection"}]}
    agg = {
        "name": REQUIRED_PYTHON,
        "needs": ["checks", "shard"],
        "if": "always()",
        "steps": [{"run": "python -m scripts.shard_partition verify --full f --of 3 --ran r"}],
    }
    agg.update(overrides.pop("agg", {}))
    assert not overrides, overrides
    return {"jobs": {"checks": checks, "shard": shard_job, "python": agg}}


def test_the_shard_pin_passes_a_correct_workflow() -> None:
    assert shard_pin_violations(_shard_workflow()) == []


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"step": {"run": SHARD_RUN + " -k fast"}}, PYTEST_RUN),
        ({"step": {"run": SHARD_RUN + " --deselect tests/unit/x.py"}}, PYTEST_RUN),
        ({"step": {"run": "pytest -m unit tests/unit"}}, PYTEST_RUN),
        (
            {
                "step": {
                    "env": {
                        "PYTEST_SHARD": "${{ matrix.shard }}/3",
                        "PYTEST_SHARD_RECORD": "r",
                        "PYTEST_ADDOPTS": "--deselect x",
                    }
                }
            },
            SHARD_ENV_ONLY,
        ),
        ({"step": {"env": {"PYTEST_SHARD": "${{ matrix.shard }}/3"}}}, SHARD_ENV_ONLY),
        ({"shard_job": {"strategy": {"matrix": {"shard": [1, 2, 4]}}}}, SHARD_MATRIX),
        ({"shard_job": {"strategy": {}}}, SHARD_MATRIX),
        (
            {
                "step": {
                    "env": {"PYTEST_SHARD": "${{ matrix.shard }}/4", "PYTEST_SHARD_RECORD": "r"}
                }
            },
            SHARD_SPEC,
        ),
        ({"agg": {"if": None}}, AGG_ALWAYS),
        ({"agg": {"if": "success()"}}, AGG_ALWAYS),
        ({"agg": {"steps": [{"run": "echo ok"}]}}, AGG_VERIFY),
        (
            {"agg": {"steps": [{"run": "python -m scripts.shard_partition verify --of 2"}]}},
            AGG_VERIFY,
        ),
        ({"agg": {"needs": ["checks"]}}, AGGREGATE),
        ({"agg": {"name": "Python"}}, AGGREGATE),
    ],
    ids=[
        "k-filter",
        "deselect",
        "unsharded-run",
        "extra-env",
        "missing-record-env",
        "matrix-gap",
        "no-matrix",
        "spec-N-differs",
        "no-always",
        "success-only",
        "no-verify",
        "verify-wrong-N",
        "not-needing-shards",
        "renamed-aggregate",
    ],
)
def test_each_way_to_break_the_shard_pin_is_refused(overrides: dict, expected: str) -> None:
    violations = shard_pin_violations(_shard_workflow(**overrides))
    assert any(v.startswith(expected) for v in violations), violations


def test_a_second_pytest_step_is_refused() -> None:
    ci = _shard_workflow()
    ci["jobs"]["checks"]["steps"].append({"run": "pytest -m unit tests/unit"})
    assert shard_pin_violations(ci)[0].startswith(ONE_PYTEST_STEP)


def test_the_gate_step_run_is_still_exact() -> None:
    ci = _shard_workflow()
    ci["jobs"]["checks"]["steps"] = [
        {"run": 'python -m scripts.check_ci_selection\necho "PYTEST_ADDOPTS=x" >> "$GITHUB_ENV"'}
    ]
    assert any(v.startswith(GATE_RUN) for v in shard_pin_violations(ci))


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


SKIPPED_SUFFIX = "tests/unit/skipped_test.py"


def test_a_self_removing_underscore_test_file_is_a_finding(tmp_path, capsys) -> None:
    # pytest's default python_files is `test_*.py *_test.py`. A scan of only
    # `test_*.py` left this file invisible and "N of N collected" true of a
    # smaller N (review of 52b80c9).
    root = _project(tmp_path, {M: MARKED, SKIPPED_SUFFIX: SKIPPED_MODULE})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert f"{SKIPPED_SUFFIX}: never collected" in out, out


def test_the_file_patterns_are_pytests_own(tmp_path, capsys) -> None:
    # A configured python_files is honoured: `check_*.py` becomes a test file,
    # so a self-removing one is a finding, and `test_*.py` no longer is one.
    root = _project(
        tmp_path, {"tests/unit/check_m.py": MARKED, "tests/unit/check_s.py": SKIPPED_MODULE}
    )
    ini = root / "pytest.ini"
    ini.write_text(
        ini.read_text(encoding="utf-8") + "python_files = check_*.py\n", encoding="utf-8"
    )
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert "tests/unit/check_s.py: never collected" in out, out
    assert "1 of 2 test files on disk collected" in out, out


def test_a_python_files_pattern_with_a_separator_is_honoured(tmp_path, capsys) -> None:
    # pytest matches a pattern holding a separator against the ABSOLUTE path
    # (`fnmatch_ex`). A hand-written root-relative match missed it, so a
    # self-removing spec was invisible (review of 0cf0420).
    root = _project(
        tmp_path,
        {"tests/unit/m_spec.py": MARKED, "tests/unit/s_spec.py": SKIPPED_MODULE},
    )
    ini = root / "pytest.ini"
    ini.write_text(
        ini.read_text(encoding="utf-8") + "python_files = tests/unit/*_spec.py\n", encoding="utf-8"
    )
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert "tests/unit/s_spec.py: never collected" in out, out
    assert "1 of 2 test files on disk collected" in out, out


def test_norecursedirs_is_honoured_by_the_disk_scan(tmp_path, capsys) -> None:
    # pytest does not descend `norecursedirs`, so a file there is not "a test
    # file on disk that never collected" -- it is not a test file to pytest.
    root = _project(tmp_path, {M: MARKED, "tests/unit/fixtures/test_data.py": MARKED})
    ini = root / "pytest.ini"
    ini.write_text(ini.read_text(encoding="utf-8") + "norecursedirs = fixtures\n", encoding="utf-8")
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "1 of 1 test files on disk collected" in out, out


def _symlinked_dir(tmp_path: Path, files: dict[str, str]) -> Path:
    """A project whose `tests/unit/linked` is a symlink to a directory outside
    it holding `files`. pytest descends a symlinked directory, so the scan
    must too, or a file there is invisible to it."""
    (tmp_path / "proj").mkdir()
    root = _project(tmp_path / "proj", {M: MARKED})
    target = tmp_path / "elsewhere"
    target.mkdir()
    for name, body in files.items():
        (target / name).write_text(textwrap.dedent(body), encoding="utf-8")
    try:
        (root / "tests" / "unit" / "linked").symlink_to(target, target_is_directory=True)
    except OSError as exc:  # Windows without the symlink privilege
        pytest.skip(f"cannot create a directory symlink here: {exc}")
    return root


def test_a_symlinked_directory_is_scanned_as_pytest_walks_it(tmp_path, capsys) -> None:
    root = _symlinked_dir(tmp_path, {"test_linked.py": MARKED})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 0, out
    assert "2 of 2 test files on disk collected" in out, out


def test_a_self_removing_file_behind_a_symlink_is_a_finding(tmp_path, capsys) -> None:
    root = _symlinked_dir(tmp_path, {"test_gone.py": SKIPPED_MODULE})
    code, out = _run(root, _baseline(tmp_path, {}), capsys)
    assert code == 1, out
    assert "tests/unit/linked/test_gone.py: never collected" in out, out
