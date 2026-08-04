---
description: Execute the current plan (from SPRINT.md or CONTEXT.md next steps), then immediately run a full debug loop on everything written.
allowed-tools: Read, Edit, Write, Bash(npx playwright test:*), Bash(npx tsc:*), Bash(git diff:*), Bash(git status:*), Bash(find:*)
---

Execute the current plan, then debug everything written.

## Step 1 — Read the plan

Read these files before writing a single line of code:
- The active `SPRINT_<n>.md` if one exists (highest n)
- `CONTEXT.md` and my `context/<name>.md` — current state and next steps
- `docs/architecture.md` if relevant
- Any relevant existing source files to understand what's already built

Summarise what you are about to build in 3–5 bullet points. This is your execution plan. **Show it to me and confirm before proceeding.**

## Step 2 — Execute using TDD

For each item in the plan:

1. Write the test first
2. Confirm it fails
3. Write the minimum implementation to pass it
4. Confirm it passes
5. Move to the next item

Do not batch-write implementation and then tests. One cycle at a time.

Follow all project principles from `CLAUDE.md`:
- Throw on errors — no silent fallbacks
- Simple functions, single responsibility
- Debug logs at key points

## Step 3 — Run the full debug loop

After all items are implemented, run `/debugloop` inline — do not skip this step.

Specifically:
- Type-check all new code with `npx tsc --noEmit`
- Check all function signatures and call sites
- Check all error handling throws rather than swallows
- Verify spec compliance against what was planned in Step 1
- Check test coverage

Fix everything found before finishing.

## Step 4 — Snapshot context

After the debug loop is clean, run `/context` inline (updates my
`context/<name>.md`, and `CONTEXT.md` only if this ships in a PR).

## Step 5 — Final report

Print:
- What was built
- Test results (pass count)
- Any issues that were found and fixed during debug loop
- What comes next
