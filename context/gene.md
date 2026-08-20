# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (Item 0 DONE, #82 merged; export trio red→green locally, adversarial audit + full suite still in flight, no PR yet)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50, #81, #82 all merged**. Only **#29** remains open (do-not-merge, parked pending W2 + clean audit). **No PR exists yet for the export trio** — verified directly, issue search and PR list both confirm this, work is local/in-progress only.

**Current work: export-target trio (#73/#75/#79), IN FLIGHT, not yet a PR.** All three fixed locally (red→green), but the agent has NOT called this done — full backend suite running, adversarial audit pass in progress. Two things it flagged as specifically unsure of and is auditing before calling this finished: (1) whether the conditional-kwarg pattern leaves some state where exporter and dashboard still disagree, (2) whether CSF's exporter has the same undisclosed-truncation defect #75 was filed against ZT for — if so, the trio only closed half of CSF's exposure and a fourth issue is needed. **Wait for the audit report before treating this as landed.**

## Item 0 (#51) — DONE (2026-08-19), PR #82 merged

Live AI verified end to end. Tier A (natural real call): ZT accounting received=74 applied=74, no drops observed on that prompt — expected, not a gap. Tier B (corrupt-after-live, my suggestion, adopted): real call, then mutate body before parsing — covers entry_shape, unknown_key, unknown_field, unparseable, out_of_range, superseded, locked, plus the shape-guard 502. Caught its own bug mid-build: passing name/model through would've silently flipped the call to FIXTURE mode, protecting the rows it was supposed to test. Tier C: `protected` stays permanently live-unverifiable by construction, asserted in a test rather than left ambiguous. 10 tests, ~9 real calls, 2m33s, self-skip in fixture mode, excluded from `-m unit` so no ambient CI cost. Live mode reverted to fixture on purpose afterward, verified from inside the container, documented in DELIVERY_PLAN.md. Key stays available for opt-in runs only.

**#82's E2E check hit the same apt-mirror Chromium-install timeout as #81's Demo job** (two occurrences now) — rerun came back clean, confirming transient infra flake, not a real failure. Worth fixing (cache/pin the Chromium install) but not urgent.

## Recurring #72 pattern — now with a sharper argument for automating it

The trio work produced a live example: the first #75 test asserted against a summary line that already carried the true total, so it would pass whether the defect existed or not. Caught and rewritten to assert against actual rendered XLSX rows. **This was the seventh instance of the #72 pattern in one session, produced roughly ten minutes after logging the sixth.** Stated plainly by the agent itself: knowing the pattern does not prevent producing it. The manual adversarial-audit pass is catching these before merge, which is working, but only because someone remembers to run it every time — that's the concrete argument for W8's mechanized CI sweep, currently sitting in DELIVERY_PLAN.md's deferred/non-MVP table. Not escalating MVP scope over this alone, but flagged here so it isn't forgotten.

Also: one existing test (`test_xlsx_handles_empty_gap_list_with_placeholder`) had its `max_row == 2` pin updated because the new caption row shifts everything down one — behavior unchanged, position only, called out explicitly in the test rather than silently adjusted. Good practice, matches the standard.

## Session length — measured from git history (unchanged, see prior entries for full detail)

1 session ≈ 4-8 hours. Item 0 closing dropped the remaining estimate to roughly 5-9 sessions (was 6-10). W2 still flagged as most likely to run long.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, now merged via #81)

Item 0 (live-AI) → DONE. Item 2 (CSF dashboard) → DONE (#80 merged). Item 1 (export trio) → in flight, not yet landed. Items 3–8 still Not started. Confirm DELIVERY_PLAN.md's own table reflects item 0 and item 1's true state once the trio actually lands — per its own LIVING convention, status updates in the PR that lands the item.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

- #44: needs_review counts as applied, tri-state reported separately. Codified in DELIVERY_PLAN.md.
- W3: Option A, approval-time snapshot. Re-approval behavior still needs explicit statement before implementation.
- Risk/W6: yes, same release guarantees as the other four services.

## Open decisions — NOT to be reconstructed from memory

- **Whether CSF's exporter shares #75's truncation defect** — just opened, see above, audit result pending.
- **Whether the conditional-kwarg pattern leaves exporter/dashboard disagreement in some state** — just opened, see above, audit result pending.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope)

## Environment notes (standing)

- Postgres migrations: confirmed clean through 0042 as of 2026-08-19.
- Provider live key: **RESOLVED.** Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail — **7 confirmed instances now**, most recent 2026-08-19 in #75's first test draft, caught before merge.
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say.
- A status line that is wrong is worse than none.
- Credential material never travels through a relay conversation, even when explicitly offered.
- Test behavior changes (like a shifted row position) get called out explicitly in the test itself, never silently adjusted to keep it green.
