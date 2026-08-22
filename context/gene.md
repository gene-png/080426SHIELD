# Gene's Context — 080426SHIELD

## Pick up here

Two things need your decision, not just your read.

1. **#59 dependency risk, found independently, not raised by the dev's relay.** Item 9's centerpiece fix (#114) is supposed to resolve the deliverable from `parent_version` instead of "latest finalized." But `parent_version` is NULL for any pre-existing multi-version parent, because the only repair path for that (#59) is a confirmed permanent no-op, and #59 sits in DELIVERY_PLAN.md's **Deferred, NOT part of MVP** table under W5. So item 9 is now MVP-blocking, but its main fix depends on something explicitly scoped outside MVP. The dev already named the fallback options in #114's own thread (fail loudly on NULL, or backfill first) but hasn't picked one, and #59 itself hasn't been pulled into the MVP path. Needs a decision: pull #59 in, or confirm the fail-loudly fallback ships instead and #59 stays deferred.
2. **Item 9 scope: should it also cover CSF/ZT/Risk audits (3a/3b only covered Tech Debt and ATT&CK)?** The dev recommends yes, same session. Worth asking for a size estimate before agreeing, given #114 alone just went from "2 suspected twins" to "4 confirmed plus 4 more lesser instances" once someone actually checked — the unaudited services are exactly where that pattern would repeat.

Otherwise: PR #116 (item 3b) is **merged**, confirmed directly (commit 1573529, 7 checks passed). PR #117 (item 9: reclassifies #114/#115/#109 as mvp-blocking) is open, not yet merged as of this check. #46 is genuinely NOT fixed, confirmed by the dev in detail: `require_list_at` still returns `[]` on a missing key, silently. The dev wants to fold #46 into item 9's work rather than fix separately, but has not actually labelled #46 `mvp-blocking` or added it to #117's body — worth confirming that's not just a dropped intention.

