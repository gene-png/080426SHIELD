# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (Five PRs merged; item 0 confirmed blocked on Gene's key; session-length measured from git history)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision.

## Branch / in flight

`main` now has **#78, #80, #76, #49, #50 merged**, in the order given. **#81 (MVP plan doc) is rebased, statuses updated, CI running** — merges automatically once green per the agent's own plan, no objection raised. Only **#29** remains parked (do-not-merge, gated on W2 + clean audit, stated independently in both this file and DELIVERY_PLAN.md).

**Next action after #81 lands:** start the export-target trio (#73/#75/#79) — item 1 in the MVP path table, no dependencies, can run any time.

## Item 0 (#51, live-AI verification) — confirmed blocked on Gene, not the agent

Real diagnosis, not a shrug: `ANTHROPIC_API_KEY` is present, well-formed (108 chars, `sk-ant-` prefix), and returns 401 anyway — expired, revoked, or wrong-account, not missing. No OpenAI/Gemini fallback configured. `.env` already has `SHIELD_LLM_MODE=live`, `SHIELD_LLM_MODEL=claude-opus-5`. The agent correctly refused to procure or touch a credential — same boundary I operate under. **This is genuinely on Gene, not a stalled agent.**

**What Gene needs to do, and what I told him:** replace the value directly in `.env` (or via the other Claude Code session, on his own machine) — **never paste the key value into chat with me**, credential material doesn't travel through a relay conversation. Before swapping, check two separate things in the Anthropic console, since a revoked key and a valid-but-wrong-tier key both 401 identically: (1) is the key itself still active, (2) does that key's account actually have access to `claude-opus-5` specifically, with billing/credits attached. `live_llm_readiness()` fails fast at startup, so a bad key/model pair surfaces immediately rather than mid-run — fast feedback once it's swapped.

**Status: open, waiting on Gene.** Once resolved, item 0 is ~1 session: 6 of 8 ZT reason codes and the CSF ones have never been observed against a real model, plus the two new shape-guard 502 paths. Two reason codes flagged as **can't be exercised this way at all**, noted rather than faked: `protected` is fixture-only by construction, `locked` needs an API-seeded lock. Real token cost involved.

## Session length — measured from git history, not estimated

Three data points: W1 ZT (#66), 5 rounds, ~8.5h dense elapsed to round 3 plus 2-3h for rounds 4-5. CSF dashboard (#80), 1 round, ~4h. Shape guards + #67 (#78), 1 round, ~2-3h. Conclusion stated in the doc: **1 session ≈ 4-8 hours of continuous work**, varying with adversarial rounds at roughly 1-3h each. On that basis, **6-10 remaining sessions ≈ 35-65 hours ≈ 7-12 working days at 5h/day** — this is where "two to three weeks" came from, now traceable rather than asserted.

Two caveats the agent wrote into the doc itself, unprompted: this is an agent's throughput with parallel subagents, not a human developer's rate, don't size someone else's week against it. And **W2 is the estimate most likely to be wrong, upward** — largest item, touches scoring, and every scoring-adjacent item so far has taken 4-5 rounds instead of 1. Also self-corrected an earlier framing: raw commit-timestamp gaps include idle time, not effort, and the doc now says so explicitly.

**My read:** the range itself is trustworthy — measured, not guessed, with the direction of likely error flagged rather than hidden. The exact 4-8h/session figure isn't cleanly re-derivable from the three data points shown (they cluster closer to 2-4h individually), which reads as "session" bundling more than one round in places. Minor, not worth blocking on — the W2-will-run-long warning is the more important part and I trust it.

## MVP completion path — table, dependencies, still current

See PR #81 / DELIVERY_PLAN.md for the full table (order, status, blocker, size per item). Unchanged from the last entry except: #80 is now MERGED (was IN REVIEW), and #81 itself is rebased/pending its own merge. Everything else in the 9-row table (items 1, 3-8) is still Not started, per the plan doc's own convention of updating status in the PR that lands the item.

## #44 — needs_review placement (resolved, reversed from my original call)

I originally recommended `needs_review` live inside `dropped` with its own reason code. The other agent pushed back with a rigorous argument grounded in the actual W2 plan §5.1 text: `applied` means "written to the record," not "contributed to the score." I conceded — correct. **Final: needs_review counts as applied, tri-state reported as a separate count.** Codified in DELIVERY_PLAN.md.

## W3 (resolved)

Option A — approval-time capability-list membership snapshot, item 4 in the MVP path table. Re-approval behavior still needs to be explicitly stated before implementation, not yet specified — flag if implementation starts before it's answered.

## Risk / W6 (resolved)

Yes — Risk needs the same release guarantees as the other four services. Items 6 and 8 in the MVP path table, both independent, both not started.

## Open decisions — NOT to be reconstructed from memory

- **Item 0 / live-AI key** — blocked on Gene, see above. Do not let anyone (agent or me) attempt to handle the credential value directly.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope per DELIVERY_PLAN.md)

## Environment notes (standing)

- Postgres migrations: [carried forward from prior entry — see commit `8533f10` history for exact gotcha text if needed]
- Provider live key: **the same item 0 blocker above.** A prior entry in this file said this was resolved — it was not; corrected.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md (can't merge until W2 lands plus a clean adversarial audit). Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail. At least 6 confirmed instances (the "#72 pattern"), attaches to W8 (adversarial audit in CI, half done).
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say — root defect family behind #73/#75/CSF-twin.
- A status line that is wrong is worse than none — the stated rationale for DELIVERY_PLAN.md's MVP path section being LIVING by convention.
- Credential material never travels through a relay conversation, even when explicitly offered. Same boundary for the agent and for me.
