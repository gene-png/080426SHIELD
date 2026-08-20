# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (#101 reopened with an explanation posted directly on the issue, confirmed on GitHub; PR #104 records the root cause in CLAUDE.md — GitHub's closing-keyword parser matches `fixed: #101` inside "Filed, not fixed: #101," the word "not" isn't part of what it reads, so "does not fix #N", "partially fixes #N", "not resolved: #N" all trip it identically; #104 is docs-only, open, not yet merged; next up is the #101+#102 persistence PR — flagged one open design question before it starts: what an assessment run before the migration lands should read as, given it has zero persisted flag data by construction)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103 merged, all verified directly on GitHub. Open: #104 (docs-only, the closing-keyword rule, not yet merged) and #29 (permanently unmerged under D-054 — still not closed as superseded even though W2 has landed; worth confirming this actually happens). #84, #85, #87, #89, #90, #92, #102 filed and open. #101 is filed and reopened — see below. #99 was closed as a false-docs-only attempt superseded by #100.

## #101 — reopened, root cause understood, documented in #104

W2's own commit body wrote "Filed, not fixed: #101" — worded specifically to record that the issue was NOT resolved. GitHub's closing-keyword parser reads `fixed: #101` out of that phrase and closed the issue anyway; it does not parse negation. Confirmed via the issue's own timeline: closed by commit `e9e8783`, the same commit that merged #103. No code was wrong here — the defect is that GitHub's own auto-linking silently dropped a real open issue from the backlog, which nobody would have caught without going looking for it. Reopened with the mechanism explained directly on the issue. #104 puts the rule in CLAUDE.md: never write "does not fix #N", "partially fixes #N", or "not resolved: #N" — use "filed as #N" or "see #N" instead, and save the actual closing keyword for the PR that lands the fix for real.

## Next: #101 + #102 persistence, not yet started

Correctly scoped together per #102's own stated dependency ("needs #101's storage before anything can clear a flag"), rather than building the storage layer twice. Planned shape: an additive, SQLite-safe migration persisting which cited strings were inferred per coverage row, their ReviewReason, and clearance state; `pending_review` as its own field on `CoverageCounts`/`TacticCoverage`, never folded into `unscored` or collapsed into `gap` per 5.1's already-settled decision; the four 5.1 invariants, including that clearing a flag moves the percentage at that moment and not before; and the panel-copy flip (it currently says a flagged citation counts toward coverage exactly as a confirmed one does — true today, false the moment #102 lands, and `AttackCitationAccounting.test.tsx` will pin the corrected string). Adversarial pass planned before merge, and #101/#102 get real closing keywords in that PR rather than an early mention.

One open design question I flagged before work starts, not yet answered: any assessment still in draft (not yet approved or released) that ran its AI citations before this migration lands will have zero persisted flag data, by construction — that's the exact gap being fixed. The question is whether such an assessment then reads as `pending_review` because its data is missing, or silently reads as fully confirmed because nothing on record contradicts it. The second behavior would repeat the same fail-open shape D-054 already rejected once on the nullable-vendor default. Not yet resolved either way.

Separately worth pricing in: #102 is a scoring change, and DELIVERY_PLAN.md itself already states scoring changes in this repo have historically run four to five adversarial rounds, not one. Not a reason to hold off, just a reason not to treat this as #103-sized.

## D-054, PR #96, PR #97, PR #98 — recap, see prior entries for full detail

D-054: W2 cut fresh off main, #29 never merges, closed as superseded once W2 lands (still not done as of this entry — W2 has merged, #29 is still open). Three open re-audit findings fixed as part of the W2 rewrite, nullable-vendor default set to refuse-and-flag — the same principle now at issue in the #101/#102 open question above. PR #96 fixed a live regression in W3's approval snapshot. PR #97 fixed the mutation-sweep tool's own node-identity bug. PR #98 made the audit gate structural; branch protection now enforces it for real.

## MVP tracking — status this round

Item 5 (W2) is DONE, merged as #103. Items 3a and 4 are DONE. Item 3b (ATT&CK export/persistence audit) is next, and folds in #101/#102's persistence work per the plan above. Items 6 (W1 Risk + #84), 7 (W1 ATT&CK), 8 (W6) remain not started.

## Open decisions — NOT to be reconstructed from memory

The #101/#102 in-flight-assessment question above — not yet answered by either side. #29 has not yet been closed as superseded, despite D-054 saying it would be once W2 lands — worth confirming this actually happens rather than assuming it will. `Require a pull request before merging` is off on branch protection — direct-push bypasses all required checks; worth a deliberate decision. Local-device mirror of this file — delivered once, not yet confirmed whether Gene wants it kept in sync going forward. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — unchanged from prior entries. Whether to parallelize item 6 with the current chain — still undecided.

## Resolved as of this round

#101 confirmed reopened on GitHub, with the explanation posted directly on the issue. #104 confirmed open, docs-only, correctly scoped as a written rule rather than an attempt to patch GitHub's own parsing. The #101/#102 persistence plan reviewed before work starts; one concrete design question raised (in-flight-assessment fail-open risk) and one estimate caution raised (scoring-change round count), neither yet answered.

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Still needs revision once #84's W1-Risk fold-in, #90's build, #92's contract-test fix, and item 3b (including #101/#102) are all landed and measured.

## Environment notes (standing)

Unchanged from prior entries: Postgres migrations clean through 0043, applied to dev Postgres and verified via alembic current. Provider live key: RESOLVED, reverted to fixture-by-default on purpose.

## Do not merge

PR #29 — under D-054 this should be closed as superseded now that W2 has landed; confirmed NOT yet closed as of this entry. Reference material only; still open on GitHub.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. A mechanism built to enforce a format only proves it handles the formats it was tested against — two instances (#98, #103), both closed correctly. Code can assert the opposite of what actually happens and nothing catches it until a human or an adversarial pass reads the code path directly — #103's panel-copy inversion remains the clearest instance; #102's planned panel-copy flip is this same shape being caught proactively before it ships, worth noting as the good version of this pattern. A fix that changes a value nothing reads is indistinguishable from a real fix by any test that only checks the value changed — #103's defect-1 finding. An issue tracker's own auto-close mechanism can produce the "status line is wrong" failure without any code being wrong — #101, now documented in CLAUDE.md via #104 as a standing writing rule: never place a closing keyword near an issue number in a sentence meant to say the opposite. A status line that is wrong is worse than none — now three distinct vectors logged: a hand-maintained plan doc, a CI gate's self-description, and an issue tracker's auto-close. A migration's effect on existing rows is not uniform by default — live open question on the #101/#102 work: what an assessment with no persisted flag data (because it predates the migration) should read as, rather than assumed to fall out automatically. A mechanism that reports on a violation is not the same as a mechanism that blocks it — closed for the audit gate specifically. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A mutation-testing survivor is only meaningful relative to which tests were actually run against it.
