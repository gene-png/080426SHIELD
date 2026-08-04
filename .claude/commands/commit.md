---
description: Stage all changes and create a conventional commit. Reads the diff to write an accurate message.
argument-hint: [optional short hint for the commit message]
allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git diff:*), Bash(git commit:*), Bash(git log:*)
model: claude-haiku-4-5-20251001
---

## Context

<recent_commits>
!`git log --oneline -5`
</recent_commits>

<current_status>
!`git status --short`
</current_status>

<current_diff>
!`git diff HEAD`
</current_diff>

## Instructions

1. Read the diff above.
2. Review `git status` for anything that should NOT ship (scratch files, artifacts, another task's files) — stage explicitly if in doubt, otherwise `git add -A`.
3. Write a commit message following Conventional Commits format:
   - `feat:` new functionality
   - `fix:` bug fix
   - `test:` adding or updating tests
   - `refactor:` restructuring without behaviour change
   - `chore:` tooling, config, dependencies

   Subject line: imperative mood, under 72 chars, lowercase after the type prefix.
   If the change is non-trivial, add a short body (1–3 lines) explaining the *why*.
   End the body with the current model's co-author line
   (`Co-Authored-By: Claude <model> <noreply@anthropic.com>`).

4. If `$ARGUMENTS` was provided, use it as guidance for the message.

5. Commit with the message.

Show me the final commit message before committing and confirm once done.
