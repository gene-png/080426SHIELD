"""An artifact an aggregate check reads is uploaded with a bounded retry (#734).

On #680 the required Python check went red only because one shard's upload of
its record timed out (ETIMEDOUT) after its tests had passed. The aggregate was
right to fail closed -- a missing record is could-not-look -- but a transient
upload error then cost a full re-run of a green suite.

So every upload an aggregate DOWNLOADS is a run of attempts: each retry runs
only if the attempt before it failed, the earlier attempts carry
`continue-on-error`, and the last does not. The artifacts are DERIVED, not
listed: every upload whose artifact name matches a download `pattern` of a
required aggregate. A new gate input is covered the day it is added, and one
that is not retried fails here.

As `test_ci_aggregate_result_step.py` executes the result step, this EXECUTES
the attempts' control flow: GitHub's `if` / `continue-on-error` semantics,
modelled for exactly the `if` forms used, walked over every success/failure
outcome of every attempt. A form the model does not know is a failure here, not
a guess. The job must succeed exactly when some attempt succeeded -- fail
closed when every attempt failed -- and no attempt may run after one succeeded.
"""

from __future__ import annotations

import fnmatch
import itertools
import pathlib
import re

import pytest
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

# The required checks that download artifacts: E2E (its shard lists) and Python
# (each unit leg's selection, dealt list and junit).
AGGREGATES = ("E2E (Playwright smoke suite)", "Python (ruff + black + pytest + bandit)")
_RETRY_IF = re.compile(r"(always\(\) && )?steps\.([A-Za-z0-9_-]+)\.outcome == 'failure'")


def _jobs() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _download_patterns(jobs: dict) -> list[str]:
    patterns = []
    for job in jobs.values():
        if job.get("name") not in AGGREGATES:
            continue
        for step in job.get("steps", []):
            if str(step.get("uses", "")).startswith("actions/download-artifact@"):
                with_ = step.get("with") or {}
                pattern = with_.get("pattern") or with_.get("name")
                assert pattern, f"an aggregate downloads with no name or pattern: {step!r}"
                patterns.append(str(pattern))
    return patterns


def _is_upload(step: dict) -> bool:
    return str(step.get("uses", "")).startswith("actions/upload-artifact@")


def gate_input_uploads(jobs: dict) -> dict[tuple[str, str], list[tuple[int, dict]]]:
    """(job, artifact name) -> its upload steps, with their indices in the job."""
    patterns = _download_patterns(jobs)
    found: dict[tuple[str, str], list[tuple[int, dict]]] = {}
    for job_id, job in jobs.items():
        for i, step in enumerate(job.get("steps", [])):
            name = str((step.get("with") or {}).get("name", ""))
            if _is_upload(step) and any(fnmatch.fnmatchcase(name, p) for p in patterns):
                found.setdefault((job_id, name), []).append((i, step))
    return found


def _base(step: dict) -> str:
    cond = str(step.get("if", "")).strip()
    assert cond in ("", "always()"), f"the first attempt's `if` is not a form this models: {cond!r}"
    return cond


def _runs(step: dict, first_if: str, prev_id: str | None, outcomes: dict[str, str]) -> bool:
    """GitHub's decision to run a retry, for the one form retries may use."""
    cond = str(step.get("if", "")).strip()
    match = _RETRY_IF.fullmatch(cond)
    assert match, f"a retry's `if` is not a form this models: {cond!r}"
    assert bool(match.group(1)) == (
        first_if == "always()"
    ), f"a retry's status function differs from the first attempt's: {cond!r} vs {first_if!r}"
    assert (
        match.group(2) == prev_id
    ), f"a retry keys on {match.group(2)!r}, not the attempt before it"
    return outcomes.get(prev_id) == "failure"


def simulate(attempts: list[dict], results: tuple[str, ...]) -> tuple[bool, list[int]]:
    """Run the attempts over a green job. (job still green, indices that ran)."""
    first_if = _base(attempts[0])
    outcomes: dict[str, str] = {}
    green, ran = True, []
    for i, (step, result) in enumerate(zip(attempts, results, strict=True)):
        coe = step.get("continue-on-error", False)
        assert isinstance(coe, bool), f"continue-on-error must be a literal, not {coe!r}"
        if i == 0:
            runs = True  # its own `if` is absent or always(), and the job is green so far
        else:
            # Without a status function GitHub prepends success(), which a
            # failure under continue-on-error leaves true.
            keyed = _runs(step, first_if, attempts[i - 1].get("id"), outcomes)
            runs = keyed if first_if == "always()" else green and keyed
        if not runs:
            continue
        ran.append(i)
        if step.get("id"):
            outcomes[step["id"]] = result
        if result == "failure" and not coe:
            green = False
    return green, ran


