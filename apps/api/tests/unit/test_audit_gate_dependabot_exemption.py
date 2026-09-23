"""The Dependabot exemption is a YAML condition, so this pins the CONDITION.

`check_audit_evidence.py` requires a `## Adversarial audit` section in the PR
body. A Dependabot PR has a body Dependabot wrote, and nobody can edit it into
compliance without taking over authorship -- so the gate is RED BY CONSTRUCTION
for that whole class, and the only exits are merging past a required check or
closing the PR and redoing the bump by hand.

The exemption therefore lives on the STEP in `audit-gate.yml`, because the
workflow is the only place the author is known: the script is handed a
changed-file list and a body and has no way to learn who opened the PR.

## What this file can and cannot assert

It reads the workflow and asserts the condition's SHAPE. It does not run
GitHub's expression evaluator, so it cannot prove what Actions does with the
expression -- that is stated here rather than implied, because a source-text
assertion reading like a behavioural one is the defect this repo keeps
recording.

A NOTE ON THE `null` CASE, because the first version of this docstring cited a
population nothing produces. It argued `!=` is right because `user.login` is
`null` "on a payload without a `pull_request`" -- and this workflow's `on:`
block is `pull_request` only, so no trigger it has can produce that, and a
deleted account arrives as `ghost` rather than null. The INEQUALITY is still
right and stays; what changed is the argument for it. The population it protects
is a future trigger -- `workflow_dispatch`, `merge_group`, `issue_comment` --
added to that `on:` block, and the reachability verdict is stated rather than
inherited, per `CLAUDE.md`'s procedure for a correct change whose stated
motivation does not survive contact with the code.

What it CAN do: assert the condition line EQUALS one exact string. That is a
stronger claim than "an inequality appears somewhere on the line", and the
difference is not academic -- the first version asserted the weaker thing under
the name `..._FAILS_CLOSED_...`, and this mutation passed all four tests:

    if: ${{ !(github.event.pull_request.user.login != 'dependabot[bot]') }}

`!=` is present, `==` is absent, the bot login is there -- and the exemption is
INVERTED: the step would run only for Dependabot and skip every human PR, with
the required check reporting success. Direction is a property of the whole
expression, and an assertion about one operator cannot establish it. So this
pins the exact string, plus `continue-on-error` and `|| true`, which are the two
other ways to disable the step without touching the condition at all.

Pinning styling as well as semantics is the right trade for a one-line
condition in a required gate: it is the only form under which "fails closed" is
a claim these tests actually make.

LIVE, NOT LATENT -- and the first version of this docstring said the opposite.
It read "zero Dependabot PRs were open", which was true when measured and false
within the hour: four arrived during the session and all four are blocked on
this exact check.
<!-- counted: gh pr list --state open --author app/dependabot --json number | jq length -> 4 (#465-#468), 2026-09-22 -->
"""

from __future__ import annotations

import pathlib
import re

import pytest

from tests._paths import find_workflows_dir

# MODULE-LEVEL SKIP, not a raise, and the first version got this wrong in the
# way that cost the most.
#
# It walked up for `.github/workflows` and RAISED when it found none. The api
# container mounts only `./apps/api:/app`, so there is no `.github` at or above
# this file there -- and `pytest` has no `--continue-on-collection-errors` in
# `apps/api/pyproject.toml`, so the raise became a collection ERROR that
# reported `Interrupted: 1 error during collection` and ran ZERO TESTS.
# `docker compose exec -T api pytest -m unit -q`, which `CLAUDE.md` prescribes
# as a loop gate, evaluated not one assertion. CI runs a full checkout, so all
# seven checks stayed green over it. Measured, not reasoned.
#
# That is #314 one file over, and the sibling
# `test_audit_gate_collects_only_this_branch.py` already carries both the fix
# and the argument: taking thousands of unrelated tests down because one gate
# test cannot reach its artifact is the fail-closed rule applied in the wrong
# direction.
#
# The precedent this file's first version CITED argues against the raise:
# `check_disclosure_consumers.py::repo_root_for` returns `Path | None` and lets
# the caller decide. The walk-up half was copied and the disposition half was
# inverted -- a known-good shape taken without the property that made it good.
#
# `find_workflows_dir` is imported rather than re-implemented because
# `test_root_discovery.py` pins it in BOTH directions, and a second copy of a
# root search is a second place for it to be wrong.
_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())

