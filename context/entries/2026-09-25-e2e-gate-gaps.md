# 2026-09-25: the Playwright gates see every file, and two refusals are pinned (#579, #580)

Branch `track1/e2e-gate-gaps`, branch-start base `2028f38`.

## #579: a spec renamed out of `*.spec.ts` left CI with both gates green

**The fix chosen, my call and overturnable:** the listing is the ground
truth. `check_e2e_spec_listing.py` now compares `npx playwright test --list`
with EVERY script file under `e2e/` (`.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`,
`.cjs`, `.mts`, `.cts`). Each must be listed or declared a non-suite file,
with a reason, in `.github/e2e-non-suite-files.json`: `helpers/`, `manual/`,
the global setup and teardown, and both configs. A declaration matching no
file is stale, and one naming a listed file is a contradiction; both are
findings. A missing or malformed declarations file is exit 2.

This does not read `testMatch` from the config. The listing already applies
the config exactly, so reading the config would be a second, weaker source.
`check_e2e_env_gates.py`, which has no listing, scans Playwright's DEFAULT
testMatch (`*.spec|test.[cm][jt]s[x]`) instead of `*.spec.ts`, and refuses
with exit 2 if `playwright.config.ts` sets its own `testMatch`.

**Measured on the real tree**, 2026-09-25: `npx playwright test --list` in
this worktree (93 tests in 45 files) against the new gate gives clean, with
57 script files: 45 in the run and 12 declared non-suite, across 6
declarations.

**Limit:** a declared directory covers any file added under it, so a spec
written into `helpers/` is not reported. The declaration's reason is the only
guard there.

## #580: two exemption refusals had no test

`_load_exemptions` refuses a `specs` that is a string or an empty list with
exit 2, and nothing pinned either. Both are now parametrized cases beside the
missing and non-string ones. The #540 landing entry now describes
spec-scoped exemptions and the #579 limit.

## Proof

Red on revert, nine mutations, each red on its named test: a string `specs`
accepted; an empty `specs` accepted; the env scan back to `*.spec.ts`; the
`testMatch` refusal removed; the listing's disk scan back to `*.spec.ts`; its
listed-file pattern back to `.spec.ts`; the declared-but-listed check removed;
the stale-declaration check removed; a missing declarations file read as none.

The existing listing tests and fixtures gained an empty declarations file,
because the file is now a required input. One test's expected clean line
encoded the old message ("all 2 spec file(s)"); that expectation was about
the old output, so it was updated.
