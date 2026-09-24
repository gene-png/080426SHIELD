# 2026-09-24: a test that exists but CI never runs is now a finding (#540)

Branch `feat/540-ci-selection-gate`, base `3286109`.

## Why

- **A test that exists, is believed to run, and does not.** That is worse than
  a vacuous test, which at least reports. Both instances turned up in one day:
  - the #535/#536 leak tests shipped unmarked, so CI's
    `pytest -m unit tests/unit` would have selected 0 of their 61 tests, while
    local runs that named the file directly passed;
  - #483: `E2E_PERF` and `E2E_OIDC` gate specs that no workflow sets.
- **`check_test_integrity.py` catches tests that cannot fail. Nothing caught
  tests that never run.** It is tier-3 by consequence, but it is the gate that
  protects every other gate.

## What changed

- **`check_ci_selection.py`** collects `tests/unit` with the real pytest,
  twice: once with CI's selector (pinned to ci.yml by a test) and once with
  none. Any file with unselected tests is a finding unless baselined with a
  reason (`.github/ci-selection-baseline.json`).
- **`check_e2e_env_gates.py`** requires every `process.env.X` read by a spec
  that calls `test.skip(` to be set by a workflow, or exempted with a reason
  (`.github/e2e-env-gate-exemptions.json`). `--list` cannot see runtime skips,
  so the check is static.
- **Both ratchet.** An entry that grows, shrinks or goes stale is a finding,
  and every run prints what it allows.
- **Both fail closed (D-051).** A wrong directory, an empty collection, an
  unparseable format or a missing baseline exits 2.
- **Both are wired into the Python job**, with fixture cases in `tests/gates`.

## The backlog, baselined rather than hidden

- **pytest:** 9 tests in 2 files: `test_admin_removal.py` 8, and
  `test_self_assessment.py` 1 (#500).
- **Playwright:** `E2E_PERF` and `E2E_OIDC` (#483). `E2E_API_URL` is exempted
  as configuration with a default.

## Proof

- **Tests first**, 14 and 12, all selected by CI's `-m unit`.
- **Red-on-revert** on every core branch, each naming its test.
- **Against the real repo**, with an empty baseline:
  - the pytest half reports exactly the 9 tests measured in the Linux image;
  - the Playwright half reports exactly `E2E_API_URL`, `E2E_OIDC` and
    `E2E_PERF`.
- **Fixture harness:** 65 cases across 13 gates.

## Limits

- A spec that skips on runtime state, not a variable (s21, s22, s23, s32), is
  invisible.
- "Set by some workflow" is coarse. A variable set in a different step from the
  one that runs the spec passes.
- A test that is selected but skips at runtime is not a selection question.
