# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (item 3a done — PR #94, all five checks green, ready to merge; #77 will close on merge, not yet closed; the reconciliation-vanishing find is the real story, traced to the 2026-08-04 incident's exact mechanism)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93 merged. Only #29 remains open (do-not-merge, parked pending W2 + clean audit) plus #94 (item 3a, Tech Debt export audit, all checks green, ready to merge on my word). #84, #85, #87, #89, #90, #92 filed and open. #77 stays open until #94 merges — it references #77 but has not merged yet, so #77 is not actually closed despite being described that way in the relay; worth merging before treating it as done.

Merge #94 when ready — no objection, checks are green and the PR body matches what was relayed almost exactly. After that: item 3b (ATT&CK export audit) stays blocked on W2 per the plan, so next real unblocked work is item 4 (W3, Tech Debt approval-time snapshot).

## Item 3 split into 3a/3b, and 3a is done

3a is Tech Debt's export/persistence audit, PR #94. 3b is ATT&CK's equivalent, explicitly blocked on W2 landing first since it touches the same files and the audit wants the post-rewrite shape. Splitting this into two DELIVERY_PLAN rows rather than leaving one item half-done is the right call — it makes the block visible instead of silently stalling the whole row.

## #77 — closes on #94's merge, and not via the fix the issue originally proposed

The issue proposed composing parse_json_object_with_list directly into tech_debt_extract. That would have been a regression: the existing parser recovers JSON a provider wrapped in prose, and the generic parser does not, so swapping in the generic one would have turned working providers into hard failures with nothing to catch it. Instead, require_json_object and require_list_at were split out as shared shape-guard primitives that both parsers call, so every registered job now genuinely carries a top-level shape guard, a sentence the codebase could not previously make true. Writing the guard's own tests then found a second, previously unknown hole: a prose-wrapped bare list would get sliced down to its first item's braces and decoded as a single object with no items key, so the guard never saw it was a list at all. That's fixed too, and it was found by testing the fix rather than existing before it.

## The real find in PR #94 — a disclosure mechanism that silently disabled itself

reconcile_rows is designed to produce two different things: excluded, a count that is always trustworthy, and excluded_rows, the named rows, which are deliberately withheld when the provider does not attribute every item to a source row. Both the exporter and the workspace measured the named list's length to decide whether to show the exclusion disclosure at all, instead of using the always-trustworthy count. So one item with incomplete attribution made the named list empty, which made both surfaces conclude nothing was excluded, which let the export print an unqualified "Total annual cost" over a partial figure. That is not a hypothetical: it is the exact mechanism behind the 2026-08-04 incident, a 21-row $1,634,236 inventory that was shown as 12 capabilities worth $891,796, and the mechanism that was reachable had already been built specifically to prevent that class of error. It's also the third recorded instance of a false branch silently dropping a record rather than surfacing it under a different reason, which is worth remembering as a named pattern now, not just three coincidences. Fixed by deriving the count from source_rows_total minus source-attributed items rather than storing a second copy that could drift, and both the exporter and the workspace were fixed together in the same change, consistent with the twins rule that #86 was caught violating.

## Two things flagged rather than smoothed over

An existing test, test_deliverable_reconciliation.py, had been constructing its test context by passing excluded_count in directly, so it was asserting the rendering of a number the test itself supplied and never touched the code that derives it. That's the same #72 shape, caught while changing the code underneath the test rather than by a dedicated audit pass, and it was rewritten to build through the real code path instead. Separately, running W8a's own mutation sweep against this change produced one apparent surviving mutant on the savings branch that turned out to be an artifact of a too-narrow test-target flag, not a real gap; a broader target killed it immediately. That caveat, that a survivor is only meaningful relative to which tests were actually run, is now written into the tool's own docstring, since a survivor list read without that context would mislead in exactly the way this class of tooling usually does.

## What was checked and found sound, recorded so it isn't redone

No top_n truncation exists in the Tech Debt exporters, unlike the ZT/CSF twin issue. cost_label already refuses to present a partial figure as a total. The top-cost card in overlap.py names its own bound and publishes the true total alongside it, so it isn't a silent truncation. Tech Debt has no maturity-target concept, so the #73/#79 hardcoded-target defect has no twin here to check.

## Item 0 (#51), export trio (#86), W8/#84/methodology (#88), D-050/#87 decision (#91), W8a (#93), item 3a (#94) — all DONE or ready-to-merge, see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, #90's build-1-and-3 scope, #92's contract-test fix, and item 3b (blocked on W2) are all landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81, updated via #88, #91, #93, and #94)

Item 0 is DONE. Item 2 (CSF dashboard) is DONE. Item 1 (export trio) is DONE. Item 2a (W8a mechanized sweep) is DONE. Item 3a (Tech Debt export audit) is DONE pending #94's merge. Item 3b (ATT&CK export audit) is blocked on W2, not started. Item 4 (W3, approval-time snapshot, composing with #90's option 3) is not started, next unblocked work after #94 merges. Item 6 (W1 Risk) is scoped to include #84's fix.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. #89's pin test — scope specified, not yet built. #92 — contract-test fix needed in both CSF and ZT, not yet built. #57 — client read behavior for a released ATT&CK assessment. ServiceStatus.RELEASED (#62). W0's freeze shape (blocked on W5's Part 3 reopen scope).

## Resolved as of this round

#94 built and ready to merge: item 3a's Tech Debt export audit, the shape-guard fix for #77 (closes on merge, not yet closed), and the reconciliation-disclosure fix tracing directly to the 2026-08-04 incident. DELIVERY_PLAN item 3 formally split into 3a (done) and 3b (blocked on W2).

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9 confirmed instances, plus one more caught in #94's own test rewrite while changing the code underneath it, which is now effectively 10 even though it wasn't logged as a numbered instance. A defect in one service or function exists in its twins until checked — #94 explicitly checked Tech Debt against the ZT/CSF twin defects (#73/#75/#79) and recorded finding no twin, which is exactly the discipline this rule requires: checking and finding nothing is not the same as not checking. A false branch dropping a record silently instead of surfacing it under a different reason — now three recorded instances, most recently the reconciliation disclosure vanishing exactly when a provider's attribution was incomplete. A status line that is wrong is worse than none — the relayed claim that #77 was closed is technically premature until #94 actually merges, a small but real instance of the same pattern, corrected here rather than carried forward. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A mutation-testing survivor is only meaningful relative to which tests were actually run against it — new this round: a narrow test-target flag can manufacture a false survivor that looks like a real gap, and that caveat now lives in the tool's own docstring rather than only in this file.
