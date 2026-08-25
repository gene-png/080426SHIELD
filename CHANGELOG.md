# Changelog

All notable changes to SHIELD by Kentro v2.0. Format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the phase template in AI Prompt §9.

> **Version renumber (Sprint 3 docs truth pass):** two releases were both
> headed `[3.0.0]`. The v2 work order (PR #1) keeps `[3.0.0]`; Sprint 1
> (smoke sweep) is now `[3.0.1]` and Sprint 2 (findings burn-down, formerly
> `[3.0.1]`) is now `[3.0.2]`. No tags existed for the collided numbers.

## [3.11.0] · Validation remediation — every Critical closed, sessions survive the work · 2026-08-08

Closes the 2026-08-07 end-to-end validation run (`REPORT.md`, N-001..N-033) and
the defects found while verifying its fixes. **All seven Critical findings are
fixed and on `main`, CI green.** No breaking changes; one additive migration
(`0040`).

> **This is not a bug-free build.** Known-accepted risks are tracked in
> **issue #25** and `context/gene.md` — most importantly, **AI spend is
> under-reported by >60% and must not be billed from**. Zero Trust, NIST CSF and
> the Risk Register have still never been driven end to end, and `csf_score` /
> `zt_score` have never completed a live run.

### The Criticals (PRs #22, #23)

- **Intake step 5 crashed the application** (N-003). `onToggle` read
  `e.currentTarget.open` inside a state updater, after React had nulled it. It
  fired on arrival, not on click, so **no client could submit an intake**. Of 41
  smoke specs none walked the wizard that far, which is why CI stayed green.
- **ATT&CK could never complete its core AI step** (N-014). `mitre_map` emits one
  object per technique across ~633 techniques — far past any single call's output
  ceiling. Now runs as concurrent batches (25 techniques × 5 workers), each
  writing its own `llm_calls` row. **Validated live: 26/26 batches, 633/633
  techniques scored.**
- **A fixture run masqueraded as live and destroyed a client's answers** (N-029).
  Readiness asked only "is a key loaded?", so the shipped shape of `.env`
  reported `ready:true` in fixture mode and silently disabled both the banner and
  the Run-AI guard. Draft answers now carry provenance and are protected.
- **A released report understated spend by $240,000** (N-010). The exclusion
  disclosure unmounted after a bundle split — the fix for one finding defeated
  the fix for another — and the deliverable never carried the reconciliation at
  all. All three formats now state it, and relabel the figure when rows were
  dropped.
- **The Risk Register could never generate live** (N-032). One entry per finding
  × 509 findings ≈ 250k output tokens against a 128k ceiling; no budget could
  have worked. Now batched like `mitre_map`.
- **ATT&CK fabricated a 100%-gap assessment with no capability list** (N-033). An
  empty allow-list means every technique reads as uncovered, so a run produced
  607 gaps that were an artifact of missing input — releasable to a client, and
  billable on every attempt. Now refused before the provider is called.
- **`/admin/deliverables` showed a raw upstream 400** (N-030) when no client was
  selected, and had been holding CI red on `main`.

### Sessions survive the work (PR #24)

- **Concurrent requests were logging users out mid-task.** Refresh tokens are
  single-use; a browser presents the same one from several requests at once, so
  the first rotated it and the rest were rejected as replay — observed as pairs
  of `auth.refresh_reused` **286 microseconds apart**. An active user was logged
  out _because_ they were active.
- Rotation now honours the immediately-previous token for
  `jwt_refresh_grace_seconds` (default 60) and serves the current identity, so
  racers converge. One generation, time-boxed; set to `0` for strict single-use.
- **Access TTL 15 min → 60 min; refresh TTL 30 min → 24 h.** The second is forced
  by the first: a refresh token must outlive the token it renews.
- **Session-expiry warnings at five minutes and one minute**, on every signed-in
  page. Dismissing the five-minute notice does not suppress the one-minute one.

### The admin workspaces read as a sequence (PRs #24, #26)

- **Four numbered steps** — draft with AI → review and adjust → approve →
  generate and release — on ATT&CK, Tech Debt, NIST CSF and Zero Trust. Sections
  had sat in the order the features were built, so on three of the four the
  actual assessment work was at the _bottom_ of the page, below the deliverable
  and the message thread.
- Blocked steps state **why** and name the step to return to. Approving an
  entirely unscored ATT&CK assessment is no longer possible.
- Risk Register deliberately unchanged — two adjacent actions, no editing
  surface.
- **Intake queue navigable at 70 organizations**: A–Z ordering, a jump-to
  dropdown, and duplicate legal names disambiguated.

### Rendering

- **Metric-card values size to fit** (`3xl → lg` by length). A real seven-figure
  annual cost ran outside its card — the number a consultant opens the page to
  read was the one they could not read. Fixed in the design system, so every
  dashboard benefits.
- **`s42-layout-overflow`** sweeps 9 pages × 2 viewport widths for content
  escaping its container. Mobile widths are not yet covered.

### Testing

824 backend unit tests, 138 web unit tests, 84 e2e specs — all green. New
coverage for the refresh race, the empty-capability guard, the security-scope
boundary (a row marked "not cyber" leaves ATT&CK but stays in Tech Debt costs),
the intake-queue dropdown, session warnings, and layout overflow.

**Still untested by construction:** live-path tests (`pytest -m live`) self-skip
without a key, so budget, latency and provider defects remain invisible to CI.
Three of five AI purposes have now been bitten by exactly that class.

## [3.10.0] · UX findings burn-down complete — Results, task-status Home, Deliverables, Help · 2026-08-07

Closes both outstanding review documents: `UX findings.docx` (22 numbered
findings plus its "Recommended page structure" appendix) and the 2026-08-04
guided live run (`REPORT.md`, F-1..F-12). New decisions **D-042**, **D-043**,
**D-044**. **No migrations** — the one new read surface derives its states from
columns that already existed.

### One place to look for results (PR #14, UX 18 — D-042)

- **`/results` replaces `/documents`.** Reports were downloaded from
  `/documents` while dashboards were reached from `/home` or a "View dashboard"
  link, so a client had three places to look for the outcome of one engagement
  and no way to know which held what.
- **`/documents` permanently redirects, and stays.** Release notification emails
  already sitting in inboxes carry the old path; a 404 on a link we sent is worse
  than keeping a route forever. `s17` asserts that promise. The release email now
  points at `/results` directly rather than through the redirect.
- Six link labels still read "Back to documents" while landing on `/results` for
  a whole release, because every spec checked the href and none checked the
  words. Fixed in PR #17; the missing assertion is recorded in SMOKE §42.

### Client Home organised by who owns the next move (PR #15, UX 17 — D-043)

- **Three buckets, one per service:** Action required / In progress / Results
  available. "Your services" was a flat grid in arrival order, so a client with
  several engagements read every phase pill to find the one that needed them.
- **The duplication is gone by construction.** An open self-assessment used to
  render twice — as a card and again in a "Waiting on you" list beside it. A
  service now lands in exactly one bucket, and "Waiting on you" is retired;
  unread messages, which need the client but have no service card, moved into
  Action required. One `needsClient()` predicate feeds both the bucket and the
  hero's Continue button, so they cannot disagree.
- **Each card names one primary action** — Resume assessment / View status /
  View results — as a span inside the card's existing link, never a nested
  anchor. A test asserts exactly one link per card.
- **No six-stage bar here.** §6.4 restricts a client surface to phase and next
  steps; the six stages stay consultant vocabulary. The phase pill is unchanged,
  so `s31`'s routing assertions needed no edit to stay green.

### Admin Deliverables (PR #16, IA appendix — D-044)

- **One place per tenant showing every deliverable, released or not.** They were
  visible only inside the workspace that produced them — the admin-side twin of
  the problem `/results` fixed for clients.
- Status derives from existing columns: superseded / released / generated. **No
  migration.** Superseded beats released, because a superseded row was often
  released once and calling it client-visible would say the client is looking at
  a version that has been replaced.
- **Read-only.** No release action on a cross-service list; that is how the wrong
  version reaches the wrong tenant. `s40` asserts the absence.

### Admin console and Help (PRs #17, #18, IA appendix)

- **Intake queue filters** by organization name, service, status and age, all
  client-side over data already fetched. A filtered-to-nothing list **names the
  filters that emptied it** — a bare "no results" on a queue reads as "no work
  exists". "Select all" is scoped to visible rows, so bulk publish can never
  reach a request filtered off screen.
- **The Risk Register states its scope** — client-specific, synthesized across
  that client's services. It already said so, but only in the "pick a client
  first" empty state, which anyone with a client selected never sees.
- **`/help`** explains every service and carries the support routes. The copy
  moved out of `Step1Services.tsx` into `lib/intake/types.ts` so the intake
  picker and the help page cannot describe a service differently.

### Test integrity (PR #19)

- **`s34`'s Run-AI-guard test can no longer self-skip.** It resolved the seeded
  ATT&CK service and bailed out if that assessment was released — so whether the
  browser exercised the guard depended on database state nobody controls, and
  that skip is what hid the fail-open race it now guards. It seeds its own
  tenant and draft assessment, and the skip became an assertion. Verified by
  forcing the old condition: it now fails loudly where it used to report green.
- Two e2e specs were added on colliding `s37`/`s38` numbers and renamed to
  `s40`/`s41`. Playwright resolves by path, so nothing failed — the collision
  surfaced only when the docs cited the numbers.

## [3.9.0] · Portfolio scope, derived stages, UX remediation · 2026-08-06

The 2026-08-04 guided end-to-end review and the UX findings document, worked
through in order of severity. New decisions **D-039**, **D-040**, **D-041**;
migrations **0038** and **0039**, both additive and SQLite-safe (C0).

### Audit integrity and the analysis lifecycle (PR #6)

- **`llm_calls.mode` reflects the provider that actually ran.** It was derived
  from `settings.shield_llm_mode` while `_build_provider` forces a live adapter
  whenever a runtime key exists — so on the exact configuration D-037 was built
  for, calls egressed to Anthropic and were logged as `FIXTURE`. For a platform
  whose egress evidence _is_ `llm_calls`, that is the audit trail lying.
- **A failed AI call leaves a FAILED audit row.** `invoke()` set the status and
  flushed, but `get_db` never commits, so the 500 discarded the row with the
  request transaction — a failure left no record at all. The failure is now
  written through an independent short-lived session that commits on its own.
- **Fixture output can no longer overwrite a submitted self-assessment.** The
  offline Run-AI guard reached one of five entry points; an unguarded fixture run
  on Zero Trust silently overwrote a real client self-assessment (average
  maturity 2.14 → 1.49). The guard is on every entry point, and it holds a click
  made _before_ the AI-status request resolves rather than failing open.
- **Anthropic streaming** for the long jobs that died with
  `APIConnectionError: Server disconnected` on a non-streaming request, keeping
  the `stop_reason` guard.

### Client-visible data integrity (PR #6)

- **Extraction reconciliation.** 21 uploaded rows / $1,634,236 became 12 items /
  $891,796 with no disclosure — the survivors presented as the whole inventory.
  The workspace now states rows received, included and excluded, with a queue to
  recover a wrongly-dropped row or confirm an exclusion (which leaves it listed:
  the reconciliation has to keep telling the truth about the upload).
- **Bundle decomposition.** Microsoft 365 E5 extracted as a single $294,120 line,
  so three of five planted redundancies were undetectable. A consultant names the
  components; the model is never asked what is inside a bundle, which would be
  exactly the fabricated detail the AI seam exists to prevent. Components carry no
  cost of their own, so decomposing can never inflate the portfolio total.
- **Review & submit completeness**, intake confirmation content, date-only
  rendering (`2027-06-30` rendered as `6/29/2027`), dashboard `<main>` landmarks,
  self-assessment type resolution from the service record, and autosave
  consistency.

### Tech Debt covers the whole portfolio (PR #9 — D-039, migration 0038)

- Prompt **v2** keeps every inventory row and classifies it — `security_related`
  plus `security_functions` from prevent / detect / respond — instead of dropping
  the non-security ones silently.
- **A negative security classification is provisional until a consultant agrees.**
  `valid_tools` in the ATT&CK mapping is a hard allow-list on the tools the model
  may cite, so a capability wrongly marked non-security becomes _uncitable_ and
  the technique it covered reads as uncovered rather than unassessed. Unclassified
  rows and unconfirmed negatives both stay in scope; only explicit sign-off
  removes one.
- `_client_tool_names` gained a status filter. It had none, so a **discarded**
  capability list's rows stayed citable forever.
- `_serialize_list_with_items` builds from the model. Hand-written, it had
  silently dropped a newly-added column twice, each reading as null in the UI
  with nothing failing.

### One derived six-stage vocabulary (PR #9 — D-040)

- `prepare → analyze → review → approve → generate → release` across all four
  services, derived read-only from status plus evidence. **No state machine,
  route or audit vocabulary changed.**
- `analyze` and `generate` are not stored states, and the naive query is a trap:
  `llm_calls` has no version link, so "has this service ever been analysed?"
  lights up a brand-new draft. Evidence is anchored to the version — by
  `created_at` for Zero Trust / CSF / ATT&CK, and by the list's own extraction
  provenance for Tech Debt, which builds its version _after_ the run that
  produced it.
- Progress is monotonic, so the bar never renders a cursor behind completed work.
  "Submitted" is not a stage: it exists only for Zero Trust and CSF, so the
  asymmetry lives in what `prepare` is called rather than in a stage that can
  never light.

### CI and test isolation (PRs #7, #10)

- **`pnpm-lock.yaml` was out of sync** with `apps/web/package.json` (missing
  `chart.js` / `react-chartjs-2`), failing CI on every branch, not just one.
- **The gitleaks job had never passed.** The workflow default is `contents: read`
  and gitleaks writes findings back to the PR, so it 403'd on every run including
  PRs with no secrets. A check that is red regardless of the diff teaches everyone
  to ignore the one signal that matters the day it is real.
- **`s11-staleness` stopped sharing the seeded ATT&CK service with `s5`** — it
  raced for it _and_ approved/finalised it, changing state every later spec
  inherited.
- **The fixture extractor behaves like the prompt it stands in for**: it
  classifies rows, and skips ones it cannot name. Both the security sign-off queue
  and the excluded-rows queue were previously unreachable offline, and an
  unreachable review surface is an untested one.

### Tests

New: `s37-security-signoff`, `s38-progress-stages`, `s39-excluded-rows`, plus
backend suites for the security scope rules, the stage derivation (including the
version-trap cases) and classification through the API. Each new rule was
verified by breaking the implementation and watching the intended test fail.

Minor bump: new user-facing surfaces and endpoints, all additive; no breaking
API changes.

## [3.8.0] · Seven-issue pass — navigation, removal, runtime AI keys, release control · 2026-08-04

Seven reported issues, fixed in four phases on `fix/seven-issue-pass`. Three of
them turned out to be the same class of defect: a surface that renders but cannot
be acted on. New decisions **D-036**, **D-037**, **D-038**; migrations **0033**
and **0034**, both additive and SQLite-safe (C0).

### Navigation dead ends (issues 1, 5, 6)

- **`/home` service cards are links.** A client could see a service on their home
  dashboard and had no way to open it — the card rendered as a bare `Card`. Every
  card now routes by its own phase: report-ready → the service dashboard (or
  `/documents` for a kind that has none), in-progress → the self-assessment,
  everything else → `/assessments`. `dashboardPathFor()` in
  `lib/dashboards/routes.ts` is the single source of truth, and `/documents` was
  re-pointed at it rather than keeping a second copy of the same switch.
- **`/admin/active` was a stub** whose whole body was a paragraph and a "Go to the
  intake queue" button. The nav entry points at the queue directly; the route
  survives as a redirect so existing bookmarks still land somewhere useful.
- **The skip-to-content link now shows a visible focus ring.** The link itself was
  never broken (every shell renders `<main id="main-content" tabIndex={-1}>` and
  `s12` already asserted the focus move), but all 8 shells carried
  `outline-hidden`, which sets `outline-style: none` and cancels the ring even
  though `focus:outline-2` applies its width — so on a short page, activation
  produced no visible change and read as dead. The class is removed rather than
  layered over, and `s12` now pins a non-zero rendered outline width.

### Client and user removal, intake by organization (issues 3, 7 — D-036)

- **`DELETE /admin/clients/{cid}`** archives a tenant (new nullable
  `client.archived_at`, migration 0033) — a soft removal following the
  `archive_service` precedent. Assessments, deliverables and the audit trail are
  retained; the tenant leaves the client list and the org index.
- **`GET /admin/clients/{cid}/users`** and **`PATCH /admin/users/{uid}`** list and
  deactivate/reactivate users. Self-deactivation is refused with a typed D-016
  error, and deactivating clears `active_refresh_jti` so an existing session dies
  immediately instead of riding a valid refresh token to expiry.
- **Fixed while testing the above: `/auth/login` never checked `User.is_active`.**
  Refresh, MFA-verify and password-reset all honoured the flag, so a deactivated
  user could still sign in with their password. The gate sits after the password
  verify (before it, the endpoint would be an account-existence oracle) and the
  typed reason reaches the sign-in form as "this account has been deactivated".
- **`/admin/queue` is now an index of organizations.** It previously opened onto a
  single org — the API returns every tenant's requests but sets `client` to the
  most recently created tenant (advisory, per its own docstring) and the UI
  rendered that as the page header. `/admin/queue/[clientId]` shows one org's
  intake detail above its own pending work; awaiting-review counts come from a
  single grouped query.

### Runtime AI key management (issue 2 — D-037)

- **`POST` / `DELETE /admin/llm-key`** let an admin paste, replace and remove a
  provider key from Management. The key is **validated against the provider before
  it is stored**, so a typo is refused with the provider's own reason instead of
  silently taking AI offline. It is stored Fernet-encrypted (migration 0034, new
  table), never returned by any endpoint, never logged, never in an audit blob —
  each asserted by tests.
- **A stored key overrides `SHIELD_LLM_MODE=fixture`** and takes effect on the
  next Run AI with no restart (every workspace's `_llm_dep` builds from the DB).
  Pasting a key is an explicit request for live AI; serving fixtures afterwards
  would be exactly the silent success this removes.
- **The offline warning is now unavoidable.** `AiStatusBanner` moved into the admin
  shell (it previously rendered on one of five workspaces) and links to the fix;
  `RunAiGuard` makes the first offline Run AI click explain that output will be
  canned, offering "Load a key" or "Continue offline". The acknowledgement is keyed
  on the current config, so removing a key re-warns in the same session.
- Also corrected: `.env` pinned `SHIELD_LLM_MODEL=claude-opus-4-7`, a value the
  code itself lists as a known placeholder — live AI would have refused to boot
  even with a valid key.
- **The guard no longer fails open while its own status request is in flight.**
  The first cut branched on `status === null`, which means both "not asked yet"
  and "endpoint down"; under load a Run AI click beat the fetch and silently
  wrote 1646 fields of canned output with no warning at all. `useAiStatus` now
  reports a `phase` (`loading` / `loaded` / `error`), a click during `loading` is
  held until the answer arrives, and only a genuine outage still fails open. Two
  unit tests pin it; `s34` clicks eagerly on purpose to keep the race covered.
- `/admin/health`'s overall badge gained `aria-label="Overall readiness"`. Moving
  `AiStatusBanner` into the admin shell put a second `role="status"` on that
  page, which made "the page's status element" ambiguous for assistive tech and
  broke `s25`'s locator.

### Release control + admin pre-release preview (issue 4 — D-038)

- **Deliverables can actually be released.** Finalize produced a PDF and an XLSX
  and nothing else, so the client dashboards' release gate (D-035) could never be
  satisfied and **no client could ever see a dashboard**. Three defects were
  stacked in that path: the `release*Deliverable()` client functions had zero
  callers; the `/api/proxy/{svc}/deliverables/{id}/release` routes they POST to
  did not exist; and the TS types declared `released_to_client_at` where the API
  serializes `released_at`, so the released state stayed false after a successful
  release. Fixed for zt, attack, csf and tech-debt.
- **Admins preview a dashboard before releasing it.** One shared
  `_dashboard_deliverable()` resolver serves all four services: clients get
  released-only (unchanged), admins also get merely-finalized, and both then run
  the _same_ builder — a test asserts the payloads are identical apart from a new
  `released` flag (default `True`, so existing consumers are unaffected).
- **Platform admins can open a dashboard on a cold URL.** The pages resolved the
  tenant from `/auth/me` then the active-client cookie, and an admin has neither —
  producing an API 400 and a Next server-exception page.
  `resolveDashboardClientId()` falls back to the service's owning tenant and the
  fetch sends `X-Client-Id`.
- **Latent bug fixed in all six web client libs:** `jsonRequest`'s error path called
  `res.json()` then `res.text()`, which throws "body stream already read" and
  masked the real error behind a confusing one.

Tests: `test_admin_removal.py` (8), `test_admin_llm_key.py` (9), 3 new dashboard
preview cases, `HomeDashboard.test.tsx` (3), `RunAiGuard.test.tsx` (5), and six
new e2e specs — `s31-home-service-links`, `s32-admin-org-index`,
`s33-admin-remove`, `s34-llm-key`, `s35-active-redirect`,
`s36-release-and-preview` — plus an extended `s12-a11y-nav`. Minor bump: new
user-facing surfaces and endpoints, all additive.

## [3.7.0] · Client-facing executive dashboards (all four services) · 2026-08-03

A released service now produces an interactive **client-facing executive
dashboard** (**D-035**) — previously specified (Design Mockup §9, IMPLEMENTATION
C5/D2) but never built. All four Atlas mockups now ship, each a faithful dark
dashboard driven by real released data, reached via a "View dashboard" link on
`/documents`:

- **MITRE ATT&CK Coverage** — KPI cards, coverage-by-tactic bar + coverage-mix
  donut, Detect/Prevent/Respond rings, blind-spot cards, searchable per-technique
  matrix.
- **Zero Trust** — current-vs-target maturity radar + per-pillar deep dive
  (`compute` run twice for current and target).
- **Tech Debt (software portfolio)** — spend-by-category bar, tool-sprawl donut,
  functional redundancies, identified savings, full inventory table.
- **Risk Register** — the synthesized 5×5 likelihood×impact matrix (code-derived
  tier), tier mix, per-axis bars, full register; client-level and gated on the
  register being finalized (linked from `/documents`).

Each has a release-gated client read endpoint over the existing deterministic
engine (no LLM), pure UI transforms with vitest, and a browser e2e
(`s27`–`s30`). Shared dark primitives in `components/dashboards/shared.tsx`; charts
use bundled `chart.js` + `react-chartjs-2` (dynamic, `ssr:false`). The mockups'
hand-written prose is intentionally not reproduced (no fabricated advice). NIST
CSF has no mockup and is not included. Details below cover the MITRE reference
vertical.

- **Backend:** new release-gated client read endpoint
  `GET /clients/{client_id}/attack/{service_id}/dashboard` returning the coverage
  rollup (overall + per-tactic) and per-technique matrix with detect/prevent/
  respond tooling. Reuses the deterministic `attack.analytics.compute()` engine
  and the value-summary release gate (`_released_service_ids_by_kind`), so it is
  visible exactly when the downloadable report is — sidestepping the fact that a
  released deliverable never flips its assessment to `RELEASED`. Tenant-scoped,
  404 (never 403) on mismatch.
- **Frontend:** a faithful dark executive dashboard at
  `/dashboards/attack/[serviceId]` — 4 KPI cards, a coverage-by-tactic stacked
  bar + coverage-mix donut (Chart.js, bundled + `ssr:false`), Detect/Prevent/
  Respond rings, "what you're blind to today" cards derived from real gap
  techniques, and a searchable/filterable per-technique matrix. Reached via a
  new "View dashboard" link on the released ATT&CK row in `/documents`.
- Charts derive from real released data only; the mockup's hand-written
  "executive recommendations" prose is intentionally not reproduced (no
  fabricated advice — AI narrative deferred).
- Tests: `test_attack_dashboard.py` (release gate + rollup math + tenant
  isolation), `lib/dashboards/attack.test.ts` (pure transforms),
  `s27-attack-dashboard.spec.ts` (client views the dashboard after release).
  New web deps `chart.js` + `react-chartjs-2`. Minor bump: a new user-facing
  surface, additive (no migration, no schema change).

## [3.6.0] · Open self-registration + tenant auto-provisioning · 2026-08-03

Standard users can now create their own accounts with no admin involvement
(**D-034**), superseding the domain-approval gate of D-004/D-016/D-019. The first
registrant still bootstraps the platform admin; after that `POST /auth/register`
auto-provisions the tenant instead of rejecting an unapproved domain:

- **Any email is accepted**, including personal providers (gmail, outlook, …).
- **Personal-email signups each get their own private organization** (never
  grouped by the generic domain — two gmail users never share a workspace).
- **A company domain groups coworkers**: the first user on a new domain creates
  the org (and its approved-domain mapping) and becomes its primary contact;
  later same-domain users auto-join it.
- Email verification stays **not required** to sign in (a verify email is still
  minted). No new migration — orgs/domains are created at runtime.
- A same-domain registration race is handled with a one-shot `IntegrityError`
  retry on `uq_client_domain_domain`.

Web: `/sign-up` copy now describes open self-serve; the sign-up form drops the
dead domain-approval error branches. Tests: backend `test_auth_routes.py` flips
the two "reject gmail/unknown-domain" cases to auto-provision assertions and adds
same-domain-join and personal-email-isolation cases; new
`SignUpForm.test.tsx` (vitest); `e2e/smoke/s1-signup-errors.spec.ts` replaces the
unapproved-domain case with a happy-path self-registration that lands the new
user signed in on `/intake`. Minor bump: a user-facing behavior change with no
schema or package-manifest change (tag/CHANGELOG level).

## [3.5.0] · Sprint 9 · Activate the seam (hybrid SSO + discard affordance + demo automation) · 2026-07-22

Branch `feat/sso-discard-demo-sprint-9`. Eleven tasks (T0 through T10) across
three themes: a hybrid Keycloak OIDC sign-in that sits beside the credentials
form (flag-gated, default off), a first-class draft-discard affordance in all
four services, and committed automation for the demo compose and the export
eyeball debt. It is a minor release: two new flag-gated user-facing surfaces
(OIDC sign-in and the discard button) with the whole existing auth and workflow
surface untouched when the flag is off. Version is tag and CHANGELOG level only;
package manifests are untouched. The plan was reviewed read-only by OpenAI Codex
before merge (verdict "rework" on 12 findings, 2 blockers; all folded into the
tasks, table in the planning PR body).

The three themes:

**Hybrid Keycloak OIDC, exchange-at-the-edge (D-032).** Keycloak authenticates
the user; the backend keeps minting its own HS256 JWTs (D-020 stays
authoritative). A Keycloak token is never accepted as an API bearer. The browser
round trip ends at a new `POST /auth/oidc/exchange`, which verifies the access
token against the realm JWKS and mints a native SHIELD pair only for an
already-active local account. There is no JIT provisioning.

**Draft discard across all four services (D-031).** A consultant can throw away
an in-progress DRAFT instead of approving a throwaway version to get it out of
the way. The three e2e specs that used to approve-away an open draft now discard
it, so version history stays honest.

**Demo and export automation (D-033).** The hosted-demo compose and reset script
are now driven by a committed self-skipping spec and a CI job on every PR, and
the five SMOKE §10 export eyeballs are replaced by unit assertions over real
PDF/DOCX/XLSX bytes.

- **Backend draft discard ×4 + `DISCARDED` status (T0, `638710c`):** a draft-only
  `POST .../discard` per service (tech-debt/csf/attack/zt), admin-only, mirroring
  each `approve` sibling. `DISCARDED` added to the four status enums (plain
  `String(16)`, no CHECK constraint, so no migration). DRAFT returns 200 with one
  audit row (`capability_list.discarded` / `{csf,attack,zt}.assessment.discarded`);
  re-discard is idempotent with no second row; SUBMITTED (csf/zt), APPROVED, and
  RELEASED refuse with a typed 409 `{reason: "not_discardable"}`; client role 403;
  unknown or cross-tenant id 404. The version trap is closed: every `_latest_*`
  helper now skips `DISCARDED` while the mint reads `max(version)` unfiltered, so
  discarding a non-v1 draft and re-extracting cuts a fresh version with no
  `IntegrityError`. The hidden latest-consumers outside the route files (the
  risk-register synthesis `_latest()` and the intake engagement cards) skip
  discarded rows too, and the discard write is a conditional
  `UPDATE ... WHERE status = 'draft'` so a racing client PATCH or AI run into a
  discarded parent loses loudly. See DECISIONS **D-031**.
- **Web discard UI + shared confirm dialog (T1, `578a98a`):** four proxy routes,
  `discard*()` client functions, `"discarded"` in the status unions, and the app's
  first destructive-confirm dialog, the shared `DiscardDraftButton` over the
  design-system `Modal`, wired into all four workspaces beside Approve/Start. It
  renders only for a DRAFT and states what will be destroyed (tech-debt N items,
  attack N scored techniques, csf/zt "N answers, including client-entered data").
  The workspace loader bumps its `reqSeq` before the post-discard refetch so a
  stale in-flight `latest` cannot resurrect the discarded draft.
- **Export-content unit assertions + pypdf test dep (T2, `af4dcf3`):** added
  `pypdf>=5` to the dev dependencies (test-only, never imported in `app/`) and a
  new `test_playbook_export_content.py` that drives the five playbook renderers
  over real bytes: PDF read back with `pypdf.PdfReader`, DOCX with
  `docx.Document`, and the XLSX Action Plan sheet (the SMOKE §19 contract, priority
  defaulting from `gap_priority()` with a `priority_override` winning). The
  per-service exporter tests moved from `%PDF-` magic to title + client name + a
  known row value; the risk register PDF/DOCX gained title + a known entry. SMOKE
  §10 is re-pointed to the proving test filenames with one explicitly-manual
  aesthetics line kept, and §19 is closed.
- **e2e: retire the approve-first dance + §31 UI proof (T3, `56bcfce`):** the three
  approve-any-open-draft preambles (`s4-techdebt`, `s5-attack`, `s11-staleness`)
  now discard the draft through the proxy, with every post-preamble assertion
  (`changed>0`, "AI 60%", the stale nudge) byte-identical. `s4` additionally drives
  the UI affordance once: draft open, cancel is a no-op, confirm throws the draft
  away and a re-upload mints a brand-new draft. New SMOKE §31.
- **Backend OIDC exchange + JWKS verifier (T4, `60d2abb`):** `SHIELD_AUTH_OIDC_ENABLED`
  (default False) with an `oidc_readiness()` boot preflight that mirrors
  `live_llm_readiness()` (config-shape only, no network at boot). `app/security/oidc.py`
  is a module-level JWKS cache (300s TTL, `threading.Lock`, 5s httpx GET, exactly one
  forced refetch on an unknown `kid`, raw fetch isolated for monkeypatching, no new
  dependency). `POST /auth/oidc/exchange` verifies RS256-only (alg-confusion guard)
  with `iss`, `aud`, and `azp` all pinned, then walks a typed dict-detail failure
  matrix (`oidc_disabled` / `oidc_token_invalid` / `oidc_jwks_unavailable` /
  `oidc_claims_missing` / `oidc_email_unverified` / `oidc_no_local_account` /
  `oidc_user_inactive` / `oidc_sub_mismatch`). TOFU binds `users.keycloak_sub` on
  first exchange. Success reuses the credentials path's `_issue_pair` +
  `_register_successful_login`, and the local DB role stays authoritative (a token
  claiming `roles:["admin"]` for a client-role user mints CLIENT tokens). Migration
  **0032** adds `users.keycloak_sub` (String(64), nullable, unique, `batch_alter_table`,
  additive). See DECISIONS **D-032**.
- **Dual-horizon Keycloak + real `/ready` probe (T5, `4c9ab64`):** the split-horizon
  issuer fix pins one canonical `iss` (`http://localhost:8080/realms/shield`) for
  browser and containers alike via `KC_HOSTNAME` + `KC_HOSTNAME_BACKCHANNEL_DYNAMIC`,
  with backchannel token/JWKS endpoints staying reachable at `keycloak:8080`. The
  `KEYCLOAK_ISSUER` default flipped in compose, the demo overlay, `.env.example`, and
  `config.py`; api gained `KEYCLOAK_JWKS_URL`, web gained `KEYCLOAK_INTERNAL_ISSUER`.
  The `/ready` keycloak probe is now real when the flag is on (httpx JWKS GET, ok/down)
  and dormant when off, and never gates readiness in either state. The realm export
  dropped the stale `reviewer` role (D-023 drift), added verified `admin@kentro.example`
  and `nolocal@atlas.example`, and added the `:3001` redirect URIs.
- **Web hybrid OIDC seam, flag-gated default OFF (T6, `ca0093b`):** new
  `lib/auth/oidc.ts` (`isOidcEnabled`, `rewriteKeycloakUrl`, `keycloakFetch` for
  container-side discovery), a conditional secret-less PKCE Keycloak provider in
  `options.ts`, and a `jwt` callback branch that calls `/auth/oidc/exchange` and
  seeds the token identically to the credentials path, with `OIDC_EXCHANGE_ERROR`
  terminal so `SessionExpiryGuard` signs out to `/sign-in?reason=oidc_exchange_failed`.
  The sign-in page conditionally renders `KeycloakSignInButton` plus the loud banner.
  With the flag off the provider does not exist and zero Keycloak network calls
  happen. The secret-less client works on next-auth `5.0.0-beta.31`, so the
  pre-approved confidential-client fallback was not needed and no secret was
  committed. A throwaway auth-code spike proved the round trip first and caught a
  real bug the unit mock could not: a rejected exchange left the token without an
  access token, so the next `jwt` call fell into `refreshAccessToken()` and clobbered
  the error; the fix makes `OIDC_EXCHANGE_ERROR` return before the refresh path.
- **Opt-in OIDC login e2e + SMOKE §32 (T7, `1e3e64e`):** `s26-oidc-login.spec.ts`
  self-skips unless `E2E_OIDC=1`, so the default suite is unchanged. Positive path:
  `admin@kentro.example` through the real Keycloak form lands authenticated and the
  admin management list renders, proving the exchanged SHIELD bearer authenticates a
  real API call end to end. Negative path: `nolocal@atlas.example` authenticates
  against Keycloak, the exchange refuses it, and the session signs out to the loud
  banner. Both paths were run green twice on the flag-on stack, then the flag was
  restored off and the full suite re-proven. New SMOKE §32 with the flip/restore
  operator note.
- **Demo-reset `--demo` mode + opt-in demo-journey spec (T8, `8b5e68a`):**
  `demo-reset.sh --demo` / `demo-reset.ps1 -Demo` overlay `docker-compose.demo.yml`
  on every compose call so the reset targets the production `shield-web:demo` image;
  plain invocation still drives the base compose. The silent web-wait is fixed to
  fail loudly and dump `docker compose logs web` on timeout. New
  `e2e/demo/demo-journey.spec.ts` (self-skips unless `SHIELD_DEMO_SMOKE=1`) asserts
  the post-reset journey: `/ready` full-matrix green, `/sign-in` 200 with the strict
  CSP (prod-build proof), admin and client sign-in, the client `/home` released-report
  hero, and a seeded `/documents` download. The destructive proving run passed, then
  the dev stack was restored. See DECISIONS **D-033**.
- **CI demo job (T9, `00d970e`):** a new isolated `demo` job in
  `.github/workflows/ci.yml` logs the compose version and hard-fails below 2.24 (the
  `!reset` floor), runs `bash scripts/demo-reset.sh --demo`, then
  `SHIELD_DEMO_SMOKE=1 npx playwright test demo/`, with always-run compose-ps/logs
  diagnostics and an `if: always()` artifact upload under a unique name; 25-minute
  timeout, triggers shared with the e2e job (push and PR to `main`). Its first green
  run is pending the dev opening the sprint PR (CI triggers only on push/PR to
  `main`), so SMOKE §27's CI-job box stays annotated "pending first PR run".
- **Wrap-up (T10, this commit):** SMOKE_TEST final pass (§10 re-pointed plus one
  manual aesthetics line, §19/§26/§27/§31 and the new OIDC §32), each box checked
  only with its proving spec or test filename; this CHANGELOG `[3.5.0]` entry;
  BUILD_REPORT synced to HEAD; the `CONTEXT.md` end-of-sprint snapshot; and
  `context/dave.md` refreshed. The final exit-gate run caught one cross-task
  regression: T5's dual-horizon flip moved the canonical issuer to
  `http://localhost:8080/realms/shield`, but T4's `test_oidc_exchange.py` still
  signed its happy-path tokens with the pre-T5 `http://keycloak:8080/...` issuer
  and relied on the config default, so all 14 positive cases failed with a
  masked-issuer mismatch. The running system was correct all along (config pins the
  canonical issuer, and T7's live `s26` exchange accepted a real Keycloak token end
  to end); only the unit fixture's issuer constant was stale, so it was corrected to
  the canonical value, no assertion weakened. The full exit gate set and the full
  e2e suite are green on the flag-off dev stack.

Migration this sprint: **0032** (`users.keycloak_sub`, T4), additive and
SQLite-safe (C0). New DECISIONS: **D-031** (draft discard as an admin-only
soft-delete state transition), **D-032** (hybrid Keycloak SSO as a flag-gated
token exchange, never a bearer), **D-033** (destructive-by-design automation is
opt-in-gated). e2e spec files grew from 25 to 27 (`s26-oidc-login` and
`demo/demo-journey` added, both self-skipping so the default suite is unchanged).

## [3.4.1] · Sprint 8 · Prove it in the browser (eyeball-debt burn-down) · 2026-07-21

Branch `feat/browser-proof-sprint-8`. Eight tasks (T0 through T7). The sprint
converts human-eyeball SMOKE debt into committed Playwright specs and pays the
last mint-route debt. It is a patch release: regression and browser proof plus
one backward-compatible idempotency fix, no new user-facing surface. Version is
tag and CHANGELOG level only; package manifests are untouched.

The sprint's most consequential outcome was an out-of-plan product bug fix, and
it is the reason the browser proof mattered:

- **Fixed: MFA sign-in never revealed the TOTP field in the browser (`f10b803`).**
  The web `SignInForm` sent `totp: undefined` into `signIn()`. next-auth
  serializes credentials through `URLSearchParams`, which coerced that
  `undefined` to the literal string `"undefined"`, defeating the `!totp` guard in
  `authorize()`. The MFA branch then verified a bogus code, returned a generic
  `credentials` failure instead of `mfa_required`, and the second-step code field
  never appeared. The fix sends `totp` only when it is present
  (`...(totp ? { totp } : {})`); the backend and `@auth/core` were correct all
  along. The new T4 browser spec surfaced it. The Sprint-7 vitest had missed it
  because that test mocks `signIn()`. A vitest guard now asserts an empty-code
  submit omits the `totp` key. This was a launch-blocker for MFA (D-027) and the
  clearest payoff of the whole sprint: a flow that unit tests called green was
  broken for every real user.
- **Shared MailHog reader helper (T0, `3b7bfb7`):** extracted the inline MailHog
  reader from `s21-email-verify.spec.ts` into `e2e/helpers/mailhog.ts`
  (`MAILHOG_API`, `fetchLatestMessage`, `extractToken`, `subjectOf`), and upgraded
  the search to poll by recipient plus expected subject so registration mail no
  longer wins a first-message race. s21 consumes the helper with zero behavior
  change.
- **Tech-debt extract draft-exists guard (T1, `4396f60`; e2e follow-up
  `b4fe0ba`):** a second POST to the tech-debt extract route while a draft is open
  now returns that draft with an idempotent 200 _before_ `extract_capabilities()`
  runs, so a double-click fires no second LLM call, writes no second audit row,
  and preserves consultant edits. This ports the CSF/attack/zt pattern to the last
  route that still minted unbounded versions on every POST.
  `test_extract_versions_subsequent_lists` was deliberately re-contracted to prove
  versioning across the APPROVED/RELEASED boundary instead. The e2e follow-up
  realigned `s4-techdebt.spec.ts` to the new contract (it now approves any open
  draft before upload so extract mints a fresh draft). No new D-number: this
  applies an existing pattern.
- **Release notification visible in MailHog (T2, `d023226`):**
  `s22-release-notify.spec.ts` creates an isolated tenant and a unique-email
  client user, finalizes and releases a CSF deliverable, then asserts via the T0
  helper that the notification lands in MailHog for that client with the release
  subject and the `/documents` link. It proves recipient selection for real, which
  the four stubbed-sender unit tests could not (SMOKE §29).
- **Verify / forgot / reset pages driven in the browser (T3, `442fca5`):**
  `s23-auth-pages.spec.ts` registers a unique-email user, pulls the verification
  token from MailHog, confirms the address on `/verify-email`, requests a reset on
  `/forgot-password`, completes it on `/reset-password`, and signs in with the new
  password. s21 stays as the API-path proof; s23 proves the pages.
- **MFA enrollment + TOTP sign-in (T4, `f70a8cc`):** `s24-mfa.spec.ts` part A adds
  an `otpauth` TOTP generator to the e2e harness, enrolls a fresh user on
  `/account` with a generated code, asserts the recovery codes are shown once, and
  signs in through the UI TOTP second step. This is the spec that surfaced the
  `f10b803` MFA bug.
- **Recovery-code sign-in, single-use (T5, `1e782de`):** `s24-mfa.spec.ts` part B,
  a self-contained test with its own fresh user, redeems one recovery code at the
  sign-in TOTP step, then proves the same code is rejected on reuse. Together T4
  and T5 retire the manual MFA walkthrough.
- **Admin-health matrix + `/documents` empty state (T6, `57277ea`):**
  `s25-admin-health.spec.ts` signs in as admin and asserts the all-green
  `/admin/health` operator matrix against the live dev stack;
  `s17-documents.spec.ts` gained an empty-state assertion in a fresh per-run
  throwaway tenant, proving the no-dead-ends state (SMOKE §17) that the persistent
  s17 tenant can never show because it always carries a released row.
- **Wrap-up (T7, this commit):** SMOKE_TEST boxes checked only with their proving
  spec filename (§29 release-notify via s22, verify/forgot/reset pages via s23,
  MFA UI via s24, `/admin/health` via s25, `/documents` empty state via s17); this
  CHANGELOG `[3.4.1]` entry; BUILD_REPORT synced to HEAD; the `CONTEXT.md`
  snapshot; and `context/dave.md` refreshed. Unit-proven backend-invariant boxes
  (§16 release deny paths, §20 preview internals, §21 audit filters) and the
  end-of-file sign-off boxes stay unchecked: nothing this sprint proves them in a
  browser.

No new migrations. No new DECISIONS. e2e spec files grew from 21 to 25 (s22, s23,
s24, s25 added; s17 gained the empty-state test).

## [3.4.0] — Sprint 7 · GCP live path + close the client loop — 2026-07-16

Branch `feat/gcp-vertex-sprint-7`. Seven tasks (T0–T6). The sprint proves the
live-AI path against a **real** provider with no static key — Vertex AI via
Application Default Credentials (D-029) — validated end-to-end on Dave's box
across all five AI purposes; closes the client loop with a release-notification
email (D-030); turns dev/CI email delivery on by default so the MailHog flow is
real in every run; finishes the Sprint-5 stale-fetch (`reqSeq`) guard sweep; and
migrates the web auth stack from next-auth v4 to Auth.js v5, clearing the
`uuid@8.3.2` moderate advisory. New user-facing surface (release notification) +
a real GCP live path justify the **minor** bump. All exit gates green: the full
Playwright suite, `pytest -m unit`, web `tsc --noEmit`, in-container web vitest,
in-container web eslint, host prettier `--check` (3.9.5), and in-container
ruff/black (root-config parity).

- **Vertex AI provider adapter via ADC (T0, `7dcf159`):** added a live
  `VertexProvider` beside `GeminiProvider` in `app/ai/llm.py`, selected by
  `SHIELD_LLM_PROVIDER=vertex`. It calls the regional
  `{region}-aiplatform.googleapis.com` `generateContent` endpoint and
  authenticates with **Application Default Credentials — no static API key**;
  `google-auth` is a real `apps/api` dep (rebuild the image). The bearer token
  never appears in logs, `llm_calls.error_message`, or exception text (it rides
  the header, not the URL — a unit test locks it). `gemini` (API key,
  `generativelanguage`) and `vertex` (ADC, `aiplatform`) speak the identical
  `generateContent` schema, so body-build/parse are factored into shared helpers.
  `live_llm_readiness()` for `vertex` requires `GCP_PROJECT_ID` set, `google-auth`
  importable, AND ADC resolvable — a loud boot `RuntimeError` otherwise (D-026
  parity); `/admin/ai-status` + `/ready` inherit it. Compose bind-mounts the host
  gcloud config dir read-only; ADC is never copied into the repo or image. See
  DECISIONS **D-029**.
- **GCP live validation sweep + SMOKE §14 GCP annotation (T1, `329f9a5`):** ran
  the sprint's is-it-real payoff — all five AI purposes through the redaction seam
  against real Vertex (`vertex`/`gemini-2.5-flash`, ADC-only) on Dave's box. The
  sweep surfaced and fixed **two adapter defects** no keyless unit test had
  exercised, both now `pytest -m unit` locked: (1) `google-auth`'s token-refresh
  transport hard-requires `requests`, so the dep is now `google-auth[requests]`;
  (2) gemini-2.5 "thinking" spent an unbounded slice of `maxOutputTokens` and
  truncated the longer drafts mid-JSON, silently returned as "completed" — fixed
  with a **loud `finishReason` guard** (non-STOP now raises at the parse seam),
  the output cap raised 4096→8192, and a bounded `thinkingConfig.thinkingBudget`
  (2048) for gemini-2.5+ only. SMOKE_TEST §14/§14.1 annotated GCP-validated
  2026-07-15 (opt-in spec is the proof, CI-skipped keyless). `.env` reverted to
  fixture; a keyless run self-skips clean. See DECISIONS **D-029** addendum.
- **Client release notification email (T2, `4420b53`):** the shared
  `release_deliverable` helper (behind all four services + risk register) now
  emails **every active client-role user of the deliverable's tenant** on release
  when delivery is on — carrying the service, title/version, and a
  `{WEB_BASE_URL}/documents` link. Best-effort: delivery-off releases behave
  exactly as v3.3.0 (loud skip log); a per-recipient SMTP failure is logged loudly
  and the release **still stands** (release is the source of truth — a
  notification failure must never roll it back). Cross-tenant users and admins are
  never notified. Four `pytest -m unit` tests
  (`test_release_notification.py`). See DECISIONS **D-030**.
- **Enable email delivery in dev/CI compose (T3, `d95f5c7`):** flipped
  `SHIELD_EMAIL_DELIVERY_ENABLED` default to `true` in `docker-compose.yml`
  (SMTP → the `mailhog` service, so boot never refuses) so the registration /
  verify / reset email loop is real in every dev and CI run and
  `s21-email-verify.spec.ts` **runs** instead of self-skipping.
  `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` stays `false` — flipping it would break every
  e2e sign-in (seeded/spec users are unverified); enforcement remains a
  deploy-time choice. The CI `e2e` job comment notes MailHog is now exercised.
- **reqSeq stale-fetch guard sweep remainder (T4, `37f9bd6`):** finished the
  Sprint-5 carry-over — swept the admin workspaces/panels the 14 react-hooks rules
  did not force, applying a `reqSeq` guard **only** where a stale mount-fetch
  response can clobber newer state (each edit justified in the commit body, no
  speculative guards). Vitest guards added for the two highest-traffic
  newly-guarded components (deferred-promise pattern).
- **Auth.js (next-auth) v5 migration (T5, `3de0626`):** migrated web auth from
  `next-auth@4.24.14` to Auth.js v5 (`next-auth@5.0.0-beta.31` + `@auth/core`).
  `lib/auth/options.ts` now owns `NextAuth()` and exports
  `{handlers, auth, signIn, signOut}`; the `[...nextauth]` route re-exports the
  handlers; 34 `getServerSession(authOptions)` call sites moved to `auth()`. The
  MFA signal is re-wired for v5 (every credentials failure normalizes to
  `CredentialsSignin`, so the password-ok-need-TOTP branch throws a subclass whose
  `code='mfa_required'` surfaces via `signIn(redirect:false).code`; `SignInForm`
  reads `result.code`, not `result.error`). Behavior-identical: auth e2e green.
  `pnpm audit`: the `uuid@8.3.2` moderate is **gone** (`uuid` no longer in the
  lockfile); only the documented `postcss` moderate remains. New
  `SignInForm.test.tsx` locks the code-based MFA signal. BUILD_REPORT audit
  posture updated.
- **Wrap-up (T6, this commit):** SMOKE_TEST §14 GCP annotation (T1), §25 checked
  via the now-running `s21` (T3), new §29 release-notification section (T2) — boxes
  only where a green committed spec proves it (honesty convention); this
  `[3.4.0]` CHANGELOG entry; BUILD_REPORT synced (Vertex in the provider matrix,
  post-T5 audit posture, gate results); DECISIONS D-029/D-030 verified landed;
  full exit gate set green; CONTEXT.md end-of-sprint snapshot; `context/dave.md`
  refreshed.

## [3.3.0] — Sprint 6 · real demo — 2026-07-12

Branch `feat/real-demo-sprint-6`. Twelve tasks (T0–T11) turning the platform
into a real, self-standing demo: the live-AI path is now runnable and fails
loudly at boot when misconfigured, seeded deliverables actually download, real
TOTP MFA and real email verification + password reset ship on the custom-JWT
stack (the D-020 boot-refusals are gone — the flags now gate enforcement), a
full-matrix `/ready` + `/admin/health` operator view lands, the demo seed tells
a coherent downloadable Atlas story with a one-command reset, and a hosted-demo
compose runs web as a production build. New user-facing auth features + a runnable
live path justify the **minor** bump. All exit gates green: the full Playwright
suite, `pytest -m unit`, web `tsc --noEmit`, in-container web vitest, host
prettier `--check` (3.9.5), in-container ruff/black (root-config parity), and the
in-container web eslint gate.

- **Live-AI enablement + boot preflight (T0, `8aebe51`):** declared
  `anthropic>=0.40,<1` as a real `apps/api` runtime dep (the `AnthropicProvider`
  lazy-imports it, so an undeclared SDK surfaced only as an `ImportError` on the
  first live Run-AI — the image must be rebuilt, not just restarted); replaced the
  stale default model `claude-opus-4-7` (invalid → 404) with `claude-sonnet-5` in
  `config.py` + `docker-compose.yml`; added a live-mode boot preflight
  (`Settings.live_llm_readiness()` → `assert_safe_for_runtime()` raises a loud
  `RuntimeError` at lifespan when the key is missing / SDK unimportable / model a
  placeholder), also surfaced via `GET /admin/ai-status`. Fixture mode unaffected.
  See DECISIONS **D-026**.
- **Live-AI integration test + SMOKE §14 (T1, `a19fded`):** codified the
  2026-07-12 manual smoke as a committed opt-in spec
  (`apps/api/tests/live/test_live_ai.py`, `@pytest.mark.live`) + a one-command
  `scripts/smoke_live_ai.py`. The `live` marker is registered and EXCLUDED from
  `-m unit` and CI; both self-skip without `SHIELD_LLM_MODE=live` + a key, so the
  loop/CI stay green keyless. SMOKE_TEST §14 annotated as validated by the opt-in
  spec + documented procedure (not falsely checked as CI-green).
- **Seed → storage parity (T2, `0bbabac`):** the demo seed obtained its backend
  from `get_storage()` (not a direct `LocalFilesystemStorage`) so it writes where
  the API reads (MinIO under compose); `tech_debt/extract.py`'s local-path
  shortcut routed through the storage protocol uniformly. e2e: after `down -v` +
  reseed, the seeded Atlas client downloads a SEEDED released deliverable → 200
  with the §15.5 filename (410 before the fix). `s17-documents.spec.ts` gained the
  parity test.
- **Full dependency-health readiness + operator view (T3, `9b2c74b`):** `/ready`
  moved from a DB-only `SELECT 1` to a per-dependency matrix (db, redis, minio,
  keycloak-dormant, LLM readiness reusing the T0 preflight); any down required
  dependency flips `ready=false` and names the offender while `/health` liveness
  stays cheap. New `/admin/health` operator page (`HealthMatrix`) renders the
  matrix with an all-green / degraded overall badge (vitest-covered).
- **Real TOTP MFA (T4, `bf8e7c6`):** migration `0030` (additive/C0) adds
  `users.mfa_totp_secret` (Fernet-encrypted, nullable) + a `user_recovery_codes`
  table. RFC 6238 TOTP against the stdlib (`app/security/totp.py`, locked to the
  RFC vectors — no OTP dep); `POST /auth/mfa/enroll` (otpauth URI + secret),
  `/auth/mfa/verify` (confirm + 10 one-time recovery codes shown once), and
  `/auth/mfa/verify-login` (completes the short-lived `mfa_pending` challenge).
  The D-020 boot-refusal on `SHIELD_AUTH_REQUIRE_MFA` is removed — the flag now
  GATES enforcement. Web: sign-in MFA step + a net-new account enrollment section.
  See DECISIONS **D-027**.
- **Real email verification + password reset (T5, `f67c79f`):** migration `0031`
  (additive/C0) adds an `email_tokens` table (SHA-256 hash only, purpose, expiry,
  used-at). Registration mints a verification token + sends the email;
  `/auth/verify-email`, `/auth/resend-verification`, `/auth/forgot-password`,
  `/auth/reset-password` — single-use, time-bounded, enumeration-safe. The SMTP
  sender is gated by `SHIELD_EMAIL_DELIVERY_ENABLED` (off = logged no-op so the
  flow works in dev/tests; on without `SMTP_HOST` refuses to boot). The D-020
  boot-refusal on `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` is removed — the flag now
  gates login. Web: net-new verify-email / forgot-password / reset-password pages.
  e2e via MailHog (opt-in, self-skips). See DECISIONS **D-028**.
- **OpenAI reasoning-model token param (T6, `19636b5`):** the OpenAI adapter now
  sends the correct output-token-limit key per model family
  (`max_completion_tokens` for reasoning/responses models, legacy `max_tokens`
  otherwise) instead of always `max_tokens`. Deferred item from Sprint 4 D-024;
  `test_llm_providers.py` updated (httpx monkeypatched, no live key).
- **Live-AI parity sweep — all five purposes (T7, `8761d91`):** extended the T1
  opt-in spec from csf-only to a parametrized sweep over `csf_score`, `zt_score`,
  `mitre_map`, `risk_synthesize`, `tech_debt_extract` — each plants identical
  canonical PII (twice each) and asserts a complete live `llm_calls` row,
  `redacted_counts == {email:2, name:2, client_org:2}`, no PII, AND that the
  response parses into the route-layer container (the per-adapter parse check).
  Still `@pytest.mark.live`, self-skips keyless. SMOKE_TEST §14.1 documents it.
- **Demo data realism + one-command reset (T8, `39b3cfc`):** the seed now
  synthesizes a coherent Atlas Risk Register (7 hand-authored entries whose tiers
  are ALWAYS code-derived via `risk.engine.tier_for`, real ATT&CK + CSF codes) and
  exports XLSX/PDF/Word through `get_storage()`; tech-debt items gained believable
  per-tool disposition rationales. New `scripts/demo-reset.(ps1|sh)`: `down -v` →
  `up -d --build` → poll `/ready` full-matrix → seed → print URLs+creds (documented
  in README + ONBOARDING). `s8-risk-register.spec.ts` gained a read-only test
  proving the seeded register's code-derived tiers + downloadable exports.
- **Hosted-demo compose (T9, `db33372`):** `docker-compose.demo.yml` is a thin
  override redefining only the web service as a production Next standalone build
  (`shield-web:demo`, `volumes: !reset []`, `node apps/web/server.js`,
  `NODE_ENV=production`), fixture-by-default. Scope expansion: added a root
  `.dockerignore` + rewrote `apps/web/Dockerfile` (it had never built cleanly), and
  fixed a latent CI lint failure in `HealthMatrix.tsx` (react-hooks
  set-state-in-effect) that the loop gate set had let slip. Cloud/terraform NOT
  touched.
- **Security + audit pass (T10, `18b7d85`):** two findings fixed TDD-first. (1)
  MFA second-factor guesses at both `verify-login` and enroll-confirm now feed the
  SAME account-lockout counter as password failures (and refuse with 423 when
  locked); the counter resets ONLY on a fully successful login (removed the
  premature `_clear_password_failures` on the mfa-challenge / email-not-verified
  branches that let a password-holder evade second-factor lockout). (2) `/ready`
  now reduces per-dependency `detail` to a generic string for anonymous callers
  (LBs/k8s still get statuses + offender names) while authenticated callers get
  full operator detail. Audit scans: bandit exit 0; JS-audit posture carried
  unchanged from Sprint 5 (0 high / 2 documented moderates — no JS manifests
  changed); manual secret-diff scan clean; no secret committed.
- **Wrap-up (T11, this entry):** SMOKE_TEST §22–§28 for live-AI enablement,
  full-matrix health + `/admin/health`, MFA, email verify/reset, seed→storage
  parity + demo realism, hosted-demo compose, and the security hardening — each box
  checked only where a green committed spec proves it, annotated by spec filename;
  key-gated live specs and the MailHog e2e marked opt-in/CI-skipped, not falsely
  checked; CHANGELOG `[3.3.0]`; DECISIONS **D-026/D-027/D-028** verified landed;
  the full exit gate set re-run green; CONTEXT.md end-of-sprint snapshot.

Migrations this sprint: **0030** (MFA TOTP secret + recovery codes, T4) and
**0031** (email verification/reset tokens, T5), both additive and SQLite-safe
(C0). New DECISIONS: **D-026** (live-AI enablement + boot preflight), **D-027**
(real TOTP MFA), **D-028** (real email verification + password reset).

## [3.2.0] — Sprint 5 · client value loop — 2026-07-10

Branch `feat/client-value-loop-sprint-5`. Eleven tasks (T0–T10) turning
consultant output into client-visible value: a deliverable release-to-client
flow, the `/home` executive dashboard with the §2.5 value-loop card, the
`/documents` page, a CSF POA&M action-plan step, a pre-egress redaction preview,
and the first read surface over the append-only audit stores — plus a web
unit-test harness, adoption of the 14 react-hooks v6 rules, and a prettier pin
sync. New client-facing features justify the **minor** bump. All exit gates
green: the full Playwright suite, `pytest -m unit`, web `tsc --noEmit`, host
prettier `--check` (3.9.5), in-container ruff/black (root-config parity), and
the new in-container web vitest gate (T8).

- **Prettier 3.9.5 pin sync (T0, `37330cc`):** landed dependabot #29's
  3.9.4→3.9.5 bump on the sprint branch and synced the four gate pins the bot
  can't touch (CLAUDE.md real-commands, CONTEXT.md machine-local facts, the
  runtime queue `gates` array, and the staged sprint-5 queue). A format gate that
  diverges from the lockfile ships red CI (the Sprint 2 lesson). #29 closed as
  superseded.
- **Deliverable release flow, backend (T1, `1863f9a`):** migration `0028`
  (additive/C0) adds `deliverables.released_at` + `released_by` (nullable; old
  rows parse as unreleased). A shared `app/deliverable_release.py` helper backs
  four per-service `POST /{svc}/deliverables/{id}/release` routes — admin-only,
  requires `finalized_at` (typed 409 `not_finalized`, D-016), idempotent 200
  no-op on re-release with a loud log, audit row `*.deliverable.released`. New
  `GET /clients/{cid}/deliverables` returns ONLY released deliverables of the
  caller's tenant (404 cross-tenant, never 403). Artifact download now admits a
  client for the formats of a released own-tenant deliverable, and nothing else
  (unit-tested allow/deny matrix). The model docstring's "no client release
  path" note is updated by design. See DECISIONS **D-025** (a new admin-only
  release action, explicitly not a revival of the removed D-005/D-006 reviewer
  gate — D-023).
