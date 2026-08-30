# SHIELD v3.0 — Build Report

> Live build status. The single-page snapshot of what is built, what gates it,
> and what is deferred. Narrative history lives in `CHANGELOG.md`; non-obvious
> choices in `DECISIONS.md`; state-of-`main` in `CONTEXT.md`.

## Latest change — 2026-08-07 (UX findings burn-down complete, `[3.10.0]`)

**Both outstanding review documents are closed out.** `UX findings.docx` (22
numbered findings plus its "Recommended page structure" appendix) and the
2026-08-04 guided live run (`REPORT.md`, F-1..F-12) are fully burnt down across
PRs #5, #6, #9-#12 and #14-#21. New DECISIONS **D-042/D-043/D-044**. **No
migrations in Phase C or D** — the one new read surface derives its states from
columns that already existed.

The finding → PR mapping lives in `CONTEXT.md` under "UX findings burn-down".
Do not re-derive it; establishing it required a pass through PR #6's
change→finding table plus the migration history, and it corrected two
assumptions (UX 5 and UX 4's review-queue half had already shipped, and F-10 was
**withdrawn** as a measurement artifact of the review harness rather than fixed).

Highlights:

- **One client-facing results surface (D-042).** `/results` replaces
  `/documents`, which permanently redirects and stays — release emails already
  delivered carry the old path.
- **Client Home by ownership (D-043).** Action required / In progress / Results
  available, one bucket per service, each card naming one primary action. That
  single placement is what removed a duplication rather than patching it: an open
  self-assessment used to render both as a card and in a "Waiting on you" list.
  The six-stage bar deliberately stays admin-only (§6.4).
- **Admin Deliverables (D-044).** Every deliverable for the active tenant,
  released or not — the admin-side twin of the problem `/results` fixed for
  clients. Derived status, superseded beats released, read-only.
- **Admin queue filters, Risk Register scope, and `/help`**, closing the IA
  appendix. Two long-standing gaps from the 2026-07-08 repo audit —
  `/admin/deliverables` and `/help` — are now built.
- **Test integrity.** `s34`'s Run-AI-guard test could self-skip on database
  state, which is what hid the fail-open race it guards; it now seeds its own
  tenant and the skip is an assertion. Verified by forcing the old condition and
  watching it fail where it used to report green.

Gates on `main` (`741b1e9`): full CI green — Python, Web, gitleaks, E2E,
Demo — plus local `pytest -m unit` 807/807 and vitest 116/116.

## Overall status

