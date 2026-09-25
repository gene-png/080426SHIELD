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

**Limit:** a declared directory covers files under it that the run does not
list. With `testDir: "."` and no `testIgnore`, a spec-NAMED file under
`helpers/` is still listed, so it is reported as declared-but-listed. The hole
is an out-of-pattern name there (`helpers/s9.specs.ts`), and spec-named files
there if a `testIgnore` ever excludes the directory. The declaration's reason
is the only guard for those. (Round 1 stated this limit as "any file", which
was wrong.)

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

## After the first review (`81871d4`)

- **A spec disabled by its final suffix or its case** (`a.spec.ts.disabled`,
  `.bak`, `a.spec.TS`) passed, because only the final suffix was read. A file
  is now a script if ANY suffix in its chain is one, case-insensitively, so
  these are reported. My call, overturnable: this over the alternative of
  comparing every file against a non-script allow-list, because it keeps
  `.json` and `.md` out without a second list to maintain.
- **The env gate's suite pattern stays anchored and case-sensitive**, also my
  call: it models what Playwright COLLECTS, and a disabled file is not
  collected, so scanning it would report its variables as unset gates for a
  spec that cannot run. The listing gate is what reports the disabled file.
- **`testMatch` in shorthand or as a quoted key** was missed by `testMatch:`;
  any mention now refuses (a comment mentioning it fails closed).
- **The limit was misstated** as "any file" under a declared directory. A
  spec-named file there is listed and reported; the hole is an out-of-pattern
  name there, or spec-named files if a `testIgnore` excludes the directory.
  Corrected here, in the gate and in the #540 entry, with a test for the
  directory-key case.
- Red on revert: eleven mutations, the earlier nine plus the suffix chain and
  the `testMatch` pattern, each red on its named test.
