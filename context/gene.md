# Gene's Context — 080426SHIELD

## Pick up here

Both open decisions from last round are settled and confirmed live on GitHub. PR #117 (item 9) is merged. Item 9 is now on `main` in DELIVERY_PLAN.md exactly as described: #114/#115/#46/#109 reclassified MVP-blocking, #59 stays deferred with a measured justification (0 NULL `parent_version` rows exist, 0 multi-version services exist, so #114 ships a loud typed error instead of a silent fallback), #46 folded into item 9 as the root of half of #115.

One new decision made this round: **sweep now, full audits post-MVP**, per the dev's own recommendation and mine. Told the dev to go ahead. The one condition attached: the post-MVP full-audit item needs an actual trigger (a date or a concrete kickoff condition) when it's filed, not just "post-MVP" sitting in a backlog next to #59 and #111 where it can quietly never come up. Not yet confirmed whether the dev has filed that item with a trigger attached.

**Last updated:** 2026-08-22 (PR #117 merged and confirmed directly, commit 634f6ea, 9 checks passed; item 9 confirmed live in DELIVERY_PLAN.md with exact language matching the relay; audit-expansion sizing comment on #117 read directly and matches the relay precisely; sweep-now/full-audit-post-MVP decision made and relayed)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## This round — verified against GitHub directly

**PR #117 merged.** `gene-png merged commit 634f6ea into main`, 9 checks passed (up from 7 required checks; this PR shows more because the merge check set has grown, not a discrepancy). Confirmed on the PR page itself.

**Both scope decisions from last round are real, on `main`, and hold up.** Read DELIVERY_PLAN.md's item 9 row directly: "Not started — MVP-blocking, reclassified 2026-08-22" with the #114/#115/#46/#109 description and the #59 fallback note, matching PR #117's body verbatim in substance. The measurement behind the #59 decision (4 of 4 finalize paths set `parent_version` at creation, 0 dev-DB rows with it NULL, 0 multi-version services, no production deployment) was read directly from the merged PR body, not taken on the relay's word.

**The audit-expansion sizing exists and matches exactly.** It's a comment on PR #117, posted by the dev, read in full. Targeted twin-sweep: ~0.5-1 session, item 9 stays ~2-2.5, sweeps seven named known defect shapes across CSF/ZT/Risk, explicitly does NOT find novel shapes (the dev states this limitation directly, not left implicit). Full audits: 2-3 sessions to audit plus 1-3 to fix (the fix half called out as the volatile part, since #114 alone turned into 8 call sites off one root cause), total 3-6, taking item 9 to 5-8 and MVP to 8-12, "close to doubling." Recommendation: sweep inside item 9 now, full audits as an honest post-MVP item rather than absorbed into a number that moves again.

**Decision made this round: take the recommendation.** Sweep now, inside item 9. Full audits post-MVP, but flagged one condition: that post-MVP item needs a real trigger when filed (a date or concrete kickoff condition), not just a backlog entry next to #59 and #111 that never comes up. Relayed to the dev; not yet confirmed whether the trigger condition was actually added when the item gets filed.

**Process note from the dev, worth keeping as-is.** Three cross-reference failures this session, in three different documents (a PR body pointing at a comment that didn't exist yet, DELIVERY_PLAN pointing at a stale branch-protection state, D-054 pointing at a no-longer-true caveat). Content was right each time, the pointer was wrong. No mechanical check currently catches this class, and the dev says so plainly rather than proposing a fix that doesn't exist yet. Worth remembering as an acknowledged gap, not a solved one.

## Branch / in flight

`main` has **#110, #113, #116, #117** merged, verified directly on GitHub. Nothing open blocking right now. Item 9's sweep work has not yet started as of this log (decision was just made this round).

## MVP tracking — DELIVERY_PLAN.md

9 of 13 items done, confirmed directly against `main`. Remaining: item 6 (W1 Risk + #84, 1.5-2 sessions), item 7 (W1 ATT&CK, 1 session), item 8 (W6 Risk export/publish, 0.5-1 session), item 9 (code-review-only defects, 1.5-2 sessions, now includes the twin-sweep per this round's decision, pushing it toward ~2-2.5). Total roughly 4.5-6 sessions before the sweep decision, likely closer to 5-6.5 once the sweep is folded in, not yet re-quoted by the dev. **Separately tracked, not in the above total:** full CSF/ZT/Risk audits, now explicitly a post-MVP item per this round's decision, needs a real trigger when filed.

## D-054, D-055, D-056, D-052 — decisions log

Unchanged from prior entries.

## Open decisions — NOT to be reconstructed from memory

**New this round:** whether the post-MVP full-audit item actually gets filed with a real trigger (date or condition), per the condition I attached to approving the sweep-now path. Whether #111 (admin-console N+1) gets pulled ahead of item 7, still undecided.

**Still open, unchanged:** path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6.

## Resolved as of this round

PR #117 (item 9) merged and independently confirmed. Both scope decisions (#59 deferred with a loud fallback, #46 folded into item 9) verified live on `main` in DELIVERY_PLAN.md, not just in a PR body. Audit-expansion sizing read directly from #117's comment and matches the relay exactly. Sweep-now/full-audit-post-MVP decision made.

## MVP-complete vs. client-ready — standing distinction

Unchanged. Worth restating given this round's outcome: even after item 9's sweep, full CSF/ZT/Risk audits remain a post-MVP item, meaning novel per-service defects in three of five services will not be found before MVP completion. That's a stated, deliberate trade-off, not an oversight, but it belongs in the client-ready conversation later, not forgotten by then.

## Adversarial-reviewer and Playwright

Unchanged from prior entries.

## Environment notes (standing)

Unchanged. Open issue count last confirmed at 34, not rechecked this round.

## Do not merge

Nothing open blocking `main` as of this log.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list, plus item 9's seven named known shapes now formally enumerated in #117's sizing comment (worth treating that comment as the canonical list going forward rather than re-deriving it). **New this round:** a reference/cross-reference between documents can be wrong even when the content on both ends is correct, three real instances surfaced this session alone (PR body to comment, DELIVERY_PLAN to branch-protection state, D-054 to caveat), and there is currently no mechanical check for this class, unlike the closing-keyword problem which got one. Named as an open gap, not a solved one.
