# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (the structural gate is built — check_audit_evidence.py, deterministic, sub-second, requires an ## Adversarial audit block with Findings:/Disposition: on any PR touching code; the other session's own adversarial audit is now running against this change before it opens as a PR; D-051 corrected in place; #94's excluded_count fix folded in)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91, #93, #94, #95, #96, #97 merged, all verified directly on GitHub. Only #29 remains open, permanently unmerged under D-054. #84, #85, #87, #89, #90, #92 filed and open. A new PR is not yet open — the audit-evidence gate plus the D-051 correction plus #94's excluded_count fix are built and tested locally, and the other session's own adversarial-reviewer subagent is running against this exact change before opening it, deliberately applying the new gate to itself before anyone else has to. No PR number yet; checked GitHub directly, nothing new has landed.

Next real work after this PR merges: back to W2's UI half on the fresh branch under D-054, unchanged approach.

## The audit-evidence gate is built, matching the recommendation sent back last round

check_audit_evidence.py: a deterministic CI job, no model in the loop, sub-second, triggered on pull_request so the PR body is available to read. Fails any PR that touches code and whose body lacks an `## Adversarial audit` section with `Findings:` and `Disposition:` lines. Verified against all three real paths: code with no evidence fails, code with evidence passes, docs-only is exempt (the #88/#91 case — the one defensible skip, since those two PRs were the ones that legitimately had nothing to audit).

Design choices worth recording, since they're the actual substance of whether this closes the gap or just relocates it. Default is "needs audit" — an unrecognized path counts as code rather than being silently exempt, so a new directory added later is covered without anyone remembering to update an allowlist. Tests and CI workflow files count as code, not docs — #93's entire defect lived inside a test-tooling file, and a gate that exempted the thing most likely to need review would defeat its own purpose. A PR that mixes docs with code still needs an audit rather than getting the docs-only exemption by inclusion. `Findings: none` is accepted as valid — refusing an empty findings list would incentivize inventing findings just to satisfy the gate, which is worse than no gate.

One real bug caught by its own test before anyone else hit it: the regex for matching the Findings/Disposition block used `\s*` after the colon, which crosses newlines, so an empty `Findings:` line could match into the next line's unrelated text and report itself satisfied — the gate would have accepted a PR with no real findings section at all. Fixed to `[ \t]*`, which does not cross lines.

What it explicitly does not claim, stated in its own docstring rather than left implicit: it proves an audit was recorded, not that one actually happened — someone could still write a hollow `Findings: none` without having looked at anything. That's the same honesty convention SMOKE_TEST.md already runs on (a box is checked only if a green spec proves it, not on the honor system, but here the analogous proof doesn't exist yet). What actually changes is that skipping stops being silent. All three prior misses (#93, #94, #95) had nothing anywhere saying the gate hadn't run — that silence is what let it happen three times without anyone noticing. This gate does not prevent a bad-faith skip; it prevents an invisible one, which is the specific failure mode that actually occurred. Worth remembering as the honest limitation if this ever gets cited as more airtight than it is.

## D-051 corrected in place, and the correction states its own error plainly

D-051 originally justified deferring W8b (the adversarial reviewer as an automated CI job) on the grounds that manual invocation was "demonstrably working." Three code PRs later that was false. The correction, per the other session's own account, states directly that the evidence used to defer the mechanism was wrong, and that this new gate closes the silent-skip failure mode specifically — without taking on the per-PR cost and non-determinism that the original W8b deferral was correctly worried about. Whether W8b itself (the full automated audit, not just evidence-of-audit) moves into the path is left explicitly open rather than quietly re-decided — consistent with what was asked for.

## #94's excluded_count fix folded in as sequenced

The comment claiming the count is "trustworthy in both regimes" is corrected to state plainly it is false when the model returns at least as many items as there are source rows. The test that previously blessed the wrong claim is renamed to name it as a known gap rather than a guarantee, so a pinned gap doesn't read as a verified correctness claim to a future reader.

## A live client-facing regression was found in already-merged W3, fixed via PR #96 — MERGED (see prior entries for full detail)

## The tool built to catch this class of defect had its own instance of it — PR #97 — MERGED (see prior entries for full detail)

## D-054 — W2 vs #29 circularity, resolved (see prior entries for full detail)

DELIVERY_PLAN's rule was that #29 must not merge until W2 lands, but W2's own rewrite target only exists on #29's branch. Decision: W2 is cut on a fresh branch off current main, not a rebase of #29. citations.py and issue #30's findings are reference material only. #29 stays permanently unmerged, closed as superseded once W2 lands.

## MVP tracking — honest status against DELIVERY_PLAN.md

DELIVERY_PLAN.md's own table is dated 2026-08-19 and still shows item 3a and item 4 as IN REVIEW even though both merged; flagged for the next session to correct in its own commit.

Real status: items 0, 1, 2, 2a, 3a and 4 are DONE. Item 3b not started, blocked on W2. Item 5 (W2) unblocked, circularity resolved via D-054, not started — and now has three completed unplanned prerequisite items ahead of it in the git history (#96, #97, and the pending audit-gate/D-051/#94 comment PR), none of which were in the original session estimate. Item 6 not started, blocked on nothing, still a candidate to run in parallel with W2. Item 7 blocked on W2. Item 8 not started, blocked on nothing.

This round is a second piece of evidence for DELIVERY_PLAN's own warning that W2 is the estimate most likely to run over — not because W2 itself has slipped, but because the process safeguards around it needed real, unplanned repair work before W2 could safely start. That is time well spent, not wasted, but it is real elapsed time DELIVERY_PLAN's 2-3 session figure did not anticipate.

## Resolved as of this round

The audit-evidence gate (check_audit_evidence.py) is built and locally tested against all three paths, with one real bug in its own regex caught and fixed by its own test before merge. D-051 corrected in place with a plain statement of what was wrong. #94's excluded_count comment and test corrected as sequenced. The other session is running its own adversarial audit against this exact change before opening the PR, applying the new gate to itself. No PR open yet as of this check — watch for it before merging.

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, #90's build-1-and-3 scope, #92's contract-test fix, W2, and item 3b are all landed and measured.

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. #89's pin test — scope specified, not yet built. #92 — contract-test fix needed in both CSF and ZT, not yet built. #57, ServiceStatus.RELEASED (#62), W0's freeze shape — all still open, unchanged. The nullable-vendor default under D-054 — adopted, not independently re-confirmed. Whether to parallelize item 6 with W2 — not yet decided. Whether W8b (the full automated audit, not just evidence-of-audit) ever moves into the path — explicitly left open by design, not answered this round.

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19; 0043 applied to dev Postgres, verified via alembic current. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene. Under D-054, permanent: #29 will never merge and will be closed as superseded once W2 lands on a fresh branch. Its diff and issue #30's findings may be read as reference material; the branch itself is not built on top of and no live work depends on it landing.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9+ confirmed instances across the project, most recently caught inside the audit-evidence gate's own regex by its own test before anyone else hit it, which is the pattern working as intended rather than another instance of it slipping through. A defect in one service or function exists in its twins until checked — the chained-call node-matching bug existed identically across all four route modules. A false branch dropping a record silently instead of surfacing it under a different reason — three recorded instances, none new this round. A status line that is wrong is worse than none — DELIVERY_PLAN.md's own status table for items 3a and 4 still lags their actual merges. A documented rule that lives in only one place is a rule that gets silently missed — this is what produced the missed audit gate, and the fix is structural (a required check) rather than just relocating the rule to a more-often-read file. A discipline-based fix for a discipline-based failure tends to repeat the failure — flagged last round, and the response this round built the structural version instead, which is the correct move rather than a repeat of the mistake. A mechanism that proves a record exists is not the same as a mechanism that proves the thing the record describes actually happened — the audit-evidence gate is explicit about this distinction in its own docstring rather than overclaiming, which is the same discipline the mutation-sweep tool now applies to its own catch-rate numbers. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored. A migration's effect on existing rows is not uniform by default, and a design that reads "old rows behave as before, new rows get the new behavior" has to be stated and tested as its own case, not assumed to fall out of the migration automatically.
