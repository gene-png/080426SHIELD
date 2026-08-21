# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-21 (#101 auto-closed a *second* time — this time by #104, the PR written specifically to document the first auto-close, because its own body had to quote the offending phrase to explain it; reopened again, CLAUDE.md's rule broadened from "don't write it in a commit message" to "don't write it at all with a live issue number, quoted or not — use a placeholder"; item 7's rebase-vs-rewrite decision is now made — hybrid, port the panel + rewrite the enrichment — and I independently checked the churn evidence behind it; DELIVERY_PLAN.md is now confirmed stale in three separate places, not just item 5)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97, #98, #100, #103, #104 merged, all verified directly on GitHub. Open PRs: **zero** — confirmed on the Pull requests list. Closed: #29 (superseded-in-part), #99, and all older. #84, #85, #87, #89, #90, #92, #33, #102 filed and open. #101 open — reopened twice now, correctly still open (real work in flight, not yet landed). Active branch `feat/attack-pending-review`: rebased onto current main, gates green, latest commit `bba591a` ("wip(attack): #101/#102 — migration 0044 + pending_review scoring"). No PR opened for it yet.

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

## #101/#102 persistence work — in progress on `feat/attack-pending-review`, no PR yet

Done: migration 0044, the model field, `analytics.compute(coverage_map, pending_codes=...)` with `pending_review` as its own field, and 10 tests covering the four 5.1 invariants. Left: persistence wiring in `run_ai`, `seed_demo.py` writes, and the panel-copy line that currently claims flagged citations "count toward the coverage score exactly as a confirmed citation does" — true today, false the moment #102 lands, and already pinned by a vitest so the flip can't land silently. Decision recorded in the migration docstring: NULL scores as pending, not confirmed (the fail-open fix from the prior round); verified affordable against zero RELEASED assessments and no production deployment. Sizing holds at 2–3 sessions / 4–5 adversarial rounds, on the write-the-state-space-first principle (status × flag-state × cleared-state × NULL-vs-empty).

## MVP tracking — status this round, and where it disagrees with DELIVERY_PLAN.md

Per this session's own recap: items 1, 2a, 3a, 4, and 5 are done (export-target trio/D-049, the #72 sweep/D-051, Tech Debt audit + #77/D-052, W3 approval snapshot/D-053, W2 citation resolver/#103), plus the §14 audit gate (D-054) and two retro-audit fixes. Branch protection confirmed live independently (see below).

**DELIVERY_PLAN.md itself was re-checked directly (raw file, not cached) and is stale in three separate places, not just item 5:**

1. Item 5 still reads **"IN PROGRESS ... ~0.5 session left"** with stale sub-detail ("PR pending audit") — #103 merged days ago.
2. The **"Live risk: `main` has NO branch protection"** section is still present, unedited, and is now flatly false — branch protection has been configured and verified live (see Environment notes).
3. D-054's own recap line still says the audit gate is **"Not enforcing until branch protection is configured"** — also now false for the same reason.

