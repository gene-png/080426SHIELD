"""The narrowed certified selection preflight writes must list test node ids.

`check_junit_counts` compares the junit report against that file, one node id
per line, so an empty file is could-not-look (exit 2) and every narrow preflight
fails. The expected value comes from the consumer, not from the planner: the
step is RUN here, against a real test file, and its output must hold node ids.
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

_API = Path(__file__).resolve().parents[2]

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


def test_the_narrowed_selection_step_writes_node_ids(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH to run the planned step with")
    root = tmp_path / "repo"
    wf = root / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text(textwrap.dedent(_CI), encoding="utf-8")
    target = "tests/unit/test_preflight_narrow_selection.py"
    steps = pp.plan(root, "main", "0", "narrow", [target])
    [sel] = [s for s in steps if s["name"].startswith("the certified selection")]
    # The planned script names `python`; run it with this interpreter. The
    # count proves the swap landed, so the test cannot run some other python.
    assert sel["script"].count("python -m pytest") == 1, sel["script"]
    script = sel["script"].replace(
        "python -m pytest", f'"{Path(sys.executable).as_posix()}" -m pytest', 1
    )
    env = {**os.environ, "RUNNER_TEMP": tmp_path.as_posix()}
    proc = subprocess.run(  # noqa: S603 -- runs the planned step this test built
        [bash, "-e", "-c", script], cwd=_API, env=env, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = (tmp_path / "sel.txt").read_text(encoding="utf-8").splitlines()
    assert lines == [f"{target}::test_the_narrowed_selection_step_writes_node_ids"], lines