**Last updated:** 2026-08-22 (PR #116 merged and independently confirmed; PR #117 opened for item 9, docs-only, matches relay; #114 twin-check confirmed at 4 dashboards not 2, plus a second lesser 4-site instance, both independently verified against the issue thread; #59's "deferred, not MVP" status creates an unstated dependency conflict with item 9's own mvp-blocking status; #46 confirmed still genuinely broken, not just newly caught)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## This round — verified against GitHub directly, not relayed as-is

**PR #116 merged.** `gene-png merged commit 1573529 into main`, 7 checks passed. Confirmed on the PR page itself, not inferred from the relay.

**PR #117 opened for item 9, and its body matches the relay closely.** Docs-only (`+29 -1`, one file). Moves #114, #115, #109 to `mvp-blocking`, adds item 9 to DELIVERY_PLAN.md, and states explicitly that item 9 is **not exhaustive** — the audits that surfaced these (3a, 3b) covered Tech Debt and ATT&CK only, CSF/ZT/Risk have had no equivalent pass. Adversarial audit disposition: none, docs-only, no code touched, recorded rather than relying on the `.md`-path exemption. Not yet merged: 4 checks (Demo, E2E, Python, Web) were still in progress, 3 passed (Audit gate, No accidental issue closes, Secret scan), at last look.

**#46: confirmed genuinely unfixed, not just newly caught.** Read the issue directly; it's still Open with no labels. The dev's explanation (require_list_at's `data.get(key, [])` default silently returns empty on a missing key, and the new test from #116 only covers "key present, wrong type") is consistent with #116's own PR body, which already said the same thing in different words. What's NOT yet reflected anywhere on GitHub: the dev's stated intent to fold #46 into item 9. #46 has no `mvp-blocking` label and isn't named in #117's body. Worth a direct question rather than assuming it's tracked.

**#114: twins confirmed, and worse than suspected.** Read the issue thread directly, including the dev's follow-up comment. Original suspicion was 2 twins (CSF, ZT). Confirmed: **4 of 4** client dashboards have the identical defect (attack, zt, tech_debt, csf) — Tech Debt wasn't even suspected originally, which the dev correctly calls the same #79 shape (a sweep that stops at the two services someone happened to name). Plus a second, lower-severity instance: 4 more call sites (`_csf_gap_total`, `_zt_gap_total`, `_attack_uncovered_total`, `_tech_debt_savings`) feed the `/home` value-loop card off the same stale-resolution pattern, no false version label but same root cause. Total scope: 8 call sites, 1 root cause. All independently verified against the actual issue text, not taken from the relay.

**#59, read directly: this is a real constraint on item 9, not a footnote.** Confirmed Open, and DELIVERY_PLAN.md's own "Deferred, NOT part of MVP" table lists it under W5, explicitly separate from the MVP path. The issue itself documents, with a specific failure scenario, that the repair path for `parent_version` is a permanent no-op for any service with more than one parent version — meaning #114's suggested fix (resolve from `parent_version` instead of latest-finalized) will silently do nothing for exactly the rows most likely to need it, unless it fails loudly or #59 lands first. Neither has been decided yet. This is the dependency flagged in "Pick up here."

**#109: confirmed labelled `mvp-blocking`.** Matches #117's stated scope.

**DELIVERY_PLAN.md on `main`, read directly: stale in one place.** Item 3b is now correctly marked DONE with the full defect list. But the "Total remaining: roughly 3.5-5 focused sessions" line right below the table still lists "items 3b, 6, 7 and 8" as remaining, unchanged from before 3b merged. Minor, same status-line-lag pattern already logged from the #73/#79 round, not urgent, but should get fixed in the same PR that lands item 9's totals.

## Branch / in flight

`main` has **#110, #113, #116** merged, verified directly on GitHub. Open: **#117** (item 9, docs-only, checks were in progress at last look). Labelled `mvp-blocking` and confirmed: **#109, #114**. Not yet labelled despite being discussed as in-scope: **#46**.

## MVP tracking — DELIVERY_PLAN.md

9 of 12 items done on `main` now that #116 (item 3b) is merged, confirmed directly. Item 9 will formalize once #117 merges. Remaining: item 6 (W1 Risk + #84), item 7 (W1 ATT&CK), item 8 (W6 Risk export/publish), item 9 (#114/#115/#109, and possibly a wider CSF/ZT/Risk audit if you approve the dev's suggestion). Per #117: totals now 4-5.5 sessions across items 6, 7, 8, 9. **Not folded into that estimate:** #59 if it needs to land before #114's fix, and #46 if it's genuinely being done as part of item 9's work rather than separately.

## D-054, D-055, D-056, D-052 — decisions log

Unchanged from prior entries. D-052 confirmed to hold for ATT&CK via item 3b, mechanically pinned via `registered_jobs()`, verified in the merged PR.

## Open decisions — NOT to be reconstructed from memory

**New this round:** whether #59 gets pulled into MVP scope or #114 ships with a documented fail-loud fallback instead, your call, not yet made either way. Whether item 9 expands to cover CSF/ZT/Risk audits (dev recommends yes; worth a size estimate first). Whether #46 is actually being folded into item 9's work or just informally mentioned, needs a direct confirmation since the tracker doesn't show it. Whether #111 (admin-console N+1) gets pulled ahead of item 7, still undecided.

**Still open, unchanged:** path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6.

## Resolved as of this round

PR #116 (item 3b) merged and independently confirmed on the PR page. PR #117 opened for item 9 and its content verified against the relay, matches closely. #109 and #114 both confirmed labelled `mvp-blocking`. #114's twin scope confirmed directly from the issue thread at 4 dashboards plus 4 lesser call sites, not taken on the dev's word alone.

## MVP-complete vs. client-ready — standing distinction

Unchanged from last round. Gene's plan: finish MVP, then a dedicated testing pass focused on UI and AI-output consistency, with code-level-only-catchable defects carved out and pushed into MVP-blocking scope instead. Item 9 is the first real application of that policy, and #59's dependency issue is a direct example of why: it's not visible from the UI, it would not surface in a UI-focused pass, and it was only found because someone read the actual repair-path code.

## Environment notes (standing)

Unchanged. Open issue count last confirmed at 34; not rechecked this round.

## Do not merge

None blocking `main`. #117 was not yet fully green as of this check, verify before merging.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list. **New this round:** the #79 shape (a sweep that stops at the services someone happened to name) recurred again inside #114 itself, at a new scale, Tech Debt was not in the original suspicion and turned out to have the identical defect. And: a fix scoped as MVP-blocking can still depend on something scoped as NOT-MVP (#114 depends on #59) without that dependency being stated anywhere until someone reads both issues side by side, worth watching for elsewhere in items 6-9.
