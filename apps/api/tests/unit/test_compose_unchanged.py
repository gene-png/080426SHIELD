"""compose_unchanged.py: the merge rule's compose-comments exception (#530, D-095).

Each case builds a throwaway git repo, so the range, merge-base and show paths
the merge rule relies on are the ones exercised.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.compose_unchanged as tool

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

BASE = "services:\n  api:\n    image: api:1\n    environment:\n      FLAG: on\n      N: 1\n"


def _repo(
    tmp_path: pathlib.Path, base: dict[str, str | None], head: dict[str, str | None]
) -> pathlib.Path:
    if shutil.which("git") is None:
        pytest.skip(
            "no git here (the api image has none); CI's python job runs on a runner that does"
        )
    r = tmp_path / "r"
    r.mkdir()

    def git(*a: str) -> None:
        cmd = ["git", "-C", str(r), *a]
        subprocess.run(cmd, check=True, capture_output=True)  # noqa: S603,S607

    def write(files: dict[str, str | None]) -> None:
        for rel, text in files.items():
            p = r / rel
            if text is None:
                p.unlink()
            else:
                p.write_text(text, encoding="utf-8", newline="\n")

    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.invalid")
    git("config", "user.name", "t")
    write(base)
    git("add", "-A")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "pr")
    write(head)
    git("add", "-A")
    git("commit", "-q", "-m", "pr")
    return r


def _run(r: pathlib.Path, capsys) -> tuple[int, str]:
    rc = tool.main(["x", "--repo", str(r), "main..pr"])
    return rc, capsys.readouterr().out


def test_a_comments_only_compose_diff_is_unchanged(tmp_path, capsys) -> None:
    # #530's shape: comments and a blank line, nothing that runs.
    head = "# why the api pins this\nservices:\n  api:\n    image: api:1  # pinned\n\n    environment:\n      FLAG: on\n      N: 1\n"
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.yml": BASE}, {"docker-compose.yml": head}), capsys
    )
    assert rc == 0, out
    assert "form only (comments, layout): docker-compose.yml" in out, out


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("image: api:1", "image: api:2"),  # a value
        ("FLAG: on", "FLAG: yes"),  # both True in YAML 1.1; different text to compose
        ("N: 1\n", "N: 1.0\n"),  # equal numbers in Python
        ("N: 1\n", 'N: "1"\n'),  # a string where there was an int
        ("FLAG: on", 'FLAG: "on"'),  # same text, a different TAG: bool becomes str
        ("FLAG: on", "FLAG: !!str on"),  # same text AND style; only the tag differs
    ],
)
def test_a_content_change_trips(tmp_path, capsys, old: str, new: str) -> None:
    head = BASE.replace(old, new)
    assert head != BASE
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.yml": BASE}, {"docker-compose.yml": head}), capsys
    )
    assert rc == 1, out
    assert out.startswith("compose content: CHANGED in 1 file(s)"), out
    assert "content: docker-compose.yml" in out, out


def test_a_compose_merge_tag_is_content(tmp_path, capsys) -> None:
    base = "services:\n  api:\n    volumes: []\n"
    head = "services:\n  api:\n    volumes: !reset []\n"
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.demo.yml": base}, {"docker-compose.demo.yml": head}),
        capsys,
    )
    assert rc == 1, out


def test_an_added_compose_file_trips(tmp_path, capsys) -> None:
    rc, out = _run(_repo(tmp_path, {"README.md": "r\n"}, {"docker-compose.demo.yml": BASE}), capsys)
    assert rc == 1, out
    assert "docker-compose.demo.yml (added or deleted)" in out, out


def test_a_range_with_no_compose_change_says_it_judged_nothing_else(tmp_path, capsys) -> None:
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.yml": BASE, "a.py": "x = 1\n"}, {"a.py": "x = 2\n"}),
        capsys,
    )
    assert rc == 0, out
    assert out.startswith("compose content: UNCHANGED"), out
    assert "says nothing about any path other than the compose files" in out, out


def test_an_unparseable_compose_file_is_could_not_look(tmp_path, capsys) -> None:
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.yml": BASE}, {"docker-compose.yml": "services: [\n"}),
        capsys,
    )
    assert rc == 2, out
    assert "does not parse as YAML" in out, out


@pytest.mark.parametrize("argv", [["x"], ["x", "main"], ["x", "main...pr"], ["x", "a..b", "c"]])
def test_a_bad_argument_is_could_not_look(argv: list[str], capsys) -> None:
    rc = tool.main(argv)
    assert rc == 2, capsys.readouterr().out


def test_a_three_dot_range_is_refused_by_name(capsys) -> None:
    # A three-dot range means something else to git; refuse it rather than let
    # a later git error stand in for the reason.
    rc = tool.main(["x", "main...pr"])
    out = capsys.readouterr().out
    assert rc == 2 and "the range must be BASE..HEAD" in out, out


def test_could_not_read_is_2_and_says_so_first(tmp_path, capsys) -> None:
    r = _repo(tmp_path, {"docker-compose.yml": BASE}, {"docker-compose.yml": "services: [\n"})
    rc, out = _run(r, capsys)
    assert rc == 2, out
    assert out.startswith("compose content: COULD NOT READ"), out


_STUB_PYTHON = """#!/bin/sh
# Stands in for `python` in the job's run block: `-m pip` succeeds, and the
# compose tool reports the state named by STUB_RC, the way the real one does.
if [ "$1" = "-m" ]; then exit 0; fi
case "$STUB_RC" in
  0) echo "compose content: UNCHANGED (stub)" ;;
  1) echo "compose content: CHANGED in 1 file(s) (stub)" ;;
  *) echo "compose-unchanged: CRASHED: stub" >&2 ;;
