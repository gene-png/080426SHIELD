"""check_condition5.py: condition 5 with the executable-line exception (#530).

The fixture cases under tests/gates/check_condition5/ exercise the CLI end to
end. These pin the pieces a fixture reaches only indirectly: that CLAUDE.md's
machine list and its prose agree, and each classification rule on its own.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

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
    """Backticked paths in the section (or the slice given), normalised the way the prose writes them."""
    if "### Condition 5: the paths" in md:
        start = md.index("### Condition 5: the paths")
        md = md[start : md.index("\n### ", start + 1)]
    out = set()
    for tok in re.findall(r"`([^`\s]+)`", md):
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


# Paths the bullets name that are NOT in the list, each on purpose. A path
# added here must carry its reason; everything else the bullets name must be
# listed, so dropping a list entry while its bullet stays goes red.
_NAMED_TO_EXCLUDE = {
    "apps/web": "named to say the web product code is condition 6's, not 5's",
    "apps/web/**": "the same exclusion, as a glob",
    "alembic/**": "named to say 'no migration' is not 'nothing under alembic/'",
    "risk.py": "history (#84); the file itself is listed as app/risk/engine.py",
}


def test_every_path_the_prose_names_is_listed_or_deliberately_excluded() -> None:
    md = _repo_claude_md()
    listed = gate.paths_from_claude_md(md)
    start = md.index("### Condition 5: the paths")
    section = md[start : md.index("\n### ", start + 1)]
    bullets = section[section.index("\n- ") : section.index("**Derive the set")]
    named = {
        t for t in _prose_tokens(bullets) if "/" in t or t.endswith((".py", ".sh", ".yml", ".md"))
    }
    unlisted = sorted(t for t in named if t not in listed and not gate.is_listed(t, listed))
    assert unlisted == sorted(_NAMED_TO_EXCLUDE), (
        "a path the bullets name is neither listed nor a recorded exclusion "
        f"(or an exclusion is no longer named): {unlisted}"
    )


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


# --- review of a9b4a77: the list's shape ------------------------------------------------

_LIST = "\n".join(f"    p{i}/**" for i in range(12))


def _md(body: str) -> str:
    return f"# T\n\n### Condition 5: the paths\n\nIntro.\n\n{body}\n\n- `p0/` bullet.\n\n### Next\n"


def test_the_list_reads_whole() -> None:
    assert len(gate.paths_from_claude_md(_md(_LIST))) == 12


def test_a_line_inside_the_list_is_could_not_look_not_a_short_read() -> None:
    lines = _LIST.split("\n")
    split = "\n".join(lines[:6] + ["<!-- counted: x -->"] + lines[6:])
    with pytest.raises(gate.CouldNotLook, match="interrupted"):
        gate.paths_from_claude_md(_md(split))


def test_a_blank_line_splitting_the_list_is_could_not_look() -> None:
    lines = _LIST.split("\n")
    with pytest.raises(gate.CouldNotLook, match="second indented run"):
        gate.paths_from_claude_md(_md("\n".join(lines[:6] + [""] + lines[6:])))


def test_an_entry_that_is_not_one_path_is_could_not_look() -> None:
    with pytest.raises(gate.CouldNotLook, match="not single paths"):
        gate.paths_from_claude_md(_md(_LIST + "\n    two words"))


# --- review of a9b4a77: classification that equality hid --------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("FLAG: on\n", "FLAG: yes\n"),  # both True under YAML 1.1; different text to compose
        ("n: 1\n", "n: 1.0\n"),  # equal numbers in Python
        ("n: 1\n", "n: true\n"),  # True == 1 in Python
        ('v: "1"\n', "v: 1\n"),  # a string becomes an int
    ],
)
def test_yaml_value_changes_python_equality_would_hide(old: str, new: str) -> None:
    assert gate.classify("docker-compose.yml", old, new) is True


def test_yaml_quote_style_alone_is_not_executable() -> None:
    assert gate.classify("w.yml", "a: 'x'\n", 'a: "x"\n') is False


@pytest.mark.parametrize(("old", "new"), [('{"a": 1}', '{"a": true}'), ('{"a": 1}', '{"a": 1.0}')])
def test_json_value_changes_python_equality_would_hide(old: str, new: str) -> None:
    assert gate.classify("package.json", old, new) is True


@pytest.mark.parametrize(
    "directive",
    ["# ruff: noqa: E501", "# isort: skip_file", "# pyright: ignore", "# -*- coding: latin-1 -*-"],
)
def test_more_directives_are_executable(directive: str) -> None:
    assert gate.classify("a.py", "x = 1\n", f"{directive}\nx = 1\n") is True


def test_moving_a_directive_to_another_line_is_executable() -> None:
    old = "a = eval(s)  # nosec B307\nb = 1\n"
    new = "a = eval(s)\nb = 1  # nosec B307\n"
    assert gate.classify("a.py", old, new) is True


# --- review of a9b4a77: the workflow-derived set ------------------------------------------


def test_workflow_scripts_resolve_working_directory_and_dotted_modules() -> None:
    wf = (
        "jobs:\n  j:\n    steps:\n"
        "      - run: bash scripts/red-on-revert.sh --self-test\n"
        "      - working-directory: apps/api\n"
        "        run: |\n"
        "          python -m scripts.check_x tests\n"
        "          python -X utf8 scripts/leave_row_oracle.py\n"
        "          echo not/a/file.py\n"
    )
    tracked = {
        "scripts/red-on-revert.sh",
        "apps/api/scripts/check_x.py",
        "apps/api/scripts/leave_row_oracle.py",
    }
    assert gate.scripts_from_workflows({"ci.yml": wf}, tracked) == tracked


# --- review of a9b4a77: --range, the only form CI runs --------------------------------------

_GIT = shutil.which("git")
_WF = "jobs:\n  j:\n    steps:\n      - run: bash scripts/run-me.sh\n"


def _repo(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    if _GIT is None:
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
    _write(r, files)
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "pr")
    return r


def _write(r: pathlib.Path, files: dict[str, str | None]) -> None:
    for rel, text in files.items():
        p = r / rel
        if text is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")


def _commit(r: pathlib.Path, files: dict[str, str | None]) -> None:
    _write(r, files)
    subprocess.run(["git", "-C", str(r), "add", "-A"], check=True)  # noqa: S603,S607
    subprocess.run(["git", "-C", str(r), "commit", "-q", "-m", "pr"], check=True)  # noqa: S603,S607


def _run(r: pathlib.Path, capsys) -> tuple[int, str]:
    rc = gate.main(["x", "--range", "main..pr", "--repo", str(r)])
    return rc, capsys.readouterr().out


def _base(extra: dict[str, str] | None = None) -> dict[str, str]:
    files = {
        "CLAUDE.md": _md(_LIST.replace("p11/**", "apps/api/app/config.py")),
        ".github/workflows/ci.yml": _WF,
        "scripts/run-me.sh": "#!/bin/sh\necho a\n",
        "apps/api/app/config.py": "X = 1\n",
        "apps/api/tests/unit/test_x.py": "def test_x():\n    assert 1\n",
        "README.md": "r\n",
    }
    files.update(extra or {})
    return files


def test_range_deleting_a_list_entry_and_editing_its_file_still_trips(tmp_path, capsys) -> None:
    r = _repo(tmp_path, _base())
    _commit(
        r,
        {
            "CLAUDE.md": _md(_LIST.replace("p11/**", "p12/**")),
            "apps/api/app/config.py": "X = 2\n",
        },
    )
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "apps/api/app/config.py" in out and "list itself changed" in out, out


def test_range_rename_out_of_a_listed_path_trips(tmp_path, capsys) -> None:
    r = _repo(tmp_path, _base({"CLAUDE.md": _md(_LIST.replace("p11/**", "apps/api/tests/**"))}))
    body = "def test_x():\n    assert 1\n"
    _commit(r, {"apps/api/tests/unit/test_x.py": None, "apps/api/archive/test_x.py": body})
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "apps/api/tests/unit/test_x.py" in out, out


def test_range_a_script_a_workflow_runs_trips_though_unlisted(tmp_path, capsys) -> None:
    r = _repo(tmp_path, _base())
    _commit(r, {"scripts/run-me.sh": "#!/bin/sh\necho b\n"})
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "scripts/run-me.sh" in out, out


def test_range_a_comment_in_a_derived_script_does_not_trip(tmp_path, capsys) -> None:
    r = _repo(tmp_path, _base())
    _commit(r, {"scripts/run-me.sh": "#!/bin/sh\n# why\necho a\n"})
    rc, out = _run(r, capsys)
    assert rc == 0, out
    assert "non-executable change only: scripts/run-me.sh" in out, out


def test_range_an_unlisted_change_is_not_tripped(tmp_path, capsys) -> None:
    r = _repo(tmp_path, _base())
    _commit(r, {"README.md": "s\n"})
    rc, out = _run(r, capsys)
    assert rc == 0 and "not tripped" in out, out


def test_range_refuses_a_checkout_claude_md(tmp_path, capsys) -> None:
    rc = gate.main(["x", "--range", "a..b", "--claude-md", "CLAUDE.md"])
    assert rc == 2 and "base AND the head" in capsys.readouterr().out


def test_range_a_base_with_no_readable_list_trips_rather_than_exits_2(tmp_path, capsys) -> None:
    # main before this gate: the section existed, and its first indented block
    # was a grep command, not a list.
    base_md = "# T\n\n### Condition 5: the paths\n\n    grep -rn x .github/\n\n### Next\n"
    r = _repo(tmp_path, _base({"CLAUDE.md": base_md}))
    _commit(r, {"CLAUDE.md": _md(_LIST.replace("p11/**", "apps/api/app/config.py"))})
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "no readable list at the base" in out, out


# --- review of 8cb5248 --------------------------------------------------------------------


def test_compose_scripts_are_mapped_through_bind_mounts() -> None:
    compose = (
        "services:\n"
        "  web:\n"
        "    volumes:\n"
        "      - ./scripts/web-install-if-stale.sh:/app/web-install-if-stale.sh:ro\n"
        "      - ./apps/web:/app/apps/web\n"
        "    command:\n"
        "      - sh\n"
        "      - -c\n"
        "      - sh /app/web-install-if-stale.sh && node server.js\n"
        "  api:\n"
        "    volumes: !reset []\n"
        "    command: uvicorn app.main:app\n"
    )
    tracked = {"scripts/web-install-if-stale.sh", "apps/api/app/main.py"}
    # The script reached only through a mount is found; `app.main` (not after
    # `-m`) is product code and is not; compose's own `!reset` tag reads.
    assert gate.scripts_from_compose({"docker-compose.yml": compose}, tracked) == {
        "scripts/web-install-if-stale.sh"
    }


def test_gate_configuration_is_derived_by_shape_at_the_top_levels() -> None:
    tracked = {
        "package.json",
        "pnpm-workspace.yaml",
        "pyproject.toml",
        "apps/api/conftest.py",
        "apps/api/ruff.toml",
        "apps/web/vitest.setup.ts",
        "apps/web/next.config.mjs",
        "apps/web/src/lib/x.config.ts",  # deeper: a stated residual, not derived
        "README.md",
    }
    wf = "jobs:\n  j:\n    steps:\n      - run: echo hi\n"
    assert gate.scripts_from_workflows({"ci.yml": wf}, tracked) == tracked - {
        "apps/web/src/lib/x.config.ts",
        "README.md",
    }


def test_a_dotted_name_is_a_module_only_after_dash_m() -> None:
    wf = "jobs:\n  j:\n    steps:\n      - run: echo app.main; python -m scripts.check_x\n"
    tracked = {"app/main.py", "scripts/check_x.py"}
    assert gate.scripts_from_workflows({"ci.yml": wf}, tracked) == {"scripts/check_x.py"}


def test_separator_class_marker_is_a_directive() -> None:
    old = "X = r'[ \\t]'\n"
    assert gate.classify("a.py", old, "X = r'[ \\t]'  # separator-class: reason\n") is True


def test_ci_runs_the_base_copy_of_the_gate_not_the_prs() -> None:
    # A STRUCTURE check of this repo's workflow, and only that: the PR's own
    # workflow runs, so a PR can edit this step and this test together. What it
    # guards is an accidental revert, not a hostile one (#572).
    import yaml

    if _WORKFLOWS is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    doc = yaml.safe_load((_WORKFLOWS / "audit-gate.yml").read_text(encoding="utf-8"))
    runs = [s.get("run", "") for s in doc["jobs"]["condition-5-report"]["steps"]]
    step = next(r for r in runs if "check_condition5" in r)
    assert 'git rev-parse --verify --quiet "$base"' in step
    assert 'git cat-file -e "$base:$gate"' in step
    assert "python /tmp/check_condition5_base.py" in step
    assert (
        "python scripts/check_condition5.py" not in step
    ), "the PR's own copy must not judge the PR"


def test_the_base_copy_trips_a_pr_whose_own_copy_says_clear(tmp_path) -> None:
    # EXECUTES both copies as CI would: the PR's rigged copy certifies itself,
    # and the base's copy -- the one CI runs -- trips the same PR.
    import sys

    real = pathlib.Path(gate.__file__).read_text(encoding="utf-8")
    anchor = "def main(argv: list[str]) -> int:\n"
    assert real.count(anchor) == 1
    rigged = real.replace(anchor, anchor + "    return 0  # rigged: always 'not tripped'\n")
    listed = _LIST.replace("p11/**", "apps/api/scripts/check_*.py")
    r = _repo(
        tmp_path,
        _base({"CLAUDE.md": _md(listed), "apps/api/scripts/check_condition5.py": real}),
    )
    _commit(r, {"apps/api/scripts/check_condition5.py": rigged})

    def show(ref: str) -> str:
        cmd = ["git", "-C", str(r), "show", f"{ref}:apps/api/scripts/check_condition5.py"]
        return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout  # noqa: S603

    def run_copy(src: str) -> tuple[int, str]:
        f = tmp_path / "copy_under_test.py"
        f.write_text(src, encoding="utf-8")
        cmd = [sys.executable, str(f), "--range", "main..pr", "--repo", str(r)]
        proc = subprocess.run(cmd, capture_output=True, text=True)  # noqa: S603
        return proc.returncode, proc.stdout

    head_src, base_src = show("pr"), show("main")
    assert head_src == rigged and base_src == real
    head_rc, head_out = run_copy(head_src)
    assert head_rc == 0, head_out  # the PR's own copy would certify itself
    base_rc, base_out = run_copy(base_src)
    assert base_rc == 1, base_out
    assert (
        "executable change in a condition-5 path: apps/api/scripts/check_condition5.py" in base_out
    )


def test_compose_mounts_merge_across_files_and_refuse_what_they_cannot_resolve() -> None:
    base = (
        "services:\n"
        "  web:\n"
        "    volumes:\n"
        "      - ./scripts/x.sh:/app/x.sh:ro\n"
        "      - type: bind\n"
        "        source: tools\n"
        "        target: /tools\n"
        "      - ${HOME_DIR:-$HOME/.cfg}:/cfg:ro\n"
    )
    override = "services:\n  web:\n    command: sh /app/x.sh && sh /tools/y.sh\n"
    tracked = {"scripts/x.sh", "tools/y.sh"}
    # The override's command runs with the base file's mounts, and a relative
    # long-syntax source resolves.
    assert (
        gate.scripts_from_compose(
            {"docker-compose.yml": base, "docker-compose.demo.yml": override}, tracked
        )
        == tracked
    )
    # A command path under a mount that needs interpolation is could-not-look.
    uses_cfg = "services:\n  web:\n    command: sh /cfg/z.sh\n"
    with pytest.raises(gate.CouldNotLook, match="interpolation"):
        gate.scripts_from_compose({"docker-compose.yml": base, "o.yml": uses_cfg}, tracked)
