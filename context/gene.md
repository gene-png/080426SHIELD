# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-20 (#91 open, docs-only, D-050 decided: Option A confirmed; #90/#89/#85 filed as required follow-ups; #85 re-weighted)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision. **This file lives in the repo, not on any one machine — a local computer restart does not affect it.**

## Branch / in flight

`main` has **#78, #80, #76, #49, #50, #81, #82, #86, #88 merged**. Only **#29** remains open (do-not-merge, parked pending W2 + clean audit) plus **#91** (D-050 docs, checks running as of this entry — verify before assuming mergeable) and **#84, #85, #87, #89, #90 filed**, all open and tracked.

**Merge #91 when green — no objection.** After that: DELIVERY_PLAN item 2a (W8a) and item 3 (Tech Debt/ATT&CK export audits), per the stated queue. Two open product calls (#87's follow-on #90, and the still-owed test) below, neither blocks #91.

## D-050 — #87 decided: Option A (contracted target), confirmed and recorded

Went with the recommendation given last round. **No business reason found for the alternative (B, the on-screen/reviewed target)** — the strongest case for B (a mid-engagement re-scope, e.g. contracted S4 renegotiated to a phased S3) doesn't actually argue for wiring the selector into the document; it argues a re-scope should be a recorded, deliberate change, which is the opposite of "whatever the selector said at click time." D-050 recorded in DECISIONS.md: no behavior change (confirms what #86/D-049 already shipped by implication), but makes the choice explicit and load-bearing rather than an artifact of a bug fix.

**#89 carries the required UI work**, not optional. Labeling the selector alone isn't enough — it's exploration-only and doesn't reach Finalize (`zt.py:1400`, `csf.py:865` take it as a query param only). The part that actually prevents confusion is surfacing the divergence **at Finalize**, the one moment the consultant can act on it. Without that, a screen showing 12 gaps at S3 and a document showing 37 gaps at S4 with no explanation reads as a permanent bug, not a policy decision.

## #90 (new) — Option A has no consultant-side write path at all

Confirming D-050 surfaced a real gap, filed and tracked rather than used to reopen the decision. The only two writes to the contracted target anywhere in the codebase are in the client self-assessment submit (`app/routes/csf.py:664`, `app/routes/zt.py:1186`), both gated on `DRAFT`. `admin.py` only reads. So the value governing every deliverable is: set by the client at intake, amendable exactly once by the client at submit, then frozen forever — **no consultant-side amendment route exists**, short of a direct DB edit or a new service. A re-scoped engagement literally cannot produce a correct document under Option A as it stands today. Three options offered in the issue (consultant-side amend route with audit trail; leave client-only but surface the change to the consultant; snapshot the target at approval, same shape as W3's approval-time snapshot). **This is a product call, not a technical one — my read below.**

**#85 re-weighted, not just re-triaged.** Originally filed as a narrow API edge case (self-assessment submit accepts `target = 1` where intake enforces `>= 2`). It's now understood as a bug in the *sole amendment path* for the value governing every deliverable — producing a document reading "0 gap(s) at target T1," the failure mode that looks most like success. Correctly folded into #90's fix rather than left as a separate low-priority ticket.

**Still owed, flagged rather than assumed:** no test pins either reading of the D-050 policy (document follows contracted target, not the selector). Should land with #89. Given nine confirmed instances of the can't-fail-test pattern in this repo, writing this down now is the right call — an unpinned decision is exactly the kind of thing that drifts back the first time someone "fixes" the mismatch by wiring the selector into finalize.

## My read on #90 (offered as input, not a decision)

Of the three options, the snapshot approach (option 3) is worth taking seriously alongside the audited-amend route (option 1), and I'd lean toward the two together rather than either alone: snapshot the target at approval so a finalized document is reproducible even if the underlying request is later touched, *and* require a consultant-side amend-with-reason route for the pre-approval case, rather than leaving the client as the only writer. Leaving it "client-only, but surfaced" (option 2) doesn't fix the actual problem #90 describes — a re-scoped engagement still can't produce a correct document without a workaround. This is a bigger product/workflow question than #87 was (it touches who owns changes to a contractual value mid-engagement), so treat this as a starting opinion, not a recommendation carrying the same weight as the #87 one.

## Item 0 (#51) — DONE, PR #82 merged; export trio (#86) DONE; W8/#84/methodology (#88) DONE — see prior entries for full detail

## Session length — measured from git history (unchanged, see prior entries)

1 session ≈ 4-8 hours. Still needs revision once #84's W1-Risk fold-in, W8a's actual cost, and now #90's scope are all landed and measured.

## MVP completion path — table, dependencies (DELIVERY_PLAN.md, merged via #81, updated via #88)

Item 0 → DONE. Item 2 (CSF dashboard) → DONE. Item 1 (export trio) → DONE, merged via #86. Item 2a (W8a mechanized sweep, two tiers) → Not started, next in queue. Item 3 (Tech Debt/ATT&CK export audits) → Not started, queued after 2a. Item 6 (W1 Risk) → scoped to include #84's fix; #90's resolution may also land there or as its own item, unclear yet. Confirm DELIVERY_PLAN.md's table reflects #91 exactly once it lands.

## #44 / W3 / Risk-W6 — all resolved, unchanged, see prior entries for full detail

## Open decisions — NOT to be reconstructed from memory

- **#90 (consultant-side amendment path for the contracted target)** — product call, my starting read given above (snapshot + audited amend route), not yet decided by Gene.
- **Test pinning the D-050 policy** — flagged as still owed, should land with #89, not yet done.
- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape (blocked on W5's Part 3 reopen scope)

## Resolved as of this round

- #87 — decided: Option A, recorded as D-050.
- W8 priority, #84 scope, audit methodology — all resolved via #88 (see prior entry).

## Environment notes (standing)

- Postgres migrations: confirmed clean through 0042 as of 2026-08-19.
- Provider live key: **RESOLVED.** Working key installed, live mode verified end to end, reverted to fixture-by-default afterward on purpose.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene, independently stated as a dependency in DELIVERY_PLAN.md. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail — **9 confirmed instances**. D-050's policy is currently unpinned by any test — flagged above as still owed, not yet a 10th instance since nothing has broken it yet, but the same shape of risk.
- **A defect in one service/function exists in its twins until checked** — proven true at same-file distance as well as cross-service (see #84, #88).
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, indistinguishable from the model having nothing to say.
- A status line that is wrong is worse than none.
- Credential material never travels through a relay conversation, even when explicitly offered.
- Test behavior changes get called out explicitly in the test itself, never silently adjusted — and the callout should cover every property the change affects, not just the one already being asserted.
- **A value with exactly one writer and no amendment path becomes load-bearing for everything downstream without anyone deciding that on purpose** — new this round (#90): the contracted target was "just" an intake field until D-050 made every deliverable depend on it, at which point its one-way, client-only write path became a real constraint nobody had chosen deliberately.
