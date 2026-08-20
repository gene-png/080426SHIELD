# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (#86 merged, all five checks green; PR #88 open answering all four sent-back questions — W8 split, #84 folds into W1 Risk, methodology fix tested and confirmed, #87 filed with a recommendation)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50, #81, #82, #86 merged** (#86 merged as `b4d8ab5`, all five checks green). Only **#29** remains open (do-not-merge, parked pending W2 + clean audit) plus **#88** (answers to the four questions below, checks not yet confirmed green — verify before assuming mergeable) and **#84, #85, #87 filed**, all open and tracked.

**Next action: merge #88 once its checks pass.** No objection to that from this side.

## PR #88 — all four sent-back questions answered

1. **W8 split, not deferred whole.** W8a is the mechanized #72-pattern sweep, in two measured tiers: a cheap static check (**measured** to catch only ~3-4 of the 9 known instances — explicitly not oversold as full coverage) plus diff-scoped mutation testing (catches the full class, but runs nightly non-blocking rather than gating a PR, since it's too slow to gate). W8a moves up to DELIVERY_PLAN.md item **2a**. W8b stays deferred, with a stated reason rather than silent parking.
2. **#84 folds into W1 Risk (item 6)**, not sequenced after it — and the justification is stronger than either of us had said: accounting-code-first would bake the wrong target into every fixture written against it, and the actual client-facing consequence is worse than "wrong numbers" — CSF tier-4 clients get **zero** risk findings, not just miscounted ones.
3. **Methodology fix tested, not just adopted.** Rather than taking the grep-for-symptom suggestion on faith, the other side tested it directly with specific `grep -rnE` commands against the known #72 instances and confirmed it actually surfaces the inline-reimplementation case that the callers-only sweep missed. That's the right way to handle a secondhand suggestion.
4. **#87 filed and tracked**, not left implicit. Read the issue in full: it's a genuine product/policy call (contracted target vs. the target the consultant reviewed against), not a technical question, so this is offered as a recommendation, not a decision made on Gene's behalf. **Recommendation: Option A, the contracted target.** The document should reflect what the client is being held to, not what happened to be on screen when the consultant clicked submit — the on-screen selection is closer to a UI/workflow bug (the reviewer should be reviewing against the contracted target in the first place) than a legitimate alternate source of truth. **If Option A is confirmed, it likely needs a UI follow-up** so the review screen itself defaults to and highlights the contracted target, rather than leaving the mismatch for someone to notice later.

## Item 0 (#51) — DONE, PR #82 merged (2026-08-19, see prior entries for full detail)

Live AI verified end to end via Tier A/B/C methodology. Live mode reverted to fixture by default afterward, on purpose, documented in DELIVERY_PLAN.md.

## Session length — measured from git history (unchanged, see prior entries)

1 session ≈ 4-8 hours. Estimate was 5-9 sessions after item 0 closed; still needs revision once #84's W1-Risk fold-in and W8a's actual cost are both landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81)

Item 0 → DONE. Item 2 (CSF dashboard) → DONE. Item 1 (export trio) → DONE, merged via #86. Item **2a** (W8a mechanized sweep, two tiers) → new, added via #88, Not started. Items 3-8 still Not started; item 6 (W1 Risk) now explicitly scoped to include #84's fix once #88 merges. Confirm DELIVERY_PLAN.md's table reflects this exactly once #88 lands — don't assume the paste matches the live table.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

- **#87 (contracted vs. reviewed target)** — recommendation given (Option A), not yet confirmed by Gene. If confirmed, needs a UI follow-up flagged above.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope)

## Resolved this round (were open, now answered via #88)

- W8 priority — split into W8a (moved up, item 2a) / W8b (deferred, stated reason).
- #84 scope — folds into W1 Risk (item 6), stronger justification recorded above.
- Audit methodology (grep symptom vs. shared-function callers) — tested and confirmed working, not just adopted on faith.

## Environment notes (standing)

- Postgres migrations: confirmed clean through 0042 as of 2026-08-19.
- Provider live key: **RESOLVED.** Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail — **9 confirmed instances**, most recent two 2026-08-19 in the #86 audit pass itself. W8a (via #88) is the first mechanized attempt to catch this class in CI rather than relying on audits finding it after the fact — measured honestly at partial coverage for the cheap tier, full coverage only on the slower nightly tier.
- **A defect in one service/function exists in its twins until checked** — proven true at same-file distance (12 lines) as well as cross-service. Grepping for one shared function's callers is not sufficient; an inline reimplementation of the same logic hides from that sweep (see #84, and the methodology fix above).
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say.
- A status line that is wrong is worse than none.
- Credential material never travels through a relay conversation, even when explicitly offered.
- Test behavior changes get called out explicitly in the test itself, never silently adjusted — and the callout should cover every property the change affects, not just the one already being asserted (see the font-regression, PR #86).
