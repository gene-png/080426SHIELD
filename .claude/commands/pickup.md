---
description: Start-of-session orientation. Reads project state, your collaborator's status, and open PRs, then briefs you in plain English — what's done, what's in flight, what to do next. Run this first when picking up after a break.
allowed-tools: Read, Bash(git log:*), Bash(git status:*), Bash(git diff:*), Bash(git config:*), Bash(git branch:*), Bash(gh pr list:*), Bash(gh pr view:*)
---

Orient me quickly. I'm picking up after a break and need to know exactly where things stand.

## Gather context

Read all of these before writing anything:
- Who am I: !`git config user.name` — maps to `context/dave.md` or `context/gene.md` (my file); the other file is my collaborator's.
- `CONTEXT.md` — project status as of main
- `context/dave.md` and `context/gene.md` — mine for where I left off, my collaborator's for what they have in flight
- Current branch: !`git branch --show-current`
- Recent git history: !`git log --oneline -10`
- Uncommitted work: !`git status --short`
- Any uncommitted diff: !`git diff HEAD --stat`
- Open PRs (mine AND my collaborator's): !`gh pr list --state open`
- The current `SPRINT_<n>.md` if one is active or staged (highest n; check `.claude/sprint-queue*.json` for loop state)

(Durable facts — principles, real test commands, environment gotchas — are in `CLAUDE.md`, already loaded. Don't re-summarize them at me.)

## Then give me a crisp briefing in this format

---

### 📍 Where We Are
[2–3 sentences. What phase is the project in right now?]

### ✅ Just Completed
[Bullet list — specific things finished recently, mine and my collaborator's (from merged PRs). Reference files and commits, not vague summaries.]

### 👥 Collaborator Activity
[What the other developer has open or in flight — from their context file and their open PRs. One or two bullets; "nothing in flight" is a fine answer.]

### 🔧 In Progress / Unfinished
[Anything started but not done. Uncommitted work, open PRs awaiting review, half-done tasks from MY context file.]

### ⚠️ Blockers or Risks
[Anything broken, deferred, or flagged that I should know before diving in. Include potential collisions with my collaborator's open work. If none, say so.]

### 🎯 Recommended Next Action
[The single most important thing to do right now — one concrete action, not a list.]

### 📋 Full Next Steps (after that)
[Ordered list — pulled from my context file, CONTEXT.md, and the active sprint doc]

---

Keep this tight. The goal is orientation in under 60 seconds, not reproducing the docs at me. If there's uncommitted work, flag it prominently — I may have left something half-done.

**Finish with:** "Ready. What would you like to do?" — then wait for me.
