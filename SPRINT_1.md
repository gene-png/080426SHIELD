# SPRINT 1 — Smoke-test automation sweep + defect burn-down

_Branch: `qa/smoke-sweep-sprint-1` (contains the seed fix from
`fix/seed-demo-a1-drift`). Queue: `.claude/sprint-queue.json`. Driver:
`/loop-sprint-cron`. Created 2026-07-02._

## Sprint goal

Every automatable section of `SMOKE_TEST.md` becomes a committed, passing
Playwright spec under `e2e/`, and the defects already found are fixed. At sprint
end, the only unchecked SMOKE_TEST items are the human-only ones (§10 document
eyeball, §14 live AI).

## Environment facts the loop must know

- Stack runs via Docker Compose; bring-up is assumed already done (containers
  healthy). If the stack is down: `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"`
  then `docker compose up -d` from repo root and wait for
  `http://localhost:8000/health`.
- Docker CLI is NOT on Git Bash PATH — always export the PATH above first.
- API code is bind-mounted into the api container (live reload); web likewise.
- Backend tests: `docker compose exec -T api pytest -m unit -q`.
- Web typecheck: `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`.
- e2e (after T0): host-run — `cd e2e && npx playwright test` (Chromium already
  installed on this machine; base URL http://localhost:3000).
- Demo logins: admin `admin@kentro.example` / `DemoPass!2026`; client
  `client@atlas.example` / `DemoPass!2026`. Extra users created by specs must use
  unique emails per run (timestamp suffix) to avoid duplicate-email collisions.
- LLM is in `fixture` mode — Run-AI buttons work offline and are deterministic.
- PowerShell is deny-ruled in this Claude Code setup; use Git Bash syntax.

## Tasks

### T0 — Scaffold the e2e harness

`e2e/` is EMPTY despite README claims. Create: `e2e/package.json` (playwright
^1.61 devDependency, scripts: `test` = `playwright test`), `e2e/playwright.config.ts`
(baseURL `http://localhost:3000`, chromium only, `fullyParallel: false` — specs
share one seeded database; trace on-first-retry), `e2e/helpers/auth.ts` (signIn
helper: fill `input[type=email]`/`input[type=password]` on `/sign-in`, click
submit, `waitForURL` away from sign-in; register helper for `/sign-up` — first
form input is Full name), and `e2e/smoke/s0-home.spec.ts` (home renders with
no console errors; admin sign-in lands authenticated: nav shows "Sign out").
Run `npm install` inside `e2e/`. Note: `node_modules/` is already gitignored
repo-wide; commit `e2e/package-lock.json`.

### T1 — Fix stale marketing + sign-up copy (defects 1, 2)

In `apps/web/src/app/page.tsx` (marketing home): remove/replace the
"reviewer audit walk" INCLUDES line (reviewer role removed, A3) — check
`reference-docs/SHIELDv2_Master_Spec.txt` for the sanctioned service blurb; and
rename the "Attack Surface Mapping" card to the spec name for the ATT&CK service
(spec calls it MITRE ATT&CK Coverage Mapping — grep the spec to confirm exact
form). In the sign-up page component: replace the "first registrant ... Primary
POC" helper with B1-accurate copy (first user on a fresh deployment becomes the
admin; everyone else needs an email domain approved by their admin). Grep all of
`apps/web/src` for remaining `reviewer` occurrences (case-insensitive) outside
tests and remove them. Update `e2e/smoke/s0-home.spec.ts` to assert the absence
of "reviewer" on the home page.

### T2 — Seed approves the demo client's email domain (defect 3)

In `apps/api/scripts/seed_demo.py`: when seeding the Atlas client, also create
the approved `client_domain` row for `atlas.example` (idempotent — skip if
present; mirror how the admin route creates it, see the B2 admin management
route/model). Verify by re-running the seed twice (no error, no duplicate) and
registering a throwaway `@atlas.example` user via the API or UI.

### T3 — Custom not-found page (defect 5)

Add `apps/web/src/app/not-found.tsx`: top-nav shell consistent with the app,
"Page not found" message, onward links (Home, My Assessments, Sign in). Spec
`e2e/smoke/s12-notfound.spec.ts`: visiting `/definitely-not-a-page` renders the
custom copy and at least one onward link (no bare Next.js default 404).

### T4 — Friendly duplicate-email registration error (defect 4)

