# Gene's Context: 080426SHIELD

## Pick up here

Item 9's adversarial re-audit is resolved: F6 and its two siblings are split correctly across items 6/8/9, not absorbed into item 9's number. Six new issues (#121-#126) filed and verified word-for-word on GitHub; #84 amended with a second call site; the ZT truncation-caption fix committed to a branch with a real revert-check. Two things the dev told Gene in chat are NOT yet true on GitHub: the new "8-10.5 session" total is not in DELIVERY_PLAN.md (main still says 5-6.5), and the "run the adversarial reviewer on every PR" rule is not in CLAUDE.md. Both need a PR before they count as decided, the same way #117 made item 9's reclassification real.

**Last updated:** 2026-08-22 (item 6/8/9 split verified issue-by-issue against GitHub; #84's second call site and the missed-grep explanation confirmed; ZT truncation test confirmed committed with a documented revert-check on an unopened branch; two claims from the relay, the new session totals and the adversarial-reviewer standing instruction, confirmed NOT YET recorded anywhere on GitHub)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine; a local computer restart does not affect it.**

## This round, verified against GitHub directly

**All six new issues confirmed, word for word.** #121 (Risk prompt/parser drift, this is F6), #122 (Risk's audit row counts findings received, never entries persisted), #123 (Risk dashboard 404s on Generate; resolves latest register, not latest finalized one), #124 (ZT client dashboard ignores the engagement target), #125 (DoD ZTRA target silently clamped, then labelled "client"), #126 (Tech Debt annual spend is an unflagged floor) all exist, all labeled `mvp-blocking`, and all read exactly as relayed; if anything the GitHub bodies are more detailed than what came through chat (exact line numbers, failure scenarios, suggested fixes). Item assignment matches the relay exactly: #121 + #122 -> item 6, #123 -> item 8, #124 + #125 + #126 -> item 9.

**#84's amendment confirmed**, with a detail the relay didn't carry: the dev's new comment explains why the original export-trio sweep caught only one of #84's two call sites (`risk.py:177`) and missed the other (`risk.py:193`); the grep pattern used, `(maturity_tier|maturity_stage|target_stage|target_tier) *[<>=]+ *[0-9]`, cannot match `else 3` or `< tgt`. CLAUDE.md already records the grep that does find it (`is not None else [0-9]`), and the dev's comment names not having used it. Worth flagging: #84 carries only the `bug` label, not `mvp-blocking`, even though it's explicitly folded into item 6 and item 6 is MVP-blocking; the same labeling gap #46 had two rounds ago.

**ZT truncation test confirmed committed.** Branch `fix/zt-truncation-disclosure-test`, single commit `f3dabab`, no PR opened yet (0 open PRs in the repo as of this check). The commit message documents a real revert-check: deleting the truncated-branch disclosure produces exactly 1 failure, the new test, with the pre-existing (wrong-branch) test still green. It also extends coverage to DOCX and PDF, which the original XLSX-only test never touched.

**Two things from the relay are NOT yet on GitHub; worth raising with the dev before treating them as settled:**

1. The "real numbers" table (item 6: 3-4, item 8: 1-1.5, item 9: 3-4, item 7: 1 unchanged, MVP total: 8-10.5) exists only in chat. `DELIVERY_PLAN.md` on `main` still shows item 6 at 1.5-2, item 9 at 2-2.5, and "Total remaining: roughly 5-6.5 focused sessions"; unchanged since PR #117. There is no open PR anywhere in the repo carrying this update (0 open PRs, checked directly). Every prior re-scope this project has done went in as a merged PR before being treated as decided; #117 for item 9's reclassification, #88 for folding #84 into W1. This one hasn't yet.
2. The "standing instruction... saved to memory" to run the adversarial reviewer on every PR/finding before opening it: searched CLAUDE.md in full, no such rule exists there. CLAUDE.md's own stated purpose is "durable facts... if it's a fact that outlives the current sprint, it belongs here," and the file elsewhere makes exactly this point about the difference between a lesson that's written down and one that's only remembered; the closing-keyword rule was rewritten three times and violated a fourth before someone made it a mechanical check. "Saved to memory" for a Claude session doesn't survive a context reset or a different session picking up the work. If it's meant to bind every future PR, it belongs in CLAUDE.md.

**The split itself holds up.** The table's arithmetic is internally consistent (old items sum to 5-6.5, new items sum to 8-10.5, matching both stated totals), and the per-item reasoning is proportionate to what's actually in each issue: #121 is a genuine prompt/parser contract decision plus a new contract test modeled on CSF's, which is why item 6 more than doubled; #123 reuses an existing "resolve latest-finalized, not latest" pattern already used by four other dashboards, consistent with a smaller +0.5-1; item 9's three new issues cost roughly what its first four cost per issue. More importantly, the split resolves the concern raised last round: #121/#122/#84 landed in item 6, not item 9, so item 9's number did not silently absorb item 6's pre-existing, previously-underpriced cost. Gene was right to insist on the split for exactly this reason.

## Branch / in flight

`main` unchanged since #119 (`main` carries #110, #113, #116, #117, #119, all verified merged in prior rounds). New work exists only on unmerged branches/issues: `fix/zt-truncation-disclosure-test` (1 commit, no PR), and six new issues (#121-#126) with no linked branches yet. #84 has a new comment but no code change yet.

## MVP tracking: DELIVERY_PLAN.md

**Two different totals currently in circulation.** The repo (`DELIVERY_PLAN.md` on `main`) still says 5-6.5 sessions across items 6/7/8/9. The dev's relay says 8-10.5, reflecting #121-#126 and the amended #84. The relay's number is almost certainly the more accurate one, since it accounts for real, now-filed defects the repo's own total doesn't yet know about, but until a PR lands the update, gene.md and DELIVERY_PLAN.md disagree; the "cross-reference wrong even when both ends are correct" class already logged. Recommend asking the dev to land the DELIVERY_PLAN.md update the same way #117 landed item 9's reclassification.

## D-054, D-055, D-056, D-052: decisions log

Unchanged from prior entries.

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether the dev lands the DELIVERY_PLAN.md session-total update and the CLAUDE.md adversarial-reviewer rule as PRs before Gene treats them as settled (recommended: yes, before proceeding on the new numbers). Whether #84 should get the `mvp-blocking` label to match its #109/#114/#115/#46-class siblings.

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead of item 7. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. First real unattended cron run (the Monday after 2026-08-22); worth confirming it actually fired.

## Resolved as of this round

The item 6/8/9 split verified issue-by-issue; all six new issues confirmed real and correctly assigned. #84's second call site and the missed-grep explanation confirmed. ZT truncation test confirmed committed with a genuine revert-check. The split resolves the F6-vs-item-9 concern raised last round.

## MVP-complete vs. client-ready: standing distinction

Unchanged.

## Adversarial-reviewer and Playwright

**New this round:** the dev's stated intent to run the adversarial reviewer proactively on every PR/finding, rather than on request, is a good instinct given the twin-sweep's four wrong verdicts; but as of this check it exists only as a stated intention, not a written rule anywhere in the repo. Worth tracking whether it gets written down and whether it actually gets followed on the next PR; #121/#122/#84's eventual fix and the ZT test's eventual PR are the first real tests of it.

## Environment notes (standing)

Unchanged. Open issue count last confirmed at 34 (2026-08-22, pre-#121-126); six new issues since (#121-#126, all open, all `mvp-blocking` except #84, which is separate, pre-existing, and unlabeled as such).

## Do not merge

Nothing open blocking `main`. Also nothing currently in an open PR at all; 0 open PRs as of this check.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list. **New this round:** a sweep that searches by a defect's known vocabulary instead of its underlying shape will miss a match already sitting in the project's own prior documentation. F6 was catalogued by name in `docs/plans/2026-08-08-cross-service-integrity.md` two weeks before the twin-sweep re-missed it, because the sweep searched for prior instances' field names rather than the "prompt vocabulary disagrees with parser vocabulary" pattern itself. This is the same lesson CLAUDE.md already records for #84's grep (symbol vs. symptom), now confirmed to generalize to whole-document sweeps, not just call-site greps.
