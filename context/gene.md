# Gene's Context — 080426SHIELD

## Pick up here

Three things outstanding, in priority order:

1. **Send this to the other Claude Code session** (drafted, not yet sent):

> Good catch on #101 — the quote-doesn't-exempt-it finding and the placeholder-number fix are the right call, nothing more needed there.
>
> One thing: DELIVERY_PLAN.md is stale in three places, not just item 5. The "Live risk: main has NO branch protection" section and D-054's "not enforcing until branch protection is configured" line are both flatly false now — protection's been live for a while. I'd rather this refresh land on its own, now, instead of folding into item 7's PR. It's a five-minute, zero-risk edit; bundling it with a multi-session feature branch is the same pattern that let item 5 go stale twice already. Your call, but that's my ask.
>
> Also: **push whatever's local.** I went to verify the "committed as 2f8bc34" report on GitHub and it isn't there — no such commit (404 on direct lookup), the branch tip is still `2f97ca7`, and DELIVERY_PLAN.md on the branch still shows the old item-5/no-item-5a text, not the edit you described. Most likely explanation is it's a real local commit that hasn't been pushed yet, not a fabricated report — the garbled-relay problem on my end is well established by now. But I can't verify or log anything past `2f97ca7` until it's on GitHub, and the §14 audit can't run against code that isn't pushed either. Push the branch (and open the PR if it's ready) before the next round.

2. **APPROVED-assessment fail-closed lockout — needs your decision, not the other session's.** New finding this round, described in full below. Short version: the fail-closed default for missing `unconfirmed_citations` data drops 29 of 48 dev assessments to 0%, including ones already APPROVED, and there's no code path back — `run_ai`, `patch_coverage`, and `confirm-citations` all 409 on an APPROVED assessment. Three options were offered; my read and recommendation are below. Nothing is blocked on this tonight, but it should get an explicit answer (and probably a new D-number) before the §14 audit or e2e tests get written against whichever shape you pick.

3. **DELIVERY_PLAN.md refresh** — same ask as #1, not yet sent, not yet landed.

**Last updated:** 2026-08-21 (2f8bc34 confirmed NOT on GitHub — three independent checks, not one; new APPROVED-lockout finding surfaced by the other session's own dev-DB spot-check, with three options on the table and a recommendation below; adversarial-reviewer subagent and Playwright both confirmed set up but neither has been run yet)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## 2f8bc34 — does not exist on GitHub, confirmed three ways

A relayed report claimed commit `2f8bc34` landed the #101/#102 persistence wiring with all gates green, tree clean, both issues still correctly Open. I did not log this as fact before checking, per standing practice. Three independent checks, all consistent with "not pushed":

1. Direct lookup — `github.com/gene-png/080426SHIELD/commit/2f8bc34` returns **"Page not found · GitHub" (404)**.
2. Full commit history of `feat/attack-pending-review` — current tip is `2f97ca7` (the already-known CLAUDE.md placeholder-number fix). No commit matching the claimed feature appears anywhere in the visible history. Zero Actions runs on the branch either, consistent with local-only gate execution.
3. `DELIVERY_PLAN.md` fetched directly from the branch (not cached) — still reads item 5 as "IN PROGRESS ... ~0.5 session left," still has the false "no branch protection" section, still has D-054's false "not enforcing" line. No item 5a. If `2f8bc34` had actually landed the plan edit described in the relay, this file would show it. It doesn't.

The two things that ARE independently confirmed and consistent with the relay: issues #101 and #102 are both still correctly Open (checked directly on each issue's timeline). So the claim isn't fabricated wholesale — most likely a real local commit not yet pushed, or a genuinely garbled SHA on relay (the same message had other clear corruption in it). Either way: nothing past `2f97ca7` is currently verifiable, and won't be until it's pushed. Asked for in the message above.

## New finding — APPROVED assessments can be driven to a permanent, unrecoverable 0%

Surfaced by the other session itself, while checking that adversarial-reviewer and Playwright were both set up (they are — see below) — not something I found independently, but worth recording carefully since it's a real design gap, not a relay artifact.

**The mechanism:** the new fail-closed rule (missing `unconfirmed_citations` data defaults to withheld, not confirmed) was run against the actual dev DB rather than assumed safe. Of 48 dev assessments, 29 have their score change under the new rule — some dropping from ~62-64% to 0%, because all 30,384 dev `attack_coverage` rows have `unconfirmed_citations = NULL`. That part is intended and already documented as the migration's known cost.

**What isn't covered by the existing reasoning:** several of the 29 are already **APPROVED**, and an approved assessment has no route back to a state where it could pick up citation data. `run_ai`, `patch_coverage`, and the new `confirm-citations` endpoint all 409 on an APPROVED assessment by design (approval is supposed to freeze the assessment). So those rows are stuck at 0% permanently — not "until someone re-runs AI," genuinely permanently, short of un-approving them through some path that doesn't currently exist. The affordability check behind the original migration decision verified zero RELEASED assessments; it never checked APPROVED ones, and APPROVED is a real, populated state in the dev data.

In dev, this is recoverable by wiping and reseeding (`docker compose down -v`; note `seed_demo.py` isn't idempotent, #65 — same recurring gap). No production exists yet, so nothing client-facing is harmed today. But the underlying design question doesn't go away just because dev can be wiped: the same trap is waiting for the first real APPROVED assessment in production, where there is no reseed.

**Three options offered, as relayed:**

1. **Accept and document.** No production yet, dev recovers by reseed. Cheapest. Leaves 29 dev assessments reading 0% until someone wipes, and — this part matters more than the framing suggests — leaves the actual design question unanswered for when it stops being a dev-only problem.
2. **Treat assessment approval as the human confirmation.** A consultant approving an assessment counts as 5.1's "a human cleared it," at assessment scope rather than row scope. `approve_assessment` would stamp the rows' citations as confirmed; already-approved rows get backfilled the same way. Principled in one sense, but it's a real semantic expansion of 5.1 — 5.1 was decided around explicit, row-level citation confirmation, not an assessment-level sign-off standing in for it.
3. **Backfill already-APPROVED rows to `[]` at migration time.** Explicit grandfathering: rows approved before this rule existed don't retroactively eat the fail-closed penalty. Narrower than option 2 — it doesn't change what approval means going forward, only protects rows approved under the old rules.

**My read, offered as analysis, not a decision for anyone else to treat as made:** option 1 isn't really a fourth path — it's deferring the decision, and the design question survives the reseed. Between 2 and 3, option 2 is doing more than it says: backfilling already-approved rows on the theory that "the consultant's approval implied citation confirmation" isn't quite honest, since those consultants approved under the old scoring, before this rule existed — they weren't confirming citations, they were approving whatever the dashboard showed them at the time. Retroactively re-reading their past approval as citation confirmation assumes something about their intent that isn't actually known. Option 3 doesn't make that assumption; it just says rows approved under the old regime don't get penalized by a rule that didn't exist yet, full stop, and it explicitly does not decide whether approval means citation-confirmation going forward.

That said, option 2's underlying question — should assessment-level approval ever count as citation-level confirmation? — is real and worth answering on its own terms, just not as a rider on a migration backfill. If the answer turns out to be yes, that's a new decision (new D-number, own invariant tests), separable from what to do with the 29 existing dev rows.

**On sequencing** (this is what the other session actually asked): settle this before running the §14 audit or writing the e2e coverage, not after. Auditing or testing against a migration shape that's still an open question means doing it twice if the shape changes. The suggestion that the audit itself might have an opinion on the APPROVED question is worth being skeptical of — the audit's job is to review code against a decided design, not to make the design decision. Recommend: pick a migration answer (my lean is option 3, decided narrowly, with the option-2 question logged separately and *not* answered by default), record it, then audit and test against the final shape.

Recreating the web container and confirming Playwright/fixture mode is a separate, lower-stakes task and can happen anytime in parallel — it doesn't block or get blocked by the APPROVED question.

## Adversarial-reviewer and Playwright — both set up, neither run yet

Checked directly rather than assumed, per the same standing practice. `adversarial-reviewer` — subagent definition committed at `.claude/agents/adversarial-reviewer.md` (6.7KB), registered as a subagent type, available but **not launched** — that's the §14 audit decision still sitting with you. Playwright — installed and functional, v1.61.1, chromium + headless shell present, web and api both respond, `SHIELD_LLM_MODE=fixture` confirmed correct for e2e. One real blocker before an e2e run means anything: `apps/web` has been edited heavily since the container was last built, and hot-reload doesn't fire through the Windows bind mount, so a run right now would test stale JS. Needs `docker compose up -d --force-recreate api web` (both together — recreating web alone can silently recreate api off whatever `.env` currently says), then re-confirm the mode stayed `fixture` after the recreate.

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103, #104 merged, all verified directly on GitHub. Open PRs: **zero** — confirmed on the Pull requests list. Closed: #29 (superseded-in-part), #99, and all older. #84, #85, #87, #89, #90, #92, #33, #102 filed and open. #101 open — reopened twice now, correctly still open (real work in flight, not yet landed — and not yet pushed past `2f97ca7`, see above). Active branch `feat/attack-pending-review`: 1 behind main, 2 ahead, no PR opened yet. Latest commit visible on GitHub is still `2f97ca7` ("docs(claude): quoting the closing-keyword phrase trips it too").

## #101 — closed twice by GitHub's parser, neither time by anything code-related

**First close:** #103's commit body contained "Filed, not fixed: #101 (flags are not persisted ...)". GitHub's closing-keyword parser matches `fixed: #101` inside that phrase and ignores the "not". The sentence written specifically to say the issue was NOT fixed is the sentence that closed it. Reopened, root-caused, and the lesson landed in CLAUDE.md via #104: never write "does not fix #N" / "partially fixes #N" / "not resolved: #N" — use "filed as #N" / "see #N".

**Second close:** #104 — the PR whose entire purpose was documenting the first close — re-triggered it. Its own body had to quote "Filed, not fixed: #101" to explain what happened, and the parser does not care that the text is inside quotation marks or a code fence; it matched the pattern in the quotation and closed the issue again on merge. Confirmed directly: #101 shows closed-by `2f997b0`, which is #104's own merge commit.

Reopened a second time, and the CLAUDE.md rule was corrected rather than just re-stated: it's not enough to avoid writing a closing-keyword-shaped sentence about an issue you're not closing — you also can't safely *quote* one with the real number in it, for any reason, including to document the bug. The fix adopted is a placeholder number in any example text, not a formatting trick. This also answers something I'd flagged as untested: quotation marks and code fences do **not** exempt text from this parser — confirmed, not assumed, because the second closure is exactly that test running for real.

Both closures verified directly on the issue's own timeline (not from a relayed claim) before logging here.

## Item 7 — decision made: hybrid (port panel, rewrite enrichment)

Decided rather than defaulted, per the ask to make this explicit before starting. Two halves treated differently:

- **Port the `/ai-inputs` panel from #29's branch.** Its files are new, zero-conflict against current main, and the branch's own test suite (838 backend + 147 vitest) passed against them. #33's panel findings (4, 6, 10, 12, 13 and others) are described as one-line fixes once ported. Finding 5 (redacted org-name tools permanently uncitable) needs to be **re-derived** against the new resolver rather than ported — its originally-suggested fix assumed the old resolver architecture, which #103 replaced. Findings 7 and 8 are already dead (fixed by W4/D-046, or moot once the panel lands).
- **Rewrite the citation-enrichment logic fresh**, not ported. Reasoning: #103 already replaced the exact seam it plugs into (`_client_tool_names` → `_client_capabilities`, returning typed `Candidate`s with vendors), so porting the old code would mean adapting it to a seam that no longer exists — costlier than writing against the current one directly.

I independently checked the churn evidence given for this split, rather than take the count at face value: `apps/api/app/routes/attack.py`'s commit history on `main` since #29 branched (Aug 8, 2026) shows 5–6 commits depending on exact branch timestamp (`ced76e4`, `261a465`, `47b841f`, `cc76717`, `92a3e79`, `e9e8783`). The claimed "5 commits" is accurate or within one — the evidence is real, not inflated. No PR exists yet for this work.

## #101/#102 persistence work — in progress on `feat/attack-pending-review`, latest pushed commit `2f97ca7`

Reported (not yet verifiable on GitHub past `2f97ca7`): migration 0044, the model field, `analytics.compute(coverage_map, pending_codes=...)` with `pending_review` as its own field, 10 tests covering the four 5.1 invariants, persistence wiring in `run_ai`, `seed_demo.py` writes, and the panel-copy fix. Decision recorded in the migration docstring: NULL scores as pending, not confirmed (the fail-open fix from a prior round). The APPROVED-lockout gap above is a consequence of this same migration that wasn't caught by the original affordability check. Sizing holds at 2–3 sessions / 4–5 adversarial rounds.

## MVP tracking — status this round, and where it disagrees with DELIVERY_PLAN.md

Per the prior session's own recap: items 1, 2a, 3a, 4, and 5 are done (export-target trio/D-049, the #72 sweep/D-051, Tech Debt audit + #77/D-052, W3 approval snapshot/D-053, W2 citation resolver/#103), plus the §14 audit gate (D-054) and two retro-audit fixes. Branch protection confirmed live independently (see below). Item 5's claimed move to DONE (with a new item 5a) is **not yet visible on GitHub** — see the 2f8bc34 finding above; the branch's DELIVERY_PLAN.md still reads the old, stale text.

**DELIVERY_PLAN.md itself was re-checked directly (raw file, both on `main` and on the branch) and is stale in three separate places, not just item 5:**

1. Item 5 still reads **"IN PROGRESS ... ~0.5 session left"** with stale sub-detail ("PR pending audit") — #103 merged days ago.
2. The **"Live risk: `main` has NO branch protection"** section is still present, unedited, and is now flatly false — branch protection has been configured and verified live (see Environment notes).
3. D-054's own recap line still says the audit gate is **"Not enforcing until branch protection is configured"** — also now false for the same reason.

This is the same document that says of itself: "a status line that is wrong is worse than none, because this is the document someone reads to decide what to work on." Three wrong status lines is not a rounding error. I pushed back on folding this refresh into the next feature PR (item 7's) and asked for it to land now, on its own — the message is drafted at the top of this file, **still not sent**.

## D-054, PR #96, PR #97, PR #98, PR #100, PR #103, PR #104 — recap, see prior entries for full detail on each

Branch protection: confirmed live and unchanged since last check — 6 required status checks (including "Adversarial audit recorded"), force-push blocked, deletions blocked, admin bypass allowed. `Require a pull request before merging` still off, so direct pushes to `main` (including this file's own commits) still bypass all required checks — standing open item, unchanged.

## Open decisions — NOT to be reconstructed from memory

**New, highest priority:** the APPROVED-lockout migration question above — needs an explicit answer (my lean: option 3, narrow grandfather clause, with option 2's "does approval mean citation-confirmation" question logged separately, not answered by default). Get the DELIVERY_PLAN.md refresh landed on its own, not folded into item 7's PR — message drafted (see top of file), **still not sent**. Get whatever's local past `2f97ca7` actually pushed — nothing past that commit is verifiable right now. Whether the placeholder-number CLAUDE.md fix is sufficient on its own, or whether a CI-level guard (grep the closing-keyword-plus-number pattern across PR title/body/commits before merge, not just a written convention) is worth the friction — raised last round, genuinely open. Whether to write "missing data defaults to unconfirmed, not confirmed" into CLAUDE.md as a standing rule — recurred multiple times now, still not confirmed landed (reported this round, not yet independently verified since it's past `2f97ca7`). What "addressable" coverage means for #102's exclusion of `pending_review` — still not stated anywhere. `Require a pull request before merging` still off. Local-device mirror of this file — still unconfirmed whether Gene wants it kept in sync. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape — unchanged. Whether to parallelize item 6 — still undecided.

**Resolved this round, removed from open decisions:** item 7's rebase-vs-rewrite question — decided (hybrid, see above).

## Resolved as of this round

#104 merged clean (6/6 checks). #101 reopened a second time with the actual root cause identified and independently verified (not just claimed) — the CLAUDE.md rule is now broader and correct rather than merely re-stated. Item 7's reuse-vs-rewrite question, flagged as an open decision two rounds ago, is now explicitly decided with evidence I checked myself rather than accepted at face value. DELIVERY_PLAN.md's staleness, previously flagged only on item 5, is confirmed to extend to two more sections, and confirmed the claimed item-5/5a fix is not actually on GitHub yet either. Adversarial-reviewer and Playwright both confirmed set up (neither run).

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Item 7's size is now known rather than uncertain: panel port is low-cost (zero-conflict, tests already pass), enrichment rewrite is the real work, sized within the session estimates already on file.

## Environment notes (standing)

Unchanged from prior entries except branch protection, now confirmed live (see above, and DELIVERY_PLAN.md's stale "no branch protection" section above it). Postgres migrations clean through 0044 as of this branch on GitHub (0043 on main, 0044 in flight on `feat/attack-pending-review`, reported but not yet independently re-verified past `2f97ca7`). Provider live key: RESOLVED, reverted to fixture-by-default on purpose. Zero RELEASED ATT&CK assessments exist and there is no production deployment yet — standing context for how "client-facing" language elsewhere in this file should be read, and the exact reason the APPROVED-lockout finding above is a dev-only problem today rather than a client-facing one.

## Do not merge

None currently open — zero open PRs as of this round.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. Missing/absent data silently defaulting to the confirmed or safe-looking state instead of the unconfirmed one — two instances, unchanged this round. A rule rewritten three times without its input space ever being enumerated is a design problem. Closing a container that bundles genuinely-done work with still-needed work can silently drop the still-needed part. A mechanism built to enforce a format only proves it handles the formats it was tested against. Code can assert the opposite of what actually happens and nothing catches it until an adversarial pass reads the code path directly. A migration's effect on existing rows is not uniform by default — **the APPROVED-lockout finding this round is a fresh, concrete instance of exactly this: the affordability check verified zero RELEASED rows and never checked the APPROVED state, which turned out to be the state that actually breaks.** A mechanism that reports on a violation is not the same as a mechanism that blocks it. Credential material never travels through a relay conversation. Test behavior changes get called out explicitly in the test itself. A rule whose measured signal is a small fraction of its raw output should be narrowed. A mutation-testing survivor is only meaningful relative to which tests were actually run against it.

**An issue tracker's own auto-close mechanism can produce a wrong status line without any code being wrong — now two distinct instances on the same issue (#101), not one.** First instance: a sentence written to say something was NOT fixed closed the issue anyway, because the parser reads the keyword and ignores the negation. Second instance, and the more interesting one: the fix for the first instance — a PR whose entire content was "here is why this happens, don't do it" — had to quote the trigger phrase to explain it, and the quotation itself retriggered the exact bug being documented. A parser with no concept of negation also has no concept of citation, explanation, or code-fencing; writing *about* a footgun in the footgun's own blast radius is itself a way to set it off. The general lesson: when documenting a text-triggered bug, the documentation's own text is not exempt from the trigger just because its purpose is explanatory — use a placeholder, not the real value, even in the write-up.
