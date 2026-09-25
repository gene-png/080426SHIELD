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


@pytest.mark.parametrize("rescue", ["exit 1", "return 2", "false"])
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
    scripts = (
        gate.workflow_scripts(root)
        + gate.hook_scripts(root)
        + gate.shell_file_scripts(root)
        + gate.claude_md_scripts(root)
    )
    findings = [f for s, w, opts in scripts for f in gate.analyse(s, w, **opts)]
    assert findings == [], findings


# --- review of a62f41e ------------------------------------------------------------------


def _unattended(script: str) -> list[str]:
    return [
        f.split(": ", 1)[1].split(" --")[0]
        for f in gate.analyse(script, "t", errexit=False, unattended=True)
    ]


def test_a_gate_in_a_subshell_or_brace_group_is_still_judged_from_outside() -> None:
    assert _rules("(cd a && pytest) && git commit -m x\ngit push") == ["R3 mid-list"]
    assert _rules("(cd a && pytest) || echo skipped") == ["R2 swallow"]
    assert _rules("{ pytest; } | tee log") == ["R1 pipe"]


def test_redirections_do_not_split_the_statement() -> None:
    assert _rules("pytest >/dev/null 2>&1 || echo skipped") == ["R2 swallow"]
    assert _rules("pytest 2>&1 | tee log") == ["R1 pipe"]
    assert _rules("pytest |& tee log") == ["R1 pipe"]


def test_the_wrapper_itself_is_judged_from_outside() -> None:
    script = 'docker compose exec -T api sh -lc "cd /app && pytest -m unit" || echo skipped'
    assert "R2 swallow" in _rules(script)


def test_or_group_with_exit_is_the_fail_loud_idiom_not_a_swallow() -> None:
    assert _rules("pytest || { echo 'suite failed'; exit 1; }\necho done") == []


def test_a_bare_negated_gate_is_a_swallow() -> None:
    assert _rules("! pytest\necho done") == ["R2 swallow"]
    assert _rules("if ! pytest; then exit 1; fi\necho done") == []


def test_set_plus_o_pipefail_turns_it_off() -> None:
    assert _rules("set -o pipefail\nset +o pipefail\npytest | tee log") == ["R1 pipe"]


def test_no_errexit_loses_a_gate_that_is_not_last() -> None:
    assert _unattended("pytest -m unit; echo done") == ["R4 no errexit"]
    assert _unattended("set -e\npytest -m unit; echo done") == []
    # The last command of an if-branch is the compound's status.
    assert _unattended("if up; then pytest; else echo skipped; fi") == []


@pytest.mark.parametrize(
    "cmd",
    [
        "env FOO=1 pytest",
        "timeout 600 pytest",
        "time pytest",
        "docker compose run --rm api pytest",
        ".venv/bin/pytest",
        "python3.12 -m pytest",
        "python -X utf8 scripts/check_x.py",
        "pnpm format:check",
    ],
)
def test_wrappers_and_spellings_are_looked_through(cmd: str) -> None:
    assert gate.is_gate(cmd.split()), cmd


def test_a_comment_quoting_a_heredoc_does_not_swallow_the_script() -> None:
    assert _rules("# run it like: python - <<'PY'\npytest || echo skipped") == ["R2 swallow"]


def test_an_unterminated_heredoc_is_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook, match="never terminated"):
        gate.statements("cat <<EOF\ntext\n")
    # No newline after the `<<` at all: only the end-of-input check can catch it.
    with pytest.raises(gate.CouldNotLook, match="never terminated"):
        gate.statements("cat <<EOF")


def test_a_substitution_inside_double_quotes_is_its_own_quote_context() -> None:
    script = 'X="$(python - <<\'PY\'\nprint("a")\nPY\n)"\necho "$X"'
    assert gate.statements(script)[-1] == ["echo", "$X"]
    # Read naively, the `"` inside the single quotes closes the outer string and
    # leaves a `'` open. Inside `"$( )"` the single quotes are their own.
    assert gate.statements('X="$(echo \'a"b\')"\necho ok')[-1] == ["echo", "ok"]


def test_an_indented_block_naming_a_gate_that_does_not_parse_is_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook):
        gate._block_has_gate('pytest "unterminated')
    assert gate._block_has_gate('prose "unterminated') is False


# --- round 2 of the review ---------------------------------------------------------------


