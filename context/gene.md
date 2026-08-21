# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-21 (#101 + #102 built out on `feat/attack-pending-review`. The state matrix was written BEFORE the wiring, as planned, and paid for itself twice: it found that `gap` was withholdable in the already-committed analytics half — which RAISES coverage_pct, because addressable is the denominator — and the pre-existing `test_heatmap_reflects_coverage_after_patches` then caught that the first predicate withheld every hand-curated row, breaking the whole manual workflow with no way to clear it. Both were design errors, not bugs, and neither would have been visible in a matrix written after the fix. D-055 records the rule; no PR yet, and the §14 adversarial audit has NOT been run — see open decisions.)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103 merged, all verified directly on GitHub. Open: #104 (docs-only closing-keyword rule, checks green except the audit-gate's own pending re-check as of last look). Closed: #29 (superseded-in-part, see below), #99, and all older. #84, #85, #87, #89, #90, #92, #102, #33 filed and open. #101 reopened, correctly still open (no PR yet for the persistence work).

## PR #29 — closed, but only half genuinely superseded

Before closing, checked #29's actual diff and issue #33 rather than assume D-054's "close once W2 lands" meant "everything in #29 is now dead." It doesn't. #29 had two halves: (A) an `/ai-inputs` panel showing what the ATT&CK mapping will run against before a consultant clicks start, and (B) sending the model the extractor's real structured fields (vendor, category, security_functions) instead of bare names, with a deliberate privacy boundary excluding notes/cost/workflow-state fields, pinned by its own test. W2 (#103) only ever replaced the citation-resolver logic — the actually-defective part (13 findings, 2 blockers in #30's audit). It explicitly did not touch the panel or the enrichment payload.

DELIVERY_PLAN.md independently confirms this: item 7 ("W1 ATT&CK step") is listed as not started, blocked only by W2 — which just landed — and issue #33 (still open) tracks exactly the panel/enrichment code's known bugs (panel not rendering pre-assessment, org-named tools permanently uncitable, draft-count over-count, plus lower-severity findings 7/8/10/12/13). None of those read as structural the way the resolver's defects were; #29's panel/enrichment code passed 838 backend + 147 vitest tests.

Closed #29 with a comment on the issue itself (not just here) stating explicitly: the resolver half should not be ported from this branch; the panel/enrichment half is live work now tracked as item 7 and #33, not dead; and whoever scopes item 7 needs to deliberately decide rebase-this-branch vs. rewrite-fresh, since D-054's rationale for a fresh rewrite was specific to the resolver's defect density and doesn't automatically transfer to code with a much lower defect rate. Not yet decided which way — flagged as an open decision below.

## #101/#102 — built out this round, on branch, NOT audited, no PR

What landed on `feat/attack-pending-review` (all gates green except the audit): `app/attack/pending.py` (the rule, 3 evidence cases), run-AI persistence per FIELD, `patch_coverage` taking authorship, a first-class `POST /attack/coverage/{id}/confirm-citations`, heatmap + finalize + all three exporters + `seed_demo`, and the UI (rollup pill + NumberCard, matrix badge, technique-panel review queue with a Confirm button, panel copy flipped). 247 vitest / all attack pytest green, ruff+black+prettier+eslint+tsc+test-integrity clean.

**Three decisions taken that were NOT in 5.1, all recorded in D-055.** Flagging them here because each changes a client-facing number and none is a detail:

1. **`gap` is not withholdable.** The committed analytics half had it in `_WITHHOLDABLE`. Withholding a gap shrinks the denominator only — ten covered beside ten gaps went from 50% to **100%** with the gaps flagged, deleting ten findings. Invariant 1 read backwards.
2. **Three evidence states, not two.** "No confirmed tool backs this" withheld every hand-curated row. A consultant typing `covered` is the AUTHOR of the claim, not a reviewer of the model's. So rejections and no-citation-at-all are now PERSISTED (entries with `tool: null`) — without them, "the model's evidence was dropped" and "nobody ever cited anything" are the same stored bytes and the rule cannot separate them.
3. **The percentage is not self-describing.** Withholding narrows the denominator, so under PARTIAL flagging the ratio can rise (95% → 100% when one partial is withheld). Unavoidable given 5.1's chosen mechanism; the mitigation is that `pending_review` is now rendered beside `coverage_pct` on every surface, with a test that says why.

Also found and fixed while re-reading the apply loop, worth knowing because it is this change's own guard inverting: a rerun that returned a status and no tool fields reset `unconfirmed_citations` to `[]` while KEEPING the tools the erased flags applied — a withheld row would flip to scoring with no human involved. Now merged per-field.

## Superseded — the earlier #101/#102 entry

Recap, see prior entry for full detail: the migration docstring's own NULL-means-"leave scoring as today" language was caught as the same fail-open shape D-054 already rejected once, fixed to three-value semantics (NULL and uncleared-inferred both score pending, `[]` scores normally). Blast radius checked: zero RELEASED assessments, no production deployment yet, all 30,384 rows dev/demo. Sizing corrected to 2-3 sessions / 4-5 rounds, with the state-space-first principle stated for future scoring changes. Analytics half done (10 tests green); persistence wiring, seed, and panel-copy flip still ahead.

