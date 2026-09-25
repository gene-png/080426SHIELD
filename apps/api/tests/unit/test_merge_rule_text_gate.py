"""check_merge_rule_text.py: a change to the merge rule's text is always red (#572).

The fixtures under tests/gates/check_merge_rule_text/ exercise the file mode.
These pin the --range mode, which is what CI runs, against real repositories.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_merge_rule_text as gate

pytestmark = pytest.mark.unit

RULE = (
    "# CLAUDE.md\n\n## The merge rule: when an agent may merge\n\n"
    "5. **None of the paths listed below.**\n\n### Condition 5: the paths\n\n"
    "- `apps/api/app/ai/`\n\n## Real commands\n\n- run things\n"
)


def _repo(tmp_path: pathlib.Path, head_text: str) -> pathlib.Path:
    if shutil.which("git") is None:
        pytest.skip(
            "no git here (the api image has none); CI's python job runs on a runner that does"
        )
    r = tmp_path / "r"
    r.mkdir()

    def git(*a: str) -> None:
        cmd = ["git", "-C", str(r), *a]
        subprocess.run(cmd, check=True, capture_output=True)  # noqa: S603,S607

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    (r / "CLAUDE.md").write_text(RULE, encoding="utf-8", newline="\n")
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "pr")
    (r / "CLAUDE.md").write_text(head_text, encoding="utf-8", newline="\n")
    git("add", "-A")
    git("commit", "-q", "-m", "pr", "--allow-empty")
    return r


def _run(r: pathlib.Path, capsys, rng: str = "main..pr") -> tuple[int, str]:
    rc = gate.main(["x", "--range", rng, "--repo", str(r)])
    return rc, capsys.readouterr().out


def test_range_a_change_inside_the_section_is_red_and_names_the_line(tmp_path, capsys) -> None:
    r = _repo(tmp_path, RULE.replace("app/ai/`", "app/ai/**/*.py`"))
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "+- `apps/api/app/ai/**/*.py`" in out and "-- `apps/api/app/ai/`" in out, out


def test_range_a_change_outside_the_section_is_green(tmp_path, capsys) -> None:
    r = _repo(tmp_path, RULE.replace("- run things", "- run other things"))
    rc, out = _run(r, capsys)
    assert rc == 0, out
    assert "the merge rule's text is unchanged" in out, out


def test_range_a_renamed_heading_is_could_not_look(tmp_path, capsys) -> None:
    r = _repo(tmp_path, RULE.replace("## The merge rule:", "## Merging:"))
    rc, out = _run(r, capsys)
    assert rc == 2, out
    assert "no `## The merge rule` section" in out and "the head" in out, out


def test_range_an_unreadable_base_is_could_not_look(tmp_path, capsys) -> None:
    r = _repo(tmp_path, RULE)
    rc, out = _run(r, capsys, "no-such-ref..pr")
    assert rc == 2, out
    assert "could not look" in out and "no-such-ref" in out, out


def test_the_section_ends_at_the_next_level_two_heading() -> None:
    body = gate.section(RULE, "t")
    assert body.startswith("## The merge rule") and "### Condition 5" in body, body
    assert "## Real commands" not in body and "run things" not in body, body


@pytest.mark.parametrize(
    "argv",
    [
        ["x"],
        ["x", "--old", "a"],
        ["x", "--range", "a..b", "--old", "a", "--new", "b"],
        ["x", "--nope"],
    ],
)
def test_a_bad_argument_is_could_not_look(argv: list[str], capsys) -> None:
    rc = gate.main(argv)
    assert rc == 2, capsys.readouterr().out