- **`/documents` client page (T2, `dd2ff1b`):** server component
  `app/documents/page.tsx` resolves the tenant (client `client_id` or admin
  active-client cookie) and renders the T1 client list as a table — service
  label, title, version, released date, Final / Superseded badge, per-format
  download links. Client nav gains **Documents**; admin nav unchanged. Empty
  state per the no-dead-ends rule. e2e `s17-documents.spec.ts` (isolated tenant):
  admin finalize+release v1, client sees the row + PDF download 200 with the
  §15.5 filename, unreleased v2 hidden.
- **`/home` client dashboard (T3, `bb981a5`):** server component
  `app/home/page.tsx` fetches existing endpoints only (deliverables, per-service
  intake status, unread messages) — no new scoring. Presentational
  `HomeDashboard`: greeting, a hero band shown ONLY when a released deliverable
  exists (else next-step guidance — no dead ends), a per-service status grid of
  phase labels (report ready / finalizing / under review / in progress / getting
  started — never numbers), waiting-on-you, and recent activity. §6.4 enforced:
  no scoring math, audit internals, or raw AI output. Role landing: a signed-in
  client on `/` redirects to `/home`, admin to `/admin`. e2e
  `s18-home.spec.ts`: hero-absent → release → hero-present, both role landings,
  no-percentage guard.
