# Decision Log

Append-only record of every choice made during the SHIELD v2.0 autonomous build. Per AI Prompt §7 / §4.9, every time a non-obvious option is picked over an alternative, it must land here.

Each entry: `D-NNN` · date (UTC) · category · subject · decision · rationale · spec/AI-Prompt reference.

---

## D-001 — Tech stack confirmation

**2026-05-19 · architecture**
Confirm locked stack from Master Spec §2: Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui (frontend), FastAPI on Python 3.12 (backend), PostgreSQL 16, Redis, S3-compatible object storage (MinIO in dev, S3 + KMS in prod), Keycloak/OIDC, Celery workers, Alembic migrations, Playwright E2E.
**Rationale:** Locked by Eugene in spec §2. No deviation.
**Ref:** Master Spec §2, AI Prompt §2, §8.2 (D-001).

## D-002 — AI provider for v1

**2026-05-19 · ai**
Default LLM provider is **Anthropic Claude** via `ANTHROPIC_API_KEY`, configured by `SHIELD_LLM_PROVIDER` and `SHIELD_LLM_MODEL`. Default model `claude-opus-4-7`. Env-configurable; never hardcoded.
**Rationale:** Eugene answered spec §17 Q6 with "developer's choice"; Anthropic Claude is the recommended default in spec §2 and `.env.example`. Best output quality for analytic prompts, cleanest API for redacted-payload pattern. Risk of non-FedRAMP egress accepted by Eugene; PII redaction (§12) is the primary compensating control.
**Ref:** Master Spec §2, §4.4, §17 Q6, AI Prompt §8.2 (D-002).

## D-003 — Marketing landing page (spec §17 Q1)

**2026-05-19 · ux**
Implement a polished one-page marketing landing at `/` (hero, mission, service cards, resource center, contact, footer). NOT a redirect to `/sign-in`.
**Rationale:** Eugene confirmed recommended option. Aligns with Round 6 design contract's PUBLIC / EXTERNAL EXPERIENCE tier (USWDS + Microsoft public portal styling).
**Ref:** Master Spec §17 Q1, Round 6 Design Contract (public-experience tier).

## D-004 — Self-registration allowed (spec §17 Q2)

**2026-05-19 · auth**
Allow self-registration. The first registrant on a fresh deployment becomes that deployment's Primary POC. A Kentro consultant verifies and attaches them post-registration.
**Rationale:** Eugene confirmed recommended option. Preserves the v1 onboarding process Eugene wants to keep. Compensating controls for the open-door surface: account lockout, short JWT TTLs, idle timeout, forced re-auth (Master Spec §4.5).
**Ref:** Master Spec §17 Q2, §4.5.

## D-005 — Reviewer assignment is deployment-wide (spec §17 Q3)

**2026-05-19 · auth**
Any admin in a deployment may attach a reviewer. A reviewer's scope is the entire deployment — they see all services in this single-tenant deployment, not service-by-service.
**Rationale:** Eugene confirmed recommended option. Single-tenant means one deployment = one client engagement; per-service slicing is over-engineering for v1.
**Ref:** Master Spec §17 Q3, §2 (single-tenant).

## D-006 — Deliverable approval flow (spec §17 Q4)

**2026-05-19 · workflow**
Approval flow: **admin marks deliverable "final"** → **reviewer (if any) approves** → **admin releases to client**. Reviewer step is skipped when no reviewer is attached to the engagement.
**Rationale:** Eugene confirmed recommended option. Matches Phase 5 reviewer audit-walk surface (Master Spec §15 Phase 5). The "if any" guard handles engagements without a reviewer without needing a second release path.
**Ref:** Master Spec §17 Q4, §15 Phase 5.

## D-007 — ATT&CK technique scope (spec §17 Q5) **[FLIPPED FROM RECOMMENDATION]**

**2026-05-19 · service**
**Use the full MITRE ATT&CK Enterprise matrix (~600 techniques)** for every engagement. NOT the recommended curated 33–40 most-relevant subset.
**Rationale:** Eugene explicitly flipped this answer ("we should build it to use all of the 600+ items").
**Implications and requirements:**

1. `packages/attack-data/` vendors the full MITRE ATT&CK Enterprise JSON (STIX 2.1 bundle) and is load-bearing.
2. The ATT&CK questionnaire UI MUST be designed for ~600 items from day one: tactic-grouped sections (14 tactics), pagination or virtualization, search by technique ID / name / data source / platform, filter by tactic / platform / data-source-availability, bulk-mark workflows, progress persistence, auto-save on every cell.
3. Master Spec §6.10 already forbids "single massive scroll" questionnaires; this decision reinforces it.
4. Coverage scoring math is unchanged per technique; only rendering scales.
5. Coverage Report deliverable (Phase 5) must paginate by tactic to remain readable as PDF/XLSX.
   **Ref:** Master Spec §17 Q5, §15 Phase 5, §6.10.

## D-008 — AI provider for v1 (spec §17 Q6)

**2026-05-19 · ai**
See D-002. Anthropic Claude API as the v1 default, env-swappable.
**Ref:** Master Spec §17 Q6.

## D-009 — Languages and locale (spec §17 Q7)

**2026-05-19 · i18n**
English only at v1.0. Build i18n-aware (no hardcoded strings; locale-keyed message files via `next-intl` for web and `babel`/`gettext`-style catalogs for API responses). Additional locales added in v1.x as content-only PRs.
**Rationale:** Eugene confirmed recommended option. Avoids translation cost in v1 while preserving zero-rewrite extensibility.
**Ref:** Master Spec §17 Q7.

## D-010 — Repo layout: monorepo with pnpm workspaces + Python workspace

**2026-05-19 · architecture**
Single repository, pnpm workspaces for `apps/web`, `apps/api` consumers (shared TS types), and `packages/*`. Python apps (`apps/api`, `apps/worker`) managed via Poetry with a shared root `pyproject.toml` for tooling config. CI runs all checks from the repo root.
**Rationale:** Spec §16 prescribes the directory shape. Monorepo simplifies sharing of `packages/shared-types`, `packages/csf-data`, `packages/attack-data`, `packages/zt-data` across web and API without publishing.
**Ref:** Master Spec §16, AI Prompt §8.2 (repo layout).

## D-011 — Working directory deviation

**2026-05-19 · environment**
Spec §3.2 mandates working directory `/workspaces/SHIELDV2-051826v2`. Actual working directory is `/workspaces/repos/SHIELDV2-051826v2` because the persistent dev-container mount in this environment is `/workspaces/repos`. All in-container paths in scripts and docs use relative paths from the repo root to remain portable across both mount points.
**Rationale:** `/workspaces/SHIELDV2-051826v2` is on the overlay FS in this environment (ephemeral on container rebuild). The mounted path persists.
**Ref:** AI Prompt §3.2.

## D-012 — Dev container runs as `appuser` with passwordless sudo

**2026-05-19 · environment**
`.devcontainer/Dockerfile` creates non-root `appuser` (uid 1000) with passwordless sudo for development convenience. Production runtime images (separate Dockerfiles under `infra/docker/`) use a least-privilege non-shell user with no sudo.
**Rationale:** Required by AI Prompt §3.10 / §3.11 to prevent the autonomous agent from stalling on sudo prompts. Production posture is unchanged.
**Ref:** AI Prompt §3.10, §3.11.

## D-013 — Reference docs renamed and relocated

**2026-05-19 · housekeeping**
Reference docs in the original GitHub repo root were renamed (whitespace → underscores, parenthetical suffixes removed) and moved to `reference-docs/`. Examples:

- `AI Prompt` → `reference-docs/AI_Prompt`
- `Shield UX fix round 6 full design update for 2.0.txt` → `reference-docs/Shield_UX_Round6_Design_Contract.txt`
- `Ongoing CSF2 Artifact Tracker (1).xlsx` → `reference-docs/CSF2_Artifact_Tracker.xlsx`
- All `Step N.M ... .docx`/`.xlsx` → `reference-docs/Step_N_M_...` (underscores, no spaces, no parentheticals).
  Moves use `git mv` so history is preserved. No file deletions.
  **Rationale:** Whitespace and parentheses in filenames are hostile to scripts, CI, and Windows paths. `reference-docs/` keeps the spec library separate from build artifacts.
  **Ref:** Master Spec §15.5 (slugifier conventions apply to deliverables; we apply the same hygiene to reference filenames).

## D-015 — Multi-tenant: shared DB with `client_id` on every row

**2026-05-21 · architecture**
Platform now supports many `client` rows per deployment instead of exactly one. Tenant isolation is enforced at the data-access layer (every business table carries `client_id`; every data route filters by it) rather than via per-tenant schemas or databases. Platform-level admin/reviewer users (`User.client_id IS NULL`) pick the active tenant via an `X-Client-Id` request header surfaced as a top-nav client switcher in the frontend; client-role users are pinned to their `User.client_id` and cannot escape it. New client tenants are created by either an admin via `POST /admin/clients` or implicitly when a non-admin self-registers (a fresh `Client(legal_name="(pending intake)")` row is created and bound to the new user, which the intake wizard then fills in).
**Rationale:** Eugene requested multi-client support. The schema already denormalized `client_id` on assessment tables (Master Spec §11.1 future-proofing); this migration (0013) adds it to the remaining business tables (`services`, `service_requests`, `artifacts`) and makes every business `client_id` `NOT NULL`. Shared-DB-with-tenant-column was chosen over schema-per-tenant and DB-per-tenant because: (1) the existing data model is one column short of being ready, (2) cross-tenant admin/reporting features remain cheap, (3) operational burden (one DB to back up, migrate, monitor) does not scale with tenant count.
**Implications and requirements:**

1. Every data route (`csf`, `zt`, `attack`, `tech_debt`, `artifacts`, `deliverables`) takes a `current_client` FastAPI dependency that resolves the active tenant; reads filter by `client_id`; writes set `client_id` at row creation; id-based fetches (`db.get(Service, id)` etc.) verify ownership via `app/tenant.py` helpers that return 404 on tenant mismatch (no existence oracle).
2. `User.client_id` stays nullable for platform admins/reviewers; everyone else's is set on registration.
3. The frontend forwards the cookie-driven `shield_active_client_id` as `X-Client-Id` through `lib/api.ts`; admin-only cross-tenant routes (e.g. `GET /admin/clients`, `POST /admin/clients`) pass `clientId: ""` to suppress that header.
4. Backwards compatibility: migration `0013` backfills all existing rows to the deployment's existing singleton `client` row (or creates a `"(legacy backfill)"` placeholder if business data exists but no `client` row does).
5. D-005 ("reviewer attachment is deployment-wide") still holds _within a tenant_; a reviewer can see every service for the active client they're scoped to.

**Ref:** Master Spec §11.1 (denormalized client_id), §2 (single-tenant — now superseded for this platform), §4.5 (auth), DECISIONS D-004 (self-registration extends to per-tenant client creation).

## D-014 — Opening commit on `main`, push deferred

**2026-05-19 · git**
Opening commit lands directly on `main`. Push is deferred until the dev container has credentials configured per AI Prompt §3.3 (no agent-introduced credentials).
**Rationale:** AI Prompt §3.9 prescribes "push frequently" but §3.3 forbids the agent from introducing its own credentials. Eugene will push when he attaches a PAT or SSH key to the container.
**Ref:** AI Prompt §3.3, §3.9.

## D-021 — Part F: harden and ship decisions

_(Renumbered from a duplicate "D-015" heading — see the D-022 erratum. Older
documents citing "D-015 (Part F)" mean this entry.)_

**2026-06-26 · F (harden)**

- **Worker / async:** AI runs are **synchronous** — the `run-ai` endpoints invoke
  the LLM inline via `app.ai.engine.run_job`. There is no Celery worker; the
  orphaned `worker` service (which referenced a non-existent `app.worker`) was
  removed from `docker-compose.yml`. `redis` remains as a config placeholder for
  future rate-limiting/async but has no consumer today.
- **Auth seam:** NextAuth stays pluggable. The active login is `CredentialsProvider`
  (against the API); a Keycloak realm is scaffolded under `infra/keycloak/` so a
  SAML/OIDC provider can be added without touching call sites. MFA stays deferred.
- **Dependency audits:** `pip-audit` (API) and `pnpm audit --audit-level high`
  (web) run in CI (non-blocking; surface advisories), and `.github/dependabot.yml`
  opens the fix PRs (pip / npm / github-actions, weekly). pip-audit is clean today.
- **Accessibility:** static `jsx-a11y` rules are enforced in CI via
  `next/core-web-vitals` (the eslint step); skip-to-content links + a
  `#main-content` landmark are present in every shell (admin + client pages).
  Runtime axe/Pa11y in CI is the remaining a11y item (needs a dev-dep + a built
  app harness in CI — pnpm-lockfile change to be made in a pnpm environment).
- **IaC:** `apps/api/Dockerfile` exists; a production `apps/web/Dockerfile`
  (Next standalone) was added. `infra/terraform` for AWS GovCloud / Azure
  Government remains a skeleton — it needs concrete account/region/network
  decisions and is intentionally left as the next infra task.
- **Isolation:** `test_new_surface_authz.py` covers cross-tenant isolation for the
  new tables (messages, client_domain, risk register, CSF tier profiles); these
  run under `pytest -m unit` in CI.

**Ref:** Work Order Part F.

## D-016 — Duplicate-email registration discloses existence (typed error copy)

**2026-07-02 · auth**
Self-registration surfaces a friendly, field-scoped error for a duplicate email
("An account already exists for that email. Sign in instead.") rather than a
generic enumeration-resistant message. The `/auth/register` endpoint returns a
typed error envelope on every rejection — `error.reason` (machine code) plus
`error.message` (human copy) — and the web sign-up form maps each `reason` to the
right field: `email_exists` (409) and `email_domain_not_allowed` /
`email_domain_not_approved` / `email_domain_unavailable` (422) attach to the email
field; `password_policy` (422) attaches to the password field; a raw
`RequestValidationError` (no `reason`) shows a plain-language form-level prompt
instead of leaking the internal "Request validation failed." string.

**Rationale:** Disclosure posture is kept **consistent with the pre-existing
domain-rejection copy**, which already tells a caller whether their domain is
approved. Registration is gated behind admin-approved email domains, so an
attacker must already control an approved-domain mailbox to probe for account
existence — the marginal enumeration surface a duplicate-email message adds over
the domain-approval oracle is negligible, and the usability win (the user learns
to sign in instead of retrying) is real. The **login** path keeps its stricter
enumeration-resistant posture unchanged (generic "Invalid email or password." +
constant-time dummy-hash compare, OWASP A07); the two surfaces differ
deliberately because login is unauthenticated-probe-heavy while register is
domain-gated. No new information beyond the existing domain oracle is disclosed.

**Ref:** Master Spec §17 Q2, §4.5; SPRINT_1.md T4; OWASP A07 (login path unchanged).

## D-017 — Fixture-mode AI serves deterministic runtime suggestions offline

**2026-07-03 · ai**
Fixture mode (`SHIELD_LLM_MODE=fixture`) now registers a deterministic,
demo-plausible canned response for every one of the five AI job purposes
(`mitre_map`, `zt_score`, `csf_score`, `extract.capabilities`,
`risk_synthesize`) via a new `app/ai/fixtures.py` module. `_build_provider`
returns a `RuntimeFixtureProvider` preloaded with those fixtures instead of a
bare, empty `FixtureProvider`. Each fixture is payload-aware — it reads the
redacted job payload (technique codes, capability codes, tiers/subcategories,
findings) so the drafted suggestions line up with the live assessment and
"Run AI" actually changes rows. The demo/dev stack is now fully exercisable
OFFLINE with no provider API key.

A missing fixture at runtime is surfaced as a typed configuration error mapped
to HTTP 503 (`reason=ai_fixture_unavailable`, mirroring the D-016 / T4 typed-error
pattern), never a raw 500 `KeyError`. The bare `FixtureProvider` keeps its loud
`KeyError` for tests, and pytest's own dependency-override fixtures still take
precedence over the runtime provider.

**Rationale:** David-approved product decision (2026-07-03) after the T6 halt
(Run-AI 500'd because the runtime provider had zero fixtures registered — only
pytest registered them). "AI suggests, code computes" is preserved: fixtures
only DRAFT values (statuses, stages, dimension scores, risk links); the
deterministic engines still compute every total, tier, roll-up and roadmap. DoD
ZTRA fixture values respect the framework's `<=3` stage clamp. Live-mode behavior
is unchanged.

**Ref:** Master Spec §4.4 (LLM env-configurable), §12 (redaction on egress);
SPRINT_1.md T6b; DECISIONS D-016 (typed-error pattern reused for the 503).

## D-018 — Dependabot majors suppressed; framework upgrades are sprint-planned

**2026-07-07 · dependencies**
Merging PR #16 activated Dependabot (config landed with Work Order F but the
repo had no CI/dependabot before that merge), and it filed its whole backlog at
once: 15 PRs, of which 7 were major framework jumps (react 19, next 16,
tailwindcss 4, eslint 10, tailwind-merge 3, @types/node 26, eslint-config-next
16). Decision (David, 2026-07-07): `.github/dependabot.yml` now ignores
`version-update:semver-major` for the entire npm ecosystem and groups
minor/patch updates into one weekly PR per ecosystem; the 7 major PRs are
closed unmerged. The 8 safe PRs (5 GitHub Actions bumps; autoprefixer,
next-auth, prettier minors/patches) are merged after a `@dependabot rebase` —
their original CI failures were stale runs from 2026-07-03 against the pre-fix
`main` (the pnpm double-pin bug fixed in `f65e36f`), not real breakage.

**Rationale:** Sprint 2 T0 deliberately stays on the Next 14.2.x App Router
line, and CI has no e2e job yet (S2 T3), so a green dependabot check proves
lint/tsc/build only — nowhere near enough verification for a framework major.
Majors move as one deliberate, e2e-netted upgrade bundle instead: Next 15/16 +
React 19 + Tailwind 4 + ESLint 10 + Node 22 LTS/@types/node (Node 20 passed
EOL 2026-04-30), targeted at Sprint 3/4 after e2e runs in CI. Trade-off
accepted: a security fix that ships only in a major is suppressed too — the
non-blocking `pnpm audit` / `pip-audit` CI steps remain the tripwire for that
case.

**Ref:** SPRINT_2.md T0/T3; CLAUDE.md (migrations/e2e gotchas); D-015 (Part F
dependency-audit posture).

**Annotation (2026-07-09 · Sprint 4 · David):** the framework-majors bundle
above executed this sprint EXCEPT its ESLint target. The bundle named ESLint 10;
what shipped is ESLint **9** (9.39.4) on flat config (T3, `bf82fd2`). ESLint 10
is not runnable with any published Next lint stack today —
`eslint-plugin-react` 7.37.5 calls the removed `context.getFilename()` and Next's
compiled babel parser hits an `eslint-scope` `scopeManager.addGlobals` gap — so
v10 is honestly deferred to a future sprint once `eslint-plugin-react` ships v10
support. This supersedes SPRINT_4.md T3's ESLint-10 Definition-of-Done item; the
Dependabot major-suppression posture is unchanged (ESLint 10 stays suppressed
until the ecosystem catches up). CHANGELOG `[3.1.0]` T3 cites this annotation.

## D-019 — Reject reserved/special-use TLDs at domain-approval time

**2026-07-07 · admin**
The admin add-domain route (`POST /admin/clients/{cid}/domains`) now rejects
reserved / special-use domains — RFC 2606/6761 names like `.test`, `.invalid`,
`.localhost` — with a typed 422 (`reason=domain_reserved_tld`, plus friendly
`message`), following the D-016 dict-detail envelope. The check reuses
email-validator's own reserved-name logic (a throwaway `validate_email` probe
via the new `app/security/email_domains.is_reserved_domain` helper) rather than a
hand-rolled TLD list — the exact check pydantic's `EmailStr` runs at
registration. `.example` is NOT reserved and still approves.

