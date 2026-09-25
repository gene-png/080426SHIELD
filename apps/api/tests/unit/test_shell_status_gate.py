"""check_shell_status.py: a gate's exit status must reach the result (#213).

The fixture cases under tests/gates/check_shell_status/ exercise the CLI. These
pin each rule, each exemption and each parser property on its own, so a
regression names the rule that moved.
"""

from __future__ import annotations

import pathlib

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_shell_status as gate

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit


def _rules(script: str, *, pipefail: bool = False) -> list[str]:
    return [
        f.split(": ", 1)[1].split(" --")[0] for f in gate.analyse(script, "t", pipefail=pipefail)
    ]


# --- what is a gate --------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "python scripts/check_x.py",
        "python -m scripts.check_x",
        "python -m pytest -m unit",
        "pytest -m unit",
        "ruff check --no-cache .",
        "npx -y prettier@3.9.8 --check .",
        "bash tests/gates/close_guard_linked_file.sh",
        "docker compose exec -T api pytest -m unit",
        "docker compose exec -T -w /app api python -m scripts.check_x",
        "FOO=1 python scripts/leave_row_oracle.py",
    ],
)
def test_is_gate(cmd: str) -> None:
    assert gate.is_gate(cmd.split()), cmd


@pytest.mark.parametrize(
    "cmd",
    ["echo check_x", "git push", "docker compose version --short", "npx prettier --write ."],
)
def test_is_not_gate(cmd: str) -> None:
    assert not gate.is_gate(cmd.split()), cmd


# --- the three rules ----------------------------------------------------------------------


def test_r1_pipe_without_pipefail() -> None:
    assert _rules("python scripts/check_x.py | head -1") == ["R1 pipe"]


def test_r1_is_off_under_pipefail_set_in_script_or_by_shell_bash() -> None:
    assert _rules("set -euo pipefail\npython scripts/check_x.py | tee o") == []
    assert _rules("python scripts/check_x.py | tee o", pipefail=True) == []


def test_a_gate_last_in_its_pipe_keeps_its_status() -> None:
    assert _rules("echo x | python scripts/check_x.py") == []


def test_r2_or_echo_swallows() -> None:
    assert _rules('pytest -m unit || echo "skipped"') == ["R2 swallow"]


@pytest.mark.parametrize("rescue", ["exit 1", "rc=$?", "return 2", "false"])
def test_r2_is_not_a_capture(rescue: str) -> None:
    assert _rules(f"pytest -m unit || {rescue}\necho done") == []


def test_r3_mid_list_followed_by_more_lines() -> None:
    assert _rules("python -m scripts.check_x && echo ok\ngit push") == ["R3 mid-list"]


def test_r3_does_not_fire_on_the_last_statement() -> None:
    # `gate && next` as the whole script: its status IS the script's status.
    assert _rules("cd /app && ruff check . && black --check .") == []


def test_r3_is_rescued_by_a_later_or_exit() -> None:
    assert _rules("pytest && echo ok || exit 1\ngit push") == []


def test_conditions_consume_the_status_on_purpose() -> None:
    assert _rules("if pytest -m unit; then echo ok; fi\ngit push") == []
    # The case the exemption actually decides: a gate in the MIDDLE of a
    # condition. (A gate first in it carries `if` as its first word and is
    # never read as a gate at all, so it cannot exercise the exemption.)
    assert _rules("if echo a && pytest && echo b; then :; fi\ngit push") == []
    assert _rules("while echo a && pytest || false; do :; done\ngit push") == []


# --- parsing ---------------------------------------------------------------------------------


def test_recurses_into_bash_c() -> None:
    script = "bash -c 'docker compose exec -T api pytest -m unit || echo skipped'"
    assert _rules(script) == ["R2 swallow"]


def test_a_quoted_string_spanning_lines_is_one_statement() -> None:
    script = 'val=$(node -e "\nconsole.log(1)\n")\npython scripts/check_x.py'
    assert gate.statements(script)[-1] == ["python", "scripts/check_x.py"]


def test_comments_and_heredocs_are_not_code() -> None:
    assert _rules("# pytest || echo x\ncat <<EOF\npytest || echo x\nEOF\n") == []


def test_unbalanced_quotes_are_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook):
        gate.statements('echo "unterminated\npytest')


# --- the live repo ------------------------------------------------------------------------------


def test_the_live_repo_is_clean() -> None:
    # The #143 hook was the one live instance and this change repairs it. A new
    # instance anywhere the gate reads turns this red. Skipped only with no
    # `.github/workflows` above this file (the api container mounts apps/api).
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    root = wf.parent.parent
    scripts = gate.workflow_scripts(root) + gate.hook_scripts(root) + gate.claude_md_scripts(root)
    findings = [f for s, w, p in scripts for f in gate.analyse(s, w, pipefail=p)]
    assert findings == [], findings