- **Cross-service value-loop card (T4, `3ccddca`):** `GET
/clients/{cid}/value-summary` — a DETERMINISTIC aggregation over
  already-computed engine outputs (CSF/ZT/ATT&CK gap counts + Tech Debt annual
  savings), no LLM and no new scoring (a unit test asserts zero `llm_calls` rows
  and no `app.ai` import in the module). A service feeds a client-visible number
  ONLY once it has a RELEASED deliverable (spec-12 visibility); otherwise the
  slot is null and the card renders **Pending** — never a fake 0.
  `ValueLoopCard` renders on `/home` when the tenant has any data. e2e
  `s19-value-loop.spec.ts`: no card pre-release → scored+released CSF → gap count
  - Pending, no percentage leak.
- **CSF POA&M / action plan (T5, `2a43a13`):** migration `0029` (additive/C0)
  adds `csf_gap_actions` keyed (assessment_id, subcategory_code), all annotation
  fields nullable (characterization / priority_override / owner / deadline /
  resources / success_criteria / poam_ref). `GET`/`PUT
/csf/services/{sid}/gap-actions[/{code}]` (admin autosave upsert, D-016 typed
  errors). The scoring engine (`playbook.py`) is read-only for the default
  priority (`gap_priority()`); a set `priority_override` wins. The playbook
  **XLSX** gains an **Action Plan** sheet (backward-compatible optional param).
  Admin UI `CsfGapActionEditor` (auto-save on change/blur, reqSeq guard). e2e
  `s7-csf-playbook.spec.ts`: characterize + owner auto-save survive a reload.
