"""The required aggregate checks go red unless every job they wait on succeeded.

`Python (ruff + black + pytest + bandit)` and `E2E (Playwright smoke suite)` are
the required checks by name, and since sharding each is an aggregate job with
`if: always()`, so it runs when a dependency failed or was skipped (a skipped
required job reports success). That makes its first step the ONLY thing turning
a failed shard into a red check: delete it, and the aggregate goes green over a
failed shard, with every other pin still satisfied (#680, review finding).

So this EXECUTES the step, as `test_e2e_spec_listing_gate.py`'s
`_run_aggregate_block` executes the verify block: every combination of
{success, failure, cancelled, skipped} for the job's `needs`, and exit 0 only
when all of them are success. The step is found by what it reads, its `env`
mapping each dependency to `${{ needs.<dep>.result }}`, not by its display
name, so renaming it changes nothing and removing it fails here.
"""

from __future__ import annotations

import itertools
import os
import pathlib
import shutil
import subprocess

import pytest
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

# The two required checks, by the exact names branch protection lists.
AGGREGATES = ("Python (ruff + black + pytest + bandit)", "E2E (Playwright smoke suite)")
RESULTS = ("success", "failure", "cancelled", "skipped")


def _jobs() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _aggregate(name: str) -> dict:
    found = [job for job in _jobs().values() if job.get("name") == name]
    assert len(found) == 1, f"expected exactly one job named {name!r}, found {len(found)}"
    return found[0]


def _needs(job: dict) -> list[str]:
    needs = job.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert needs, "the aggregate waits on no job, so it has nothing to aggregate"
    return needs


def _result_step(job: dict) -> tuple[dict, dict[str, str]]:
    """The step whose env carries every dependency's result, and that mapping."""
    needs = _needs(job)
    wanted = {f"${{{{ needs.{dep}.result }}}}" for dep in needs}
    steps = [
        s
        for s in job.get("steps", [])
        if wanted <= {str(v).strip() for v in (s.get("env") or {}).values()}
    ]
    assert len(steps) == 1, (
        f"expected exactly one step reading {sorted(wanted)} from its env, found {len(steps)}: "
        "without it, a failed dependency leaves this `if: always()` check green"
    )
    step = steps[0]
    env_for = {
        dep: var
        for var, value in step["env"].items()
        for dep in needs
        if str(value).strip() == f"${{{{ needs.{dep}.result }}}}"
    }
    return step, env_for


@pytest.mark.parametrize("name", AGGREGATES)
def test_the_result_step_is_present_and_cannot_be_skipped_or_ignored(name: str) -> None:
    step, _ = _result_step(_aggregate(name))
    assert "if" not in step, f"a step-level `if` can skip the result step: {step['if']!r}"
    assert not step.get("continue-on-error"), "`continue-on-error` would ignore its failure"
    # No `shell:` means GitHub's default on ubuntu, `bash -e {0}`, which is
    # exactly how the test below executes it.
    assert "shell" not in step, f"the step runs under {step['shell']!r}, not the tested bash -e"
    assert str(step.get("run") or "").strip(), "the result step runs nothing"


@pytest.mark.parametrize("name", AGGREGATES)
def test_the_result_step_passes_only_when_every_dependency_succeeded(name: str) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash here")
    job = _aggregate(name)
    step, env_for = _result_step(job)
    deps = sorted(env_for)
    assert deps == sorted(_needs(job)), f"not every dependency is read: {deps}"

    outcomes = {}
    for combo in itertools.product(RESULTS, repeat=len(deps)):
        env = {**os.environ, **{env_for[d]: r for d, r in zip(deps, combo, strict=True)}}
        proc = subprocess.run(  # noqa: S603 - the workflow's own step, fixture inputs
            [bash, "--noprofile", "--norc", "-e", "-c", step["run"]],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        outcomes[combo] = proc.returncode

    # Vacuity guard: every combination ran. Both aggregates wait on two jobs
    # today, so this is 16 each; it follows the needs count if that changes.
    assert len(outcomes) == len(RESULTS) ** len(deps), len(outcomes)
    wrong = {
        repr(dict(zip(deps, combo, strict=True))): rc
        for combo, rc in outcomes.items()
        if (rc == 0) != all(r == "success" for r in combo)
    }
    assert not wrong, f"{name}: exit status disagrees with 'all succeeded' for {wrong}"
