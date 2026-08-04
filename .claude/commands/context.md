---
description: Snapshot project state into the right docs — CONTEXT.md (state of main, PR-scoped), your context/<name>.md (personal status), and CLAUDE.md (durable lessons). Run at end of session or before a PR.
allowed-tools: Read, Write, Edit, Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git config:*), Bash(git branch:*), Bash(gh pr list:*)
---

Update the project's state docs. Since we split them by volatility, write to the RIGHT file — not everything goes in CONTEXT.md anymore.

## Gather context first

- Who am I: !`git config user.name` — determines which `context/<name>.md` is mine
- Current branch: !`git branch --show-current`
- Recent git log: !`git log --oneline -15`
- Current status: !`git status --short`
- Uncommitted diff: !`git diff HEAD --stat`
- The existing `CONTEXT.md`, my `context/<name>.md`, and `CLAUDE.md`

## Then route each kind of information to its home

### 1. `context/<my-name>.md` — ALWAYS update this
My personal status file (never my collaborator's). Overwrite freely:
- **Branch / in flight** — what branch, what it does, PR # if open
- **Next steps** — ordered, actionable
- **Personal todos** — human-only items on my plate
- **Notes for [collaborator]** — anything they should know that isn't in a PR yet

### 2. `CLAUDE.md` — append durable lessons, if any were learned this session
Only facts that outlive the current sprint: new environment gotchas, tooling
traps, conventions decided. Add to the relevant existing section — don't
duplicate what's already there, and don't add session-specific status.

### 3. `CONTEXT.md` — update ONLY if this session's work ships in a PR
CONTEXT.md describes the project as of `main` and changes as part of a PR
(typically the end-of-sprint commit). If updating it, keep the established
structure: Current state / Backlog / Needs a human / Test coverage status.
Point at `SPRINT_<n>.md` and PR descriptions for detail rather than inlining
sprint history. If this session's work is NOT heading into a PR yet, leave
CONTEXT.md alone — my context file carries the in-flight state.

### 4. `DECISIONS.md` — append a D-number entry if a real decision was made
(disclosure posture, product behavior, architectural choice). Skip otherwise.

After writing, print a short confirmation: which files changed, what the key
updates were, and flag anything that looks like a risk or blocker.
