# Gene's Context: 080426SHIELD

## Pick up here

Both PRs are real and green. PR #127 (ZT truncation test) and PR #128 (adversarial-reviewer rule in CLAUDE.md, MVP resize to 8-10.5, D-057) verified directly on GitHub: both open, both 7/7 checks passed, both carry their own adversarial-audit section. #128's content is more precise than the relay conveyed, including a self-correction of a number I'd previously verified as accurate ("four of seven" wrong verdicts is actually "four of six"). Recommend merging both now.

**Last updated:** 2026-08-22 (PR #127 and PR #128 confirmed open, green, and content-accurate against GitHub; D-057 read in full; the refuted #108 finding checked; a raw.githubusercontent.com caching gotcha caught and noted)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine; a local computer restart does not affect it.**

## This round, verified against GitHub directly

**PR #127 (ZT test) confirmed**, open, 7/7 checks green, one commit. Its own adversarial-audit section: 1 finding (the test was written after the behavior it tests, so proved nothing until the revert-check was added), fixed before pushing. Matches what was committed on the branch two rounds ago.

**PR #128 (rule + resize + review) confirmed**, open, 7/7 checks green, two commits, six files changed (`.claude/agents/adversarial-reviewer.md`, `.claude/commands/loop-sprint-cron.md`, `.claude/commands/pr.md`, `CLAUDE.md`, `DECISIONS.md`, `DELIVERY_PLAN.md`). The resize table in the PR body matches what I verified two rounds ago exactly: item 6 1.5-2 to 3-4, item 8 0.5-1 to 1-1.5, item 9 2-2.5 to 3-4, total 5-6.5 to 8-10.5, arithmetic checked (3+1+1+3=8, 4+1+1.5+4=10.5).

**D-057 read in full on the branch.** Reverses part of D-054 (which rejected "document the gate in CLAUDE.md" as a discipline fix) on a stated distinction: D-054 rejected documenting a mechanism that already existed, D-057 requires running the reviewer at all, which nothing enforces. Tagged `Issues: #108`. D-054 itself now carries a dated in-entry correction pointing to D-057, in the project's established house style for reversals.

**The self-correction is real and matters.** D-054's corrected text now reads "re-auditing that sweep overturned four of its six verdicts," not seven. The original twin-sweep evaluated six shapes cleanly plus the one real finding, not seven; the earlier round's "four of seven" (which I verified as an accurate transcription of what was posted, and reported as confirmed) was itself wrong at the source. Worth remembering: I confirmed the relay matched GitHub; I did not re-derive the count myself. Same caveat as before, now with a second concrete instance.

**The refuted finding is the best evidence the rule is working as designed.** The reviewer marked "the CLAUDE.md half of #108 is not supported by the repo" as CONFIRMED while stating it could not read GitHub issues. The dev re-verified against #108 directly (it names CLAUDE.md twice) and refuted the finding rather than accepting it. This is exactly the "a finding is a question, not a verdict, re-verify every one" clause doing its job on the first real use.

**One thing I caught in my own process, not a repo issue:** `raw.githubusercontent.com` returned a stale (pre-push) version of `DECISIONS.md` on the PR branch immediately after checking, showing no D-057. The GitHub blob view (`/blob/<branch>/...`) had it correctly. Raw's CDN can lag a push by up to a minute or two; prefer the blob UI for anything checked right after a commit.

**#108 is not fully closed by this PR.** Its three suggested fixes were: correct the gate's self-description (done via PR #105), add a PR template audit section (not addressed here), add the gate to CLAUDE.md's collaboration rules (done here, via the adversarial-reviewer rule rather than the audit-gate specifically, which is a reasonable reading but not a literal match). #108 should stay open until the PR template piece lands or someone decides it's out of scope. Not a red flag, just tracking.

## MVP tracking: DELIVERY_PLAN.md

**Still pending merge, not yet on `main`.** The 8-10.5 total lives in PR #128, verified accurate to what was reported, but `main` itself still shows 5-6.5 until the PR merges. Once it merges, gene.md and DELIVERY_PLAN.md will agree for the first time this round.

## D-054, D-055, D-056, D-057, D-052: decisions log

D-057 new this round (see above). D-054 carries an in-entry correction pointing to D-057. Others unchanged from prior entries.

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether the PR template piece of #108 (the still-unaddressed suggested fix) gets its own issue or gets folded into a future PR. Whether #84 should get the `mvp-blocking` label (still open from last round, unaffected by this PR).

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead of item 7. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. First real unattended cron run (the Monday after 2026-08-22), worth confirming it actually fired.

## Resolved as of this round

PR #127 and PR #128 confirmed real, open, and green. D-057 read in full and matches the relay. The four-of-six correction confirmed. The #108 refutation confirmed as the rule's first real re-verify catch working correctly.

## MVP-complete vs. client-ready: standing distinction

Unchanged.

## Adversarial-reviewer and Playwright

**Updated this round:** the rule is now real, in `CLAUDE.md` on the PR branch (not yet `main`), with the evidence, the three operational clauses, and the D-057 decision backing it. Its first real use (this PR reviewing itself) caught 11 findings, 9 fixed, 1 correctly refuted, 1 deliberately left. That is a working demonstration, not just a policy.

## Environment notes (standing)

**New this round:** `raw.githubusercontent.com` can serve a stale version of a file for roughly a minute after a push; the blob UI (`/blob/<branch>/<path>`) does not have this lag. Prefer blob view when verifying something checked immediately after a commit. Open issue count last confirmed at 34 pre-#121-126; six new issues since (#121-#126), unchanged this round.

## Do not merge

Nothing open blocking `main`. Two PRs open and green: #127, #128. Both recommended for merge.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list plus last round's vocabulary-vs-shape addition. **New this round:** a number carried forward from an earlier round can be wrong at the source, not just mistranscribed later. Confirming a relay matches what's on GitHub is not the same as confirming the number GitHub shows is itself correct; "four of seven" passed that first check cleanly last round and was still wrong.