- **Redaction preview gate (T6, `0a92110`):** `POST /ai/preview` (admin-only,
  AI-rate-limited) shows the EXACT payload a service's next Run-AI would egress
  AFTER redaction — WITHOUT egress and WITHOUT an `llm_calls` row (no provider is
  ever constructed). Each service's inline run-ai payload build was factored into
  one builder (`build_{csf,zt,attack}_ai_request`) that both run-ai and preview
  call, so preview can never diverge from egress (a no-behavior-change refactor
  the run-ai regression suites lock). TECH_DEBT (file-extract, not state-based)
  returns a typed 422 `preview_unsupported`. Reusable `AiPreviewButton` wired
  into the CSF/ZT/ATT&CK Run-AI surfaces (non-blocking — an offered gate). e2e
  `s7-csf-playbook.spec.ts` asserts preview payload + counts, then a real run.
- **`/admin/audit` viewer (T7, `a14c1b0`):** two admin-only read routes over the
  append-only stores that had 42 write sites and zero readers — `GET
/admin/audit-entries` (filters: action prefix, target_type, actor,
  correlation_id, date range) and `GET /admin/llm-calls` (filters: client_id,
  purpose, provider, status, date range; projects only audit-safe fields, no API
  keys). Keyset cursor pagination on `(at/requested_at desc, id desc)` — no
  OFFSET; a bad cursor is a typed 422. `AuditViewer` is a read-only two-tab UI
  (Activity / AI calls) with per-tab filters and correlation-id click-through
  that links the tabs. e2e `s20-audit.spec.ts`: an in-test `csf.run_ai` appears
  in Activity, its fixture `csf_score` row in AI calls, correlation links them.
