"""check_condition5.py: condition 5 with the executable-line exception (#530).

The fixture cases under tests/gates/check_condition5/ exercise the CLI end to
end. These pin the pieces a fixture reaches only indirectly: that CLAUDE.md's
machine list and its prose agree, and each classification rule on its own.
"""

from __future__ import annotations

import pathlib
import re

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.check_condition5 as gate

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

_WORKFLOWS = find_workflows_dir(pathlib.Path(__file__).resolve())


def _repo_claude_md() -> str:
    if _WORKFLOWS is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return (_WORKFLOWS.parent.parent / "CLAUDE.md").read_text(encoding="utf-8")


# --- the list and the prose must agree ---------------------------------------------


def _prose_tokens(md: str) -> set[str]:
    """Backticked paths in the section's bullets, normalised the way the prose writes them."""
    start = md.index("### Condition 5: the paths")
    section = md[start : md.index("\n### ", start + 1)]
    out = set()
    for tok in re.findall(r"`([^`\s]+)`", section):
        tok = tok.rstrip(",.;:")
        if tok.startswith("app/"):
            tok = "apps/api/" + tok
        if tok.endswith("/"):
            tok += "**"
        out.add(tok)
    return out


def test_every_listed_path_is_named_in_the_prose() -> None:
    md = _repo_claude_md()
    listed = gate.paths_from_claude_md(md)
    missing = [p for p in listed if p not in _prose_tokens(md)]
    assert (
        not missing
    ), f"listed in the machine block but explained nowhere in the bullets: {missing}"


def test_the_repo_list_is_the_real_one() -> None:
    listed = gate.paths_from_claude_md(_repo_claude_md())
    # Anchors from three different eras of the list: the first entry, the
    # D-059a web globs, and the 2026-09-19 compose entry that #530 tripped.
    for anchor in ("apps/api/app/ai/**", "apps/web/**/*.test.tsx", "docker-compose.yml"):
        assert anchor in listed, listed


def test_prose_mentions_of_excluded_paths_do_not_become_listed() -> None:
    # The first draft read the prose, which names `apps/web/**` and `alembic/`
    # precisely to EXCLUDE them.
    listed = gate.paths_from_claude_md(_repo_claude_md())
    assert "apps/web/**" not in listed and "alembic/**" not in listed, listed


# --- path matching -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("apps/web/src/components/X.test.tsx", True),
        ("apps/web/X.test.ts", True),
        ("apps/web/src/components/X.tsx", False),
        ("apps/api/app/ai/redact.py", True),
        ("apps/api/app/airline.py", False),
        ("apps/api/scripts/check_condition5.py", True),
        ("apps/api/scripts/red-on-revert.sh", False),
    ],
)
def test_is_listed(path: str, expected: bool) -> None:
    pats = [
        "apps/web/**/*.test.ts",
        "apps/web/**/*.test.tsx",
        "apps/api/app/ai/**",
        "apps/api/scripts/check_*.py",
    ]
    assert gate.is_listed(path, pats) is expected


# --- classification --------------------------------------------------------------------


def test_python_comment_is_not_executable() -> None:
    assert gate.classify("a.py", "x = 1\n", "# why\nx = 1  # because\n") is False


def test_python_directive_comment_is_executable() -> None:
    assert gate.classify("a.py", "x = 'p'\n", "x = 'p'  # noqa: S105\n") is True


def test_python_docstring_is_not_executable_unless_the_file_reads_doc() -> None:
    assert gate.classify("a.py", '"""a"""\nx = 1\n', '"""b"""\nx = 1\n') is False
    reads = "print(__doc__)\n"
    assert gate.classify("a.py", '"""a"""\n' + reads, '"""b"""\n' + reads) is True


def test_python_code_change_is_executable() -> None:
    assert gate.classify("a.py", "x = 1\n", "x = 2\n") is True


def test_yaml_reflow_is_not_executable_but_a_run_comment_is() -> None:
    assert gate.classify("w.yml", "a: [1, 2]\n", "# c\na:\n  - 1\n  - 2\n") is False
    old = "steps:\n  - run: echo hi\n"
    new = "steps:\n  - run: |\n      # c\n      echo hi\n"
    assert gate.classify("w.yml", old, new) is True


def test_shell_comment_is_not_executable_unless_heredoc() -> None:
    assert gate.classify("s.sh", "#!/bin/sh\necho a\n", "#!/bin/sh\n# c\necho a\n") is False
    heredoc = "#!/bin/sh\ncat <<EOF\n# {}\nEOF\n"
    assert gate.classify("s.sh", heredoc.format("a"), heredoc.format("b")) is True


def test_shebang_change_is_executable() -> None:
    assert gate.classify("s.sh", "#!/bin/sh\necho a\n", "#!/bin/bash\necho a\n") is True


def test_data_and_fixture_files_count_every_line() -> None:
    assert gate.classify(".github/pull_request_template.md", "a\n", "a\n<!-- b -->\n") is True
    assert gate.classify("apps/api/tests/gates/x/case/in.py", "# a\n", "# b\n") is True


def test_added_or_deleted_is_executable() -> None:
    assert gate.classify("a.py", None, "x = 1\n") is True
    assert gate.classify("a.py", "x = 1\n", None) is True


def test_typescript_is_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook):
        gate.classify("apps/web/a.test.ts", "a\n", "// b\na\n")


def test_unparseable_python_is_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook):
        gate.classify("a.py", "x = 1\n", "x = (\n")
