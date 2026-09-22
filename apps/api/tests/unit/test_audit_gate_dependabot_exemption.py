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

What it CAN do, and what makes it worth having rather than decorative: the
FAIL-CLOSED DIRECTION is a property of the operator, and an operator is
checkable. `!=` runs the step for every author that is not the bot, including
the `null` that `user.login` is on a payload without a `pull_request`. An `==`
would invert it and exempt everyone EXCEPT Dependabot -- a one-character
mutation, in a required gate, that no other test in this repo would catch.

LATENT WHEN WRITTEN: zero Dependabot PRs were open on 2026-09-22, so nothing
was unblocked and nothing visibly changed. That is precisely why it needs a
test -- an empty queue is not an exemption, and nobody would notice the
operator flipping until a bot PR arrived and the gate silently stopped applying
to everyone else.
"""

from __future__ import annotations

import pathlib
import re

import pytest


def _repo_root() -> pathlib.Path:
    """The repo root, DERIVED by walking up for a marker.

    Not `parents[N]`. That is a claim about where this file sits relative to a
    mount, and it is wrong in the container: `apps/api` is mounted at `/app` for
    the lint gate and the whole tree at `/work` for a full-checkout run, so the
    same expression names two different directories. The first version of this
    file used `parents[3]` and died with `FileNotFoundError` -- loudly, which is
    the only reason it cost a minute rather than a wrong verdict.

    `check_disclosure_consumers.py::repo_root_for` makes the same argument.
    """
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".github" / "workflows").is_dir():
            return candidate
    raise AssertionError(
        f"no directory above {here} contains .github/workflows -- this test "
        f"cannot look, which is not the same as finding nothing wrong"
    )


WORKFLOW = _repo_root() / ".github" / "workflows" / "audit-gate.yml"
STEP = "Require recorded audit evidence"
BOT = "dependabot[bot]"


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
def test_the_condition_FAILS_CLOSED_by_using_an_inequality() -> None:
    """The operator is the whole safety property, and it is one character.

    `!=` means every author that is not the bot RUNS the step, so an unexpected
    or absent `user.login` still gets the gate. `==` inverts it: the step would
    run ONLY for Dependabot, exempting every human PR from the audit
    requirement -- the gate's entire subject, switched off, with the workflow
    still listing the step and CI still green.
    """
    block = _step_block()
    condition = next((ln.strip() for ln in block.splitlines() if ln.strip().startswith("if:")), "")
    assert condition, "no `if:` line found in the step block"
    assert "!=" in condition, (
        f"the author condition must be an INEQUALITY. Found: {condition!r}. "
        f"An `==` exempts everyone except Dependabot."
    )
    assert "==" not in condition, (
        f"found an equality in the author condition: {condition!r}. "
        f"See this test's docstring -- it inverts the exemption."
    )
    assert BOT in condition, f"the condition names no bot login: {condition!r}"


@pytest.mark.unit
def test_the_exemption_records_WHY_beside_itself() -> None:
    """A gate exemption with no stated reason is the decorative-marker defect.

    `CLAUDE.md`: an unstated exemption reads as an oversight to everyone who
    finds it later. This asserts the reason is AT the site rather than only in a
    commit message nobody greps.
    """
    src = WORKFLOW.read_text(encoding="utf-8")
    before = src[: src.index(f"- name: {STEP}")]
    reason = before[-2600:]
    # Case-insensitively: these are prose and the file emphasises with capitals,
    # so a case-sensitive match pins the STYLING rather than the content. The
    # first version of this test matched `"red by construction"` against a
    # comment reading `RED BY CONSTRUCTION` and failed on nothing.
    haystack = reason.lower()
    for phrase, why in [
        ("red by construction", "the reason the exemption exists at all"),
        ("fails closed", "the property a future edit must preserve"),
        ("gh pr review --approve", "that human review is UNCHANGED by this"),
        ("latent", "that an empty bot queue is not evidence it works"),
    ]:
        assert phrase in haystack, f"the exemption does not record {why} ({phrase!r} absent)"


@pytest.mark.unit
def test_the_script_itself_is_still_author_BLIND() -> None:
    """The exemption must not leak into the script.

    Giving `check_audit_evidence.py` an identity to judge would make a text
    checker into an authorisation checker, and the next exemption would go
    there instead of in the workflow where the author is actually known.
    """
    gate = _repo_root() / "apps" / "api" / "scripts" / "check_audit_evidence.py"
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
