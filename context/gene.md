# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (W2 merged as #103 — `e9e8783` — and #100 merged as `1c04358`, both confirmed directly on `main`'s commit history; #103's Disposition-format issue was fixed by reformatting the PR body, correctly treated as a separate future change rather than quietly loosening the gate's own parser; branch protection confirmed exactly as configured — 6 required checks including the audit gate, strict mode off, admin bypass on, force-push and deletion both blocked, no PR requirement; NEW this round: issue #101 shows CLOSED, auto-closed by the #103 merge commit, even though #103's own PR body explicitly says "flagged citations aren't persisted (#101, filed not fixed)" — a real contradiction between GitHub's tracked status and the PR's own stated truth)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103 merged, all verified directly on GitHub. Only #29 remains open (permanently unmerged under D-054, reference material only — confirmed via the open-PR list, nothing else is open). #84, #85, #87, #89, #90, #92, #102 filed and open. #101 is filed but shows CLOSED — see below, this is wrong and needs reopening. #99 was closed as a false-docs-only attempt superseded by #100.

## W2 (PR #103) — merged, `e9e8783`

citations.py rewritten fresh against "every rule finds exactly one candidate or gives up." Adversarial audit: 11 findings (10 confirmed, 1 plausible) plus 4 minors, all with real dispositions. Two were client-facing-severity: the panel told a consultant the inverse of the truth (a rejected citation was said to make a technique read as uncovered; it actually stayed fully covered with an empty tool list, so the real risk was overstated coverage, not understated), and defect 1's original #29/#30 fix was inert (INCOMPLETE_VENDOR_DATA was computed and nothing read it). Also caught: a real regression against main (case-variant vendor names in two lists caused a false ambiguous-rejection) and #72 instance eleven (test_defect_3 didn't test defect 3, since its fixture's two candidates shared a vendor).

