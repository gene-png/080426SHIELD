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
   cleanup — out of scope here.)
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
