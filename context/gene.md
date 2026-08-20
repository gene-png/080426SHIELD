# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (#91 merged, docs-only, only #29 remains open; #90 corrected — the "frozen forever" claim was wrong — and direction given: build 1+3 together, strike option 2; #89's test-pinning scope specified)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91 merged. Only #29 remains open (do-not-merge, parked pending W2 + clean audit). #84, #85, #87, #89, #90 filed, all open and tracked — #87 is decided (D-050) but its follow-ups (#89, #90, #85) are still open work, not just tracking tickets.

Next up: DELIVERY_PLAN item 2a (W8a), then item 3 (Tech Debt/ATT&CK export audits). No objection — this is the agreed queue and nothing is blocking it.

## Correction to my own prior entry — #90's "frozen forever" claim was wrong

Last round I told the other side the contracted target was "amendable exactly once by the client, then frozen forever," and logged that a re-scoped engagement had no route to a correct document at all. Both were false, and my own question about a possible renewal cycle is what surfaced it. The 409 on self-assessment submit is per-assessment, not a global lock, keyed to the latest assessment rather than the service. The admin-only new-assessment-version route cuts a new version once the prior one has moved on, which reopens the client's submit and lets the target be written again. So SHIELD does have a renewal-cycle concept, confirming the thing I'd asked about — I just didn't have the mechanism right, and neither did the original #90 filing.

That doesn't close #90 — it changes the reason it stays open. Cutting a new assessment cycle is technically possible but not usable for a re-scope: it discards the completed assessment (new versions seed blank rows, so changing one number costs all 87 to 106 answers), the consultant can't do it alone (the client must re-submit, so an unresponsive client blocks it entirely), and the client sets the value unilaterally with no required consultant agreement. Starting a new cycle is a re-assessment; a re-scope is not one, and treating the former as the only route to the latter was the actual problem all along — just not for the reason originally stated. Corrected in D-050, CONTEXT.md, and on the #90 thread itself, not left standing.

## Direction given on #90 — confirmed close to my read, sharper reasoning

Option 2 struck. Agreed it's a dead end, and correctly reclassified as never having been a real third option, not just deprioritized.

Build option 1 (consultant-side amend route) and option 3 (approval-time snapshot) together — but the reasoning is sharper than "they solve different problems." Without 3, adding 1 is actively worse than doing nothing: a consultant-side edit would retroactively change what an already-released deliverable claims it was measured against, reintroducing exactly the drift D-049 just closed. Without 1, 3 just freezes today's dead end more firmly. Option 3 composes with W3 (DELIVERY_PLAN item 4, already scoped as an approval-time membership snapshot, decision already made as Option A) — same shape, same lifecycle moment, build together rather than invent a second snapshot mechanism.

#89's test-pinning scope specified, not just requested. Required, lands in the same PR as the UI work: assert the exported document follows the contracted target and not the selector (concretely: set target=4, hit the gap-analysis endpoint with target_tier=3, finalize, assert built against 4); verified red-on-revert (wire the selector into finalize, confirm the test fails, then revert); and assert the target itself, not a bare gap count — because a bare count is exactly how instance 8 of the #72 pattern passed vacuously in this same file (test_export_targets.py already has the needed fixture shape via its intake-target helper).

## Item 0 (#51), export trio (#86), W8/#84/methodology (#88), D-050/#87 decision (#91) — all DONE, see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, W8a's actual cost, and #90's build-1-and-3 scope are all landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81, updated via #88 and #91)

Item 0 is DONE. Item 2 (CSF dashboard) is DONE. Item 1 (export trio) is DONE. Item 2a (W8a mechanized sweep) is not started, next in queue. Item 3 (Tech Debt/ATT&CK export audits) is not started, queued after 2a. Item 4 (W3, approval-time snapshot) is now explicitly the same build as #90's option 3, not a separate item — worth confirming the table reflects that link once work starts. Item 6 (W1 Risk) is scoped to include #84's fix.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. Composes with W3/item 4. #89's pin test — scope specified (target assertion, red-on-revert, not a bare count), not yet built. #57 — client read behavior for a released ATT&CK assessment. ServiceStatus.RELEASED (#62). W0's freeze shape (blocked on W5's Part 3 reopen scope).

## Resolved as of this round

#91 merged, docs-only, no code change. #90 direction given: strike option 2, build 1+3 together, compose 3 with W3/item 4. #89 pin-test scope specified as required, same PR as the UI work. My own #90 "frozen forever" error, corrected, not left standing.

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9 confirmed instances. Instance 8 (a bare gap count satisfied by an unrelated coverage fraction) is the direct reason #89's pin test must assert the target value, not a count — named explicitly rather than left to be rediscovered as a 10th instance. A defect in one service or function exists in its twins until checked — proven true at same-file distance as well as cross-service (see #84, #88). A conditional written to stop double-counting whose false branch silently drops the record. An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say. A status line that is wrong is worse than none — this round's own correction is an instance of it: I logged "frozen forever" with confidence last round, it was wrong, and it stayed wrong in the record for a full round until directly re-checked. It matters more here than usual, since this file exists specifically so a relay doesn't have to re-derive state from memory. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A value with exactly one writer and no amendment path becomes load-bearing for everything downstream without anyone deciding that on purpose (#90) — refined this round: even a value with a technical second path (the renewal cycle) can still be effectively one-writer if that path is too costly or too dependent on an unresponsive third party (the client) to use for its actual purpose.
