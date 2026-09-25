"""compose_unchanged.py: the merge rule's compose-comments exception (#530, D-095).

Each case builds a throwaway git repo, so the range, merge-base and show paths
the merge rule relies on are the ones exercised.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

# The DOTTED form, deliberately: see test_leave_row_oracle_anchors.py.
import scripts.compose_unchanged as tool

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


def _compose_job() -> str:
    wf = pathlib.Path(__file__).resolve().parents[4] / ".github" / "workflows" / "audit-gate.yml"
    if not wf.is_file():
        pytest.skip(f"no workflow at {wf} (the api image mounts apps/api only)")
    text = wf.read_text(encoding="utf-8")
    start = text.index("  compose-content-changed:\n")
    end = text.index("\n  # ", start)  # the next job's leading comment
    return text[start:end]


def test_the_ci_job_is_red_on_a_change_and_on_could_not_read() -> None:
    # The job's colour is the verdict: the tool's own 1 and 2 must reach the
    # job, so no flag may turn a change into a 0, and the status is passed on.
    job = _compose_job()
    assert "name: compose content changed\n" in job, job
    assert "compose_unchanged.py --repo ." in job and "--report" not in job, job
    assert 'exit "$rc"' in job, job


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
