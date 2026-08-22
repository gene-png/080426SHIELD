# Gene's Context — 080426SHIELD

## Pick up here

Nothing blocking, but one scope decision now standing: Gene has set a policy that anything only a detailed, code-level audit would catch, not something visible from using the product, must be fixed as part of MVP completion, not filed and left in backlog. That reclassifies **#114**, **#115**, and **#109** from "filed for later" to MVP-blocking, and reopens the question of whether **#46** (still Open) is actually fixed or just newly caught by a test. Relayed to the dev; awaiting confirmation and a scope decision on #114's suspected CSF/ZT twins.

Otherwise: PR #116 (item 3b) is open, 5 of 7 checks green, E2E and Python still running. Merge once green — MVP goes to 9 of 12 the moment it lands, not before. #113 is merged and the closing-keyword guard is now a real required check, confirmed directly in branch protection settings, not just claimed.

**Last updated:** 2026-08-21 (#113 merged and verified as a required check with exact settings confirmed; #73/#79 closed with real evidence after being found done-but-never-closed; PR #116 covers item 3b, fixing 3 defects and filing #114/#115, plus re-surfacing long-open #46; Gene has set an explicit MVP-scope policy for code-level-only-catchable defects)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## This round — verified, not relayed

**#113 merged, and the closing-keyword guard is a real, confirmed required check.** Not just claimed: I opened the branch protection rule directly and read the toggle states myself. Seven required status checks including "No accidental issue closes," `has_required_reviews` true (PRs still required), `allows_force_pushes` false (force-push blocked), `enforce_all_for_admins` false (admin bypass still available). Every specific claim about this matched exactly.

**The guard's design holds up on inspection.** It checks title, description, and every commit message (the third accidental close came from the PR description, which every prior rule had missed by targeting only commit bodies). It doesn't validate that a referenced issue number exists, deliberately: issue numbers only increase, so a keyword next to a currently-unused number is inert today and a live closing reference the day the repo reaches it. The placeholder that can never go live is `#NNN`, no digits. An intended close still requires an explicit `Auto-close-approved: 123, 456` declaration (bare numbers, no `#`, so the marker itself can't trip the bug it's declaring). Found while writing it: CLAUDE.md's own rule illustrated the trap with a live number right after `fixed:`, CLAUDE.md line 287 had the same shape in a sentence meaning the opposite, and the rewritten rule illustrated "don't use a made-up number" with a made-up number, caught by the script's own self-test before it could ship.

**Correction to my own prior read:** I'd characterized the guard's fail-closed-on-bad-input behavior as something the dev self-caught in a first draft. That's not right, they corrected me. The `return 2` path was designed in from the start, deliberately, because the earlier audit-gate lesson (fail-open on unreadable input) was already written down. Recorded properly this time: this is CLAUDE.md's one entry marked as a case where writing a lesson down demonstrably worked, set against the closing-keyword rule that was rewritten three times and violated a fourth. The real generalization: a rule about code you're writing on purpose responds to diligence; a rule about prose you're not thinking about needs a machine.

**#73 and #79 were done, just never closed — confirmed by reading the code, not the plan.** Both closed by hand this round (per the new guard's own discipline) with real evidence: `routes/zt.py:1595` carries the comment "The CLIENT'S CONTRACTED target, not the engine default (#73)," and the two symptom greps CLAUDE.md records for this defect family now return nothing in the ZT or CSF paths (both remaining hits are `risk.py`, tracked separately as #84, scheduled with item 6). This is the inverse of the #101 problem: accidental closes on one side, a status line correctly marked DONE while its own tracking issues sat open on the other. DELIVERY_PLAN.md's item 1 was right all along; the bookkeeping was the only thing wrong.

**PR #116 (item 3b) — verified in full, all specific claims checked out.**
- D-052's shape-guard invariant (every registered job has a top-level shape guard) survived three attempts to break it, and is now genuinely parametrized over `registered_jobs()` instead of a hardcoded list of five job names — confirmed by reading the diff, not the summary.
- Writing that test surfaced **#46**, a real, pre-existing, still-Open issue ("Silent: a response with the WRONG TOP-LEVEL KEY is still discarded"), confirmed directly. The PR body says the new test now *catches* this failure mode; it does not claim the underlying silent-discard behavior in `require_list_at` is fixed. That distinction matters and needs confirming, see "Pick up here."
- Three real defects fixed: (1) a released workbook where the summary tab said "Pending review 5" while the detail tab beside it, and the client dashboard's matrix, both showed those same five rows as Covered, fixed by deriving the pending set once in `build_context` rather than per-renderer, a structural fix, not a third patch on the same recurring hole. (2) D/P/R posture counted unconfirmed tools as coverage, so an all-inferred run could read "Detect 100%" on the same page whose rollup said zero covered, fixed. (3) The top-50 gap truncation disclosure had no test pinning it, deleting the "(N of M shown)" text left the suite green, this is #75's exact defect shape recurring, unpinned, inside the service D-049 named as the good example. Fixed.
- Two filed rather than fixed, both pre-existing and larger than 3b's scope: **#114** (client dashboard recomputes from the latest APPROVED assessment but labels it with the released deliverable's version, so approving v2 can show v2's numbers under a "Report v1" header, confirmed real and Open, with `Deliverable.parent_version`'s own docstring already describing this exact bug) and **#115** (a partially-failed `mitre_map` run is indistinguishable from a complete one on every screen, `batches_failed` is returned and typed but rendered nowhere, confirmed real and Open).

