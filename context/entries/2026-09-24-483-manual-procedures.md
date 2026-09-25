# 2026-09-24: the two never-run specs become named manual procedures (#483)

Branch `track1/e2e-manual-procedures`, base `20f747f`.

## Why

These specs were gated on variables no workflow sets, so they self-skipped on
every CI run while reading as part of the suite:

- `e2e/smoke/s26-oidc-login.spec.ts`, a SMOKE spec, behind `E2E_OIDC=1`;
- `e2e/perf-admin-management.spec.ts`, behind `E2E_PERF=1`.

## Decision, my call and overturnable: neither runs in CI today

- **The perf spec is a measurement, not a test.** It measures `/admin/management`
  fan-out at a client count CI's empty-volume runners can never reproduce
  (#111). It cannot honestly run in CI.
- **The OIDC spec COULD run in CI, and this PR does not make it.** No new job is
  needed. The e2e job already brings up keycloak, and the #487 step already
  shows the pattern: recreate `api web` with a step-level env, then run one
  spec. So two steps would do it, and condition 1's count is unchanged. What is
  unproven is whether a host browser on the runner completes the Keycloak round
  trip. That proof belongs in its own change, filed as #565, together with the
  flag-off restoration box below. (An earlier draft of this entry said a CI job
  would change condition 1's count. That was false, and the adversarial review
  of this PR caught it.)

So neither is deleted, and neither stays in the suite. Both are now
`e2e/manual/*.manual.ts`, which the default config never collects, run only
through `e2e/playwright.manual.config.ts`. The env gates are removed, so run in
the wrong state they FAIL rather than skipping.

Measured with both configs:
- the default lists 93 tests in 45 files, with neither moved file among them;
- the manual config lists exactly 3 tests in the 2 moved files.

## SMOKE_TEST.md is made honest in the same change

Its §32 ticked the OIDC positive and negative paths citing s26, which never ran
in CI.
- Those two boxes are now unticked, and marked as a manual procedure last run
  green in Sprint 9 T7.
- The dormancy box keeps only what a CI spec proves (`s25` asserts `keycloak`
  dormant on `/ready`). "s26 reports two skipped tests" proved only the skip.
- The ticked **Flag-off restoration** box is left as it was, and it is not
  honest either. Its specs prove the flag-off steady state, not the transition
  back to it. That is pre-existing, and it is filed under #565.

## Interaction with #545

#545's env-gate check exempts `E2E_OIDC` and `E2E_PERF`, and it scans only
`*.spec.ts`. Once this lands, both exemptions are stale, and #545's own gate
reports them as stale. Whichever of the two lands second removes them.
