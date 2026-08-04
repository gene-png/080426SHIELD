---
description: End-of-session wrap-up. Runs review → tests → debug loop → security audit → commit → context snapshot. One command to cleanly close out a session.
allowed-tools: Read, Write, Edit, Bash(npx playwright test:*), Bash(npx tsc:*), Bash(npm audit:*), Bash(git diff:*), Bash(git status:*), Bash(git add:*), Bash(git commit:*), Bash(git log:*), Bash(grep:*), Bash(find:*)
---

Close out this session cleanly. Run the full wrap-up sequence in order.

---

## Stage 1 — Review

Run `/review` inline.

Check all uncommitted changes against the four project principles:
- TDD: tests exist for all new behaviour
- Fail loudly: no silent catches or fallback returns
- Simple: no unnecessary complexity
- Debug logs: success paths are logged

**If critical issues are found** (missing tests, silent error handling), fix them before proceeding. Minor style issues can be noted but don't block shipping.

---

## Stage 2 — Test

Run `/test` inline — the real gates from `CLAUDE.md`, per layer touched:

```bash
cd e2e && npx playwright test --reporter=line                 # browser flows (force-recreate web first if apps/web changed)
docker compose exec -T api pytest -m unit -q                  # if API code changed (PATH export first)
docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"   # if web TS changed
```

All tests must be green before proceeding. Fix any failures — fix the code, not the tests.

---

## Stage 3 — Debug loop

Run `/debugloop` inline.

Full audit: types, logic, spec compliance, coverage. Fix everything found.

This stage ensures nothing slips through that `/review` and `/test` missed.

---

## Stage 4 — Security audit

Run `/audit` inline.

Check for:
- `pnpm audit` (root) and `npm audit` (in `e2e/`) critical and high vulnerabilities
- Hardcoded secrets or API keys
- OWASP Top 10 patterns

**If critical vulnerabilities or hardcoded secrets are found, stop and flag them to me before committing.** These are blockers. High vulnerabilities should be noted in the commit message if not immediately fixable.

---

## Stage 5 — Commit

Run `/commit` inline.

Stage all changes and write a conventional commit message based on the diff. Show me the message before committing.

---

## Stage 6 — Snapshot context

Run `/context` inline.

Route updates to the right docs: always my `context/<name>.md` (personal status + next steps); `CLAUDE.md` for any durable lessons learned; `CONTEXT.md` only if this work is going into a PR.

---

## Final output

Print a session summary:
- What was built or changed
- Test result (pass count)
- Security audit result (clean / issues found)
- Commit message used
- Top 2–3 next steps for next session

**You're done. Pick up next time with `/pickup`, then `/sprint` or `/execute`.**