**`v3.0.0` shipped (PR #1, v2 work order Parts A–F). Sprints 1–9 all merged.
Since Sprint 9 the work has been review-driven rather than sprint-planned — the
seven-issue pass, then the UX findings burn-down, which completed at `[3.10.0]`
on 2026-08-07; no sprint is currently staged. The live-AI path is proven against
real Vertex AI via ADC with no static key (Sprint 7 D-029); the client
release-notification loop is closed (D-030) and the web auth stack is on Auth.js
v5. Sprint 9 activates the long-dormant Keycloak seam as a hybrid OIDC sign-in
(flag-gated, default off, D-032, migration 0032), adds a first-class draft-discard
affordance to all four services (D-031), and puts the demo compose and export
eyeballs under committed automation (D-033). Cloud infra (terraform, FedRAMP LLM
connector) and full Keycloak token federation remain blocked on David's
cloud/account/region decisions.**

| Milestone                                                                           | Status                     | Reference                          |
| ----------------------------------------------------------------------------------- | -------------------------- | ---------------------------------- |
| Phase 1 — Foundation (`v0.1.0`)                                                     | Complete                   | CHANGELOG (earlier history)        |
| Phase 2 — Intake (`v0.2.0`)                                                         | Complete                   | CHANGELOG (earlier history)        |
| Phase 3 — Tech Debt service (`v0.3.x`)                                              | Complete                   | CHANGELOG (earlier history)        |
| v2 work order Parts A–F (`v3.0.0`, migrations 0015–0025)                            | **Complete (PR #1)**       | DECISIONS D-021 (Part F)           |
| Sprint 1 — smoke sweep (`qa/smoke-sweep-sprint-1`, PR #16)                          | **Complete**               | `SPRINT_1.md`                      |
| Sprint 2 — findings burn-down (`fix/findings-burndown-sprint-2`)                    | **Complete (PR #19)**      | `SPRINT_2.md`, CHANGELOG `[3.0.2]` |
| Sprint 3 — audit correctness & honesty (`fix/audit-correctness-sprint-3`)           | **Complete (PR #26)**      | `SPRINT_3.md`, CHANGELOG `[3.0.3]` |
| Sprint 4 — framework majors + multi-provider LLM (`feat/majors-providers-sprint-4`) | **Complete (PR #28)**      | `SPRINT_4.md`, CHANGELOG `[3.1.0]` |
| Sprint 5 — client value loop (`feat/client-value-loop-sprint-5`)                    | **Complete (PR #31)**      | `SPRINT_5.md`, CHANGELOG `[3.2.0]` |
| Sprint 6 — real demo (`feat/real-demo-sprint-6`)                                    | **Complete (PR #33)**      | `SPRINT_6.md`, CHANGELOG `[3.3.0]` |
| Sprint 7 — GCP live path + close the client loop (`feat/gcp-vertex-sprint-7`)       | **Complete (PR #36)**      | `SPRINT_7.md`, CHANGELOG `[3.4.0]` |
| Sprint 8 · prove it in the browser (`feat/browser-proof-sprint-8`)                  | **Complete (PR #42)**      | `SPRINT_8.md`, CHANGELOG `[3.4.1]` |
| Sprint 9 · activate the seam (`feat/sso-discard-demo-sprint-9`)                     | **Complete (this branch)** | `SPRINT_9.md`, CHANGELOG `[3.5.0]` |
| Infra (cloud terraform, FedRAMP LLM connector)                                      | **Blocked (needs-David)**  | `DELIVERY_PLAN.md`                 |

## Product surface at `v3.0.0`

- **Four assessment services:** Technical Debt Review, Zero Trust (CISA ZTMM 2.0
  - DoD ZTRA), NIST CSF 2.0 (10-step Playbook), MITRE ATT&CK coverage (full
    Enterprise matrix per D-007).
- **Risk Register** (5×5 NIST 800-30) synthesized from the four services; tier
  is code-derived, never prompted.
- **Multi-tenant** consultant-led onboarding (shared DB + `client_id`, D-015).
- **AI job registry** behind the single redacting egress client (`app/ai/llm.py`);
  fixture-mode is fully offline + deterministic (D-017). "AI suggests, code
  computes" — deterministic engines own every total/tier/roll-up.

## Current gate set

The repo-wide gates enforced this sprint (and encoded in the sprint queue):

| Gate                  | Command                                                                                                                  | Where                 |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------ | --------------------- |
| Backend unit tests    | `docker compose exec -T api pytest -m unit -q`                                                                           | api container         |
| Web typecheck         | `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`                                           | web container         |
| Web unit tests        | `docker compose exec -T web sh -lc "cd /app && pnpm -F web test"` (vitest, Sprint 5 T8; Sprint 6 added HealthMatrix)     | web container         |
| Web eslint            | `docker compose exec -T web sh -lc "cd /app && pnpm -F web lint"` (in the queue gate set, Sprint 6)                      | web container         |
| Full e2e smoke suite  | `cd e2e && npx playwright test` (27 spec files; Sprint 9 added s26-oidc-login and demo/demo-journey, both self-skipping) | host → composed stack |
| Runtime axe WCAG A/AA | `s16-axe.spec.ts` (part of the suite)                                                                                    | host → composed stack |
| Python lint/format    | `docker compose exec -T api sh -lc "ruff check --no-cache . && black --check ."` (root-config parity, Sprint 4 T0)       | api container         |
| Repo format           | `npx -y prettier@3.9.6 --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"`                                                  | host                  |
| Dependency audit      | `pnpm audit` (root) / `npm audit` (`e2e/`)                                                                               | host                  |

### CI jobs (`.github/workflows/ci.yml`)

Five jobs gate every push / PR to `main`:

1. **python** — ruff, black, bandit, `pytest -m unit`.
2. **web** — prettier, eslint (incl. static `jsx-a11y`), tsc, `next build`.
3. **secret-scan** — gitleaks.
4. **e2e** _(Sprint 2 T3)_ — `docker compose up`, fail-loud health waits
   on `:8000` + web, seed, `npm ci` + chromium, `playwright test` (includes the
   axe sweep), `always()` upload of `playwright-report/` + `test-results/`,
   30-min timeout.
5. **demo** _(new Sprint 9, T9)_ — on its own isolated runner (its `down -v`
   cannot touch the e2e job): logs `docker compose version` and hard-fails below
   2.24 (the `!reset` floor), runs `bash scripts/demo-reset.sh --demo` (builds
   `shield-web:demo`, seeds inside the script), then
   `SHIELD_DEMO_SMOKE=1 npx playwright test demo/`, with always-run compose-ps/logs
   diagnostics and an `if: always()` artifact upload under a unique name; 25-min
   timeout, triggers shared with e2e (push + PR to `main`).

> **CI-proof note (honesty):** the `e2e` and `demo` jobs' first real runs need
> the review-required branch push, which is Dave-manual, so their green runs are
> cited on the sprint PR open. The `demo` step block was proven locally end-to-end
> (Sprint 9 T8's destructive proving run), and the YAML validated
> (5 jobs, `demo` runs-on ubuntu-latest, 9 steps in order).

## Gate results at HEAD (Sprint 9 close)

```
pytest -m unit         → green (in api container; Sprint 9 T0 added test_discard_draft.py, T2 the export-content tests, T4 test_oidc_exchange.py + config boot cases, T5 the readiness probe cases)
web tsc --noEmit       → clean (Next 15 / React 19 / Tailwind 4; Auth.js v5)
web vitest (pnpm test) → green 36/36 (10 files, in web container; Sprint 9 T1 added DiscardDraftButton + CsfWorkspace tests, T6 the oidc/button/guard suites)
web eslint (pnpm lint) → 0 errors (1 pre-existing postcss warning)
prettier --check       → clean (3.9.5, repo-wide; the T10 docs-only gate run)
ruff / black --check   → clean (root-config parity)
e2e (host)             → 27 spec files; the full default suite (flag-off dev stack) re-run green in six foreground sub-9-min shards: 51 passed / 6 skipped (2 s26-oidc-login + 4 demo/demo-journey self-skip), zero failures/flakes. This box is overload-prone, so per-spec standalone is the flake arbiter (a cold-compile sign-in timeout under load is a documented flake, not a logic failure)
```

(Exact figures recorded in the T10 wrap-up commit / CONTEXT.md. The machine running
this sprint serves web on **:3001**; Playwright resolves the port via
`e2e/helpers/baseUrl.ts`, canonical/CI is `:3000`.)

## OWASP Top 10 cumulative review (through Sprint 6, `v3.3.0`)

| ID  | Category                  | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| --- | ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A01 | Broken Access Control     | PASS — `current_user` + `require_role`; multi-tenant `X-Client-Id` scoping returns 404 on cross-tenant access (no existence oracle); admin layout double-checks server-side. Sprint 5: the client deliverable list + artifact download are released-only and tenant-scoped (404, never 403; unit-tested deny matrix); `/admin/audit` read routes and `/ai/preview` are admin-only                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| A02 | Cryptographic Failures    | PASS — Argon2id + HS256 JWT; placeholder secret refused in prod; sha256 on every upload; S3 SSE=KMS in prod                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| A03 | Injection                 | PASS — SQLAlchemy parameterized queries only; app-generated storage keys; filename sanitization                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| A04 | Insecure Design           | PASS — append-only audit log (two layers); MIME allowlist + size cap; redaction disclosure before upload; explicit service-request lifecycle                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| A05 | Security Misconfiguration | PASS — `assert_safe_for_runtime`; HSTS + CSP + X-Frame-Options + Permissions-Policy + Referrer-Policy at the edge (asserted by `s15-headers.spec.ts`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| A06 | Vulnerable Components     | PASS WITH NOTES — pip-audit + `pnpm audit` in CI, Dependabot opens fix PRs; on the Next 15 / React 19 / Tailwind 4 / ESLint 9 / Node 22 stack (Sprint 4). Sprint 7 T5's Auth.js v5 migration removed the `uuid@8.3.2` moderate (`uuid` no longer in the lockfile). Two root advisories are now documented and deferred (both blocked on a lockfile bump this sprint deliberately did not touch): `sharp <0.35.0` **HIGH** (libvips CVEs), transitive via next@15's image optimizer and NOT introduced by this branch, and `postcss` 8.4.31 moderate (pinned in next@15, XSS-stringify path N/A at build). Neither is exploitable in our use; both clear on a Dependabot bump or a root pnpm override on `main`. (The npm audit HTTP endpoint 410s upstream; posture verified from the lockfile dependency graph.) |
| A07 | ID & Auth Failures        | PASS WITH NOTES — email+password + Argon2id + lockout + account-existence oracle defense + typed reg errors (D-016); refresh-token rotation (replay rejected) + daily forced-reauth ceiling (`auth_time` claim, typed 401) + 30-min refresh TTL as idle timeout. **Sprint 6: real TOTP MFA (D-027, RFC 6238, encrypted secret at rest, single-use recovery codes, second-factor failures feed account lockout) and real email verification + password reset (D-028, hashed single-use time-bounded tokens, enumeration-safe) now SHIP** — the D-020 flags gate enforcement instead of refusing boot. Keycloak SSO cutover remains a needs-David deferral                                                                                                                                                          |
| A08 | Software & Data Integrity | PASS — audit rows immutable by contract; sha256 stored + audited on upload                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| A09 | Logging & Monitoring      | PASS — structured JSON + correlation IDs; audit + notification fan-out on state change; `llm_calls` rows record redacted-count only. Sprint 5: the append-only `audit_entries` + `llm_calls` stores gained their first read surface (`/admin/audit`, admin-only, read-only, correlation-linked) — the trail is now reviewable, not just written                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| A10 | SSRF                      | PASS — LLM endpoint env-configured only; no user-supplied URLs                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

## Open items / deferred (needs-David or a future sprint)

0. **UNPROVEN, and the most important item here: the live Anthropic path for
   `zt_score`, `csf_score` and `mitre_map`.** The 2026-08-04 live run
   (`REPORT.md`) never completed CSF or MITRE scoring, and F-3 records that Zero
   Trust could not complete on live Anthropic at all — a non-streaming request
   ran too long and the connection was dropped. PR #6 added streaming to answer
   that, but **nothing has re-proven those three purposes on Anthropic since**.
   Sprint 7's live validation (2026-07-15) was **Vertex/Gemini**, a different
   adapter with a different failure mode. On the default provider exactly one
   purpose (`extract.capabilities`) has ever completed live, and that predates the
   streaming change. Needs a human with a real key; SMOKE §14 and §36 both want
   it. Treat "live Anthropic works" as unproven until a run says otherwise.
1. **SMOKE_TEST §27 — CI `demo` job pending its first PR run:** the new `demo`
   job is green locally (Sprint 9 T8's destructive proving run) and the YAML is
   validated, but this repo's CI triggers only on push/PR to `main`, so its first
   green CI run is cited on the sprint-PR open per the honesty convention. Same
   posture as the `e2e` job.
2. **`sharp <0.35.0` HIGH advisory (needs-David / Dependabot):** a new root
   advisory (libvips CVEs), transitive via next@15's image optimizer, NOT
   introduced by this branch and not exploitable in our use (no untrusted image
   processing). Not fixable without a lockfile bump, which Sprint 9 deliberately
   did not touch. Recommend a Dependabot bump or a root pnpm override on `main`.
   The `postcss` 8.4.31 moderate sits in the same bucket (clears on the next
   upstream Next bump).
3. **Full Keycloak token federation / JIT provisioning (needs-David):** Sprint 9
   activated the hybrid OIDC exchange (D-032) but deliberately stopped short of
   the backend accepting Keycloak tokens as API bearers, JIT user provisioning,
   and migrating register/MFA/email flows into Keycloak. An un-discard/recovery
   endpoint (DISCARDED is terminal in v1; rows stay DB-recoverable) and stamping
   local `email_verified_at` from a Keycloak `email_verified` claim are also
   deferred.
4. **SMOKE_TEST §10 aesthetics line** — the one explicitly-manual box that
   remains after Sprint 9 T2 replaced the five export eyeballs with content
   assertions: maturity/level cell shading, heatmap colors, spacing, and
   page-breaks (values are asserted; layout and color are not).
5. **SMOKE_TEST §14 / §14.1 — GCP-VALIDATED 2026-07-15 (Sprint 7 T1):** the
   live-AI opt-in specs were run for real against Vertex AI (`vertex`/
   `gemini-2.5-flash`, ADC-only) across all five purposes; redacted `llm_calls`
   row, no PII, per-adapter response parse all confirmed. The specs still self-skip
   keyless, so CI/loop stay green without a key; a keyed/ADC re-run re-verifies.
6. **Cloud infra (needs-David):** `infra/terraform` (AWS GovCloud / Azure Gov,
   needs account/region/network decisions), FedRAMP-authorized LLM connector, DR
   runbooks. Sprint 6 T9 plus Sprint 9 T8/T9 deliver only a local hosted-demo
   compose and its CI proof, not cloud provisioning. See `DELIVERY_PLAN.md`.
7. **Standing upstream-blocked items:** ESLint 10 (no published Next lint stack
   runs on it, D-018); `azure_openai`/`bedrock`/`local` LLM adapters (loud
   not-implemented until a deployment needs one).

## Significant decisions

See [`DECISIONS.md`](DECISIONS.md) for the full log. Highlights:

- **D-007 (FLIPPED):** ATT&CK uses the full Enterprise matrix (~600 techniques).
- **D-015:** Multi-tenant shared DB with `client_id` on every row. **D-021:**
  Part F harden-and-ship posture (renumbered from a duplicate D-015 heading,
  erratum D-022).
- **D-016 / D-017:** typed registration errors; offline deterministic
  fixture-mode AI.
- **D-019:** reject reserved/special-use TLDs at domain-approval time
  (renumbered from D-018 this sprint to avoid a collision with the unmerged
  `chore/dependabot-policy` branch, which owns D-018).
- **D-026 / D-024 / D-017:** live-AI enablement + boot preflight; multi-provider
  LLM egress; offline deterministic fixture mode.
- **D-029 (Sprint 7):** Vertex AI via Application Default Credentials as the GCP
  live path — a `vertex` provider with no static key, ADC-authenticated, token
  never logged. **D-030 (Sprint 7):** client release-notification email —
  best-effort notify, the release is the source of truth.
- **D-031 (Sprint 9):** draft discard is an admin-only soft-delete state
  transition (`DISCARDED`), with a conditional-UPDATE concurrency contract so a
  racing child write loses loudly. **D-032 (Sprint 9):** hybrid Keycloak SSO is a
  flag-gated token exchange at `POST /auth/oidc/exchange`, never a bearer; local
  HS256 JWTs stay authoritative and there is no JIT provisioning. **D-033
  (Sprint 9):** destructive-by-design automation is opt-in-gated — reset specs
  self-skip, destructive scripts never run implicitly, CI isolation is the only
  unattended venue.

## How to resume

Read `BUILD_REPORT.md` (this file), `CONTEXT.md`, the last `git log --oneline
-15`, `CHANGELOG.md`, and `DECISIONS.md`. The sprint loop's machine-local facts
(port 3001, tool paths, gh read-only posture) live in
`.claude/sprint-queue.json` `scratch` and `CONTEXT.md`.
