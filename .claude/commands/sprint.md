---
description: Sprint orchestrator for an existing project. Plans the next sprint, executes it with TDD, runs the debug loop, and snapshots context. Use at the start of each new sprint.
argument-hint: [optional: brief description of this sprint's goal]
allowed-tools: Read, Write, Edit, Bash(npx playwright test:*), Bash(npx tsc:*), Bash(git diff:*), Bash(git status:*), Bash(git log:*), Bash(find:*)
---

Run the full sprint cycle. This will plan, build, debug, and snapshot in one sequence.

## Sprint goal
$ARGUMENTS

---

## Stage 1 — Orient

Read the current state of the project before anything else:
- `CONTEXT.md` — state of main
- `context/dave.md` + `context/gene.md` — what's in flight on both sides
- `DELIVERY_PLAN.md` — the sprint roadmap
- Open PRs: !`gh pr list --state open`
- Recent git log: !`git log --oneline -10`

(`CLAUDE.md` conventions are already loaded. For long autonomous sprints use
`/loop-sprint-cron` with a staged queue instead — this command is the
interactive, single-session variant.)

Summarise what this sprint will deliver in 3–5 bullet points. If `$ARGUMENTS` was provided, use it to focus the scope. If not, derive the goal from `CONTEXT.md`'s "Important Next Steps."

**Show me the sprint goal and wait for my confirmation before proceeding.**

---

## Stage 2 — Plan functions

Run `/planfunction` inline.

Produce `SPRINT.md` with full typed function signatures, process outlines, and test plans for everything this sprint requires.

Present the plan. Wait for confirmation.

---

## Stage 3 — Execute (with parallelization)

Read `SPRINT.md` and identify the dependency graph before building anything:
- Which functions depend on other functions in this sprint?
- Which functions are completely independent of each other?

**For independent functions:** spawn one subagent per function. Each subagent runs a full TDD cycle for its function simultaneously:
1. Write the test
2. Confirm it fails
3. Implement the minimum to pass
4. Confirm it passes
5. Report back: function name, test result, files changed

**For dependent functions:** build in dependency order, sequentially. A function cannot be started until its dependencies are green.

After all subagents complete, run the full gate set to confirm nothing conflicts (commands in `CLAUDE.md`): `cd e2e && npx playwright test --reporter=line`, plus in-container pytest / tsc for the layers touched.

---

## Stage 4 — Debug loop

Run `/debugloop` inline.

Full multi-agent audit on everything written this sprint:
- Type errors
- Logic and runtime issues
- Spec compliance against `SPRINT.md`
- Test coverage gaps

Fix everything found. Do not finish this stage until tests are green and the audit is clean.

---

## Stage 5 — Snapshot context

Run `/context` inline.

Update `CONTEXT.md`:
- Move this sprint's work to "Just Completed"
- Update "Current State"
- Update "Important Next Steps" with what comes after

---

## Final report

Print:
- Sprint goal and whether it was fully delivered
- Functions built (count and names)
- Test results
- Any issues found in debug loop and how they were resolved
- What the next sprint should focus on
