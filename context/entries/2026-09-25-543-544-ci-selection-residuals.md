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
- **#544 is a pin, not a read, and the pin is a derivation.** A test
  requires the gate step to be the step IMMEDIATELY before CI's
  `pytest -m unit` step, in the same job, with its `run` exactly
  `python -m scripts.check_ci_selection` (a second line could write
  `$GITHUB_ENV`; review of `ec113e1`) and the same step `env`,
  `working-directory` and `shell` (a login shell can source a profile). So every job, workflow and earlier-step environment
  reaches both, and no step can change one without the other. The
  `check_e2e_env_gates` step, which sat between them, moved above the gate in
  `ci.yml`; it reads only `e2e/` and the workflows and writes nothing, so the
  order is harmless.

  Round 1 matched step text for `GITHUB_ENV`/`GITHUB_PATH`, and review of
  `0cf0420` showed what that missed: `uses:` actions that export, scripts that
  write the file, and `${{ steps.X.outputs }}` in an env. Adjacency leaves no
  step for any of them to be in. The pin is a pure function over a parsed
  workflow, tested against synthetic workflows with each refusal's exact
  message.
- **The file scan is pytest's own.** It uses pytest's own matcher,
  `_pytest.pathlib.fnmatch_ex`, called directly, with `python_files` and
  `norecursedirs` taken from pytest via the probe. A pattern with a separator
  is therefore matched against the absolute path, as pytest does. Round 1's
  hand-written root-relative match missed `tests/unit/*_spec.py` (review of
  `0cf0420`).

## Measured, before writing the check

On a full checkout at `ebdd23d`, all 162 `test_*.py` files under
`tests/unit` contributed a node id. So the new check starts clean, and the
baseline gains no entries.

At the first head, `52b80c9`, the gate read: `CI selects 8587 of 8596 collected tests; 162 of 162
test files on disk collected`.

## Verified

- `pytest -p no:cacheprovider -o addopts= tests/unit/test_ci_selection_gate.py tests/unit/test_gate_crash_exit_code.py`:
  **133 passed**. Run at the round-4 fix head, in `docker run --rm` of
  `shield-v2-api:latest` with the full worktree mounted.

  An earlier version of this line said "43 tests pass". That was not a
  count. It was the number of progress dots on pytest's LAST `-q` output line,
  read through `tail -1`, and `-q` wraps its dots across lines. Corrected on
  review of `42c11a2`.
- Red-on-revert, 5 of 5, with each anchor counted:
  - the file findings dropped;
  - equality-only file matching;
  - the now-collected ratchet dropped;
  - both baseline shapes accepted in one entry;
  - a `PYTEST_ADDOPTS` env added to CI's pytest step only, written into
    `ci.yml` and restored.

  After the first review, 3 of 3 more went red:
  - the hard-coded `test_*.py`, caught by a self-removing `*_test.py` and a
    configured `python_files`;
  - the `GITHUB_ENV` check dropped;
  - a `GITHUB_ENV` writer inserted into the real `ci.yml` between the two
    steps, then restored.

  After the second review, 5 of 5 more went red, in two runs (four, then the
  shell pin on its own):
  - the round-1 root-relative matcher, caught by `tests/unit/*_spec.py`;
  - `norecursedirs` ignored;
  - adjacency not required;
  - a `uses:` step inserted into the real `ci.yml` between the two, then
    restored;
  - the shell pin dropped.

  After the third review, 2 of 2 more went red:
  - the gate step's `run` no longer pinned exactly, caught by a two-line
    `run` whose second line writes `$GITHUB_ENV`;
  - `followlinks=False`, caught by a symlinked test directory, both in its
    passing state and with a self-removing file in it.

  After the fourth review, 1 of 1 more went red: the new refusal of any
  `${{ }}` expression in either step's `env`, `working-directory` or `shell`,
  dropped. Equal TEXT is not equal VALUES once an expression is involved,
  because GitHub evaluates `${{ }}` once per step, so
  `${{ steps.gate.outcome == 'success' && '--deselect ...' || '' }}` gives ''
  while the gate runs and a deselect afterwards. Both tests use identical text
  on the two steps. The real `ci.yml` python job has no expressions in those
  fields and stays clean.

## Limits

- The check is per FILE. A module that removes only some of its tests at
  collection is not seen.
- A conftest hook deselecting individual items applies to both collections,
  and is still invisible.
- The environment pin sees what the workflow file shows. A variable a tool
  sets for itself when invoked is not seen.
- The file scan calls `_pytest.pathlib.fnmatch_ex`, a private pytest API, and
  mirrors pytest's walk: it follows symlinked directories and prunes
  `norecursedirs`. Both behaviours were read from pytest 9.1.1, and
  `pyproject.toml` allows `pytest>=8.3`. A pytest release that changes either
  would make the scan drift with nothing to say so. A missing `fnmatch_ex` is
  exit 2. The walk behaviour was read from pytest's collection path,
  `Dir.collect` (main.py) and `Package.collect` (python.py), each `scandir()`
  then `direntry.is_dir()`. It was NOT read from `_pytest.pathlib.visit`, which
  is not on that path; an earlier version cited it.
- Filed from round 4, not fixed here:
  - #627: the pin ignores `continue-on-error:` and `if:`;
  - #628: the scan swallows a scandir error, and counts a broken `test_*.py`
    symlink;
  - #629: "CI's exact argv" is `python -m pytest`, which adds the cwd to
    `sys.path`, where CI runs bare `pytest`.
