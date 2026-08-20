# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (#96 and #97 both merged, live regression closed; root cause of the missed audit gate confirmed directly — §14 exists only in the cross-service-integrity plan doc, not in CLAUDE.md, and the miss was a silent conflict between two standing instructions, not forgetting; D-051's justification for deferring W8b confirmed false; Gene sent back a recommendation to mechanize gate enforcement narrowly rather than the full non-deterministic audit)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97 merged, all verified directly on GitHub. Only #29 remains open, permanently unmerged under D-054. #84, #85, #87, #89, #90, #92 filed and open.

Next real work: #94's excluded_count comment fix, folded together with two more things per this round — moving the §14 audit gate into CLAUDE.md, and correcting D-051's now-false justification for deferring W8b. Then back to W2's UI half on the fresh branch under D-054, unchanged approach.

## The missed audit gate — root cause confirmed, and a recommendation sent back

Verified directly rather than taken on trust: `docs/plans/2026-08-08-cross-service-integrity.md` §14 reads exactly as reported — "Every workstream merges on a clean adversarial-reviewer audit, not on a green suite." CLAUDE.md, read in full, has zero mention of this rule; it documents the two static/mutation gates (#72, D-051) but not the pre-merge adversarial-audit requirement. So the structural half of the explanation holds: the only always-loaded file doesn't carry the rule.

The other half, given directly rather than deflected: the other session's own operating instructions say not to invoke agents unless asked; Gene asked once, at the start of the workstream, for the #86 audit; after that the session treated the standing "don't invoke agents" as silently overriding §14 rather than surfacing the conflict. That is why #93, #94 and #95 all merged on green CI without it, and #96 is the live regression that resulted.

Response sent back: agreed with folding the gate into CLAUDE.md and enforcing it for W2/item 6/item 8 going forward, but flagged that a documentation fix alone is a discipline-based fix for what was diagnosed as a discipline-based failure — the same shape that already burned W8a nine times before it got mechanized. Recommended a narrower structural addition: a required GitHub check that blocks merge without evidence the audit ran (a required label or bot comment), which is a small, cheap, deterministic addition — distinct from building the full W8b (the audit itself running automatically and non-deterministically in CI on every PR, which was deferred for real cost/flakiness reasons that this round does not change). Framed as two separate questions rather than one: mechanize the gate's enforcement (recommended, cheap, now) versus mechanize the audit itself (not recommended to reflexively reopen just because D-051's stated evidence broke). Not yet confirmed which the other session will build; watch the #94 PR for how this lands.

## A live client-facing regression was found in already-merged W3, fixed via PR #96 — MERGED

override_security_classification exists so a consultant can correct a wrongly-excluded row and have it become citable again. W3's approval-time snapshot, once a list is approved, reads only the snapshot — so a correction made after approval was invisible to the resolver. Concrete scenario from the PR: a security tool misclassified as non-security, approved that way, corrected later via override — the corrected tool still could not be cited, and every technique it would have covered came back a fabricated gap in the released report, with no warning anywhere. add_capability_components had the same shape. #32 was the allow-list being too wide; this made it too narrow, which the codebase has repeatedly ruled the worse direction. A second bug in the same audit: an approved list with zero in-scope security tools was read as falsy and treated the same as no snapshot, silently falling back to live rows — reopening #32's exact hole for that case.

