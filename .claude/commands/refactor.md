---
description: Codebase-wide refactor pass — finds accumulated complexity, duplication, and drift after multiple sprints. Different from /debugloop which finds bugs; this finds smell. Always TDD-safe: no behaviour changes, tests stay green.
allowed-tools: Read, Edit, Write, Bash(find:*), Bash(npx tsc:*), Bash(npx playwright test:*), Bash(git diff:*)
---

Run a structured refactor pass across the codebase. The goal is to reduce complexity and duplication that has accumulated over multiple sprints — **without changing any behaviour**.

**Ground rule: every test must still pass after every change. If a refactor would break a test, stop and flag it rather than modifying the test.**

---

## Stage 1 — Parallel analysis

Spawn four subagents to analyse in parallel:

### Agent 1 — Duplication Scanner
Read all source files and identify:
- Functions that do the same thing in different places
- Copy-pasted blocks (even with minor variations)
- Similar conditional logic repeated across files
- Constants or magic numbers defined multiple times

Report as: `[FILE:LINE] — duplicate of [FILE:LINE] — description`

### Agent 2 — Complexity Scanner
Read all source files and flag:
- Functions longer than ~25 lines that could be split
- Functions that do more than one thing (detectable by: "and" in the function name, multiple unrelated operations in the body, deeply nested conditionals)
- Files longer than ~200 lines that have grown into catch-alls
- Parameters lists with more than 4 parameters (candidate for an options object)

Report as: `[FILE:LINE] functionName — reason it's complex`

### Agent 3 — Naming & Consistency Scanner
Read all source files and flag:
- Inconsistent naming conventions (camelCase vs snake_case, `get` vs `fetch` vs `load` for similar operations)
- Vague names that require reading the function body to understand (`handle`, `process`, `doThing`, single-letter variables outside loops)
- Inconsistent module/file naming
- Functions named differently than what they actually do

Report as: `[FILE:LINE] — current name — issue — suggested name`

### Agent 4 — Architecture Drift Scanner
Read `ARCHITECTURE.md` and compare against what actually exists:
- Files or modules that exist but weren't planned
- Planned modules that ended up in the wrong place
- Dependencies between modules that shouldn't exist (e.g. UI code importing directly from DB layer)
- `TODO`, `FIXME`, `HACK` comments accumulated in the code

Report as: `[FILE] — description of drift`

---

## Stage 2 — Prioritise and plan

Consolidate all findings into a prioritised refactor plan:

```
## Refactor Plan

### High Priority (complexity or duplication that's actively causing problems)
1. [specific change] — [why it matters]

### Medium Priority (naming and consistency)
2. [specific change]

### Low Priority / Nice to Have
3. [specific change]

### Architecture Drift (flag for discussion, don't auto-fix)
- [item]
```

**Present this plan to me and wait for approval before making any changes.**

---

## Stage 3 — Execute approved refactors

For each approved item, in priority order:

1. Make the change — smallest possible diff that achieves the goal
2. Run `npx tsc --noEmit` — confirm no type errors
3. Run `npx playwright test --reporter=line` — confirm all tests still pass
4. If tests break, **revert the change immediately** and flag it — do not try to fix tests to accommodate a refactor

Do not batch multiple refactors together. One at a time, tests after each.

---

## Stage 4 — Final check

After all approved refactors:

```bash
npx playwright test --reporter=line
npx tsc --noEmit
```

Both must be clean.

Report: what was changed, what was skipped (and why), final test result.