- **Web unit-test harness (T8, `3bc2b54`):** stood up vitest +
  `@testing-library/react` + jsdom in `apps/web` (no framework existed before —
  only the root e2e/). `pnpm -F web test` is a single deterministic run with a
  fail-loud fetch stub for unmocked network. Two guard tests lock the two
  stale-fetch `reqSeq` guards (`MessageThread`, `CsfPlaybookPanel`): a stale
  mount GET resolving after a newer request is discarded, and a failed load
  surfaces to `role=alert` — each verified to bite (defeating the guard fails the
  test). The web CI job runs the step, and the in-container web test gate was
  appended to the runtime queue `gates` array (the Sprint-4 T0 pattern).
- **react-hooks v6 adoption (T9, `f590d99`):** enabled all 14
  `eslint-plugin-react-hooks` v6 rules that Sprint-4 T3 had configured off for
  flat-config parity — ZERO rules now configured off. `eslint .` surfaced 14
  errors (13 set-state-in-effect + 1 purity); fixed by pattern, not suppression:
  mount-fetch effects wrapped in an async IIFE (the `MessageThread` shape),
  `AuditViewer`'s pre-await setState moved inside a nested async fn, the
  Tier/ZtStage focus-sync effects rewritten as the sanctioned adjust-state-during-render
  pattern, and `SaveStatus`'s render-time `Date.now()` moved into interval-driven
  state. Behavioral edits to shared components validated by the full e2e suite.
- **Wrap-up (T10, this entry):** SMOKE_TEST §16–§21 for the release flow,
  `/documents`, `/home` + value card, POA&M editing, redaction preview, and
  audit viewer — each box checked only where a green committed spec proves it,
  annotated by spec filename; CHANGELOG `[3.2.0]`; BUILD_REPORT synced; DECISIONS
  **D-025** verified landed; the full exit gate set (full e2e, `pytest -m unit`,
  tsc, prettier 3.9.5, in-container ruff/black, web vitest) re-run green;
  CONTEXT.md end-of-sprint snapshot.

Migrations this sprint: **0028** (deliverable release fields, T1) and **0029**
(`csf_gap_actions`, T5), both additive and SQLite-safe (C0). New DECISIONS:
**D-025** (deliverable release-to-client as a new admin-only action).

## [3.1.0] — Sprint 4 · framework majors + multi-provider LLM — 2026-07-09

Branch `feat/majors-providers-sprint-4`. The D-018 framework-majors bundle
deferred from Sprint 2/3 landed one major at a time with the full Playwright
suite as the regression net, plus multi-provider LLM egress. The bundle of
runtime/framework majors (Next 14→15, React 18→19, Tailwind 3→4, ESLint 8→9,
Node 20→22) justifies the **minor** version bump. All exit gates green: the
full e2e suite (34 tests), `pytest -m unit`, web `tsc --noEmit`, host prettier
`--check` (lockfile-pinned 3.9.4), and the new in-container ruff/black gate
(root-config parity, T0).

- **Lint-gate CI parity (T0, `4c068d0`):** Sprint 3's only red CI was 6
  ruff/black findings the loop never saw — CI runs from a full checkout where
  config discovery walks up to the ROOT `pyproject.toml [tool.ruff]`, but the
  api container mounts only `apps/api`, so in-container runs silently used
  defaults. Fixed with a read-only compose mount of the root config into the
  api service (parent of `/app`, so discovery finds it naturally); the
  `ruff check --no-cache . && black --check .` gate is now in the runtime queue
  `gates` array and documented in CLAUDE.md. The loop's lint gate now equals
  CI's.
- **Next 15 + React 19 (T1, `77bd360`):** bumped `next` → 15.5.20, `react` /
  `react-dom` → 19.2.7 (plus `@types/react*` and `eslint-config-next`) together;
  ran the official `@next/codemod`. Reviewed the breaking surfaces that touch
  us: async request APIs (`cookies()`/`headers()` in `app/api/proxy/*` routes)
  and the fetch/route-handler caching default change (the app relies on dynamic
  rendering — each proxy route verified). `next-auth` 4.24.x runs on Next 15
  without forcing the Auth.js v5 migration (verified sign-in/session/middleware
  early). The full e2e suite is green on the new stack; the `next < 15.5.16`
  advisories that dominated the root audit are cleared.
- **Tailwind 4 (T2, `f6d816a`):** CSS-first migration — `@tailwindcss/postcss`
  plugin, `@theme` in CSS replacing most of `tailwind.config`, breaking utility
  renames swept across `apps/web/src` and `packages/`. The
  `packages/design-system/src/tokens.css` custom properties survive; the s16 axe
  sweep asserts the Sprint 2 `--ink-tertiary` contrast fix still holds. Full
  e2e + axe green; in-container `pnpm -F web build` clean.
