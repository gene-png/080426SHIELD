---
description: Plan all functions needed for the current sprint. Produces a SPRINT.md with purpose, parameters, process outline, and typed return values for each function.
allowed-tools: Read, Write, Bash(find:*)
---

Plan every function needed for the current sprint and write the plan to the next `SPRINT_<n>.md` (one higher than the latest existing).

## Read first

Before planning anything, read:
- `CONTEXT.md` — current state and next steps
- `docs/architecture.md` — overall structure and data model
- Existing source files to understand what already exists and what patterns are in use (`apps/api/app/`, `apps/web/src/`, `e2e/`)

## Identify the function list

First, identify every function this sprint requires. Write a simple flat list: function names and one-sentence purpose for each.

Present this list and wait for my confirmation before deep-planning.

## Parallel deep-planning

Once the function list is confirmed, spawn one subagent per function. Each subagent independently produces the full plan entry for its function:

```markdown
### functionName

**File:** `src/path/to/file.ts`
**Purpose:** One sentence — what this function does and why it exists

**Parameters:**
| Name | Type | Required | Description |
|------|------|----------|-------------|
| paramName | string | yes | What it represents |

**Process:**
1. Step one — what happens first
2. Step two — what logic runs
3. Step three — what gets returned or side effect produced
Note any: validation that happens, errors that should throw, external calls made

**Returns:** `TypeName` — what it is and what it represents

**Error behaviour:** What this function throws and when. Must throw — not return null or a fallback.

**Debug log:** Where a log line should appear to confirm success

**Tests needed:**
- Happy path: [description]
- Failure case: [description]
- Edge case (if any): [description]
```

Each subagent also identifies: does this function depend on any other function in this sprint? Report back with the entry + dependency list.

## Consolidate and write SPRINT.md

After all subagents complete, consolidate into `SPRINT.md`:

```markdown
# Sprint Plan
_Generated: [date]_

## Goal
[One paragraph — what this sprint delivers]

## Functions to Build

[One entry per function using the format above]

## Build Order
[Ordered list — which functions to build first due to dependencies]
[Mark which functions can be built in parallel — no dependencies on each other]

## Definition of Done
- [ ] All functions implemented
- [ ] All functions type-check with `npx tsc --noEmit`
- [ ] All planned tests written and passing
- [ ] `/debugloop` run and clean
- [ ] `CONTEXT.md` updated
```

After writing the file, print a summary: how many functions are planned, which can be parallelized, the dependency order, and any risks you spotted.
