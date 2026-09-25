# 2026-09-24: a test that exists but CI never runs is now a finding (#540)

Branch `feat/540-ci-selection-gate`, base `3286109`.

## Why

A test that exists, is believed to run, and does not is worse than a vacuous
test, which at least reports. Both instances turned up in one day:

- the #535/#536 leak tests shipped unmarked, so CI's `pytest -m unit
  tests/unit` would have selected 0 of their 61 tests, while local runs that
  named the file directly passed;
- #483: `E2E_PERF` and `E2E_OIDC` gated specs that no workflow set, until #560
  (`06fa7ce`) moved them to `e2e/manual/`.

`check_test_integrity.py` catches tests that cannot fail. Nothing caught tests
that never run. It is tier-3 by consequence, and it is the gate that protects
every other gate.

## What changed: the checks, all wired into CI

- **`check_ci_selection.py`** (Python job). It collects `tests/unit` as NODE IDS
  with the real pytest, once with CI's selector and once with none. Every
  collected test that is not selected is a finding, unless its id is baselined
  with a reason (`.github/ci-selection-baseline.json`). A test parses ci.yml
  and requires the selector to EQUAL CI's `run:` line.
- **`check_e2e_env_gates.py`** (Python job). Every variable read by a spec that
  skips must be set by a workflow, or exempted with a reason AND the specs the
  exemption covers (`.github/e2e-env-gate-exemptions.json`). An unlisted spec
  reading an exempted variable is a finding, and so is a listed spec that no
  longer reads it. The workflows are parsed as YAML: a comment is not a
  setting, and empty, `"0"` and `"false"` are not enabling values.
- **`check_e2e_spec_listing.py`** (E2E job, the owner's design). It compares
  the specs on disk with `npx playwright test --list`, run with the same cwd
  and arguments as the real run step (pinned by a test). Since #579, EVERY
  script file under `e2e/` must be in that listing or declared a non-suite
  file, with a reason, in `.github/e2e-non-suite-files.json`.

**Ratchets.** A baselined test that now runs or no longer exists is a finding,
and so is an exemption for a variable now set or no longer read. So the
backlog only goes down, and every run prints what it allows.

**Fail closed (D-051).** A wrong directory, an empty or unparseable collection
or listing, a malformed baseline, or a workflow that does not parse exits 2.

## Review found, and this round fixed

- **Workflow text was matched raw.** ci.yml's own comment
  `# SHIELD_DEMO_SMOKE=1` counted as setting it, so deleting the real env line
  would have passed.
- **The selector pin was a substring**, so `-k "not slow"` appended in CI would
  have passed.
- **`parents[4]` raised IndexError in the api container.** The repo root is now
  found with `find_workflows_dir`, skipping only where there is none.
- **A per-file COUNT let a new never-run test replace an old one.** The
  baseline is now node ids.
- **The env and skip patterns missed** `process.env["X"]`, destructuring,
  `test.describe.skip`, `test.fixme` and `testInfo.skip`.
- **The owner's specs-on-disk-vs-CI-run check had not been built.** It is now
  `check_e2e_spec_listing.py`.
- **PyYAML is declared** (dev extras), rather than arriving transitively
  (bandit, `uvicorn[standard]`).
- **(Reviews of 324dc15 and adaf082.) The collections cleared addopts, which
  CI applies.** A `--deselect` there would have narrowed CI with the gate
  still clean. Reading named config files to make up for it was the second
  attempt, and it missed native `[tool.pytest]`, `tox.ini`, `setup.cfg` and
  config files in the test directories. The SELECTED collection now runs CI's
  argv with the config left alone, and a probe plugin reports what pytest
  itself collected: a derivation, not a reader.
- **(Review of 701f032.) `PYTEST_ADDOPTS` reached both collections**, because
  pytest prepends it before the ini is read and `-o addopts=` does not clear
  it. The unselected collection now runs without it.
- **(Review of 3bc0975.) An exemption keyed on the variable alone covered every
  future spec that reads it.** Exemptions now name their specs; a missing,
  string, empty or non-string `specs` is could-not-look, and the string and
  empty-list branches are pinned by tests since #580.

## This PR was red when it opened, for the reason the gate exists

The gate catches one class of defect: a test that exists and CI never runs,
while a local run passes. That class broke this PR's own CI.

- The new gates carry the crash handler, so `discover_gates` finds them.
  They had no entry in `test_gate_crash_exit_code.GATES`.
  `test_universe_equals_the_other_gate_enumeration` failed on BOTH heads,
  `d3aeaaf` and `7bbd791`.
- The author's local runs named `test_gate_crash_exit_code.py`, where the list
  lives, and never `test_gate_fixtures_harness.py`, where the equality check
  lives. So everything the author ran was green.
- The author then reported the PR as waiting only on merge order, without
  re-reading its checks.

It was the second time on 2026-09-24 that a local run and CI disagreed. The
first was the #535/#536 tests shipping unmarked, which is why this gate
exists. The check that catches "CI never runs this" was itself broken by "the
author ran it locally and CI did not". **A local run proves what it selected,
never what CI selects.** That is the strongest argument for this gate, and it
is also why the gate asks pytest rather than trusting a person's selection.

Fixed at `d95521d`: the harness files and the gate test files pass in
the api image.

## The backlog, allowed with reasons rather than hidden

- **pytest:** 9 tests in 2 files (#500): 8 in `test_admin_removal.py` and 1 in
  `test_self_assessment.py`.
- **Playwright env gates:** `E2E_API_URL` is exempted as configuration with a
  default. `E2E_PERF` and `E2E_OIDC` (#483) were exempted until #560 merged
  (`06fa7ce`). #560 renamed both specs to `e2e/manual/*.manual.ts` and removed
  their env reads, so no scanned `*.spec.ts` reads either, and the gate
  reported both exemptions as stale. This PR landed second, so it removed
  them.
- **Playwright listing:** every spec file on disk is in CI's run. The count is
  `cd e2e && npx playwright test --list`, not a number written here. It was 47
  before #560 moved the OIDC and perf specs out of the suite.

## Limits

- A variable read in an imported helper is unseen.
- A spec that skips on runtime state (s21, s22, s23, s32) is unseen.
- "Set by some workflow" does not check that it is set in the step that runs
  the spec, nor the exact value the spec needs.
- A selected test that skips at runtime is not a selection question.
- A module-level `pytest.skip(..., allow_module_level=True)` drops the file
  from both collections: a smaller denominator, not a finding (#543). So does
  a conftest hook that deselects.
- The listing compares spec FILES; an unconditional `test.skip()` is listed and
  never runs, and neither Playwright gate reports it.
- Until #579 both Playwright gates scanned only `*.spec.ts`, so a spec renamed
  out of that pattern left CI with both green. Now the listing gate requires
  every script file to be listed or declared, and the env-gate scan uses
  Playwright's default testMatch (refusing a config that sets its own). A
  declared DIRECTORY (`helpers/`) still hides an out-of-pattern name under it
  (`helpers/s9.specs.ts`); a spec-named file there is listed and reported.
