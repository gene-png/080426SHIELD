# Gene's Context — 080426SHIELD

## Pick up here

Nothing blocking. Three things worth your attention, in priority order:

1. **PR #112 is open, green, and ready to merge.** All 6 checks passed, no conflicts. It adds a gated (`E2E_PERF=1`) measurement spec for #111 and flips DELIVERY_PLAN.md's item 5a to DONE, correctly scoped — #101/#102 are complete and merged (PR #110), #111 stays open on its own merits. Low risk: one new opt-in test file plus one doc line.
2. **#111 is a real, quantified, product-facing scalability finding, not a flaky test.** `/admin/management` costs roughly 2s + 1.1s per client card, measured and confirmed linear within 5% across a 29× range in N. At 88 clients that's 95 seconds to settle. CI can never see this — its runners start with empty volumes. This needs a business-timeline judgment call from you: does it ride the general backlog, or get pulled forward ahead of item 7, based on how fast your real client count is heading toward the range where this actually hurts. Not decided.
3. **`context/gene.md` commits now require an admin "bypass rules" click**, not a plain direct commit — branch protection has tightened enough that even this file's standing direct-commit exception now shows GitHub's bypass-path UI. Recommended fix, not yet requested from the dev team: a path-scoped branch-protection exemption for `context/gene.md` specifically, so it skips the PR requirement without relying on an admin bypassing a rule every time, and without dragging a docs-only log update through a full CI cycle the way a PR under `context/` (not covered by the existing `docs/` exemption) might.

