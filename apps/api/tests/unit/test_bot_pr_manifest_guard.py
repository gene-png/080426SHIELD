"""The content bound on the audit exemption — the half that closes the hole.

`audit-gate.yml` skips the audit requirement when the PR author is
`dependabot[bot]`. That skip is keyed on AUTHOR and justified by CONTENT, and
the gap between them is reachable: a maintainer can push commits to a Dependabot
branch — the routine case is a bump that breaks something and a human fixing it
in place — and `pull_request.user.login` stays `dependabot[bot]`.

Without a content bound, arbitrary human-authored code merges with the required
audit check green and no audit block anywhere in the record. That is the class
#93/#94/#95 record putting a client-facing fabricated gap on `main`, arriving
through the one PR class nobody can edit.

`check_bot_pr_is_manifest_only.py` runs only for the exempted author and fails
when that PR touches anything outside the manifest and lockfile set.

## The pair that matters

The positive case is easy and is not the interesting one. What decides whether
this guard is worth having is that it **cannot fail a human PR** — a check that
fires on the wrong population gets disabled, and then the hole is back with a
test suite that says otherwise.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from tests._paths import find_workflows_dir

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_bot_pr_is_manifest_only.py"
)
BOT = "dependabot[bot]"

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_COULD_NOT_LOOK = 2


def _run(tmp_path: pathlib.Path, changed: str | None, *extra: str, diff: str | None = None):
    """Run it as a PROCESS, so the `__main__` crash handler is exercised."""
    args = [sys.executable, str(SCRIPT), *extra]
    if changed is not None:
        path = tmp_path / "changed.txt"
        path.write_text(changed, encoding="utf-8")
        args += ["--changed-files", str(path)]
    if diff is not None:
        dpath = tmp_path / "diff.txt"
        dpath.write_text(diff, encoding="utf-8")
        args += ["--diff", str(dpath)]
    # noqa justified: every argument is built here from `sys.executable` and
    # `tmp_path`; there is no untrusted input.
    return subprocess.run(  # noqa: S603
        args, capture_output=True, text=True, encoding="utf-8", timeout=120
    )


@pytest.mark.unit
def test_a_real_version_bump_passes(tmp_path: pathlib.Path) -> None:
    """Manifests and lockfiles only, which is what a bump is."""
    result = _run(tmp_path, "pnpm-lock.yaml\napps/web/package.json\n", "--author", BOT)
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_a_HUMAN_PUSHING_CODE_onto_a_bot_branch_FAILS(tmp_path: pathlib.Path) -> None:
    """THE hole this guard closes, and the reason the exemption is safe.

    The author is still the bot, because pushing to its branch does not change
    `pull_request.user.login`. Only the content betrays it.
    """
    result = _run(tmp_path, "pnpm-lock.yaml\napps/api/app/ai/llm.py\n", "--author", BOT)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"
    assert "apps/api/app/ai/llm.py" in result.stderr, (
        "the failure must NAME the offending path -- a guard that fires without "
        "saying what tripped it gets debugged in the wrong direction"
    )


@pytest.mark.unit
def test_it_CANNOT_fail_a_human_authored_PR(tmp_path: pathlib.Path) -> None:
    """The control, and the one that decides whether this guard survives.

    A check that can fail the wrong population gets disabled, and then the hole
    is back with a suite that says otherwise. Same diff as the case above, human
    author, must exit 0.
    """
    result = _run(tmp_path, "pnpm-lock.yaml\napps/api/app/ai/llm.py\n", "--author", "gene-png")
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"
    assert "not applicable" in result.stdout


@pytest.mark.unit
def test_a_MISSING_author_is_2_and_not_the_human_path(tmp_path: pathlib.Path) -> None:
    """The branch that would otherwise be a silent pass.

    Without an author this cannot tell an exempted bot PR from a human one — and
    the human path exits 0. Falling through to it would report clean over a bot
    PR nobody checked, which is the could-not-look branch wearing the clean
    one's clothes.
    """
    result = _run(tmp_path, "apps/api/app/ai/llm.py\n")
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("changed", "extra", "label"),
    [
        ("", ("--author", BOT), "an empty changed-file list"),
        (None, ("--author", BOT), "no --changed-files"),
        ("x\n", ("--author", BOT, "--bogus"), "an unknown flag"),
    ],
)
def test_could_not_look_branches_are_2(tmp_path, changed, extra, label) -> None:
    result = _run(tmp_path, changed, *extra)
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{label}: {result.stdout} {result.stderr}"


@pytest.mark.unit
def test_the_guard_and_the_workflow_agree_on_the_EXEMPTED_LOGIN() -> None:
    """Two files naming one login, and if they disagree the exemption is unguarded.

    `audit-gate.yml` skips the audit step for one author; this script bounds that
    same author. A rename in one place and not the other leaves either a bounded
    author nobody exempts (harmless) or an exempted author nobody bounds (the
    hole, reopened silently). `CLAUDE.md`'s rule is that where a value must agree
    across two files, the pointer sits where the change originates — and where a
    test can simply assert the agreement, it should.
    """
    workflows = find_workflows_dir(pathlib.Path(__file__).resolve())
    if workflows is None:  # pragma: no cover - container-only branch
        pytest.skip("no .github/workflows above this file -- the api container (#314)")
    yml = (workflows / "audit-gate.yml").read_text(encoding="utf-8")
    src = SCRIPT.read_text(encoding="utf-8")
    assert f'EXEMPTED_AUTHOR = "{BOT}"' in src, "the script's exempted author is not the bot login"
    assert f"!= '{BOT}'" in yml, "the workflow does not skip the audit step for that same login"
    assert f"== '{BOT}'" in yml, (
        "the workflow does not RUN the manifest guard for that same login -- so "
        "the exemption is granted without being bounded"
    )


# --------------------------------------------------------------------------
# `.github/` is judged by CONTENT. This is the half the first version missed.
# --------------------------------------------------------------------------

_WF = ".github/workflows/audit-gate.yml"
_HDR = f"diff --git a/{_WF} b/{_WF}"


def _diff(*lines: str) -> str:
    return (
        _HDR
        + chr(10)
        + f"--- a/{_WF}"
        + chr(10)
        + f"+++ b/{_WF}"
        + chr(10)
        + "@@ -1,3 +1,3 @@"
        + chr(10)
        + chr(10).join(lines)
        + chr(10)
    )


@pytest.mark.unit
def test_a_bot_PR_REWRITING_THIS_WORKFLOW_fails(tmp_path: pathlib.Path) -> None:
    """The hole the first version of this guard left open.

    `.github/workflows/*.yml` was on the PATH allow-list, so a PR authored as
    the bot could have deleted the audit step itself and passed manifest-only.
    In the file class that controls every other gate, with `enforce_admins`
    false and zero required reviews.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff("-      - name: Require recorded audit evidence"),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"
    assert "Require recorded audit evidence" in result.stderr, (
        "the failure must quote the offending LINE, not only the file -- a "
        "workflow diff is where a reader most needs to see what changed"
    )


