"""Every required status check must RUN on a merge-queue entry, not be skipped.

A merge queue merges a group only when every required context reports on the
group's commit. A workflow without a `merge_group` trigger never reports, so the
queue stalls. That failure is loud. The quiet one is a JOB-LEVEL `if:`: a skipped
required job reports SUCCESS, so a condition that excludes `merge_group` from a
required job is a silent green on exactly the event where the check matters.

## The required contexts are a CONSTANT here, not read live

`REQUIRED_CONTEXTS` is what branch protection listed on the date below. It is
not fetched at test time -- a unit test with a network dependency would be a
different test. If branch protection changes, update this constant in the same
PR; a context missing from it is simply not checked here.

    <!-- counted: gh api repos/gene-png/080426SHIELD/branches/main/protection
         --jq .required_status_checks.contexts, 2026-09-26 -->

## What this reads

The workflow YAML, parsed. It asserts the trigger and the ABSENCE of a job-level
condition; it does not run GitHub's expression evaluator, so a step-level
condition's behaviour is out of its reach except for the secret-scan pair, whose
two conditions it pins as exact complements.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml

from tests._paths import find_workflows_dir

# Module-level SKIP in the api container, which mounts only apps/api: the same
# disposition, and the same reason, as test_audit_gate_dependabot_exemption.py.
_WORKFLOWS_DIR = find_workflows_dir(pathlib.Path(__file__).resolve())
if _WORKFLOWS_DIR is None:  # pragma: no cover - container-only branch
    pytest.skip(
        "no .github/workflows above this file -- expected inside the api container",
        allow_module_level=True,
    )

REQUIRED_CONTEXTS = (
    "Adversarial audit recorded",
    "Demo (hosted-demo reset + journey spec)",
    "E2E (Playwright smoke suite)",
    "Python (ruff + black + pytest + bandit)",
    "Secret scan (gitleaks)",
    "Web (prettier + eslint + typecheck + build)",
    "No accidental issue closes",
)


def _workflows() -> dict[str, dict]:
    return {
        path.name: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(_WORKFLOWS_DIR.glob("*.yml"))
    }


def _triggers(workflow: dict) -> dict:
    """The `on:` block. PyYAML reads the bare key `on` as the boolean True."""
    on = workflow.get("on", workflow.get(True))
    assert isinstance(on, dict), f"expected a mapping of triggers, got {on!r}"
    return on


def _job_named(name: str) -> tuple[str, str, dict]:
    """The one job, in any workflow, whose `name:` is this required context."""
    found = [
        (file, key, job)
        for file, workflow in _workflows().items()
        for key, job in workflow.get("jobs", {}).items()
        if job.get("name") == name
    ]
    assert len(found) == 1, (
        f"required context {name!r} is the name of {len(found)} jobs, expected exactly 1: "
        f"{[(f, k) for f, k, _ in found]}. A rename would leave this test checking nothing."
    )
    return found[0]


@pytest.mark.unit
@pytest.mark.parametrize("context", REQUIRED_CONTEXTS)
def test_a_required_checks_workflow_runs_on_merge_group(context: str) -> None:
    file, key, _ = _job_named(context)
    triggers = _triggers(_workflows()[file])
    assert "merge_group" in triggers, (
        f"{context!r} ({file}:{key}) never reports on a queue entry: {file} has no "
        f"merge_group trigger, so the merge queue waits on it forever."
    )


@pytest.mark.unit
@pytest.mark.parametrize("context", REQUIRED_CONTEXTS)
def test_a_required_job_has_no_job_level_condition(context: str) -> None:
    """A skipped required job reports success. No condition, no skip."""
    file, key, job = _job_named(context)
    assert "if" not in job, (
        f"{context!r} ({file}:{key}) carries a job-level `if: {job['if']}`. When it is "
        f"false the job is SKIPPED and the required context reports SUCCESS -- a "
        f"silent green on the event it excluded."
    )


@pytest.mark.unit
def test_the_secret_scan_runs_exactly_one_scanner_per_event() -> None:
    """gitleaks-action@v3 rejects merge_group, so the job runs the action on
    every other event and the pinned CLI on merge_group. The two conditions
    must be exact complements: if both were false the job would pass having
    scanned nothing."""
    _, _, job = _job_named("Secret scan (gitleaks)")
    conditions = [step.get("if") for step in job["steps"] if "if" in step]
    assert sorted(conditions) == sorted(
        ["github.event_name != 'merge_group'", "github.event_name == 'merge_group'"]
    ), f"expected one step for merge_group and one for every other event, got {conditions}"
