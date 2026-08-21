# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (PR #29 closed under D-054, with a comment splitting its two halves — the resolver logic is genuinely superseded by #103 and should not be ported; the /ai-inputs visibility panel + enriched-model-payload half is NOT superseded, is still live work, maps to DELIVERY_PLAN item 7 (W1 ATT&CK step, blocked only by W2, now unblocked) and issue #33's open findings, and its reuse-vs-rewrite question is left as an explicit open decision rather than defaulted; caught before closing, not after — closing #29 wholesale would have silently dropped real, wanted functionality the same way a status line goes stale, just via a PR close instead of a doc)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103 merged, all verified directly on GitHub. Open: #104 (docs-only closing-keyword rule, checks green except the audit-gate's own pending re-check as of last look). Closed: #29 (superseded-in-part, see below), #99, and all older. #84, #85, #87, #89, #90, #92, #102, #33 filed and open. #101 reopened, correctly still open (no PR yet for the persistence work).

## PR #29 — closed, but only half genuinely superseded

Before closing, checked #29's actual diff and issue #33 rather than assume D-054's "close once W2 lands" meant "everything in #29 is now dead." It doesn't. #29 had two halves: (A) an `/ai-inputs` panel showing what the ATT&CK mapping will run against before a consultant clicks start, and (B) sending the model the extractor's real structured fields (vendor, category, security_functions) instead of bare names, with a deliberate privacy boundary excluding notes/cost/workflow-state fields, pinned by its own test. W2 (#103) only ever replaced the citation-resolver logic — the actually-defective part (13 findings, 2 blockers in #30's audit). It explicitly did not touch the panel or the enrichment payload.

DELIVERY_PLAN.md independently confirms this: item 7 ("W1 ATT&CK step") is listed as not started, blocked only by W2 — which just landed — and issue #33 (still open) tracks exactly the panel/enrichment code's known bugs (panel not rendering pre-assessment, org-named tools permanently uncitable, draft-count over-count, plus lower-severity findings 7/8/10/12/13). None of those read as structural the way the resolver's defects were; #29's panel/enrichment code passed 838 backend + 147 vitest tests.

Closed #29 with a comment on the issue itself (not just here) stating explicitly: the resolver half should not be ported from this branch; the panel/enrichment half is live work now tracked as item 7 and #33, not dead; and whoever scopes item 7 needs to deliberately decide rebase-this-branch vs. rewrite-fresh, since D-054's rationale for a fresh rewrite was specific to the resolver's defect density and doesn't automatically transfer to code with a much lower defect rate. Not yet decided which way — flagged as an open decision below.

## #101/#102 persistence work — in progress, no PR yet

Recap, see prior entry for full detail: the migration docstring's own NULL-means-"leave scoring as today" language was caught as the same fail-open shape D-054 already rejected once, fixed to three-value semantics (NULL and uncleared-inferred both score pending, `[]` scores normally). Blast radius checked: zero RELEASED assessments, no production deployment yet, all 30,384 rows dev/demo. Sizing corrected to 2-3 sessions / 4-5 rounds, with the state-space-first principle stated for future scoring changes. Analytics half done (10 tests green); persistence wiring, seed, and panel-copy flip still ahead.

## D-054, PR #96, PR #97, PR #98 — recap, see prior entries for full detail

D-054: W2 cut fresh off main; #29 closed as superseded now that W2 landed — done this round, but with the resolver-only scope made explicit rather than assumed total. Nullable-vendor default set to refuse-and-flag — the same principle reapplied twice more since (the #101/#102 NULL-citation case, and implicitly the reasoning behind why #29's still-live half shouldn't be silently discarded). PR #96/#97/#98 recap unchanged; branch protection enforces the audit gate for real.

## MVP tracking — status this round

Item 5 (W2) DONE. Items 3a and 4 DONE. Item 7 (W1 ATT&CK step) is now unblocked and has a real starting point — #29's diff, plus #33's cataloged bugs — but is NOT started, and the rebase-vs-rewrite decision needs making before it is. Item 3b in progress via #101/#102 (2-3 sessions, correctly re-sized). Items 6, 8 not started. DELIVERY_PLAN.md itself is stale again on item 5 specifically (still shows "IN PROGRESS" as of the version checked this round, since #100's fix predated #103's merge) — worth another quick refresh pass, same discipline as before.

## Open decisions — NOT to be reconstructed from memory

**New, highest priority:** item 7 — rebase #29's branch (fixing #33's findings) or rewrite fresh. Not yet decided either way; the comment on #29 states the case for not defaulting to fresh-rewrite reflexively. DELIVERY_PLAN.md needs another status-table refresh (item 5 → DONE, plus #29's closure, #101/#102/#104 status) — same pattern as before, not yet done. Whether to write "missing data defaults to unconfirmed, not confirmed" into CLAUDE.md as a standing rule — not yet done, recurred twice now. What "addressable" coverage means for #102 — not yet stated anywhere. `Require a pull request before merging` still off on branch protection. Local-device mirror of this file — still unconfirmed. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — unchanged. Whether to parallelize item 6 — still undecided.

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
