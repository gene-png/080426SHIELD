# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (W8a shipped — PR #93, all five checks green, ready to merge; two-tier sweep for the #72 pattern; D-051 records what it does and does not close; first run filed #92)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has #78, #80, #76, #49, #50, #81, #82, #86, #88, #91 merged. Only #29 remains open (do-not-merge, parked pending W2 + clean audit) plus #93 (W8a, all checks green, ready to merge on my word — verify before assuming already merged). #84, #85, #87, #89, #90, #92 filed, all open and tracked.

Merge #93 when ready — no objection, checks are genuinely green and the PR body itself is honest about scope. After that: DELIVERY_PLAN item 3 (Tech Debt/ATT&CK export audits, #77 folding into Tech Debt).

## W8a shipped — PR #93, DELIVERY_PLAN item 2a

Two tiers, verified directly against the PR rather than taken on the paste. Tier 1 is check_test_integrity.py, static and blocking, wired ahead of pytest in the Python CI job — a two-second check runs before a 13-minute suite proves green for the wrong reason. TI001 flags a test importing a private constant from the module it tests (instance 1's shape). TI002 flags a containment assertion whose needle carries no literal text (instance 8's shape — a bare count satisfied by an unrelated coverage fraction). Neither rule forbids the pattern; both require a written test-integrity marker with a reason, because the same import shape is right in one place (the prompt constant in a contract test, since the prompt is the spec) and wrong in another (instance 1), and no static rule can tell those apart on its own — only a human justification can.

Tier 2 is mutation_sweep.py, nightly plus manual dispatch, never a PR gate — every mutant costs a full test run, and 50 to 150 mutants cannot sit in front of a merge without getting disabled the first time someone is in a hurry.

## The correction volunteered this round, and it matters

The numbers quoted in the #88 round were wrong: "5 + 2 hits, near-zero noise" was a description of the rule as intended, not as built. The first real implementation flagged 41 TI001s and 38 TI002s. Measuring showed 36 of the TI001s were FastAPI dependency-override handles that say nothing about what a test asserts, and 36 of the TI002s were bare containment checks indistinguishable from a dict lookup without type information — both real instances used explicit str() conversion, which became the actual fingerprint. A rule whose real signal is 12% of its raw output would get muted within a week, and a muted rule is worth nothing. One of the checker's own unit tests had encoded the wrong, broader behavior as correct; it's inverted now with the reason written in its docstring rather than just silently changed. This is exactly the kind of number I logged uncritically in a prior round for #90 and had to walk back later — worth naming that this is the second time in three rounds a stated number turned out to be an early estimate rather than a measured one, and the second time it was corrected on the record rather than left standing.

## Why mutmut was rejected, and it's not the reason given at first

The real reason is not that pip install fails in the api container, though it does. Instance 9 was targets= being deletable from a call with the whole suite green — a missing keyword argument, not a wrong operator or value. mutmut mutates expressions and values, not call signatures, so it would not have caught instance 9 either, independent of any environment problem. That's why a purpose-built DropKeyword mutation exists, and it was validated against the real case rather than only unit-tested: dropping targets= near the finalize call produced a killed mutant, pytest returncode 1, with the assertion failing for the expected reason (the per-capability target being ignored, expected 36 gaps), and the file was confirmed restored afterward. That's a real reproduction of instance 9, not a demonstration on a toy case.

## What W8a does not do, stated plainly rather than oversold

D-051 says explicitly that this does not close #72. Tier 1 is structurally blind to instance 2's shape, a test whose own setup performs the step the code under test is supposed to perform, since no static signature exists for that pattern. A surviving mutant in Tier 2 is a question, not a verdict, since some mutants are semantically equivalent to the original and some paths are untested by design. Claiming the sweep closes #72 would be the exact defect this project keeps finding, one level up, and the PR is explicit that it isn't making that claim.

## #92 — the sweep's first real find, filed correctly rather than quietly patched

test_csf_ai_contract.py checks parser-to-prompt but never prompt-to-parser, and its end-to-end half builds its expected response body from the parser's own constants, so it agrees with the parser by construction and can never catch the one thing a contract test exists to catch: the model and the code disagreeing about a key. The import that trips Tier 1 is justified in place with a marker naming #92, so the CI gate stays green without the finding disappearing, which is the property a justification mechanism has to have to be worth anything. The issue also flags that ZT's equivalent contract test needs the same one-directional audit, per the same-defect-in-its-twins pattern, before this is considered closed.

## Item 0 (#51), export trio (#86), W8/#84/methodology (#88), D-050/#87 decision (#91), W8a (#93) — all DONE or ready-to-merge, see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session is roughly 4 to 8 hours. Still needs revision once #84's W1-Risk fold-in, #90's build-1-and-3 scope, and now #92's contract-test fix are all landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81, updated via #88, #91, and #93)

Item 0 is DONE. Item 2 (CSF dashboard) is DONE. Item 1 (export trio) is DONE. Item 2a (W8a mechanized sweep) is DONE pending #93's merge. Item 3 (Tech Debt/ATT&CK export audits, folding in #77) is not started, next in queue. Item 4 (W3, approval-time snapshot, composing with #90's option 3) is not started. Item 6 (W1 Risk) is scoped to include #84's fix.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

#90's build (options 1 and 3 together) — direction given, not yet built. #89's pin test — scope specified, not yet built. #92 — contract-test fix needed in both CSF and ZT, not yet built. #57 — client read behavior for a released ATT&CK assessment. ServiceStatus.RELEASED (#62). W0's freeze shape (blocked on W5's Part 3 reopen scope).

## Resolved as of this round

#93 built and ready to merge, W8a's two tiers, D-051 recorded. The #88 number correction (41+38, not 5+2) volunteered and recorded rather than left standing. The mutmut rejection reason corrected to the real one (call-signature mutations, not just the container issue). #92 filed with a concrete fix path and flagged in ZT as well as CSF.

## Environment notes (standing)

Postgres migrations confirmed clean through 0042 as of 2026-08-19. Provider live key: RESOLVED. Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

A test that supplies its own expected value or precondition from the thing under test cannot fail — 9 confirmed instances, now with a mechanized Tier 1 check for two of the nine shapes (instances 1 and 8) and a mutation-based Tier 2 check that independently reproduces instance 9. Still structurally blind to instance 2's shape. A defect in one service or function exists in its twins until checked — proven true at same-file distance and cross-service, and #92 is a fresh instance: the CSF contract test's one-directionality almost certainly exists in ZT's equivalent test too, flagged explicitly rather than assumed fine. A conditional written to stop double-counting whose false branch silently drops the record. An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say. A status line that is wrong is worse than none — both the #88 numbers and the #90 "frozen forever" claim were wrong-but-stated-with-confidence in this same file within the last three rounds, and both were caught and corrected on the record rather than left standing. That is the pattern this file exists to prevent, and it is worth naming when it happens rather than only naming it as an abstract principle. Credential material never travels through a relay conversation, even when explicitly offered. Test behavior changes get called out explicitly in the test itself, never silently adjusted. A rule whose measured signal is a small fraction of its raw output should be narrowed rather than kept broad and ignored — new this round, from the TI001/TI002 measurement: an unnarrowed rule at 12% signal is functionally the same as no rule, since it trains people to ignore its output.
