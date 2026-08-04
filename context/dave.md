# Dave: current status

_Owner: Dave (SpearheadAnalytica). Only Dave's sessions write this file._
_Last updated: 2026-07-22 (Sprint 9 "activate the seam" complete on its branch;
sprint PR not yet opened)._

## Branch / in flight

- **Sprint 9 "activate the seam" is COMPLETE on `feat/sso-discard-demo-sprint-9`**
  (T0 through T10 all done, targeting `v3.5.0`). The loop ran the eleven tasks;
  T10 wrote the wrap-up docs and re-ran the full exit gate set plus the full e2e
  suite green on the flag-off dev stack. The branch is ready for the sprint PR,
  which I open myself (agents never open the sprint PR).
- What shipped, by theme:
  - **Hybrid Keycloak OIDC (T4 through T7, D-032, migration 0032).** Flag-gated
    default off. `POST /auth/oidc/exchange` verifies the Keycloak access token
    against the realm JWKS (RS256-only, `iss`/`aud`/`azp` pinned) and mints a
    native SHIELD HS256 pair only for an already-active local account. No JIT.
    Keycloak tokens are never accepted as API bearers. Flag off is a behavioral
    no-op (provider absent, zero Keycloak network). The secret-less PKCE client
    worked on next-auth `5.0.0-beta.31`, so the pre-approved confidential-client
    fallback was never needed and no secret was committed.
  - **Draft discard across all four services (T0 through T3, D-031).** Draft-only
    admin `POST .../discard`, the app's first destructive-confirm dialog, the
    version trap closed, hidden latest-consumers (risk synthesis, engagement cards)
    skipping discarded rows, a conditional-UPDATE concurrency contract. The three
    approve-first e2e preambles now discard instead.
  - **Demo + export automation (T2, T8, T9, D-033).** The five SMOKE §10 export
    eyeballs are now unit assertions over real bytes (pypdf test dep);
    `demo-reset --demo` plus `e2e/demo/demo-journey.spec.ts` and a new CI `demo`
    job prove the hosted-demo bring-up.

## Decisions made / carried (recorded for agents)

- **Sprint 9 scoping calls held as planned:** hybrid OIDC depth only (no full
  federation); discard on all four services with client-touched CSF/ZT drafts
  discardable behind a warning dialog; pypdf for PDF content assertions; the CI
  demo job on every PR.
- **Agents never launch the sprint loop, and never open the sprint PR.** Both are
  mine at the keyboard.
- **Keycloak SSO deferral stays LIFTED at hybrid depth.** Full token federation,
  JIT provisioning, an un-discard endpoint, and `email_verified_at` stamping from a
  Keycloak claim are explicitly out of scope, carried on the deferred list.
- **Infra: local containers still** (2026-07-13 call unchanged); `.env` stays
  fixture-mode, flag off. No live-AI or cloud credentials were needed.

## Next steps

1. Open the Sprint 9 PR from `feat/sso-discard-demo-sprint-9` into `main` with a
   rich body (summary, task table, test plan, the two pending-PR-run citations and
   the deferred/eligibility notes below). Adopted/rejected Codex findings already
   tabled in the planning PR.
2. Once the PR is open, cite the green `demo` and `e2e` CI job runs
   (`gh run view`) in the PR body and check SMOKE §27's CI-job box then. Both jobs
   trigger only on push/PR to `main`, so this is the first venue they run.
3. Flag a follow-up for the `sharp <0.35.0` HIGH advisory (libvips CVEs, transitive
   via next@15's image optimizer, not branch-introduced). It needs a lockfile bump
   this sprint deliberately did not touch: a Dependabot bump or a root pnpm override
   on `main`. The `postcss` moderate rides along.
4. When flipping the OIDC flag on to demo it, remember to restore it off and re-run
   one credentials sign-in before ending the session. The flag must never be
   committed on.

## Notes for Gene

- Sprint 9 is complete on its branch but NOT merged; I open the PR. The plan of
  record is `SPRINT_9.md`; the end-of-sprint state is in `CONTEXT.md` and
  `BUILD_REPORT.md`, the narrative in `CHANGELOG.md` `[3.5.0]`.
- The OIDC work is deliberately hybrid: Keycloak authenticates, the backend keeps
  minting its own HS256 JWTs through `POST /auth/oidc/exchange` (RS256/JWKS
  validation, no JIT, TOFU `keycloak_sub` binding, migration 0032). Every existing
  auth surface is untouched with the flag off, and the default e2e suite proves it.
- T0 touched `risk.py` and `intake.py` beside the four service route files on
  purpose: both had their own "latest assessment" queries that had to skip the new
  `DISCARDED` status (Codex's two blockers). Not scope creep.
- Two opt-in specs self-skip by default (`s26-oidc-login` on `E2E_OIDC`,
  `demo/demo-journey` on `SHIELD_DEMO_SMOKE`), so the default suite is unchanged at
  the 27-file count. `demo-reset --demo` is destructive; never run it implicitly.
- Lint pins unchanged: `ruff==0.15.20` / `black==26.5.1` exact,
  `known-first-party=["app"]` in root pyproject; do not remove.