- **ESLint 9 flat config (T3, `bf82fd2`):** migrated `apps/web` to
  `eslint.config.js` flat config on ESLint 9 (9.39.4) with
  `eslint-config-next` 16's `./core-web-vitals` flat export, preserving the
  exact 47-rule set from the old `next/core-web-vitals` (verified via
  `eslint --print-config` diff); old `.eslintrc*` deleted, prettier compat kept.
  **ESLint 10 is honestly deferred upstream** (Dave decision 2026-07-09,
  superseding SPRINT_4.md's ESLint-10 target): no published Next lint stack runs
  on 10 today — `eslint-plugin-react` 7.37.5 uses the removed
  `context.getFilename()` and Next's compiled babel parser hits an
  `eslint-scope` `scopeManager.addGlobals` gap. Revisit when
  `eslint-plugin-react` ships v10 support. See DECISIONS **D-018** annotation.
- **Node 22 (T4, `bf6ccdd`):** `node:20-bookworm-slim` → `node:22-bookworm-slim`
  in the three `apps/web/Dockerfile` stages, `node:20-bookworm` → `node:22`
  compose web image, `engines.node >= 22` in the web package.json, both CI
  `setup-node` steps (web + e2e jobs) to `22`, and the ONBOARDING host-Node
  note. Web force-recreated on node 22.23.1; full e2e green on the rebuilt
  stack. Deliberately after T1–T3 so a Node failure would not be confounded with
  framework breakage.
- **Audit to zero (T5, `987a4f2`):** root `pnpm audit` reports 0 critical / 0
  high (T1's Next 15 cleared the 17 `next < 15.5.16` advisories); `e2e/` `npm
audit` 0 total. Two root **moderates** are deliberately left open and
  documented: `postcss` 8.4.31 (pinned inside `next@15.5.20`; the XSS-stringify
  path only fires on untrusted CSS, N/A at build time) and `uuid` 8.3.2 (via
  `next-auth@4.24.14`; the buffer-bounds bug is v3/v5/v6-only). Neither is
  overridden — forcing a bump would risk regressing the e2e-validated stack for
  zero real security gain; both clear on the upstream / Auth.js v5 bumps.
  `dependabot.yml` D-018 major-suppression posture is unchanged (this sprint IS
  that plan executing); only the stale policy comment was refreshed.
- **Multi-provider LLM egress (T6, `05121de`):** live `OpenAIProvider`
  (chat/completions) and `GeminiProvider` (`generateContent`) added beside
  `AnthropicProvider` in `app/ai/llm.py`, both thin `httpx` adapters (no new SDK
  dependency). `_build_provider` now routes `anthropic`/`openai`/`gemini`;
  `azure_openai`/`bedrock`/`local` stay loud not-implemented `RuntimeError`s. The
  egress contract above the seam is untouched — redaction, the `llm_calls` audit
  row (provider/model/client_id), and "AI suggests, code computes" all unchanged;
  adapters only translate prompt+redacted-payload → provider REST → text+tokens.
  New settings `OPENAI_API_KEY` / `GEMINI_API_KEY` (empty default); a missing key
  for the selected provider raises the same loud `RuntimeError` at construction
  as Anthropic. `SHIELD_LLM_MODEL` stays the single model knob. 11 new unit tests
  (`test_llm_providers.py`) monkeypatch `httpx` — request shape, response
  parsing, token counts, missing-key raise, unimplemented-provider raise, and
  HTTP 500 → `llm_calls` status=failed — with **no** live calls. Fixture mode
  stays the default and byte-identical deterministic (D-017 untouched). Docs:
  README AI provider matrix, `docs/architecture.md` AI-flow matrix, SMOKE_TEST
  §14 rewritten provider-agnostic, DECISIONS **D-024**.
- **MessageThread stale-fetch race (T8, `67e79ad`):** `MessageThread.onSend`
  POSTed a message (201, row in DB, draft cleared) but a slow mount-time `load()`
  GET could resolve after the POST-append and `setMessages(rows)` would clobber
  the just-sent message. Fixed with the `efcbbfc` request-sequence-guard pattern
  — a `reqSeq` ref, only the newest GET writes state, and `onSend` bumps the seq
  so an in-flight mount GET is discarded. s9-messaging now green
  deterministically (previously a deterministic failure in isolation).
- **Checkpoint fixes:** checkpoint 1 (`efcbbfc`) fixed the same class of
  stale-fetch race in `CsfPlaybookPanel` breaking s7 (request-sequence guard +
  content-aware spec waiter — the pattern T8 reused); checkpoint 2 was a clean
  pass at `05121de` (full e2e green, security clean) with no fix needed.
- **Wrap-up (T7, this entry):** SMOKE_TEST §14 provider-agnostic wording
  verified landed (T6); BUILD_REPORT A06 row updated to the zero-audit state;
  CHANGELOG `[3.1.0]`; CONTEXT.md end-of-sprint snapshot.
- **Post-sprint audit hardening:** the end-of-sprint deep + security audit
  fixed three items on this branch. (1) **Security:** `GeminiProvider` now sends
  its API key via the `x-goog-api-key` header instead of a `?key=` URL query
  param — the query form leaked the key into httpx's `HTTPStatusError` message,
  which `LLMClient.invoke` persists to `llm_calls.error_message` and the logs on
  any HTTP failure. A new `test_gemini_http_error_records_failed_row` asserts the
  FAILED row and that the key is absent from `error_message`. (2) **Fail loudly:**
  `CsfPlaybookPanel`'s post-edit refresh no longer swallows a failed reload as a
  console-only unhandled rejection — errors now surface via `setError` like the
  other reload callers. (3) **Egress cleanup:** internal `__`-prefixed control
  keys (`__purpose__`) are stripped from the payload before it reaches a live
  provider (new `_egress_payload`); the misleading "real providers ignore it"
  comment is corrected. The ESLint-10 deferral now also carries a dated
  annotation on **D-018** in DECISIONS.md.

## [3.0.3] — Sprint 3 · audit correctness & honesty — 2026-07-09

Branch `fix/audit-correctness-sprint-3`. Eight tasks (T0–T7) burning down the
correctness, security, and truth-in-docs findings from the 2026-07-08 deep repo
audit (`docs/audits/2026-07-08-repo-audit.md`). All exit gates green: the full
Playwright suite (16 files / 34 tests), `pytest -m unit`, web `tsc --noEmit`,
and the newly-mandatory repo-wide prettier `--check` (lockfile-pinned 3.9.4).

- **CSF live-mode Run-AI fixed (T0, `03175f8`):** `_CSF_SCORE_PROMPT` asked the
  model for a `{subcategories:[…]}` shape the route never parsed (it reads
  `scores[]` keyed on tier + subcategory_code) — live mode silently discarded a
  compliant response. Aligned the prompt to the parser's shape and grounded the
  payload in the assessment's interview answers/evidence (mirroring ZT), with a
  loud warning when a Run-AI parses to zero changes. Fixture determinism (D-017)
  untouched; a contract test locks the schema.
- **Draft-exists guard ported to ATT&CK + ZT (T1, `4056170`):** the attack mint
  (~600 coverage rows/version) and zt mint (~87 rows) shared CSF's old
  unbounded-version bug. Both now return the open DRAFT idempotently (HTTP 200)
  and only cut v+1 after the prior draft closes; tech_debt has no equivalent
  mint. Two new contract tests; s5/s6/s11 close-then-mint for a fresh grid.
- **Auth compensating controls made honest (T2, `bc491b9`):** README/BUILD_REPORT
  claimed daily forced re-auth + 30-min idle timeout that nothing enforced. Now
  real: an `auth_time` claim rides refreshes and `/auth/refresh` returns a typed
  401 `reauth_required` past `SHIELD_FORCED_REAUTH_SECONDS` (24h default);
  refresh-token rotation via `users.active_refresh_jti` (migration 0026, C0) so a
  replayed refresh token is rejected (`refresh_reused`); dead `require_mfa` /
  `require_email_verify` flags now refuse boot instead of silently no-op'ing; web
  shows a friendly session-expired banner. See DECISIONS **D-020**.
- **Rate limiting on auth + run-AI (T3, `b48a39f`):** new `app/security/rate_limit.py`
  — fixed-window Redis counters, per-IP + per-account on login/register (checked
  before Argon2), per-client on the five run-AI endpoints. Over-limit → typed 429
  `rate_limited` (D-016) + `Retry-After`; a Redis outage fails **open** with a
  loud structlog warning (unit-tested). Redis finally earns its keep. Defaults
  are generous so the serialized e2e suite never trips.
- **Spec §15.5 export filenames (T4, `b14ccd5`):** the CSF Playbook 5-file export
  and Risk Register export bypassed `deliverable_filename()`. Both now route
  through it — e.g. `Atlas_Defense_Solutions_CSF_Playbook070926_v8_Executive.pdf`
  — carrying Company + Service + `MMDDYY` + version (v1 carries no suffix).
- **`llm_calls` tenant attribution (T5, `cea0c5a`):** added nullable
  `llm_calls.client_id` (migration 0027, batch_alter_table + FK, C0) threaded
  through all five call sites so the largest cross-assessment egress (risk
  synthesis) is finally attributable to a tenant.
- **Docs truth pass (T6, `aeac503`):** `docs/architecture.md` rewritten to the
  real system (multi-tenant, no Celery/worker — AI runs synchronously in `api`,
  Redis = rate limiting, two-layer append-only `audit_entries`, one-way redactor
  with no unredact). README phantom runbooks/terraform marked planned-not-present;
  real test matrix. DECISIONS append-only fixes: the duplicate `[3.0.0]` /
  duplicate D-015 heading resolved (Part F → **D-021**, erratum **D-022**),
  D-005/D-006 reviewer-role + release-flow supersession recorded (**D-023**).
  Zero `reviewer` hits remain in `apps/api/app` docstrings/OpenAPI summaries.
  ops/development docs de-fictionalized.
- **Loop hygiene + wrap-up (T7, this entry):** host prettier `format:check` gate
  documented in CLAUDE.md (the Sprint 2 loop shipped unformatted files CI caught);
  SMOKE_TEST §14 flagged as now-meaningful post-T0 but left unchecked (needs
  David's live key) and §10 artifact names synced to the §15.5 convention;
  CONTEXT.md end-of-sprint snapshot.

## [3.0.2] — Sprint 2 · findings burn-down — 2026-07-07

Branch `fix/findings-burndown-sprint-2`. Ten tasks (T0–T9) burning down the
defect + coverage backlog Sprint 1 surfaced, plus this docs refresh (T10). All
exit gates green: the full 16-file Playwright suite (34 tests — recorded as 32
at the time, corrected in the Sprint 3 audit), `pytest -m unit`, and web
`tsc --noEmit`.

- **Dependency bump (T0, `f580a3b`):** `next` → latest 14.2.x patch (14.2.35;
  stayed on the 14 App-Router line, no 15.x jump). `pnpm audit` clean of
  criticals; the 5 remaining high advisories are 15.x-only fixes documented in
  the commit body as no-non-breaking-fix.
- **Runtime e2e id resolution (T1, `1e6640a`):** new `e2e/helpers/ids.ts`
  (`atlasClientId` / `atlasServiceId`, per-file cached) replaces every hardcoded
  seeded UUID across 8 specs so the suite survives a re-seeded DB. Zero
  hardcoded UUIDs remain under `e2e/` (grep-enforced).
- **Fresh-stack proof + bring-up doc (T2, `64d5b95`):** `down -v` → reseed →
  full suite green on a pristine DB; `e2e/README.md` documents the canonical
  bring-up that T3's CI job automates.
- **CI e2e job (T3, `f0475ce`):** `.github/workflows/ci.yml` gains an `e2e` job
  — composed stack up, fail-loud health waits on `:8000` + web, seed, `npm ci` +
  chromium, `playwright test`, `always()` upload of report/traces, 30-min
  timeout — alongside the untouched python/web/secret-scan jobs. First real run
  is pending the review-required branch push (Dave-manual).
- **Runtime axe sweep (T4, `7603799`):** `@axe-core/playwright` + new
  `s16-axe.spec.ts` runs a WCAG A/AA sweep over public/client/admin surfaces
  (zero violations, no rule exclusions). Triage found one recurring contrast
  miss — the `--ink-tertiary` token (2.7–3.0:1) — darkened to ~4.8:1 in
  `packages/design-system/src/tokens.css`.
- **IG Core/Supporting metadata (T5, `ec59f1d`):** imported the real
  per-subcategory Core / Supporting / Alignment classification (108 codes, from
  the Working Profile reference workbook) into `app/csf/catalog.py` as additive
  metadata, threaded into `routes/csf.py` so CSF Playbook Rules 2 (Core+Primary
  floor) and 5 (Supporting/Supplemental override) finally fire. Additive/C0:
  absent codes keep safe defaults; no migration (flags computed at roll-up).
- **a11y roving tabindex + heatmap semantics (T6, `137727b`):** WAI-ARIA
  radiogroup roving tabindex on `TierPicker` / `ZtStagePicker` (arrow keys move
  focus with wrap; select stays on Space/Enter/click to avoid auto-save PATCH
  flooding); risk heatmap `tbody th` gains `scope="row"` so Chromium exposes
  rowheaders.
- **CSF draft-exists guard (T7, `efa87b8`):** `POST
/csf/services/{id}/assessments` now returns the open draft idempotently (HTTP 200) instead of minting an unbounded new version; a new v+1 is only cut once
  the prior draft closes. CSF-scoped; the attack/zt mint routes share the
  pattern and are backlogged.
- **Coverage gaps (T8, `9dbb83f`):** new `s2-management.spec.ts` drives the
  `/admin/management` UI itself (create client, approve/remove domain); `s3`
  gains verbatim CSF outcome-prompt assertions (C8). SMOKE_TEST §2 + §3-verbatim
  checked off.
- **Reserved-TLD guard (T9, `1cdfa89`):** admin add-domain route rejects
  special-use / reserved TLDs (`.test` / `.invalid` / `.localhost`) with a typed
  422 (`domain_reserved_tld`, D-016 envelope), reusing email-validator's own
  reserved-name check rather than a hand-rolled list. The web Management client
  now surfaces the typed `error.message`. See DECISIONS.md **D-019**.
- **Docs refresh (T10, this entry):** BUILD_REPORT.md + CHANGELOG.md brought to
  v3.0.x reality; SMOKE_TEST.md synced (§12 roving-tabindex note); CONTEXT.md
  end-of-sprint snapshot; DECISIONS D-018 → **D-019** renumber to clear a
  D-number collision with the unmerged `chore/dependabot-policy` branch (which
  owns D-018 for its majors-suppressed policy).

## [3.0.1] — Sprint 1 · smoke sweep — 2026-07-06

Branch `qa/smoke-sweep-sprint-1` (PR #16). A green Playwright smoke suite now
backs `SMOKE_TEST.md`, plus the runtime defects the sweep surfaced and fixed.

- 14-file / 27-test Playwright suite under `e2e/smoke/` covering SMOKE_TEST
  sections 0–15 (home, signup errors, self-assessment, tech-debt, ATT&CK, ZT,
  CSF Playbook, risk register, messaging, staleness, a11y nav, not-found,
  tenant isolation, security headers).
- **D-017 — fixture-mode AI:** deterministic offline suggestions for all five
  AI purposes (`mitre_map`, `zt_score`, `csf_score`, `extract.capabilities`,
  `risk_synthesize`) so the demo stack is fully exercisable with no provider key.
- **D-016 — typed registration errors:** `{reason, message}` envelope mapped to
  field-scoped friendly copy on the sign-up form.
- Missing ATT&CK coverage PATCH proxy route added; assorted runtime fixes the
  sweep found. Full detail in `SPRINT_1.md` and the PR #16 description.

## [3.0.0] — v2 work order (Parts A–F) — merged via PR #1

The v2 work order (migrations 0015–0025) shipped all four assessment services
end-to-end, multi-tenant consultant-led onboarding, the AI job registry behind
the single redacting egress client, and the deterministic engines (CSF Playbook
`app/csf/playbook.py`, Risk Register `app/risk/engine.py`, ZT scoring
`app/zt/scoring.py`) — "AI suggests, code computes." Part F added the hardening
pass (synchronous AI runs, dependency audits + Dependabot, cross-tenant
isolation tests, production Dockerfiles). See DECISIONS.md D-021 (Part F;
renumbered from a duplicate D-015 heading, erratum D-022) and
the granular history below.

## Earlier build history — v0.x foundation → v2 work order

The phase-by-phase log below (Phases 1–3, `v0.x`) records the original
autonomous build and the incremental v2 evolution (multi-tenant, D-015) that
the Parts A–F work order completed and PR #1 merged as `v3.0.0`. `[Unreleased]`
labels in this section are historical.

### Multi-tenant: allow many clients per deployment — 2026-05-21

- Added `client_id` to `services`, `service_requests`, `artifacts` (Alembic 0013); made `client_id` `NOT NULL` on `csf_assessments`, `csf_answers`, `zt_assessments`, `zt_answers`, `attack_assessments`, `attack_coverage` after backfill from the deployment's existing singleton client (or a placeholder `(legacy backfill)` client when business data exists but no `client` row does).
- `User.client_id` stays nullable (platform admin/reviewer = `NULL`; client-role users get a fresh client created and bound at registration). Indexed for filtering speed.
- New FastAPI dependency `current_client` resolves the active tenant per request: client-role users are pinned to `user.client_id`; admin/reviewer users pick a tenant via the `X-Client-Id` header.
- `app/tenant.py` introduces `require_*_in_tenant` helpers used by every data route (CSF, ZT, ATT&CK, tech-debt, artifacts, deliverables); cross-tenant id-based access returns 404 with no existence oracle.
- New admin endpoints: `GET/POST /admin/clients`, `GET /admin/clients/{id}`. `GET /admin/intake-queue` now optional-filters by `client_id` and shows cross-tenant rows by default.
- Frontend: added `ClientSwitcher` to the top nav for admin/reviewer roles; the selection is persisted in a `shield_active_client_id` cookie (`httpOnly`, `SameSite=Lax`) and `lib/api.ts` forwards it as `X-Client-Id` to the FastAPI backend on every proxied call. New route handler `POST /api/active-client` sets the cookie.
- See DECISIONS.md D-015 for the architectural rationale.

### Opening commit — 2026-05-19

- Repo scaffolded per Master Spec §16 and AI Prompt §8.
- Reference documents relocated to `reference-docs/` with normalized filenames (see DECISIONS.md D-013).
- Dev container configured with `appuser` + passwordless sudo per AI Prompt §3.10–§3.11.
- Docker Compose stack defined for 8 services (db, redis, minio, keycloak, mailhog, api, worker, web).
- Pre-commit hooks and CI workflow seeded per AI Prompt §5 / §8.6.
- Documentation skeleton seeded under `docs/`.
- Seven spec §17 open questions answered in DECISIONS.md (D-003 through D-009); Q5 flipped to full ATT&CK matrix per Eugene's direction.

### Phase 1 stage 1 — API skeleton (`v0.1.1`) — 2026-05-19

- FastAPI app factory with lifespan (`apps/api/app/main.py`).
- Structured JSON logging via `structlog` with merged correlation-IDs (`apps/api/app/logging.py`).
- `CorrelationIdMiddleware` reads/echoes `X-Request-ID` (validated; 1–128 chars, alnum + `-_`).
- Global exception handler returns correlation-ID-only 500 responses; stack traces never leak (Master Spec §6.3).
- `app.config.Settings` (pydantic-settings) loads every env var, refuses production with `SHIELD_REDACTION_MODE=off` or placeholder `JWT_SIGNING_SECRET`.
- SQLAlchemy 2 + Alembic wiring (`alembic.ini`, `alembic/env.py`, `script.py.mako`), shared metadata naming convention.
- `/health` liveness endpoint.
- Runtime Dockerfile under `apps/api/Dockerfile` with least-privilege `shield` user (uid 10001), no shell, no sudo (production posture per AI Prompt §3.10 note).
- Unit tests (9 passing): health, correlation-ID middleware, exception handler, config safety asserts.

### Phase 1 stage 2 — Data model + audit log (`v0.1.2`) — 2026-05-19

- ORM models for the three Phase 1 tables: `client` (singleton org), `users` (with `UserRole` enum: admin/reviewer/client), `audit_entries` (append-only) — `apps/api/app/models/`.
- Cross-dialect first Alembic migration (`alembic/versions/0001_initial_schema.py`): creates tables on both Postgres and SQLite; installs Postgres-only `audit_entries_block_mutation()` trigger function + `BEFORE UPDATE`/`BEFORE DELETE` triggers.
- Application-layer append-only guard: `SQLAlchemy` `before_flush` event listener raises `AuditEntryImmutableError` on any update or delete of an `AuditEntry`. Catches logic bugs even when running against SQLite or if the prod trigger is somehow missing.
- `app.audit.spine.audit()` is the only blessed write surface for audit rows; automatically merges the current correlation ID from the request context.
- `/ready` readiness probe that touches the DB (`SELECT 1`) and reports per-dependency status (returns 200 with `status=degraded` rather than 5xx, so load balancers get a clean signal but readiness sweeps stay green).
- Alembic env honors any `sqlalchemy.url` already set in the config (tests override it for SQLite).
- 16 unit tests passing: migration applies cleanly on SQLite; ORM round-trips a User + audit row; audit immutability fires on UPDATE and DELETE; client singleton inserts; `audit()` row carries correlation_id; everything from stage 1 still green.

### Phase 1 stage 3 — Auth backbone (`v0.1.3`) — 2026-05-19

- Argon2id password hashing tuned per OWASP Password Storage Cheat Sheet (`apps/api/app/security/password.py`).
- HS256 JWT issue + verify with typed claims (`apps/api/app/security/jwt.py`); separate access / refresh `typ` claim; `verify_token(expected_type=...)` prevents token-confusion attacks.
- Lockout bookkeeping columns added to `users` via migration `0002_user_lockout_columns.py`: `failed_login_count`, `last_failed_login_at`, `locked_until_at`. 10 failed attempts in 15 minutes locks the account (Master Spec §4.5).
- Auth routes (`apps/api/app/routes/auth.py`):
  - `POST /auth/register` — self-registration per D-004. First registrant becomes Primary POC with `admin` role; subsequent registrants are `client`.
  - `POST /auth/login` — email + password. Account-existence oracle defended (wrong-email runs a dummy Argon2 verify so timing matches wrong-password).
  - `POST /auth/refresh` — refresh token → new access + refresh pair. Refuses access tokens.
  - `POST /auth/logout` — audited.
  - `GET /auth/me` — current user.
- `current_user` FastAPI dependency: validates `Authorization: Bearer <access>` and loads the user (`apps/api/app/dependencies.py`).
- 14 new auth route tests + 13 primitive tests = 43 unit tests all passing.

### Phase 1 stage 4 — Keycloak realm (`v0.1.4`) — 2026-05-19

- `infra/keycloak/shield-realm.json` imported on `keycloak` service start (compose mounts the dir at `/opt/keycloak/data/import` and starts with `--import-realm`).
- Realm + 3 realm roles (admin / reviewer / client) + 2 clients (`shield-web` public OIDC w/ PKCE S256, `shield-api` bearer-only).
- Brute-force protection mirrors API lockout counters (10 failures, 60s/900s waits).
- SSO session idle 1800s, max 86400s — matches Master Spec §4.5.
- Bootstrap dev-admin user with temporary password (dev only).

### Phase 1 stage 5 — Next.js skeleton (`v0.1.5`) — 2026-05-19

- `apps/web` baseline: Next.js 14.2 App Router + React 18 + TS strict + Tailwind 3.4 + NextAuth 4.24.
- `next.config.mjs` ships `output: "standalone"` for slim prod image, security headers (`X-Frame-Options: DENY`, HSTS, Permissions-Policy, no `X-Powered-By`).
- NextAuth Credentials provider (`src/lib/auth/options.ts`) posts to `/auth/login` on the API and stores access + refresh tokens in the encrypted JWT session. 401/423 from the API map to `null` (sign-in failure); other errors propagate.
- Server-side `apiFetch<T>()` helper (`src/lib/api.ts`) attaches Bearer tokens, surfaces correlation IDs from `X-Request-ID`, raises `ApiError` with status + payload on non-2xx.
- Typed session augmentation in `src/types/next-auth.d.ts` exposes `session.role` and `session.accessToken`.
- Placeholder landing at `/` (real Round-6 landing arrives in stage 7).
- Smoke: `pnpm typecheck` clean; `pnpm build` succeeded — 4 routes built (`/`, `/_not-found`, `/api/auth/[...nextauth]`), 87.2 kB First Load JS shared.

### Phase 1 stage 6 — Design-system primitives (`v0.1.6`) — 2026-05-19

- New workspace package `@shield/design-system` (`packages/design-system/`).
- Round-6 tokens in `src/tokens.css` as CSS custom properties: surface, ink, border, brand navy, status palette (saturated colors reserved for status per Round-6), type scale, 4-px spacing scale, radii, soft shadows, motion tokens that collapse under `prefers-reduced-motion`.
- Tailwind preset (`src/tailwind-preset.ts`) wires the tokens to classnames.
- 8 primitives, all keyboard-accessible and WCAG-2.1-AA-targeted:
  - `Card` + sub-parts — modular, soft shadow.
  - `StatusPill` — saturated colors only here per Round-6.
  - `NumberCard` — KPI card for executive surfaces.
  - `DataTable` — sticky header, sortable columns with `aria-sort`, row click, empty-state slot.
  - `Toast` + `ToastProvider` + `useToast()` — `aria-live=polite` region, auto-dismiss.
  - `Modal` + `SlideOver` — native `<dialog>` (browser focus trap + ESC), backdrop click closes.
  - `EmptyState` — icon + title + description + action slot.
- Wired into `apps/web`: package dep, Tailwind preset, token CSS import, placeholder `/` now uses `Card` + `StatusPill`.
- Smoke: `pnpm typecheck` clean across workspace; `pnpm build` succeeded — `/` route now 8.57 kB First Load JS (up from 138 B placeholder); 4 routes, 87.1 kB shared.

### Phase 1 stage 7 — Landing + auth screens (`v0.1.7`) — 2026-05-19

- Marketing landing (`/`): `PublicHeader` + `Hero` + `ServiceGrid` (4 service cards using `Card` from `@shield/design-system`) + trust strip with `StatusPill`s + `PublicFooter`. Round-6 PUBLIC EXPERIENCE tier.
- `/sign-in`: NextAuth Credentials-backed form (`SignInForm`) wrapped in `<Suspense>` (uses `useSearchParams` for `callbackUrl`). Errors render inline; 401/423 from the API surface as "Invalid email or password" to avoid an account-existence oracle.
- `/sign-up`: form (`SignUpForm`) posting to `/api/proxy/auth/register`, which proxies to the FastAPI `/auth/register` via the server-side `apiFetch` helper. On success, immediately calls `signIn("credentials")` so the user lands in an authenticated session.
- `/api/proxy/auth/register`: thin server route that keeps API host names off the wire to the browser and maps `ApiError` → `NextResponse` with the upstream status preserved.
- Footer pages stubbed at `/accessibility`, `/privacy`, `/security` so the footer nav doesn't 404; each carries a real mailto contact for the relevant team.
- `AuthSessionProvider` (NextAuth `SessionProvider`) and `ToastProvider` wired into the root layout.
- `next.config.mjs` `typedRoutes` left OFF intentionally (requires `next build` to populate the route manifest before `tsc --noEmit`, which we run as a pre-build smoke).
- Smoke: `pnpm typecheck` clean across workspace; `pnpm build` succeeded — 9 routes total (`/`, `/_not-found`, `/sign-in`, `/sign-up`, `/accessibility`, `/privacy`, `/security`, `/api/auth/[...nextauth]`, `/api/proxy/auth/register`). First Load JS shared 87.2 kB; biggest route (`/sign-up`) at 105 kB.

### Phase 1 stage 8 — CI green (`v0.1.8`) — 2026-05-19

- All linters and formatters configured and clean across the whole tree:
  - **Python:** `ruff` (curated rule set, with TCH dropped because SQLAlchemy 2's `Mapped[uuid.UUID]` etc. need their referent types resolvable at runtime; per-file ignores for test fixtures and Alembic env), `black`, `bandit` (0 issues), `pytest -m unit` (43 passing). Targeted `# noqa` for FastAPI's `Depends(...)` default and the OAuth `token_type="bearer"` field (false positives, not credentials).
  - **Web:** `prettier --check`, `eslint`, `tsc --noEmit`, `next build` (9 routes). Added `.prettierignore` so the lockfile and `reference-docs/` are not reformatted.
- CI workflow rewritten (`.github/workflows/ci.yml`) to actually run those checks against the codebase. Three jobs: `python` (ruff, black, pytest, bandit), `web` (prettier, eslint, typecheck, build), `secret-scan` (gitleaks).
- `apps/api/app/models/user.py`: `UserRole(str, Enum)` → `UserRole(StrEnum)` (Python 3.11+ idiom; what ruff UP042 wanted).

## Phase 1 — Foundation — Complete (`v0.1.0`) — 2026-05-19

### Acceptance criteria

- [x] User can self-register, sign in. (MFA + email verification deferred per Master Spec §2 risk acceptance; columns + feature flags in place to enable in v1.x.)
- [x] Three roles distinguishable (admin / reviewer / client).
- [x] Audit log records every login (and registration, lockout, logout).
- [x] No stack trace surfaces to user under any forced error.

### Notable features shipped

- API skeleton with structured JSON logs and correlation IDs end-to-end.
- Data model for `client` (singleton), `users` (with role enum + lockout bookkeeping), `audit_entries` (append-only at two layers).
- Auth backbone: Argon2id hashing, JWT issue/verify, register/login/refresh/logout/me routes, account lockout, account-existence oracle defense.
- Keycloak realm exported and ready for v1.x OIDC federation with the same audience claim.
- Next.js 14 web app: marketing landing (Round-6 PUBLIC EXPERIENCE), sign-in + sign-up, NextAuth Credentials provider, security headers, footer stub pages.
- `@shield/design-system` package: Round-6 tokens, Tailwind preset, 8 keyboard-accessible primitives (Card, StatusPill, NumberCard, DataTable, Toast, Modal, SlideOver, EmptyState).
- CI green across the whole tree: ruff, black, bandit, pytest, prettier, eslint, tsc, next build.

### Security review (OWASP Top 10) — see BUILD_REPORT.md for full matrix

- A01 Access Control: PARTIAL (authn done; role-based route guards in Phase 2)
- A02 Cryptographic Failures: PASS
- A03 Injection: PASS
- A04 Insecure Design: PASS
- A05 Misconfiguration: PASS
- A06 Vulnerable Components: PARTIAL (pinned versions; audit hooks in Phase 6)
- A07 Auth Failures: PASS WITH NOTES (MFA deferred per spec)
- A08 Software Integrity: PASS
- A09 Logging and Monitoring: PASS
- A10 SSRF: PASS

### What's stubbed or deferred

- MFA enrollment + email verification — feature-flagged off; columns and feature flags ready.
- Postgres audit-trigger integration smoke — waits on Docker availability in the dev container.
- axe-core / Playwright accessibility CI job — deferred to Phase 6 hardening; WCAG 2.1 AA is implemented at the component layer.
- Redactor module (`apps/api/app/ai/redact.py`) — lands in Phase 3 with the first AI-extraction use case (Tech Debt capability list).

### Known issues

- None blocking Phase 2.

### How to try it

1. `cp .env.example .env`; paste `ANTHROPIC_API_KEY` (only needed when `SHIELD_LLM_MODE=live`); generate `NEXTAUTH_SECRET` via `openssl rand -hex 32`.
2. `docker compose up -d db redis minio keycloak mailhog && docker compose up -d --build api worker`.
3. `docker compose run --service-ports --rm web bash scripts/dev-web.sh`.
4. Open http://localhost:3000.

### Decisions logged this phase

- D-001 through D-014 (opening commit). No new decisions added during stages 1–9 beyond DECISIONS.md entries already on `main`.

## [Unreleased — Phase 2 in progress]

### Phase 2 stage 1 — Intake data model (`v0.2.1`) — 2026-05-19

- New `ServiceRequest` ORM model (`apps/api/app/models/service_request.py`) matching Master Spec §11: `service_type`, `requested_by`, `requested_at`, `notes`, `deadline`, `fulfilled_service_id`, `declined_at`, `declined_reason`.
- New `ServiceType(StrEnum)`: `tech_debt`, `zero_trust_cisa`, `zero_trust_dod`, `nist_csf`, `attack_coverage`, `consultation`. The fifth-option "I'm not sure" intake path maps to `CONSULTATION`.
- `Client.intake_completed_at` column added so the admin queue can surface new leads with a real timestamp (Phase 2 acceptance).
- `Client.service_interests` switched to `ARRAY(String(32)).with_variant(JSONB, "sqlite")` for SQLite test compatibility.
- Migration `0003_intake.py`: adds the column, creates `service_requests` + indexes on `(requested_at)` and `(service_type)`.
- 5 new unit tests (48 total).

### Phase 2 stage 2 — Intake API routes (`v0.2.2`) — 2026-05-19

- Three routes on the FastAPI side back the wizard (`apps/api/app/routes/intake.py`):
  - `GET /intake` — current state; lazily creates the singleton client placeholder so the wizard always has a target.
  - `PATCH /intake` — auto-save target on every blur. Accepts a sparse body; only set-and-non-None fields are applied (avoids overwriting NOT-NULL columns like `users.timezone` with None).
  - `POST /intake/submit` — finalizes submission: validates a real legal name, writes `ServiceRequest` rows (dedupes by service_type), stamps `client.intake_completed_at = utcnow()`, and writes a `client.intake_submitted` audit row whose `details.services` are sorted for stable diffing.
- `IntakePatchRequest` / `IntakeSubmitRequest` / `IntakeStateResponse` Pydantic schemas (`apps/api/app/schemas/intake.py`). `IntakeSubmitRequest.service_requests` enforces `min_length=1`; `consultation` is a valid first pick so the "I'm not sure" path doesn't get blocked.
- 7 new route tests (55 total): GET creates the singleton, PATCH writes partial updates, submit writes service_requests + audit row, submit rejects empty service list, submit rejects the pending placeholder legal name, submit dedupes duplicates, all three routes return 401 when unauthenticated.

### Phase 2 stage 3 — Web intake wizard skeleton (`v0.2.3`) — 2026-05-19

- `/intake` route gated by `getServerSession()` in `app/intake/layout.tsx`; unauthenticated users are redirected to `/sign-in?callbackUrl=/intake`.
- `IntakeWizard` client component manages step state (`services` → `organization` → `contact` → `systems` → `notes` → `review`) and pulls the current intake from `/api/proxy/intake` on mount. If the intake is already submitted, jumps to `review` so the user can verify what's on file instead of re-starting.
- `IntakeProgress` renders a 6-step indicator with `aria-current="step"`, success-tone tick marks for completed steps, focus-tone for the current step, and ink-tertiary for upcoming steps.
- `SaveStatus` reads a discriminated `SaveState` (`idle | saving | saved | error`) and renders an `aria-live=polite` indicator with "Saved X seconds/minutes ago" that updates once a second.
- Server-side proxy routes (`/api/proxy/intake`, `/api/proxy/intake/submit`) attach the session's access token as a Bearer header and forward to FastAPI; ApiError shapes pass through with the upstream status preserved.
- Client-side wrappers (`lib/intake/client.ts`) cover `fetchIntake`, `patchIntake`, `submitIntake` with typed return values; per-step forms in stage 4 call these.
- TS types in `lib/intake/types.ts` mirror `apps/api/app/schemas/intake.py` 1:1; `SERVICE_LABELS` gives the plain-English copy the wizard renders (Master Spec §15 Phase 2: "All copy in plain English").
- Smoke: typecheck clean, eslint 0 warnings, prettier clean, `next build` clean — now 12 routes total (3 new: `/intake`, `/api/proxy/intake`, `/api/proxy/intake/submit`). `/intake` is server-rendered on demand (dynamic) because it reads the session at request time.

### Phase 2 stage 4 — Per-step form fields + real auto-save (`v0.2.4`) — 2026-05-19

- `useIntakeAutoSave` hook wraps `patchIntake` with a discriminated `SaveState` and surfaces the updated intake state back to the wizard via an `onUpdate` callback.
- Six step components (`apps/web/src/components/intake/steps/Step*.tsx`):
  - **Step 1 — Services:** card-grid of the 6 service types with USWDS-style checkboxes. Picking "I'm not sure" is exclusive (clears the four real services); picking a real service clears "I'm not sure". Each card is keyboard-focusable; descriptions are wired via `aria-describedby`.
  - **Step 2 — Organization:** legal_name (required) + dba_name + website + size_band (`<select>`) + industry, plus 6-field address block. Every input is wired to PATCH on blur.
  - **Step 3 — Contact:** display_name + title + phone + timezone for the user. Email shown read-only with hint copy (locked to the signed-in account).
  - **Step 4 — Systems:** single textarea writing to `client.prompting_context`. Real systems table comes in Phase 4 with the CSF assessment.
  - **Step 5 — Notes:** per-picked-service notes + optional target deadline. Lives in wizard local state until submit (the API only writes `service_requests` at POST `/intake/submit`).
  - **Step 6 — Review:** read-only summary (organization / services / context). Submit button disabled unless legal_name is real and at least one service is picked. Pre-existing `intake_completed_at` surfaces as "submitted on …; you can re-submit" copy.
- New `Field` component (`apps/web/src/components/intake/Field.tsx`) wires label / hint / error with `aria-describedby` and `aria-invalid` per USWDS accessibility patterns. Exports shared Tailwind class strings (`inputClasses`, `textareaClasses`, `selectClasses`) so every input renders identically.
- `IntakeWizard` rewires the placeholder step renderer to dispatch to the real step components; submit handler bundles client state + service_inputs into `POST /intake/submit` and reflects the response.
- Smoke: typecheck clean, ESLint 0 warnings, prettier clean, `next build` clean — `/intake` route now 8.0 kB (up from 3.56 kB), 112 kB First Load JS. 12 routes total; no schema changes so the 55 API unit tests still pass.

### Phase 2 stage 5 — Section-tabbed questionnaire renderer (`v0.2.5`) — 2026-05-19

- New `@/components/questionnaire` module — the shared rendering primitive that Phases 4 (CSF) and 5 (ATT&CK with the full ~600-technique matrix per D-007) will both consume. Master Spec §15 Phase 2: "Section-tabbed questionnaire renderer (shared component for CSF, ZT, future frameworks)."
- **`QuestionnaireDefinition` shape:** JSON-friendly (so it can ship as static assets in `packages/csf-data` / `packages/attack-data` / `packages/zt-data`). Sections contain questions; each question carries a stable id used as the key in a flat `Responses` map (matches the `questionnaire_responses` table shape from Master Spec §11).
- **Eight question primitives** cover the v1 surface: `short_text`, `long_text`, `number` (with optional `unit`), `score_0_2` (named-label radio group for CSF 5-dimension scoring + ATT&CK coverage), `choice` (single-select), `multi` (multi-checkbox), `yes_no`, `tristate` (yes/no/n-a). Specialized CSF grid composes these in Phase 4.
- **`SectionTabs`** has full WAI-ARIA APG tab semantics: `role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls`, roving `tabIndex`, plus full keyboard nav (ArrowLeft / ArrowRight / Home / End) with manual activation. Per-section completion chips drive a small progress percentage.
- **`QuestionnaireRenderer`** renders the active section as a `role="tabpanel"` with `aria-labelledby` wired to the active tab. Computes `sectionProgress` via `useMemo` from the responses map — Phase 4 reuses this for the "needs answers" badge on the admin queue.
- **Dev preview** at `/dev/questionnaire-preview` exercises every question type end-to-end with a hand-rolled definition (3 sections, 10 questions). Unlisted route; the page header makes the dev-only nature obvious.
- Smoke: typecheck clean, ESLint 0 warnings, prettier clean, `next build` clean. 13 routes total (1 new: `/dev/questionnaire-preview`).

### Phase 2 stage 6 — Document upload + redaction disclosure (`v0.2.6`) — 2026-05-19

- Storage abstraction (`apps/api/app/storage/`): `StorageBackend` Protocol with `LocalFilesystemStorage` for tests/dev and `S3Storage` for production (KMS-encrypted, boto3 imported lazily).
- `Artifact` model + migration `0004_artifacts.py` matching Master Spec §11 (origin enum, indexes on uploaded_at / uploaded_by / sha256).
- Three API routes: `POST /artifacts` (multipart, MIME allowlist, 50 MB cap, filename sanitization, sha256 + audit row), `GET /artifacts` (current user's uploads), `GET /artifacts/{id}` (404 for unknown id or wrong owner).
- Server-side multipart proxy `/api/proxy/artifacts` forwards FormData with the session bearer; browser never sees the API host name.
- Web components: `Dropzone` (drag/drop + click + keyboard, multi-file, per-file status with `aria-label`), `RedactionDisclosure` (plain-English copy of §12 policy), `EmptyArtifactsHint`.
- Wired into intake **Step 5** above the per-service notes: redaction disclosure → dropzone → live upload list (refreshes on mount via `GET /artifacts`).
- 7 new pytest tests (62 total): upload writes row + storage object + audit; rejects unknown MIME (415); rejects empty (422); sanitizes path-traversal filenames; list returns own only; GET unknown id 404; routes 401 without auth.
- Smoke: pytest 62/62 green, ruff + black + bandit clean, prettier + ESLint + tsc clean, `next build` clean. 14 routes total.

### Phase 2 stage 7 — Admin queue (`v0.2.7`) — 2026-05-19

- `require_role(*allowed)` FastAPI dependency factory (`apps/api/app/dependencies.py`) returns 403 (not 401) when authenticated callers lack the required role — matches RFC 7231 and lets clients distinguish "sign in" from "you're signed in but not allowed".
- `GET /admin/intake-queue` (`apps/api/app/routes/admin.py`) returns the singleton client (with `intake_completed_at`), all service requests (with requester user summary joined in), all artifacts, and the total user count. Per Master Spec §15 Phase 2 acceptance: the admin queue surfaces the new-lead timestamp and reflects exactly what the client entered.
- `AdminUserSummary` schema redacts password hash + lockout state but keeps the identity bits the consultant needs (email, display name, title, role, last_login_at).
- Server-side proxy `/api/proxy/admin/intake-queue` attaches the session bearer.
- `/admin/queue` page gated by `app/admin/layout.tsx`: redirects to `/sign-in?callbackUrl=/admin/queue` if unauthenticated; renders a "Not authorized" landing if signed in as a non-admin (session intact so navigation elsewhere works).
- `IntakeQueue` component (`apps/web/src/components/admin/IntakeQueue.tsx`) renders the organization panel, service requests list (with `Open`/`Fulfilled`/`Declined` `StatusPill` per row + the requester's name/email/title), and uploaded documents. Empty states for no-intake-yet and no-service-requests.
- `PublicHeader` is now an async Server Component: shows "Intake" + "Admin queue" (admin-only) when signed in, sign-in/get-started CTAs when not. Surfaces the signed-in user's email.
- 4 new pytest tests (66 total): empty queue, reflects submitted intake with requester summary, client role gets 403, unauthenticated gets 401.
- Smoke: pytest 66/66 green, ruff + black + bandit clean, prettier + ESLint + tsc clean, `next build` clean. 16 routes total (2 new: `/admin/queue`, `/api/proxy/admin/intake-queue`).

### Phase 2 stage 8 — Notifications + Phase 2 acceptance gate (`v0.2.8` / `v0.2.0`) — 2026-05-19

- `Notification` model + migration `0005_notifications.py` matching Master Spec §11: user_id, event_type, title, body, link, created_at, read_at. Indexes on `(user_id, created_at)` and `(user_id, read_at)` so per-user list + unread count both stay index-backed.
- `notify(...)` and `notify_role(role, ...)` helpers (`apps/api/app/notifications/spine.py`) — blessed write surface, mirrors the audit-spine pattern. `notify_role` fans out one row per user with the given role.
- Three notification routes: `GET /notifications` (newest first, capped at 50, returns `unread_count`); `POST /notifications/{id}/read` (404 for unknown id or wrong owner); `POST /notifications/read-all`.
- **Intake submit now fans out a `intake.submitted` admin notification** with `link=/admin/queue` (AI Prompt §6.12: bell links must resolve to a working page). Body includes the client legal name + sorted services list.
- 6 new pytest tests (72 total): intake submit writes admin notification; submitter (client role) does NOT get a copy; `GET /notifications` reflects unread count; mark-read updates `read_at` and clears unread count; cross-user mark-read returns 404; all routes 401 without auth.

## Phase 2 — Intake — Complete (`v0.2.0`) — 2026-05-19

### Acceptance criteria

- [x] A new client can complete intake end-to-end without internal vocabulary, raw JSON, or stack traces.
- [x] Submitting intake reflects correctly in the admin queue with the new-lead timestamp.
- [x] All intake data round-trips correctly: client enters X, admin reads X.

### Notable features shipped

- Self-service 6-step intake wizard with auto-save on every blur and a live "Saved Xs ago" indicator.
- Drag-and-drop document upload with up-front redaction disclosure (the user-facing copy of the Master Spec §12 policy).
- Generic section-tabbed questionnaire renderer with full WAI-ARIA tab semantics — load-bearing for Phases 4 and 5.
- Admin queue at `/admin/queue` with role-based authz; reflects the singleton client + every service request (with requester user joined in) + every uploaded document.
- Admin notification fan-out on intake submit, with link pointing at `/admin/queue`.
- 72 unit tests across the API; web typecheck + lint + prettier + next build all green.

### Security review (OWASP Top 10) — full matrix in BUILD_REPORT.md

- A01 Access Control: PASS (role-based guards at route + layout layer)
- A02 Cryptographic Failures: PASS
- A03 Injection: PASS
- A04 Insecure Design: PASS (audit immutability, MIME allowlist, redaction disclosure)
- A05 Misconfiguration: PASS
- A06 Vulnerable Components: PARTIAL (Dependabot in Phase 6)
- A07 Auth Failures: PASS WITH NOTES (MFA still deferred per spec)
- A08 Software & Data Integrity: PASS (sha256 captured + audited on upload)
- A09 Logging & Monitoring: PASS (audit + notification fan-out)
- A10 SSRF: PASS

### What's stubbed or deferred

- Notification bell UI in the header — API + data layer shipped; visual surfacing is a small follow-up.
- Postgres audit-trigger integration smoke — waits on Docker availability.
- The redactor module — lands in Phase 3 with the first AI extraction (Tech Debt capability list).

### Known issues

- None blocking Phase 3.

### How to try it

A SQLite-only dev demo is documented in BUILD_REPORT.md ("Recommended next steps"). For the full stack: `cp .env.example .env`, paste `ANTHROPIC_API_KEY`, generate `NEXTAUTH_SECRET`, then `docker compose up`.

### Decisions logged this phase

- No new DECISIONS.md entries beyond stages tracked in this CHANGELOG; the seven §17 open questions were already settled in Phase 1's D-003 through D-009.

## [Unreleased — Phase 3 in progress]

### Phase 3 stage 1 — Tech Debt data model (`v0.3.1`) — 2026-05-19

- New ORM models matching Master Spec §11 verbatim:
  - **`Service`** — the workspace that opens when an admin promotes a `ServiceRequest` to live work. Carries `kind` (StrEnum: `tech_debt` / `zero_trust_cisa` / `zero_trust_dod` / `nist_csf` / `attack_coverage`), `status` (`draft`/`in_progress`/`review`/`released`/`archived`), `title`, `source_request_id` (FK back to the originating request), `opened_by`, `released_at`. Other service kinds are listed in the enum so Phase 4 + 5 don't need a schema change.
  - **`CapabilityList`** — versioned per service (unique constraint on `(service_id, version)`); `draft` / `approved` / `released` status.
  - **`CapabilityItem`** — `name` / `vendor` / `category` / `function` / `annual_cost_usd` (Numeric(14,2)) / `license_count` / `notes` / `confidence_pct` (0-100, AI-set; cleared on human edit) / `source_artifact_id` (FK to the uploaded artifact the item was extracted from).
  - **`Deliverable`** — `service_id`, `title`, `summary`, `version`, `pdf_artifact_id`, `xlsx_artifact_id`, `finalized_at`/`finalized_by`, `released_to_client_at`, `superseded_by` (self-FK for re-releases).
- Migration `0006_tech_debt.py`: creates all four tables + indexes (`services.kind`, `services.status`, `capability_items.capability_list_id`, `deliverables.service_id`, `deliverables.released_to_client_at`).
- 3 new pytest tests (75 total): migration creates Phase 3 tables; full round-trip through Service → CapabilityList → CapabilityItem → Deliverable with realistic financial data; unique-constraint on `(service_id, version)` enforced.

### Phase 3 stage 2 — PII redactor (`v0.3.2`) — 2026-05-19

- **`app.ai.redact`** module — the §12 security boundary in front of every LLM call. Intentionally pure (no I/O, no DB, no clock) so it can be reviewed line-by-line in an OWASP audit.
- Two public functions: `redact_for_ai(text, *, mode, client_org_name, name_hints)` for strings and `redact_payload(obj, ...)` that walks dicts/lists/tuples recursively. Both return `(cleaned, removed_counts)` — the counts dict (e.g. `{"email": 3, "phone": 1}`) is what `artifact_redactions.removed_items` (Master Spec §11) and the `llm_calls` audit row both record. **Counts only, never payload content.**
- Ten categories redacted in `strict` mode (this entry said "Eight" and then listed ten; corrected 2026-08-25 while fixing #130, which found the same miscount repeated in three other places): emails, phones (US + international, 10–20 char digit-run-with-separators), SSNs, EINs, CAGE codes (introducer-keyword form only), govcon contract numbers (e.g. `W91QUZ-23-C-0001`), street addresses + Suite/Apt/PO Box, signature blocks (everything from `Sincerely,` / `Regards,` / `V/R` etc. onwards), name hints supplied by the caller, and the client's org name.
- `standard` mode keeps addresses + org name (when the prompt explicitly needs the org context).
- `off` mode is pass-through. The runtime config refuses it outside development via `Settings.assert_safe_for_runtime()` (Phase 1); tests use it to compare raw-vs-redacted paths.
- Order of operations matters: signature block → email → SSN → EIN → contract → phone → CAGE → names → addresses → org. SSN runs before phone so `123-45-6789` is replaced with `[SSN]` before the phone pass sees it.
- 23 new pytest tests (98 total): every PII pattern + every mode + nested-payload walk + non-string-scalar preservation.

### Phase 3 stage 3 — AI client + `llm_calls` audit (`v0.3.3`) — 2026-05-19

- `app.ai.llm` module — the only path that calls an external AI provider. `LLMClient.invoke(...)` redacts the payload, opens an `llm_calls` row with `status=running` before the provider call, calls the provider, then finalizes with `status=completed | failed` + token counts + duration + `redacted_counts`.
- Two provider implementations: `FixtureProvider` (canned responses keyed by `purpose`; raises on unregistered purpose), `AnthropicProvider` (lazy SDK import; raises if `ANTHROPIC_API_KEY` is empty).
- `LLMCall` model + migration `0007_llm_calls.py` matching Master Spec §11 verbatim. `redacted_counts` is JSONB on Postgres / JSON on SQLite — counts only, never payload content (§12.1). `correlation_id` auto-populates from the request-scoped contextvar.
- 5 new pytest tests (103 total): provider sees the **redacted** payload (raw email/SSN never reach it); completed row carries token counts; failed row carries `error_message` + `duration_ms`; dict keys (field names) preserved through redaction; unregistered fixture purpose raises a loud `KeyError`; correlation_id threaded from request context.

### Phase 3 stage 4 — Capability list ingest (`v0.3.4`) — 2026-05-19

- **First real LLM extraction.** Admin uploads a CSV/XLSX inventory; the route runs it through `LLMClient.invoke(purpose="extract.capabilities")` with strict redaction; the response becomes a versioned `CapabilityList` + `CapabilityItem` rows.
- `app.tech_debt.parsers` parses CSV (stdlib) and XLSX (openpyxl, lazy import) into row-dicts. Header row becomes the keys; up to 500 rows ship; a sentinel `__truncated__` marker rides at the end if the input was longer.
- `app.tech_debt.extract` builds the prompt (versioned `PROMPT_VERSION="v1"` so future prompt-shape changes don't silently regress past extractions; the version is recorded on the `llm_calls` row), assembles `{rows, context}` payload, and parses the JSON response. Response parser handles the common "LLM wrapped JSON in prose" case by stripping to the outermost `{...}`.
- Name hints + client org name are pulled from the deployment (every user's display name + email-local-part as name hints; the singleton client's legal name as `[CLIENT]`) so the redactor uses real deployment data, not hardcoded fixtures.
- Three routes (`/tech-debt/services`, `/tech-debt/services/{id}/capability-lists/extract`, `/tech-debt/services/{id}/capability-lists/latest`) — all admin-only via `require_role(UserRole.ADMIN)`.
- Versioning: each extract creates `version = max + 1`; the unique constraint from stage 1's migration enforces it.
- Bad-JSON path: extractor raises `ValueError`, route maps to **502 Bad Gateway** (the `llm_calls` row is already written, so the operator can debug; client error code is wrong here because it's the upstream provider that misbehaved).
- 8 new pytest tests (111 total): admin can open service; client role gets 403; full extract flow with PII in CSV → redacted payload reaches the FixtureProvider (verified end-to-end); subsequent extracts version incrementally; unsupported artifact MIME (PDF) returns 415; non-existent service returns 404; bad JSON from the LLM returns 502; latest-list is admin-only until release.
- Demo DB migrated to head; `openpyxl` added to the API dev environment.

### Phase 3 stage 5 — Editable extraction table (`v0.3.5`) — 2026-05-19

- Two new API routes:
  - `PATCH /tech-debt/capability-items/{id}` — partial-update; clears `confidence_pct` on every human edit (the row is no longer an AI guess); rejects edits on items in a released list (409); audit row `capability_item.edited` records the list of fields touched.
  - `POST /tech-debt/capability-lists/{id}/approve` — flips `status: draft → approved`, stamps `approved_at` + `approved_by`, audits.
- New web workspace at `/admin/services/{id}/tech-debt` (admin-gated by the existing `/admin` layout):
  - Inventory upload via the existing `Dropzone` + `RedactionDisclosure` (Phase 2 stage 6) — drop a CSV/XLSX, the workspace auto-runs `POST /tech-debt/services/{id}/capability-lists/extract`.
  - `EditableCapabilityTable` renders the AI-extracted rows as a **real editable table** (AI Prompt §6.2: no raw JSON in user-facing UI). Each cell auto-saves on blur via `PATCH`; per-row status pill flips to "Saving…" → "Saved" or "Save failed". Low-confidence rows (`confidence_pct < 70`) get a warning row tint.
  - Confidence pill per row: `Human-curated` (success, after edit) | `AI 85%+` (info) | `AI 70–84%` (warning) | `AI <70%` (neutral with warning row tint).
  - Header strip shows total cost, low-confidence count, and the **Approve list** button (disabled if already approved/released).
  - Released lists render read-only.
- Six new server-side proxies (`/api/proxy/tech-debt/*`) consolidated through a shared `_proxy.ts` helper that handles bearer attachment + `ApiError` mapping. Adding a new tech-debt proxy is now a 4-line file.
- 6 new pytest tests (117 total): patch clears confidence + persists edits, patch rejects empty body 422, patch 404 for unknown item, patch rejects client role 403, approve writes status + actor, approve 404 for unknown list.
