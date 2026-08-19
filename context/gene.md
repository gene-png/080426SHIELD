# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (PR #81 delivers the MVP completion path; two open questions sent back; merge order given)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision.

## Branch / in flight

`main` is at `265071e`. Seven PRs open: **#81** (MVP completion path doc + CLAUDE.md convention row — see below), **#80** (CSF dashboard, CI re-running after the s31 home-links fix), **#78** (shape guards + CSF provenance, green), **#76** (docs sync, green), **#49**/**#50** (dependabot, green), **#29** (do-not-merge, parked pending W2 + clean audit — now also stated as a dependency in DELIVERY_PLAN.md itself, not just here).

**Merge order given, not yet executed by me:** #78 first (foundational — other suggestion-job work likely sits on it), #80 next once CI is actually green, then #76/#49/#50 in any order, #81 last. #29 stays parked. Nothing merged yet — this is guidance sent back, not an action taken.

## MVP completion path — now a real doc, not just this file (2026-08-19)

Asked the other agent to stop tracking the MVP path only through relayed decisions and put it in the repo. **PR #81** does this: adds a "MVP completion path" section to `DELIVERY_PLAN.md` (order/status/blocker/size table, dependency graph, honest "nothing in the AI layer has run against a real model" callout as item 0) and adds a row to `CLAUDE.md`'s doc table making that section LIVING by convention — status updates in the same PR that lands the item, not after. I verified both files directly on the `docs/mvp-completion-plan` branch before responding, not just from the relayed paste (which came through with a garbled table).

**The table, as verified:**

| # | Item | Status | Blocked by | Size |
|---|---|---|---|---|
| 0 | Live-AI verification (#51) | BLOCKED | working provider key, `.env` key 401s | 1 session once a key exists |
| 1 | Export-target trio — #73/#75/#79 | Not started | nothing | 0.5–1 session |
| 2 | CSF client dashboard | IN REVIEW (PR #80) | CI | done bar review |
| 3 | Export/persistence audit — Tech Debt, ATT&CK | Not started | ATT&CK's pass should follow W2, not race it | 0.5 each + unknowns |
| 4 | W3 — Tech Debt approval snapshot | Not started | nothing (Option A decided) | 1–1.5 sessions |
| 5 | W2 — ATT&CK resolver rewrite + tri-state | Not started | W3 (item 4) | 2–3 sessions |
| 6 | W1 Risk step | Not started | nothing | 1–1.5 sessions |
| 7 | W1 ATT&CK step | Not started | W2 (item 5) | 1 session |
| 8 | W6 — Risk export/publish split | Not started | nothing | 0.5–1 session |

Headline: **roughly 7–11 focused sessions, called two to three weeks**, with the W3→W2→W1-ATT&CK chain over half of it. Items 1, 6, 8 are independent and can run in parallel with the chain.

### Two things I pushed back on rather than just accepting

1. **Item 0 has no owner and no next action.** Every other row is engineering work someone can pick up. Item 0 is "needs a real provider key" and isn't wired into the dependency graph as blocking anything else — it just sits there. That means the 2-3 week estimate covers everything except the one thing that actually gates whether this is an MVP. Sent back: is procuring a live key in flight, and if not, what's needed from Gene to unblock it. **Open — answer pending.**
2. **"Session" has no stated wall-clock length.** 7-11 sessions becoming "two to three weeks" is a conversion I can't check. Asked for hours-per-session so the estimate is something to hold them to. **Open — answer pending.**

## #44 — needs_review placement (resolved, reversed from my original call)

I originally recommended `needs_review` live inside `dropped` with its own reason code. The other agent pushed back with a rigorous argument grounded in the actual W2 plan §5.1 text: `applied` in W1's accounting means "written to the record," not "contributed to the score," and for ATT&CK specifically §5.1 states "needs review" changes nothing about the score on its own. I conceded — that's correct.

**Final: needs_review counts as applied. The tri-state (applied / needs_review / dropped) is reported as a separate count, not folded into the dropped reason vocabulary.** Now also codified in DELIVERY_PLAN.md's dependency notes as settled.

## W3 (resolved)

Option A — approval-time capability-list membership snapshot, now item 4 in the MVP path table, no longer blocked. Re-approval behavior still needs to be explicitly stated before implementation — not yet specified by the other agent as of last update, flag this if implementation starts before it's answered.

## Risk / W6 (resolved)

Yes — Risk needs the same release guarantees as the other four services for MVP. Now items 6 and 8 in the MVP path table, both independent, both not started.

## CSF client dashboard — PR #80 open, CI re-running

Full audit came back clean except the three-surface tier inconsistency, decided: ship the dashboard as built (correct), twin issue filed paired with ZT's #73/#75 fix at the front of the item-4 audit queue (now item 3 in the formal table). Pre-launch confirmed with evidence (see prior entries) closed the urgency question — first-in-queue, not fire-drill.

PR #80 itself had a red E2E (s31-home-service-links hardcoded which dashboard kinds a "Report ready" card may link to; CSF joining `dashboardPathFor` broke it). Root-caused correctly: greeped source consumers but not `e2e/` assertions on the route map, a data-structure instance of the "grep before you change anything a spec asserts on" rule. Fixed, passing locally (3/3), CI re-running. Merge order above puts this second, after #78.

## Open decisions — NOT to be reconstructed from memory

- Item 0 ownership / live-AI key status — **just opened, see above**
- Session-to-hours conversion — **just opened, see above**
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (now explicitly stated in DELIVERY_PLAN.md as blocked on W5's Part 3 reopen scope)

## Environment notes (standing)

- Postgres migrations: [carried forward from prior entry — see commit `8533f10` history for exact gotcha text if needed]
- Provider live key / root `.env` key issue: **still open** — this is the same key referenced as item 0's blocker above, not a separate resolved issue. Correcting prior entry which said this was resolved; it was not.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene. DELIVERY_PLAN.md now independently states the same constraint (can't merge until W2 lands plus a clean adversarial audit). Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail. At least 6 confirmed instances of this pattern so far (the "#72 pattern"). #72 itself now attaches to W8 (adversarial audit in CI, half done) per DELIVERY_PLAN.md.
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, making the run indistinguishable from a run where the model had nothing to say — root defect family behind #73/#75/CSF-twin.
- A status line that is wrong is worse than none — now the stated rationale for making DELIVERY_PLAN.md's MVP path section LIVING by convention (CLAUDE.md doc table), not just a principle applied ad hoc.
