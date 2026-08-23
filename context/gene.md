# Gene's Context: 080426SHIELD

## Pick up here

PR #129 is real and matches the relay closely, in more detail than what came through chat. Not ready to merge yet though: as of this check it's 3/7 checks green (the two audit-gate checks plus secret scan) with 4 required checks still running (CI Demo, E2E, Python, Web). Wait for those before merging. Separately, PR #127 and PR #128 are both confirmed merged, so `main` now actually has the adversarial-reviewer rule and the 8-10.5 MVP total, closing the gap flagged two rounds ago.

**Last updated:** 2026-08-22 (PR #129 read in full, checks still in progress; #127/#128 confirmed merged and their content now live on `main`; #106 and #107 confirmed carrying fresh, accurate comments from this round; the vacuous-gate near-miss, the five-state clause, and the authority admission all verified word-for-word against the actual CLAUDE.md diff on the branch)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine; a local computer restart does not affect it.**

## This round, verified against GitHub directly

**PR #127 and PR #128 confirmed merged.** `main`'s `CLAUDE.md` now has 5 occurrences of "adversarial" and `DELIVERY_PLAN.md` now shows the 8-10.5 total. Both were still branch-only two rounds ago; both are real now.

**PR #129 confirmed open**, one commit, six files changed. Read the PR body in full: the near-vacuous-gate finding is real (HTML comments aren't stripped by `check_audit_evidence.py`, so a colon-based commented example in the PR template would have satisfied the FINDINGS/DISPOSITION check invisibly), caught by the dev before review, with the review catching the second half (nothing protected the arrow substitution from being "corrected" back to a colon in a docs-only, gate-exempt diff). Fixed with a CI step that mutates the template and asserts the gate fails on it, proven by a real mutation test shown in the PR body (`MUTANT (arrow -> colon) exit: 1`).

**The five-state clause confirmed on the branch, word for word.** Fetched `CLAUDE.md` at `docs/reviewer-unavailable-clause` directly: "If the reviewer did not run, write `Findings: not run, reviewer absent` (or erroring, timed out, not dispatched: <what conflicted>). Never `Findings: none`." Plus a fifth, separate category for a reviewer that ran against the wrong thing (stale tree, wrong branch, subset, exhausted context), which gets its own `Scope:` line rather than folding into the availability list.

**The authority admission confirmed, word for word.** "No script reads the line; nothing distinguishes a body where Gene approved from one where an agent typed his name... enforce_admins is false and both devs are admins, either of them can already merge past a red gate without writing anything at all." Matches the relay's summary exactly, and is more precise about naming the checkable alternative (`gh pr review --approve`).

**#106 and #107 both confirmed carrying fresh, accurate comments this round.** #107's new comment states the near-miss plainly ("it very nearly shipped a vacuous audit gate") and correctly leaves the issue open since the root fix (strip HTML comments before matching) is still not done, only worked around. #106's new comment adds the PR-template instance as a second concrete example of the docs/-exemption problem, also correctly left open. Both match the PR body's "Known follow-ups" section exactly.

**Two self-corrections confirmed accurate.** The PR body states plainly: "A CLAUDE.md-only diff is not docs-exempt, it's in CODE_PATHS" and ".github/pull_request_template.md was not code before this change. I told Gene the opposite last turn." Both are corrections of things I passed along uncritically last round (I'd suggested the dev check whether a CLAUDE.md-only edit might be docs-exempt; it isn't, and saying so was on me, not just the dev).

## Branch / in flight

`main` now has #110, #113, #116, #117, #119, #127, #128 merged. PR #129 open, checks in progress, not yet mergeable in practice until CI clears. #106, #107, #108 all still open by design, each now carrying evidence from this round rather than being resolved.

## MVP tracking: DELIVERY_PLAN.md

**Resolved.** `main` and `gene.md` now agree: 8-10.5 sessions across items 6, 7, 8, 9. PR #129 does not touch this file, confirmed by its own body ("MVP path is unchanged").

## D-054, D-055, D-056, D-057, D-052: decisions log

Unchanged this round; #129 does not add a new D-number, it's a docs+ci fix, not a decision reversal.

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether to wait here for PR #129's CI to finish before telling the dev to merge (yes), and whether #106/#107's root fixes (stripping HTML comments, narrowing the docs/ prefix match, guarding against renames) get their own scheduled work or stay parked behind "worked around, issue stays open" indefinitely.

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead of item 7. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. Whether #84 gets the `mvp-blocking` label. First real unattended cron run (the Monday after 2026-08-22), worth confirming it actually fired.

## Resolved as of this round

PR #127 and PR #128 confirmed merged, their content now live on `main`. PR #129 read in full and verified accurate, including the five-state clause and the authority admission checked word-for-word against the actual file diff, not just the PR body summary. #106 and #107 confirmed carrying accurate new comments. Two self-corrections in the PR body confirmed genuine.

## MVP-complete vs. client-ready: standing distinction

Unchanged.

## Adversarial-reviewer and Playwright

**Updated this round:** the rule survived its second real use intact. First use (PR #128 reviewing itself) found 11, fixed 9, refuted 1, left 1. Second use (PR #129) found 9, fixed all 9, with 3 of those being narrow workarounds for issues (#106, #107, #108) that stay open rather than closed, which is itself the honest outcome, not a shortcut.

## Environment notes (standing)

Unchanged from last round's `raw.githubusercontent.com` CDN-lag note. Open issue count last confirmed at 34 pre-#121-126; six new issues since (#121-#126), unchanged this round; #106, #107, #108 remain open with updated evidence, not new issues.

## Do not merge

PR #129 open, not yet fully green (3/7 checks passed, 4 required checks still running as of this check). Wait for CI before merging. Nothing else blocking `main`.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged. No new shape this round; this round's findings (HTML-comment gate bypass, docs/-prefix carve-out, rename laundering) are new instances of shapes already recorded (#72's fail-open-looks-like-pass family, and the docs-exemption problem CLAUDE.md's own "sweeping for twins" entry already warns about).
