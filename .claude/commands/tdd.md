---
description: Start a TDD cycle for a feature or function. Writes a failing test first, confirms it fails, then implements.
argument-hint: <description of the feature or function to build>
allowed-tools: Read, Edit, Write, Bash(npx playwright test:*)
---

We are doing TDD. Follow this sequence strictly — do not skip steps.

## The feature to build
$ARGUMENTS

## Steps

1. **Write the test first.** API behaviour: a pytest under `apps/api/tests/unit/`. Browser behaviour: a Playwright spec under `e2e/smoke/` (or `e2e/` subdir that fits). The test must target the described behaviour. Do not create any implementation code yet.

2. **Run the test and confirm it fails.** Use the matching command from `CLAUDE.md` (in-container pytest, or `cd e2e && npx playwright test <file>`). Show me the failure output. If the test passes immediately, stop — something is wrong. Either the test is not actually testing the right thing, or the implementation already exists. Flag this before proceeding.

3. **Write the minimum implementation to make the test pass.** No extra features, no defensive abstractions, no speculative generality. Just enough to go green.

4. **Run the test again and confirm it passes.** Show me the passing output.

5. **Review for simplicity.** If anything in the implementation is more complex than it needs to be, simplify it now. Do not add cleverness.

6. **Check error handling.** Ensure any failure modes throw explicitly — no silent catches, no fallback returns that hide errors.

7. **Confirm debug logs are in place** at key points: after the main operation completes, and at any branch that isn't obvious.

Report the result of each step before moving to the next.
