---
description: Deep multi-agent audit — type errors, logic bugs, spec compliance, and test coverage gaps, then fixes everything found. Use at end of session or after a large implementation. For a quick mid-work test run, use /test instead.
allowed-tools: Read, Edit, Write, Bash(npx tsc:*), Bash(npx playwright test:*), Bash(git diff:*), Bash(find:*)
---

Run a structured debug loop on the current codebase. Use subagents to parallelise the checks, then consolidate findings and fix all issues found.

## What to check

<recent_changes>
!`git diff HEAD`
</recent_changes>

<changed_files>
!`git diff HEAD --name-only`
</changed_files>

## Agent 1 — Type & Signature Audit
Spawn a subagent to:
- Check every function in the changed files
- Verify parameter types match how the function is called at every call site
- Verify return types match what callers expect
- Flag any `any` types introduced (TS) or untyped dict-passing across module boundaries (Python)
- Run the typecheck for the layers touched (commands in `CLAUDE.md`): web `tsc --noEmit` in-container; API `pytest -m unit` in-container catches type/contract breaks
- Report findings as a list: `[FILE:LINE] description of issue`

## Agent 2 — Logic & Runtime Error Audit
Spawn a subagent to:
- Read each changed function and trace the execution paths
- Look for: null/undefined dereferences, off-by-one errors, incorrect conditionals, unreachable branches, infinite loops, async/await misuse (missing await, unhandled promises)
- Check that every thrown error includes a useful message with context (not just `throw new Error('failed')`)
- Check that no `catch` block silently swallows an error
- Report findings as a list: `[FILE:LINE] description of issue`

## Agent 3 — Spec Compliance Audit
Spawn a subagent to:
- Read `CONTEXT.md` and any planning docs (the active `SPRINT_<n>.md`, `docs/architecture.md`, `reference-docs/SHIELDv2_Master_Spec.txt` sections relevant to the change)
- Compare what was just written against what was intended
- Flag any function that is missing, named differently than planned, or behaves differently than specified
- Report findings as a list: `[FILE] description of discrepancy`

## Agent 4 — Test Coverage Audit
Spawn a subagent to:
- Check every function in the changed files
- Confirm there is a test covering the main behaviour
- Confirm there is a test covering at least one failure/edge case
- List any functions with no test at all
- Report findings as a list: `[FILE] function name — coverage status`

---

## After all agents complete

Consolidate all findings into a single report:

```
## Debug Loop Report

### Type & Signature Issues
[list or "none found"]

### Logic & Runtime Issues
[list or "none found"]

### Spec Compliance Issues
[list or "none found"]

### Test Coverage Gaps
[list or "none found"]
```

Then **fix every issue found**, in order of severity (type errors and runtime bugs first, then spec issues, then coverage gaps). For each fix:
- State what you are changing and why
- Make the change
- Do not introduce new abstractions to paper over a bug — fix the root cause

After all fixes, run the suites for every layer touched (see `CLAUDE.md` for the exact commands):
```bash
cd e2e && npx playwright test --reporter=line      # plus pytest / tsc in-container as applicable
```

If tests fail, fix the failures before finishing. Do not exit the loop until all tests are green and the report is clean.

Final output: a summary of what was fixed and confirmation of green tests.