def test_every_gate_input_is_found() -> None:
    """Vacuity guard: the derivation finds the shard lists and the full list."""
    found = gate_input_uploads(_jobs())
    names = {name for _, name in found}
    assert "e2e-list-full" in names, names
    assert any(n.startswith("e2e-list-shard-") for n in names), names
    assert any(n.startswith("python-shard-") for n in names), names


def test_each_gate_input_is_uploaded_by_contiguous_identical_attempts() -> None:
    for (job_id, name), sites in gate_input_uploads(_jobs()).items():
        where = f"{job_id}: {name}"
        assert (
            len(sites) >= 2
        ), f"{where} is uploaded once, so one transient error reddens the check"
        indices = [i for i, _ in sites]
        assert indices == list(range(indices[0], indices[0] + len(sites))), (
            f"{where}: the attempts are not adjacent ({indices}), so a step between them "
            "could change the file a retry uploads"
        )
        steps = [s for _, s in sites]
        first = {k: v for k, v in steps[0]["with"].items() if k != "overwrite"}
        for step in steps[1:]:
            rest = {k: v for k, v in step["with"].items() if k != "overwrite"}
            assert rest == first, f"{where}: a retry uploads something else: {rest} vs {first}"
            assert (
                step["with"].get("overwrite") is True
            ), f"{where}: a retry without `overwrite: true` collides with a half-made artifact"
        assert all(
            s.get("id") for s in steps[:-1]
        ), f"{where}: an attempt a retry keys on has no id"


def test_the_attempts_fail_closed_and_stop_at_the_first_success() -> None:
    checked = 0
    for (job_id, name), sites in gate_input_uploads(_jobs()).items():
        attempts = [s for _, s in sites]
        for results in itertools.product(("success", "failure"), repeat=len(attempts)):
            green, ran = simulate(attempts, results)
            first_ok = results.index("success") if "success" in results else None
            where = f"{job_id}: {name} with attempts {results}"
            assert green == (
                first_ok is not None
            ), f"{where}: the job is {'green' if green else 'red'}"
            expected = list(range(first_ok + 1 if first_ok is not None else len(attempts)))
            assert ran == expected, f"{where}: attempts {ran} ran, expected {expected}"
            checked += 1
    assert checked, "no attempt sequence was walked"


# --- the model itself, so a broken model cannot pass the workflow -----------------


def _attempts(n: int, *, coe_last: bool = False, first_if: str | None = None) -> list[dict]:
    steps = []
    for i in range(n):
        step: dict = {"uses": "actions/upload-artifact@v7", "with": {"name": "x"}}
        if i < n - 1:
            step["id"] = f"a{i}"
        if i < n - 1 or coe_last:
            step["continue-on-error"] = True
        if i == 0 and first_if:
            step["if"] = first_if
        if i:
            prefix = "always() && " if first_if == "always()" else ""
            step["if"] = f"{prefix}steps.a{i - 1}.outcome == 'failure'"
        steps.append(step)
    return steps


def test_the_model_reds_three_failures_and_greens_a_late_success() -> None:
    assert simulate(_attempts(3), ("failure",) * 3) == (False, [0, 1, 2])
    assert simulate(_attempts(3), ("failure", "success", "failure")) == (True, [0, 1])
    assert simulate(_attempts(3, first_if="always()"), ("success",) * 3) == (True, [0])


def test_the_model_sees_a_last_attempt_that_cannot_fail() -> None:
    green, _ = simulate(_attempts(3, coe_last=True), ("failure",) * 3)
    assert green, "with continue-on-error on the last attempt, three failures stay green"


def test_the_model_refuses_an_if_it_does_not_know() -> None:
    steps = _attempts(2)
    steps[1]["if"] = "steps.a0.conclusion == 'failure'"
    with pytest.raises(AssertionError, match="not a form this models"):
        simulate(steps, ("failure", "success"))
