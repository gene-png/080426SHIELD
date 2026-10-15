"""What every required check READS on a merge-queue entry (#659, #736 item C).

`test_merge_group_triggers.py` pins that each required context RUNS on
`merge_group`. Running is not enough: a step that reads `github.base_ref` or
`github.event.pull_request.*` gets an EMPTY string on that event, and an empty
string inside a range (`origin/...HEAD`) or a body file is a green that judged
nothing. These tests pin, for every required job and every job it `needs`:

  * the commit it tests is `merge_group.head_sha` -- no checkout overrides
    `ref:`, so `actions/checkout` takes `github.sha`, which on this event is
    the group's head commit;
  * no step reads pull_request-only context unless the step itself runs on
    pull_request only;
  * the two body checks' resolver step runs on merge_group by EQUALITY, passes
    the group's `base_sha` and `head_sha` (so it can confirm the PR head is
    what the group merges), and writes every file the check step then reads.

Reads the workflow YAML; it does not evaluate GitHub expressions.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from tests._paths import find_workflows_dir

_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())
if _WORKFLOWS_DIR is None:  # pragma: no cover - container-only branch
    pytest.skip(
        "no .github/workflows above this file -- expected inside the api container",
        allow_module_level=True,
    )

# Derived, not copied: the one list of required contexts lives in the trigger
# test, with the command that read it from branch protection.
from tests.unit.test_merge_group_triggers import REQUIRED_CONTEXTS  # noqa: E402

PULL_REQUEST_ONLY = "github.event_name == 'pull_request'"
MERGE_GROUP_ONLY = "github.event_name == 'merge_group'"

#: Context that is empty on merge_group. `github.head_ref` is the PR branch on
#: pull_request and unset otherwise; `github.event.merge_group.head_ref` is a
#: different expression and does not contain `github.head_ref`.
_PR_ONLY_CONTEXT = re.compile(r"github\.base_ref|github\.head_ref|github\.event\.pull_request")

#: The one step allowed to read pull_request context on both events: it picks
#: the event's login on pull_request and the FETCHED author file on merge_group,
#: in shell, and exits 2 on an empty result. Its behaviour on both events is
#: executed by test_audit_gate_dependabot_exemption.py.
_BRANCHES_IN_SHELL = {("audit-gate.yml", "audit-gate", "Who opened the PR")}


def _workflows() -> dict[str, dict]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(_WORKFLOWS_DIR.glob("*.yml"))
    }


def _required_closure() -> list[tuple[str, str, dict]]:
    """Every required job, and every job it transitively `needs` (#680 moves
    the real work of two required contexts into needed shard jobs)."""
    workflows = _workflows()
    seen: dict[tuple[str, str], dict] = {}
    pending: list[tuple[str, str]] = []
    for context in REQUIRED_CONTEXTS:
        hits = [
            (file, key)
            for file, wf in workflows.items()
            for key, job in wf.get("jobs", {}).items()
            if job.get("name") == context
        ]
        assert len(hits) == 1, f"{context!r} names {len(hits)} jobs, expected 1: {hits}"
        pending.extend(hits)
    while pending:
        file, key = pending.pop()
        if (file, key) in seen:
            continue
        job = workflows[file]["jobs"][key]
        seen[(file, key)] = job
        needs = job.get("needs", [])
        pending.extend((file, n) for n in ([needs] if isinstance(needs, str) else needs))
    assert len(seen) >= len(REQUIRED_CONTEXTS), seen.keys()
    return [(file, key, job) for (file, key), job in sorted(seen.items())]


def _step_text(step: dict) -> str:
    """Everything in a step an expression can live in, as one string."""
    return yaml.safe_dump({k: v for k, v in step.items() if k not in ("name", "if")})


@pytest.mark.unit
def test_the_closure_is_not_empty_and_has_steps() -> None:
    """A selector that selects nothing passes (CLAUDE.md). Count first."""
    closure = _required_closure()
    steps = sum(len(job.get("steps", [])) for _, _, job in closure)
    assert len(closure) >= 7 and steps >= 20, (len(closure), steps)


@pytest.mark.unit
def test_no_job_a_required_check_needs_can_be_skipped_on_merge_group() -> None:
    """A job a required aggregate `needs` that is skipped hands the aggregate a
    `skipped` result instead of a verdict. `always()` (#680's aggregates) is the
    one condition allowed, by equality: it never skips."""
    for file, key, job in _required_closure():
        assert job.get("if", "always()") == "always()", (
            f"{file}:{key} carries `if: {job['if']}`; a required check or a job it "
            "needs must run on every event, merge_group included"
        )


@pytest.mark.unit
def test_no_required_checkout_overrides_the_commit_under_test() -> None:
    """With no `ref:`, actions/checkout takes `github.sha`, which on merge_group
    is `merge_group.head_sha` -- the commit the queue will merge."""
    checkouts = 0
    for file, key, job in _required_closure():
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                checkouts += 1
                assert "ref" not in (step.get("with") or {}), (
                    f"{file}:{key} checks out `ref: {step['with']['ref']}`; on merge_group "
                    "that is not the group's head, so this required check would test "
                    "something other than what the queue merges"
                )
    assert checkouts >= 7, f"found {checkouts} checkouts in the required closure"


@pytest.mark.unit
def test_pull_request_context_is_read_only_by_pull_request_only_steps() -> None:
    readers: list[tuple[str, str, str]] = []
    for file, key, job in _required_closure():
        for step in job.get("steps", []):
            if not _PR_ONLY_CONTEXT.search(_step_text(step)):
                continue
            name = step.get("name", step.get("uses", "?"))
            readers.append((file, key, name))
            if (file, key, name) in _BRANCHES_IN_SHELL:
                continue
            assert step.get("if") == PULL_REQUEST_ONLY, (
                f"{file}:{key} step {name!r} reads pull_request context, which is EMPTY on "
                f"merge_group, under `if: {step.get('if')}`. Make it pull_request-only and "
                "give merge_group its own input, or read the merge_group payload instead."
            )
    # Positive control: the known readers exist, so the regex is not blind.
    names = {name for _, _, name in readers}
    assert "Read the PR body" in names and "Who opened the PR" in names, readers


@pytest.mark.unit
@pytest.mark.parametrize("pattern", ["github.base_ref", "github.event.pull_request.body"])
def test_the_context_pattern_matches_what_it_forbids(pattern: str) -> None:
    assert _PR_ONLY_CONTEXT.search("${{ " + pattern + " }}")


@pytest.mark.unit
def test_the_context_pattern_leaves_the_merge_group_payload_alone() -> None:
    assert not _PR_ONLY_CONTEXT.search("${{ github.event.merge_group.head_ref }}")


def _job(context: str) -> dict:
    return next(
        job
        for wf in _workflows().values()
        for job in wf.get("jobs", {}).values()
        if job.get("name") == context
    )


def _one_step(job: dict, name: str) -> dict:
    found = [s for s in job["steps"] if s.get("name") == name]
    assert len(found) == 1, f"expected one {name!r} step, found {len(found)}"
    return found[0]


#: The check step each body job ends in, and the files it reads. The paths are
#: literals in the workflow, not temp files this test creates.
_BODY_CHECKS = {
    "Adversarial audit recorded": (
        "Require recorded audit evidence",
        ["/tmp/changed.txt", "/tmp/body.md", "/tmp/pr_head_sha.txt"],  # noqa: S108
    ),
    "No accidental issue closes": (
        "Reject undeclared issue closes",
        [
            "/tmp/pr_title.txt",  # noqa: S108
            "/tmp/pr_body.txt",  # noqa: S108
            "/tmp/pr_commits.txt",  # noqa: S108
            "/tmp/pr_linked.txt",  # noqa: S108
        ],
    ),
}


@pytest.mark.unit
@pytest.mark.parametrize("context", sorted(_BODY_CHECKS))
def test_the_resolver_runs_on_merge_group_and_confirms_the_head(context: str) -> None:
    job = _job(context)
    resolver = _one_step(job, "Read the queued PR (merge_group)")
    assert resolver.get("if") == MERGE_GROUP_ONLY, resolver.get("if")
    env = resolver["env"]
    assert env["HEAD_REF"] == "${{ github.event.merge_group.head_ref }}"
    assert env["BASE_SHA"] == "${{ github.event.merge_group.base_sha }}"
    assert env["GROUP_HEAD_SHA"] == "${{ github.event.merge_group.head_sha }}"
    run = resolver["run"]
    for flag in ('--base-sha "$BASE_SHA"', '--group-head-sha "$GROUP_HEAD_SHA"'):
        assert (
            flag in run
        ), f"{context!r}: the resolver is not given {flag}, so the PR head is NOT checked against the group: {run}"


@pytest.mark.unit
@pytest.mark.parametrize("context", sorted(_BODY_CHECKS))
def test_the_resolver_writes_every_file_the_check_reads(context: str) -> None:
    job = _job(context)
    resolver_run = _one_step(job, "Read the queued PR (merge_group)")["run"]
    check_name, files = _BODY_CHECKS[context]
    check_run = _one_step(job, check_name)["run"]
    for path in files:
        assert path in check_run, f"{check_name!r} no longer reads {path}; update this test"
        assert re.search(
            rf"--[a-z-]+-out {re.escape(path)}(\s|$)", resolver_run
        ), f"on merge_group nothing writes {path}, which {check_name!r} reads"


@pytest.mark.unit
def test_the_audit_check_requires_the_head_to_be_named_on_merge_group_only() -> None:
    """The head SHA is passed on merge_group and never on pull_request: on
    pull_request the rule would redden every PR between a push and a body edit,
    which is a change to today's gate nobody asked for."""
    step = _one_step(_job("Adversarial audit recorded"), "Require recorded audit evidence")
    assert step["env"]["EVENT"] == "${{ github.event_name }}"
    run = step["run"]
    branches = re.findall(r"python -m scripts\.check_audit_evidence[^\n]*", run)
    assert len(branches) == 2, run
    with_head = [b for b in branches if "--head-sha /tmp/pr_head_sha.txt" in b]
    assert len(with_head) == 1, branches
    assert 'if [ "$EVENT" = "merge_group" ]; then' in run, run
    assert run.index(with_head[0]) < run.index(
        "else"
    ), "the --head-sha branch must be the merge_group one"
