# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (Continuity check — PR #81 checks status confirmed, session state as of last exchange)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50 merged**, in the order given. **#81 (MVP plan doc) is open, not yet merged.** Checks: 4/5 green (Python, Web, Secret scan, E2E). The fifth, **Demo (hosted-demo reset + journey spec), was cancelled** after Playwright's Chromium install hung ~23 minutes on an apt-mirror timeout — an infra flake unrelated to the docs content, not a real failure. GitHub reports the PR as mergeable despite this. Only **#29** remains parked (do-not-merge, gated on W2 + clean audit).

**Next action once #81 is in:** start the export-target trio (#73/#75/#79) — item 1 in the MVP path table, no dependencies.

## Item 0 (#51, live-AI verification) — blocked on Gene, open

`ANTHROPIC_API_KEY` is present, well-formed (108 chars, `sk-ant-` prefix), returns 401 anyway — expired, revoked, or wrong-account, not missing. No fallback provider configured. `.env` already has `SHIELD_LLM_MODE=live`, `SHIELD_LLM_MODEL=claude-opus-5`.

**What's needed from Gene:** replace the key value directly in `.env` (own machine or the other Claude Code session) — **never paste the key value into chat with either agent**, credential material doesn't travel through a relay conversation. Before swapping, check in the Anthropic console: (1) is the key itself still active, (2) does that key's account have access to `claude-opus-5` specifically with billing/credits attached — a revoked key and a valid-but-wrong-tier key both 401 identically. `live_llm_readiness()` fails fast at startup once swapped.

**Status: still open, nothing new since last exchange.** Once resolved: ~1 session, 6 of 8 ZT reason codes + CSF ones never observed against a real model, plus two new shape-guard 502 paths. Two reason codes can't be exercised this way at all: `protected` (fixture-only by construction), `locked` (needs an API-seeded lock).

## Session length — measured from git history

W1 ZT (#66): 5 rounds, ~8.5h to round 3 + 2-3h for rounds 4-5. CSF dashboard (#80): 1 round, ~4h. Shape guards (#78): 1 round, ~2-3h. Conclusion: **1 session ≈ 4-8 hours**, so **6-10 remaining sessions ≈ 35-65 hours ≈ 7-12 working days at 5h/day** — traceable, not asserted. Caveats stated in the doc itself: this is agent throughput with parallel subagents, not a human rate; **W2 is the estimate most likely to run long** (largest item, touches scoring, every scoring-adjacent item so far took 4-5 rounds not 1); commit-timestamp gaps include idle time, not effort. My read: the range is trustworthy, the exact 4-8h/session figure isn't perfectly re-derivable from the three points shown (they cluster closer to 2-4h), minor, not worth blocking on.

## MVP completion path — table, dependencies (PR #81 / DELIVERY_PLAN.md)

Full table: order/status/blocker/size per item. #80 is now MERGED (was IN REVIEW). Items 1, 3-8 still Not started. Status updates happen in the PR that lands each item, per the doc's own convention.

## #44 — needs_review placement (resolved, reversed from my original call)

Final: needs_review counts as applied, tri-state (applied/needs_review/dropped) reported as a separate count, not folded into the dropped reason vocabulary. Codified in DELIVERY_PLAN.md.

## W3 (resolved)

Option A — approval-time capability-list membership snapshot, item 4 in the MVP path table. Re-approval behavior still needs to be explicitly stated before implementation, not yet specified — flag if implementation starts before it's answered.

## Risk / W6 (resolved)

Yes — Risk needs the same release guarantees as the other four services. Items 6 and 8 in the MVP path table, both independent, both not started.

## Open decisions — NOT to be reconstructed from memory

- **Item 0 / live-AI key** — blocked on Gene, see above. Credential value never handled by either agent.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope per DELIVERY_PLAN.md)

## Environment notes (standing)

- Postgres migrations: [carried forward from prior entry — see commit `8533f10` history for exact gotcha text if needed]
- Provider live key: same item 0 blocker above. A much earlier entry in this file wrongly said this was resolved — corrected since.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail. At least 6 confirmed instances (the "#72 pattern"), attaches to W8 (adversarial audit in CI, half done).
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say — root defect family behind #73/#75/CSF-twin.
- A status line that is wrong is worse than none — the stated rationale for DELIVERY_PLAN.md's MVP path section being LIVING by convention.
- Credential material never travels through a relay conversation, even when explicitly offered. Same boundary for the agent and for me.
