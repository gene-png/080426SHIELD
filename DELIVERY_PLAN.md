# SHIELD Delivery Plan — post-v2 (A–F) to production

_Created 2026-07-02. Owner: David Catarious. Execution: autonomous sprint loop
(`/loop-sprint-cron` + `.claude/sprint-queue.json`), human-gated items called out
explicitly. Sprint docs: `SPRINT_<n>.md`._

## Where we are

The v2 Developer Work Order (Parts A–F) is merged to `main` (PR #1, v3.0.0). All
local CI gates were green at merge, but **nothing has been verified at runtime by
a human or a browser**. `SMOKE_TEST.md` is the gate before prod and is entirely
unchecked. Session 2026-07-02 established the runtime works (stack up, sign-in,
onboarding flows) and surfaced the first defects — see CONTEXT.md.

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
