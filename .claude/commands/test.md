---
description: Lightweight test runner — run the suite that matches what changed (e2e, pytest, tsc) and fix any failures. Use mid-work to stay green. For a deep end-of-session audit, use /debugloop instead.
argument-hint: [optional e2e spec file or pytest -k pattern]
allowed-tools: Bash(npx playwright test:*), Bash(cd e2e:*), Bash(docker compose exec:*), Bash(export PATH:*), Read, Edit, Write
---

Run the tests that cover what changed (see `CLAUDE.md` for the canonical commands):

- **e2e (browser flows):** `cd e2e && npx playwright test $ARGUMENTS --reporter=line` — host-run, base URL http://localhost:3000. If `apps/web` source changed since the containers started, `docker compose up -d --force-recreate web` FIRST (bind-mount hot-reload gotcha).
- **API changes:** `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin" && docker compose exec -T api pytest -m unit -q` (run detached and poll if the shell may time out).
- **Web TS changes:** `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`

If only one layer changed, run only that layer's suite; run all three before a commit that touches multiple layers.

## If all tests pass
Report the result and stop.

## If any tests fail
For each failure:

1. **Read the failure message carefully.** Understand what the test expected vs. what actually happened.

2. **Find the root cause in the implementation** — not in the test. Do not modify test assertions to make them pass unless the test itself has a genuine bug (wrong selector, wrong URL, etc.). If you believe a test needs changing, say so explicitly and explain why before touching it.

3. **Fix the implementation.**

4. **Re-run the tests** to confirm green.

5. **Do not introduce graceful fallbacks to silence a failure.** FAIL LOUDLY is a project principle — if the test is failing because something is broken, fix what is broken. Never add try/catch to hide the error.

Known flake (not a defect): next-dev cold-compile timeouts under back-to-back e2e load — one clean re-run is the fix; don't rewrite specs for it.

Report what you found, what you changed, and the final test result.