esac
exit "$STUB_RC"
"""


def _compose_step() -> tuple[dict, dict]:
    """The compose job and its tool step, PARSED from audit-gate.yml (not restated)."""
    import yaml

    # Not `parents[4]`: inside the api container this file is
    # /app/tests/unit/x.py, with four parents, and that raised IndexError before
    # any skip (#314). Skip ONLY when no `.github/workflows` exists above this
    # file at all (the container); a checkout that has the directory and not
    # the file or the job is RED, not skipped.
    wf_dir = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf_dir is None:
        pytest.skip(
            "no .github/workflows directory above this file -- expected inside the "
            "api container, which mounts apps/api at /app (#314); CI's python job "
            "runs this on a full checkout"
        )
    wf = wf_dir / "audit-gate.yml"
    assert wf.is_file(), f"{wf} is missing, so the compose job cannot be checked"
    jobs = yaml.safe_load(wf.read_text(encoding="utf-8"))["jobs"]
    assert "compose-content-changed" in jobs, f"no compose-content-changed job in {wf}"
    job = jobs["compose-content-changed"]
    steps = [s for s in job["steps"] if "compose_unchanged.py" in str(s.get("run", ""))]
    assert len(steps) == 1, steps
    return job, steps[0]


#: The ONE job-level condition allowed, compared by string equality. It exists
#: because audit-gate.yml gained a merge_group trigger, where `github.base_ref`
#: is unset and this job could not read a range. It is allowed because the job
#: is NOT a required check and has already run on the PR head, so skipping it on
#: the queue entry gates no merge. As an allowlist it skips every trigger but
#: pull_request, which excludes only merge_group while those are the workflow's
#: only two triggers -- pinned by the test below it. Allowed by the
#: coordinator's verdict on the merge_group PR; every other `if:`, and
#: continue-on-error, is still refused.
_ALLOWED_JOB_CONDITION = "github.event_name == 'pull_request'"


def test_the_ci_job_cannot_be_made_green_by_configuration() -> None:
    job, step = _compose_step()
    assert job["name"] == "compose content changed", job["name"]
    for where, node in (("job", job), ("step", step)):
        assert "continue-on-error" not in node, f"{where} carries continue-on-error"
    assert (
        job.get("if", _ALLOWED_JOB_CONDITION) == _ALLOWED_JOB_CONDITION
    ), f"the job carries `if: {job['if']}`; only `{_ALLOWED_JOB_CONDITION}` is allowed"
    assert "if" not in step, "the step carries an if:"
    assert "shell" not in step, "the test runs the block under GitHub's default bash -e"


def test_the_one_allowed_condition_excludes_only_merge_group() -> None:
    """`event_name == 'pull_request'` skips the job on EVERY other trigger. That
    is safe only while the workflow's other trigger is exactly merge_group; a
    `push` added later would be skipped silently too."""
    import yaml

    _compose_step()  # the same skip-in-the-container, red-on-a-checkout contract
    wf_dir = find_workflows_dir(pathlib.Path(__file__).resolve())
    assert wf_dir is not None
    workflow = yaml.safe_load((wf_dir / "audit-gate.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))  # PyYAML reads `on` as True
    assert sorted(triggers) == ["merge_group", "pull_request"], (
        f"audit-gate.yml's triggers are {sorted(triggers)}; the compose job's "
        f"`{_ALLOWED_JOB_CONDITION}` would skip every one but pull_request"
    )


def _run_block(tmp_path: pathlib.Path, stub_rc: int) -> tuple[int, str]:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash here")
    _, step = _compose_step()
    run = step["run"]
    marker = "${{ github.base_ref }}"
    assert run.count(marker) == 1, run
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir(exist_ok=True)
    (stub_dir / "python").write_text(_STUB_PYTHON, encoding="utf-8", newline="\n")
    (stub_dir / "python").chmod(0o755)
    summary = tmp_path / f"summary-{stub_rc}.md"
    summary.write_text("", encoding="utf-8")
    script = tmp_path / f"block-{stub_rc}.sh"
    script.write_text(
        'PATH="$(cd "$STUB_DIR" && pwd):$PATH"\n' + run.replace(marker, "main"),
        encoding="utf-8",
        newline="\n",
    )
    env = {
        **os.environ,
        "STUB_DIR": str(stub_dir),
        "STUB_RC": str(stub_rc),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    # GitHub runs a `run:` block with no `shell:` as `bash -e {0}`.
    proc = subprocess.run(  # noqa: S603
        [bash, "--noprofile", "--norc", "-e", str(script)], env=env, capture_output=True
    )
    return proc.returncode, summary.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("stub_rc", "red", "named"),
    [
        (0, False, "compose content: UNCHANGED (stub)"),
        (1, True, "compose content: CHANGED in 1 file(s) (stub)"),
        (2, True, "CRASHED: stub"),
    ],
)
def test_the_ci_job_is_red_on_a_change_and_on_could_not_read(
    tmp_path, stub_rc: int, red: bool, named: str
) -> None:
    # EXECUTES the job's own run block against a stub tool: its exit status is
    # the job's colour, and its summary must name the state, including a crash
    # whose only output is on stderr.
    rc, summary = _run_block(tmp_path, stub_rc)
    assert (rc != 0) is red, (stub_rc, rc, summary)
    assert named in summary, (stub_rc, summary)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('MODE: "0o17"\n', "MODE: 0o17\n"),  # a string to compose's YAML 1.2 octal
        ('SIZE: "1e3"\n', "SIZE: 1e3\n"),  # a string to compose's YAML 1.2 float
    ],
)
def test_a_quote_flip_is_content_even_where_the_1_1_tag_agrees(tmp_path, capsys, old, new) -> None:
    # PyYAML (YAML 1.1) composes both sides to the same tag and value; compose
    # reads the plain forms as numbers. Only the scalar's style tells them apart.
    base = "services:\n  api:\n    environment:\n      " + old
    head = "services:\n  api:\n    environment:\n      " + new
    rc, out = _run(
        _repo(tmp_path, {"docker-compose.yml": base}, {"docker-compose.yml": head}), capsys
    )
    assert rc == 1, out


def test_a_deleted_compose_file_trips(tmp_path, capsys) -> None:
    r = _repo(
        tmp_path,
        {"docker-compose.demo.yml": BASE, "README.md": "r\n"},
        {"docker-compose.demo.yml": None},
    )
    rc, out = _run(r, capsys)
    assert rc == 1, out
    assert "docker-compose.demo.yml (added or deleted)" in out, out