if _WORKFLOWS_DIR is None:  # pragma: no cover - container-only branch
    pytest.skip(
        "no .github/workflows above this file -- expected inside the api "
        "container, which mounts only apps/api (#314). Exercised on a full "
        "checkout, which is what CI runs, and ci.yml asserts this module does "
        "NOT skip there.",
        allow_module_level=True,
    )

WORKFLOW = _WORKFLOWS_DIR / "audit-gate.yml"
STEP = "Require recorded audit evidence"
BOT = "dependabot[bot]"
EXPECTED_CONDITION = f"if: github.event.pull_request.user.login != '{BOT}'"


def _step_block() -> str:
    """The step's own YAML, from its `- name:` to the next `- name:` or job.

    Sliced rather than parsed with a YAML loader on purpose: a loader drops the
    comments, and the REASON for this exemption is in the comments. A test that
    could not see them would pass over the exemption being silently rewritten
    into something unexplained.
    """
    src = WORKFLOW.read_text(encoding="utf-8")
    assert src.count(f"- name: {STEP}") == 1, f"expected exactly one {STEP!r} step"
    start = src.index(f"- name: {STEP}")
    tail = src[start + 1 :]
    m = re.search(r"\n  [a-z-]+:\n|\n      - name: ", tail)
    return tail[: m.start()] if m else tail


@pytest.mark.unit
def test_the_step_carries_an_author_condition() -> None:
    """Without an `if:`, the gate is red by construction for every bot PR."""
    block = _step_block()
    assert "if:" in block, (
        f"the {STEP!r} step has no `if:`. A Dependabot PR cannot satisfy "
        f"check_audit_evidence -- its body is not editable by a human without "
        f"taking over the PR -- so the gate is red by construction for that class."
    )
    assert "github.event.pull_request.user.login" in block, (
        "the condition must key on the PR AUTHOR. `github.actor` is who "
        "triggered the run, which on a re-run is whoever clicked it, not the "
        "bot that opened the PR."
    )


@pytest.mark.unit
def test_the_condition_is_EXACTLY_the_expected_string() -> None:
    """Equality, because a claim about direction needs the whole expression.

    THE FIRST VERSION OF THIS TEST WAS NAMED
    `..._FAILS_CLOSED_by_using_an_inequality` AND ASSERTED THREE SUBSTRINGS:
    `!=` present, `==` absent, the bot login present. An adversarial review
    handed back a mutation that satisfies all three and INVERTS the exemption:

        if: ${{ !(github.event.pull_request.user.login != 'dependabot[bot]') }}

    Run: 4 passed, exit 0. The step would execute only for Dependabot, so every
    human PR skips the audit gate while the required check reports success.

    Direction is a property of the WHOLE expression, and the assertions
    established only that one operator appears on the line. That is the
    certificate-over-the-wrong-proposition shape, in a test named for the
    property it did not check -- so the name changed too, because a test named
    for a claim it cannot make is worse than an unnamed one.
    """
    block = _step_block()
    condition = next((ln.strip() for ln in block.splitlines() if ln.strip().startswith("if:")), "")
    assert condition, "no `if:` line found in the step block"
    assert condition == EXPECTED_CONDITION, (
        f"the author condition is not the expected string.\n"
        f"  expected: {EXPECTED_CONDITION!r}\n"
        f"  actual:   {condition!r}\n"
        f"Equality is deliberate: `!=` present and `==` absent does NOT establish "
        f"the direction -- `!(a != b)` satisfies both and inverts the exemption. "
        f"If this change is intended, re-derive the fail-closed argument and "
        f"update EXPECTED_CONDITION in the same commit."
    )


@pytest.mark.unit
def test_the_step_cannot_be_disabled_WITHOUT_touching_the_condition() -> None:
    """Two ways to switch the step off that leave the `if:` line untouched.

    Both came from the same review, and both are plausible as a temporary
    softening rather than as sabotage -- which is what makes them worth pinning:
    `continue-on-error: true` on the step, and `|| true` appended to its `run:`.
    Either one makes the audit requirement unenforceable for EVERY author while
    the condition above still reads exactly right.
    """
    block = _step_block()
    assert "continue-on-error" not in block, (
        "`continue-on-error` on this step makes the audit requirement "
        "advisory for every author, with the condition above unchanged."
    )
    assert "|| true" not in block, (
        "`|| true` on the run line swallows the gate's exit code. The gate "
        "returns 1 for a violation and 2 for could-not-look; both become 0."
    )


