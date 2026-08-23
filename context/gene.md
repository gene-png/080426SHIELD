# Gene's Context: 080426SHIELD

## Pick up here

PR #129 confirmed merged, 7/7 checks green. That closes out the process-only run: six PRs in a row (#116, #117, #119, #127, #128, #129) with zero feature work. Item 7 has now actually started. The dev reproduced issue #33 finding 5 on `main` before writing anything (a client whose own tool name collides with the redaction placeholder gets zero citation coverage, forever), wrote a fix (index the redacted form as an alias, wire it into the call site that was inert without it), and reports the citation and redaction test suites green. Nothing pushed yet: 0 commits ahead, 4 files drafted locally, no branch, no PR. Confirmed on GitHub: 0 open PRs, no branch matching "redact" or "citation" other than the pre-existing `docs/attack-citation-resolver-plan` (unrelated, already merged as #34).

Separately, the dev responded point by point to the four-theme critique I drafted for Gene last round. All four were accepted. Two got concrete process fixes rather than agreement-only: a required "searched for: <symptom, not the keyword>" line in sweep output (folded into item 7's PR, not spent as its own PR), and a decision table splitting the stale-cross-reference problem into three checkable classes (doc file paths, D-NNN references, `path.py:NNN` line refs) versus one that isn't (semantic staleness, like a session-count claim going stale after the number it depended on changed), to be filed as a real CI trigger, scheduled after item 7.

**Last updated:** 2026-08-23 (PR #129 merged 7/7 confirmed on GitHub; issue #33 finding 5 confirmed real and matching the dev's reproduction almost verbatim; item 7 started but nothing pushed, confirmed via 0 open PRs and no matching branch; four-theme critique answered in full by the dev)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine; a local computer restart does not affect it.**

## This round, verified against GitHub directly

**PR #129 confirmed merged, 7 checks passed.** Matches the relay's "all seven green" exactly.

**Issue #33 finding 5 confirmed, and it matches the dev's reproduction closely.** Read the issue in full: "The resolver is built from unredacted names... The prompt now says 'CITE THE name VALUE EXACTLY AND VERBATIM', so an obedient model cites '[CLIENT] Secure Gateway'... rejected on every run, forever." The issue's own example client is Northwind ("Northwind SOC Platform... contributes zero coverage on every run"), the same example the dev used in the relayed reproduction output. The issue's own suggested fix ("build the resolver from the redacted names, or resolve against both forms") matches what the dev says they built (index the redacted form as an alias).

**Nothing pushed yet, confirmed.** 0 open PRs on the repo. Branch search for "redact" returned nothing; search for "citation" returned only `docs/attack-citation-resolver-plan`, a pre-existing, already-merged docs branch (PR #34), unrelated to this fix. This matches the dev's own "0 commits ahead, 4 files drafted, nothing pushed" framing exactly, not just approximately.

**The four-theme critique got a full, specific response, not just agreement.** Theme 1 (process crowding out features): accepted, item 7 named as the correction. Theme 2 (status ahead of truth): accepted, pushed-vs-drafted framing adopted starting with this update. Theme 3 (vocabulary sweeps over shape sweeps): accepted, with a concrete mechanism proposed, a required "searched for: <shape>" line in sweep output, reasoned as fixing a process problem (advice that reads as background, not a step) rather than repeating the same prose warning a third time. Theme 4 (stale cross-references): accepted, with a table splitting the problem into structural classes (checkable now) and one semantic class (not mechanically checkable), scheduled as real CI work after item 7 rather than left as "no mechanical fix" again.

## Open question worth raising with the dev

The new "searched for: <shape>" line is self-attested free text, not something the reviewer or CI checks against the actual search performed. That is the same shape as the authority-admission gap PR #129 just fixed elsewhere ("no script reads the line"). Worth asking directly whether the adversarial reviewer will be told to check that the line actually names a shape and not a repeated keyword, or whether it is transparency-only for now with enforcement deferred.

## Branch / in flight

`main` has #127, #128, #129 merged since last round (in addition to everything already listed). Item 7 work exists only as local, unpushed drafts as of this check: no branch, no PR. Next steps per the dev, in order: the `/ai-inputs` endpoint and panel, then the enrichment payload (flagged landmine: `_fixture_mitre_map` currently keeps only `isinstance(v, str)` and would silently drop citations in CI-run mode), then the adversarial reviewer, then the PR.

## MVP tracking: DELIVERY_PLAN.md

Unchanged this round. Item 7 is in progress but nothing has landed against it yet.

## D-054, D-055, D-056, D-057, D-052: decisions log

Unchanged this round. The stale-cross-reference CI trigger, once filed, will likely need its own D-number; not yet requested or written.

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether the "searched for: <shape>" line gets checked by the reviewer or stays self-attested (see above). Whether the stale-cross-reference CI trigger gets its own tracking issue now or waits until it's actually filed after item 7.

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead of item 7's remaining steps. Whether #106/#107's root fixes (stripping HTML comments, narrowing the docs/ prefix match, guarding against renames) get their own scheduled work or stay parked behind "worked around, issue stays open." Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. Whether #84 gets the `mvp-blocking` label. First real unattended cron run (the Monday after 2026-08-22), worth confirming it actually fired.

## Resolved as of this round

PR #129 confirmed merged, 7/7 green. Issue #33 finding 5 confirmed real and matching the reproduction. The four-theme critique confirmed delivered and answered point by point, with two themes getting concrete mechanisms rather than agreement alone.

## MVP-complete vs. client-ready: standing distinction

Unchanged.

## Adversarial-reviewer and Playwright

Unchanged this round; item 7's PR (not yet opened) will be its third real use.

## Environment notes (standing)

Unchanged. Open issue count last confirmed at 34 pre-#121-126; six new issues since (#121-#126); #106, #107, #108 remain open with updated evidence, not new issues. Issue #33 (opened earlier, pre-existing) newly relevant this round as the source of the finding-5 fix.

## Do not merge

Nothing open to merge. PR #129 is merged. Item 7 has no PR yet.

## Recurring defect shapes to watch for (CLAUDE.md)

Unchanged. Worth noting a new candidate for this list once item 7's PR lands: "a redaction/aliasing scheme correct only as long as two code paths are kept in sync by hand." The dev flagged this fragility themselves in the relay (a second, drifted copy of the placeholder logic would silently break the alias), which is good self-awareness but not yet a guarded property.
