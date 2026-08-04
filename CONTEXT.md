# Project Context — state of `main`

_Last updated: 2026-07-22 (Sprint 9 "activate the seam" complete on
`feat/sso-discard-demo-sprint-9`, targeting `v3.5.0`, PR not yet opened; Sprint 8
"prove it in the browser" merged as PR #42, `v3.4.1`). This file describes the
project as of the branch it sits on and is updated ONLY as part of a PR. Durable
facts and environment gotchas live in `CLAUDE.md`; personal in-flight status
lives in `context/<name>.md`; per-sprint detail lives in `SPRINT_<n>.md`._

## Current state

- **v2 work order (Parts A–F) merged to `main`** (PR #1, migrations 0015–0025,
  `v3.0.0`): all four service surfaces, multi-tenant onboarding, AI job
  registry, CSF Playbook engine, Risk Register, F hardening pass.
- **Sprint 1 "smoke sweep"** (PR #16, `v3.0.1`): `SMOKE_TEST.md` backed by a
  green Playwright smoke suite; offline fixture-mode AI (D-017), typed
  registration errors (D-016).
- **Sprint 2 "findings burn-down"** (PR #19, `v3.0.2`): 11 tasks, CI `e2e` job
  added.
- **Sprint 3 "audit correctness & honesty"** (PR #26, `v3.0.3`): 8 tasks burning
  down the 2026-07-08 deep repo audit.
- **Sprint 4 "framework majors + multi-provider LLM"** (PR #28, `v3.1.0`): the
  web stack moved to Next 15 / React 19 / Tailwind 4 / ESLint 9 / Node 22, and
  multi-provider LLM egress (OpenAI + Gemini beside Anthropic, D-024) landed
  below the unchanged redacting seam.
- **Sprint 5 "client value loop"** (PR #31, `v3.2.0`): consultant output now
  delivers visible value to the CLIENT role — deliverable release flow (D-025),
  `/home` executive dashboard + §2.5 value-loop card, `/documents`, a CSF POA&M
  step, a pre-egress redaction preview, and the first read surface over the
  append-only audit stores (`/admin/audit`).
- **Sprint 6 "real demo"** (PR #33, `v3.3.0`): the platform became a real,
  self-standing demo — runnable live-AI path with boot-time fail-loud (D-026),
  seed→MinIO storage parity, real TOTP MFA (D-027) + real email verification /
  password reset (D-028) on the custom-JWT stack (D-020 boot-refusals gone, flags
  now gate enforcement), a full-matrix `/ready` + `/admin/health` operator view,
  a coherent downloadable Atlas demo seed with one-command reset, and a
  hosted-demo production compose. Migrations 0030 (MFA TOTP) + 0031 (email
  tokens).
- **Sprint 7 "GCP live path + close the client loop" MERGED** (PR #36,
  `v3.4.0`): the live-AI path is now **proven against
  a real provider with no static key** — Vertex AI via Application Default
  Credentials (D-029), validated end-to-end across all five AI purposes on Dave's
  box (2026-07-15). The client loop is closed with a best-effort release
  notification email (D-030); dev/CI email delivery is on by default so the
  MailHog register/verify/reset loop is real every run (s21 runs, not skips); the
  Sprint-5 `reqSeq` stale-fetch guard sweep is finished; and the web auth stack
  migrated from next-auth v4 to Auth.js v5, clearing the `uuid@8.3.2` moderate
  advisory. No new migrations. New user-facing surface (release notification) + a
  real GCP live path justify the **minor** bump. Full exit gate set green — full
  Playwright e2e, `pytest -m unit`, web `tsc`, in-container web vitest (12/12),
  in-container web eslint (0 errors), host prettier `--check` (3.9.5), and
  in-container ruff/black.

### Sprint 7 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Vertex AI provider adapter via ADC — `VertexProvider` on `{region}-aiplatform.googleapis.com` generateContent, Bearer ADC (no static key), shared body-build/parse with `gemini`, token never logged, `live_llm_readiness()` boot preflight; D-029 | `7dcf159` |
| T1 | GCP live validation sweep (opt-in) — all five purposes live on `vertex`/`gemini-2.5-flash` (ADC-only) through the redaction seam; found+fixed 2 adapter defects (`google-auth[requests]`; loud `finishReason` guard + cap 4096→8192 + `thinkingBudget` for 2.5+); SMOKE §14/§14.1 GCP-annotated | `329f9a5` |
| T2 | Client release notification email — shared release helper emails the tenant's active client users on release (best-effort, release is source of truth); D-030 | `4420b53` |
| T3 | Email delivery on by default in dev/CI compose (MailHog); s21 email-verify now RUNS instead of self-skipping; REQUIRE_EMAIL_VERIFY stays off | `d95f5c7` |
| T4 | reqSeq stale-fetch guard sweep remainder (Sprint-5 carry-over) across admin workspaces/panels; guards only where a stale mount-fetch clobbers newer state; two vitest guards | `37f9bd6` |
| T5 | Auth.js (next-auth) v5 migration — `getServerSession`→`auth()` at 34 sites, MFA code-signal re-wired, behavior-identical; clears the `uuid@8.3.2` moderate | `3de0626` |
| T6 | Wrap-up: SMOKE §14 GCP annotation / §25 checked / new §29 release-notification, CHANGELOG `[3.4.0]`, BUILD_REPORT sync, DECISIONS D-029/D-030 verify, full gates, this snapshot | `4796429` (PR #36 squash) |

No new migrations this sprint. New DECISIONS: **D-029** (Vertex AI via ADC as the
GCP live path) + **D-030** (client release notification, best-effort notify).

- **Sprint 8 "prove it in the browser" MERGED** (PR #42,
  `v3.4.1`): eight tasks (T0 through T7) that convert
  human-eyeball SMOKE debt into committed Playwright specs and pay the last
  mint-route debt. The release notification is now eyeballed in MailHog (§29,
  s22), the verify/forgot/reset pages and the MFA enrollment / TOTP / recovery-code
  UI are browser-driven (s23, s24), `/admin/health` and the `/documents` empty
  state have specs (s25, s17), and a double-POST to the tech-debt extract route
  reuses the open draft instead of burning a second LLM call (T1). The sprint's
  headline was an out-of-plan product fix: **MFA sign-in never revealed the TOTP
  field in the browser** because `SignInForm` sent `totp: undefined`, which
  next-auth coerced through `URLSearchParams` into the string `"undefined"`,
  defeating the backend `!totp` guard (fixed in `f10b803`; the new T4 browser spec
  caught what the Sprint-7 vitest could not). No migrations, no new DECISIONS.
  Version is tag/CHANGELOG level only; package manifests untouched. Plan was
  reviewed read-only by OpenAI Codex pre-merge (findings table in PR #37).

### Sprint 8 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Shared MailHog reader helper (`e2e/helpers/mailhog.ts`): `fetchLatestMessage` / `extractToken` / `subjectOf`, polls by recipient plus subject; s21 consumes it with zero behavior change | `3b7bfb7` |
| T1 | Tech-debt extract draft-exists guard: a second POST while a draft is open returns it idempotent-200 before the LLM call (no re-extract, consultant edits survive), matching CSF/attack/zt; `test_extract_versions_subsequent_lists` re-contracted to the APPROVED/RELEASED boundary | `4396f60` (+ e2e realign `b4fe0ba`) |
| T2 | `s22-release-notify.spec.ts`: isolated tenant + unique-email client, release a CSF deliverable, assert the notification in MailHog by recipient + subject + `/documents` link (SMOKE §29) | `d023226` |
| T3 | `s23-auth-pages.spec.ts`: browser-drive verify-email / forgot-password / reset-password pages end to end, then sign in with the new password | `442fca5` |
| T4 | `s24-mfa.spec.ts` part A: enroll on `/account` with a generated TOTP (otpauth dep), assert shown-once recovery codes, sign in through the UI TOTP step. **Surfaced the MFA sign-in browser bug** | `f70a8cc` (fix `f10b803`) |
| T5 | `s24-mfa.spec.ts` part B: redeem a recovery code at sign-in, prove it single-use on reuse. T4+T5 retire the manual MFA walkthrough | `1e782de` |
| T6 | `s25-admin-health.spec.ts` asserts the all-green `/admin/health` matrix on the live stack; `s17-documents.spec.ts` gains a `/documents` empty-state assertion in a fresh throwaway tenant | `57277ea` |
| T7 | Wrap-up: SMOKE annotations, CHANGELOG `[3.4.1]`, BUILD_REPORT sync, this snapshot, `context/dave.md` refresh | `b7d482d` |

No new migrations and no new DECISIONS this sprint: T1 applies the existing
CSF/attack/zt idempotency pattern, and MFA (D-027), email verify/reset (D-028),
and the release notification (D-030) all shipped earlier and were only proven in
the browser here.

- **Sprint 9 "activate the seam" COMPLETE on its branch** (`feat/sso-discard-demo-sprint-9`,
  targeting `v3.5.0`): eleven tasks (T0 through T10) across three themes. The
  long-dormant Keycloak seam is now a working hybrid OIDC sign-in beside the
  credentials form, flag-gated behind `SHIELD_AUTH_OIDC_ENABLED` and default off
  (D-032, migration 0032 `users.keycloak_sub`). The browser round trip ends at
  `POST /auth/oidc/exchange`, which verifies the Keycloak access token against the
  realm JWKS (RS256-only, `iss`/`aud`/`azp` pinned) and mints a native SHIELD HS256
  pair only for an already-active local account. A Keycloak token is never accepted
  as an API bearer; the backend keeps minting its own JWTs (D-020 stays
  authoritative); there is no JIT provisioning. With the flag off the provider does
  not exist and zero Keycloak network calls happen. Every service also gained a
  first-class draft-discard affordance (D-031): a draft-only admin `POST .../discard`,
  the app's first destructive-confirm dialog, the version trap closed, and the
  hidden latest-consumers (risk synthesis, engagement cards) skipping discarded
  rows. The demo compose and the export eyeball debt are now under committed
  automation (D-033): the five SMOKE §10 export checks are unit assertions over real
  PDF/DOCX/XLSX bytes, and `demo-reset --demo` plus `e2e/demo/demo-journey.spec.ts`
  and a new CI `demo` job prove the hosted-demo bring-up. Minor bump for the two new
  flag-gated user-facing surfaces; tag/CHANGELOG level only, package manifests
  untouched. Plan was reviewed read-only by OpenAI Codex pre-merge (verdict
  "rework" on 12 findings, 2 blockers, all folded into the tasks).

### Sprint 9 task → commit

| Task | What shipped | Commit |
| --- | --- | --- |
| T0 | Backend draft discard ×4 + `DISCARDED` status; version trap closed (`_latest_*` skip discarded, mint reads unfiltered `max(version)`); risk synthesis + intake cards skip discarded; conditional-UPDATE concurrency contract; D-031 | `638710c` |
| T1 | Web discard UI: 4 proxies, client fns, shared `DiscardDraftButton` + design-system Modal (first destructive-confirm dialog), `reqSeq` bump before post-discard refetch | `578a98a` |
| T2 | Export-content unit assertions over real bytes (pypdf test dep; PDF/DOCX/XLSX readers); SMOKE §10 re-pointed + one manual aesthetics line; §19 closed | `af4dcf3` |
| T3 | e2e: the three approve-first preambles (s4/s5/s11) now discard via proxy, post-preamble assertions byte-identical; s4 drives the UI discard once; SMOKE §31 | `56bcfce` |
| T4 | Backend OIDC: flag + `oidc_readiness()`, JWKS verifier (RS256-only, cache/TTL/lock), `POST /auth/oidc/exchange` typed-failure matrix, TOFU sub binding, migration 0032; D-032 | `60d2abb` |
| T5 | Infra: dual-horizon Keycloak (`KC_HOSTNAME` + backchannel-dynamic, one canonical iss), realm drift fixes, env plumbing, real flag-gated `/ready` probe | `4c9ab64` |
| T6 | Web OIDC: conditional secret-less PKCE provider, jwt-callback exchange branch, sign-in button, `SessionExpiryGuard` failure path; flag off is a behavioral no-op | `ca0093b` |
| T7 | Opt-in `s26-oidc-login.spec.ts` (positive + negative through the real Keycloak form, self-skips unless `E2E_OIDC=1`); SMOKE §32 | `1e3e64e` |
| T8 | Demo-reset `--demo`/`-Demo` mode (sh/ps1 parity) + fail-loud web-wait; opt-in `e2e/demo/demo-journey.spec.ts`; SMOKE §26; D-033 | `8b5e68a` |
| T9 | CI `demo` job on its own isolated runner (compose-version floor, `demo-reset --demo`, `SHIELD_DEMO_SMOKE=1` playwright, always-run diagnostics + artifact upload); SMOKE §27 | `00d970e` |
| T10 | Wrap-up: SMOKE final pass (§10/§19/§26/§27/§31/§32), CHANGELOG `[3.5.0]`, BUILD_REPORT sync, this snapshot, `context/dave.md` refresh, full gates + full e2e | `ee8bf23` |

One migration this sprint: **0032** (`users.keycloak_sub` String(64) nullable
unique, additive/SQLite-safe, C0). New DECISIONS: **D-031** (draft discard as an
admin-only soft-delete state transition), **D-032** (hybrid Keycloak SSO as a
flag-gated exchange, never a bearer), **D-033** (destructive-by-design automation
is opt-in-gated).

## Machine-local facts (this box)

- **Web runs on port 3001**, not 3000: root `.env` `WEB_PORT=3001` /
  `NEXTAUTH_URL=:3001` (a separate next-dev holds `:3000`). Playwright resolves
  the port via `e2e/helpers/baseUrl.ts` — never hardcode `:3000` in new specs.
  Canonical/CI stays `:3000`.
- **gh CLI has two accounts:** active `SpearheadAnalytica` (full write) and
  `david-catarious_kentro` (Kentro EMU — reads only; GitHub blocks EMU writes
  outside its enterprise). `gh auth switch --user <name>` to flip; `git push`
  authenticates as SpearheadAnalytica via GCM regardless.
- **Tooling not on default PATH:** `node.exe` + `gh.exe` live under
  `%LOCALAPPDATA%\Microsoft\WinGet\Packages`. Run e2e via that `node.exe` +
  `e2e/node_modules/@playwright/test/cli.js`. Docker CLI needs
  `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` per shell.
  Host Node LTS is 22 (matches the container after Sprint 4 T4).
- **Six queue gates:** `pytest -m unit`, web `tsc`, host prettier 3.9.5
  `--check`, in-container ruff/black (root-config parity), in-container web vitest
  (`pnpm -F web test`), in-container web eslint (`pnpm -F web lint`). Bandit is
  CI-only (a ruff `# noqa` does NOT suppress it — a flagged string needs its own
  `# nosec`).
- **GCP live path (Sprint 7):** live Vertex needs `SHIELD_LLM_MODE=live`,
  `SHIELD_LLM_PROVIDER=vertex`, `SHIELD_LLM_MODEL=gemini-2.5-flash`,
  `GCP_PROJECT_ID=kentro-cloudmod-dev`, `GCP_REGION=us-central1`, and host gcloud
  ADC bind-mounted read-only (`GCLOUD_CONFIG_DIR`, `%APPDATA%\gcloud` on this box)
  with `GOOGLE_APPLICATION_CREDENTIALS` pointing at the mounted file — all in the
  **gitignored** `.env`, reverted to fixture after validation. There is NO static
  Google API key anywhere. Adding `google-auth` (T0) required
  `docker compose build api` — a plain restart won't install it.
- **Framework/module reinstall dance:** after editing any `apps/web` source,
  `docker compose up -d --force-recreate web` before any e2e (next-dev hot-reload
  does not fire through the Windows bind mount). After `apps/web/package.json`
  changes (Sprint 7 Auth.js v5), reinstall INSIDE the web container. A NEW python
  module under `app/` needs `docker compose restart api`; NEVER restart api while an
  in-container pytest is running (SIGKILL 137).
- **Hybrid OIDC flag is default OFF and must never be committed on** (Sprint 9,
  D-032). `SHIELD_AUTH_OIDC_ENABLED=true` in the repo-root `.env` plus
  `docker compose up -d --force-recreate api web` (web reads it at provider
  registration, api at boot readiness) turns it on; a realm-export change since the
  last import also needs a keycloak volume wipe
  (`docker compose stop keycloak && docker volume rm shield-v2_keycloak-data && docker compose up -d keycloak`).
  The `s26-oidc-login` opt-in spec runs with `E2E_OIDC=1`; always restore the flag
  off and re-prove one credentials sign-in afterward. The realm now pins one
  canonical issuer (`http://localhost:8080/realms/shield`) for browser and
  containers via `KC_HOSTNAME` + backchannel-dynamic; the api fetches JWKS on the
  `keycloak:8080` horizon.

## Deferred / needs a human

- **SMOKE_TEST §14 / §14.1 — GCP-validated 2026-07-15 (Sprint 7 T1):** the
  opt-in `@pytest.mark.live` specs were run for real against Vertex (ADC-only)
  across all five purposes; still self-skip keyless so CI/loop stay green without
  credentials. Re-verify with a keyed/ADC run.
- **SMOKE_TEST §29 (release notification), done in Sprint 8 T2:**
  `s22-release-notify.spec.ts` now reads the notification out of MailHog for a real
  registered client of an isolated tenant, matching on recipient, subject, and the
  `/documents` link, on top of the four `test_release_notification.py` unit tests.
- **SMOKE_TEST §10 (export content) closed in Sprint 9 T2:** the five eyeball
  boxes are now unit assertions over real bytes (PDF via `pypdf.PdfReader`, DOCX via
  `docx.Document`, XLSX via openpyxl). One explicitly-manual line remains, deferred
  by design: visual aesthetics only (cell shading, heatmap colors, spacing,
  page-breaks), which no test can assert.
- **CI `demo` job green-run pending the first PR (Sprint 9 T9):** the `demo` job
  in `.github/workflows/ci.yml` is green locally (T8's destructive proving run) and
  YAML-validated, but this repo's CI triggers only on push/PR to `main`, so its
  first green CI run is cited when the dev opens the sprint PR. SMOKE §27's CI-job
  box stays annotated "pending first PR run". Same posture as the `e2e` job.
- **`sharp <0.35.0` HIGH advisory (needs Dependabot / a human):** a new root
  advisory (libvips CVEs), transitive via next@15's image optimizer, NOT introduced
  by this branch and not exploitable in our use (no untrusted image processing). Not
  fixable without a lockfile bump, which Sprint 9 deliberately did not touch.
  Recommend a Dependabot bump or a root pnpm override on `main`.
- **MFA / email web UI eyeball, done in Sprint 8 (T3 through T5):** the sign-in
  MFA step, the enrollment section, and the verify/forgot/reset pages are now
  browser-driven (`s24-mfa.spec.ts`, `s23-auth-pages.spec.ts`); the manual MFA
  walkthrough is retired.
- **Hosted-demo + demo-reset, automated in Sprint 9 (T8/T9):**
  `demo-reset --demo`/`-Demo` plus the opt-in `e2e/demo/demo-journey.spec.ts` and
  the CI `demo` job now drive the hosted-demo bring-up; the manual-only note is
  retired (the destructive proving run is opt-in-gated per D-033).
- **ESLint 10** — deferred upstream (D-018 dated deferral): no published Next lint
  stack runs on it today.
- **One documented moderate audit finding** left deliberately open: `postcss`
  8.4.31 (pinned in `next@15`; XSS-stringify path N/A at build). Clears on the next
  upstream Next bump. The npm audit HTTP endpoint 410s upstream; posture verified
  from the lockfile dependency graph.
- **Needs David (cloud infra + full federation):** `infra/terraform`
  (cloud/account/region/network) and DR runbooks are stubs; FedRAMP-authorized LLM
  connector; `azure_openai`/`bedrock`/`local` LLM adapters stay loud
  not-implemented. The Keycloak SSO deferral is LIFTED at hybrid depth (Sprint 9
  D-032): OIDC sign-in works flag-gated. Full token federation (the backend
  accepting Keycloak tokens as API bearers), JIT user provisioning, migrating
  register/MFA/email flows into Keycloak, an un-discard/recovery endpoint (DISCARDED
  is terminal in v1; rows stay DB-recoverable), and stamping local
  `email_verified_at` from a Keycloak claim all stay out of scope. Dave's 2026-07-13
  call: local containers for now.

## Test coverage status

- Backend: full `pytest -m unit` green in-container. Sprint 9 added
  `test_discard_draft.py` (the four-service discard contract: draft-only 200 +
  single audit row, idempotent re-discard, 409 on SUBMITTED/APPROVED/RELEASED, 403
  client, 404 cross-tenant, the version-trap regression, the hidden latest-consumers
  in `risk.py`/`intake.py`, and the discard-then-stale-write concurrency contracts —
  the end-of-sprint audit pass rounded the file out to full four-service symmetry:
  tech-debt child-mutation-after-discard 409, plus csf/zt idempotent re-discard);
  `test_oidc_exchange.py` (an in-test RSA keypair signs Keycloak-shaped tokens, a
  monkeypatched `_fetch_jwks` returns the matching JWKS, and the full rejection
  matrix plus TOFU sub-binding is exercised); the export-content tests (T2, real
  PDF/DOCX/XLSX bytes); and the readiness-probe cases (T5, flag-off dormant /
  flag-on ok/down, `ready` never gated by keycloak). Sprint 7's Vertex adapter and
  release-notification suites and the opt-in `tests/live/test_live_ai.py`
  (`@pytest.mark.live`, excluded from `-m unit`, GCP-validated 2026-07-15) are
  unchanged.
- Web unit tests: `pnpm -F web test` (vitest) 37/37 across 10 files. Sprint 9 T1
  added `DiscardDraftButton.test.tsx` (renders only for a draft, opens the Modal,
  confirm invokes the callback, cancel/ESC/backdrop are no-ops) and `CsfWorkspace`
  discard tests (the answered-count warning line, plus the end-of-sprint audit pass's
  onDiscard main-path test: confirm → `discardAssessment` → guarded refetch clears the
  workspace to the empty state); T6 added `oidc.test.ts` (isOidcEnabled truth table + rewrite/passthrough),
  `KeycloakSignInButton.test.tsx`, and `SessionExpiryGuard.test.tsx` (signs out on
  `OIDC_EXCHANGE_ERROR`). The Sprint-8 `SignInForm` omit-totp guard and the reqSeq
  guards remain.
- Web `tsc --noEmit` clean on Next 15 / React 19 / Tailwind 4 / Auth.js v5. ESLint
  0 errors (1 pre-existing postcss warning). In-container `pnpm -F web build` was
  proven green in T6 (the standalone prod image the demo compose runs).
- e2e: 27 spec files (host, resolves `:3001`). Sprint 9 added `s26-oidc-login`
  (opt-in, self-skips unless `E2E_OIDC=1`) and `demo/demo-journey` (opt-in,
  self-skips unless `SHIELD_DEMO_SMOKE=1`), so the default suite count is unchanged.
  The T10 exit run was green on the flag-off dev stack: 51 passed / 6 skipped (2
  s26 + 4 demo-journey), zero failures/flakes, across six foreground sub-9-min
  shards. Known cold-compile flake under load documented in `CLAUDE.md`; per-spec
  standalone is the flake arbiter.
- Format: repo-wide prettier `--check` clean at 3.9.5. Python ruff/black clean
  (root-config parity).
- Audit: bandit CI-only, exit 0. Root `pnpm audit` posture: one new documented
  `sharp <0.35.0` HIGH (libvips CVEs, transitive via next@15's image optimizer, not
  branch-introduced, not exploitable in our use) plus the standing `postcss`
  moderate; both blocked on a lockfile bump this sprint did not touch (Dependabot /
  root override on `main`). The `uuid@8.3.2` moderate cleared in Sprint 7 T5. No
  secret / token committed this sprint (the secret-less PKCE client meant the T6
  dev-realm fallback secret was never needed).

## Lessons learned (Sprint 9)

- **Activating a state means auditing every reader, not just the writer.** Adding
  `DISCARDED` was the easy part. Codex's two blockers were both hidden consumers:
  the risk-register synthesis has its own `_latest()` that would have read a
  discarded highest-version assessment straight into the gate, and the intake
  engagement cards reported the raw latest version. A dormant status is only as safe
  as the query that forgot about it. The rule that fell out: when a new row state
  goes live, grep for every "latest" and every parent-state guard across the whole
  codebase, not just the four route files that mint the state.
- **The version trap is a real IntegrityError, not a hypothetical.** The
  `_latest_*` helpers must skip `DISCARDED` (so a discarded draft is invisible to
  consumers) while the mint's next-version computation must read `max(version)`
  unfiltered (so it does not reuse the discarded version's number and collide on the
  `(service_id, version)` unique constraint). Getting the second half wrong throws
  on the first re-extract after discarding a non-v1 draft. The regression test runs
  on an alembic-upgraded SQLite fixture precisely so the unique constraint is real,
  not mocked away.
- **A mocked unit test cannot prove a flag-off no-op or a beta integration.** T6's
  hardest promise was that flag-off changes nothing, and the only honest proof is a
  vitest trap that fails on an unexpected Keycloak fetch. The throwaway auth-code
  spike then caught a bug no unit mock could: a rejected exchange left the token
  without an access token, so the next `jwt` call fell into `refreshAccessToken()`
  and clobbered `OIDC_EXCHANGE_ERROR` into `RefreshAccessTokenError`, and the guard
  never fired. Making the error terminal in the callback fixed it. Beta-sensitive
  seams need a real round trip before the full wiring, so the verdict lands early.
- **Fail loudly at the wait, not at the far-downstream death.** The demo-reset web
  poll printed its success banner even on a 120s timeout, so a stalled production
  build looked like a clean reset until Playwright died opaquely much later. Moving
  the failure to the wait (non-zero exit plus a `docker compose logs web` dump)
  turns a confusing downstream symptom into an obvious local cause.
- **Changing a shared default in one task silently breaks another task's hardcoded
  fixture, and the final full-suite gate is where it surfaces.** T5 flipped the
  canonical Keycloak issuer to `http://localhost:8080/realms/shield`; T4's
  `test_oidc_exchange.py` had baked in the pre-T5 `keycloak:8080` issuer and leaned
  on the config default, so every happy-path case started failing with an issuer
  mismatch the catch-all message masked. The running system stayed correct
  throughout (T7's live `s26` exchange proved it end to end); only the unit fixture
  lagged. Fixing it was correcting a stale constant, not weakening a check. The
  lesson: when a task changes a default other tests read implicitly, re-run the full
  `-m unit` suite, not just the touched file, and the wrap-up exit run is the
  backstop that catches what per-task gates missed.

## Lessons learned (Sprint 8)

- **A flow that unit tests call green can be broken for every real user.** MFA
  sign-in passed `pytest -m unit` and a Sprint-7 vitest, yet the TOTP field never
  appeared in a browser. The cause sat three layers deep: `SignInForm` sent
  `totp: undefined`, next-auth serializes credentials through `URLSearchParams`,
  and `URLSearchParams` stringifies `undefined` to `"undefined"`, so the backend
  `!totp` guard saw a truthy value and verified a bogus code. The vitest could not
  catch it because it mocks `signIn()` and never runs the real serialization. Only
  a spec driving the actual browser through the real client library exposed it.
  That is the thesis of this sprint, proven the hard way.
- **Send the key only when you have a value.** The fix was one line,
  `...(totp ? { totp } : {})` in place of always passing `totp`. A default of
  `undefined` is not the absence of a field once it crosses a string-serializing
  boundary; the silent coercion made a broken auth path look like a routine
  bad-password rejection.
- **Idempotency belongs before the expensive side effect, not at the write.** The
  tech-debt extract guard had to sit before `extract_capabilities()`, not at the
  version-mint site, or a double-click would still fire the LLM call it was meant
  to prevent. Guarding at the cheapest correct point is the difference between a
  fix and a half-fix (Codex flagged exactly this in the plan review).
- **On an overload-prone box, the per-spec standalone run is the flake arbiter.**
  Full-suite e2e here repeatedly failed on cold-compile sign-in timeouts under
  load while every spec passed alone. A spec that dies at `auth.ts` sign-in under
  load is a documented load flake, never a logic bug; the authoritative full run
  is the quiet-box shutdown checkpoint.

## Lessons learned (Sprint 7)

- **"Feasible with curl" is not "works through the adapter."** T0's Vertex path
  was proven by a raw ADC `generateContent` curl, but the first live sweep (T1)
  still found two defects a keyless unit test could never hit: `google-auth`'s
  token-refresh transport needs the `[requests]` extra (the unit test mocked
  `_bearer_token`, so it never exercised the real transport), and gemini-2.5
  "thinking" ate the output budget and truncated JSON. A real end-to-end sweep is
  the only thing that exercises the transport and the model's real output shape.
- **A silent "completed" on a truncated response is a lie.** `_parse_generate_content`
  returned a half-JSON draft as "completed" and it died downstream as an opaque
  `JSONDecodeError`. The fix is to fail LOUDLY at the seam: any non-`STOP`
  `finishReason` now raises and marks the `llm_call` failed with the real reason.
- **The token rides the header, not the URL.** The Vertex bearer token is sent as
  an `Authorization` header so an `HTTPStatusError` (which embeds only the request
  URL) cannot leak it into logs or `llm_calls.error_message` — mirroring the
  Gemini key-in-header lesson, and unit-locked.
- **Best-effort side effects must not roll back durable state.** A
  release-notification SMTP failure is logged loudly but the release still stands
  — the release is the source of truth. "Fail loudly" means surface the failure,
  not undo the thing the user already asked for.
- **A major auth dep bump is behavior-preservation work, not a feature.** The
  Auth.js v5 migration touched 34 call sites and re-wired the MFA signal (v5
  normalizes every credentials failure to `CredentialsSignin`, so the MFA branch
  surfaces via `signIn(...).code`, not `.error`). The bar was every auth e2e green
  and not one weakened test.