@pytest.mark.parametrize(
    "script",
    ["pytest -m unit || exit 0", "pytest || { echo skipped; exit 0; }", "pytest || return 0"],
)
def test_exit_zero_after_or_is_143_in_another_spelling(script: str) -> None:
    assert _rules(script + "\necho after") == ["R2 swallow"]


@pytest.mark.parametrize("rescue", ["exit", "exit $?", "{ echo x; exit 3; }", "{ exit $?; }"])
def test_status_preserving_exits_are_rescues(rescue: str) -> None:
    assert _rules(f"pytest || {rescue}\necho after") == []


def test_r4_applies_to_workflows_after_set_plus_e_unless_the_status_is_read() -> None:
    wf = gate._shell_flags(None)
    lost = gate.analyse("set +e\npython scripts/check_x.py\necho done", "t", **wf)
    assert [f.split(": ", 1)[1].split(" --")[0] for f in lost] == ["R4 no errexit"]
    kept = "set +e\npython scripts/check_x.py > o.txt\ncode=$?\nset -e\nexit $code"
    assert gate.analyse(kept, "t", **wf) == []


def test_a_brace_group_end_is_not_terminal_but_a_subshell_end_is() -> None:
    assert _rules("{ pytest && echo ok; }\ngit push") == ["R3 mid-list"]
    assert _rules("( pytest && echo ok )\ngit push") == []


def test_a_trailing_operator_continues_onto_the_next_line() -> None:
    assert _rules("pytest ||\n  exit 1\necho after") == []
    assert _rules("pytest &&\n  echo ok") == []


def test_custom_workflow_shells_are_read_for_their_own_flags() -> None:
    assert gate._shell_flags("bash -euo pipefail {0}")["pipefail"] is True
    assert gate._shell_flags("bash {0}")["errexit"] is False
    assert gate._shell_flags("bash") == {"unattended": True, "errexit": True, "pipefail": True}


def test_a_shebang_e_flag_is_errexit(tmp_path: pathlib.Path) -> None:
    (tmp_path / "a.sh").write_text("#!/bin/bash -e\npytest\necho done\n", encoding="utf-8")
    (tmp_path / "b.sh").write_text("#!/bin/bash\npytest\necho done\n", encoding="utf-8")
    found = {
        rel: gate.analyse(text, rel, **opts)
        for text, rel, opts in gate.shell_file_scripts(tmp_path)
    }
    assert found["a.sh"] == []
    assert len(found["b.sh"]) == 1 and "R4" in found["b.sh"][0]


def test_the_could_not_look_word_list_is_the_gate_set() -> None:
    # `tests/gates/*.sh` was a gate to is_gate and prose to the old word list.
    with pytest.raises(gate.CouldNotLook):
        gate._block_has_gate('bash tests/gates/x.sh "unterminated')


# --- round 3: the conservative rescue model --------------------------------------------


@pytest.mark.parametrize(
    "script",
    [
        "pytest || { echo skipped; exit; }",  # bare exit = echo's status, 0
        "pytest || { echo x; exit $?; }",  # $? is echo's
        "pytest || { rc=$?; echo failed; exit 0; }",  # captured, never decided on
        "pytest || rc=$?\necho done",  # captured, never read
        'pytest || exit "$code"',  # nothing shows $code holds the gate's status
    ],
)
def test_a_rescue_that_does_not_visibly_keep_the_failure_is_a_finding(script: str) -> None:
    assert _rules(script + "\necho after") == ["R2 swallow"]


def test_a_capture_counts_only_when_something_decides_on_it() -> None:
    assert _rules('pytest || rc=$?\necho after\nexit "$rc"') == []
    assert _rules('pytest || rc=$?\nif [ "$rc" -ne 0 ]; then exit "$rc"; fi') == []


def test_printing_the_status_is_not_keeping_it() -> None:
    # CLAUDE.md's opening-table row: the step then exits 0 over a red gate.
    wf = gate._shell_flags(None)
    found = gate.analyse('set +e\npython scripts/check_x.py\necho "gate exit $?"', "t", **wf)
    assert [f.split(": ", 1)[1].split(" --")[0] for f in found] == ["R4 no errexit"]
    kept = gate.analyse("set +e\npython scripts/check_x.py\nrc=$?\nexit $rc", "t", **wf)
    assert kept == []
