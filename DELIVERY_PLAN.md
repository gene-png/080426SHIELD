# SHIELD Delivery Plan — post-v2 (A–F) to production

_Created 2026-07-02. Owner: David Catarious. Execution: autonomous sprint loop
(`/loop-sprint-cron` + `.claude/sprint-queue.json`), human-gated items called out
explicitly. Sprint docs: `SPRINT_<n>.md`._

## Where we are

**Current as of 2026-08-19.** The MVP path is tracked in the section below, which
is maintained rather than archival. Sprint sections further down are historical
and are left as written.

Five services are built and running (Tech Debt, ATT&CK, Zero Trust, NIST CSF,
Risk Register), all with exporters, deliverables and client dashboards. 43
Playwright specs plus ~900 backend and ~220 web unit tests run in CI. Since
2026-08-08 the work has been the **cross-service integrity stretch**
(`docs/plans/2026-08-08-cross-service-integrity.md`, W0–W8) rather than new
features: making AI-suggested values impossible to lose silently, and making
approval and release mean what they say.

The 2026-07-02 framing below — "nothing has been verified at runtime" — no longer
holds and is kept only as history. What is still true, and is the single largest
gap, is that **no part of the AI layer has ever run against a real model**; see
item 0 in the MVP path.

_Original 2026-07-02 entry: the v2 Developer Work Order (Parts A–F) is merged to
`main` (PR #1, v3.0.0); all local CI gates were green at merge but nothing was
runtime-verified; `SMOKE_TEST.md` was entirely unchecked._

## Guiding rules

- Every automatable SMOKE_TEST.md item becomes a **committed Playwright spec**
  under `e2e/` — the smoke test should never again require a human for the parts
  a browser can assert.
- Defects found get fixed in the same sprint, each on the sprint branch as its
  own conventional commit; small PRs to `gene-png/SHIELD062626` once collaborator
  access lands.
- Human-only items (document eyeballing, live-AI run, infra account decisions)
  are tracked here as **needs-David**, never silently dropped.
- "AI suggests, code computes" is inviolable: no fix may move scoring into
  prompts or fixtures into human-reachable paths.

## MVP completion path (LIVING — update as items land)

_Added 2026-08-19. **This section is maintained, not archival.** When an item
lands, change its status here in the same PR that lands it — the same rule
`CONTEXT.md` follows. A status line that is wrong is worse than none, because
this is the document someone reads to decide what to work on._

**MVP means:** all five services usable for real client engagements, producing
correct documents, with the AI layer working end to end. Not the seeded demo —
fixture mode already demos all five.

### Order, status, and what blocks what

| # | Item | Status | Blocked by | Rough size |
| --- | --- | --- | --- | --- |
| 0 | **Live-AI verification (#51)** | **BLOCKED** | A working provider key. The `.env` key returns 401 | 1 session once a key exists |
| 1 | **Export-target trio — #73 + #75 + #79** | Not started | Nothing | 0.5–1 session |
| 2 | **CSF client dashboard** | **DONE** (PR #80, merged 2026-08-19) | — | — |
| 3 | **Export/persistence audit — Tech Debt, ATT&CK** | Not started | ATT&CK's pass should follow W2 (item 5), not race it | 0.5 session each + unknown fixes |
| 4 | **W3 — Tech Debt approval snapshot** | Not started | Nothing. Decision made: **Option A**, approval-time membership snapshot | 1–1.5 sessions |
| 5 | **W2 — ATT&CK resolver rewrite + tri-state** | Not started | **W3** (item 4) | 2–3 sessions |
| 6 | **W1 Risk step** | Not started | Nothing | 1–1.5 sessions |
| 7 | **W1 ATT&CK step** | Not started | **W2** (item 5) | 1 session |
| 8 | **W6 — Risk export/publish split** | Not started | Nothing | 0.5–1 session |

**Total remaining: roughly 6–10 focused sessions** (item 2 landed), plus whatever items 0 and 3
surface. Call it **two to three weeks** of concentrated work, not days — and the
W3 → W2 → W1-ATT&CK chain is over half of it.

### What a "session" is, in hours

Measured from this repo's own git history rather than estimated:

| Unit of work | Rounds | Dense elapsed |
| --- | --- | --- |
| W1 ZT step (PR #66) — red tests through round 5 | 5 | ~8.5h continuous for red → round 3, plus ~2–3h for rounds 4–5 |
| CSF client dashboard (PR #80) — API + frontend + e2e | 1 | ~4h |
| Shape guards + CSF provenance (PR #78) | 1 | ~2–3h |

So **one "session" ≈ 4–8 hours of continuous work**, and the variance is almost
entirely adversarial rounds: each round costs roughly 1–3h including the fixes it
generates. W1-ZT's elapsed span looks like 23h in the log, but two of those gaps
are idle time, not work — do not read commit timestamps as effort.

**6–10 sessions ≈ 35–65 hours ≈ 7–12 working days** at 5–6 productive hours a
day. That is where "two to three weeks" comes from.

Two caveats that matter for planning:

- These are throughput numbers for an agent working with parallel subagents, not
  a human developer's rate. Do not use them to size someone else's week.
- **W2 is the estimate most likely to be wrong**, and wrong upward. It is the
  largest item, it touches scoring, and items that touch scoring in this repo
  have needed four to five adversarial rounds rather than one.

### Dependencies, stated rather than implied

```
W3 ──> W2 ──> W1 ATT&CK          (the long pole; ~4-5.5 sessions end to end)
                └─> ATT&CK export audit

#73 ─┬─> (independent)
#75 ─┤
#79 ─┘

W1 Risk ──> (independent)
W6      ──> (independent)
#51     ──> (independent, but gates "MVP" itself)
```

- **W3 before W2** — narrow-confirmed is unsound against a mutable approved list,
  and the snapshot is what discharges that. Do not assume the dependency is
  satisfied by the ADD-path carve-out; it is not.
- **W2 before W1-ATT&CK** — building counters against a resolver that is about to
  be replaced means building them twice. Also settled: **#44's fork resolves to
  `applied` + a separate tri-state count**, not a reason code inside `dropped`.
- **W2 before the ATT&CK export audit** — same files, and the audit wants the
  post-rewrite shape.
- **#29 must not merge** until W2 lands plus a clean adversarial audit.
- Items 1, 6 and 8 depend on nothing and can run in parallel with the chain.

### Why the chain is worth a second session in parallel

Items 4, 5 and 7 are ~4–5.5 sessions; everything else combined is ~2–3. The
chain touches `attack.py`, `tech_debt.py` and `citations.py`; the parallel track
touches `risk.py`, `csf.py` and the web dashboards. File contention is low, and
the two decisions the chain was waiting on are now made.

### The one thing no amount of work here closes

**Nothing in the AI layer has ever run against a real model.** All five jobs are
proven only against fixtures that echo the parser's own keys back, which
structurally cannot produce a drop, a shape error, or a drift. Six of eight ZT
reason codes have never been observed; the CSF ones have not either. That is
**item 0**, it needs a key rather than engineering, and no amount of review
substitutes for it. Treat MVP as not-reached until it is done.

### Recently landed (context for the above)

- **W1 CSF** (PR #54, D-045) and **W1 ZT** (PR #66, D-047) — every AI suggestion
  applied or itemized. ZT took five adversarial rounds.
- **W4** (PR #58, D-046) — release assigns RELEASED to the parent. Unblocked W5.
- **Shape guards + CSF provenance** (PR #78, D-048) — all four suggestion jobs
  refuse a wrong-shaped list; offline runs no longer overwrite hand-typed CSF
  scores.
- **CSF client dashboard** (PR #80) — the last assessment service without one.
  Ships reading the client's intake target, which is why #79 exists and is first
  in the queue.

### Deferred, and NOT part of MVP — listed so they are not silently dropped

| Item | Status | Note |
| --- | --- | --- |
| **W0 freeze** | Open decision | Unblocked by W4, but needs Part 3 reopen scoped for CSF (that is W5). D-046 is explicit the W4 lock is PARTIAL |
| **W5 — reopen ×4 + release-staleness guard** | Not started | Unblocked by W4. **#59 is in scope for it** |
| **W7 — watermarking** | Not started | Gated on W5 |
| **W8 — adversarial audit in CI** | Half done | Agent file landed (PR #36); the CI job was never built. **#72** (sweep for tests that cannot fail) attaches here |
| **#67 recurrence risk** | Fixed for CSF (PR #78) | — |
| Production runway | Unscheduled | See the section below; still gated on cloud/account decisions |

### Open issues by theme (as of 2026-08-19)

- **Export correctness:** #73, #75, #79 — item 1
- **AI ledger:** #47, #52, #53 — `llm_calls` says COMPLETED for rejected calls,
  is flushed-not-committed, and marks unbillable calls charged
- **Silent discard:** #46, #60, #77 — wrong top-level key, CSF's unread
  `executive_summary`, `tech_debt_extract`'s unguarded parser
- **Accessibility:** #69 — live regions mounted with their text, so failures
  announce and successes never do
- **Dev loop:** #65 — `seed_demo.py` is all-or-nothing, so a drifted dev DB
  cannot be repaired by re-seeding
- **Policy, needs a human:** #57 (client read of a released ATT&CK assessment),
  #62 (`ServiceStatus.RELEASED`)

## Sprint 1 — Smoke-test automation sweep + defect burn-down (COMPLETE 2026-07-03)

Goal: every automatable section of SMOKE_TEST.md (§0–§9, §11–§13, §15) has a
passing Playwright spec; defects found so far are fixed. Branch:
`qa/smoke-sweep-sprint-1`. Detail: `SPRINT_1.md`. Queue: `.claude/sprint-queue.json`.

Known defects going in (from the 2026-07-02 interactive session):
1. Home-page marketing copy advertises "reviewer audit walk" (reviewer role was
   removed in A3) and names the fourth service "Attack Surface Mapping" instead
   of MITRE ATT&CK Coverage Mapping.
2. ~~Sign-up helper copy describes v1 behavior ("first registrant becomes the
   Primary POC") instead of B1 (first user bootstraps admin; others need an
   approved domain).~~ **RESOLVED (D-034):** `/sign-up` copy now describes open
   self-serve registration with automatic org assignment.
3. ~~Seed data creates the Atlas client but approves no email domain, so
   self-registration on a fresh stack is impossible until an admin adds one.~~
   **RESOLVED (D-034):** self-registration is now open and auto-provisions the
   tenant, so a fresh stack needs no admin domain approval to sign up.
4. Duplicate-email registration surfaces a raw "Request validation failed."
5. No custom `not-found.tsx`: bad URLs render the bare Next.js 404 (dead end,
   violates the §12 no-dead-ends rule).
6. Doc drift: README describes a worker service (removed in F) and an e2e
   harness (directory is empty); BUILD_REPORT.md / CHANGELOG.md stuck at Phase 2.
   (Fixed already: seed_demo.py crash on dropped A1 column — parked on
   `fix/seed-demo-a1-drift` awaiting PR access.)

## Sprint 2 — Findings burn-down + CI hardening (PLANNED 2026-07-03, not launched)

Goal: fix everything Sprint 1's specs surfaced; wire the e2e suite and runtime
axe into GitHub CI; import IG Core/Supporting cross-reference metadata so CSF
roll-up Rules 2/5 and `is_core` stop using safe defaults; refresh stale docs
(BUILD_REPORT, CHANGELOG; README was fixed in Sprint 1 T10). Detail:
`SPRINT_2.md` (11 tasks T0-T10). Queue staged at
`.claude/sprint-queue.sprint-2.json` — see the SPRINT_2.md launch checklist
(branch creation, queue swap, demo-DB wipe warning) before invoking
`/loop-sprint-cron`.

## Sprint 3 — Audit correctness & honesty (COMPLETE 2026-07-09, PR #26)

(The "production runway" sprint originally sketched here was re-scoped; infra
remains gated on David — see the needs-David track.) Actual Sprint 3 burned
down the 2026-07-08 deep repo audit: CSF live-mode Run-AI schema align, real
forced-reauth + refresh rotation, Redis rate limiting, §15.5 export
filenames, `llm_calls` tenant attribution, docs truth pass. Detail:
`SPRINT_3.md`.

## Sprint 4 — Framework majors + multi-provider LLM (COMPLETE 2026-07-10, PR #28)

The D-018 majors bundle (Next 15 / React 19 / Tailwind 4 / ESLint 9 flat /
Node 22; ESLint 10 deferred upstream) executed one major per commit to
audit-zero, plus OpenAI + Gemini adapters behind the redacting egress seam
(D-024). Detail: `SPRINT_4.md`.

## Sprint 5 — Client value loop (PLANNED 2026-07-10, not launched)

Goal: the client-facing value surfaces — deliverable release-to-client flow
(D-025), `/documents` (§6.7), `/home` dashboard (§6.4) + value-loop card
(§2.5), CSF POA&M step (spec step 10), redaction preview gate, `/admin/audit`
viewer, vitest harness + react-hooks v6 adoption. Detail: `SPRINT_5.md`.
Queue staged at `.claude/sprint-queue.sprint-5.json` — see the SPRINT_5.md
launch checklist before invoking `/loop-sprint-cron`.

## Production runway (unscheduled — gated on David)

`infra/terraform` skeleton for AWS GovCloud / Azure Government (**blocked on
David: account/region/network decisions**); MFA + email-verify feature-flag
enablement (D-020); production deploy runbook; DR drills.

## Needs-David track (not in any sprint queue)

- SMOKE_TEST §10: eyeball the generated CSF/Risk Register PDF/Word/XLSX files
  (Sprint 1 generates and collects them; David judges "looks right").
- SMOKE_TEST §14: one live-AI run (requires `ANTHROPIC_API_KEY` +
  `SHIELD_LLM_MODE=live` in `.env`).
- Push `fix/seed-demo-a1-drift` + open PR once Gene grants collaborator access;
  same for the Sprint 1 branch.
- Sprint 3 infra decisions (cloud, account, region, network).
