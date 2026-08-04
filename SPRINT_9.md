# SPRINT 9 — Activate the seam (hybrid SSO + discard affordance + demo automation)

_Branch: `feat/sso-discard-demo-sprint-9` (cut from `main` post-#42). Queue:
`.claude/sprint-queue.sprint-9.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron` (or execute tasks by hand). Created
2026-07-21 after Sprint 8 (PR #42, `v3.4.1`) merged._

_Plan reviewed by OpenAI Codex (v0.144.5, read-only, 2026-07-21) — initial
verdict "rework" on 12 findings (2 blockers: the risk-register synthesis reads
discarded rows through its own `_latest()`; discard needs a concurrency
contract, not just state checks). ALL 12 findings folded into the tasks below;
the findings table is in the planning PR body._

## Why this sprint exists

Three debts have been carried sprint over sprint, and each is now the oldest
item of its kind:

1. **The Keycloak seam has been dormant since day one.** The realm export, the
   `aud=shield-api` claim alignment, and the config keys were built in v2 Part A
   precisely so SSO could be activated later without a schema migration — but no
   OIDC code exists anywhere: no provider in `options.ts`, no RS256 path in the
   backend, a hardcoded `dormant` health probe. "Later" is now, at **hybrid
   depth**: Keycloak authenticates, the backend keeps minting its own JWTs
   (D-020 stays authoritative), and the Credentials + MFA (D-027) + email
   verify/reset (D-028) stack stays fully intact beside it, flag-gated default
   OFF.
2. **No service has a way to intentionally re-extract a draft.** Sprint 8 T1
   finished porting the idempotent draft-reuse guard to all four services —
   which also means a consultant with a botched draft must APPROVE it (lying
   about its quality) to mint a fresh one. Three e2e specs literally encode that
   workaround (`s4`/`s5`/`s11` approve-any-open-draft preambles). The missing
   affordance is a first-class discard.
3. **The demo surface and the export eyeballs are still human-verified.**
   `docker-compose.demo.yml` and `scripts/demo-reset.*` have never been driven
   by a committed spec (SMOKE §26/§27 are manual-only), and SMOKE §10's export
   checks are five boxes ticked off a human review dated 2026-07-09 — s7/s8
   assert HTTP transport, never content. XLSX content assertion is already a
   solved pattern (openpyxl); DOCX has an installed-but-unused reader
   (python-docx); PDF needs one new test dep (pypdf).

## Sprint goal

A user can sign in through Keycloak (flag on) and land with working backend
tokens while every existing auth path is untouched (flag off is a behavioral
no-op: the provider is absent, zero Keycloak network calls happen, every
credential surface is unchanged); an admin can discard an open draft in any of
the four services and mint
a fresh one without the approve-first lie; the demo compose + reset script are
proven by a committed spec and a CI job; the export eyeball debt is replaced by
content assertions over real bytes.

Version at close: **`3.5.0`** (minor: new flag-gated user-facing surface —
OIDC sign-in + the discard affordance). Tag/CHANGELOG-level only; package
manifests are NOT touched.

**New decisions this sprint (append in the tasks that make them):**
**D-031** — draft discard is an admin-only soft-delete state transition (T0).
**D-032** — hybrid Keycloak OIDC: exchange-at-the-edge, local JWTs stay
authoritative (T4). **D-033** — destructive-by-design automation is
opt-in-gated (T8). One migration: `0032_user_keycloak_sub` (T4, additive).

## Prerequisites / launch checklist

1. Merge this planning PR.
2. `git checkout -b feat/sso-discard-demo-sprint-9 main` BEFORE the first fire.
3. Archive the old runtime queue if one exists on your box, then COPY
   `.claude/sprint-queue.sprint-9.json` to `.claude/sprint-queue.json`; set
   `working_dir` + `expected_gh_user` for YOUR box; confirm the `gates` array
   matches your environment (six gates unchanged from Sprint 8).
4. The human dev launching this sprint runs `/loop-sprint-cron` themselves —
   agents do NOT start the loop.
5. No live-AI or cloud credentials needed. Keycloak runs in the dev compose
   already; `SHIELD_AUTH_OIDC_ENABLED` stays **false** for the default suite
   and is flipped only inside T6 (hand-verify) / T7 (opt-in e2e), then restored.

## Environment facts the loop must know

All CLAUDE.md gotchas hold, plus:

- **Realm-export edits need a Keycloak volume wipe to take effect** —
  `start-dev --import-realm` skips a realm that already exists. Procedure:
  `docker compose stop keycloak`, `docker volume rm <project>_keycloak-data`,
  `docker compose up -d keycloak`. Applies to T5 and any realm fix after it.
- **`scripts/demo-reset.*` is destructive** (`docker compose down -v` — nukes
  Postgres/MinIO/Redis/Keycloak volumes). Never run it implicitly. T8's local
  proving run is scheduled late for this reason, and MUST reseed the dev stack
  afterward (`seed_demo.py` is part of the script; verify `/ready` + one
  sign-in before moving on).
- **New pytest dep (pypdf, T2) requires `docker compose build api`** — a plain
  restart won't install it (the Sprint 7 `google-auth` lesson). Same for any
  pyproject change.
- **New python modules (`app/security/oidc.py`, `app/routes/oidc.py`, T4) need
  `docker compose restart api`** (uvicorn --reload may miss new files). Never
  restart api mid-pytest (SIGKILL 137).
- **Migration 0032 (T4):** apply in-container (`docker compose exec -T api
  alembic upgrade head`) before any e2e that signs in; unit tests build their
  own SQLite schema.
- **Flipping `SHIELD_AUTH_OIDC_ENABLED` requires recreating BOTH containers**
  (`docker compose up -d --force-recreate api web`) — the web reads it at
  provider-registration time, the api at boot readiness. Restore flag-off and
  re-prove one credentials sign-in before ending any task that flipped it.
- **Every new spec must self-skip by default.** Playwright `testDir` is `"."`
  under `e2e/`, so anything committed there runs in the default suite unless
  guarded: `s26-oidc-login` skips unless `E2E_OIDC=1`; `demo/demo-journey`
  skips unless `SHIELD_DEMO_SMOKE=1`. Prove the skip (suite count unchanged)
  before writing assertions.
- After ANY `apps/web` source edit: `docker compose up -d --force-recreate web`
  before e2e (T1/T6 touch web; the dance applies).
- Playwright traps (recurring): `getByRole` name matching is SUBSTRING;
  `click()` + `waitForResponse` on auto-save controls; assert post-action state
  after `page.reload()`; spec-created users need unique timestamped emails.

## Tasks

### T0 — Backend: discard endpoints ×4 + `DISCARDED` status + version fix (D-031)

- New route per service, mirroring each `/{id}/approve` sibling byte-for-byte
  in layout/RBAC/audit shape (all four are `_admin_required`):
  `POST /tech-debt/capability-lists/{list_id}/discard`,
  `POST /csf/assessments/{assessment_id}/discard`,
  `POST /attack/assessments/{assessment_id}/discard`,
  `POST /zt/assessments/{assessment_id}/discard`.
- Add `DISCARDED` to all four status enums (`capability.py`,
  `csf_assessment.py`, `attack_assessment.py`, `zt_assessment.py`). These are
  `native_enum=False` → plain `String(16)` columns with **no CHECK constraint**
  (verified against migration 0009) — code-only, **no migration**.
- State rules, every rejection a typed D-016 dict-detail:
  - `DRAFT` → 200, serialized resource with `status="discarded"`, audit row.
  - `DISCARDED` again → idempotent 200, **no second audit row**.
  - `SUBMITTED` (CSF/ZT) → 409 `{reason: "not_discardable"}` — once a client
    formally submits, destruction is off the table.
  - `APPROVED`/`RELEASED` → 409 `not_discardable`.
  - Unknown id / wrong tenant → 404 (mirror approve's tenant check);
    client-role POST → 403 via `require_role`.
  - Client-touched CSF/ZT **drafts** ARE discardable (Dave's call) — the UI
    warns with the answered-row count (T1); the API allows it.
- **The version trap (regression test is mandatory):** every `_latest_*`
  helper (`tech_debt.py:121`, `csf.py:185`, `attack.py:141`, `zt.py:175`)
  gains `status != DISCARDED` — covering the reuse guard, GET latest, and all
  downstream consumers — but the mint's next-version computation
  (`tech_debt.py:222`, `csf.py:391`, `attack.py:274`, `zt.py:555`) switches to
  a dedicated `select(func.max(version))` **without** the filter, because of
  the `(service_id, version)` unique constraints. Test: v1 approved → v2 draft
  → discard v2 → mint = **v3**, no `IntegrityError`, on the alembic-upgraded
  SQLite fixture so the constraint is real.
- **Hidden "latest" consumers outside the four route files (Codex blocker +
  should-fix):** the risk-register synthesis has its OWN generic `_latest()`
  (`risk.py:65-78`) feeding `_gate()`/`_gather_findings()` (`risk.py:125-162`)
  — it must also skip DISCARDED, or a discarded highest-version assessment
  still unlocks the gate and supplies findings. Regressions: finalized v1 +
  discarded v2 → synthesis reads v1; a discarded-only service does NOT unlock
  the gate. Same for the client engagement-status cards
  (`intake.py:299-306`, `:326`): rule is "latest non-discarded", tested for
  discarded-only and finalized-v1/discarded-v2.
- **Child mutations must reject a discarded parent (Codex should-fix):** audit
  every by-row-ID mutation and AI-run guard across the four services (e.g.
  `zt.py:639-652`, `attack.py:480-487`) — several only reject
  approved/released, which would accept a DISCARDED parent from a stale tab.
  Rule becomes "parent must be in its editable state(s)", not "not
  approved/released". Stale-tab PATCH-after-discard tests for all four
  services.
- **Concurrency contract (Codex blocker):** the discard write is a conditional
  `UPDATE ... WHERE status = 'draft'` (rows-affected check drives the
  200/idempotent/409 branch) so two transactions cannot both observe DRAFT and
  proceed; combined with the child-writer parent-state guards above, a client
  answer PATCH or an AI run racing a discard loses loudly (typed 409) instead
  of writing into a discarded parent. An AI run that already loaded a DRAFT
  parent re-checks parent status before committing its rows. Contract tests
  cover discard-then-stale-write per service.
- Audit rows (dotted convention): `capability_list.discarded`,
  `csf.assessment.discarded`, `attack.assessment.discarded`,
  `zt.assessment.discarded` — details `{service_id, version, item_count /
  answer_count, answered_count}` (csf/zt: rows carrying any client data).
  Success-path logs: `techdebt_discarded_draft`, `csf_assessment_discarded`,
  `attack_assessment_discarded`, `zt_assessment_discarded`.
- tech_debt: uploaded intake artifacts SURVIVE discard — re-extracting from the
  same document is the point. Contract test: discard, then re-extract with the
  same `artifact_id` succeeds and fires the LLM seam exactly once.
- TDD-first in a new `tests/unit/test_discard_draft.py` (four-service contract
  in one file; copy the `app_client` fixture shape from
  `test_attack_draft_guard.py`). Expected scope now includes `risk.py` and
  `intake.py` beside the four service route files. Append **D-031** to
  DECISIONS.md (including the conditional-update concurrency contract).

### T1 — Web: discard proxies, client fns, shared confirm dialog

- Four proxy routes copied from each sibling `approve/route.ts`:
  `apps/web/src/app/api/proxy/{tech-debt/capability-lists,csf/assessments,attack/assessments,zt/assessments}/[id]/discard/route.ts`.
- `discard*()` functions in the four client libs
  (`apps/web/src/lib/{tech_debt,csf,attack,zt}/client.ts`); `"discarded"`
  added to the status type unions.
- New shared `DiscardDraftButton.tsx` (button + design-system `Modal` — the
  app's first destructive-confirm dialog; props: label copy, destruction
  summary line, onConfirm). Rendered/enabled only when `status === "draft"`,
  beside each workspace's Approve/Start affordance in `TechDebtWorkspace.tsx`,
  `AttackWorkspace.tsx`, `CsfWorkspace.tsx`, `ZtWorkspace.tsx`.
- Dialog copy states what is destroyed: tech-debt "N capability items"; attack
  "N scored techniques"; CSF/ZT **"N answers, including client-entered data,
  will be discarded"** — counts computed from the already-fetched grid, no new
  endpoint.
- Bump the workspace loaders' seq counter before the post-discard refetch (the
  `listSeq`/`assessmentSeq` reqSeq pattern) so a stale in-flight `latest` fetch
  can't resurrect the discarded draft; after discard the workspace shows its
  existing empty/upload state and the extract/start affordance is live again
  (`GET latest` 404 → null).
- TDD-first vitest: `DiscardDraftButton` renders only for draft status, opens
  the Modal, confirm invokes the callback, cancel does not; one workspace test
  proves the answered-count line renders in the CSF dialog copy.

### T2 — Export-content unit assertions (retire the §10 eyeball, close §19)

- Add `pypdf>=5` to `[project.optional-dependencies].dev` in
  `apps/api/pyproject.toml` (test-only; CI already installs `.[dev]`; `pypdf`
  is imported ONLY inside test files, never in `app/`). Then
  `docker compose build api`.
- Pure-renderer tests parsing real bytes — the renderers take plain kwargs, no
  DB/TestClient needed:
  - New `tests/unit/test_playbook_export_content.py` over the five
    `app/csf/playbook_export.py` renderers with constructed
    `enterprise_rows`/`tier_profiles`/`gap_actions`. **The §19 contract:** the
    XLSX has an Action Plan sheet with the expected header set; priority
    defaults from `gap_priority()` and a `priority_override` wins. Exec/full
    PDF via `pypdf.PdfReader`: concatenated `extract_text()` contains client
    name, document title, at least one CSF function name, one known gap value
    (match distinctive substrings, never exact layout — reportlab text extract
    is whitespace-mangled). Exec/full DOCX via `docx.Document(BytesIO(...))`:
    heading text + scorecard table headers + one known maturity cell value.
  - Extend `test_exporters.py` / `test_csf_exporters.py` /
    `test_attack_exporters.py` / `test_zt_exporters.py` /
    `test_risk_register.py` (explicitly in scope — Codex nit): per-service
    PDFs get title + client name + one known row value (upgrade from `%PDF-`
    magic-only); risk PDF/DOCX get title + a known entry; XLSX stays as-is
    (already content-tested).
- SMOKE §10: re-point the five checked eyeball boxes to the proving test
  filenames; keep ONE explicitly-manual line ("visual aesthetics: colors,
  spacing, page-breaks — human, optional"). Check §19's deferred Action-Plan
  box with the new test filename. Honesty convention throughout.

### T3 — e2e: retire the approve-first dance; SMOKE §31

- Replace "approve any open draft" with a discard POST in the three preambles:
  `s4-techdebt.spec.ts` (:58-76), `s5-attack.spec.ts` (`openFreshDraft`
  :42-78), `s11-staleness.spec.ts` (:53-57). Behavior coverage after the
  preamble stays byte-identical — do not weaken the changed>0 / "AI 60%"
  assertions.
- One spec (s4 or s5) additionally drives the UI affordance once: draft open →
  click Discard draft → Modal → confirm → workspace returns to empty state → a
  fresh mint follows. This is the browser proof for SMOKE §31.
- New SMOKE §31 (discard affordance) checked ONLY with the green committed
  spec filenames (UI proof + per-service API behavior; the 409-on-SUBMITTED
  contract cites `test_discard_draft.py`).
- Full host-run e2e suite green (all specs, not just the three edited).
  `docker compose up -d --force-recreate web` first — T1 touched web sources.

### T4 — Backend OIDC: flag, RS256 verifier, `POST /auth/oidc/exchange` (D-032)

- Config: `shield_auth_oidc_enabled: bool = False` (`SHIELD_AUTH_OIDC_ENABLED`)
  beside the other auth flags; new `keycloak_jwks_url` setting (default
  `http://keycloak:8080/realms/shield/protocol/openid-connect/certs` —
  network-only, never compared to `iss`). `oidc_readiness() -> tuple[bool,
  str]` mirroring `live_llm_readiness()`: flag on requires non-empty http(s)
  `keycloak_issuer` + `keycloak_jwks_url` and non-empty
  `keycloak_audience`/`keycloak_client_id`; wired into the boot-time
  fail-loud path. **No network preflight at boot** (D-026 precedent; api has
  no `depends_on: keycloak` and must not crash-loop on cold compose-up) —
  network reality surfaces as a typed 503 at runtime and via T5's real probe.
- New `app/security/oidc.py`: JWKS cache (module-level `{kid: jwk}` + fetch
  timestamp, 300s TTL, `threading.Lock`), `httpx` GET 5s timeout, exactly one
  forced refetch on unknown `kid`, raw fetch isolated in module-level
  `_fetch_jwks()` so unit tests monkeypatch it. **No new runtime dependency**
  — `python-jose[cryptography]` + `httpx` already ship.
- New `app/routes/oidc.py` (`APIRouter(prefix="/auth/oidc")`, registered in
  `main.py`): `POST /auth/oidc/exchange` takes
  `{keycloak_access_token: str}` (the ACCESS token — it carries
  `aud=shield-api` via the realm's audience mapper), returns `{user, tokens}`
  (mirrors `RegisterResponse`; no `/auth/me` follow-up needed).
- Validation pipeline, every failure a typed dict-detail, FAIL LOUDLY:
  flag off → 403 `oidc_disabled`; RS256 verify via
  `jose.jwt.decode(..., algorithms=["RS256"], audience=keycloak_audience,
  issuer=keycloak_issuer, options={"require": ["exp","iat","sub"]})` (HS256
  tokens rejected by the algorithms list — alg-confusion guard) → 401
  `oidc_token_invalid`; JWKS unreachable → 503 `oidc_jwks_unavailable`
  (message names the URL and the flag); rate-limit after signature verify;
  missing `email` claim → 401 `oidc_claims_missing`; `email_verified` not
  true → 403 `oidc_email_unverified`; **`azp` claim ≠ `keycloak_client_id` →
  401 `oidc_token_invalid`** (Codex finding: `aud` names the resource server,
  not the requesting client — a correctly signed token minted to a DIFFERENT
  client must be rejected, with a test proving it); no local user by
  normalized email (**NO JIT provisioning**) → 403 `oidc_no_local_account`;
  inactive → 403 `oidc_user_inactive`; TOFU sub binding —
  `user.keycloak_sub` NULL → stamp it (log `oidc.sub_bound`),
  set-and-different → 403 `oidc_sub_mismatch`.
- Success path reuses `_issue_pair` + `_register_successful_login` from
  `routes/auth.py` (promote to a shared helper only if ruff fights the
  private import): identical rotation bookkeeping, lockout-counter reset,
  `last_login_at`, forced-reauth semantics. The minted pair is plain D-020
  HS256 — **Keycloak tokens are never accepted as API bearers.** Local DB
  role stays authoritative (the Keycloak `roles` claim is ignored for authz);
  OIDC sessions bypass local TOTP MFA (Keycloak owns MFA on that path); the
  local password-lockout is NOT consulted (Keycloak `bruteForceProtected`
  owns it — honoring the local lock would let a password-endpoint attacker
  DoS SSO users); the exchange does NOT stamp local `email_verified_at`.
- Migration `0032_user_keycloak_sub`: `users.keycloak_sub` String(64),
  nullable, unique (multiple NULLs legal in PG and SQLite),
  `batch_alter_table`, additive.
- TDD-first `tests/unit/test_oidc_exchange.py`: in-test RSA keypair signs
  Keycloak-shaped tokens; monkeypatched `_fetch_jwks` returns the matching
  JWKS. Cases: happy path (pair passes `verify_token`, follow-up
  `/auth/refresh` rotates, role comes from DB — a token claiming
  `roles:["admin"]` for a local client-role user mints CLIENT tokens); wrong
  iss; wrong aud; expired; HS256-signed rejected; unknown kid → exactly one
  refetch; missing email; unverified email; no local user; inactive; sub TOFU
  stamp; sub mismatch; flag off; JWKS failure → 503. Plus `test_config.py`
  boot-shape cases (flag on + empty jwks_url → boot RuntimeError). Flag
  default OFF: the whole pre-existing unit suite passes untouched. Append
  **D-032** to DECISIONS.md.

### T5 — Infra: dual-horizon Keycloak, realm fixes, real `/ready` probe

- **The split-horizon issuer fix, the sprint's environmental linchpin:**
  Keycloak service gains `KC_HOSTNAME: http://localhost:8080` +
  `KC_HOSTNAME_BACKCHANNEL_DYNAMIC: "true"` (KC 25 hostname-v2). One canonical
  `iss` (`http://localhost:8080/realms/shield`) no matter which interface
  served the request; backchannel requests to `keycloak:8080` get
  container-reachable token/JWKS endpoints. Flip the `KEYCLOAK_ISSUER` default
  to the realm URL in compose + `.env.example` + `config.py`; add api-env
  `KEYCLOAK_JWKS_URL` + `SHIELD_AUTH_OIDC_ENABLED:-false`, web-env
  `KEYCLOAK_INTERNAL_ISSUER=http://keycloak:8080/realms/shield` +
  `SHIELD_AUTH_OIDC_ENABLED:-false`.
- Realm export fixes (`infra/keycloak/shield-realm.json`): remove the
  `reviewer` realm role (D-023 drift); add permanent, `emailVerified: true`,
  non-temporary-password users `admin@kentro.example` / `DemoPass!2026`
  (realmRoles `["admin"]`, matches the seeded local admin — T7's identity) and
  `nolocal@atlas.example` / `DemoPass!2026` (no local account — the negative
  path); add `http://localhost:3001/*` redirect URIs + webOrigins (Dave's box);
  keep PKCE S256. Keep `dev-admin@shield.local` for console poking.
- **`docker-compose.demo.yml` must be aligned too (Codex finding):** the demo
  override independently sets the web env `KEYCLOAK_ISSUER` (`:48-55`) and
  would silently undo the issuer flip under the demo overlay. Align its
  issuer/internal-issuer variables with base compose and extend the
  hand-check: `docker compose -f docker-compose.yml -f docker-compose.demo.yml
  config` shows the pinned issuer on both api and web.
- `/ready` keycloak probe (`health.py:117-125`): flag off → `dormant` exactly
  as today (detail updated to name the flag); flag on → REAL probe (httpx GET
  `keycloak_jwks_url`, 2s timeout) reporting `ok`/`down`. **`required` stays
  `False` in both states** — credentials login keeps the app serviceable
  during a Keycloak outage, so OIDC must never gate LB readiness.
  `HealthMatrix.tsx` already renders ok/down/dormant — no web change; s25
  stays green.
- TDD-first in `test_readiness.py`: flag off → dormant/not-required (existing
  tests re-anchored, not weakened); flag on + probe ok → ok; flag on + fetch
  raising → down AND `ready` stays true.
- Hand-verify (documented in the task log; wipe the keycloak volume first):
  browser GET `localhost:8080/realms/shield/.well-known/openid-configuration`
  shows the pinned issuer; in-container curl of the same path via
  `keycloak:8080` shows the SAME issuer with a `keycloak:8080` token endpoint.

### T6 — Web OIDC: conditional provider, exchange branch, sign-in button (HIGHEST RISK)

- New `apps/web/src/lib/auth/oidc.ts` (pure, vitest-friendly):
  `isOidcEnabled()` (`process.env.SHIELD_AUTH_OIDC_ENABLED === "true"`),
  `rewriteKeycloakUrl(url, publicIssuer, internalIssuer)`, `keycloakFetch`
  (customFetch prefix-rewrite so Auth.js fetches OIDC discovery container-side;
  after discovery the backchannel-dynamic token endpoint already points at
  `keycloak:8080`, so the rewrite is a passthrough for everything else).
- **Start with a minimal authorization-code spike (Codex finding):** before
  wiring the full callback branch, prove the raw redirect → Keycloak form →
  callback → token round trip with the secret-less client, so the
  beta-sensitivity verdict lands in the first hour, not the last.
- `options.ts`: `providers: [Credentials({...}), ...(isOidcEnabled() ?
  [keycloakProvider()] : [])]` — flag off means the provider does not exist.
  Keycloak provider config: public client + PKCE (`checks: ["pkce","state"]`,
  `client: { token_endpoint_auth_method: "none" }`, `[customFetch]:
  keycloakFetch`). **Pre-approved fallback if next-auth 5.0.0-beta.31 fights
  the secret-less client** — defined completely (Codex finding): realm export
  gets `publicClient: false` + `clientAuthenticatorType: "client-secret"` +
  the dev secret (dev-realm-only, same class as the bootstrap password;
  if gitleaks flags it, add a documented allowlist entry scoped to the realm
  export); `KEYCLOAK_CLIENT_SECRET` plumbed through BASE **and DEMO** compose;
  a confidential-token-exchange e2e proof. Do NOT bump the next-auth beta in
  this task (one variable at a time).
- `jwt` callback: a keycloak branch ordered BEFORE the credentials `if (user)`
  seed (the OIDC initial sign-in also carries a profile `user`): call
  `POST /auth/oidc/exchange` with `account.access_token`, seed
  `token.{role,accessToken,refreshToken,accessExpiresAt}` exactly like the
  credentials path — downstream expiry/refresh/session logic untouched. On
  `ApiError`: log the typed reason server-side, set `token.error =
  OIDC_EXCHANGE_ERROR` (new constant in `lib/auth/errors.ts`);
  `SessionExpiryGuard` extended to sign out to
  `/sign-in?reason=oidc_exchange_failed`; the sign-in page renders a loud
  banner for that reason beside the existing `session_expired` one.
- `/sign-in/page.tsx` (server component) reads `isOidcEnabled()` and
  conditionally renders a new `KeycloakSignInButton` client component
  (`signIn("keycloak", { callbackUrl: "/" })`), visually separated from the
  credentials form. Flag off → button absent, page byte-identical to today.
- **The task's hardest promise: flag OFF is a behavioral no-op** — the
  Keycloak provider is absent, ZERO Keycloak discovery/JWKS network requests
  occur (add a vitest trap for unexpected fetches), and every credential
  surface behaves unchanged. `options.ts` is load-bearing for all ~24
  credential e2e specs — the full default suite and the existing
  SignInForm/MFA vitest suites must pass unchanged.
- **Production build must survive (Codex finding):** in-container
  `pnpm -F web build` green (CI runs it; the demo compose runs the standalone
  prod image — provider registration/env handling can typecheck clean and
  still die at build/start). Mandatory for this task, not a new global gate.
- TDD-first vitest: `rewriteKeycloakUrl` rewrite/passthrough table;
  `isOidcEnabled` truth table; button renders + calls mocked
  `signIn("keycloak")`; `SessionExpiryGuard` fires on `OIDC_EXCHANGE_ERROR`.
- Hand-verify against the T5 stack with the flag flipped on both containers
  (then restored): full browser round trip as `admin@kentro.example` lands
  authenticated with working API pages; `nolocal@atlas.example` lands on the
  loud banner; credentials + TOTP MFA sign-in re-verified working WITH the
  flag on (hybrid coexistence).

### T7 — Opt-in e2e proof: `s26-oidc-login.spec.ts`

- `test.skip(process.env.E2E_OIDC !== "1", ...)` at the top — the default
  suite runs zero new tests and stays green flag-off. Prove the skip first.
- Documented flip procedure in the spec header + SMOKE: set
  `SHIELD_AUTH_OIDC_ENABLED=true` in `.env`, `docker compose up -d
  --force-recreate api web`, wipe the keycloak volume if the realm export
  changed since import, then `E2E_OIDC=1 npx playwright test s26`.
- Positive path: `/sign-in` → "Sign in with Keycloak" → Keycloak form on
  `localhost:8080` (`#username`/`#password`, `admin@kentro.example` /
  `DemoPass!2026`) → back on the app authenticated → load an API-backed page
  (backend tokens proven end-to-end). Negative path: `nolocal@atlas.example`
  → `/sign-in?reason=oidc_exchange_failed` banner visible.
- Spec green on the flag-on stack, THEN the full default suite re-run green on
  the restored flag-off stack (restoration proven, not assumed).
- SMOKE gains the OIDC section (spec-backed boxes + the volume-wipe gotcha +
  the flip/restore procedure as an operator note).

### T8 — Demo-reset `--demo` mode + opt-in demo-journey spec (§26, D-033)

- `scripts/demo-reset.sh` gains `--demo`; `scripts/demo-reset.ps1` gains
  `-Demo` (keep sh/ps1 parity): the flag appends
  `-f docker-compose.yml -f docker-compose.demo.yml` to every compose
  invocation; the step sequence (down -v → build → `/ready` poll → seed → web
  wait → banner) is otherwise identical. Plain invocation still drives the
  base compose only. Document `--demo` in `README.md:106-132`.
- **Fix the silent web wait (Codex finding):** today the script's web poll
  gives up after 120s and prints success anyway (`demo-reset.sh:68-75`) — a
  failed prod image looks like a successful reset until Playwright dies
  opaquely. Make the timeout FAIL LOUDLY (non-zero exit) and dump
  `docker compose logs web` on the way out; sh/ps1 parity.
- New `e2e/demo/demo-journey.spec.ts`, self-skipping unless
  `SHIELD_DEMO_SMOKE=1` (mandatory — it must never run against a stack it
  didn't just reset). Asserts the post-reset journey: `/ready` full-matrix
  green; `/sign-in` serves 200 with CSP headers (prod-build proof); UI sign-in
  as `admin@kentro.example` AND `client@atlas.example`; client `/home` shows
  the released-report hero; a seeded `/documents` deliverable downloads 200
  with non-zero bytes.
- **Local proving run is destructive** — run `bash scripts/demo-reset.sh
  --demo` once locally, then `SHIELD_DEMO_SMOKE=1 npx playwright test demo/`
  green; afterward reseed/verify the dev stack before any later task. Also
  prove the no-flag invocation still targets the base compose.
- SMOKE §26 checked with the spec filename, box text updated to what is
  actually proven. Append **D-033** (destructive automation is opt-in-gated:
  reset specs self-skip, destructive scripts never run implicitly, CI
  isolation is the only unattended venue).

### T9 — CI `demo` job (§27, every PR)

- New `demo` job in `.github/workflows/ci.yml` on its own runner (CI runners
  are isolated — `down -v` there cannot hurt the e2e job; no `.env` needed,
  compose defaults suffice): log `docker compose version` first and fail
  loudly if below 2.24 (the `!reset` floor) → `bash scripts/demo-reset.sh
  --demo` → `shield-web:demo` builds → seed runs inside the script → `cd e2e
  && npm ci && npx playwright install --with-deps chromium &&
  SHIELD_DEMO_SMOKE=1 npx playwright test demo/` → always-run diagnostics
  (`docker compose ps` + logs dump, the e2e job's fail-loud pattern) + upload
  playwright artifacts `if: always()`. Timeout ~25 min. Runs on every PR
  (Dave's call — breakage surfaces pre-merge).
- Proving artifact: the job green on this sprint branch's PR run, verified via
  `gh run view` and cited in the task log. SMOKE §27 checked with the spec
  filename + job name.

### T10 — Wrap-up

- SMOKE_TEST annotations final pass (§10 re-pointed + one manual line, §19,
  §26, §27, §31, OIDC section) — every box checked only with its proving spec
  or test filename.
- CHANGELOG `[3.5.0]` per-task entries with commits; BUILD_REPORT sync (gate
  results at HEAD, e2e spec count, new flags/decisions).
- `CONTEXT.md` overwritten with the end-of-sprint snapshot; the LAUNCHING
  dev's own `context/<name>.md` refreshed (owner-only rule).
- Full exit gate set (all six) + full e2e (quiet box; per-spec standalone
  re-run remains the flake arbiter).

## Definition of done

- With `SHIELD_AUTH_OIDC_ENABLED=true`, a Keycloak realm user with a matching
  local account signs in through the real Keycloak page and lands with working
  backend tokens; a realm user with NO local account gets the loud typed
  banner, not a silent failure. With the flag off (default), the provider is
  absent, zero Keycloak network calls occur, and every existing auth surface
  and all ~24 credential e2e specs are untouched.
- An admin can discard an open draft in each of the four services from the UI
  (confirm dialog, client-work warning on CSF/ZT) and by API; the next mint is
  a fresh version with no `IntegrityError`; SUBMITTED/APPROVED/RELEASED refuse
  with typed 409s; discarded rows are invisible to the risk-register gate and
  the engagement cards; stale writes into a discarded parent lose loudly;
  three e2e specs no longer approve-to-refresh.
- Export content (XLSX Action Plan contract, PDF text, DOCX tables) is
  asserted by unit tests over real bytes; SMOKE §10 carries test filenames
  plus exactly one explicitly-manual aesthetics line; §19's deferral is
  closed.
- `demo-reset --demo` + the demo-journey spec prove the hosted-demo compose
  locally and in a green every-PR CI job; §26/§27 are spec-backed.
- D-031/D-032/D-033 appended in their tasks; migration 0032 additive and
  SQLite-safe; no credential committed (the dev-realm fallback secret, if the
  T6 fallback fires, is documented in the PR body as dev-only); every commit
  conventional and task-scoped; CONTEXT.md snapshot written.

## Explicitly out of scope (needs-Dave / later)

- **Loop launch** — the human dev at the keyboard starts `/loop-sprint-cron`;
  agents never do.
- Full token federation (backend accepting Keycloak tokens as API bearers),
  JIT user provisioning, and migrating register/MFA/email flows into Keycloak
  — the hybrid exchange deliberately defers all three.
- Stamping local `email_verified_at` from a Keycloak `email_verified` claim
  (paths stay independent this sprint).
- An un-discard/recovery endpoint (DISCARDED is terminal in v1; rows are
  DB-recoverable).
- §10 visual aesthetics (the one explicitly-manual line that remains).
- ESLint 10 + the `postcss` moderate (upstream-blocked, D-018).
- Cloud deploy / terraform / DR runbooks; FedRAMP LLM connector;
  `azure_openai`/`bedrock`/`local` adapters (loud not-implemented).