## D-054, PR #96, PR #97, PR #98 — recap, see prior entries for full detail

D-054: W2 cut fresh off main; #29 closed as superseded now that W2 landed — done this round, but with the resolver-only scope made explicit rather than assumed total. Nullable-vendor default set to refuse-and-flag — the same principle reapplied twice more since (the #101/#102 NULL-citation case, and implicitly the reasoning behind why #29's still-live half shouldn't be silently discarded). PR #96/#97/#98 recap unchanged; branch protection enforces the audit gate for real.

## MVP tracking — status this round

Item 5 (W2) DONE. Items 3a and 4 DONE. Item 7 (W1 ATT&CK step) is now unblocked and has a real starting point — #29's diff, plus #33's cataloged bugs — but is NOT started, and the rebase-vs-rewrite decision needs making before it is. Item 3b in progress via #101/#102 (2-3 sessions, correctly re-sized). Items 6, 8 not started. DELIVERY_PLAN.md itself is stale again on item 5 specifically (still shows "IN PROGRESS" as of the version checked this round, since #100's fix predated #103's merge) — worth another quick refresh pass, same discipline as before.

## Open decisions — NOT to be reconstructed from memory

**New, highest priority:** the §14 adversarial audit on `feat/attack-pending-review` has NOT been run. D-054 records that the last agent to hit the conflict between "do not invoke subagents unprompted" and §14 resolved it silently in favour of skipping; this round it is being raised instead of resolved. The branch cannot open a PR without it (the audit gate is a required check). Then: item 7 — rebase #29's branch (fixing #33's findings) or rewrite fresh. Not yet decided either way; the comment on #29 states the case for not defaulting to fresh-rewrite reflexively. DELIVERY_PLAN.md status-table refresh — DONE this round: item 5 → DONE (PR #103), new item 5a for #101/#102 in progress, 3b and 7 re-pointed at it, and item 7's rebase-vs-rewrite decision written into its row. Whether to write "missing data defaults to unconfirmed, not confirmed" into CLAUDE.md as a standing rule — DONE this round, along with the denominator lesson it turned out to need. What "addressable" coverage means for #102 — now stated, in `app/attack/pending.py` and D-055: it excludes N/A and pending-review rows, and `gap` is never pending. `Require a pull request before merging` still off on branch protection. Local-device mirror of this file — still unconfirmed. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — unchanged. Whether to parallelize item 6 — still undecided.

## Resolved as of this round

PR #29 closed under D-054, with an explicit split between what's genuinely superseded (the resolver) and what's still live, unblocked work (the panel/enrichment half, item 7). Caught and prevented before closing: closing #29 wholesale would have silently dropped real functionality nothing else on main provides. The reuse-vs-rewrite question for item 7 is now an explicit, tracked open decision rather than something that would have defaulted silently.

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Item 7's size is now uncertain in a new way — DELIVERY_PLAN's original 1-session estimate assumed building on #29; whether that still holds depends on the rebase-vs-rewrite decision above.

## Environment notes (standing)

Unchanged from prior entries: Postgres migrations clean through 0043, applied to dev Postgres and verified via alembic current. Provider live key: RESOLVED, reverted to fixture-by-default on purpose. Zero RELEASED ATT&CK assessments exist and there is no production deployment yet — standing context for how "client-facing" language elsewhere in this file should be read.

## Do not merge

None currently open. PR #29, previously listed here under D-054, is now closed (see above) rather than merely never-merged.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. Missing/absent data silently defaulting to the confirmed or safe-looking state instead of the unconfirmed one — two instances (D-054's nullable-vendor default, this round's NULL-citation migration text), still worth a standing CLAUDE.md line. A rule rewritten three times without its input space ever being enumerated is a design problem — stated as a general principle this round. NEW this round: closing a container (a PR, an issue, a ticket) that bundles genuinely-done work with still-needed work can silently drop the still-needed part if the close doesn't explicitly separate them — the same "status line wrong" shape, but at the level of a close/merge decision rather than a written status line; caught here by reading the actual diff and the plan's own dependency table rather than trusting a decision's original framing at face value. A mechanism built to enforce a format only proves it handles the formats it was tested against — two instances (#98, #103). Code can assert the opposite of what actually happens and nothing catches it until an adversarial pass reads the code path directly — #103's panel-copy inversion; #102's planned flip is the same shape caught proactively. An issue tracker's own auto-close mechanism can produce a wrong status line without any code being wrong — #101, documented via #104. A migration's effect on existing rows is not uniform by default — resolved this round for #101/#102. A mechanism that reports on a violation is not the same as a mechanism that blocks it. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself. A rule whose measured signal is a small fraction of its raw output should be narrowed. A mutation-testing survivor is only meaningful relative to which tests were actually run against it.
