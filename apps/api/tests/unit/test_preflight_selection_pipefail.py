"""A collection error in one narrowed file must fail the narrowed selection step.

`pytest --collect-only` prints the node ids it could collect and then exits 2
on a broken file; piped into `grep "::"`, the step's status is grep's 0 unless
the step runs under pipefail (see #1294). The planned step is RUN here, in a
throwaway project with this repo's own `addopts`, as preflight runs it
(`bash -e`): once with one importable and one broken file, which must fail,
and once with the importable file alone, which must pass.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import scripts.preflight_plan as pp

pytestmark = pytest.mark.unit

_CI = """\
    on:
      pull_request:
    jobs:
      python:
        runs-on: ubuntu-latest
        steps:
          - name: gate
            working-directory: apps/api
            run: python -m scripts.check_ci_selection --selected-out "$RUNNER_TEMP/sel.txt"
          - name: unit
            working-directory: apps/api
            run: pytest -m unit tests/unit
"""

_PROJECT = '[tool.pytest.ini_options]\naddopts = "-ra -q"\nmarkers = ["unit: u"]\n'
_GOOD = "import pytest\n\npytestmark = pytest.mark.unit\n\n\ndef test_ok():\n    pass\n"
_BROKEN = "import a_module_that_does_not_exist_1294\n"


def _run_selection_step(tmp_path: Path, files: list[str]) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH to run the planned step with")
    repo = tmp_path / "repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "ci.yml").write_text(textwrap.dedent(_CI), encoding="utf-8")
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pyproject.toml").write_text(_PROJECT, encoding="utf-8")
    (proj / "test_good.py").write_text(_GOOD, encoding="utf-8")
    (proj / "test_broken.py").write_text(_BROKEN, encoding="utf-8")
    [sel] = [
        s
        for s in pp.plan(repo, "main", "0", "narrow", files)
        if s["name"].startswith("the certified selection")
    ]
    assert sel["script"].count("python -m pytest") == 1, sel["script"]
    script = sel["script"].replace(
        "python -m pytest", f'"{Path(sys.executable).as_posix()}" -m pytest', 1
    )
    env = {**os.environ, "RUNNER_TEMP": tmp_path.as_posix()}
    return subprocess.run(  # noqa: S603 -- runs the planned step this test built
        [bash, "-e", "-c", script], cwd=proj, env=env, capture_output=True, text=True, timeout=120
    )


def test_a_broken_narrowed_file_fails_the_selection_step(tmp_path: Path) -> None:
    proc = _run_selection_step(tmp_path, ["test_good.py", "test_broken.py"])
    # The importable file's id still reaches the selection file, so only the
    # exit status can tell a partial selection from a whole one.
    selected = (tmp_path / "sel.txt").read_text(encoding="utf-8").splitlines()
    assert selected == ["test_good.py::test_ok"], selected
    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_an_importable_narrowed_file_passes_the_selection_step(tmp_path: Path) -> None:
    proc = _run_selection_step(tmp_path, ["test_good.py"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    selected = (tmp_path / "sel.txt").read_text(encoding="utf-8").splitlines()
    assert selected == ["test_good.py::test_ok"], selected