@pytest.mark.unit
def test_the_exemption_records_WHY_beside_itself() -> None:
    """A gate exemption with no stated reason is the decorative-marker defect.

    `CLAUDE.md`: an unstated exemption reads as an oversight to everyone who
    finds it later. This asserts the reason is AT the site rather than only in a
    commit message nobody greps.

    ## WHAT THIS CANNOT DO, and the first version implied otherwise

    **It is polarity-blind.** It matches substrings, so a comment documenting the
    REMOVAL of a property satisfies the assertion that the property is recorded:
    "this step no longer FAILS CLOSED" contains `fails closed`, and "this used to
    be RED BY CONSTRUCTION" contains `red by construction`. Stated rather than
    fixed, because the fix is a prose critic and this repo records what happens
    when a pattern is widened until it fires on everything. What this test buys
    is that the region is not EMPTY; whether it says the right thing is a
    reviewer's job.

    ## The window is derived from the JOB, not a magic number

    It first took the last 2,600 characters before the step -- and the comment
    block is about 2,400, so `red by construction` sat near the edge and a
    paragraph added ABOVE the step could have reddened this test on a purely
    additive documentation edit. A false red on a required gate is how a gate
    gets routed around.

    The second attempt ran from the PREVIOUS STEP's `- name:` to this one, and
    that broke immediately for a reason worth keeping: the manifest-only guard
    was inserted between them, so "the previous step" stopped being the thing
    the reason is attached to. The exemption's justification legitimately spans
    both steps -- one removes the requirement, the other bounds it -- so the
    honest window is the JOB above this step. It is derived, it cannot drift on
    an additive edit, and it does not assume how many steps sit between.
    """
    src = WORKFLOW.read_text(encoding="utf-8")
    step_at = src.index(f"- name: {STEP}")
    job_at = src.index("  audit-gate:")
    assert job_at < step_at, "the audit-gate job does not precede its own step"
    reason = src[job_at:step_at]
    assert len(reason) > 400, (
        f"the audit-gate job carries only {len(reason)} characters above "
        f"{STEP!r} -- there is no reason recorded beside this exemption"
    )
    # Case-insensitively: these are prose and the file emphasises with capitals,
    # so a case-sensitive match pins the STYLING rather than the content. The
    # first version matched `"red by construction"` against a comment reading
    # `RED BY CONSTRUCTION` and failed on nothing.
    haystack = reason.lower()
    # `gh pr review --approve` was in this list and has been REMOVED, because the
    # claim it certified is false: branch protection on `main` has
    # `required_approving_review_count: 0` and `enforce_admins: false`, measured
    # 2026-09-22. The test was asserting that a sentence was recorded, not that
    # the control existed -- and the sentence said review was still required. A
    # test certifying a false assurance is worse than no test.
    for phrase, why in [
        ("red by construction", "the reason the exemption exists at all"),
        ("fails closed", "the property a future edit must preserve"),
        ("manifest", "that the exemption is bounded by CONTENT, not author alone"),
        ("#465", "the live PRs it unblocks, so the queue is nameable"),
    ]:
        assert phrase in haystack, f"the exemption does not record {why} ({phrase!r} absent)"


@pytest.mark.unit
def test_the_script_itself_is_still_author_BLIND() -> None:
    """The exemption must not leak into the script.

    Giving `check_audit_evidence.py` an identity to judge would make a text
    checker into an authorisation checker, and the next exemption would go
    there instead of in the workflow where the author is actually known.
    """
    # Off `_WORKFLOWS_DIR`, which is `<repo>/.github/workflows`, rather than a
    # second root search. `_repo_root()` existed here and was deleted -- it
    # re-implemented `find_workflows_dir` and raised where that returns None,
    # which is what took the whole unit suite down in the container.
    gate = _WORKFLOWS_DIR.parent.parent / "apps" / "api" / "scripts" / "check_audit_evidence.py"
    src = gate.read_text(encoding="utf-8").lower()
    # IDENTITY TOKENS, not the English word "author". The first version of this
    # test included `"author"` and failed on three prose lines -- "It proves the
    # author RECORDED an audit", "telling an author something false about their
    # own text", "an author pasting the error message back". Every one is the
    # word, none is a check. An over-broad predicate producing a confident false
    # positive is the shape this repo keeps recording, and it is cheaper to hit
    # in my own test than in a gate.
    for token in ("dependabot", "github.actor", "pull_request.user", "actor_login", "user.login"):
        assert token not in src, (
            f"{token!r} appears in check_audit_evidence.py. The author check "
            f"belongs in the workflow, which is the only place the author is "
            f"known; the script judges TEXT."
        )
