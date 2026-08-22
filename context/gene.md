# Gene's Context — 080426SHIELD

## Pick up here

Item 9 is now fully specified and de-risked. Nothing blocking. The scheduled-trigger mechanism (#119, merged) is proven end-to-end against the live GitHub API, not just designed, confirmed by reading the actual workflow run history and the throwaway issue's real bot comment. The twin-sweep across CSF/ZT/Risk is done and reported (not yet fixed): one real finding, ZT's truncation-disclosure caption is untested on the truncated branch. Told the dev to proceed from reporting to fixing. Item 9's number holds at 2-2.5 sessions, the fix is one test file.

**Last updated:** 2026-08-22 (PR #119 merged and its mechanism independently verified via two real Actions runs and a real closed throwaway issue #120, not taken on the dev's word; twin-sweep results read in full from #118's comment, one real finding confirmed: ZT's truncation caption tests only the untruncated branch; #118 confirmed still untouched, correctly skipped by both test runs since its date is in the future)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## This round — verified against GitHub directly

**PR #119 merged**, commit 2a47337, 7 checks passed, confirmed on the PR page.

**The scheduled-trigger mechanism is proven, not just shipped.** Read the Actions run history for `scheduled-triggers.yml` directly: 2 manual runs, both by gene-png. Read issue #120 directly: a real throwaway with `Trigger-date: 2020-01-01`, closed with a real bot comment from `github-actions` quoting the `Trigger-reason`, and a real `trigger-fired` label applied. Confirmed the dev's table is accurate: future-dated #118 was skipped on both runs, past-dated #120 fired once and produced exactly one comment across both dispatches (the idempotency claim). Re-checked #118 directly afterward: still only `scheduled-trigger`, no `trigger-fired`, no comment, exactly as it should be. The only remaining unverified piece is the actual Monday 07:00 UTC cron firing on its own; the `gh` interaction itself, the part previously flagged as untested, is now proven against the real API.

**Twin-sweep across CSF/ZT/Risk: done, reported, not yet fixed.** Read #118's sweep-result comment in full. Six of seven known defect shapes came back clean across all three services. One real finding: `apps/api/app/zt/exporters.py` builds two caption branches (untruncated / truncated), and `test_zt_exporters.py` only asserts the untruncated one. Deleting the truncated branch's disclosure would leave the suite green. This is confirmed worse than ATT&CK's original 3b finding: ATT&CK had no caption test at all, so the gap was visible to a grep; ZT has a passing test that reads as coverage while asserting the wrong branch, a harder failure mode to catch because CI looks trustworthy. CSF is confirmed properly pinned on both branches, in both XLSX and DOCX. The dev's own caveat is accurate and worth keeping: six-of-seven clean means D-049/D-052's lessons generalized broadly, not that CSF/ZT/Risk are sound overall, since a sweep only catches shapes already seen once, and 3b's own headline finding (rollup-vs-rows) had no precedent to sweep for.

**Decision made this round:** move from reporting to fixing. Told the dev to write the ZT caption test now.

## Branch / in flight

`main` has **#110, #113, #116, #117, #119** merged, verified directly on GitHub. #118 remains open, untouched, correctly holding its future trigger date, now carrying the twin-sweep results as a comment for whoever picks it up. The one ZT test fix from the sweep has not yet been written.

## MVP tracking — DELIVERY_PLAN.md

9 of 13 items done. Item 9 (code-review-only defects + twin-sweep) at 2-2.5 sessions, unchanged and confirmed by the sweep's outcome, the fix is one test file. Remaining: items 6, 7, 8, 9. MVP total 5-6.5 sessions, last confirmed figure, not re-quoted this round since nothing moved it. Separately tracked: #118 (full CSF/ZT/Risk audits), post-MVP, real trigger date 2026-10-01, now also carrying the twin-sweep table so the eventual audit knows what's already been checked.

## D-054, D-055, D-056, D-052 — decisions log

Unchanged from prior entries.

## Open decisions — NOT to be reconstructed from memory

**New this round:** none, both decisions from the prior round are now settled and verified. First real unattended cron run lands the Monday after 2026-08-22; worth confirming it actually fired rather than assuming, since that's the one link in the chain still unexercised.

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead of item 7. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6.

## Resolved as of this round

PR #119 merged and its mechanism independently proven against the live API (not just self-reported), via two real Actions runs and a real closed throwaway issue. Twin-sweep complete and verified in full from source; one real finding confirmed (ZT truncation caption), six shapes confirmed clean with the correct caveat attached. Decision made to proceed to the fix.

## MVP-complete vs. client-ready — standing distinction

Unchanged. This round is a good concrete example of the distinction holding up in practice: the ZT caption gap is exactly the kind of defect a UI-focused pre-launch pass would never catch (the rendered output looks identical whether the branch is tested or not), and it was caught precisely because code-level-only-catchable defects were made MVP-blocking rather than left to Gene's own review.

## Adversarial-reviewer and Playwright

Unchanged from prior entries.

## Environment notes (standing)

Unchanged. Open issue count last confirmed at 34, not rechecked this round. New issues since: #118 (open, deferred), #120 (closed, throwaway, expected).

## Do not merge

Nothing open blocking `main` as of this log.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list, now including item 9's seven-shape sweep table (recorded canonically on #118). **New this round:** a test that asserts only one branch of a two-branch function can be strictly worse than no test at all, because it produces a passing CI run that reads as coverage. Watch for this shape specifically wherever a renderer or exporter has a truncated/untruncated or happy-path/edge-path split, the untested branch is invisible unless someone checks which branch the assertion actually exercises.