Reproduce: register the same email twice via `/sign-up` — second attempt shows
raw "Request validation failed." Find where the web sign-up form maps API errors
and where the API raises on duplicate email; surface a human message ("An
account with this email already exists. Sign in instead.") without leaking
whether an email exists more broadly than the product already does (check how
B1 rejection copy handles this — domain rejection already discloses domain
non-approval, so a duplicate-email message is consistent disclosure here; if the
API deliberately returns a generic 400 for enumeration resistance, instead map
it to "That registration could not be completed" + sign-in link and note the
decision in DECISIONS.md). Spec: `e2e/smoke/s1-signup-errors.spec.ts` covering
unapproved-domain rejection copy AND duplicate-email copy.

### T5 — §3 client self-assessment specs

`e2e/smoke/s3-selfassessment.spec.ts`, as a fresh unique `@atlas.example` user
(or `client@atlas.example`): client entry is `/assessments` (NOT
`/self-assessment` — that bare path 404s; the real route is
`/self-assessment/[serviceId]`). Assert: intake/assessment pages say
"assessment" never "engagement"; open the CSF self-assessment, answer 2–3
questions, save-and-exit, reopen, answers persisted; open ZT self-assessment,
DoD scale shows exactly 3 levels (A4); submit moves status to
submitted/under-review.

### T6 — §4–§6 service workspace specs (admin)

`e2e/smoke/s4-techdebt.spec.ts`: tech-debt dashboard row shows capabilities
count, annual cost, categories, to-consolidate/cut, low-confidence counts (seed
provides data); editing a capability cell clears its AI-confidence badge.
`e2e/smoke/s5-attack.spec.ts`: matrix + heatmap render; Run AI (fixture) reports
"Updated N fields across M techniques"; technique panel shows D/P/R chips +
rationale; Lock a technique, Run AI again, locked row unchanged and absent from
what-changed (C2).
`e2e/smoke/s6-zt.spec.ts`: questionnaire renders by pillar; set current/target;
Run AI applies suggestions with DoD clamped to <= 3; gap list reflects targets;
12-month roadmap card groups gaps by month.

### T7 — §7–§8 CSF Playbook + Risk Register specs (admin)

`e2e/smoke/s7-csf-playbook.spec.ts`: Seed Working Profiles (~106 subcats x
tiers); Run AI drafts dimensions + narrative; dimension editor: set the five
0/1/2 scores + Evidence toggle, total/level/cap update live, no-evidence caps
level <= 2; Enterprise roll-up shows tier levels, enterprise level, rule #,
target, gap, P1/P2/P3; Export produces 5 files (XLSX, exec PDF/Word, full
PDF/Word) with working download links (HTTP 200, correct content-type; save to
`e2e/artifacts/` for David's §10 eyeball).
`e2e/smoke/s8-risk-register.spec.ts`: for a client with only ATT&CK the register
is locked and lists what's missing; with CSF or ZT added the gate unlocks;
Generate produces entries with code-derived tiers (assert a known combo, e.g.
High x Catastrophic = Critical), KPI cards + 5x5 heatmap render, cited links
only reference the client's own assessments; Regenerate bumps version; exports
download (save to `e2e/artifacts/`).

### T8 — §9 messaging + §11 staleness specs

`e2e/smoke/s9-messaging.spec.ts`: client posts on their self-assessment thread,
admin sees it in the workspace thread and in `/admin/messages` inbox with unread
badge; admin reply appears for client; opening a thread clears its unread count.
`e2e/smoke/s11-staleness.spec.ts`: after a Run-AI on any service the workspace
shows the "regenerate to refresh" nudge (C3); finalize/export clears it on
reload.

### T9 — §12 a11y/navigation + §13 tenant isolation specs

`e2e/smoke/s12-a11y-nav.spec.ts`: on `/account`, `/messages`, `/assessments` and
one admin page: first Tab lands on "Skip to content"; activating it moves focus
to `#main-content`; every page shows top-nav; spot-check keyboard operability of
one workspace (radios/selects/buttons reachable).
`e2e/smoke/s13-isolation.spec.ts`: register `bob@beacon.test` (Beacon Labs —
domain already approved in the DB from the 2026-07-02 session; if missing,
create client+domain via admin UI in the spec setup); as a client, admin URLs
show not-authorized; as admin switched to Beacon, opening an Atlas service URL
404s rather than leaking data; Beacon client never sees Atlas data on any page.

### T10 — §15 headers spec + checklist/doc sync

`e2e/smoke/s15-headers.spec.ts`: response headers on `/` include CSP,
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
`Strict-Transport-Security`, `Permissions-Policy`; and no CSP-blocked resource
errors in the console on the signed-in dashboard. Then: check off every
SMOKE_TEST.md item covered by a green spec (annotate each checked item with its
spec file); leave §10/§14 and anything red unchecked; update README's stale
worker + e2e claims; overwrite CONTEXT.md with the end-of-sprint snapshot.

## Definition of done

- All specs green on a fresh `docker compose up` + seeded stack, twice in a row.
- `pytest -m unit` and web tsc still green.
- SMOKE_TEST.md accurately reflects automated coverage.
- Export artifacts collected in `e2e/artifacts/` for David's §10 pass.
- Every commit conventional, scoped to its task's files.

## Explicitly out of scope (needs-David or Sprint 2+)

- §10 document eyeballing, §14 live-AI run.
- Pushing branches / opening PRs (blocked on collaborator access).
- CI wiring of the e2e suite; runtime axe/Pa11y (Sprint 2).
- BUILD_REPORT.md / CHANGELOG.md rewrite (Sprint 2 docs pass).
