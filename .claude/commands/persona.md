---
description: Generate user personas, get approval, build interaction test plans, run Playwright tests, fix issues found, then run a debug loop to confirm everything is solid.
allowed-tools: Read, Write, Edit, Bash(npx playwright test:*), Bash(find:*)
---

Run a complete persona-driven UX and test cycle. This command has five stages — complete each one before moving to the next.

## Stage 1 — Generate personas

Read `docs/architecture.md` and `CONTEXT.md` to understand the app and its users (`CLAUDE.md` is already loaded).

Generate 3–5 distinct user personas. For each one:

```markdown
### Persona: [Name]

**Who they are:** [2–3 sentences — background, context, technical level]
**Goal:** [What they are trying to accomplish with this app]
**Pain points:** [What frustrates them or what they need to avoid]
**Usage pattern:** [How often, in what context, on what device]
**What success looks like for them:** [The outcome they want]
```

Present the personas to me. **Wait for my feedback before proceeding.** I may ask you to adjust, add, or remove personas. Iterate until I say I'm satisfied.

## Stage 2 — Build interaction test plans

For each approved persona, write a step-by-step interaction walkthrough:

```markdown
### [Persona Name] — Interaction Plan

**Scenario:** [One sentence describing the session]

**Steps:**
1. [What they do — be specific: what they click, type, see]
2. [Next action]
3. [Continue through the full interaction]

**Expected outcome:** [What the UI should show or do at the end]
**Potential failure points:** [Where things could go wrong for this persona]
```

Present these plans to me. **Wait for confirmation** before writing any test code.

## Stage 3 — Write Playwright tests (parallelized)

Spawn one subagent per approved persona. Each subagent independently writes its test file — they have no dependencies on each other and can run simultaneously.

Each subagent is responsible for one persona and must:
- Create `e2e/personas/[persona-name].spec.ts`
- Follow the interaction steps from the approved plan exactly
- Use `getByRole` and `getByLabel` selectors — not CSS selectors
- Assert the expected outcome at the end
- Include a comment at the top identifying which persona and scenario it covers
- Report back: filename created and a one-line summary of what it tests

Wait for all subagents to complete, then run the full suite (host-run; force-recreate web first if `apps/web` changed):
```bash
cd e2e && npx playwright test personas/ --reporter=line
```

Report which passed and which failed.

## Stage 4 — Fix issues found

For each failing test:

1. Determine whether the failure is:
   - **A bug in the app** — fix the implementation
   - **A design issue** — the UI doesn't support the interaction the persona needs (flag this to me before changing the UI)
   - **A test issue** — the test has a wrong selector or incorrect assumption (explain why before changing the test)

2. Fix bugs in the implementation. Do not weaken tests to make them pass.

3. If a design issue is found, describe what the persona needs vs. what exists, propose a fix, and wait for my approval before implementing UI changes.

4. After fixes, re-run the persona tests to confirm green.

## Stage 5 — Debug loop

Run `/debugloop` inline on everything written or changed during this command — test files, implementation fixes, and any UI changes.

Ensure:
- All new code is type-checked
- No silent error handling was introduced
- All persona tests pass
- The general test suite still passes

## Final report

Print:
- The approved personas (names and one-line summary)
- Test results per persona (pass/fail)
- Bugs found and fixed
- Any design issues flagged
- Debug loop result
