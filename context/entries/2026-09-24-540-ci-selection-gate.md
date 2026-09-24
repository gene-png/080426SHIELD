# 2026-09-24: a test that exists but CI never runs is now a finding (#540)

Branch `feat/540-ci-selection-gate`, base `3286109`.

## Why

A test that exists, is believed to run, and does not is worse than a vacuous
test, which at least reports. Both instances turned up in one day:

- the #535/#536 leak tests shipped unmarked, so CI's `pytest -m unit
  tests/unit` would have selected 0 of their 61 tests, while local runs that
  named the file directly passed;
- #483: `E2E_PERF` and `E2E_OIDC` gate specs that no workflow sets.

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
  skips must be set by a workflow, or exempted with a reason
  (`.github/e2e-env-gate-exemptions.json`). The workflows are parsed as YAML: a
  comment is not a setting, and empty, `"0"` and `"false"` are not enabling
  values.
- **`check_e2e_spec_listing.py`** (E2E job, the owner's design). It compares
  the specs on disk with `npx playwright test --list`, run with the same cwd
  and arguments as the real run step (pinned by a test).

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
- **PyYAML is declared** (dev extras), rather than arriving through bandit.

## The backlog, allowed with reasons rather than hidden

- **pytest:** 9 tests in 2 files (#500): 8 in `test_admin_removal.py` and 1 in
  `test_self_assessment.py`.
- **Playwright env gates:** `E2E_PERF` and `E2E_OIDC` (#483). `E2E_API_URL` is
  exempted as configuration with a default.
- **Playwright listing:** all 47 spec files on disk are in CI's run today.

## Limits

- A variable read in an imported helper is unseen.
- A spec that skips on runtime state (s21, s22, s23, s32) is unseen.
- "Set by some workflow" does not check that it is set in the step that runs
  the spec, nor the exact value the spec needs.
- A selected test that skips at runtime is not a selection question.