Fix: CapabilityListResponse gains approved_membership_stale, computed on read, rather than auto-refreshing (would trade #32 back) or blocking the edit (breaks two legitimate workflows). Re-approval stays the one deliberate, audited path to change what the model may cite. The falsy-list bug fixed with an explicit is None check, pinned by its own test. Four new tests, red-on-revert verified. Merged and confirmed on GitHub — the live exposure window is closed.

## The tool built to catch this class of defect had its own instance of it — PR #97 — MERGED

#93's mutation-sweep tool matched AST nodes by (type, lineno, col_offset), not unique across chained calls sharing a position, so it silently mutated the wrong node on chains like update(X).where(...).values(...) and reported the resulting no-op mutant as SURVIVED — sending a reader hunting for a missing test on a line that was never actually mutated. Existed identically in attack.py, csf.py, zt.py and tech_debt.py. The no-op guard that should have caught it compared ast.unparse output against raw file text, never equal for any real file, so it could never fire. No green baseline existed either: any non-zero pytest exit counted as "killed," so a suite that never ran an assertion due to a collection error would print "no surviving mutants" instead of surfacing the failure. Also caught: the tool's restore logic doesn't survive SIGTERM (what a cancelled CI job sends), and it writes comment-stripped source mid-mutation, so an interrupted run could have corrupted a file undetected — a .sweep-orig sidecar now makes that recoverable. Two more #72-pattern instances surfaced fixing this, both inside the tool built to find #72 instances.

Catch numbers re-measured rather than assumed unaffected: the "5+2 real hits" static-checker figure is untouched by this bug and re-measured clean. The mutation sweep has produced exactly one real report ever (the #94 dogfood, a file with no chained calls, so the bug never fired there) and the nightly workflow has never run at all. Nothing that already merged was validated by the broken tool — the numbers hold because the tool was barely used, not because the bug was harmless. On attack.py alone, the fix changed the no-op-mutant count from 8 to 0, which is the exposure the next real target would have hit. Merged and confirmed on GitHub.

## D-054 — W2 vs #29 circularity, resolved

DELIVERY_PLAN's rule was that #29 must not merge until W2 lands, but W2's own rewrite target, citations.py, only exists on #29's branch — a genuine circularity. Verified directly against GitHub: PR #29 shows real merge conflicts against main, 60 commits behind. Issue #30's original audit found 13 issues; a fix commit addressed two blockers; the re-audit found it still partially blocked with three remaining findings. Separately, #32, one of #29's own deferred findings, has already been fixed independently on main via W3/PR #95.

Decision: W2 is cut on a fresh branch off current main, not a rebase of #29 and not built on top of #29's branch. citations.py and issue #30's findings are reference material only. The rewrite fixes the three still-open re-audit findings from day one, including a nullable-vendor bypass — when vendor is null or missing, the resolver refuses to attribute and flags the row for human review. This default is my call, adopted so it doesn't become a blocking round-trip, not yet independently re-confirmed by Gene beyond the overall go-ahead. W2 stays scoped to the resolver logic itself; issue #33's follow-ups stay separately tracked.

## MVP tracking — honest status against DELIVERY_PLAN.md

DELIVERY_PLAN.md's own table is dated 2026-08-19 and still shows item 3a and item 4 as IN REVIEW even though both merged; flagged for the next session to correct in its own commit.

Real status: items 0, 1, 2, 2a, 3a and 4 are DONE. Item 3b not started, blocked on W2. Item 5 (W2) unblocked, circularity resolved via D-054, not started — and now carries #96/#97 as completed unplanned prerequisite work, plus the audit-gate fix and D-051 correction as small additional work ahead of it. Item 6 not started, blocked on nothing, still a candidate to run in parallel with W2. Item 7 blocked on W2. Item 8 not started, blocked on nothing.

This round is itself evidence for DELIVERY_PLAN's own warning that W2 is the estimate most likely to run over: an already-merged, already-audited PR (#95) still produced a live regression on retro-audit, caught only because the gate finally ran. That argues for budgeting W2's audit cycle to surface more rather than fewer findings, not for slowing down.

## Resolved as of this round

#96 and #97 both confirmed merged on GitHub, live regression closed. Root cause of the missed audit gate verified directly: structural (§14 lives only in a plan doc, not CLAUDE.md) plus a silently-resolved conflict between two standing instructions. D-051's justification for deferring W8b confirmed false by the other session's own re-measurement. Recommendation sent back: fix visibility (CLAUDE.md) and enforce going forward, but prefer a narrow structural merge-gate over building the full non-deterministic W8b CI job, since the actual failure was enforcement slipping, not the audit being too expensive to run manually when it does run. Not yet confirmed which the other session will build.

## W3 shipped — PR #95, closes #32, DELIVERY_PLAN item 4 (see prior entries for full original detail; PR #96 above is the regression this same PR introduced, found and fixed via retro-audit)

## Item 0 (#51), export trio (#86), W8/#84/methodology (#88), D-050/#87 decision (#91), W8a (#93), item 3a (#94) — all DONE and confirmed merged, see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, #90's build-1-and-3 scope, #92's contract-test fix, W2, and item 3b are all landed and measured.

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. #89's pin test — scope specified, not yet built. #92 — contract-test fix needed in both CSF and ZT, not yet built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — all still open, unchanged. The nullable-vendor default under D-054 — adopted, not independently re-confirmed. Whether to parallelize item 6 with W2 — not yet decided. Whether the other session builds the narrow merge-gate or the full W8b for the audit-gate fix — recommendation sent, not yet confirmed which was built.

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19; 0043 applied to dev Postgres, verified via alembic current. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene. Under D-054, permanent: #29 will never merge and will be closed as superseded once W2 lands on a fresh branch. Its diff and issue #30's findings may be read as reference material; the branch itself is not built on top of and no live work depends on it landing.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9 confirmed instances, plus one in #94's own test rewrite, plus two more inside the mutation-sweep tool itself, both in tests written specifically to catch this pattern. A defect in one service or function exists in its twins until checked — the chained-call node-matching bug existed identically in attack.py, csf.py, zt.py and tech_debt.py. A false branch dropping a record silently instead of surfacing it under a different reason — three recorded instances, none new this round. A status line that is wrong is worse than none — DELIVERY_PLAN.md's own status table for items 3a and 4 still lags their actual merges. An empty collection being falsy is not the same as the collection being absent — an approved list with zero security tools and an unapproved list both evaluated as falsy, collapsing two states that needed to stay distinct. A green test suite proves nothing about a tool whose own baseline was never confirmed capable of failing — the mutation sweep's core defect, generalized: a tool that certifies other code's tests can fail needs its own proof that it can itself fail. A documented rule that lives in only one place is a rule that gets silently missed — this round's sharpest new instance: §14 governed every merge this workstream made but existed in a plan doc nobody re-reads every session, not in the file that loads every time. A discipline-based fix for a discipline-based failure tends to repeat the failure — the same lesson W8a already taught applied a second time, now to the audit gate itself rather than to a test. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A migration's effect on existing rows is not uniform by default, and a design that reads "old rows behave as before, new rows get the new behavior" has to be stated and tested as its own case, not assumed to fall out of the migration automatically.
