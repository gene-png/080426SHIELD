"""The required Python check is two unit legs plus an aggregate, wired as designed.

`ci.yml` runs the unit suite in `python-shard` (a two-leg matrix) and names its
aggregate job `Python (ruff + black + pytest + bandit)`, the check branch
protection requires. What each half does is pinned where it is built --
`test_shard_deselect.py` (the deal), `test_check_python_shards.py` (the
aggregate's verdicts), `test_ci_aggregate_result_step.py` (the result step,
executed) and `test_ci_upload_retry.py` (the upload retries). THIS file pins the
wiring between them, which none of those can see: the legs and the aggregate
agree on `of`, the lint and gates stay on leg 1, the plugin is the only
narrowing and is fed by the job's own environment, and the files a leg uploads
are the files the aggregate reads.

Each is a way for the required check to go green over less than the suite.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from tests._paths import find_workflows_dir

pytestmark = pytest.mark.unit

LEG = "python-shard"
AGGREGATE_NAME = "Python (ruff + black + pytest + bandit)"
LEG_ONE = "matrix.shard == 1"


def _jobs() -> dict:
    wf = find_workflows_dir(pathlib.Path(__file__).resolve())
    if wf is None:
        pytest.skip("no .github/workflows above this file (the api container mounts apps/api)")
    return yaml.safe_load((wf / "ci.yml").read_text(encoding="utf-8"))["jobs"]


def _run(step: dict) -> str:
    return str(step.get("run", "")).strip()


def _steps_running(steps: list[dict], needle: str) -> list[dict]:
    return [s for s in steps if needle in _run(s)]


def _aggregate_job(jobs: dict) -> dict:
    found = [j for j in jobs.values() if j.get("name") == AGGREGATE_NAME]
    assert len(found) == 1, f"expected one job named {AGGREGATE_NAME!r}, found {len(found)}"
    return found[0]


def test_the_required_name_is_the_aggregate_and_not_a_leg() -> None:
    jobs = _jobs()
    aggregate = _aggregate_job(jobs)
    assert aggregate is jobs["python"]
    assert aggregate["needs"] == [LEG]
    assert str(aggregate["if"]).strip() == "always()", aggregate["if"]
    assert "strategy" not in aggregate, "a matrix would rename the required check"
    assert AGGREGATE_NAME not in str(
        jobs[LEG].get("name")
    ), "a leg must not share the required name"


def test_the_matrix_deals_every_leg_and_the_aggregate_expects_exactly_those() -> None:
    jobs = _jobs()
    matrix = jobs[LEG]["strategy"]["matrix"]
    assert matrix["of"] == [len(matrix["shard"])], matrix
    assert matrix["shard"] == list(range(1, len(matrix["shard"]) + 1)), matrix
    assert jobs[LEG]["strategy"].get("fail-fast") is False, "a red leg must not cancel the other"
    (check,) = _steps_running(_aggregate_job(jobs)["steps"], "scripts.check_python_shards")
    assert _run(check).endswith(f'--dir "$RUNNER_TEMP/legs" --of {matrix["of"][0]}'), _run(check)


def test_the_job_environment_tells_every_step_which_leg_it_is() -> None:
    env = _jobs()[LEG]["env"]
    assert env == {
        "SHIELD_SHARD_INDEX": "${{ matrix.shard }}",
        "SHIELD_SHARD_OF": "${{ matrix.of }}",
    }, env


def test_the_plugin_is_the_only_narrowing_and_runs_in_the_certified_envelope() -> None:
    steps = _jobs()[LEG]["steps"]
    (unit,) = _steps_running(steps, "-m unit tests/unit")
    assert " -p scripts.shard_deselect " in _run(unit), _run(unit)
    # The plugin reads its leg from the JOB's environment: a step-level env on the
    # run (or on the gate before it) could give the two different legs.
    assert "env" not in unit, unit
    for narrowing in ("-k ", "--deselect", "--ignore", "--lf", "--ff", "--co"):
        assert narrowing not in _run(unit), narrowing


def test_every_step_that_is_not_the_legs_own_work_stays_on_leg_1() -> None:
    steps = _jobs()[LEG]["steps"]
    on_every_leg = []
    on_leg_one = []
    for step in steps:
        cond = str(step.get("if", "")).strip()
        # YAML reads ` #734)` in a step name as a comment, so a retry's name ends
        # at "(retry 1,"; the retry suffix is dropped to compare the attempts as one.
        name = str(step.get("name") or step.get("uses")).split(" (retry")[0]
        if cond == LEG_ONE:
            on_leg_one.append(name)
        else:
            assert LEG_ONE not in cond, f"{name}: a compound leg-1 condition this does not model"
            on_every_leg.append(name)
    # The legs' own work, by name: everything else (lint, bandit, the gates, the
    # audit-gate and size-gate tests) is leg 1's, so it runs once and a failure on
    # it reddens the aggregate through the leg's result.
    own_work = {
        "actions/checkout@v7",
        "actions/setup-python@v7",
        "Install API + dev tools",
        "every unit test is one CI runs (#540)",
        "pytest -m unit",
        "every dealt test ran exactly once",
        "Collect this leg's selection, dealt list and junit",
        "Upload this leg's record",
    }
    assert set(on_every_leg) == own_work, (
        "a step runs on every leg that should be on leg 1 only (add `if: matrix.shard == 1`), "
        f"or the legs' own work changed (update this list): {sorted(set(on_every_leg) ^ own_work)}"
    )
    for must in ("ruff check", "black --check", "bandit", "pip-audit"):
        assert must in on_leg_one, f"{must} is not on leg 1: {on_leg_one}"
    assert len(on_leg_one) >= 10, on_leg_one  # vacuity guard: the gates really are listed


def test_the_gate_steps_that_must_not_skip_are_still_on_the_leg_that_runs_them() -> None:
    # Two steps assert, from OUTSIDE pytest, that tests which skip themselves
    # off a full checkout did not skip. They need the full checkout and the
    # tests: leg 1 has both, and moving them to a leg that deals other tests
    # would assert nothing.
    steps = _jobs()[LEG]["steps"]
    audit = [s for s in steps if "the audit-gate tests must not skip" in str(s.get("name"))]
    size = [s for s in steps if "size-gate real-file test must not skip" in str(s.get("name"))]
    assert len(audit) == len(size) == 1
    assert audit[0]["if"] == size[0]["if"] == LEG_ONE


def test_a_leg_uploads_the_three_files_the_aggregate_reads_under_the_names_it_reads() -> None:
    jobs = _jobs()
    steps = jobs[LEG]["steps"]
    (collect,) = [s for s in steps if str(s.get("name")).startswith("Collect this leg's")]
    run = _run(collect)
    assert run.startswith("set -euo pipefail"), "a missing file must fail the step, not be skipped"
    for source, named in (
        ("pytest-selection.txt", "selection-$SHIELD_SHARD_INDEX.txt"),
        ("pytest-dealt.txt", "dealt-$SHIELD_SHARD_INDEX.txt"),
        ("pytest-unit.xml", "junit-$SHIELD_SHARD_INDEX.xml"),
    ):
        assert f'cp "$RUNNER_TEMP/{source}" "$RUNNER_TEMP/leg/{named}"' in run, (source, named)
    uploads = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact@")]
    assert len(uploads) == 3
    for upload in uploads:
        assert upload["with"]["name"] == "python-shard-${{ matrix.shard }}"
        assert upload["with"]["path"] == "${{ runner.temp }}/leg"
        assert upload["with"]["if-no-files-found"] == "error"
    (download,) = [
        s
        for s in _aggregate_job(jobs)["steps"]
        if str(s.get("uses", "")).startswith("actions/download-artifact@")
    ]
    assert download["with"]["pattern"] == "python-shard-*"
    assert download["with"]["merge-multiple"] is True
    assert download["with"]["path"] == "${{ runner.temp }}/legs"


def test_the_aggregate_cannot_be_skipped_past_or_ignored() -> None:
    steps = _aggregate_job(_jobs())["steps"]
    for step in steps:
        assert not step.get("continue-on-error"), step
        assert "if" not in step, f"a step-level `if` can skip an aggregate step: {step}"
    (verdict,) = _steps_running(steps, "scripts.check_python_shards")
    assert re.fullmatch(r"python -m scripts\.check_python_shards --dir \S+ --of \d+", _run(verdict))
    assert verdict.get("working-directory") == "apps/api"


def test_the_notes_that_name_the_job_name_the_leg() -> None:
    # The image-optimizer step's note tells a reader how to extract the step the
    # way the runner invokes it; it must point at the job that holds the step.
    text = (find_workflows_dir(pathlib.Path(__file__).resolve()) or pytest.skip("no workflows")) / (
        "ci.yml"
    )
    body = text.read_text(encoding="utf-8")
    assert 'd["jobs"]["python-shard"]["steps"]' in body
    assert 'd["jobs"]["python"]["steps"]' not in body
