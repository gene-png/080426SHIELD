# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (Item 0 unblocked — live AI verified end to end; two open questions sent before #51 runs)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50 merged**. **#81 (MVP plan doc) status unknown as of this entry** — check PR #81 directly for current merge state, last confirmed at 4/5 checks green with the Demo job cancelled on an infra flake. Only **#29** remains parked (do-not-merge, gated on W2 + clean audit).

**Directed next action: run #51's live verification pass, not the export trio** — see reasoning below. Trio (#73/#75/#79) is queued after.

## Item 0 (#51) — KEY WORKS, LIVE AI VERIFIED END TO END (2026-08-19)

No longer blocked. A real `csf_score` call to `claude-opus-5` completed: 573 in / 1218 out tokens, 19.6s, `status = completed`, `error_message = None`. Redaction seam held on real output (`redacted_counts` populated, model's own response referenced "redacted identifiers", confirming PII stripped pre-egress not post). "AI suggests, code computes" respected — dimension scores returned, totals/roll-ups computed downstream, not by the model.

**Credential handling — done right, worth trusting as a pattern:** key found in a local file outside the repo, `.env`'s gitignore status verified *before* writing to it, written via a script so the value never touched tool output, an unignored `.env.bak` backup was caught and deleted rather than left in the tree, one command was blocked by a permission classifier and the agent respected that rather than working around it. No secret ever appeared in any relayed output. This is the standard.

**What's NOT yet verified, and why it matters — flagged before running #51, not after:** a well-behaved model won't produce malformed output on request. Live verification proves the happy path; it does not exercise the six ZT reason codes, CSF's equivalents, or the two shape-guard 502 paths — which are specifically about drops and bad shapes, the core defect family this entire stretch exists to catch. **Sent back, not yet answered:**

1. **How do the drop paths get exercised?** Pushed for corrupting a real response after a genuine live call (real cost/latency, injected bad shape) over leaving these permanently fixture-only. If infeasible for some reason codes, that needs to be stated explicitly in DELIVERY_PLAN.md rather than let "item 0 done, 1 session" quietly cover a partial result. **Open.**
2. **Is live mode staying on, or flipping back to fixture after this pass?** Any later `docker compose up` touching web now keeps live mode; every Run-AI from here costs real tokens. Fine if intentional, needs to be a decision, not a leftover default. **Open.**

Two reason codes were already flagged (prior entry) as untestable this way regardless: `protected` (fixture-only by construction), `locked` (needs an API-seeded lock).

Migration note: `alembic upgrade` ran through to 0042 on this container — the earlier Postgres-migration lesson applied cleanly here.

## Session length — measured from git history (unchanged, see prior entry for full detail)

1 session ≈ 4-8 hours measured from three data points (W1 ZT, CSF dashboard, shape guards). 6-10 remaining sessions ≈ 35-65 hours ≈ 7-12 working days. W2 flagged as most likely to run long. Full reasoning and caveats in commit history if needed.

## MVP completion path — table, dependencies (PR #81 / DELIVERY_PLAN.md)

Full table: order/status/blocker/size per item. Item 0 status changes from BLOCKED to done (or partially-done, pending the two open questions above) — this should land in the plan doc's own table per its own LIVING convention, confirm it did when #51 wraps.

## #44 — needs_review placement (resolved, reversed from my original call)

Final: needs_review counts as applied, tri-state reported as a separate count. Codified in DELIVERY_PLAN.md.

## W3 (resolved)

Option A — approval-time capability-list membership snapshot, item 4 in the MVP path table. Re-approval behavior still needs to be explicitly stated before implementation.

## Risk / W6 (resolved)

Yes — Risk needs the same release guarantees as the other four services. Items 6 and 8, both independent, both not started.

## Open decisions — NOT to be reconstructed from memory

- **Drop-path test methodology for #51** — just opened, see above.
- **Live mode default going forward** — just opened, see above.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope per DELIVERY_PLAN.md)

## Environment notes (standing)

- Postgres migrations: confirmed clean through 0042 as of this entry (2026-08-19), see item 0 above.
- Provider live key: **RESOLVED as of 2026-08-19.** Working key installed, live mode verified end to end. (Earlier entries tracked this as open/blocked — now closed.)

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail. At least 6 confirmed instances (the "#72 pattern").
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say — root defect family behind #73/#75/CSF-twin, and the exact reason live-AI verification of the happy path alone isn't sufficient for item 0.
- A status line that is wrong is worse than none.
- Credential material never travels through a relay conversation, even when explicitly offered. Same boundary for the agent and for me. The 2026-08-19 key install followed this correctly — verify gitignore before writing, never let the value touch tool output, clean up any unignored copy.
