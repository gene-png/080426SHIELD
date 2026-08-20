# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (PR #86 open, checks running; audit caught CSF-truncation twin + 2 more can't-fail tests; W8/#84/methodology questions sent back)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50, #81, #82 merged**. Only **#29** remains open (do-not-merge, parked pending W2 + clean audit) plus **#86** (export trio, checks running as of this entry — verify current state before assuming still open). **#84 and #85 filed, both open, both verified directly** — real issues, correctly scoped out of #86 rather than folded in or dismissed.

**Merge #86 when green — no objection to that part.** Three real questions sent back before anything after that starts.

## PR #86 — the audit was the valuable part, not the fixes

The three original fixes (#73/#75/#79) were correct, but the audit caught what would otherwise have shipped wrong:

- **CSF shares #75's exact defect** — same `DEFAULT_TOP_N = 20`, same three renderers, undisclosed truncation. Worse: the #79 fix raised CSF's target to the client's tier, which increased the gap count, so the undisclosed truncation hid *more* after the "fix" than before it.
- **Same shape found 12 lines away** — `_zt_gap_total` had the identical bug sitting next to the `_csf_gap_total` just fixed. Twins-until-checked now proven at same-file distance, not just cross-service.
- **8th and 9th instances of the #72 pattern**, both in this same audit pass. One asserted a count appeared in text, satisfied by an unrelated number already in that text regardless of whether the fix worked.
- **A real font-regression** introduced by the earlier row-shift fix — the test updated for the shift checked caption and value, not the one font property the shift actually broke.
- **Two new issues filed correctly, not folded in or dropped:**
  - **#84** — `risk.py` hardcodes target=3, ignoring the client's intake target. Affects roughly two-thirds of engagements (any target ≠ 3). Escaped the trio's sweep because `risk.py` re-derives the comparison inline instead of calling `analyze_gaps` — a methodology gap, not a coverage gap. **Question sent: should this fold into W1 Risk (item 6) rather than come after it, since both touch the same file?**
  - **#85** — self-assessment submit schemas allow target=1 where intake enforces ≥2; not UI-reachable but produces a vacuously-empty "0 gaps" document, the failure mode that reads most like success. Correctly triaged as low-severity, not dismissed.
- **Self-corrected their own PR body** — original claim was the fix "tracks the view the consultant reviewed and signed off." Not true, the selector is a query param finalize never sees; the document follows the contracted target instead. Flagged as a policy question, not silently resolved. **Sent back: track this explicitly as an open decision, don't let the correcting sentence quietly settle it.**
- Rebase onto #82 hit a DELIVERY_PLAN.md conflict in the live-AI section — kept main's version (better) and appended only the new observation, rather than overwrite. Good instinct, no objection.

## Three open questions sent back, none answered yet

1. **W8 (mechanized adversarial-audit sweep) needs an actual decision, not continued deferral.** Nine #72-pattern instances now, two from this very audit. The agent's own conclusion, "this is a mechanism problem, not a discipline problem," is correct — discipline has failed nine times including against the same agent minutes after writing the rule down. Does W8 move up in DELIVERY_PLAN.md's ordering, or stay deferred with a stated reason? **Open.**
2. **Does #84 fold into W1 Risk rather than sequence after it?** Same file, and #84 is a real client-facing correctness gap, not a nice-to-have. **Open.**
3. **Audit methodology blind spot** — #84 escaped the sweep because `risk.py` reimplements the comparison inline rather than calling the shared function. Should future "exists in its twins" passes also grep for the symptom (literal defaults, truncation constants), not just the shared function's callers? **Open.**

Plus the policy-question item above (contracted target vs. consultant's on-screen selection) — also open, not yet added to the tracked list below at time of writing, add once answered or confirmed as its own line.

## Item 0 (#51) — DONE, PR #82 merged (2026-08-19, see prior entry for full detail)

Live AI verified end to end via Tier A/B/C methodology. Live mode reverted to fixture by default afterward, on purpose, documented in DELIVERY_PLAN.md.

## Session length — measured from git history (unchanged, see prior entries)

1 session ≈ 4-8 hours. Estimate was 5-9 sessions after item 0 closed; will need revision once #84/#85's scope is decided and W8's status is settled.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81)

Item 0 → DONE. Item 2 (CSF dashboard) → DONE. Item 1 (export trio) → PR #86 open, not yet merged. Items 3-8 still Not started, though #84 may now be in-scope for item 6 (W1 Risk) pending the question above. Confirm DELIVERY_PLAN.md's table reflects true state once #86 lands.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

- **W8 priority decision** — just opened, see above.
- **#84 scope: fold into W1 Risk or sequence after** — just opened, see above.
- **Audit methodology: grep for symptom vs. shared-function callers** — just opened, see above.
- **Contracted target vs. consultant's on-screen selection (policy)** — just opened, see above.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope)

## Environment notes (standing)

- Postgres migrations: confirmed clean through 0042 as of 2026-08-19.
- Provider live key: **RESOLVED.** Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail — **9 confirmed instances now**, most recent two 2026-08-19 in the #86 audit pass itself.
- **A defect in one service/function exists in its twins until checked** — now proven true at same-file distance (12 lines), not just cross-service. Grepping for one shared function's callers is not sufficient; an inline reimplementation of the same logic hides from that sweep (see #84).
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say.
- A status line that is wrong is worse than none.
- Credential material never travels through a relay conversation, even when explicitly offered.
- Test behavior changes get called out explicitly in the test itself, never silently adjusted — and the callout should cover every property the change affects, not just the one already being asserted (see the font-regression above).
