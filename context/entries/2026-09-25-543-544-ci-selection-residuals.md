# 2026-09-25: the CI-selection gate sees whole files and the pytest step's environment (#543, #544)

Branch `track1/ci-selection-residuals`, branch-start base `ebdd23d`.

## Why

`check_ci_selection.py` compares two collections of `tests/unit`: all tests,
and the tests CI's selector picks. Two gaps were stated in its docstring as
limits.

- **#543.** Some files remove themselves at collection time: a module-level
  `pytest.skip(..., allow_module_level=True)`, or a conftest `collect_ignore`.
  Such a file is absent from BOTH collections, so it shrinks the denominator
  instead of producing a finding. "CI selects N of N" reads clean with a
  smaller N.
- **#544.** The gate pins CI's pytest `run:` line and nothing else. An
  `env: PYTEST_ADDOPTS: --deselect ...` on that step would narrow CI and not
  the gate, with every pin green.

## What changed

- **Every file on disk under `tests/unit` that pytest's `python_files` names
  must contribute a node id to the unselected collection.** The patterns are
  pytest's own answer: the probe plugin writes `config.getini("python_files")`.
  The first version hard-coded `test_*.py` and missed the default's second
  half, `*_test.py` (review of `52b80c9`). A file that contributes none is a finding. It
  can instead carry a baseline entry `{"reason": ..., "uncollected_file":
  true}`. That entry ratchets like the node-id entries: it is a finding once
  the file collects again, or is deleted.
- **Rootdir below the root.** Node ids can be relative to a pytest rootdir
  below the root (a `tests/pytest.ini`), so a disk path matches a node file
  that equals it or is a `/`-bounded suffix of it.
- **The clean line** now also says `N of N test files on disk collected`.
- **#544 is a pin, not a read.** A new test requires CI's `pytest -m unit`
  step and the gate's step to sit in ONE job, so job and workflow env reach
  both. It also requires identical step-level `env` and `working-directory`,
  and no step BETWEEN the two writing `$GITHUB_ENV` or `$GITHUB_PATH`, which
  would change the environment of the later step only (review of `52b80c9`).
  The pin is a pure function over a parsed workflow, so synthetic workflows
  test it.

## Measured, before writing the check

On a full checkout at `ebdd23d`, all 162 `test_*.py` files under
`tests/unit` contributed a node id. So the new check starts clean, and the
baseline gains no entries.

At the first head, `52b80c9`, the gate read: `CI selects 8587 of 8596 collected tests; 162 of 162
test files on disk collected`.

## Verified

- 43 tests pass in the gate's file plus the crash-exit test, in
  `docker run --rm` of `shield-v2-api:latest` with the full worktree mounted.
- Red-on-revert, 5 of 5, with each anchor counted:
  - the file findings dropped;
  - equality-only file matching;
  - the now-collected ratchet dropped;
  - both baseline shapes accepted in one entry;
  - a `PYTEST_ADDOPTS` env added to CI's pytest step only, written into
    `ci.yml` and restored.

  After review, 3 of 3 more went red:
  - the hard-coded `test_*.py`, caught by a self-removing `*_test.py` and a
    configured `python_files`;
  - the `GITHUB_ENV` check dropped;
  - a `GITHUB_ENV` writer inserted into the real `ci.yml` between the two
    steps, then restored.

## Limits

- The check is per FILE. A module that removes only some of its tests at
  collection is not seen.
- A conftest hook deselecting individual items applies to both collections,
  and is still invisible.
- Environment set outside the step, such as a runner image or a composite
  action, is not seen. Nor is a step between the two that changes the
  environment by any route other than `$GITHUB_ENV` or `$GITHUB_PATH`.