Explicitly NOT done, stated rather than implied in the PR itself: a technique still scores covered when every citation for it was rejected (#102), and flagged citations aren't persisted (#101) — both filed. An earlier draft's false claim that 5.1 was "enforced in analytics.py" was removed from all three places it appeared.

## The gate's Disposition-format issue — resolved correctly

#103's own audit-gate check initially failed: check_audit_evidence.py's parser wants a colon-prefixed `Disposition:` line per finding, and the PR originally used only a markdown table. Fixed by reformatting the PR body to add literal `Disposition:` lines alongside the table, not by patching the parser to accept tables — the stated reasoning is sound and worth keeping as a standing principle: loosening the gate to fit your own currently-blocked PR is a change to the gate itself and belongs in its own reviewed change, never a quiet edit to get unblocked. The edited-trigger fix from #98's own finding 2 is what let the re-run pick up the fix without a new commit.

## Branch protection — final state, verified directly in Settings

Confirmed via the actual checkbox states, not just the summary given: `has_required_statuses` true with all 6 checks required (audit gate, Demo, E2E, Python, Secret scan, Web); `strict_required_status_checks_policy` false (strict/up-to-date off); `enforce_all_for_admins` false (admins can bypass); `allows_force_pushes` false; `allows_deletions` false; `has_required_reviews` false (no PR requirement — direct pushes to main are still possible and bypass the required checks entirely, confirmed firsthand when committing this file). Both judgment calls Gene made read as reasonable for a two-person team at this stage: admin bypass as a labeled, deliberate escape hatch rather than a silent one, and strict mode off to avoid forcing a rebase and full ~20-minute CI re-run on every PR at this cadence. Neither is something I'd push back on.

## NEW: #101 auto-closed by the merge, despite the PR saying it wasn't fixed

Checked #101 and #102 directly rather than trust "filed" at face value. #102 (5.1 pending_review enforcement) is correctly still open. #101 (flagged-citation persistence — "queued for a human" is neither queued nor retrievable) shows CLOSED, auto-closed by commit `e9e8783` — the same commit that merged #103. This directly contradicts #103's own PR body, which states in its own words that #101 was "filed not fixed." Something in the merge (a commit message or PR text GitHub parsed as a closing keyword) closed the issue without the underlying persistence/migration work being done. This matters concretely: #102's own body says "Needs #101 (the flags must be persisted before anything can clear them)" — the two were meant to be built together, and a closed #101 makes that dependency invisible to anyone scanning open issues next. Needs reopening before the #101+#102 work starts. Not yet actioned by either side as of this entry.

## D-054, PR #96, PR #97, PR #98 — recap, see prior entries for full detail

D-054: W2 cut fresh off main, #29 never merges, closed as superseded once W2 lands (still needs actually doing now that W2 has merged — #29 has not yet been closed as of this entry). Three open re-audit findings fixed as part of the rewrite, nullable-vendor default set to refuse-and-flag. PR #96 fixed a live regression in W3's approval snapshot. PR #97 fixed the mutation-sweep tool's own node-identity bug. PR #98 made the audit gate structural, with its own 9-finding self-audit, reporting-not-blocking until branch protection required it — now true and confirmed.

## MVP tracking — status this round

Item 5 (W2) is DONE — merged as #103. Items 3a and 4 are DONE (confirmed via #100). Next per the other session's own account: item 3b (ATT&CK export/persistence audit), now unblocked by W2, plus #101 and #102 which should be built together given #102's explicit dependency on #101's storage — though #101 needs reopening first. Items 6 (W1 Risk + #84), 7 (W1 ATT&CK), 8 (W6) remain not started.

## Open decisions — NOT to be reconstructed from memory

#101 needs reopening — a real, verified discrepancy, not yet actioned. #29 has not yet been closed as superseded, despite D-054 saying it would be once W2 lands — worth confirming this actually happens rather than assuming it will. `Require a pull request before merging` is off — direct-push bypasses all required checks; worth a deliberate decision rather than an unexamined default, especially now that the checks are meaningful. Local-device mirror of this file — delivered once, not yet confirmed whether Gene wants it kept in sync going forward. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — unchanged from prior entries. Nullable-vendor default under D-054 — adopted, not independently re-confirmed by Gene. Whether to parallelize item 6 with W2's successor work — still undecided.

## Resolved as of this round

#103 confirmed merged (`e9e8783`) with all findings verified directly from the PR body. #100 confirmed merged (`1c04358`). Branch protection's exact configuration confirmed via checkbox state, not summary. The Disposition-format fix confirmed correct in both outcome and reasoning. New, not previously known: #101 is closed but shouldn't be — flagged for reopening.

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Still needs revision once #84's W1-Risk fold-in, #90's build, #92's contract-test fix, and item 3b are all landed and measured — W2 itself is now landed and can be added to the sample.

## Environment notes (standing)

Unchanged from prior entries: Postgres migrations clean through 0043, applied to dev Postgres and verified via alembic current. Provider live key: RESOLVED, reverted to fixture-by-default on purpose.

## Do not merge

PR #29 — under D-054 this should be closed as superseded now that W2 has landed; confirmed NOT yet closed as of this entry. Reference material only; still open on GitHub.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. A mechanism built to enforce a format only proves it handles the formats it was tested against — two real instances (#98's bold-Findings case, #103's table-Disposition case), both now closed correctly. Code can assert the opposite of what actually happens and nothing catches it until a human or an adversarial pass reads the code path directly — #103's panel-copy inversion remains the clearest instance. A fix that changes a value nothing reads is indistinguishable from a real fix by any test that only checks the value changed — #103's defect-1 finding, same shape as PR #97's no-op-guard bug. NEW this round: an issue tracker's own auto-close mechanism can silently produce the exact "status line is wrong" failure the project already watches for in docs — #101 closed itself via a merge commit while the merging PR's own text said the opposite. The failure mode isn't new, but the vector (GitHub's own keyword-closing, not a hand-maintained status table) is one this list hadn't named before. A status line that is wrong is worse than none — now with three distinct vectors logged: a hand-maintained plan doc (D-053, #100), a CI gate's self-description (#98), and an issue tracker's auto-close (#101). A mechanism that reports on a violation is not the same as a mechanism that blocks it — closed for the audit gate specifically. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A mutation-testing survivor is only meaningful relative to which tests were actually run against it. A migration's effect on existing rows is not uniform by default, and "old rows behave as before, new rows get the new behavior" has to be stated and tested as its own case.
