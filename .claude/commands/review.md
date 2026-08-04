---
description: Review current changes against project principles — TDD, fail loudly, simplicity, and debug logging.
allowed-tools: Bash(git diff:*), Bash(git status:*), Read
---

## Context

<current_diff>
!`git diff HEAD`
</current_diff>

<staged_changes>
!`git diff --cached`
</staged_changes>

## Review Instructions

Review the changes above against these four principles (defined in `CLAUDE.md` — they apply to Python and TypeScript alike). For each one, give a clear pass/fail and specific line references for any violations:

### 1. TDD — Tests written first
- Is there a test for every new piece of behaviour?
- Are any tests obviously written after the fact (i.e., testing only the happy path in a way that mirrors the implementation too closely)?
- Flag any new functions or logic that have no corresponding test at all.

### 2. Fail Loudly — No silent failures
Look specifically for:
- `catch` blocks that swallow errors (`catch (e) { return null }`, `catch (e) { console.error(e) }` without re-throwing); in Python: bare `except:` or `except Exception: pass`
- Functions that return `null`/`None`, or a default value on failure instead of throwing/raising
- API calls or async operations with no error handling at all
- Optional chaining (`?.`) or `.get(..., default)` used where a missing value is actually a bug, not an expected case
- API errors surfaced raw instead of as typed `{reason, message}` details (the D-016 pattern)

### 3. Simple Code
- Are there any functions longer than ~20 lines that should be split?
- Is there abstraction or generalisation that isn't yet needed?
- Are there any names (variables, functions) that are vague or require reading the body to understand?

### 4. Debug Logging
- Are there `console.log` statements (or equivalent) confirming success at key operations — not just on failure?
- Are logs using a consistent `[module]` prefix?
- Is anything missing a log where a future reader would wonder "did this actually run?"

## Output Format
For each principle: **PASS** or **FAIL**, followed by specific observations. If everything is clean, say so plainly.
