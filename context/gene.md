# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (item 3a merged; W3 shipped as PR #95, all five checks green, ready to merge — closes #32, unblocks W2; D-053 corrects a claim in the plan of record rather than acting on it)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94 merged. Only #29 remains open (do-not-merge, parked pending W2 + clean audit) plus #95 (W3, item 4, all checks green, ready to merge on my word). #84, #85, #87, #89, #90, #92 filed and open. #32 will close on #95's merge.

Merge #95 when ready — no objection, checks are green and the design (snapshot, not lock) is sound. This is the head of the long pole: merging #95 unblocks W2 (item 5), which is gated behind it to avoid rebase churn on the same files. After W2 comes W1-ATT&CK, then item 3b.

## W3 shipped — PR #95, closes #32, DELIVERY_PLAN item 4

The problem: approval never froze the tech-debt capability list's membership, only its status. _editable_list_or_404 blocks RELEASED and DISCARDED, but the whole APPROVED window stayed mutable through five doors, two of which change what the ATT&CK allow-list actually contains — renaming an item, or removing a row via the security-classification confirm queue. Since the allow-list is built from live names at the moment ATT&CK runs, "confirmed against the approved list" really meant "confirmed against whatever the list had since become." W4 is what made this urgent rather than theoretical: release now actually locks the list, so before W4 this was dead code and the list stayed mutable forever; the live window is now specifically APPROVED-to-released, and ATT&CK runs happen inside it.

The fix is a snapshot, not a lock, and that distinction is the actual insight, not just an implementation detail. #32 sat deferred for months because the obvious fix, making an approved list immutable, would break two real features: the security-classification confirm queue and excluded-row recovery. What was actually wrong was never that the list could change, it was that changing it silently rewrote history with no record. Migration 0043 adds a stored snapshot of every in-scope item's id and name at the moment of approval; ATT&CK reads that snapshot instead of live rows whenever one exists. Re-approval refreshes it explicitly, and the audit trail records both the new count and how many entries were replaced, since a count alone can't say whether a re-approval actually changed the allow-list. Item ids are stored alongside names on purpose: once a name changes, the name alone can't be traced back to its original row, which is exactly the failure this whole mechanism exists to survive.

## A claim in the plan of record was wrong, and the response was to correct the plan rather than the code

The plan's section 7 asserted that a specific field, written when a consultant manually curates a row, produces "an affirmative false claim" on screen, a badge reading as machine-verified when nothing was verified. Checking the actual code showed that claim doesn't hold: every writer of that field is explicitly documented as human-supplied, and the route's own docstring says re-deriving the value at that point would be guessing rather than reflecting what a human already decided. So no code changed. The claim was corrected in D-053 instead, with the reasoning for why it doesn't hold, because a plan document read by whoever picks up work next is exactly the kind of place where an uncorrected wrong claim eventually gets "fixed" by someone who trusted it. This is the same discipline as the numeric corrections from the last two rounds, applied to a planning document instead of a status report, and it's arguably more valuable there, since a wrong claim in a living plan has a longer half-life than a wrong number in a chat relay.

## Verification, and one thing worth naming rather than treating as routine

Nine new tests, one per door identified in the design. Each side was verified separately with red-on-revert: reverting the read side fails four tests, reverting the write side fails six. The migration was applied to the actual dev Postgres instance, not just exercised in SQLite unit tests, specifically because CLAUDE.md already records this exact gotcha, a new column existing in every SQLite test fixture while the running dev database sits on the previous revision and nobody notices until something reads a column that isn't there. A backgrounded full local suite run was stopped before it finished printing, which was flagged directly rather than left ambiguous: CI's Python job runs the identical pytest command and passed, so nothing is actually unverified, but the distinction between "I ran this and it passed" and "CI ran this and it passed, and I'm telling you why the local run doesn't add anything CI didn't already confirm" is exactly the kind of thing worth stating plainly rather than blurring together.

## Item 0 (#51), export trio (#86), W8/#84/methodology (#88), D-050/#87 decision (#91), W8a (#93), item 3a (#94), W3 (#95) — all DONE or ready-to-merge, see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, #90's build-1-and-3 scope, #92's contract-test fix, W2, and item 3b are all landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81, updated via #88, #91, #93, #94, and #95)

Item 0 is DONE. Item 2 (CSF dashboard) is DONE. Item 1 (export trio) is DONE. Item 2a (W8a mechanized sweep) is DONE. Item 3a (Tech Debt export audit) is DONE. Item 3b (ATT&CK export audit) is blocked on W2, not started. Item 4 (W3, approval-time snapshot) is DONE pending #95's merge. Item 5 (W2) is unblocked once #95 merges, next real work after this. Item 6 (W1 Risk) is scoped to include #84's fix.

## #44 / W3 / Risk-W6 — all resolved (W3 now fully shipped via #95, not just planned), see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. #89's pin test — scope specified, not yet built. #92 — contract-test fix needed in both CSF and ZT, not yet built. #57 — client read behavior for a released ATT&CK assessment. ServiceStatus.RELEASED (#62). W0's freeze shape (blocked on W5's Part 3 reopen scope, which is now closer given W3's snapshot pattern may inform how W5's reopen scope gets designed — worth watching, not yet linked explicitly by either side).

## Resolved as of this round

#95 built and ready to merge: W3's approval-time membership snapshot, closing #32, unblocking W2. D-053 recorded correcting a wrong claim in the plan of record about the human-curated badge, with no code change since the claim didn't hold up. #94 confirmed actually merged (not just ready) as of this round.

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19; 0043 now applied to dev Postgres as of this round, verified via alembic current rather than assumed from the SQLite test suite. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9 confirmed instances, plus the one caught in #94's own test rewrite. A defect in one service or function exists in its twins until checked — W3's design explicitly separates the "lists with a snapshot" case from "lists with no snapshot," so old pre-migration approved lists don't silently get treated as if nothing was ever approved; that distinction is itself an instance of not assuming a migration's effect is uniform across every existing row. A false branch dropping a record silently instead of surfacing it under a different reason — three recorded instances so far, none new this round. A status line that is wrong is worse than none — this round adds a plan-document instance rather than a status-relay instance: an uncorrected wrong claim in a living planning document was treated with the same seriousness as a wrong number in a chat relay, and corrected in the document itself rather than left to become someone's future "fix." Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A mutation-testing survivor is only meaningful relative to which tests were actually run against it. New this round: a migration's effect on existing rows is not uniform by default, and a design that reads "old rows behave as before, new rows get the new behavior" has to be stated and tested as its own case, not assumed to fall out of the migration automatically.