**Gene's new standing policy, set this round:** anything discoverable only through detailed, code-level audit, not through using the product, must be fixed as part of MVP completion, not filed and left in the general backlog. This reclassifies #114, #115, and #109 from "filed for later" to MVP-blocking, and reopens whether #46 is genuinely fixed. Relayed; the dev has not yet confirmed scope or the CSF/ZT twin question for #114.

## Branch / in flight

`main` has everything through **#110, #113** merged, verified directly on GitHub, plus everything from prior rounds. Open: **#116** (item 3b, 5/7 checks green, E2E + Python running, merge once green). Closed this round: **#73, #79** (by hand, with evidence, per the new guard's own discipline). Newly filed and confirmed real: **#114, #115** (both now MVP-blocking per Gene's policy above). Re-surfaced and confirmed still Open: **#46** (status of the underlying fix unconfirmed, see "Pick up here").

## MVP tracking — DELIVERY_PLAN.md

8 of 12 done on `main` right now. Item 3b will make it 9 of 12 once #116 merges (not yet, `main` still shows 3b as "Not started" as of this check). Remaining after that: item 6 (W1 Risk + #84), item 7 (W1 ATT&CK, unblocked, hybrid approach already decided), item 8 (W6 Risk export/publish). Roughly 3–4 sessions per the dev's estimate, nothing blocked. **Not counted in that remaining-items number, but now MVP-blocking per Gene's policy:** #114, #115, #109, and confirming #46.

## D-054, D-055, D-056, D-052 — decisions log

Unchanged from prior entries for D-054/055/056. D-052 (item 3a's export/persistence audit invariant, Tech Debt) is now confirmed to also hold for ATT&CK via item 3b, and is mechanically pinned rather than just asserted, per this round's verification.

Branch protection on `main`, confirmed directly this round: 7 required checks (Adversarial audit recorded, Demo, E2E, Python, Secret scan, Web, No accidental issue closes), PRs required, force-push blocked, admin bypass still available. This is the actual current state, not inferred from behavior.

## Open decisions — NOT to be reconstructed from memory

**New this round:** whether #114's suspected CSF/ZT twins are real, unconfirmed by the dev as of this log. Whether #46's underlying silent-discard behavior is actually fixed or just newly caught by a test, unconfirmed. Whether #111 (the admin-console N+1) gets pulled ahead of item 7, still genuinely undecided, and now sits alongside a broader question: Gene has said his own pre-launch testing pass will focus on UI and AI-output consistency, not code-level review, so any future finding in that same "only a code audit would catch this" category should probably default to MVP-blocking under the same policy rather than being separately re-litigated each time. Worth confirming that reading with Gene rather than assuming it.

**Still open, unchanged:** path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. Whether "does assessment approval imply citation confirmation" should ever be picked up.

## Resolved as of this round

#113 merged and confirmed as a real required check with exact settings verified. #73/#79 closed with real evidence, correcting a bookkeeping error rather than a code error. PR #116 (item 3b) fixes 3 real defects and files 2 more, all independently verified; not yet merged.

## MVP-complete vs. client-ready — standing distinction, set this round

Gene has explicitly agreed these are two different milestones, not one. Finishing items 6–8 clears the MVP checklist. It does not by itself mean ready for a real client: #111 (real, quantified N+1) is unaddressed and undecided on timing; 34 open issues as of this round include correctness bugs the dev's own words called "embarrassing in front of a client"; zero production deployment or RELEASED assessments exist yet per the project's own docs. Gene's plan: finish MVP, then a dedicated testing and processing pass before going live, focused on UI and on the AI producing consistent, accurate outcomes. Code-level-only-catchable defects are explicitly carved out of that pass and pushed into MVP-blocking scope instead, per the policy above, precisely because Gene's own review won't be positioned to catch them.

## Adversarial-reviewer and Playwright

Confirmed run again this round, on PR #116 (item 3b, ATT&CK export/persistence). 4 confirmed findings, 1 absence-of-coverage finding, 4 minor, 3 fixed, 2 filed. Consistent pattern: this tool keeps finding real things when pointed at real branches, not just docs diffs.

## Environment notes (standing)

Unchanged from prior entries. Open issue count is now 34 (was ~30 a couple rounds ago) despite #73/#79 closing this round — net growth from active discovery (#106–109, #111, #114, #115), not scope creep. Worth knowing the number trends up for a good reason right now, but also worth periodic triage so it doesn't quietly become a real backlog problem.

## Do not merge

None currently blocking on `main`. #116 is open and not yet fully green (E2E + Python still running as of this check) — verify green before merging, don't assume from a partial check list.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list. **New this round:** the rollup-vs-detail-rows contradiction (item 3b's fix #1) is the same defect family as the earlier HIGH-severity dashboard/PDF mismatch, just at per-technique granularity instead of aggregate — watch for a third instance anywhere else that reads coverage status directly instead of through the now-shared `build_context` derivation. And: **a status line that is technically correct (item 1's DONE) can still be wrong in a way that matters if its own tracking issues were never closed** — the inverse of the #101 problem, both are the same underlying lesson that bookkeeping needs to be verified against code, not assumed from either direction.