This is the same document that says of itself: "a status line that is wrong is worse than none, because this is the document someone reads to decide what to work on." Three wrong status lines is not a rounding error. I pushed back on folding this refresh into the next feature PR (item 7's) and asked for it to land now, on its own — bundling a docs fix with active feature work is the same pattern that let item 5 go stale twice already; a small, fast, zero-risk PR doesn't need to wait behind a multi-session feature branch. Not yet confirmed whether that request will be honored or the fold-in plan stands.

## D-054, PR #96, PR #97, PR #98, PR #100, PR #103, PR #104 — recap, see prior entries for full detail on each

Branch protection: confirmed live and unchanged since last check — 6 required status checks (including "Adversarial audit recorded"), force-push blocked, deletions blocked, admin bypass allowed. `Require a pull request before merging` still off, so direct pushes to `main` (including this file's own commits) still bypass all required checks — standing open item, unchanged.

## Open decisions — NOT to be reconstructed from memory

**New, highest priority:** get the DELIVERY_PLAN.md refresh landed on its own, not folded into item 7's PR — asked for, not yet confirmed. Whether the placeholder-number CLAUDE.md fix is sufficient on its own, or whether a CI-level guard (grep the closing-keyword-plus-number pattern across PR title/body/commits before merge, not just a written convention) is worth the friction — raised as a question this round, genuinely open, not mine to decide unilaterally. Whether to write "missing data defaults to unconfirmed, not confirmed" into CLAUDE.md as a standing rule — recurred twice now, still not done. What "addressable" coverage means for #102's exclusion of `pending_review` — still not stated anywhere. `Require a pull request before merging` still off. Local-device mirror of this file — still unconfirmed whether Gene wants it kept in sync. #90's build, #89's pin test, #92's contract-test fix — still not built. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape — unchanged. Whether to parallelize item 6 — still undecided.

**Resolved this round, removed from open decisions:** item 7's rebase-vs-rewrite question — decided (hybrid, see above).

## Resolved as of this round

#104 merged clean (6/6 checks). #101 reopened a second time with the actual root cause identified and independently verified (not just claimed) — the CLAUDE.md rule is now broader and correct rather than merely re-stated. Item 7's reuse-vs-rewrite question, flagged as an open decision two rounds ago, is now explicitly decided with evidence I checked myself rather than accepted at face value. DELIVERY_PLAN.md's staleness, previously flagged only on item 5, is now confirmed to extend to two more sections that state things as current risk/status when they are neither.

## Session length — measured from git history (unchanged, see prior entries)

Still roughly 4 to 8 hours per session. Item 7's size is now known rather than uncertain: panel port is low-cost (zero-conflict, tests already pass), enrichment rewrite is the real work, sized within the session estimates already on file.

## Environment notes (standing)

Unchanged from prior entries except branch protection, now confirmed live (see above, and DELIVERY_PLAN.md's stale "no branch protection" section above it). Postgres migrations clean through 0044 as of this branch (0043 on main, 0044 in flight on `feat/attack-pending-review`). Provider live key: RESOLVED, reverted to fixture-by-default on purpose. Zero RELEASED ATT&CK assessments exist and there is no production deployment yet — standing context for how "client-facing" language elsewhere in this file should be read.

## Do not merge

None currently open — zero open PRs as of this round.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 12 confirmed instances, unchanged this round. Missing/absent data silently defaulting to the confirmed or safe-looking state instead of the unconfirmed one — two instances, unchanged this round. A rule rewritten three times without its input space ever being enumerated is a design problem. Closing a container that bundles genuinely-done work with still-needed work can silently drop the still-needed part. A mechanism built to enforce a format only proves it handles the formats it was tested against. Code can assert the opposite of what actually happens and nothing catches it until an adversarial pass reads the code path directly. A migration's effect on existing rows is not uniform by default. A mechanism that reports on a violation is not the same as a mechanism that blocks it. Credential material never travels through a relay conversation. Test behavior changes get called out explicitly in the test itself. A rule whose measured signal is a small fraction of its raw output should be narrowed. A mutation-testing survivor is only meaningful relative to which tests were actually run against it.

**An issue tracker's own auto-close mechanism can produce a wrong status line without any code being wrong — now two distinct instances on the same issue (#101), not one.** First instance: a sentence written to say something was NOT fixed closed the issue anyway, because the parser reads the keyword and ignores the negation. Second instance, and the more interesting one: the fix for the first instance — a PR whose entire content was "here is why this happens, don't do it" — had to quote the trigger phrase to explain it, and the quotation itself retriggered the exact bug being documented. A parser with no concept of negation also has no concept of citation, explanation, or code-fencing; writing *about* a footgun in the footgun's own blast radius is itself a way to set it off. The general lesson: when documenting a text-triggered bug, the documentation's own text is not exempt from the trigger just because its purpose is explanatory — use a placeholder, not the real value, even in the write-up.