**Rationale:** Before this guard, the email validator 422'd special-use TLDs at
self-registration _before_ the domain-approval check, so an admin could approve a
domain (e.g. the demo's `beacon.test`) that no user could ever register on —
approved-but-unregistrable, a silent dead end. Rejecting at approval time fails
loudly at the point of the mistake. The web Management client (`_detail`) was
also reading the wrong error field (`detail` vs the D-016 `error.message`); it now
prefers the typed message so the rejection copy actually surfaces in the form.
The guard is add-time only: rows approved before it (legacy reserved domains)
still list and remove unchanged (C0/additive). `seed_demo.py` was checked — it
only seeds `atlas.example` and never created `beacon.test`, so no seed migration
was needed (s13 find-or-creates `beacon.example` itself).

**Ref:** SPRINT_2.md T9; DECISIONS D-016 (typed-error pattern); D-004/B1
(domain-gated registration); `email-validator` `SPECIAL_USE_DOMAIN_NAMES`.

## D-020 — Auth compensating controls: enforce the real ones, retract the fiction

**2026-07-09 · admin**
README §Risk-acceptance and BUILD_REPORT A07 claimed "30-minute idle timeout"
and "daily forced re-auth" as MFA offsets, and said the deferred
`SHIELD_AUTH_REQUIRE_MFA` / `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` flags "enable
both in v1.x with no code changes". None of that was true: the reauth/idle
config knobs were referenced nowhere and `/auth/refresh` re-issued token pairs
indefinitely with no rotation or ceiling. Sprint 3 T2 makes the claims honest:

- **Forced re-auth ceiling (real):** access + refresh tokens now carry an
  `auth_time` claim (original login time) that rides forward unchanged across
  refreshes. `/auth/refresh` rejects a refresh whose session age exceeds
  `SHIELD_FORCED_REAUTH_SECONDS` (default 24h) with a typed 401
  `reason=reauth_required` (D-016 envelope).
- **Refresh-token rotation (real):** each refresh mints a new refresh token and
  stores its jti on the user (`users.active_refresh_jti`, additive/nullable
  migration 0026, C0). Only the most recently issued refresh token is valid; a
  replayed/rotated-out token is rejected `reason=refresh_reused`. This is a
  **single active session per user** posture — a new login supersedes the prior
  session's refresh token. Acceptable for a consultant-led tool; revisit if
  concurrent multi-device sessions become a requirement.
- **Idle timeout (documented, not new machinery):** the 30-minute refresh-token
  TTL already IS the idle timeout — an idle session cannot refresh past it. We
  document that rather than invent a second timer.
- **Dead flags fail loudly:** `assert_safe_for_runtime` now refuses to boot if
  `SHIELD_AUTH_REQUIRE_MFA` or `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` is true,
  because the enrollment/challenge and email-verification flows do not exist.
  Silently ignoring a security flag is worse than refusing to start.
- **Web:** the NextAuth refresh callback surfaces the reauth/rotation reasons as
  a distinct `REAUTH_REQUIRED_ERROR`; a `SessionExpiryGuard` clears the dead
  session and routes to `/sign-in?reason=session_expired` with friendly copy.

**Why DB rotation, not Redis:** a jti denylist in Redis (T3's territory) would
also work, but the rotating-pair check needs only one nullable column, is fully
testable under the SQLite unit suite with no Redis dependency, and survives
restarts/multi-worker without an outage fail-open/closed dilemma.

**Ref:** SPRINT_3.md T2; DECISIONS D-016 (typed errors); migration 0026;
`app/config.py`, `app/security/jwt.py`, `app/routes/auth.py`.

## D-022 — Erratum: duplicate D-015 heading renumbered to D-021

**2026-07-09 · housekeeping**
Two distinct decisions were both headed `D-015`: the 2026-05-21 multi-tenant
architecture entry and the 2026-06-26 "Part F: harden and ship decisions"
entry. This log is append-only, so the collision is resolved by renumbering
the **second** entry (Part F) to **D-021** with an in-place note at its
heading, and recording the change here. `D-015` now unambiguously means the
multi-tenant decision. Documents written before this erratum that cite
"D-015 (Part F)" refer to D-021.
**Rationale:** The Sprint 3 repo audit (docs/audits/2026-07-08-repo-audit.md)
flagged the duplicate heading; two entries sharing a D-number breaks the
log's whole purpose as a citation target. Same remedy as the Sprint 2
D-018→D-019 renumber.
**Ref:** SPRINT_3.md T6; DECISIONS D-015, D-021.

## D-023 — Supersession: D-005/D-006 reviewer role and release flow removed

**2026-07-09 · auth/workflow**
D-005 (deployment-wide reviewer assignment) and D-006 (deliverable approval
flow: admin marks final → reviewer approves → admin releases to client) are
**superseded**. Work Order A1/A3 removed the reviewer role entirely — the
`UserRole` enum is now `admin` / `client` only, multiple admins all see and
do the work with no separate approval gate — and the mark-final /
release-to-client workflow was removed with it. Deliverables are generated,
versioned, and downloaded directly by admins; there is no release gate in
the current code. Sprint 5 may reintroduce a deliberate release-to-client
step as a client-facing feature; if it does, that will be a new decision,
not a revival of D-006.
**Rationale:** Code reality has diverged from the two entries since the v2
work order merged (PR #1); docstrings and OpenAPI summaries still claiming a
reviewer role were purged in Sprint 3 T6. Recording the supersession keeps
the append-only log honest without rewriting history.
**Ref:** Work Order A1/A3 (via PR #1); SPRINT_3.md T6; `app/models/user.py`
(UserRole); DECISIONS D-005, D-006.

---

## D-024 — Multi-provider LLM egress: provider-configurable adapters below the seam

**2026-07-09 · ai/architecture**
Add live `OpenAIProvider` and `GeminiProvider` beside `AnthropicProvider` in
`app/ai/llm.py`, selected by `_build_provider` on `SHIELD_LLM_PROVIDER`.
Adapters are thin `httpx` translators (OpenAI chat/completions, Gemini
`generateContent`) — no SDK dependency; Anthropic keeps its lazy-imported SDK.
New settings `OPENAI_API_KEY` / `GEMINI_API_KEY` (empty default); a missing key
for the selected provider raises the same loud `RuntimeError` at construction as
Anthropic. `SHIELD_LLM_MODEL` stays the single model knob (`gpt-*`, `gemini-*`,
`claude-*`). `azure_openai` / `bedrock` / `local` remain valid config values with
no adapter yet and raise a loud not-implemented `RuntimeError`. Fixture mode
stays the default and byte-identical deterministic (D-017 untouched).
**Rationale:** Master Spec §4.4 requires the provider be env-configurable and
never hardcoded. Everything that enforces the security posture — redaction, the
`llm_calls` audit row (provider/model/client_id), "AI suggests, code computes" —
lives ABOVE the provider seam and is unchanged; adapters only translate
prompt+payload → provider REST API → text back. FedRAMP deployments pick the
provider whose service sits inside their authorization boundary; fixture mode
keeps the whole stack exercisable offline with zero egress.
**Ref:** Master Spec §4.4, §12; SPRINT_4.md T6; `app/ai/llm.py`,
`app/config.py`, `tests/unit/test_llm_providers.py`; DECISIONS D-017.

---

## D-025 — Deliverable release-to-client: a new admin-only release action

**2026-07-10 · workflow/deliverables**
Reintroduce an explicit release-to-client step for deliverables. Migration
`0028` adds `deliverables.released_at` (nullable DateTime) + `released_by`
(nullable FK `users.id`, SET NULL); old rows parse as UNRELEASED (C0). A new
admin-only route `POST /{service}/deliverables/{id}/release` (one per service,
behind the shared `app/deliverable_release.release_deliverable` helper) requires
`finalized_at` set (typed 409 `not_finalized`, D-016), is idempotent (a second
release is a logged no-op, not an error), and writes a `*.deliverable.released`
audit row. Clients read released deliverables via `GET /clients/{cid}/deliverables`
(tenant-enforced, 404 on mismatch) and download their artifacts through the
existing artifact-download path, which now also admits a client for a format of
a RELEASED deliverable of their own tenant — and nothing else.
**Rationale:** Master Spec §12 requires "released to client = consultant
explicitly released; until then the client sees nothing." D-023 anticipated
this as a NEW decision, explicitly NOT a revival of the removed D-005/D-006
reviewer→approve→release gate: there is no separate reviewer role and no
approval hand-off — one admin action flips visibility. Release state is the
sole gate for every client-facing surface built this sprint (`/home`,
`/documents`, the value-loop card), so unreleased and draft work stays
invisible to clients by construction.
**Ref:** Master Spec §6.7, §12; SPRINT_5.md T1; `app/models/deliverable.py`,
`app/deliverable_release.py`, `app/routes/clients.py`, `app/routes/artifacts.py`,
`alembic/versions/0028_deliverable_release.py`,
`tests/unit/test_deliverable_release.py`; DECISIONS D-023, D-016.

## D-026 — Live-AI enablement: `anthropic` is a real runtime dep + a live-mode boot preflight

**2026-07-12 · ai/config**
Make the live-AI path actually runnable rather than a config that 500s on first
use. Three changes: (1) declare `anthropic>=0.40,<1` in `apps/api`
dependencies — the `AnthropicProvider` lazy-imports `from anthropic import
Anthropic` (`app/ai/llm.py`), so an undeclared SDK surfaced only as an
`ImportError` on the first live Run-AI; it is now a real runtime dependency and
the image must be rebuilt (a plain restart won't install it). (2) Replace the
stale default model `claude-opus-4-7` (invalid → 404) with `claude-sonnet-5`
in both `app/config.py` and `docker-compose.yml`. (3) Add a live-mode boot
preflight: `Settings.live_llm_readiness()` is the single source of truth for
"will a live call succeed" — anthropic needs its key AND an importable SDK,
openai/gemini (httpx adapters) need only their key, every other provider value
has no adapter, and the model must not be a known placeholder. It never raises;
`assert_safe_for_runtime()` wraps a false result in a loud `RuntimeError` at
boot (lifespan `app/main.py`), and `GET /admin/ai-status` surfaces the same
detail to operators. Fixture mode is entirely unaffected.
**Rationale:** FAIL LOUDLY at boot beats a 404/500 mid-engagement. The
2026-07-12 manual smoke PROVED the path works end-to-end against a live
`claude-sonnet-5` call (2.6s, redaction stripped `{client_org:2,name:2,email:2}`,
correct `llm_calls` row, no PII egress) — the only blockers were the missing
dep, the stale model, and the absent preflight. The SDK-importable check
guards specifically against the "declared but image not rebuilt" trap.
**Ref:** SPRINT_6.md T0; `apps/api/pyproject.toml`, `app/config.py`,
`app/main.py`, `app/routes/admin.py`, `docker-compose.yml`,
`tests/unit/test_config.py`; DECISIONS D-017, D-024.

## D-027 — Real TOTP MFA: a single custom-JWT enroll/verify/login-challenge flow

**2026-07-12 · auth**
Ship real multi-factor auth on the existing custom HS256-JWT auth stack rather
than deferring to a Keycloak federation. RFC 6238 TOTP (SHA1 / 6-digit /
30-second), implemented against the stdlib (`app/security/totp.py`) and locked
to the RFC's published test vectors — no third-party OTP dependency. Three
endpoints on `routes/auth.py`: `POST /auth/mfa/enroll` (returns an otpauth
provisioning URI + secret), `POST /auth/mfa/verify` (confirms a code, flips
`users.mfa_enrolled`, issues 10 one-time recovery codes shown exactly once),
and `POST /auth/mfa/verify-login` (completes the login challenge). When a user
has MFA enrolled, `/auth/login` returns a short-lived (`jwt_mfa_pending_ttl`,
default 5 min) `mfa_pending` token INSTEAD of the access+refresh pair; that
token authorizes nothing but `verify-login`, which accepts a current TOTP OR a
single-use recovery code and then mints the real pair. The verify endpoints are
rate-limited via the existing per-account auth limiter.

**At-rest secrets.** The TOTP secret is Fernet-encrypted (`cryptography`,
already transitive) with a key derived from `JWT_SIGNING_SECRET` — no new
secret to provision; rotating the signing secret invalidates stored MFA secrets
(users re-enroll), which is a loud, correct failure rather than a silent
decrypt. Recovery codes are Argon2id-hashed (a dedicated hasher, since they are
shorter than the 12-char password policy) and never stored or logged in
plaintext. Migration `0030` is additive/SQLite-safe (C0): `users.mfa_totp_secret`
is nullable so old rows parse as "not enrolled", and `user_recovery_codes` is a
new cascade-deleted table.

**Flag semantics change.** The old `config.py` boot-refusal on
`SHIELD_AUTH_REQUIRE_MFA=true` (which refused to start because no flow existed)
is removed. The flag now GATES enforcement: an enrolled user is always
challenged regardless of the flag; with the flag ON, a not-yet-enrolled user
still receives a session (first enrollment necessarily needs one) but the login
result carries `mfa_enrollment_required` so the UI routes them to enroll. The
email-verification boot-refusal stays until T5 lands that flow.

**Web.** The NextAuth Credentials provider gains an optional `totp` credential:
the sign-in form submits email+password first, and on an `mfa_required` signal
reveals a code field and re-submits; `authorize` completes the challenge
server-side (re-running `/auth/login` for a fresh pending token, then
`verify-login`) so the pending token never reaches the browser. A net-new
account-page enrollment section (`MfaEnrollment.tsx`) drives enroll → confirm →
recovery-code display through server-side proxies. Keycloak stays dormant; when
v1.x federates auth it replaces this flow behind the same `aud=shield-api`
claim.

**Rationale:** MFA is a FedRAMP-Moderate baseline control; a config flag that
refused to boot was worse than a real control. The single-JWT design keeps the
whole flow in one deterministic, testable seam ("AI suggests, code computes" is
untouched — this is pure crypto). TDD: enroll → verify → login-with-TOTP happy
path, wrong/expired code rejected, single-use recovery-code login, and
flag-off = no challenge for non-enrolled users (back-compat).
**Ref:** SPRINT_6.md T4; `apps/api/alembic/versions/0030_mfa_totp.py`,
`app/security/totp.py`, `app/models/user.py`, `app/models/user_recovery_code.py`,
`app/security/jwt.py`, `app/routes/auth.py`, `app/config.py`,
`app/schemas/auth.py`, `tests/unit/test_totp.py`, `tests/unit/test_mfa_routes.py`,
`tests/unit/test_auth_reauth.py`, `apps/web/src/lib/auth/options.ts`,
`apps/web/src/components/auth/{SignInForm,MfaEnrollment}.tsx`,
`apps/web/src/app/account/page.tsx`; DECISIONS D-020.

## D-028 — Real email verification + password reset over SMTP/MailHog

**2026-07-12 · auth**
Ship real email-address verification and self-service password reset on the
existing custom-JWT auth stack (MailHog in dev; any SMTP host in prod). Four new
endpoints on `routes/auth.py`: `POST /auth/verify-email` (consumes a token and
stamps `users.email_verified_at`), `POST /auth/resend-verification`,
`POST /auth/forgot-password`, and `POST /auth/reset-password`. Registration now
mints a verification token and sends the email as part of the same transaction.
All four are rate-limited via the existing per-account auth limiter.

**Token model.** A new additive/SQLite-safe migration `0031` adds an
`email_tokens` table holding only the SHA-256 hash of each opaque token (the raw
token — ~256 bits from `secrets.token_urlsafe` — lives only in the emailed
link), a `purpose` (`email_verify` | `password_reset`), an `expires_at`, and a
`used_at`. Tokens are single-use (stamped `used_at` on success only, so a failed
action leaves them replayable within their window) and time-bounded
(verification 24h, reset 1h). SHA-256 is deliberate, not a KDF: these are
already high-entropy, so lookup must be one indexed query and a slow hash buys
nothing. A completed reset voids every other outstanding reset token for the
user, clears any lockout, and nulls `active_refresh_jti` so live sessions must
re-auth.

**No enumeration.** `resend-verification` and `forgot-password` always return an
identical uniform message whether or not the account exists; only a real account
produces a token/email. `verify-email` / `reset-password` fail on the token
itself (typed `invalid_token`), never on account existence.

**Delivery gating + flag semantics.** The SMTP sender is gated by
`SHIELD_EMAIL_DELIVERY_ENABLED` (default off): with delivery off the send is a
logged no-op (subject/recipient only — never the token-bearing body), so the
token flow still works in dev/tests without MailHog; with delivery on but no
`SMTP_HOST`, `assert_safe_for_runtime` refuses to boot rather than silently drop
mail. The old `config.py` boot-refusal on `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY=true`
is removed (mirroring D-027): the flag now GATES login enforcement — an
unverified user is rejected at `/auth/login` with a typed `email_not_verified`
403 when the flag is on, and login proceeds normally when off.

**Web.** Net-new `/verify-email`, `/forgot-password`, and `/reset-password`
pages (+ server proxies) drive the flows; the verify page reads the token from
`?token=` and auto-submits, offering an enumeration-safe resend on failure. A
"Reset it" link is added to sign-in.

**Rationale:** email verification + password reset are baseline account-security
controls; a flag that refused to boot was worse than a real flow. The design
keeps the whole thing in the same deterministic, testable seam as the rest of
auth ("AI suggests, code computes" untouched). TDD: register→verify happy path,
bad/expired/used token rejected, enumeration-safe resend + forgot, reset changes
the password and is single-use, weak-password policy enforced, and the login
gate blocks-then-allows across the flag.
**Ref:** SPRINT_6.md T5; `apps/api/alembic/versions/0031_email_tokens.py`,
`app/models/email_token.py`, `app/email/{sender,tokens}.py`,
`app/routes/auth.py`, `app/config.py`, `app/schemas/auth.py`,
`tests/unit/test_email_verification.py`, `tests/unit/test_auth_reauth.py`,
`apps/web/src/app/{verify-email,forgot-password,reset-password}/page.tsx`,
`apps/web/src/components/auth/{VerifyEmailClient,ForgotPasswordForm,ResetPasswordForm}.tsx`,
`apps/web/src/app/api/proxy/auth/{verify-email,resend-verification,forgot-password,reset-password}/route.ts`,
`e2e/smoke/s21-email-verify.spec.ts`; DECISIONS D-020, D-027.

---

## D-029 — Vertex AI via Application Default Credentials as the GCP live path

**2026-07-15 · ai/architecture**
Add a live `VertexProvider` beside `GeminiProvider` in `app/ai/llm.py`, selected
by `SHIELD_LLM_PROVIDER=vertex`. It calls the regional Vertex endpoint
`https://{region}-aiplatform.googleapis.com/v1/projects/{project}/locations/{region}/publishers/google/models/{model}:generateContent`
and authenticates with **Application Default Credentials — NO static API key**.
New settings `GCP_PROJECT_ID` (empty default) and `GCP_REGION`
(`us-central1`); `google-auth>=2,<3` is a real api dependency (rebuild the
image). ADC is obtained via
`google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])`,
refreshed lazily, and sent as an `Authorization: Bearer` header. The bearer
token NEVER appears in logs, `llm_calls.error_message`, or exception text — it
rides the header, not the URL, so an `HTTPStatusError` (which embeds only the
request URL) cannot leak it (a unit test locks this; mirrors the Gemini
key-in-header lesson). `gemini` (API key, `generativelanguage`) and `vertex`
(ADC, `aiplatform`) speak the identical `generateContent` schema, so the
body-build/parse are factored into shared helpers and the two remain **distinct
providers** for two distinct GCP postures.

**Boot preflight (D-026 parity).** `live_llm_readiness()` for `vertex` requires
`GCP_PROJECT_ID` set, `google-auth` importable, AND ADC resolvable
(`google.auth.default()` succeeds) — a loud `RuntimeError` at boot otherwise, not
a 500 on the first Run-AI. `/admin/ai-status` and the `/ready` LLM check inherit
it. Fixture mode is unaffected.

**Compose / credentials.** The api service bind-mounts the host gcloud config
dir **read-only** (`GCLOUD_CONFIG_DIR`, default `$HOME/.config/gcloud`; this
Windows box sets `%APPDATA%\gcloud` in the gitignored `.env`) and
`GOOGLE_APPLICATION_CREDENTIALS` points at the ADC file inside it. Credentials
are never copied into the repo or the image — the read-only mount is the only
path in.

**Rationale:** Dave's GCP posture (inherited from kentro-cloud-modernization) is
Vertex via ADC with no `AIza…` keys committed anywhere. Feasibility was proven
2026-07-13 — a direct ADC-authenticated `generateContent` call to
`us-central1-aiplatform` / `kentro-cloudmod-dev` / `gemini-2.5-flash` returned
HTTP 200. The existing `gemini` adapter only speaks the API-key
`generativelanguage` path, so it cannot use this machine's credentials; Vertex is
the FedRAMP-relevant path (the model runs inside the GCP authorization
boundary). Everything above the seam — redaction, the `llm_calls` audit row,
"AI suggests, code computes" — is untouched.
**Addendum (2026-07-15, T1 live sweep hardening).** The first real Vertex sweep
(all five purposes, ADC-only) surfaced two defects no keyless unit test had
exercised, both now fixed and `pytest -m unit` locked: **(1)** `google-auth`'s
token-refresh transport (`google.auth.transport.requests.Request`) hard-requires
`requests`, so the dep is now `google-auth[requests]>=2,<3` — without the extra
the first live token refresh raised `ImportError` (the unit test mocks
`_bearer_token`, so it never hit the real transport). **(2)** gemini-2.5
"thinking" spends an unbounded, run-variable slice of `maxOutputTokens` before
the visible answer and truncated the longer drafts mid-JSON;
`_parse_generate_content` silently returned the half-doc as "completed" and it
died downstream as an opaque `JSONDecodeError`. Fix: `_parse_generate_content`
now **fails loudly** on any non-`STOP` `finishReason` (marks the `llm_call`
failed with the real reason); the shared output cap is raised 4096→8192; and a
bounded `thinkingConfig.thinkingBudget` (2048) is sent for gemini-2.5+ models
only (the gemini-1.5 API-key path, which rejects `thinkingConfig`, is untouched).
All five purposes then passed live (vertex/gemini-2.5-flash).

**Ref:** Master Spec §4.4, §12; SPRINT_7.md T0/T1; `app/ai/llm.py`, `app/config.py`,
`apps/api/pyproject.toml`, `docker-compose.yml`,
`tests/unit/test_llm_providers.py`, `tests/unit/test_config.py`,
`tests/live/test_live_ai.py`, `SMOKE_TEST.md` §14/§14.1; DECISIONS D-024, D-026.

## D-030 — Client release notification email: best-effort notify, release is source of truth

**Decision (Sprint 7 T2).** When a consultant releases a finalized deliverable
(the shared `release_deliverable` helper behind all four service routes), and
`SHIELD_EMAIL_DELIVERY_ENABLED` is on, SHIELD emails **every active client-role
user of that deliverable's tenant** a notification carrying the service, the
deliverable title/version, and a link to `{WEB_BASE_URL}/documents`. Recipient
selection is `role == client AND client_id == <tenant> AND is_active` — cross-
tenant users and consultants (admins) are never notified.

**Best-effort semantics.** The notification is sent **after** the release is
committed, and the release is the **source of truth**. With delivery off the
release proceeds exactly as v3.3.0 — a loud skip log ("notify skipped, delivery
disabled"), no send attempted. With delivery on, each recipient send is wrapped:
a per-recipient SMTP failure is logged **loudly** (with the deliverable id,
recipient, and error) and the release **still stands** — a notification failure
must never roll back a release the consultant already performed. A summary log
records recipients / sent / failed counts either way.

**Rationale.** Sprint 5 (D-025) shipped the release action but deferred the
client notification pending a real sender; Sprint 6 T5 shipped
`app/email/sender.py`. Wiring the notification into the single shared release
helper means all four services plus the risk register notify identically. The
"loud but non-blocking" failure mode is the correct reading of "fail loudly":
the failure IS surfaced (logged with full context), but the durable state the
user asked for (the release) is not undone by a downstream best-effort side
effect — that would be the worse lie.

**Ref:** Master Spec §12; SPRINT_7.md T2; `app/deliverable_release.py`,
`app/email/sender.py`, `tests/unit/test_release_notification.py`; DECISIONS
D-025, D-028.

## D-031 — Draft discard is an admin-only soft-delete state transition

**Decision (Sprint 9 T0).** Each of the four assessment services gains a
`POST .../{id}/discard` route beside its existing `/approve` sibling (all four
admin-only via `_admin_required`). A new `DISCARDED` value joins each status
enum. The columns are already `native_enum=False` `String(16)` with no CHECK
constraint (verified against migration 0009), so this is code-only with no
migration.

**State machine.** Only a `DRAFT` is discardable: it flips to `DISCARDED` and
writes exactly one audit row (`capability_list.discarded`,
`csf.assessment.discarded`, `attack.assessment.discarded`,
`zt.assessment.discarded`). A second discard on an already-discarded resource
returns an idempotent 200 with no second audit row. A `SUBMITTED` CSF or ZT
assessment, or any `APPROVED`/`RELEASED` resource, returns a typed 409
`{reason: "not_discardable"}` (the D-016 envelope): once a client formally
submits, or an admin approves, destruction is off the table. A client-role POST
is a 403; an unknown or cross-tenant id is a 404. Client-touched CSF/ZT drafts
stay discardable, and the audit details carry the answered-row count so the web
confirm dialog (T1) can warn about client-entered data.

**The version trap.** A discarded row keeps its version under the
`(service_id, version)` unique constraint, so the two "latest" reads split. The
per-service `_latest_*` helpers now exclude `DISCARDED` (covering GET latest,
the draft-reuse guard, and every downstream consumer), but the next-version mint
switches to a dedicated `select(func.max(version))` that counts discarded rows.
Without that split, discarding a v2 draft over an approved v1 would mint v2
again and raise an `IntegrityError` on the first re-extract.

**Hidden "latest" consumers.** The Risk Register has its own generic `_latest`
feeding the gate and finding-gather; it grew an `active_only` flag so a
discarded highest-version assessment no longer unlocks the gate or supplies
findings (RiskRegister itself has no discard state, so those callers leave the
flag off). The client engagement cards (`intake._latest_assessment_status`) now
report the latest non-discarded status, reading `None` for a discarded-only
service rather than the word "discarded".

**Concurrency contract.** The discard write is a conditional
`UPDATE ... WHERE status = 'draft'`; the rows-affected count drives the
200/idempotent/409 branch, so two transactions cannot both observe `DRAFT` and
proceed. Every child mutation (the per-row PATCH routes) and each `run-ai` guard
rejects a parent that is not in its editable state, so a stale-tab answer edit
or an AI run racing a discard loses loudly with a typed 409 instead of writing
into a discarded parent. An AI run that already loaded a `DRAFT` parent re-reads
its status before committing its suggestions.

**Rationale.** A consultant who extracts or opens the wrong draft had no way to
retract it: the draft-reuse guard would hand the same stale draft back forever.
Discard is a soft delete (the row and its audit trail survive) rather than a
hard `DELETE`, which keeps the append-only audit history intact and leaves
un-discard as a future affordance. Uploaded intake artifacts survive a
tech-debt discard on purpose: re-extracting from the same document is the whole
point of the escape hatch.

**Ref:** Master Spec §11, §15; SPRINT_9.md T0; `app/models/capability.py`,
`app/models/csf_assessment.py`, `app/models/attack_assessment.py`,
`app/models/zt_assessment.py`, `app/routes/tech_debt.py`, `app/routes/csf.py`,
`app/routes/attack.py`, `app/routes/zt.py`, `app/routes/risk.py`,
`app/routes/intake.py`, `tests/unit/test_discard_draft.py`; DECISIONS D-016.

## D-032 — Hybrid Keycloak SSO: a flag-gated token exchange, never a bearer

**Decision (Sprint 9 T4).** `POST /auth/oidc/exchange` is the single door for a
Keycloak identity. Keycloak owns the browser login and MFA; the web app hands the
API the resulting Keycloak ACCESS token, the API verifies it once and mints a
plain D-020 HS256 pair in its place. A Keycloak token is never accepted as an API
bearer — the existing `verify_token` path is unchanged, and the exchange output is
an ordinary SHIELD pair that flows through refresh/expiry/lockout untouched. The
whole feature is behind `SHIELD_AUTH_OIDC_ENABLED`, default OFF; with the flag off
the route returns a typed 403 `oidc_disabled` and no Keycloak network is touched.

**Boot preflight, no boot-time network.** `Settings.oidc_readiness()` mirrors
`live_llm_readiness()`: a config-shape check (non-empty http(s) `keycloak_issuer`
and `keycloak_jwks_url`, non-empty `keycloak_audience` and `keycloak_client_id`)
wired into `assert_safe_for_runtime`, so the flag on with an incoherent config
fails loudly at startup. It makes NO network call — the api has no
`depends_on: keycloak` and must not crash-loop on a cold `compose up` (the D-026
precedent). A real Keycloak outage surfaces as a runtime 503, not a boot failure.

**Verification (`app/security/oidc.py`).** RS256 only — the algorithms list is
the alg-confusion guard, so an HS256 token (even one signed with the app's own
secret) is rejected. `iss` is pinned to `keycloak_issuer`, `aud` to
`keycloak_audience`, and `exp`/`iat`/`sub` are required. JWKS keys are cached
process-wide (300s TTL, `threading.Lock`); a token bearing an unknown `kid`
forces exactly one refetch to pick up a Keycloak key rotation, then rejects —
never an unbounded loop. The raw fetch is isolated in `_fetch_jwks` so unit tests
monkeypatch it and touch no network; `python-jose[cryptography]` and `httpx`
already ship, so no new dependency.

**azp, not just aud (Codex finding).** `aud` names the resource server
(`shield-api`), so a correctly signed token minted to a _different_ Keycloak
client would still satisfy the audience check. The exchange additionally requires
`azp == keycloak_client_id`, rejecting a token that was not issued to our web
client with a 401 `oidc_token_invalid`.

**Local account authority.** Match is by normalized verified email against an
EXISTING local user — no JIT provisioning (`oidc_no_local_account` 403 for an
unknown identity). The minted pair's role comes from `user.role`, so a token
claiming `roles: ["admin"]` for a client-role user still mints CLIENT tokens. The
Keycloak subject is TOFU-bound: `users.keycloak_sub` (migration 0032, nullable
and UNIQUE, additive C0) is stamped on first exchange and a later exchange whose
`sub`
differs is rejected 403 `oidc_sub_mismatch`. The exchange bypasses local TOTP MFA
(Keycloak owns MFA on this path), does NOT consult the local password lockout
(Keycloak's `bruteForceProtected` owns SSO lockout — honoring the local lock would
let a password-endpoint attacker DoS SSO users), and does NOT stamp local
`email_verified_at`. It DOES reuse the shared `_register_successful_login` +
`_issue_pair` bookkeeping, so lockout counters clear and `last_login_at` stamps
exactly as on the credentials path.

**Failure matrix (all typed dict-detail, D-016).** 403 `oidc_disabled` /
401 `oidc_token_invalid` (bad signature/iss/aud/expiry/azp/unknown-kid) /
503 `oidc_jwks_unavailable` (names the URL + flag) / 401 `oidc_claims_missing` /
403 `oidc_email_unverified` / 403 `oidc_no_local_account` / 403
`oidc_user_inactive` / 403 `oidc_sub_mismatch`.

**Rationale.** SHIELD's custom-JWT stack is the source of truth for authz and
session lifetime; federating the login without ceding either means verifying the
IdP token at one auditable boundary and re-minting locally, rather than trusting a
foreign bearer across the app. Flag-gating keeps every existing credentials e2e
green and the feature dormant until a deployment turns it on.

**Ref:** Master Spec §4.5; SPRINT_9.md T4; `app/config.py`, `app/security/oidc.py`,
`app/routes/oidc.py`, `app/main.py`, `app/schemas/auth.py`, `app/models/user.py`,
`alembic/versions/0032_user_keycloak_sub.py`, `tests/unit/test_oidc_exchange.py`,
`tests/unit/test_config.py`; DECISIONS D-016, D-020, D-026.

## D-033 — Destructive-by-design automation is opt-in-gated

**Decision (Sprint 9 T8).** The demo-reset scripts and the demo-journey e2e spec
automate a workflow that destroys local state (`docker compose down -v` wipes the
Postgres, MinIO, Redis, and Keycloak volumes). Nothing about that automation may
fire implicitly. Three rules hold it in place:

1. **Reset specs self-skip by default.** `e2e/demo/demo-journey.spec.ts` lives
   under the `testDir: "."` root, so the default `npx playwright test` run
   discovers it. A module-scope `test.skip(process.env.SHIELD_DEMO_SMOKE !== "1")`
   guard makes every test in the file skip unless the operator opts in, so the
   default suite's pass count is unchanged and the spec never runs against a
   stack it did not just reset (a half-reset or dev-mode stack would report
   misleading results).
2. **Destructive scripts never run implicitly.** `scripts/demo-reset.sh` /
   `.ps1` are invoked by hand. A new `--demo` / `-Demo` flag overlays
   `docker-compose.demo.yml` (the production web image) on every compose call;
   the plain invocation drives the base compose only. The flag changes which
   stack is reset, never whether a reset happens.
3. **CI isolation is the only unattended venue.** The reset runs unattended only
   on an isolated CI runner (T9), where `down -v` cannot touch a developer's
   volumes or a shared host.

**Fail loud, not silent (Codex finding).** The old web-readiness poll gave up
after 120 seconds and printed the success banner anyway, so a failed production
build read as a clean reset until Playwright died with an opaque error later. The
poll now exits non-zero on timeout and dumps `docker compose logs web` on the way
out, in both the sh and ps1 scripts. The web port is resolved from `WEB_PORT`
(env, then the repo-root `.env`, then 3000) so the wait probes the port the stack
actually publishes on.

**Ref:** SPRINT_9.md T8; `scripts/demo-reset.sh`, `scripts/demo-reset.ps1`,
`e2e/demo/demo-journey.spec.ts`, `docker-compose.demo.yml`, `README.md`,
`SMOKE_TEST.md`; DECISIONS D-016.

## D-034 — Open self-registration with tenant auto-provisioning

**Decision.** A standard user can create their own account with no admin
involvement. This supersedes the domain-approval half of D-004/D-016/D-019: after
the first registrant (still the bootstrap platform admin, `client_id=None`),
`POST /auth/register` no longer rejects a signup whose email domain an admin has
not pre-approved. Instead it auto-provisions the tenant:

1. **Personal mailbox providers** (gmail, outlook, … — `is_generic_provider`) are
   now **allowed**, and each such signup gets its **own private `Client`** with
   **no `ClientDomain` mapping**. Personal emails are never grouped — two
   `@gmail.com` users must never share a workspace.
2. **A known approved company domain** joins that existing `Client` (unchanged
   coworker grouping).
3. **An unknown company domain** stands up a **new `Client`** and inserts a
   `ClientDomain` mapping, so later coworkers on the same domain auto-join it.
   The first user of a freshly provisioned org is stamped its `primary_poc`.

Role is unchanged (`admin` for the first user, `client` for everyone after). No
new migration — only `Client`/`ClientDomain` rows are created at runtime. Email
verification stays **not enforced** (`SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` off by
default); a verify token is still minted and sent as before. Auto-provisioned
orgs carry a placeholder `legal_name` (the domain, or the user's display name for
personal emails) that the org refines through the intake wizard.

**Concurrency.** Two users on the same brand-new company domain can race: both
resolve "no match" and both try to insert the same unique `domain`. The loser's
commit raises `IntegrityError` on `uq_client_domain_domain`; `register()` catches
it, rolls back, and retries once — on the retry the domain now exists, so the
user joins the just-created org instead of erroring. (Same class of unique-
constraint race as the Sprint 9 "version trap".)

**Security tradeoff (accepted).** Opening registration removes the compensating
control D-016 leaned on — that an attacker had to already control an
approved-domain mailbox to probe account existence via the friendly
`email_exists` 409. We keep the friendly duplicate-email copy (the D-016 UX the
product wants) and rely on the compensating controls D-004 already names: per-IP
and per-account rate limiting (`limiter.enforce_auth`), account lockout, short
JWT TTLs, idle timeout, forced re-auth. The **login** path keeps its stricter
enumeration-resistant posture (unchanged).

**Ref:** `apps/api/app/routes/auth.py` (`register`,
`_resolve_registration_tenant`, `_provision_self_serve_client`);
`apps/api/app/security/email_domains.py`; `apps/web/src/app/sign-up/page.tsx`;
`apps/web/src/components/auth/SignUpForm.tsx`;
`apps/api/tests/unit/test_auth_routes.py`;
`apps/web/src/components/auth/SignUpForm.test.tsx`;
`e2e/smoke/s1-signup-errors.spec.ts`; supersedes the domain-gate half of D-004,
D-016, D-019.

## D-035 — Client-facing executive dashboards, release-gated on the deliverable

**Decision.** A released service now produces an interactive, client-facing
executive dashboard (Design Mockup §9, Master Spec §2.4/§6.5, IMPLEMENTATION.md
C5/D2 — previously unbuilt). MITRE ATT&CK Coverage ships first as the reference
vertical; Zero Trust, Tech Debt, and the Risk Register follow the same pattern.

Key choices:

1. **Release-gated on the released _deliverable_, not the assessment status.** The
   client read endpoint `GET /clients/{client_id}/attack/{service_id}/dashboard`
   reuses `_released_service_ids_by_kind()` (the same §12 gate the value summary
   uses) and reads the latest finalized (APPROVED/RELEASED) assessment's coverage
   rows. This deliberately sidesteps a latent gap: `release_deliverable()` never
   flips the per-service _assessment_ to `RELEASED`, so the pre-existing admin
   `assessments/latest` client guard (`status == RELEASED`) can never pass for a
   client. Gating on the deliverable makes the dashboard visible exactly when the
   downloadable report is, with no change to the shared release flow. (Flipping
   the assessment to RELEASED on release remains a possible future consistency
   cleanup — out of scope here.) **SUPERSEDED by D-046 (2026-08-17):** release
   now does flip the parent, and the deferral above turned out to be load-bearing
   — it left the stage bar reporting a released service as still needing release,
   and Tech Debt's mutability lock as dead code. The gate chosen in this decision
   (the released deliverable, not parent status) is unchanged and still correct.
2. **"AI suggests, code computes" holds.** Every number is recomputed by the pure
   `app/attack/analytics.py::compute()` engine over frozen coverage rows — no LLM.
   Blind-spot cards are derived from real `gap` techniques + their stored
   `rationale`; the mockup's curated "executive recommendations" prose (fabricated
   narrative) is intentionally NOT reproduced. AI-generated narrative is a
   deferred follow-up.
3. **Faithful dark surface, charts bundled.** The dashboard reproduces the
   mockup's dark executive style (self-contained inline styling, distinct from the
   app's light shell). `chart.js` + `react-chartjs-2` were added and the two
   charts are dynamically imported with `ssr:false` (Chart.js is client-only);
   bundled, not CDN.
4. **Tenant isolation unchanged.** The endpoint is `current_client`-scoped and
   404s (never 403) on a tenant/id mismatch, matching the other client-portal
   routes.

**Ref:** `apps/api/app/routes/clients.py` (`attack_dashboard`,
`_latest_released_deliverable`), `apps/api/app/schemas/clients.py`,
`apps/api/app/attack/analytics.py`; `apps/web/src/app/dashboards/attack/[serviceId]/page.tsx`,
`apps/web/src/components/dashboards/attack/*`, `apps/web/src/lib/dashboards/attack.ts`;
`apps/api/tests/unit/test_attack_dashboard.py`,
`apps/web/src/lib/dashboards/attack.test.ts`,
`e2e/smoke/s27-attack-dashboard.spec.ts`. Mockups:
`reference-docs`/Atlas dashboard HTML set.

**Update — all four dashboards shipped.** The same pattern was extended to the
other three services (each: a release-gated client read endpoint over the
existing engine + a faithful dark dashboard + pure transforms + backend/vitest/
e2e tests):

- **Zero Trust** — `GET /clients/{cid}/zt/{sid}/dashboard` over `app/zt/scoring.py`
  (`compute` run twice for current + target). Current-vs-target maturity radar +
  per-pillar deep dive with lowest-scored capabilities as focus areas.
  `components/dashboards/zt/*`, `lib/dashboards/zt.ts`, `test_zt_dashboard.py`,
  `s28-zt-dashboard.spec.ts`.
- **Tech Debt** — `GET /clients/{cid}/tech-debt/{sid}/dashboard` over the released
  `CapabilityList`. Spend-by-category bar, tool-sprawl donut, functional
  redundancies (dispositions), identified savings (CUT items, floor when a cost is
  missing), full inventory. `components/dashboards/techDebt/*`,
  `lib/dashboards/techDebt.ts`, `test_tech_debt_dashboard.py`,
  `s29-tech-debt-dashboard.spec.ts`.
- **Risk Register** — `GET /clients/{cid}/risk/dashboard`. Client-LEVEL (not
  per-service) and gated on the register's `finalized_at` (the register has no
  per-service Deliverable), reached via a link on `/documents`. 5×5 likelihood×
  impact matrix (code-derived tier via `app/risk/engine.py::matrix_counts`), tier
  mix, per-axis bars, full register. `components/dashboards/risk/*`,
  `lib/dashboards/risk.ts`, `test_risk_dashboard.py`, `s30-risk-dashboard.spec.ts`.

Shared dark primitives live in `apps/web/src/components/dashboards/shared.tsx`.
The mockups' curated prose (per-pillar narrative, roadmaps, reduction plans,
governance/executive-summary sections) is intentionally NOT reproduced — every
figure is engine-derived, no fabricated narrative (AI narrative deferred). NIST
CSF has no mockup and no dashboard yet.

## D-036 — Tenant and user removal is soft, and login honours `is_active`

**Decision (seven-issue pass, issues 3 + 7).** The admin console can now remove a
client tenant and deactivate a user, and both are **soft** removals following the
existing `archive_service` precedent — never a hard delete:

    DELETE /admin/clients/{cid}        archive a tenant (all data retained)
    GET    /admin/clients/{cid}/users  list a tenant's users
    PATCH  /admin/users/{uid}          deactivate / reactivate a user

Archiving stamps a new nullable `client.archived_at` (migration 0033, additive
and SQLite-safe per the C0 pattern) and drops the tenant from the client list and
the intake org index, while assessments, deliverables and the audit trail stay
intact. Consultant-led engagements are the reason: a removed tenant's assessment
history is exactly what must survive removal.

Two supporting choices:

1. **Self-deactivation is refused** with a typed D-016 error. Locking yourself out
   of the only admin console is unrecoverable from the UI, so the API refuses
   rather than letting the click succeed.
2. **`/auth/login` now checks `User.is_active`** — it did not before. Refresh,
   MFA-verify and password-reset all honoured the flag, so a deactivated user
   could still sign in with a password: deactivation was a lie. The gate sits
   **after** the password verify (placing it before would make the endpoint an
   account-existence oracle), and deactivating also clears `active_refresh_jti`
   so an already signed-in user loses their session instead of riding a valid
   refresh token to expiry. The typed reason propagates through NextAuth so the
   sign-in form says "this account has been deactivated" rather than implying a
   bad password.

**Issue 7, same pass.** `/admin/queue` opened onto exactly ONE organization: the
API returns every tenant's requests but sets `client` to the most recently created
tenant (its own docstring calls that advisory), and the UI rendered it as the page
header. The queue is now an **index of organizations**; `/admin/queue/[clientId]`
shows one org's intake detail above its own pending work, using the `client_id`
filter the API already supported. Row counts come from one grouped query.

**Ref:** `apps/api/app/routes/admin.py`, `apps/api/app/routes/auth.py`,
`apps/api/app/models/client.py`, `apps/api/app/schemas/admin.py`,
`apps/api/alembic/versions/0033_client_archived_at.py`,
`apps/api/tests/unit/test_admin_removal.py`;
`apps/web/src/components/admin/IntakeOrgIndex.tsx`,
`apps/web/src/components/admin/IntakeQueue.tsx`,
`apps/web/src/lib/admin/client.ts`, `apps/web/src/lib/auth/options.ts`,
`apps/web/src/components/auth/SignInForm.tsx`;
`e2e/smoke/s32-admin-org-index.spec.ts`, `e2e/smoke/s33-admin-remove.spec.ts`.
Extends D-016 (typed errors).

## D-037 — Provider API keys are managed at runtime, and a stored key beats fixture mode

**Decision (seven-issue pass, issue 2).** An admin can paste, replace and remove a
provider API key from the Management page. Before this, the only key path was an
environment variable read once at boot through the `lru_cache`d `get_settings()`,
so switching AI on meant a redeploy — and the "AI is offline" warning rendered on
exactly one of five workspaces, so an admin could accept canned fixture output
believing it was real analysis.

    POST   /admin/llm-key   validate against the provider, THEN store
    DELETE /admin/llm-key   remove it; AI drops back to offline responses
    GET    /admin/ai-status now also reports can_configure + key_source

Five choices worth recording:

1. **Validate before writing.** `live_validate_key()` makes the smallest real
   provider call (one output token). A typo is refused with the provider's own
   reason instead of silently taking AI offline — FAIL LOUDLY at the moment the
   admin can still fix it. Providers with no cheap probe yet (openai, gemini,
   vertex) say so explicitly rather than pretending the key was checked.
2. **A stored key overrides `SHIELD_LLM_MODE=fixture`.** Pasting a key is an
   explicit request for live AI; continuing to serve fixtures afterwards is
   exactly the silent-success failure this removes.
3. **Database beats environment**, so removal through the UI is a real removal and
   not a quiet fallback to whatever the container booted with.
4. **Fernet encryption derived from `JWT_SIGNING_SECRET`** (migration 0034, new
   table) rather than a second secret an operator could forget to set. Rotating
   that secret makes stored keys undecryptable — reported as "no key" and logged
   loudly, so the admin re-pastes instead of every Run-AI dying on an opaque 401.
   The key is never returned by any endpoint, never logged, and never placed in an
   audit `details` blob; tests assert each.
5. **The offline warning is now unavoidable.** `AiStatusBanner` moved into the
   admin shell (every admin page, and it links to the fix), and `RunAiGuard` wraps
   Run AI: while offline the first click explains the output will be canned and
   offers "Load a key" / "Continue offline". The acknowledgement is keyed on the
   current config, so removing the key makes the very next Run AI warn again in
   the same session.
6. **"Still loading" is not "unavailable."** The guard's first cut failed open
   whenever `status` was `null` — a value that means both "not asked yet" and
   "status endpoint down". Under full-suite load a Run AI click beat the status
   fetch and the guard silently ran, writing 1646 fields of canned output with no
   warning: the exact failure the component exists to prevent. `useAiStatus` now
   exposes an explicit `phase` (`loading` / `loaded` / `error`), a click during
   `loading` is HELD until the answer arrives, and only a real outage still fails
   open (an outage must not stop an admin working). A safety control that
   degrades to silence under load is not a safety control.

Also corrected here: `.env` pinned `SHIELD_LLM_MODEL=claude-opus-4-7`, which the
code itself lists in `_KNOWN_PLACEHOLDER_MODELS` — live AI would have refused to
boot even with a valid key.

**Ref:** `apps/api/app/ai/keystore.py`, `apps/api/app/ai/llm.py`,
`apps/api/app/models/llm_credential.py`,
`apps/api/alembic/versions/0034_llm_credential.py`,
`apps/api/app/routes/admin.py` (and each workspace's `_llm_dep`),
`apps/api/tests/unit/test_admin_llm_key.py`;
`apps/web/src/components/admin/LlmKeyPanel.tsx`,
`apps/web/src/components/admin/RunAiGuard.tsx`,
`apps/web/src/components/admin/AiStatusBanner.tsx`,
`apps/web/src/lib/admin/aiStatus.ts`; `e2e/smoke/s34-llm-key.spec.ts`.
Extends D-017 (fixture mode), D-024/D-026/D-029 (live providers).

## D-038 — Releasing a deliverable is a real control, and admins preview pre-release

**Decision (seven-issue pass, issue 4).** D-035 gated the client dashboards on a
**released** deliverable, but nothing in the product could release one — Finalize
produced a PDF and an XLSX and stopped. The gate was therefore unsatisfiable and
no client could ever see a dashboard. Three defects sat in that path, each hidden
by the next: the `release*Deliverable()` web-client functions had zero callers;
the `/api/proxy/{svc}/deliverables/{id}/release` Next routes they POST to did not
exist; and the TS `Deliverable` types declared `released_to_client_at` where the
API serializes `released_at`, so the card's released state was false even after a
successful release. All three are fixed for zt, attack, csf and tech-debt.

1. **Admins preview before release, through the same builder.** One shared
   `_dashboard_deliverable()` resolver serves all four service dashboards: clients
   get released-only (D-035 unchanged), admins additionally get merely-finalized.
   Both roles then run the **same** builder — that is what stops the preview and
   the client view from drifting, and a test asserts the two payloads are
   identical apart from a new `released` flag. That flag defaults `True`, so every
   existing consumer is unaffected (the C0 additive pattern).
2. **Admins resolve the tenant by falling back to the service's owner.** The
   dashboard pages resolved the client from `/auth/me` then the active-client
   cookie; a platform admin on a cold URL has neither, which produced an unhandled
   API 400 and a Next server-exception page. `resolveDashboardClientId()` falls
   back to the owning tenant and the fetch sends `X-Client-Id`.
3. **`jsonRequest` reads the response body once.** Its error path called
   `res.json()` and then `res.text()`, which throws "body stream already read" and
   masked the real 404 behind a confusing error. Fixed in all six client libs, not
   only the ones this issue touched.

**Ref:** `apps/api/app/routes/clients.py` (`_dashboard_deliverable`),
`apps/api/app/schemas/clients.py`, `apps/api/tests/unit/test_zt_dashboard.py`;
the four `apps/web/src/app/api/proxy/<svc>/deliverables/[id]/release/route.ts`,
the four admin `*DeliverableCard.tsx`,
`apps/web/src/lib/dashboards/resolveClient.ts`, the six `lib/*/client.ts` and
four `lib/*/types.ts`; `e2e/smoke/s36-release-and-preview.spec.ts`.
Completes D-035.

## D-039 — Tech Debt covers the whole portfolio; a negative security call needs sign-off

**Decision (2026-08-05, UX finding 4 / E2E F-5).** The extraction prompt kept
only _security_ capabilities and silently dropped everything else. The guided
review uploaded 21 rows / $1,634,236 and the workspace showed 12 rows /
$891,796 — the survivors presented as the entire inventory. Prompt **v2** keeps
every row and classifies it instead: `security_related`, plus
`security_functions` drawn from prevent / detect / respond (migration **0038**).

`security_functions` is a **list**, not a scalar. An EDR genuinely serves all
three, and the three map 1:1 onto the columns `AttackCoverage` already keeps
(`prevention_tools` / `detection_tools` / `response_tools`), so the
classification reaches the mapping surface without translation.

**Broadening the scope moves the risk rather than removing it.**
`_client_tool_names` feeds the ATT&CK mapping, and `valid_tools` there is not
merely prompt input — it is a **hard allow-list on which tools the model may
cite**. A capability wrongly marked non-security becomes _uncitable_, so the
technique it covered reads as **uncovered rather than unassessed**: a fabricated
gap, presented to a client as an assessed absence.

So a negative classification is **provisional until a human agrees with it**:

| `security_related`                         | `security_class_confirmed` | In the ATT&CK subset? |
| ------------------------------------------ | -------------------------- | --------------------- |
| `True`                                     | any                        | yes                   |
| `NULL` (pre-0038, or the model omitted it) | any                        | yes                   |
| `False`                                    | `False`                    | **yes — provisional** |
| `False`                                    | `True`                     | no                    |

`None` never collapses to `False`: an unclassified row is the absence of a
decision, not a negative one. An unreviewed negative costs a consultant one
glance at a row that did not need it; the failure it prevents is a blind spot
nobody ever sees. We take the glance.

Two endpoints work the queue: **confirm** a negative, or **overturn** it by
naming the functions it actually serves (which also clears the sign-off, so a
stale flag cannot silently re-exclude the row later).

Fixed in the same pass: `_client_tool_names` had **no status filter at all**, so
a DISCARDED list's rows stayed citable forever. Only DISCARDED is excluded —
DRAFT still counts, because mapping ATT&CK before approving the tech-debt list is
a normal order of work.

**Ref:** `apps/api/app/tech_debt/security_scope.py` (the rule, in one place),
`apps/api/app/tech_debt/extract.py` (prompt v2), `apps/api/app/routes/attack.py`
(`_client_tool_names`), `apps/api/app/routes/tech_debt.py` (confirm / override),
migration `0038`; `test_tech_debt_security_scope.py`,
`test_tech_debt_security_classification.py`;
`e2e/smoke/s37-security-signoff.spec.ts`.

## D-040 — One derived six-stage vocabulary, presentation only

**Decision (2026-08-06, UX findings 16 and 15).** The four services each
described progress in their own words. They now share six stages — **prepare,
analyze, review, approve, generate, release** — rendered from a read-only
derivation.

**Relabel only.** No state machine, route or audit vocabulary changed, and
`status` still means exactly what it meant. `app/services/stages.py` answers a
narrower question ("how far along does this version look?") and writes nothing.

Two of the six are **not states anybody stores** — a capability list is DRAFT
before a Run-AI and still DRAFT after — so `analyze` and `generate` are derived
from evidence. The naive query is a trap: `llm_calls` has **no version link at
all** and `Deliverable.version` is its own counter, so "has this service ever
been analysed?" lights up `analyze` on a brand-new draft because a discarded one
was analysed earlier.

Evidence is therefore anchored to the version **two different ways**, because the
services do not build their versions in the same order:

- **Zero Trust, CSF, ATT&CK** create the assessment and _then_ run AI on it, so a
  run belonging to this version is newer than it — `created_at` is the anchor.
- **Tech Debt is inverted.** The extraction runs FIRST and the capability list is
  built from its output, so the `llm_calls` row precedes the list it produced by
  milliseconds, and a timestamp anchor reports every extraction as belonging to
  no version at all. Tech Debt uses the list's own extraction provenance
  (`source_rows_total`), which is version-scoped by construction. **The e2e spec
  found this; the unit tests did not.**

Neither needs a migration or a new column.

Two further rules, both found in the browser rather than by a test:

1. **Progress is monotonic.** Reaching a stage means the ones before it are
   behind you. Without this, an approved list whose extraction predated the
   current version rendered `analyze` as "current" sitting _left of_ three
   completed stages — a cursor behind finished work reads as a broken step.
2. **A service with no version has prepared nothing.** `prepare` is otherwise
   unconditional for Tech Debt and ATT&CK (no client-input step), so an empty
   service claimed its inventory was already uploaded.

**"Submitted" is not a stage.** It exists only for Zero Trust and CSF. Rather
than render a stage that can never light for half the services, the asymmetry
lives in what `prepare` _means_ — labelled "Self-assessment" where there is one,
"Prepare" where there is not.

**The admin queue reuses these six words** rather than the finding's separate
seven-item list (submitted / ready / workspace created / analyzing / review
required / finalized / released). Naming the same concept two ways in two places
is the confusion this work exists to remove, and reusing the derivation means the
queue cannot drift from the workspace because it is the same computation. One
genuinely new state sits in front of the bar: **"No workspace yet"** — nothing
exists for a stage to describe.

**Ref:** `apps/api/app/services/stages.py`,
`apps/api/app/routes/service_stages.py`, `apps/web/src/lib/stages/client.ts`,
`apps/web/src/components/admin/ProgressStages.tsx`; `test_service_stages.py`;
`e2e/smoke/s38-progress-stages.spec.ts`.

## D-041 — The primary contact belongs to the engagement, not to whoever typed it

**Decision (2026-08-06, UX finding 9).** Intake took the contact from the
signed-in user's own record, and the email field is deliberately read-only. That
is right when they _are_ the point of contact and wrong whenever they are not —
an assistant or procurement lead completing the wizard on someone else's behalf
had no way to say so, so the engagement recorded the wrong person and a
consultant would go on to contact them.

Four nullable columns on `client` (migration **0039**), not on `users`: the
contact is a property of the engagement, not of the account that happened to fill
in the form. `NULL` means "the contact is the submitter", which is what every
pre-0039 row already means. No new endpoint — these ride the `ClientProfilePatch`
auto-save path the Organization step already uses.

`_effective_contact` is the single resolver, and its rules are tested because
getting them wrong means mail goes to someone who explicitly said they are not
the contact:

- an override must **name** someone; a stray title or phone redirects nothing
- a named contact with no email keeps the account address — the only one we can
  be sure reaches a human
- partial overrides fall back **field by field** rather than blanking
- unchecking the box **clears** the stored values, so it cannot keep redirecting

Two round-trip bugs fixed alongside, the second found only in the browser:
`title` / `phone` / `timezone` were passed to Step 3 as **hardcoded nulls** (the
API saved and returned them; the form never read them back), and the new override
columns were initially missing from `ClientProfileResponse`, so re-opening the
step would have shown an unchecked box over a live override.

**Explicitly NOT done: merging Organization and Contact into one wizard step.**
The finding raises it conditionally ("if the resulting page remains manageable"),
and it is the expensive half — renumbering the wizard ripples through Step 6
review and the intake specs. Prefill plus the override delivers the finding's
actual value without that. Confirmed with the repo owner on 2026-08-06; recorded
here so it is not re-opened as an oversight.

**Ref:** `apps/api/app/routes/intake.py` (`_effective_contact`),
`apps/api/app/models/client.py`, `apps/api/app/schemas/intake.py`, migration
`0039`; `apps/web/src/components/intake/steps/Step3Contact.tsx`;
`test_intake_primary_contact.py`.

## D-042 — `/results` is the one client-facing results surface, and `/documents` redirects forever

**Decision (2026-08-06, UX finding 18).** Reports were downloaded from
`/documents` while dashboards were reached from `/home` or a "View dashboard"
link. A client had **three places** to look for the outcome of one engagement and
no way to know which held what.

`/results` is now the single destination. The list already carried nearly
everything the finding asks for — service, version, release date, status
(Final / Superseded), the dashboard link and the PDF/XLSX downloads — so this is
consolidation and a rename, not a rebuild.

**`/documents` permanently redirects, and stays.** Release notification emails
carrying the old path are already sitting in people's inboxes; a 404 on a link we
sent is worse than keeping a route forever. `s17` asserts that promise rather
than leaving it to trust. The release email now points at `/results` directly
rather than through the redirect.

**Ref:** `apps/web/src/app/results/`, `apps/web/src/app/documents/page.tsx`
(redirect), `apps/web/src/components/results/ResultsList.tsx`,
`apps/api/app/notifications/`; `s17`.

## D-043 — Client Home groups by who owns the next move; the six-stage bar stays admin-only

**Decision (2026-08-06, UX finding 17).** "Your services" was one flat grid in
arrival order, so a client with several engagements read every phase pill to work
out which one needed them — and an open self-assessment appeared **twice**, once
as a card and again in a "Waiting on you" list beside it.

Three buckets, and every service lands in **exactly one**: **Action required** /
**In progress** / **Results available**. Ownership, not progress. That single
placement is what removes the duplication rather than patching around it, and
"Waiting on you" is gone entirely — unread messages, which need the client but
have no service card, moved **into** Action required.

**The six-stage bar (D-040) deliberately does NOT appear here.** Master Spec §6.4
restricts a client surface to phase and next steps; the six stages are consultant
vocabulary and stay in the workspaces and the admin queue. The finding named three
buckets, not six stages, and the two answer different questions — so the card
keeps its existing **phase pill** alongside the bucket heading. Leaving the pill
alone also meant `s31`'s phase-driven routing assertions needed no edit to stay
green, which is the right way round: the test did not move to accommodate the
change.

Each card names **one primary action** — Resume assessment / View status / View
results — keyed off the bucket so the label cannot disagree with the group. It is
a `<span>` inside the card's existing link, never a nested `<a>`: that would be
invalid HTML and would give every card two tab stops to the same destination. A
test asserts exactly one link per card.

The finding's third clause, "move secondary actions into a menu", is a **no-op**
here — `/home` has no per-card secondary actions to move. Recorded rather than
faked.

**Ref:** `apps/web/src/components/home/HomeDashboard.tsx` (`bucketFor`,
`needsClient`, `BUCKET_ACTIONS`); `HomeDashboard.test.tsx`; `s31`.

## D-044 — The admin Deliverables view derives its status, and is read-only

**Decision (2026-08-07, IA appendix).** D-042 gave clients one place to find
their reports. Admins still had that problem: deliverables were visible only
inside the workspace that produced them, so "what have we produced for this
client, and what have they actually seen?" meant opening every workspace in turn.

`GET /admin/deliverables` mirrors the client route's query with one deliberate
difference — it **drops the `released_at IS NOT NULL` filter**. That filter is the
§12 release rule and is correct for a client; for an admin the unreleased rows are
half the answer.

**No migration.** All three states derive from columns already on the table:

| Condition           | Status     | `client_visible` |
| ------------------- | ---------- | ---------------- |
| `superseded_by` set | superseded | false            |
| `released_at` set   | released   | **true**         |
| `finalized_at` set  | generated  | false            |

**Superseded wins over released.** A superseded row was often released once;
reporting it as client-visible would tell a consultant the client is looking at a
version that has since been replaced. `released_at` remains the single source of
truth for client visibility, so there is no second lifecycle to drift from §12.

**Read-only on purpose.** No release button on a cross-service list — that is how
someone releases the wrong version to the wrong tenant. Finalize and release stay
in the owning workspace, and the e2e asserts the absence rather than trusting it.

Scope is the active-client tenant via `current_client`, the same mechanism the
Risk Register uses; no new cross-tenant read surface. A cross-tenant roll-up is a
recorded follow-up, not a silent omission.

**Ref:** `apps/api/app/routes/admin.py` (`list_admin_deliverables`,
`_deliverable_status`), `apps/api/app/schemas/admin.py`;
`apps/web/src/components/admin/DeliverablesTable.tsx`,
`apps/web/src/lib/admin/deliverables.ts`; `test_admin_deliverables.py`, `s40`.

## D-045 — A dropped AI suggestion is counted in VALUES, and the invariant is a sum

**Decision (2026-08-09, W1 CSF step, issue #44).** W1 makes every AI suggestion
either applied or itemized. #44 settled the shape (itemized, not counters) but
left the unit of `suggestions_received` / `suggestions_applied` open: its own
reason vocabulary mixes `unparseable` / `out_of_range`, which describe a single
field, with `entry_shape` / `unknown_key` / `locked`, which describe a whole
entry. The two integers cannot count both.

**The unit is ONE SUGGESTED VALUE** — one field the model asked to set on one
row. Counting whole entries was rejected: a row whose every field is invalid
would report as `applied` while changing nothing, and the invariant would hold
vacuously over it. That is the silent-drop family W1 exists to close, reached
through the mechanism meant to prevent it.

**Entry-level drops state their own width.** `entry_shape`, `unknown_key` and
`locked` fail before any single value can be blamed, so each carries `values`
rather than defaulting to 1 — a rejected row carrying three suggestions is three
lost values. An entry too broken to enumerate (a non-object, or an object naming
no recognized field) is charged the full row width, so an unreadable entry is
never cheaper to lose than a readable one that failed validation.

**Therefore the invariant changes shape.** #44 wrote it as

```
received == applied + len(dropped)
```

which is only true when every record covers exactly one value. It is now

```
received == applied + sum(d.values for d in dropped)
```

and is asserted in the API tests. The audit row carries `dropped_by_reason` in
values so the durable record can be checked against itself after the fact —
recorded, not enforced; nothing validates the invariant at runtime.

**`what_we_found` is a countable value like the rest**, with `wrong_type` for a
non-string. It was previously skipped by a bare `isinstance` check with no
trace — a silent gap sitting directly beside the counter that exists to end
silent gaps.

**A non-list `scores` is an error, not a pile of drops.** `{"scores": "..."}`
passes `parse_json_object` (the top level IS an object) and then iterates one
character at a time, manufacturing an unreadable entry per character. It raises
via `parse_json_object_with_list("scores")`, by #44's own rule: a condition that
can never coexist with an applied suggestion belongs in the error path. A
MISSING `scores` key is untouched — that is #46, filed and deliberately outside
W1's invariant.

**Constraint 1 holds as written.** The API response carries `key` and `value`
(transient, admin-only, the same trust boundary as the run result). The audit
row gets reason codes and value counts only; the log gets counts only. Neither
`key` nor model text reaches **the audit row or the log**, per Master Spec
§12.1. (Model text of course still persists where the feature intends it to —
`what_we_found` and the dimension scores land on `csf_dimension_scores`. The
constraint is about the audit/log channel, not about the product.)

**Scope of the two integers, stated because the UI sentence reads like a
completeness claim.** They count values suggested for SCORING ROWS. The
response's top-level `executive_summary` is outside them — and is not persisted
by CSF at all, ~~though ZT persists its equivalent (`routes/zt.py`)~~. That
asymmetry is pre-existing and is NOT resolved here; the copy says "score
values" so the panel stops implying otherwise, and the gap is filed separately.

> **Correction (2026-08-18, W1's ZT step).** The struck clause above is FALSE.
> **ZT does not persist its equivalent.** `ZtAssessment` has no
> `pillar_narratives`, `executive_summary` or `roadmap_summary` column, no
> migration adds one, `zt/exporters.py` never reads them, and across all of
> `apps/web/src` the only occurrence is the type declaration in
> `lib/zt/types.ts`. The citation pointed at `routes/zt.py`, which _returned_
> the values; nothing wrote them anywhere.
>
> The error is worth naming, not just fixing: this is a claim about a design
> that was intended and never finished, written down as though it described the
> schema, and never checked against it. Nothing in the codebase contradicted it
> loudly, because a field that is returned and ignored looks exactly like a
> field that is returned and stored, from the route.
>
> It was load-bearing. This sentence was the stated basis for scoping ZT's
> narratives INTO W1's suggestion accounting — the reasoning being that a
> dropped narrative would be a real lost value. Once the premise failed, so did
> the conclusion: those values were discarded unconditionally, valid or not, so
> a "dropped narrative" count would report loss where a validation failure lost
> nothing that was not already thrown away by design, and a counter implying the
> harm of a real dropped score trains the reader to discount the counters that
> matter (the #31 constraint). The fields were removed from `_ZT_SCORE_PROMPT`
> instead — see **D-047** and issue **#64**. CSF's half remains open as **#60**.

### What the adversarial pass changed (same day, before merge)

Two independent reviews of the first cut found the design defeating itself in
five places. The headline one is the reason `received` is now enumerated from
what the model WROTE rather than from what the parser recognizes:

- **`unknown_field` (new reason).** `fields = [f for f in _RUN_FIELDS if f in
sugg]` enumerated only recognized keys, so a misnamed field vanished from BOTH
  sides of the invariant — received and applied agreed, `dropped` was empty, and
  the panel asserted full accounting over the loss. The opening is real though
  **not yet observed in a run**: the csf_score prompt names the dimensions in
  prose as "Policy and Process" / "Monitoring and Measurement" / "Continuous
  Improvement" while its JSON example uses `policy` / `monitoring` /
  `improvement` (`test_csf_ai_contract.py` does pin every parser key into the
  prompt text, which makes drift less likely, not impossible). **A count that
  only sees what it already understands cannot detect drift, which is the one
  thing it exists to detect.**
- **`superseded` (new reason).** Two entries for the same row+field counted as
  two applied while the row held one value — `applied` could exceed the values
  actually on the rows without limit.
- **`_verbatim_key` was half-fixed.** The guard was `tier is None AND code is
None`, so one written half still produced `"high|None"`. Each half is now
  either what the model wrote or an explicit `(missing …)` marker.
- **`received == 0` is no longer reported as a clean run.** A response under the
  wrong top-level key parses, yields an empty list, and rendered "AI applied 0 of
  0" in the same calm type as "12 of 12" — the most reassuring possible way to
  report a wholly-lost response. It now renders as a typed warning. This is the
  reader-facing half of #46; **#46 itself stays open** — the parser still accepts
  a missing `scores` key.
- **`reason` is a closed `Literal`, and the UI gained a fallback label.** As a
  bare `str` a new server-side code reached the workspace as an unmapped label
  and rendered an empty bullet — count right, explanation silently gone. That
  one was live. The companion change (the UI's by-design test from `!== "locked"`
  to a named allow-list) is **hardening, not a defect** — with today's
  vocabulary the two forms behave identically and no test distinguishes them.

Also: the accounting log moved BELOW the D-031 re-read (it claimed `applied=N`
for transactions that then rolled back), `out_of_range` now reports the raw model
value rather than the coerced one, and row-key halves are length-bounded like
`value` already was.

**The log placement is the third sighting of one defect class**, and worth
tracking as such rather than as a one-off: a success record written independently
of the success. N-019 — `llm_calls` holds 0 input/output tokens for FAILED calls,
two of which logged `charged_likely: true`, so the money was spent and the ledger
says zero. #47 — `llm_calls` records COMPLETED for a response rejected after
parsing. And this one — `applied=N` logged above the guard that could still
refuse the run. All three are the ledger asserting something the database does
not contain. Rule added to CLAUDE.md.

### The second round, and what it says about "done"

The repairs above were themselves audited before merge, and **the headline
repair had re-opened the hole it closed.** Guarding with `if not fields and not
unknown_fields` meant one unrecognized key suppressed the full-row-width charge:
`{"dimensions": {…five scores…}}` was charged ONE value, so four fell out of
both sides and the invariant held vacuously over them. An unknown key is now
charged what it actually hides (`_hidden_value_count`).

Also from that round: `unknown_field` no longer renders in the red "could not be
applied" alert — a model volunteering one extra key per row loses nothing, and
318 red items on a clean run is #31 rebuilt — it renders as its own visible,
non-alarming block; the `unknown_key` label was reworded (it ended mid-clause
and its em dash collided with the list separator, so the key read as the end of
the sentence); and `skippedValues` gained the assertion it never had.

**The generalisable part — stated narrowly, because the first version of this
paragraph overclaimed.** ONE of these defects is explained by fixture vocabulary
(`unknown_field`): every AI fixture in the suite was hand-authored using the
parser's own field names, and **a fixture whose author already knew the answer
the parser wanted cannot express drift** — the same blind spot §5's caveat names
for fixture mode, one level down. That rule is now in CLAUDE.md. The others were
missed for the ordinary reason: no fixture expressed two writes to one field, or
a half-written key, or an empty `scores` list. The honest general lesson is the
weaker one — **a fixture can only express the failure shapes its author already
imagined** — and the specific one is worth naming because it is structural
rather than imaginative.

### The third round, run after a machine restart, on the same working tree

Three more reviewers — backend accounting, web/e2e surface, test honesty — over
the tree the first two rounds produced. **Every gate was green when they ran:**
prettier, `tsc`, vitest 146/146, eslint. They found six more.

- **The e2e assertion for this feature could never have matched.** `s7` waited
  on `/AI applied \d+ of \d+ suggested value/` while the panel renders
  `suggested score value` — the wording THIS decision record introduced, in the
  scope paragraph above. The vitest was updated with it; the spec was not. All
  three reviewers found it independently. It would have failed as a 30s
  "element(s) not found", which is the symptom CLAUDE.md records being
  misdiagnosed as a slow page and "fixed" with a longer timeout. **The only
  end-to-end check of W1 was broken by the copy change made to be precise.**
- **`unknown_key` swallowed the drift diagnostic.** The `row is None` branch
  returned before the `unknown_field` loop, so a model that misnames the ROW KEY
  — writing `code` for `subcategory_code`, which is the Sprint 3 T0 bug verbatim
  — produced N identical "no matching row" bullets and never once said the word
  `code`. The field name is itemized before the row is resolved now, and before
  the lock is checked, which also closes the locked-row blind spot the docstring
  had merely disclosed.
- **The container count was still one level deep, and never applied to
  recognized keys.** `{"governance": {"high": 2, "moderate": 1, "low": 0}}` was
  charged 1; `{"values": {"dimensions": {…5…}}}` was charged 1. Both held the
  invariant over the undercount — the same vacuous hold round 2 fixed, once one
  key over and once one level down. It counts leaves to a bounded depth now, for
  every key the model wrote.
- **`int()` was doing validation.** `int(1.9)` is 1, in range, so it was written
  to the row, counted as applied, and itemized nowhere. `true` became 1 the same
  way. The suite had a test for `3.9` — but only because it is out of RANGE, so
  the doctrine was pinned exactly where the code upheld it and nowhere it broke
  it. Range is judged before wholeness now, so `3.9` stays `out_of_range` and
  `1.9` is refused; `"2"` and `2.0` are still applied, because refusing a value
  the model plainly meant is the #31 failure in the other direction.
- **The panel called the loss "Harmless".** On the drift this feature exists to
  catch, the grey block's number and the headline's shortfall are the SAME
  values, and the copy led with "Harmless if the model is volunteering extra
  detail" — inviting a consultant to write off three of five dimensions on every
  row. It now says the values are part of the shortfall above, not extra.
- **`dropped[].value` had no consumer.** The repair recorded above — "`out_of_range`
  now reports the raw model value rather than the coerced one" — was invisible:
  nothing rendered it, so the panel said a value fell outside 0-2 and never said
  what it was. A run that wrote `5` looked identical to one that wrote `"high"`.

Both drop lists are also capped at ten items now with an "and N more" line;
systematic drift is the expected shape here, not the exception, and 318 bullets
or one 5 KB comma-joined line is the diagnostic collapsing when it matters.

**Two process notes.** Every new test above was verified by reverting the fix
and watching it fail, because the fixes and tests were written together rather
than test-first — the reverts are the substitute for having watched it fail the
first time, and they are not optional when the order is wrong. And the reviewers'
own claims were checked before being acted on: rounds 1-3 produced ten findings
here, and the two that were downgraded (a log-above-commit window nobody could
construct, a row-key collision that turned out unreachable) were downgraded by
the reviewers themselves.

**What this says about "done", now three rounds in.** Each round found real
defects in the previous round's repairs, and green CI never caught any of them.
The rate is not obviously falling. The honest reading is not "the third round
made it correct" but "an audit gate keeps finding things a green suite cannot",
and W1's remaining services (ZT, Risk, ATT&CK) should budget for the same rather
than assume the pattern is now understood.

**Ref:** `apps/api/app/routes/csf.py` (`_apply_suggestions`, `_verbatim_key`,
`_hidden_value_count`, `_as_number`, `_ROW_VALUE_SLOTS`),
`apps/api/app/schemas/csf.py` (`CsfDroppedSuggestion`),
`apps/api/app/ai/engine.py` (`parse_json_object_with_list`);
`apps/web/src/components/admin/csf/CsfPlaybookPanel.tsx` (`RunAiAccounting`,
`describeItem`, `summarizeItems`);
`test_csf_run_ai.py`, `CsfPlaybookPanel.test.tsx`, `s7`.

## D-046 — Release assigns RELEASED to the parent, and the deliverable records which parent

**Decision (2026-08-17, W4, plan §8).** `release_deliverable()` now flips the
parent assessment / capability list to `RELEASED`, in the same transaction that
sets `deliverables.released_at`. Migration **0041** adds
`deliverables.parent_version` so it flips the right row.

**This supersedes D-035 §1**, which recorded the gap and deferred it verbatim:
_"Flipping the assessment to RELEASED on release remains a possible future
consistency cleanup — out of scope here."_ D-035's own choice — gating the client
dashboard on the released deliverable rather than on parent status — stands
unchanged and is still the right gate. What changes is that the parent status is
no longer a dead field.

**Why it stopped being cosmetic.** No API route assigned `RELEASED` anywhere; the
only writer in the repo was `seed_demo.py` (8 assignments). The plan's first
draft asserted the status was "never assigned anywhere", which was false and came
from a grep scoped to `apps/api/app` presented as a repo-wide claim. The correct
claim is narrower and worse: **the seeded world and the API-created world
disagreed**, and every reader keyed on parent status worked only for seeded data.

Consequences that were live in the product:

- **The progress bar lied.** `services/stages.py` derives `released` from the
  PARENT status, not from `deliverables.released_at`, so a service released
  through the product showed `release` as its current incomplete stage while the
  client already had the report. `test_service_stages.py:277` constructs
  `status="released"` by hand and passed throughout — a test asserting a state no
  route could reach.
- **Tech Debt's mutability lock was dead code.** `_editable_list_or_404` refuses
  edits to a RELEASED list; nothing could reach that status, so an approved list
  stayed fully editable under a released PDF.
- **Three approve routes returned an idempotent 200 after release** instead of
  the 409 they were written to return.

**Option B was rejected, reversing the plan's first draft.** Deleting the status
comparisons and keying everything on `Deliverable.released_at` would un-lock the
seeded Atlas capability list (`seed_demo.py:489`), which has no released
deliverable behind it — so a demo client dashboard becomes editable under a
released report, and four e2e specs flip from asserting read-only to silently
exercising the path they were written to prove was blocked. It also does not fix
the stage bar. Option A is the larger change and the one that does not quietly
remove protection that currently fires.

**The parent version is RECORDED, not inferred.** `deliverables` has no foreign
key to any parent — the four parents live in four tables — and deliverable
versions and parent versions are independent counters. So "which row" had three
candidate answers that diverge in a real sequence:

```
approve v1 -> finalize -> cut v2 -> approve v2 -> release
```

"Latest APPROVED" flips v2, which the released report was never built from. This
repo has hit the version trap twice already, so `parent_version` is stamped at
**finalize** — the moment content freezes against a specific parent, and the gate
that already requires APPROVED — and release flips exactly that row.

**Two loud refusals, neither fatal.** The release is the source of truth (the
D-030 rule: a side effect must not roll back what the user already asked for).
`parent_version` NULL means finalized before 0041 and the parent is left alone
with a `release_parent_unknown` warning — guessing is what the column exists to
prevent. A parent that is not APPROVED is left alone with
`release_parent_not_approved`, because flipping a DRAFT would skip APPROVED
entirely and lock work in progress.

**One guard was aligned, and it is the reason this could have shipped broken.**
`tech_debt.py`'s finalize gate was `!= APPROVED` where csf/zt/attack accept
`in (APPROVED, RELEASED)`. Once the parent flips, that would have made releasing
a tech-debt deliverable **permanently block finalizing any further version** for
that service. **CI could not have caught it**: the only release-then-finalize
coverage (`s17-documents`) runs on CSF, which already accepted RELEASED. The
ATT&CK plan's claim that all four services "hard-gate finalize on
APPROVED/RELEASED" was false, and false only here. Now covered by a test that
fails with `assert 409 == 201` without the fix.

**The lock this creates is PARTIAL, and saying otherwise would overclaim.** For
Tech Debt, RELEASED genuinely locks the list (`_editable_list_or_404`). For CSF it
does not: `patch_dimension_score`, `profiles/seed` and `upsert_gap_action` have no
parent-status guard at all, so the Working-Profile and POA&M track stays mutable
on a RELEASED assessment — and `patch_dimension_score` feeds `export_playbook`,
which writes artifacts. That is the deferred W0 freeze, recorded and open, not
something W4 closes. "Release locks the parent" is true of the status field, not
of every write path behind it.

**Explicitly out of scope: `ServiceStatus.RELEASED`.** A fifth never-assigned
RELEASED, read by two frontend surfaces (`HomeDashboard`, `AssessmentsView`) and
still reachable only via the seed. W4 covers the parent assessment/list record,
which is what the stage bar and the mutability locks read. Flipping
`Service.status` is a separate question and stays open.

**What the audit found, and it is the same lesson twice in one change.** The
adversarial pass caught that `DeliverableCard.tsx` gated its finalize button on
`capabilityListStatus === "approved"` — the identical one-off this decision
congratulates itself on catching in `tech_debt.py`, in the half a human actually
touches, unfixed. Releasing would have greyed out the only finalize control in
the product, permanently and with no reason shown (the explanatory hint renders
only when no deliverable exists). The API test asserting `201` on the same call
passed straight over it: **it proves the route, not the product.** The component
had no vitest at all, which is why. It has one now, and reverting the one-word
fix fails exactly that case. Fixing one layer of a two-layer guard is not fixing
the guard.

**Ref:** `apps/api/app/deliverable_release.py` (`_PARENTS`, `_release_parent`),
`apps/api/app/models/deliverable.py` (`parent_version`),
`apps/api/alembic/versions/0041_deliverable_parent_version.py`,
the four finalize routes (`csf.py`, `zt.py`, `attack.py`, `tech_debt.py`);
`test_deliverable_release.py`, `test_tech_debt_dashboard.py`,
`test_zt_dashboard.py`, `test_attack_dashboard.py`.

## D-047 — ZT accounts for every suggested stage, and stops asking for narratives nobody reads

**Date:** 2026-08-18 · **Workstream:** W1, ZT step · **Issues:** #44, #64 · **Supersedes nothing; corrects D-045's ZT-persistence claim in place.**

W1's second service. The shape is D-045's, carried over intact: every suggested
value is either applied or itemized, counted in VALUES, with the invariant

```
received == applied + sum(d.values for d in dropped)
```

What follows is only what differs from CSF, plus the one decision that is not a
port.

**The narrative fields were removed, not counted.** `_ZT_SCORE_PROMPT` asked for
`pillar_narratives`, `executive_summary` and `roadmap_summary` on every run.
`routes/zt.py` parsed all three and returned them; `lib/zt/types.ts` declared
them; and that was the end of the road. No column on `ZtAssessment`, no
migration, no reader in `zt/exporters.py`, and no reference anywhere in
`apps/web/src` outside the type declaration itself.

They were briefly scoped INTO this accounting, on the strength of D-045's claim
that ZT persisted them. That claim was false and is corrected in place above.
Once the premise went, the conclusion went with it, and the replacement argument
— "a value the model wrote and the run discarded is the defect family regardless
of storage" — does not hold either. **The defect W1 exists to catch is content
that would otherwise have been KEPT vanishing silently.** These values vanished
unconditionally, valid or not. A validation failure lost nothing that was not
already being thrown away by design, so a per-reason drop count for them would
have measured a quantity with no consumer and reported it in the same register
as a genuinely lost score. That is the #31 alert-fatigue constraint arriving
from a new direction: a counter that reports harm where none occurred teaches
the reader to discount the counters that report harm where it did.

So this was never an invariant-scope question. It was a waste question, and the
answer is to stop paying for the tokens: the three fields are gone from the
prompt, the response schema, the fixture and the TS types. **Not deprecated and
left empty** — a dead field implying a live one is its own defect (#62). If a
narrative or an executive summary should ever appear in the ZT workspace or the
exported report, that is a real feature needing a column, a migration, an
exporter change and a UI surface; re-adding the prompt text is the LAST step of
that work, not the first. CSF's half of the same waste is open as #60.

**`protected` is a reason code, distinct from `locked`.** ZT has a skip CSF does
not: an offline run declines to overwrite a non-AI answer (migration 0035).
`if row.locked or code in protected: continue` recorded nothing for either. They
are now two records with two reasons. Folding them together was rejected: both
are by-design skips that must render away from the failure alert, but telling a
consultant a row is "locked" when nobody locked it is a false statement about
who did what, and the two have different fixes.

**A non-list `capabilities` is a 502, not a pile of drops.** The old path did
`raw_caps = []` after a warning — a default-value fallback on a bad shape, which
FAIL LOUDLY forbids, and which made a structurally broken response
indistinguishable from a model with nothing to say. `zt_score` now uses
`parse_json_object_with_list("capabilities")`, matching `csf_score`. Counting it
as drops was the alternative and is wrong: there are no entries to enumerate, so
any per-entry number would be invented. A MISSING key is still untouched — that
is #46, deliberately outside this.

**No `wrong_type`.** CSF needed it for a narrative field. Every value ZT applies
is a stage, so the vocabulary is `entry_shape | unknown_key | unknown_field |
unparseable | out_of_range | superseded | locked | protected`.

**`suggested` gains a code only where a value landed.** The F9 provenance
settlement loop iterates that set. Adding a code on a rejected suggestion would
hand the settlement a row the model never wrote and re-open the defect PR #39
closed.

**The log moved below the D-031 re-read**, and the audit row gained
`suggestions_received`, `suggestions_applied` and `dropped_by_reason` in values.
Both follow the rule D-045 records the reviewers enforcing on CSF: a record
saying "this happened" goes below the guard that makes it true.

**Four log lines lost their model content.** `zt.py` logged
`received=repr(raw_caps)[:120]`, `entry=repr(sugg)[:120]`,
`capability_code=repr(code)[:120]` and `value=repr(raw)[:120]` — AI output in a
log line, against #44 constraint 1. The per-event warnings are gone entirely,
along with `_MAX_REJECT_LOGS`, which existed only to bound them. What they
carried now reaches the admin through `dropped` on the response, which is the
channel allowed to hold verbatim keys and values.

**One pre-existing test changed on purpose, and one assertion was removed.**
`test_a_malformed_response_does_not_500_and_changes_nothing` asserted a 200 for
a non-list `capabilities`; that encodes the fail-soft path being deleted, so the
case moved to its own 502 assertion. `test_zt_run_ai_applies_current_and_target`
asserted the narratives were echoed back; that behaviour is deliberately gone.
Neither was wrong about the old code — both are recorded here rather than
quietly edited, because "fix the code, not the test" only permits touching a
test when the behaviour it pins is itself the thing being changed.

### What the adversarial pass changed (round 1, same day, before merge)

Two reviewers, one on the engine's arithmetic and one on the removal's blast
radius. **One real defect, five stale artifacts, and three test gaps.** Every one
was invisible to a green suite, and the suite was green when the round started.

**The defect: a container under a recognized key broke the invariant.**
`received` charged every key the leaves it hides, but the three per-field drop
records passed no `values` at all, defaulting to 1. So
`{"code": "CISA.ID.01", "current": {"stage": 2, "confidence": 0.8}}` charged
`received=2` and itemized 1 — one suggested value gone with no record, which is
precisely the silent loss this feature exists to end. Widened, it scales:
`{"current": [1,2,3], "target": [1,2,3]}` lost four. The CSF sibling had this
right (`csf.py:1641-1676` passes `values=field_values[field]` on every per-field
record) **and had a regression test for it**; the ZT port copied the enumeration
and not the charge. The tell was `field_values` being computed per field and then
never read per field — only summed. Two of the three records were only
accidentally safe, since a container cannot currently reach `out_of_range` or the
non-whole branch; they were fixed anyway, because "unreachable today" is an
unstated carve-out.

**The removal left five things behind, and the worst of them reached a human.**
`ZtWorkspace.tsx` still told the consultant Run AI produces "the per-pillar
narrative", in an always-visible step description — the copy outlived the field
it described, which is the same "dead thing implying a live one" this decision
cites #62 to avoid. The `run_ai` docstring, which FastAPI renders as the endpoint
description at `/docs`, still promised narratives in the response, contradicting
the response model on the same page. `s6` delegated its uncovered drop branches
to `ZtWorkspace.test.tsx`, **a file that has never existed** — the real one is
`ZtRunAiAccounting.test.tsx`. Only two of the three removed fields were pinned
absent, leaving `roadmap_summary` — the likeliest to be re-added alone, since a
roadmap feature genuinely exists — free to come back green. And the by-design
skip bullet had no zero-guard, so field drift on a locked row renders
"0 suggested values skipped", the same contradiction the failure block above it
had already been fixed to avoid.

**Three test gaps, each of which would have let a revert pass green.** The
`protected` branch was exercised only by a test asserting
`preserved_client_answers`, never `dropped` — reverting it to a bare `continue`
left the suite green over a two-value silent loss, one branch over from where
that shape was already defended. The `superseded` record claims to name the value
that was LOST, and nothing pinned it, so recording the winner instead — the
natural mistake — would have told a consultant the opposite of the truth,
greenly. And the second `entry_shape` branch had no test at all.

Also hardened: `unknown_field.field` echoed the model's JSON key unbounded, while
`code` beside it was bounded to 80 characters by a helper whose docstring names
the threat. A key is model output too.

**What held.** The invariant was hand-traced over roughly twenty payload shapes —
empty entries, unhashable codes, `inf`/`nan`, a 400-digit integer, depth-5
nesting, duplicate JSON keys, 3→4→3 round-trips — and holds everywhere else.
`applied` cannot go negative. The F9 settlement loop cannot `KeyError`, because
`suggested` only gains codes that resolved to a real row. `int(n)` cannot raise,
because range is judged first. No model text reaches any log or audit row. And
the removal genuinely has no consumer: no column, no migration, no exporter
reader, no wholesale serialisation of the AI payload, and nothing in `apps/web`
beyond the type declaration.

The honest reading is the one D-045 reached for CSF: not "round 1 made it
correct", but that an audit gate keeps finding what a green suite cannot. This
step budgeted four rounds on that basis.

### What the adversarial pass changed (round 2)

Two lenses again: one attacking round 1's own fixes, one asking what was still
missing. **Round 1's six changes all held** — the `values=field_values[field]`
charge cannot double-count, because the `unknown_key` / `locked` / `protected`
branches `continue` before the per-field loop is ever reached, so the two charges
are mutually exclusive by control flow rather than by luck. What round 2 found
was in the artifacts around the change, in one test that could not fail, and in a
claim this decision itself asserted without checking.

**A claim in round 1's own record was false.** Round 1 wrote that ZT's skip
bullet reproduced "the contradiction the failure block above it had already been
fixed to avoid" — implying the CSF sibling it was mirroring had the guard. It did
not. `CsfPlaybookPanel.tsx` printed **"0 suggested values skipped because you
locked those rows"** whenever every field on a locked row was also misnamed, which
is the realistic prompt-prose drift shape CSF's own test calls out by name. So the
sentence asserting nothing was lost printed at the moment the most was, live, in
shipped CSF code. Fixed here with the ZT fix rather than filed, because it is the
same defect and leaving a false statement in front of a consultant to preserve
PR scope is the wrong trade.

**"Fixture mode structurally cannot produce a drop" is FALSE for ZT.** It was
written in four places — the component header, the vitest header, `s6`'s comment,
and #51's framing — and it is inherited from CSF, where it is true. ZT has a
reason CSF does not: `protected` is reachable **only** in fixture mode, because
`protected_keys` returns an empty set off-fixture (`app/ai/provenance.py`). So the
blanket claim is backwards for exactly one reason code, and it matters twice
over: `protected` can never be observed live at all, and `s6` **could** have
proven a drop branch end to end had it not deliberately minted a blank draft. All
four sites now say what is actually true. The precise live-verification scope now
lives on #51 rather than as a vague "never observed".

**The audit-row test could not tell values from records.** It asserted
`dropped_by_reason == {"unknown_field": 1}` over a scalar, where values and
records are both 1 — so a refactor to `+= 1` would have passed it while writing
`{"unparseable": 1}` over three lost stages into the durable record that outlives
the response. This is round 1's own "ported the enumeration and not the charge"
defect, one layer up, and round 1 did not look there. The payload now hides three
values behind one key, and the test asserts the durable row's arithmetic closes
against itself. CSF had already done both, deliberately.

**Five behaviours were correct but unpinned**, each of which a revert would have
carried green: the row-level record emitted at `values=0` (ZT's nearest test used
a recognized field, so `if recognized_values:` would still have passed it); field
drift surviving the lock check; the `OverflowError` guard whose absence is a bare
500 that costs money and writes no ledger row; a two-level wrapper counting leaves
rather than the wrapper; and the same field on two capabilities not reading as a
supersede. Plus one the response could never pin: the _prompt_ no longer asking
for narratives — `assert "roadmap_summary" not in body` only fires on a schema
re-add, since `response_model` strips unknown keys, and the change that costs
money is a re-add to the prompt.

**The depth cap's comment was wrong, in the direction that matters.** It claimed
"the undercount is bounded and stated". It is bounded in RECORDS and unbounded in
VALUES: a list of 10,000 stages nested below `_MAX_NEST_DEPTH` is charged 1 on
both sides, so the invariant closes over 9,999 lost values. It is the only path
where the invariant holds vacuously — in the feature built to stop exactly that.
No real model nests five deep, so it is accepted rather than fixed, but an
accepted exclusion belongs on the record and not only in a comment. Corrected in
both services.

**Also corrected:** `IMPLEMENTATION.md`, which declares itself verified against
live code, still described `zt_score` as producing pillar narratives — a sixth
stale artifact of the same shape as round 1's five. A test-file docstring still
pointed readers at a `zt_run_ai_suggestions_dropped` log line, and at a rationale
for deliberately withholding the count, both of which this step deleted. And the
round-1 test-block header claimed all five of its tests failed first; only three
did, the other two characterising already-correct behaviour that had no test —
a distinction worth keeping straight, because only the first kind proves a fix.

**Stated, not fixed:** `response_shape` from #44's shared vocabulary is
implemented by neither CSF nor ZT. The reason is real — a condition that can never
coexist with an applied suggestion belongs in the error path, not a per-item drop
list, which is what `parse_json_object_with_list` does — but it lived only in a
parser comment, so a future agent building Risk or ATT&CK would read #44, find a
ninth reason code, and either add it or spend a round working out why it is
absent. Also unaccounted and now stated: duplicate JSON keys inside one entry, and
extra top-level keys alongside a correct `capabilities` (the latter is adjacent to
#46 but not the same defect).

Two rounds, and the pattern D-045 recorded holds: the defect rate did not fall,
it moved. Round 1 found the code; round 2 found the claims about the code.

### What the adversarial pass changed (round 3)

Three lenses this time, two of which nothing had used: a regression hunt on
round 2, a SECURITY and tenancy pass, and a CONSULTANT-REALITY pass that worked
out the exact text a person sees in five real scenarios. Round 3 found more than
rounds 1 and 2 together, and round 2's code changes all held — as round 1's had.
The pattern is now unmistakable: each round's fixes survive, and each round finds
a class of defect the previous round was not looking for.

**A 500 after a successful commit.** `_bounded_key` claimed in its own docstring
to share `_bounded`'s echo-back path. It did not: `_bounded` runs everything
through `repr()`, which escapes every non-printable code point; `_bounded_key`
returned the model's `str` RAW, and that is the only branch a well-formed `code`
can take. `json.loads` accepts an unpaired surrogate escape, so such a `code`
reached `dropped[].key` intact, `db.commit()` SUCCEEDED — suggestions applied,
provenance stamped, audit row written, `llm_calls` marked COMPLETED — and only
then did the response encoder raise. The consultant saw "an internal error
occurred" over a database that had already been rewritten, and `ZtWorkspace`'s
catch does not re-fetch, so the grid kept showing pre-run values. A 500 after the
commit is worse than a refusal. The cheaper variant needs no exotic encoding at
all: a right-to-left override in `code` renders in the admin alert with the
override live, because React escapes markup characters and not control ones.
Fixed by escaping non-printables while leaving printable codes untouched, in ZT
and in CSF's identical `_bounded_key_part`.

**Two user-facing severity bugs, both of which reported success over failure.**
A run losing 100% of its values to field-name drift routed every record to the
deliberately-quiet `NOT_UNDERSTOOD` block: "AI applied 0 of 74" in calm secondary
grey, no alert anywhere — while "applied 0 of 0" got one. The quiet block's own
comment justifies it only for runs where everything asked for WAS applied, and
nothing enforced that; this is the #31 constraint inverted. Worse, `WorkflowStep`
took `done={runResult !== null}`, so a green success badge and a "— done" heading
sat directly above that line. Severity is now derived from whether anything was
applied, with EXACTLY one assertive region: the failure block when there is one,
the headline when there is not. Two alerts announce over each other, which is why
the first attempt at this — escalating the quiet records into the alert — was
rewritten rather than kept.

**A remedy that could not work.** `update_answer` sets `locked` and never writes
`answer_source`, so every locked row whose stage was never AI-written is
simultaneously `locked` and `protected`. (Round 4 correction: this said "every
consultant-typed locked row", which overstates it — a row the AI drafted keeps
`answer_source = "ai"` through a consultant's correction, so `protected_keys`
excludes it. The workspace copy had this right where the decision record did
not.) The skip bullet said "row is locked" while the paragraph below
counted the same row and instructed "Load an API key to run real analysis over
them" — but live runs skip locked rows too. A consultant following that advice
pays for a call and gets the identical result with no explanation. The paragraph
now says the two blocks describe the same rows, and scopes the remedy to exclude
locked ones.

**Two numbers about the same rows, in different units, with no bridge.** In the
commonest demo flow the panel showed "10 suggested values skipped" beside "5
answers left untouched" — a factor of two, because ZT charges `current` and
`target` per row, stated nowhere. The skip bullet now carries its row count as
well as its value count, which is also what makes it reconcilable when the ratio
is not 2 (a model that suggests for only some protected rows).

**Also fixed:** `unknown_key`'s label was ported from CSF and lost the half that
made it actionable — CSF asks "is that tier seeded?", and seeding is a button on
that page, whereas ZT has no such action and the consultant cannot fix a model's
spelling. It now says what they can do: set it by hand. `describeReason` looked
up an untrusted reason on an object literal, so `"toString"` resolved to an
inherited function and rendered as the empty bullet the guard exists to prevent.
`d.key ?? …` let an empty-string code render as a blank.

**Round 2's own claims needed three corrections**, which is the same shape round
2 found in round 1. Its `protected`-is-fixture-only fix left a fifth site
contradicting the four it fixed. Its depth-cap comment said the cap was "the only
path where the invariant holds vacuously"; duplicate JSON keys inside one entry
are a second and likelier one, since `json.loads` keeps the last and the earlier
value is gone before this code sees it — no hostile nesting required. And its
"exact" #51 scope was off by one in the expensive direction: `locked` needs no
live run, because `build_zt_ai_request` sends every row including locked ones, so
a fixture run over an API-locked row surfaces that reason end to end today. Six
of eight, not seven.

**Prompt-injection reach is real, new, and now stated.** A client-role user's
`notes` go into the egress payload verbatim; the model's reply now lands on the
consultant's screen through `dropped[].key`. ~800 characters of tenant-chosen
prose can render inside the panel the consultant uses to judge whether the AI
draft is trustworthy. Bounded, escaped, no privilege gained, and #44 sanctions
`key`/`value` in the response — but before W1 that field never left the server.
The schema docstring justified it as "same trust boundary as the run result",
which is true of the MODEL and skips that a lower-privileged user seeds the
model's input. That is the unstated-carve-out shape, and it belongs here rather
than nowhere.

**What held.** Tenant isolation is clean: every query is anchored to the
tenant-verified service, the D-031 re-read cannot re-scope, and `dropped` is
built only from model output and hardcoded literals, so it cannot carry another
tenant's data. Logs and audit rows are counts-only, `dropped_by_reason`'s keys
cannot be attacker-controlled because the `Literal` validates at construction,
and the tests proving both are not vacuous. No new `llm_calls` hole. No DoS —
`_MAX_OUTPUT_TOKENS` is the real ceiling, though nothing in `zt.py` would notice
if it were raised the way `mitre_map`'s was. And the CSF zero-guard round 2 added
did not change the non-zero copy by so much as a space.

**Filed, not fixed** (at the time; #67 shipped in D-048): #67 — CSF has no provenance protection at all, so an
offline run silently overwrites hand-typed dimension scores where ZT protects the
equivalent work. Pre-existing, and made more likely by this step, because a
consultant who learns ZT's behaviour will assume it on CSF.

Three rounds, and the honest reading is unchanged from D-045: not "round 3 made
it correct", but that an audit gate keeps finding what a green suite cannot —
and that the classes of defect keep moving. Round 1 found the arithmetic, round 2
the claims, round 3 the security boundary and what a person actually sees.

### What the adversarial pass changed (round 4)

Two lenses: a regression hunt on round 3, and an ACCESSIBILITY pass nobody had
run. **Round 4's yield was as high as round 3's**, which is the opposite of what
"CSF needed four rounds" would predict — four was CSF's observed yield curve, not
a law, and this one has not flattened. Both lenses independently found the same
thing: **round 3's severity fix was half-right and half-backwards, and each half
failed in the channel the other half was not tested in.**

**Round 3 re-opened #31 in the exact workflow `protected` exists for.** Gating
severity on `applied === 0` alone meant an offline run in which every suggestion
was preserved BY DESIGN — a client submits all 37 capabilities, a consultant
presses Run AI with no key — rendered a red assertive alert reading "Nothing was
applied, every suggestion this run received was rejected or unrecognized", over a
run in which nothing whatsoever went wrong. Three elements below it the grey
block correctly said the same 74 values were skipped by design. And
`done={… suggestions_applied > 0}` left Step 1 permanently un-done for that
workflow, on every re-run: a guard that refuses to fire when it should. Severity
now derives from `lostValues` — what was actually lost — with by-design skips
excluded, and `ZtWorkspace` imports the same predicate so two places cannot
decide "did this run go well" by different rules.

**And the same fix under-fired in the audio channel.** `headlineIsAlert` demotes
the headline to polite whenever a failure block exists, so with failures AND
nothing applied the only assertive utterance was the failure block — which, by
its own zero-guard, says "**Some** suggestions could not be applied". A
screen-reader user heard "some" over a total loss while a sighted user read
"0 of 74" in the line above. The alert has to be a SUPERSET of the headline, not
a sibling of it; it now states the total when nothing applied. The round-3
invariant — "exactly one assertive region" — was correct about count and silent
about content, and the word "Some" that made the audio version wrong was chosen
in round 3 to fix the visual version.

**`agreedThroughout` claimed agreement over a shortfall.** Gated on
`applied > 0 && changed === 0` and not on losses, so a re-run where the model
volunteered a `confidence` key per capability printed "Every suggestion matched
what was already recorded" one paragraph above "these are part of the shortfall
in the line above". Now requires `lostValues === 0`.

**Three smaller ones, all the same shape — a fix that reads as coverage and is
not.** The `unknown_key` label round 3 rewrote to be actionable advises setting
the capability by hand; every catalogue capability is seeded as a row at
assessment creation, so an unknown key means the model invented a code the
framework does not have and there is no row to go to. It now says that. The skip
bullet's row count counted RECORDS, so two entries naming one locked code read as
two capabilities — in the number added specifically to reconcile with
`preserved_client_answers`, which counts rows. And the vitest added beside the
`Object.hasOwn` hardening used `"invented_later"`, which is `undefined` and
passes under `??` too — it could not detect the change it was added for. The
inherited-function case (`"toString"`) now has its own test.

**Round 3 ported one hardening to CSF and not the other, and tested neither.**
`_bounded_key_part` got the escaping fix with no test at all — reverting it left
the whole suite green over the commit-then-500 path. CSF now has the same three
tests ZT has. `describeReason`'s prototype lookup was left on the `??` form in
the file whose own docstring calls it "the reference implementation everyone
ports from" — fixes travelling from copy to original and not back is how a
codebase ends up with the original being the worst version of itself.

**Two claims corrected.** The preserved-answers sentence round 3 added — "these
are the same rows counted in the skipped line above" — is false whenever a
protected row is also locked, because the lock check runs first and wins, which
is precisely the overlap round 3 wrote the sentence to explain. And D-047's own
round-3 text said "every consultant-typed locked row is simultaneously `locked`
and `protected`"; a row the AI drafted keeps `answer_source = "ai"` through a
consultant's correction, so `protected_keys` excludes it. The workspace copy had
this right where the decision record did not.

**What held.** The escaping fix itself survived a determined attack: `repr(c)`
always uses single quotes for non-printables so the `[1:-1]` slice is always
correct; `' '.isprintable()` is `True` so codes with spaces pass through;
combining marks and astral characters are preserved; lone surrogates are the only
unencodable code points in a Python `str` and they are always escaped, so the
output is guaranteed encodable. The single-alert enumeration is structurally
sound across all five combinations. `#51`'s corrected six-of-eight scope is
accurate. `CLAUDE.md`'s new seed paragraph is accurate. No double announcement is
reachable. Severity is stated in words as well as colour everywhere, contrast
passes, and `WorkflowStep`'s done state is in the heading's accessible name
rather than only the ✓ badge.

**Filed, not fixed:** #69 (every admin live region is mounted with its text, so
`role="alert"` fires and `aria-live="polite"` almost certainly never does —
failures announce and successes do not; plus `role="alert"` wrapping an unbounded
itemized list, since `ITEM_CAP` caps per reason group and not overall). #70
(`AttackWorkspace` still marks its step done for a run that applied nothing — the
rule ZT just adopted, unstated exemption). #71 (`csf.py` stores `what_we_found`
unescaped — the one raw-model-string path round 3's fix did not reach, and the
only durable one). #68 (the prompt-injection surface, documented in round 3 and
not mitigated — filed because "documented" was doing work "mitigated" should have
been doing).

Four rounds, and the honest reading is unchanged and getting sharper: the audit
gate keeps finding what a green suite cannot, the classes keep moving, and **the
yield has not fallen**. Round 1 found the arithmetic, round 2 the claims, round 3
the security boundary and what a person sees, round 4 the workflow the fixes
themselves broke and the channel nobody had listened to. Anyone reading this to
decide whether to stop at four should read the yield, not the count.

### What the adversarial pass changed (round 5)

Two lenses: PERSISTENCE/EXPORT, which nothing had audited, and a regression hunt
on round 4. Both were high-yield, and between them they produced the two most
important results of the whole exercise — one about the product, one about this
component's design.

**The export layer discards the values this feature exists to account for.**
`finalize_zt_deliverable` calls `analyze_gaps(cat_fw, stage_map, notes=notes_map)`
with no `targets` and no `target_stage`, while the `/gap-analysis` route the
consultant reviews and approves from passes both. So `analyze_gaps` falls back to
`DEFAULT_TARGET_STAGE = 3` for every capability, and the exported PDF/XLSX/DOCX
lists a different gap set than the consultant approved, under a heading stating a
target the engagement never agreed to. A capability stored as
`maturity_stage=1, target_stage=2` exports a "Target stage" cell reading **3** —
a number the database does not contain and the client never chose. `intake.py`
makes the ZT target mandatory and carries the comment "we re-check server-side so
the target is never silently dropped (the consultant relies on it)"; the export is
exactly where it is silently dropped. Pre-existing and filed as **#73**, with the
companion truncation defect (**the exported gap plan is capped at 20 with
`total_gap_count` rendered nowhere**, while the on-screen list discloses it) as
**#75**. Neither is fixed here: they change the content of client-facing
deliverables and belong in a change whose subject is the exporter.

The lens also confirmed the thing worth knowing: **apply → database → score is
exact.** Every input was traced — `2.0`, `"2"`, `2.0000000001`, `True`, `"1e400"`,
a 400-digit integer, `"nan"`, `4` on DoD — and none diverges; 1-4 are exactly
representable as doubles so `int(n)` is exact whenever `n == int(n)`; SQLite and
Postgres agree on `SmallInteger`. The audit accounting is durable (JSONB, no
truncation) and correctly reaches no exporter. A released deliverable is a true
byte snapshot and cannot be changed by a later edit. The divergence is entirely at
score → document.

**And the severity rule was wrong for the third consecutive round — which is the
finding.** Round 4's `done` fix re-opened round 3's defect in a new state: with
`received === 0` the response is wholly lost, and because every drop path also
increments `received`, `dropped` is then necessarily empty, so "nothing was lost"
passes vacuously and the step rendered a green ✓ and "— done" directly above the
red "the AI returned no suggestions at all" alert. Round 3's rule returned false
there; round 4 widened the disjunct to fix the all-protected workflow and swept
this in.

Two more of the same shape: the alert lead quantified over `suggestions_received`,
which is charged BEFORE the lock and protection checks, so a run with 60 skipped
and 14 lost values announced "all 74 suggested values were rejected or
unrecognized" — overstating the failure five-fold and contradicting the block
below it. And `agreedThroughout` said "every suggestion matched what was already
recorded" over 60 suggestions that were declined unseen. Both now quantify over
what was actually lost or evaluated.

**The response is a truth table, not another conditional.** The predicate has
changed shape three times — `applied === 0`, then `applied === 0 &&
failed.length === 0`, then `applied === 0 && lostValues > 0` — and each version
was right about the case that prompted it and wrong about one nobody had listed.
The inputs are four booleans, so the whole space is thirteen renderable states.
Those are now enumerated in a table-driven `describe("severity matrix")` asserting
alert presence in each, plus an invariant that two assertive regions are never
reachable. `lostValueCount` — which `ZtWorkspace` uses to decide step completion,
and which had **no test at all**, so reverting the done-rule to either of its two
previously-wrong forms passed every gate — now has its own. The general lesson is
recorded in `CLAUDE.md`: write the matrix first, because a matrix written after
the fix only pins the fix.

**Round 4 committed the exact failure it had just diagnosed.** It found that the
`Object.hasOwn` vitest used `"invented_later"` — `undefined`, and so satisfied by
the old `??` form — and fixed that in ZT. In the same pass it ported the hardening
to CSF with only the defective test, in the file whose own docstring it quotes as
"the reference implementation everyone ports from". CSF now has the `"toString"`
twin. That is the fifth instance this session of a test that agrees with itself by
construction, and the reason **#72** proposes a systematic sweep rather than
another lesson.

**Also corrected:** the `unknown_key` label. Round 4 rewrote it from unfollowable
advice ("set it by hand", when every catalogue capability is already a seeded row)
into an accusation nothing enforces ("the model invented a code this framework
does not have") — the lookup is against the rows seeded when THIS assessment was
created, not the live catalogue, so a later catalogue addition or a code valid for
the other framework lands there too. It now describes rather than diagnoses. And
two claims in round 4's own record were narrowed: the "single-alert enumeration
sound across five combinations" omitted the skipped dimension, which is precisely
where this round's findings lived.

**Stated, not fixed:** the severity threshold is still a cliff at `applied === 0`.
A run applying 37 of 74 with the other 37 lost to drift renders entirely calm. The
unrecognized block still explains the loss in words, and #31 argues against making
a run that produced real work assertive — so this is a deliberate choice, recorded
here because round 4's record implied the state space was covered when it had not
been enumerated. **#74** carries the CSF port of this whole severity model, which
never happened and which D-047 had not admitted.

Five rounds. The yield has not fallen, and the classes have not repeated: the
arithmetic, the claims, the security boundary and what a person sees, the workflow
the fixes broke, and now the document a client actually receives. What changed at
round 5 is the kind of conclusion available — for the first time the finding is
not "here is another defect" but "this predicate is the wrong shape", which is the
signal that patching should stop and enumeration should start.

**Ref:** `apps/api/app/routes/zt.py` (`_as_number`, `_hidden_value_count`,
`_bounded`, `_bounded_key`, the apply loop), `apps/api/app/schemas/zt.py`
(`ZtDroppedSuggestion`, `ZtRunAiResponse`), `apps/api/app/ai/jobs.py`
(`_ZT_SCORE_PROMPT`), `apps/api/app/ai/fixtures.py` (`_fixture_zt_score`),
`apps/web/src/lib/zt/types.ts`, `apps/api/tests/unit/test_zt_run_ai.py`.

## D-048 — Every suggestion job refuses a wrong-shaped list, and CSF protects hand-typed scores

**Date:** 2026-08-19 · **Issues:** #67, #77 · **Migration:** 0042

Two correctness-only changes, no new features, taken together because both are
"the AI layer must not lose work silently" and neither has dependencies.

**All four suggestion jobs now refuse a non-list.** `mitre_map` and
`risk_synthesize` joined `csf_score` and `zt_score` on
`parse_json_object_with_list(<key>)`. Both were broken, in opposite directions:
ATT&CK's `(data.get("techniques") or [])` turned a scalar into an empty batch and
a dict into an iteration over its KEYS, contributing nothing with no error; Risk's
batching loop did the same, and only a truthy non-iterable reached a TypeError
that escaped as an untyped 500. The first draft of this decision claimed Risk
produced a bare 500 for a scalar — that was wrong, and is corrected in the code
comments rather than left as the rationale a future reader inherits.

**Scope stated, because it was overstated once.** `mitre_map` is BATCHED and
`attack.py` counts a failed batch and continues, raising only when every batch
fails. So the guard turns a silently-empty batch into a counted one; it does not
fail the run. One bad batch of 26 still returns 200 with `batches_failed=1`, and
that field is rendered nowhere in the web app. The ledger improved; what the
consultant sees did not.

**`tech_debt_extract` is deliberately NOT included** and is the last unguarded
parser (#77). It needs per-item coercion the generic parser does not do, so the
fix is a composition rather than a substitution. Its blast radius is smaller
because `reconcile_rows` reports every uploaded row as excluded when extraction
returns nothing — loud-ish rather than clean. The claim "every registered job now
carries a shape guard" was written and then narrowed; it is not true and should
not be written again until #77 lands.

**CSF protects hand-typed dimension scores from offline runs (#67).** ZT has done
this since the 2026-08-04 incident, in which a fixture run replaced a real client
self-assessment with canned demo values — average maturity 2.14 → 1.49, Identity
3.00 → 1 — unrecoverably. `protected_keys` had exactly one caller, so pressing
Run AI with no key loaded silently overwrote a consultant's Working Profile.

Migration 0042 adds `csf_dimension_scores.answer_source`, and **this reverses a
stated rationale in 0035**, which said the column was "Zero Trust ONLY,
deliberately" because CSF's Run-AI never touches `csf_answers`. That reasoning was
right about the question it asked — the CLIENT's submission was never at risk on
the CSF side. It did not consider the other population: `csf_dimension_scores` is
where a CONSULTANT types the Working Profile by hand.

**Why a column rather than a value test.** ZT can ask "is this row answered?"
because `maturity_stage` is nullable. Every CSF dimension is `NOT NULL DEFAULT 0`
and 0 is a legitimate score, so "has a value" is true for every seeded row the
moment a profile is created. Protection has to key on "somebody actually wrote
this", which nothing recorded.

**CSF does NOT stamp `SOURCE_AI`, and must not — this is where it diverges from
ZT on purpose.** ZT stamps because its `is_answered` keys on the value, so a row
the AI answered would otherwise be protected from the AI's own next run. CSF's
`is_answered` keys on the source column, so the predicate collapses to
`answer_source == "consultant"`: NULL and `"ai"` are both unprotected, and writing
`"ai"` can only ever REMOVE protection.

The first cut of this change stamped `SOURCE_AI` from the before/after diff,
copying ZT. The adversarial round caught it, and the defect was the one #67
exists to prevent, reintroduced by #67's fix: protection is per-ROW while
`_RUN_FIELDS` is six fields, so a live run that rewrote only `what_we_found`
stamped the whole row `ai` and stripped protection from five hand-typed scores the
model had merely agreed with. The next offline run overwrote them and reported it
as an applied change. `zt.py` carries a comment warning against exactly this
shape — "a run that merely proposes a target has not answered the assessment and
must not strip a stamp from a value it never wrote" — and the port omitted the
narrowing at six times the granularity.

Pinned by a MODE-FLIP test (consultant edit → live run → offline run). No
single-mode test can express it, which is why the first suite was green over it.
The characterisation test that looked like coverage for the stamp is labelled as
characterisation-only in place, rather than deleted, because it does constrain the
predicate even though it cannot see the stamp.

**An explicit clear counts as consultant work.** Gating the stamp on
`data[f] is not None` meant a consultant DELETING an AI narrative left the row
unprotected, so the next offline run repopulated the text they had just removed.

**Pre-0042 rows are not protected**, and no backfill can help: existing
hand-typed scores are indistinguishable from seeded defaults. They become
protected the first time they are edited again. Backfilling "everything existing
is consultant work" would freeze every seeded row against offline runs and break
the demos the NULL semantics exist to keep working.

**CSF's skip copy is now grouped by reason.** It hardcoded "you locked that row",
which was true while `locked` was the only by-design skip and a false statement
about who decided the moment `protected` joined it. It also counted records where
it meant rows. Both fixed together, because adding the reason without the copy
change would have shipped the false statement.

**Known and not fixed here:** `llm_calls` records COMPLETED for a response
rejected after parsing (#47), and this change extends that to two more purposes —
both batched, where each batch is separately billable and the failure path commits
the row precisely so the evidence survives. The evidence that survives is wrong.
Named here rather than left to be rediscovered.

**Ref:** `apps/api/app/ai/jobs.py`, `apps/api/app/routes/csf.py`
(`patch_dimension_score`, `_apply_suggestions`, `run_ai`),
`apps/api/app/models/csf_profile.py`, `apps/api/alembic/versions/0042_*.py`,
`apps/api/app/schemas/csf.py`, `apps/web/src/lib/csf/types.ts`,
`apps/web/src/components/admin/csf/CsfPlaybookPanel.tsx`.

## D-049 — An exported document uses the client's contracted target, discloses what it omits, and records which target it used

**Date:** 2026-08-20 · **Issues:** #73, #75, #79 (filed out of it: #84, #85)

Three issues, one defect: `analyze_gaps` called without the target the rest of
the product resolves, and a truncation nobody disclosed. They merge together
because splitting them would have shipped the half-fix the third one is about.

**The exporters now use the engagement target.** `finalize_zt_deliverable` called
`analyze_gaps` with neither `targets` nor `target_stage`, and the CSF twin with
no `target_tier`, for the life of the repo. Every exported document was computed
against `DEFAULT_TARGET_STAGE`/`TIER` (3) while the dashboards used the client's
choice — and intake makes that choice MANDATORY, so roughly two-thirds of
engagements had a document that disagreed with every screen showing the same
assessment. A capability stored with target 2 printed as 3: a number the database
does not contain and nobody chose.

**Which target, precisely.** The document follows the CONTRACTED target from
intake, not the `/gap-analysis` target selector. The selector is a query
parameter the consultant moves freely to explore a phased goal, and finalize
never receives it, so leaving it on 3 and finalizing yields an S3 screen and an
S4 document. That is the intended reading — the artefact belongs to the
engagement, not to the last thing anyone clicked — but it is a policy rather
than a consequence, so both finalize audit rows now record `target_*` and
`target_*_source` ("client" vs "default"). A `gap_count` without its target was
uninterpretable the moment the target stopped being a constant, and a fallback
that happens to equal a choice must not read as one. The first draft of the ZT
comment claimed the fix tracked "the view the consultant reviews and signs off";
it does not, and the comment was corrected rather than left as inherited
rationale.

**Truncation is disclosed in all three renderers, for both services.**
`analyze_gaps` slices to `DEFAULT_TOP_N = 20` while keeping the true count, and
XLSX/DOCX/PDF printed only the slice, so a client read 20 of 106 remediation
items with no way to tell. ATT&CK has always disclosed this in its heading; CSF
and ZT now do too, and no exporter truncates a client-facing list silently.

**#75 was filed against ZT and is fixed for both.** The first implementation
fixed ZT alone. The audit caught it, and correctly noted that the CSF half was
made _worse_ rather than merely left alone: raising CSF's target from the engine
default to the client's tier INCREASES the gap count, so more is hidden exactly
where the disclosure started mattering more. `test_csf_exporters.py` had asserted
the truncation as intended behaviour (`ws.max_row == 21` over a 106-gap fixture)
without ever asking whether the document said so.

**The ZT caption does not name a single target for every row.** ZT honours a
per-capability `target_stage`, so `gap.target_stage` is the engagement value and
rows may legitimately differ; a headline "at target S4" over a row reading S2
would be the same contradiction one document down. The caption names the
engagement target and points at the per-row column. CSF takes a single tier with
no override, so its caption can and does name one target.

**Two of the tests written for this could not fail**, both caught by the audit
rather than by any gate — the eighth and ninth instances of the #72 pattern.
The CSF assertion `str(dash["total_gap_count"]) in doc_summary` was satisfied by
the coverage fraction: with the fix reverted the summary reads `106/106
subcategories scored; 0 gap(s) at target T3`, and `"106" in ...` is True. The ZT
per-capability half (`targets=`) was deletable with the whole suite green,
because the only test touching it left every `target_stage` NULL. Every
assertion in this change was subsequently verified red-on-revert individually,
and that verification is the practice #72 should mechanise.

**Out of scope, filed rather than folded in:** `routes/risk.py` re-derives the
comparison inline against a hardcoded 3 and so fell outside the `analyze_gaps`
sweep (#84); the self-assessment submit schemas accept a target of 1 where
intake enforces `>= 2`, which was inert until this change made stored targets
load-bearing (#85).

**Known coverage gap:** `seed_demo.py` creates services with no
`source_request_id`, so no seeded service and no e2e spec exercises any of this —
all three fixes are proven by unit tests that attach a `ServiceRequest` by direct
DB write. That is also why nothing caught the defect for the life of the repo:
the fixtures could not express it.

## D-050 — An exported document uses the contracted target, and the gap-analysis selector affects nothing but the screen

**Date:** 2026-08-20 · **Issues:** #87 (the decision), #89 + #90 + #85 (required follow-ups) · **Follows:** D-049

D-049 shipped this behaviour by implication while fixing #73/#79. It was
corrected in a comment and then filed as #87 rather than left settled by the
correction, because the behaviour shipping is not the same as the choice being
made.

**Decided: the document uses the CONTRACTED target from intake**, not the
`/gap-analysis` selector. The deliverable is a contractual artifact, not a
snapshot of exploratory UI state. The rejected alternative — the target the
consultant last had on screen — produces output that silently depends on ambient
UI state at the moment of a click, so two consultants reviewing the same
assessment could produce different documents and neither could reproduce the
other's. That is a worse defect than the one D-049 fixed.

**No behaviour change: this confirms what D-049 already shipped.** What it adds
is the obligations, which is the point of deciding it explicitly.

**The selector affects nothing but the screen, and the UI must say so (#89 —
required, not optional).** A consultant who moves the selector to discuss a
phased goal, leaves it, and finalizes gets a 12-gap S3 screen and a 37-gap S4
document with nothing explaining the difference. The behaviour is correct; the
silence is what makes it read as a permanent bug. The load-bearing part of #89
is surfacing the divergence **at Finalize** — labelling the selector alone leaves
it discoverable only by whoever reads carefully before clicking.

**The gap this decision creates (#90).** There is no consultant-side write path
to the contracted target. The only two writes are in the client self-assessment
submit (`csf.py:664`, `zt.py:1186`); `admin.py` only reads it.

An earlier draft of this record said the value was therefore "amendable exactly
once and then frozen." **That was wrong and is corrected here.** The 409 guard is
on the LATEST ASSESSMENT's status, not a global one-time lock, and
`POST /services/{id}/assessments` — admin-only — cuts a new assessment version
once the prior one has moved on. A new version starts DRAFT, so the client's
self-assessment submit is reachable again and writes the target again. A re-scope
IS achievable today: the consultant cuts a new cycle, the client re-submits with
the agreed target.

**What is actually wrong with that path** is the price, not its absence:

- It **discards the completed assessment**. New versions seed blank answer rows
  (`ZtAnswer(assessment_id=…, capability_code=…)` with no stage), so changing one
  number costs all 87/106 answers and the work behind them.
- It **cannot be completed by the consultant alone** — the client must re-submit.
  An unresponsive client means the target cannot change.
- The client can set a target the consultant never agreed to, and it silently
  governs the deliverable.

So the mechanism exists and is unusable for its purpose, which is a different
finding from "no mechanism exists" and points at the same fix.

**Direction on #90: a consultant-side amend route AND an approval-time target
snapshot, together.** They are not alternatives. The amend route is how a
legitimate change gets made; the snapshot is what stops an already-approved
report drifting when the underlying request is edited later. Without the
snapshot, adding the amend route makes things WORSE — a consultant edit would
retroactively change what a released deliverable claims it was measured against.
The snapshot is the same shape and the same lifecycle moment as W3's
approval-time membership snapshot, so they should be built together rather than
inventing a second mechanism.

**The test pinning this decision is required scope for #89, not a follow-on.**
#89 exists because the selector/document divergence reads as a bug, and the
obvious "fix" for anyone who has not read this record is to wire the selector
into finalize — silently reversing the decision, breaking nothing, caught by no
current test. The assertion must name the TARGET (`gap(s) at target T4`), not a
bare gap count: `str(count) in summary` is precisely how instance 8 of the #72
pattern passed vacuously in this same area.

**It re-weights #85.** Filed as narrow and API-only, it is in fact the sole
amendment path for the value that now governs every deliverable, and it accepts
`target = 1` where intake enforces `>= 2` — producing a document reading
`0 gap(s) at target T1` with no gaps at all. Fix it with #90, not separately.

**No test pins either reading yet — and that is #89's required scope**, per the
paragraph above rather than a hope. An unpinned decision is the same class of
thing as an untested fix, and this repo has nine recorded instances of the
second.

## D-051 — W8a: the #72 sweep is two tiers, and each states what it cannot catch

**Date:** 2026-08-20 · **Issues:** #72 (the sweep), #92 (filed by its first run) · **Follows:** D-049, D-050

Nine recorded instances of a test that passes whether or not the fix it guards
is present. The rule has been in `CLAUDE.md` since instance 2; instances 8 and 9
were written anyway, by someone who had read it that day. **That is a mechanism
problem, and W8 was split so half of it could be built now** rather than deferred
behind five workstreams that each ship new tests.

**Tier 1 — `scripts/check_test_integrity.py`, static, blocking, in CI.** Two
signals, both derived from real instances:

- **TI001** — a test importing a private CONSTANT from the module it tests
  (instance 1: `_PARSER_ROW_KEYS = (..., *_DIM_FIELDS, ...)`).
- **TI002** — a containment assertion whose needle carries no literal text
  (instance 8: `str(dash["total_gap_count"]) in doc_summary`, satisfied by the
  coverage fraction `106/106 subcategories scored`).

Neither forbids the pattern; both demand a written `# test-integrity:` reason,
because the same syntax is sometimes correct. Importing `_CSF_SCORE_PROMPT` into
a contract test is RIGHT — the prompt is the spec. Importing `_DIM_FIELDS` to
build the expected response is the defect. No static rule separates them, so the
checker makes someone say which one it is.

**Both rules were narrowed after measuring, and the measurement is the point.**
The first implementation flagged every private import and every bare `x in y`:
**41 + 38 findings, of which 5 + 2 were real.** Restricting TI001 to
constant-style names drops 36 FastAPI dependency-override handles
(`_llm_dep`, `_storage_dep`) that say nothing about what a test asserts;
restricting TI002 to explicit `str(...)`/f-string stringification drops 36
assertions that cannot be told from `key in mapping` without type information.
A rule whose signal is 12% of its output gets muted, and a muted rule is worth
nothing. One of the checker's own tests demanded the broad behaviour and was
**wrong**; it is inverted now, and says so in its docstring.

**Correction (2026-08-20): W8b's deferral reasoning was wrong within a day.**
The reasoning is not in this record — it lives in `DELIVERY_PLAN.md` (the W8b
bullet in the W8-split section, and the W8b row of the deferred table), which is
the LIVING document people plan from. Both copies are annotated there; saying
"below" here pointed at text that was in another file, so the append-only log
carried the correction while the document people act from carried the falsehood.
It read "invoking it manually is demonstrably working". Three consecutive CODE PRs then merged with the §14
audit silently skipped (#93, #94, #95), each green, each putting a defect on
`main` that the audit found afterwards — including a client-facing fabricated
gap. The evidence used to defer the mechanism was false. That is this decision's
own argument (mechanism beats discipline) applied to the gate that enforces it,
and got backwards. The response is NOT full W8b: a deterministic merge-blocking
check now requires recorded audit evidence on any code PR
(`scripts/check_audit_evidence.py`), which closes the silent-skip failure mode
without taking on the per-PR cost and non-determinism W8b was rightly deferred
for. Whether W8b itself moves up remains open.

**Tier 2 — `scripts/mutation_sweep.py`, scheduled, non-blocking.** Change the
code, does a test go red — the automation of the revert-each-fix-individually
practice that found instances 8 and 9 by hand.

**It is purpose-built rather than mutmut, and the decisive reason is
`DropKeyword`.** Instance 9 was `targets=` being deletable from
`finalize_zt_deliverable` with the entire suite green: a MISSING ARGUMENT, not a
wrong operator. mutmut mutates expressions, not call signatures, so it would not
have caught it either. Validated end to end against that exact case — the tool
independently generates the `drop targets=` mutant at `zt.py:1619` and confirms
the test added in D-049 kills it.

**Not a PR gate, deliberately.** Every mutant costs a full run of the selected
tests and the unit suite is 13-16 minutes, so 50-150 mutants cannot sit in front
of a merge. It runs nightly over files changed in the last day, plus manual
dispatch. A non-blocking mechanism that runs beats a blocking one that gets
disabled.

**What neither tier catches, stated because overstating it would be this exact
defect one level up.** Tier 1 is structurally blind to instance 2 (a test whose
SETUP performs the step the code under test is supposed to perform) — no static
signature exists for it. A surviving mutant is a QUESTION, not a verdict: some
mutants are semantically equivalent and some paths are untested by design. **This
does not close #72**, and #72 should not be closed on the basis that a checker
exists.

**The sweep's first run filed #92.** `test_csf_ai_contract.py` checks
parser→prompt but never prompt→parser, and its end-to-end half builds its
response body from the parser's own constants. The static half is sound and the
import is justified in place with a marker naming the issue — so the gate stays
green without the finding becoming invisible, which is the behaviour a
justification mechanism has to have to be worth anything.

## D-052 — Tech Debt: the shape guard closes, and the reconciliation stops vanishing when it cannot name rows

**Date:** 2026-08-20 · **Issues:** #77 · **Follows:** D-048, D-051

DELIVERY_PLAN item 3, Tech Debt half. ATT&CK's half stays blocked on W2 per the
plan — same files, and the audit wants the post-rewrite shape.

**#77 closes, and the invariant is now true.** `tech_debt_extract` was the last
AI parser with no top-level shape guard, carrying both halves of the family:
`decoded.get("items", []) if isinstance(decoded, dict) else []` swallowed a
bare-list top level whole, and `for item in raw_items` iterated the KEYS of a
non-list `items`. Either reported zero capabilities, indistinguishable from an
inventory holding nothing recognisable — and this path feeds the ATT&CK
allow-list, where an empty capability list once produced 607 fabricated `gap`
rows.

**The fix shares the CHECK, not the whole parse.** #77 proposed composing
`parse_json_object_with_list`. That would have been a regression:
`_parse_response` recovers JSON a provider wrapped in prose, tolerance
`parse_json` does not have, so a wholesale swap would have turned working
providers into hard failures with no test noticing. `require_json_object` and
`require_list_at` were split out of the existing parsers and are now called by
both. `jobs.py`'s carve-out comment is removed: every registered job carries a
top-level shape guard, and that sentence is now writable.

**The prose retry had its own hole, found by the test written for the guard.** It
considered `{...}` only, so a bare list wrapped in prose sliced down to the first
ITEM's braces and decoded as one object with no `items` key — the guard never saw
a list, and the run reported one capability or zero. It now considers `[...]`
too, first-decoding-candidate wins so an unrelated citation bracket cannot
hijack the slice.

**The reconciliation disappeared exactly when it mattered most.**
`reconcile_rows` deliberately produces two things: `excluded`, a COUNT that is
trustworthy in every case, and `excluded_rows`, the NAMED rows, populated only
when every item attributed itself to a source row — its comment says the naming
is "withheld rather than guessed" and "the count stays honest". The count did not
stay honest, because nothing persisted it. Both surfaces measured the NAMED list
(`len(cap_list.excluded_rows or [])`; `(list.excluded_rows?.length ?? 0) > 0`),
so a provider omitting `source_row_index` on one item produced an empty list, no
disclosure at all, and an unqualified **"Total annual cost"** over a partial
figure. That is the 2026-08-04 incident — 21 rows / $1,634,236 presented as 12 /
$891,796 — reachable through the mechanism added to prevent it, and the third
recorded instance of a false branch dropping the record instead of emitting it
under a different reason.

**Derived, not stored.** `source_rows_total - source-derived items` equals
`len(excluded_rows)` whenever attribution is complete and recovers the true count
when it is not. A persisted counter would need decrementing on the
include-an-excluded-row path and would be a second source of truth to drift, so
no migration was added. Children of a decomposed bundle carry `parent_item_id`
and are not counted — the same correction the workspace made after `28 > 32`
went false and unmounted the disclosure permanently. When the rows cannot be
named, both surfaces now say so rather than showing a bare number that reads as
a rendering bug.

**Fixed on both surfaces in the same change**, per the twins rule that #86 was
caught violating.

**One existing test was rewritten, and the reason is stated rather than
implied.** `test_deliverable_reconciliation.py` constructed `DeliverableContext`
directly with `excluded_count=excluded` passed in, so it asserted the rendering
of a number it had supplied and never exercised the code that derives it. It now
builds through `build_context`. That is the #72 shape, found while changing the
code underneath it.

**Audited and found sound**, recorded so the next pass does not redo it: the
exporters iterate the full item list with no `top_n` (no #75 twin here);
`cost_label` already refuses to call a partial figure a total; `overlap.py`'s
`costed[:5]` is a "top-cost" card that names its own bound and publishes
`total_items` alongside; Tech Debt has no maturity-target concept, so #73/#79
have no twin in it.

## D-053 — W3: approving a Tech Debt list records WHAT was approved, and the ATT&CK allow-list reads that

**Date:** 2026-08-20 · **Issues:** #32 (closed by this) · **Migration:** 0043 · **Unblocks:** W2

DELIVERY_PLAN item 4, and the head of the long pole. **Option A, the
approval-time membership snapshot**, as the plan of record scoped it.

**The problem, restated from `main` rather than from the plan.**
`_editable_list_or_404` blocks RELEASED and DISCARDED only, so the entire window
between approval and release is mutable through five doors. Two of them change
what the ATT&CK allow-list contains: `patch_capability_item` can rewrite `name`,
and the security-classification confirm queue removes a row from
`security_scope_filter` **by design**. `attack.py::_client_tool_names` turns
those names into a HARD allow-list whose own module docstring states the stakes —
"Drop a real security tool from it and the model cannot name it, so the technique
it covers reads as uncovered. That is a fabricated gap." So "confirmed against
the approved list" was checked against whatever the list had since become.

**W4 made the window real rather than theoretical.** Release now flips the list
to RELEASED (D-046), which is what brought `_editable_list_or_404`'s lock to
life; before that the lock was dead code and the list was mutable forever. The
window is now APPROVED → released, and ATT&CK runs happen inside it.

**Migration 0043 adds `capability_lists.approved_membership`** —
`[{item_id, name}]` for every item in security scope at the moment of approval.
Approval writes it; `_client_tool_names` reads it for any list that has one.
Item ids are stored alongside names because a name alone cannot be traced back to
its row once the name has changed, which is the failure this exists to survive.

**It is a snapshot, not a lock, and that is the decision.** Editing an approved
list is a real workflow — the confirm queue exists on purpose and excluded-row
recovery is a first-class feature. #32 deferred this precisely because making
APPROVED immutable would break both. What was actually wrong is that the edit
silently rewrote history. Re-approval refreshes the snapshot, so the escape
hatch is explicit and audited; the audit row records
`approved_membership_count` AND `replaced_membership_count`, because a count
alone cannot say whether a re-approval changed the allow-list.

**Lists with no recorded membership still read live**, and the distinction is
deliberate: a DRAFT because mapping ATT&CK before approving the tech-debt list is
a normal order of work, and a pre-0043 list because NULL means "nobody recorded
this", which is not "nothing was approved". Inventing a membership for those
would assert something no consultant ever did (the C0 pattern).

**#32 closes.** Its failure scenario — "a list is approved with 20 reviewed
tools, someone adds 4 free-text rows via the excluded-rows recovery UI, all 4
enter the ATT&CK allow-list and egress to the model immediately, while
`approved_by`/`approved_at` still point at the earlier review" — no longer
happens: those rows are absent from the allow-list until someone re-approves.

**A claim in the plan of record does NOT hold on `main`, and is corrected rather
than acted on.** §7 asserts that `include_excluded_row` writing
`confidence_pct=None` makes "a row nobody reviewed render a green pill reading
'Human-curated' — an affirmative false claim". That is not true of this code:
`IncludeExcludedRowRequest` documents "the consultant supplies the values;
nothing is inferred from the raw row", and the route's own docstring says
re-parsing the raw row "would be guessing at exactly the point a human has
stepped in". All three writers of `confidence_pct=None` — excluded-row recovery,
add-components, and manual curation — are human-supplied values, so the badge is
accurate. No change made. Recorded here because the plan is the document the next
person will read.

## D-054 — The §14 audit gate is a merge check, not a line in a document

**Date:** 2026-08-20 · **PRs:** #98 (the gate), #96 + #97 (the defects that motivated it) · **Supersedes the deferral reasoning in D-051**

Plan §14 — "every workstream merges on a clean adversarial-reviewer audit, not
on a green suite" — was skipped on three consecutive code PRs (#93, #94, #95).
All three were green. All three put a defect on `main` that a retro-audit then
found, including a client-facing fabricated gap (#96).

**Two causes, and only one of them was mine to forget.** The gate lived in
exactly one place, `docs/plans/2026-08-08-cross-service-integrity.md:580`, which
is not auto-loaded; `CLAUDE.md`, which is, had no mention of it. And the agent
resolved a conflict between "do not invoke subagents unprompted" and §14
silently, in favour of not running it, instead of raising it.

**The first proposed fix was to document the gate in `CLAUDE.md`. Rejected by
Gene, correctly.** That is a discipline fix, and discipline against this exact
shape has failed nine recorded times (#72) — including instances written minutes
after the rule was logged. Visibility was never the binding constraint.

**The decision: a deterministic merge check** (`scripts/check_audit_evidence.py`,
`.github/workflows/audit-gate.yml`). A PR touching code fails unless its body
records an `## Adversarial audit` section with `Findings:` and `Disposition:`
lines. Stdlib-only, sub-second, no model in the loop — it costs none of what W8b
was rightly deferred for, and it is not a substitute for W8b either.

**What it proves is narrow and stated as such:** that an audit was RECORDED, not
that it happened or was any good. Same honesty convention as `SMOKE_TEST.md`.
What changes is that skipping becomes deliberate and visible instead of silent,
and all three misses were silent.

**Correction (2026-08-21): it is enforcing now, and this entry said otherwise
for a day.** "Adversarial audit recorded" was registered as a required status
check on `main` on 2026-08-20, along with the five CI checks and force-push
blocking. The paragraph below was true when written and is kept intact; what it
is missing is that the condition it names was met.

Two things the correction must not overstate, because the first draft of the
`DELIVERY_PLAN.md` update did: required checks bind **a non-admin merging via a
pull request**, `enforce_admins` is false so both developers bypass them, and a
PR is not required — and `audit-gate.yml` triggers on `pull_request` only, so a
direct push to `main` produces no check run at all. The gate is a guardrail on
the PR path, not a wall around `main`. Current state, what it covers, and what
it does not: `DELIVERY_PLAN.md`, "Branch protection: configured 2026-08-20".

Recorded here rather than only in the living document, which is the mistake
D-051's own correction records making in the opposite direction — "the
append-only log carried the correction while the document people act from
carried the falsehood". Append-only forbids rewriting history, not annotating
it; D-045 and D-051 both do exactly this.

**It is not enforcing yet, and that is the load-bearing caveat.** A workflow job
only reports. It blocks only once "Adversarial audit recorded" is a required
status check in `main`'s branch protection — and as of 2026-08-20 `main` has NO
branch protection rules at all, not even force-push blocking. Until that is
configured the gate is a visible red X and nothing more. Recorded here because
the first version of the gate's own docstring claimed it "blocks the merge",
which was false and was the #72 pattern one level up.

**Correction (2026-08-22): the "reject a CLAUDE.md rule" reasoning is partly
superseded.** D-057 adds a `CLAUDE.md` rule requiring the reviewer to be RUN, not
merely recorded. That is a different proposition from the one rejected here —
this entry rejected documenting a mechanism that already existed, where the red X
did the work. Nothing enforces _running_ it, so there is no mechanism to point
at. The caveat below about what this gate proves is exactly why: three PRs and a
sweep passed it on self-audits, and re-auditing that sweep overturned four of its
six verdicts. See D-057.

**Its own adversarial audit found eight defects in it**, all fixed before merge —
including `main()` having zero test coverage (inverting its exit code left the
suite green), `edited` missing from the workflow triggers (so a fixed PR stayed
red with no way to clear it), and `**Findings:**` in this repo's own prose style
being rejected. The gate caught its own defects only because it was audited; it
would not have caught them itself.

## D-055 — Unconfirmed support withholds a claim; it never becomes a gap, and it never withholds one

**Date:** 2026-08-21 · **Issues:** #101 (persistence), #102 (scoring) · **Plan:** `docs/plans/2026-08-08-attack-citation-resolver.md` §5.1, owner-confirmed 2026-08-08 · **Migration:** 0044

5.1 settled the rule — _a technique's status counts toward the score only when it
is backed by a CONFIRMED citation_ — and left three things for the
implementation. Each turned out to be a decision rather than a detail, and the
state matrix was written before the wiring specifically to surface them
(CLAUDE.md: "a matrix written after the fix only pins the fix"). It found two of
the three before any code moved.

### `gap` is NOT withholdable, and the first implementation had it backwards

`analytics._WITHHOLDABLE` shipped as `(COVERED, PARTIAL, GAP)`. Withholding a gap
looks conservative and is the opposite: `coverage_pct` is
`(covered + 0.5·partial) / (covered + partial + gap)`, so dropping a gap out of
`addressable` shrinks the **denominator** only. Ten covered beside ten gaps
reports 50%; flag every gap and the same assessment reports **100%**, with ten
findings deleted. A run in which more evidence was doubted claimed twice the
coverage.

A gap is an ABSENCE claim. Its evidence is the lack of a citation, so there is
nothing to withhold. `covered` and `partial` are the only statuses that assert
something a citation could fail to support. Locked in two places on purpose —
`app/attack/pending.py` never emits a gap code, and `_WITHHOLDABLE` would refuse
it if it did.

### Three states of evidence, not two — and this is what makes the rule usable

The first predicate was "pending unless a confirmed tool backs the status". It
was correct for every AI case and broke the entire manual workflow:
`test_heatmap_reflects_coverage_after_patches` set ten techniques to `covered`ﾠby
hand and the heatmap reported **zero** covered, 0% coverage, and nothing anywhere
in the product that could ever clear it. A consultant curating the matrix is the
AUTHOR of the claim, not a reviewer of the model's; 5.1 is about inferences, and
they made none.

So a row's citation record answers with three values:

1. **cited and confirmed** — a tool in one of the lists that no uncleared entry
   names. Backed.
2. **cited and not confirmed** — inferred (awaiting a human), rejected (resolved
   to nothing), or claimed with nothing cited at all. Withheld.
3. **never cited** — no entries. The status stands on whoever assigned it.

Cases 2 and 3 look identical on the stored row — `[]` over empty tool lists —
unless the outcomes that resolve to NO tool are recorded too. So they are:
rejections carry `tool: null` plus the string the model actually sent, and a
positive status the model cited nothing for gets a `no_citation` entry. Neither
has a tool to store, which is exactly why both must be stored. That is what makes
the plan's related defect ("a technique can read `covered` with EMPTY tool
lists") enforceable at all, by both of its routes.

### NULL is not `[]`, and NULL scores as pending

Migration 0044's tri-state. An earlier draft said #102 should "leave such a
technique scoring exactly as it does today" — the fail-open reading, and the same
shape D-054 rejected on the nullable-vendor default one layer up. Absence of
evidence is not evidence of confirmation. Affordable because **zero** ATT&CK
assessments have ever been RELEASED and there is no production deployment;
verified, not assumed.

### The exemption, stated rather than left to be found

`coverage_pct` is a ratio over what can currently be CLAIMED, so withholding a
row leaves both the numerator and the denominator. Invariant 1 ("a run whose
citations are ALL flagged scores no higher") holds — every positive claim is
withheld, `addressable` empties, the answer is 0%. Under PARTIAL flagging it does
not: nine confirmed `covered` beside one flagged `partial` reads 95% before and
100% after. No arrangement of exclude-from-addressable avoids this, and the
alternative — scoring a withheld row as zero — understates coverage rather than
declining to claim it, which 5.1 rejects as a different wrong answer.

The consequence is that **the percentage is not self-describing**, so
`pending_review` is rendered beside it on every surface that shows it: the rollup
card, the per-tactic table, and all three exporters. `test_narrowing_the_
denominator_can_raise_the_ratio_and_that_is_stated` is the test that says so, and
it exists to stop the count being quietly dropped from one of them later.

### How a withheld row is cleared

Three ways, all of them 5.1's second definition of confirmed ("a human cleared
it"): vouch for the entry, name a tool that resolves cleanly, or set the status
or tool lists through `patch_coverage` — which stamps the row's outstanding
entries as cleared, because the admin has taken authorship. Scoped to those four
fields: clearing a review queue as a side effect of fixing a typo in `notes`
would be a silent loss of the disclosure, which is #101 all over again.

Entries are STAMPED, never deleted. "A human accepted this" and "nobody ever
cited it" are different answers to why a technique counts, and an auditor needs
to be able to tell them apart.

A re-run **replaces** the list rather than carrying `cleared_at` forward. Matching
old clearances to new inferences by (tool, field, reason) would be inferring that
the judgement still applies, and inference is precisely what is not confirmation
here. It costs re-review after a rerun; the plan's tiebreak spends that.

### The demo data was modelling the defect

`seed_demo.py` wrote `covered` and `partial` rows with EMPTY tool lists — the
exact shape #102 withholds. It now cites real names from its own `_TD_ITEMS`
capability list, writes `[]` explicitly, and **raises** if any row it created
would be withheld, rather than letting the demo report a coverage number its own
data does not support.

## D-056 — A locked assessment cannot be re-run, so its pre-resolver citations are grandfathered once

**Date:** 2026-08-21 · **Migration:** 0045 · **Follows:** [[D-055]], migration 0044 · **Issues:** #101, #102

D-055 made `unconfirmed_citations IS NULL` score as PENDING. Migration 0044
priced that as affordable: "what it costs is one Run-AI on each of the existing
drafts, which is exactly the work that was never done for them."

**APPROVED assessments are not drafts, and nothing can reach them.** Every write
path refuses a locked parent — `run_ai` re-reads the assessment status before
committing and raises `assessment_not_editable`, `patch_coverage` raises "This
assessment is locked", and the new `confirm-citations` endpoint does the same.
An assessment approved before the resolver existed was therefore pinned at 0%
coverage permanently, with no action available anywhere in the product.

0044's affordability check verified **zero RELEASED** assessments. It never asked
about APPROVED. Measured on the dev database: **14 approved assessments holding
8,862 NULL-citation rows**, and 29 of 48 assessments dropping from ~62% to 0%.
The gap was in the reasoning, not the code — the code did exactly what it said.

### The decision, taken narrowly

Migration 0045 sets `unconfirmed_citations = []` for rows whose parent is locked
against every write path (`approved`, `released`) **and** whose column is still
NULL.

- **Only `IS NULL`.** A locked row that already carries an outstanding flag keeps
  it. A blanket `SET ... = '[]'` would erase the review queue #101 exists to
  persist — a worse defect than the one being fixed.
- **Not `draft`.** Reachable by Run-AI, which is the work 0044 said was owed.
  Grandfathering drafts would spend the fail-closed guarantee to save a click.
- **Not `discarded`.** Equally unreachable, but soft-deleted and unread; writing
  "confirmed" onto it asserts something no human checked, for no benefit.
- **`released` included despite a zero count.** The criterion is the PROPERTY
  ("locked against every write path"), not today's row count. Right by
  construction rather than by coincidence.

### What this is explicitly NOT

**Not a decision that approval counts as citation confirmation.** Whether
`approve_assessment` should stamp its rows' citations from here on is a real,
separate design question and gets its own D-number if the answer is yes. This is
a one-time backfill of rows that predate the rule. Kept apart deliberately, so
"we grandfathered old data" never quietly becomes "sign-off is evidence".

### The casing trap, and why the log line is the only reason it was caught

The first version of 0045 matched `status IN ('approved', 'released')`,
grandfathered **zero** of the 8,862 rows, and reported success.
`AttackAssessment.status` is a `SAEnum(..., native_enum=False)`, and
SQLAlchemy's `Enum` persists the member's **NAME** — the column holds
`'APPROVED'`, while `AttackAssessmentStatus.APPROVED.value` is `'approved'`.

Two deliberate choices caught it, and no test did:

1. **The migration prints its row count.** "Touched nothing" and "correctly had
   nothing to do" are indistinguishable afterwards; the number is the only
   evidence of which happened.
2. **It was applied to the dev database instead of being trusted from green
   tests.** CLAUDE.md already records that a new migration does not reach dev
   Postgres on its own; the corollary is that running it there is a test no unit
   suite performs.

**The test could not have caught it, and that is the reusable lesson.** Its
fixture inserted `'approved'` by hand, so it agreed with the migration by
construction — CLAUDE.md's standing rule about a test that supplies its own
precondition from the thing under test, now instance ten. The fixture seeds
through the ORM, so the stored representation comes from the same code path
production uses, and a test pins the literal `'APPROVED'` against a raw read.

The migration matches `upper(status)` rather than either casing: the stored
representation belongs to SQLAlchemy, and a migration is pinned to history while
the model is free to change, so importing the enum here would couple this file
to a model that may not exist in this shape later.

## D-057 — Run the reviewer on every PR, which reverses part of D-054

**Date:** 2026-08-22 · **Reverses:** part of [[D-054]] · **Issues:** #108 · **Follows:** D-051

D-054 recorded, and rejected, "document the gate in `CLAUDE.md`":

> **The first proposed fix was to document the gate in `CLAUDE.md`. Rejected by
> Gene, correctly.** That is a discipline fix, and discipline against this exact
> shape has failed nine recorded times (#72). Visibility was never the binding
> constraint.

**That reasoning stands, and this is a different proposition.** D-054 rejected
documenting a _mechanism that already existed_ — the gate was built, so writing
about it added nothing a red X did not. What is being added now is the
requirement to run the reviewer at all, which no mechanism enforces and W8b (the
reviewer as a CI job) is still deferred.

**Recorded because the alternative was a rule in the auto-loaded file that
silently contradicted the append-only log.** That divergence has bitten three
times, most recently D-051's own correction, which exists because "the
append-only log carried the correction while the document people act from carried
the falsehood". Leaving this as a CLAUDE.md bullet alone would have been the same
shape a fourth time, pointing the other way.

### What the drift cost, measured rather than argued

Three PRs (#112, #113, #119) and the item-9 cross-service sweep were self-audited.
The §14 gate passed all of them, because — as D-054 states outright — it proves
an audit was RECORDED, not that it happened.

Pointed at that sweep, the reviewer overturned **four of its six** clean verdicts.
One had reported "no twin" over a defect written up as F6 in
`docs/plans/2026-08-08-cross-service-integrity.md` two weeks earlier and still
live. The MVP total moved from 5–6.5 sessions to 8–10.5 as a direct result.

The diagnosis is why more care would not have helped: the sweep generalised
ATT&CK's _vocabulary_ (`pending_review`, "withheld") instead of its _shape_ — an
aggregate applying an exclusion the per-row rendering does not. Grepping the word
found nothing; the shape was in three services. A self-audit cannot reach that,
because the blind spot and the reviewer are the same mind.

### The honest caveat, stated in the rule itself

**This is unenforceable and unobservable.** Nothing records whether the reviewer
ran or when, and the gate cannot see who wrote the findings. It is weaker than
the gate it supplements, because the gate at least produces a red X. It is
therefore exactly the "discipline against a known shape" D-051 says has failed
nine times here — written down anyway, because the alternative is nothing and
because this time the cost of not doing it was counted.

W8b remains the mechanism that would bind it, and remains deferred.

### Also settled here

- **Docs-only PRs are exempt from the GATE and not from the RULE.** The gate's
  "one defensible skip" is about a merge check; a wrong claim in `CLAUDE.md`,
  `DELIVERY_PLAN.md` or `DECISIONS.md` is where this project's defects actually
  live. The review that produced this decision found eleven in two markdown
  files.
- **Re-audit after substantive changes, not once at open.** PR #29's plan records
  two consecutive patches that each looked done and each were wrong, both caught
  only by re-auditing while CI stayed green.
- The rule closes the `CLAUDE.md` half of **#108**. The other half — the gate's
  own source still saying it "only REPORTS" and citing D-051 instead of D-054 —
  is untouched and still open.

## D-058 — The address rule is decided by a truth table, and its residuals are named

**Date:** 2026-08-24 · **Context:** #130 · **Supersedes:** nothing

`redact_for_ai` is the single LLM egress path, so `_redact_addresses` is the one
rule whose errors reach every AI input in all five services. Before this, its
suite-designator pattern had no trailing boundary after the keyword alternation
and a separator class that could match empty, so the keyword ate the rest of any
word it prefixed. Verified in-container against `main`, over the corpus committed as
`PRODUCT_NAMES` in the truth table so the ratio is reproducible from the repo
rather than from a scratch list: **17 of 23 real security product names
corrupted** — `Stellar Cyber` → `[ADDRESS] Cyber`, `Flowmon`,
`Fleet`, `Flashpoint`, `Fluency`, `Steadfast`, `Steampipe`, `Aptible`, `Unity`,
`Unitrends`, `Suitecrm` → a bare `[ADDRESS]` — plus prose (`Flat network
segmentation`, `flaws in the flow control`), because security vocabulary is
unusually dense in "fl".

It also re-opened **#33 finding 5** through a different door: three products that
all egress as `[ADDRESS]` collide in `_by_alias_norm`, so the only string an
obedient model can cite resolves `ambiguous`, and under **#102** the technique
leaves the ATT&CK coverage **denominator**.

### The decision is the method, not the regex

The pattern was rewritten three times in one sitting and each draft was correct
for the corpus that prompted it and wrong for the next: the first lost `Ste-400`,
the second lost `Suite Twelve`, the third lost every zero-separator form. That is
CLAUDE.md's stated tell for a design problem rather than a bug list, so the rule
is now decided by an enumerated truth table
(`apps/api/tests/unit/test_redact_address_matrix.py`) over six axes — suffix
shape, separator shape, value position, trigger-inside-a-product-name,
surrounding context, and text that has already been through the pipeline once —
derived from what the redactor SHOULD do. Any future change to this rule changes
the table first.

**On "written BEFORE the pattern", which this entry said without qualification.**
The original five axes were. The sixth was not, and neither were the rows added
for the street rule or the rows the adversarial review of this fix forced. The
method held for the part that was hardest to get right and was applied
retroactively to the rest, and that is the honest version — a decision record
claiming more discipline than the work had is the same defect as a status line
claiming more progress.

The issue's own suggested minimal fix (`\b` plus a required separator) was
measured and **rejected**: it fixes less _and_ leaks more, dropping `Ste-400`
while leaving `Apt Cache Proxy` and `Adobe Creative Suite Enterprise` corrupt.

### Accepted residuals — deliberately wrong, and named so no one has to rediscover them

Every one is pinned by a test that fails if it silently changes.

**Over-redacted (a designator keyword followed by a number):** `Burp Suite
2024.1`, `Burp Suite v2`, `Adobe Creative Suite 6`, `apt 1.2.3`, `APT 28`,
`Unit 42`, `Unit 8200`, and `Suite B Cryptography`. A version number and a suite
number are the same shape; **no suffix-shape rule can separate them.** Only
surrounding-context logic could, and that is a different design, deliberately not
built here — it would gate the rule on a `street_pat` hit, and `street_pat` is
itself unreliable (see below).

**Leaked (accepted):** letter-only designators (`Suite AB`, `Ste BB`) and a letter
designator space-separated from its number (`Suite B 201`); a colon or comma
separator (`Suite: 400`, pre-existing); an intervening word (`Suite No. 4`,
`Unit Number 12`) -- the separator class holds no letters, which is the same
shape that makes the CAGE rule miss its own primary phrasing; an underscore in
the suffix (`Suite 400_B`, from the same exported-spreadsheet source class as the
zero-separator forms); an all-full-width numeral run; a designator wrapped onto
the next line; a bare number before `Floor` (`3 Floor`, no ordinal); and non-US
designators (`Flat 3`, `Level 2`), which were never covered -- `Flat` matched
before only via the `\bFl` bug being fixed.

**On full-width numerals, stated correctly rather than plausibly:** Python's
`\d` on a `str` pattern IS Unicode-aware, so it matches U+FF10-FF19. It is the
ASCII-only TAIL that fails, and then the trailing `\b` falls between two word
characters. So `Suite 4` in full-width redacts, and only a run of two or more
full-width digits leaks. An earlier draft of this record said "`[A-Za-z0-9]` is
ASCII-only", which named the right character class for the wrong reason.

**Two shapes were FIXED rather than accepted, because their failure mode is worse
than a leak: a partial match that READS as a completed redaction.** `Suite B-201`
produced `[ADDRESS]-201`, keeping the unit number under an output that looks
finished, and `Suite B 201` produced `[ADDRESS] 201`. Both now either redact
whole or decline whole. A leak the truth table records beats half a string
vanishing silently, and that asymmetry is why the rule exists at all.

Letter-only designators are accepted on this reasoning: once `street_pat` has
fired, a letter-only designator carries no identifying content
(`1234 Main Street, Suite AB` → `[ADDRESS], Suite AB`). The rejected alternative
was an uppercase-scoped branch `(?-i:[A-Z]{1,3})`, which corrupts `Adobe Creative
Suite CC` and `Sophos Security Suite XG` — #130 reintroduced on another branch,
i.e. a fix that breaks an earlier fix. **Stated caveat:** `street_pat` does NOT
reliably catch the identifying half — spelled-out and alphanumeric house numbers
pass it (`One Federal Plaza`, `221B Baker Street`), filed as #138 — so this
justification is weaker than it first reads and is recorded that way on purpose.

### What was ADDED, not preserved

A value may precede its keyword (`2nd Floor`, `3rd Fl`). The pattern never
modelled this. Before the fix `2nd Floor` produced `2nd [ADDRESS]` — the `\bFl`
bug firing and leaving the number behind — and `3rd Fl` matched nothing at all.
So the new branch adds coverage that never existed and closes a live leak; it
does not preserve coverage through a fix, and the commit says so.

The shape has exactly one member: only `Floor`/`Fl` take a number in front.
`Building`, `Bldg`, `Rm`, `Room`, `Level` and `Mail Stop` match nothing at all,
before or after — a coverage gap rather than a wrong shape, filed as #139.

### The guarantee has to hold for every sub-pattern, and at first it held for two

`_RE_ADDRESS` compiles three sub-patterns: `_STREET_PAT`, `_SUITE_PAT` and
`_PRE_KEYWORD_PAT`. The newline exclusion — the reason `_SUITE_SEP` stops at a
line break rather than using `\s` — was applied to the second and third and **not** the
first, while the truth table carried a comment asserting it held for all three.
Two of three, and the row that would have caught it did not exist.

`_STREET_PAT` fails worse than the suite rule does, because its leading
`\d{1,6}` reaches BACKWARD across the break and takes a number off the previous
line:

    "Servers reviewed: 5"  +  "Main Street office is unstaffed."
      -> "Servers reviewed: [ADDRESS] office is unstaffed."

The count is gone, the two lines are merged, and the result reads as an ordinary
sentence. That is #130's own failure mode — plausible output, nothing raised,
nothing counted — inside the fix for #130.

**Decided:** `_STREET_SEP` is horizontal whitespace, matching `_SUITE_SEP`.

**Cost, named rather than discovered — and this paragraph was WRONG when first
written; see "The separator is a SUBTRACTION" below, which supersedes it. The
list below is the whole cost only under the subtraction, not under the
enumerated class this paragraph originally described.** An address wrapped
across a line break now leaks (`1600 Pennsylvania` / `Avenue NW`). Unlike `Flat`, whose coverage
existed only through the `\bFl` bug, this coverage was real — but it was never
clean: the trailing directional falls outside the alternation, so the wrapped
form redacted to `[ADDRESS] NW` on main and the single-line form still does. A
partial match that reads as a completed redaction is the shape this decision
elsewhere refuses to accept, so trading it for a recorded leak is consistent
rather than convenient. Pinned as an accepted residual; the directional gap and
the house-number gaps are #138.

### The separator is a SUBTRACTION, because the enumerated version leaked

This reverses a decision made earlier in this same entry, one round later, and
the reversal is the part worth keeping.

Narrowing the separator away from `\s` was written as `[ \t\xa0]` — space, tab,
non-breaking space — and the cost was recorded as _"an address wrapped across a
line break now leaks"_, full stop. That was **false**. `\s` matches 19 horizontal
characters, so the enumerated class silently dropped **sixteen** of them:
U+2000-U+200A, U+202F narrow no-break, U+205F medium mathematical, U+3000
ideographic, U+1680 ogham, and U+001F.

Those are not exotic. Thin and narrow-no-break spaces are what PDF and Word text
extraction emit, which is precisely how a client's letterhead reaches this
boundary. A street address separated by U+202F redacted on `main` and egressed
**verbatim** under the enumerated class, with no `address` key in
`removed_counts` — a leak at the security boundary whose audit row is
byte-identical to a note that contained no address. Strictly worse than the
over-match it was fixing, in the one direction that matters.

**How it got in.** The decision was framed as being about NEWLINES, so the
replacement was written to solve newlines and nobody re-derived what else was in
the class being replaced. Every cell anyone thought to write passed, because the
cells were written by the same person with the same mental model of "whitespace"
— CLAUDE.md's corpus lesson, one level down, inside the fix that added it.

**Decided:** `_HSPACE = r"[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]"` — that is
`\s` minus exactly the ten characters `str.splitlines()` calls a line break.
Every separator in the ADDRESS rule is built from it, so "does not cross a line"
is one
definition rather than a property each pattern re-asserts. `PO\s+Box` inside
the keyword alternation was still using `\s` and now uses it too. `_RE_PHONE`
and `_RE_CAGE` still do NOT -- filed as #140 and #137, not fixed here, and said
out loud because an unstated exemption reads as an oversight.

`[^\S\r\n]`, the obvious idiom and what the review of this fix proposed, is
**also** wrong: it still crosses `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, U+2028 and
U+2029, every one of which IS a line break. Measured rather than argued — both
halves are now pinned as parametrised sweeps over the two sets, with the
parameters derived from `str.splitlines()` rather than from the pattern.

**The general rule, and why this is a decision rather than a bug fix:** replacing
a character class with an enumerated one is a subtraction you must COMPUTE, not
guess. Write it as the subtraction and let the language define the set.

### Claims from READING fail at about even odds; claims from RUNNING have held

Recorded here rather than in a review comment because it is the strongest
argument in this repo for mechanism over discipline, and it now has **three
independent sources** in a single week whose entire subject was that error.

Everyone working on this branch made the same class of mistake -- asserting a
number or a rule from reading, without executing anything:

- **The adversarial reviewer** proposed `[^' + chr(92) + 'S' + chr(92) + 'r' + chr(92) + 'n]` as the whitespace fix (it still
  crosses eight line-break characters), and asserted "No accidental issue closes"
  was not a required check (the live API says it is). It runs read-only by
  construction, so every one of its claims is static reading -- which is also why
  it catches what it catches.
- **The implementing agent** shipped "153 cells" when the count was 327, claimed
  a separator-class gate had 1:1 signal when it measured 1 in 13, and asserted a
  plan total without adding the rows.
- **The reviewing human** made the same error six times: a rule quoted from
  memory that the file contradicts, a stale audit finding, an unsummed total, a
  count taken from a docstring, a percentage that had gone stale, and the 1:1
  ratio above.

The pattern is not carelessness and it is not fixable by care -- all three
participants knew the rule, and two of them had written it down that week. Every
claim any of us made **after executing something** has held. Every claim from
reading has failed at roughly even odds.

**So: nothing reportable until it has been run.** Where a claim cannot be
executed -- a judgement about scope, a prediction about a future reader -- say
that it is a judgement rather than dressing it as a measurement.

This is D-051's argument with a bigger sample. It is also why this branch ships
four gates rather than four paragraphs: `check_no_control_chars`,
`check_plan_totals`, `check_separator_classes`, and the truth tables themselves.

### The fourth class the corpus was missing

CLAUDE.md gained the four classes a hand-written corpus structurally cannot
contain **on this branch**, and the table shipped covering three of them. The
missing one was text that has already been through the pipeline once — which is
not hypothetical here, because the Tech Debt extractor redacts its own inventory
input, so `[CLIENT] SOC Platform` is the normal product of any extraction after
intake and is fed back through the egress path on the next call.

Added as an idempotence axis asserting a fixed point (`_clean(_clean(x)) ==
_clean(x)`) rather than literal expected strings, so it cannot decay into the #72
shape of encoding the implementation's own answer. It is green today. It is worth
having anyway: nothing else in the suite would notice if a future widening made a
placeholder re-match, and the ATT&CK resolver's alias tier depends on the
transformation being stable under a second pass.

## D-059 — The unattended-merge rule stands, and its framing sentence states what it measured

**Date:** 2026-08-26 · **Context:** the merge rule in `CLAUDE.md` · **Supersedes:** the framing half of the 2026-08-26 rule as first written

Condition 5 grew to its current path list over two sessions. Every addition was
individually justified and all of them are kept. The net effect was not stated
anywhere: because the list now includes `apps/api/tests/**` and `e2e/**`, and
because this repo does not ship code without tests, no PR containing code can
clear the rule. A reader deriving the scope from the conditions could reasonably
land somewhere more generous than the conditions actually permit, and the
framing sentence did nothing to stop them.

**Measured rather than argued.** Condition 5's current path list applied to the
last fifteen PR merges on `main`: **four cleared, eleven came back**, the eleven
tripping 1 to 20 paths each. The four are all documentation
(`1bc5733`, `16267b0`, `634f6ea`, `65e0f31`).

Two independent constructions were built from opposite directions — a denylist
(condition 5) and an allowlist proposal — and converged on "documentation".
They disagree on exactly two PRs, `8aaaace` (`test(zt)`) and `0a26f8c`
(`test(e2e)`): the allowlist permitted `apps/api/tests/**`, condition 5 forbids
it, so six became four. **Neither figure was stale; they were two different
rules**, and the denylist is the stricter one. Convergence from opposite
directions is evidence about the codebase rather than about either construction:
on this codebase a green suite genuinely does not license an unattended merge of
code.

**One objection, killed by the same data.** The worry that this becomes a
machine for auto-merging a developer's own state file does not survive: exactly
one of the four cleared PRs touches `context/`.

**The alternative weighed and rejected: drop the rule.** Four reviewer passes
and a long section of `CLAUDE.md` is a real cost against four cleared PRs in
fifteen. It loses anyway, because those passes were not spent discovering the
rule was wrong — they were spent discovering that a green suite does not license
an unattended code merge here. That finding is worth having written down whether
or not a standing rule survives it, and the four cleared PRs are the kind that
recur every round.

**What does not survive is a framing sentence promising more than four in
fifteen.** It now says what the rule clears, with the measurement, its window
and its date.

**Trigger, because this number has a specific way of going wrong.** The
measurement is a claim about a fixed slice of history, so it does not rot the
way a live count does — but it is only true of condition 5 as that list stood on
2026-08-26. **Re-derive it whenever condition 5 changes.** Condition 5 changed
twice in the three days before this entry, so that is a scheduled event and not
a remote contingency.