@pytest.mark.unit
def test_a_genuine_uses_bump_in_a_workflow_PASSES(tmp_path: pathlib.Path) -> None:
    """And removing the glob outright would have broken this.

    #465 is the github-actions group: three workflow files, every changed line a
    `uses:` bump. That is legitimate bot traffic and must pass, or closing the
    hole re-breaks what the exemption was built to unblock.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff("-      - uses: actions/checkout@v4", "+      - uses: actions/checkout@v7"),
    )
    assert result.returncode == EXIT_OK, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_LOCAL_action_reference_is_not_a_version_bump(tmp_path: pathlib.Path) -> None:
    """`uses: ./local` points at in-repo code, which is not a dependency.

    The pattern is anchored on owner/repo for this reason: repointing a workflow
    at a different local action is a code change wearing a bump's syntax.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff("+      - uses: ./.github/actions/something-else"),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_github_path_with_NO_diff_is_2(tmp_path: pathlib.Path) -> None:
    """Refusing to answer beats answering from a path match.

    This is the branch that would otherwise reinstate the hole the moment the
    workflow forgets to pass `--diff`.
    """
    result = _run(tmp_path, _WF + chr(10), "--author", BOT)
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_github_path_MISSING_from_the_diff_is_2(tmp_path: pathlib.Path) -> None:
    """The two inputs disagreeing is a could-not-look, not a pass.

    The direction that matters: the file would otherwise be approved unexamined.
    """
    other = ".github/workflows/ci.yml"
    result = _run(
        tmp_path,
        _WF + chr(10) + other + chr(10),
        "--author",
        BOT,
        diff=_diff("-      - uses: actions/checkout@v4", "+      - uses: actions/checkout@v7"),
    )
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{result.stdout}{chr(10)}{result.stderr}"
    assert other in result.stderr


@pytest.mark.unit
def test_the_diff_header_lines_are_not_counted_as_changes(tmp_path: pathlib.Path) -> None:
    """`---`/`+++` start with the same characters as content lines.

    Counting them would make every changed `.github/` file look like it carries
    a non-bump line, so a legitimate bump would fail -- and the guard would then
    be turned off, which is how the hole comes back.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff("+      - uses: actions/setup-python@v7"),
    )
    assert result.returncode == EXIT_OK, (
        "a diff whose only content change is a uses: bump failed -- the "
        f"---/+++ headers are probably being counted. {result.stderr}"
    )