**Last updated:** 2026-08-21 (PR #110 merged — #101/#102 genuinely done; §14 audit against the branch found 6 real defects, 5 fixed + 1 filed as #109, all independently verified against the diff; #111 investigated, measured, and root-caused as a real N+1 in the admin console; PR #112 open and green, flips item 5a to DONE with #111 correctly carved out)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## This round — verified, not relayed

Everything below was checked directly on GitHub: diffs, commit history, Actions runs, issue and PR bodies. Bottom line: this was the most accurate relay round of the engagement so far, including one self-caught overclaim that was corrected before it reached me as a wrong "done."

**PR #110 merged 2026-08-21.** #101 and #102 are genuinely closed out — the flags are persisted (migration 0044), the withholding rule is wired everywhere the percentage appears (rollup card, matrix badge, technique panel, client dashboard, all 3 exporters), and locked assessments are grandfathered (migration 0045, D-056). This is the real landing of the work D-055/D-056 described two rounds ago.

**§14 adversarial audit, run against the branch (96fdf8d's parent) — 6 confirmed, 1 filed, 5 survived.** Verified every finding against the actual diff, not just the summary:
1. **HIGH — client dashboard didn't withhold.** `routes/clients.py`'s `attack_dashboard` called `attack_compute(coverage_map)` with no pending codes, while `finalize_attack_deliverable` and `heatmap` did — meaning a released PDF could say 0% while the in-app dashboard the same client can log into said 100%. Fixed, and the fix ships with a regression test that would have failed on the old code.
2. `seed_demo`'s guard could never fire — it called `is_pending_review()` over rows written with `unconfirmed_citations=[]`, which is case 3 (never pending) by construction. The guard supplied its own precondition. Fixed by asserting the underlying property directly.
3. DOCX and PDF per-tactic tables lacked the "Pending review" column that XLSX had — an unstated exemption between twin renderers, the same shape as #75/#79. Fixed, and the new test covers the *upward*-drift direction the old fixture never touched.
4. Citation order decided whether a technique scored — `["CrowdStrike", "CrowdStrike Falcon"]` withheld the row, reversed order scored it, identical evidence. A confirmed citation now retracts an earlier inference of the same capability. Fixed.
5. A row with `unconfirmed_citations = null` (pre-resolver state) rendered a "Pending review" badge over an empty panel with no route out for the consultant. Fixed, with an explicit message and a real escape hatch (set the status or tools directly).
6. **Filed, not fixed:** an `unusable` citation (bare string, null, empty name) leaves no per-row disclosure record — scoring is unaffected, but the audit trail is lost when another field on the same row supplies a usable tool. Correctly scoped as a disclosure gap, not a scoring error. Filed as **#109**, confirmed open and accurately described.
Also fixed along the way: a frontend `cleared_at === null` check that would have read a missing key as "cleared" in the browser while every backend reader treats a missing key as uncleared — latent behind pydantic always emitting the key, normalized anyway.

**A gap I found that the relay hadn't mentioned, since resolved:** PR #110 was opened as draft specifically to "start required-check coverage," but I confirmed via the Checks tab and the Actions history that zero workflow runs existed for it — draft PRs appear to be skipped by this repo's CI/audit-gate triggers, so the stated intent wasn't actually happening. Flagged it; the PR was marked ready for review shortly after, which triggered a real run: CI #207, 17m31s, marked success, plus three green Audit gate runs. Confirmed the fix worked, not just the intent.

**#111 — the local e2e failures, root-caused and quantified.** The first pass at this overclaimed: "s33-admin-remove passes on clean containers" turned out to be a misread of a mid-run progress line with no failure marker yet, not an actual result — caught and corrected in the same round, in a commit literally titled "correct 5a — s33-admin-remove:84 does NOT pass on clean containers." The actual measurement (drifted DB, 88 clients vs. a fresh 3-client seed): navigation time is flat (2.0s) across a 29× change in N, ruling out cold compile. Subtracting that fixed cost, both measurements agree within 5% on ~1.1 seconds per rendered client card — confirmed linear, not noise. Root cause: `ManagementView.tsx` fires an unconditional `listClientUsers()` + `listDomains()` per card on mount, so page cost is `1 + 2N` requests. At 88 clients that's 95.6 seconds to `networkidle`, against 5.4s at 3 — which lands the timeout failures exactly where they were observed (`s2`: 90s budget, fails ~N=80; `s33:84`: 240s budget, two page loads, fails ~N=94). Deliberately not fixed — a real fix (server-side aggregation or lazy per-card loading) is scoped for its own PR and audit. Filed and confirmed accurate as **#111**.

**PR #112 — open, green, correctly scoped.** Adds the measurement as an opt-in Playwright spec (`E2E_PERF=1`, same pattern as `s26-oidc-login`'s `E2E_OIDC`), creates no data itself (so it can't pollute the drift it measures), and flips DELIVERY_PLAN.md's item 5a to DONE — explicitly scoped to mean #101/#102 are complete and verified, not that #111 is resolved. Self-audit on this diff found 3 issues, all fixed before push, the sharpest being that `playwright.config.ts`'s `testDir: "."` would have let CI's bare test collection silently pick up the new spec without the `E2E_PERF` gate — caught and fixed, verified via `--list` showing the file present-but-skipped without the flag.

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103, #104, #105, and now **#110** merged, all verified directly on GitHub. Open: **#112** (measurement spec + item 5a → DONE, green, ready to merge). Closed: #29, #99, and all older. #84, #85, #87, #89, #90, #92, #33, #106, #107, #108, **#109**, **#111** filed and open — #109 and #111 both newly filed this round, both independently verified accurate. Branch `feat/attack-pending-review` is now fully merged into `main` via #110; no further work continues on it.

## #101 / #102 — closed for real, via #110

The persistence and scoring work described across D-055/D-056 is merged and live on `main`. See "This round" above for the audit disposition. The placeholder-number CLAUDE.md convention held again this round — no accidental closes.

## Item 7 — now genuinely unblocked

Per DELIVERY_PLAN.md's own dependency table (as updated in #112's diff, not yet on `main` until #112 merges), item 7 was waiting on item 5a. 5a is done. Decision from prior rounds stands: hybrid approach — port the `/ai-inputs` panel from #29's branch (6 new files, zero drift), rewrite the enrichment fresh against the new resolver, re-derive #33's finding 5 rather than porting it. This is the next real MVP-path item, pending your call on whether #111 takes priority first.

## MVP tracking — DELIVERY_PLAN.md

Item 5: DONE (PR #103). Item 5a: **DONE** as of #112's diff (PR #110 merged 2026-08-21) — #101+#102 complete and verified, local e2e finding tracked separately as #111. Item 7: unblocked, not started. Items 6 and 8: not started, unchanged.

## D-054, D-055, D-056 — decisions log

Unchanged from prior entries — D-054 (branch protection/audit gate), D-055 (scoring/persistence rule, 3 sub-decisions), D-056 (APPROVED-lockout grandfather) are all now shipped in merged code via PR #110, not just decided on paper.

Branch protection: now visibly stricter than last round — direct commits to `main` surface a "Bypass rules and commit changes" control rather than a plain commit button, confirmed by hitting it directly on this file. `Require a pull request before merging` — status not reconfirmed this round, but behavior observed is consistent with it now being on or close to it.

## Open decisions — NOT to be reconstructed from memory

**New this round:** whether #111 (the admin-console N+1) gets pulled ahead of item 7 — a business-timeline call, not a technical one, genuinely undecided. Whether to set up a path-scoped branch-protection exemption for `context/gene.md` so it stops needing an admin bypass — recommended, not yet requested of the dev team.

**Still open, unchanged:** whether the placeholder-number CLAUDE.md fix needs a CI-level guard on top. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape — unchanged. Whether to parallelize item 6. Whether "does assessment approval imply citation confirmation" (D-056's deliberately-deferred question) should ever be picked up — still genuinely open.

## Resolved as of this round

#101/#102 shipped and merged (PR #110). §14 audit against the real feature branch run and disposed: 5 fixed, 1 filed (#109), both confirmed accurate against the diff. The CI-not-running gap on draft PR #110 found and fixed (marked ready for review). #111 root-caused, measured, and correctly not fixed inline. PR #112 opened, green, correctly scoped, not yet merged.

## Adversarial-reviewer and Playwright

`adversarial-reviewer` has now been run against the real #101/#102 feature branch (not just PR #105's docs diff) and found 6 real, verifiable defects — this was the larger, more consequential audit flagged as outstanding for two rounds running, and it delivered. Playwright/e2e: the local-failure investigation this round (#111) is itself a demonstration of the suite doing its job — it caught a real product bug local dev containers can reproduce and CI structurally cannot.

## Session length — unchanged, see prior entries

## Environment notes (standing)

New this round: local dev DB measured at 88 clients / 113 users while investigating #111 — consistent with the "measure, don't assume" pattern this project keeps proving out. Zero RELEASED ATT&CK assessments, no production deployment — still the standing context for why #109/#111 are dev-discoverable problems rather than confirmed client-facing incidents, though #111 in particular is a real risk once client count grows.

## Do not merge

None currently blocking. #112 is open, green, and recommended to merge.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged core list (12+ instances of the self-fulfilling-test pattern; the SAEnum casing trap from last round). **New this round:** a workflow trigger silently skipping draft PRs can defeat the stated purpose of opening one early — the fix worked once actually checked, but the "opened as draft to get coverage" intent was not itself proof coverage was happening. And: **reading a mid-run progress line with no failure marker yet as a final result is the same class of mistake as trusting a green suite without checking what it actually covered** — self-caught this round, corrected within the same relay round rather than shipped as a wrong "done."

**An issue tracker's own auto-close mechanism can produce a wrong status line without any code being wrong** — unchanged from last round; not retriggered this round, placeholder-number convention held.
