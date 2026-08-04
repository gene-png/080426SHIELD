# SPRINT 2 — Findings burn-down + CI hardening

_Branch: `fix/findings-burndown-sprint-2` (branch from `qa/smoke-sweep-sprint-1`
until that PR merges; rebase onto `main` after merge). Queue:
`.claude/sprint-queue.sprint-2.json` (rename to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron`. Created 2026-07-03. NOT YET LAUNCHED._

## Sprint goal

Everything Sprint 1's smoke sweep surfaced gets fixed, the e2e suite survives a
from-scratch reseed, and CI runs it. Concretely: the `next@14.2.15` CRITICAL
advisory is resolved, the eight specs with hardcoded seeded UUIDs resolve ids at
runtime, a GitHub Actions job runs the Playwright suite (plus runtime axe) against
a composed stack, the CSF Playbook's Rules 2/5 stop using safe-default IG
metadata, and the small-fix backlog (reserved TLDs, roving tabindex, scope=row,
CSF draft guard, coverage gaps, stale docs) is burned down.

## Prerequisites / launch checklist (human)

1. Ideally merge the Sprint 1 PR first (`qa/smoke-sweep-sprint-1` -> `main`),
   then branch `fix/findings-burndown-sprint-2` from `main`. If Gene's
   collaborator access is still pending, branch from `qa/smoke-sweep-sprint-1`
   instead — the e2e suite this sprint depends on lives there, not on `main`.
2. Create the branch BEFORE the first fire: the loop preflight only auto-creates
   branches from `main`.
3. `mv .claude/sprint-queue.json .claude/sprint-queue.sprint-1.done.json`
   then `mv .claude/sprint-queue.sprint-2.json .claude/sprint-queue.json`.
4. Invoke `/loop-sprint-cron`.
5. HEADS-UP: T2 wipes the local demo database (`docker compose down -v` +
   fresh seed) to prove the fresh-stack path. Any manually-created UI state
   (QA junk clients, in-progress drafts) is lost. Do the SMOKE_TEST §10/§14
   human checks first if you want the current DB state for them (the §10
   artifacts in `e2e/artifacts/` are on the host and survive regardless).

## Environment facts the loop must know

Carried forward from Sprint 1 (all still true):

- Docker CLI is NOT on Git Bash PATH — `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` in every shell.
- next dev hot-reload does NOT fire through the Windows bind mount — after ANY
  `apps/web` source edit: `docker compose up -d --force-recreate web` (~10-20s)
  before e2e. New python modules under `app/` need `docker compose restart api`.
- Backend tests: `docker compose exec -T api pytest -m unit -q` (~3 min alone,
  13-16 min under load; run detached, poll for `PYTEST_EXIT=`).
- Web typecheck: `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`.
- e2e runs on the HOST: `cd e2e && npx playwright test [file]`, base URL
  `http://localhost:3000`. Full suite ~17 min. Known flake: dev-server
  cold-compile timeouts under back-to-back load — re-run clears it.
- Demo logins: admin `admin@kentro.example` / `DemoPass!2026`; client
  `client@atlas.example` / `DemoPass!2026`. Spec-created users need unique
  timestamped emails.
- LLM is fixture-mode and fully offline (T6b, D-017): Run-AI is deterministic.
- Playwright gotchas log: see CONTEXT.md "Lessons Learned".
- NEW this sprint: after editing `apps/web/package.json`, dependencies must be
  reinstalled INSIDE the web container (`docker compose exec web pnpm install`
  or `docker compose up -d --build web` — check how the compose file provisions
  node_modules before choosing).

## Tasks

### T0 — Dependency bump: resolve the next@14.2.15 CRITICAL advisory

`pnpm audit` reports 29 advisories, 1 critical against `next@14.2.15`
(`apps/web/package.json`). Bump `next` to the latest 14.2.x patch release
(App-Router-stable line; do NOT jump to 15.x this sprint). Address remaining
high/critical transitive advisories with targeted bumps or `pnpm.overrides` in
the root `package.json` where a direct bump isn't possible; document any
advisory deliberately left open (moderate/low with no non-breaking fix) in the
commit body. Reinstall inside the web container, force-recreate, then verify:
`pnpm audit` shows 0 critical + 0 high (or documented exceptions),
`next build` succeeds in-container, tsc clean, FULL e2e suite green (the suite
is the App-Router regression net — this is exactly why Sprint 1 built it).

### T1 — De-brittle hardcoded seeded UUIDs in e2e specs

Final-audit finding: s4, s5, s6, s7, s8, s11, s13 hardcode the seeded Atlas
client/service UUIDs (e.g. `ATLAS_CLIENT_ID = "1b9c80e3-..."`), which only hold
for a seeded-once-and-persisted DB. s9 already does it right
(`atlasClientId()` at `e2e/smoke/s9-messaging.spec.ts:42`, resolving via
`GET /api/proxy/admin/clients`). Create `e2e/helpers/ids.ts` exporting
`atlasClientId(page)` and `atlasServiceId(page, serviceType)` — resolve the
client by `legal_name ~ /atlas/i` (beware the QA-* junk clients), then services
via the intake list the admin proxy exposes with the active-client cookie set
(s9's scratch notes: `GET /api/proxy/intake/assessments`, upstream
`/intake/engagements`; there is NO admin list-services endpoint — verify the
admin+cookie path works, else resolve via the client login). Refactor s9 to use
the shared helper too. Cache per-worker (suite is serialized, one lookup per
spec file is fine). No hardcoded UUID may remain in `e2e/smoke/`.

### T2 — Prove the fresh-stack path: down -v, reseed, full suite green

With T1 done, the suite must pass on a genuinely fresh database — the exact
environment CI will create. `docker compose down -v` (DESTRUCTIVE to local demo
data — flagged in the launch checklist), `docker compose up -d`, wait for
`http://localhost:8000/health`, run the seed, then the FULL e2e suite. Fix
whatever else proves seeded-state-dependent (candidates: version-number
assertions, the `beacon.example` find-or-create in s13, artifact version names
in s7/s8 — they already delta-assert, verify). Document the canonical
fresh-stack bring-up sequence in `e2e/README.md` (create it) — this becomes the
CI job's script. Commit any spec fixes; the reseed itself is not a commit.

### T3 — CI: e2e job in GitHub Actions

Add an `e2e` job to `.github/workflows/ci.yml`: compose the stack on the runner
(postgres/redis/minio/keycloak/mailhog/api/web — same `docker-compose.yml`),
seed, `npm ci` in `e2e/`, install chromium, run the suite, upload the Playwright
report + traces as artifacts on failure. Gate on PRs to `main` alongside the
existing python/web jobs. Mind runner constraints: Keycloak + the full stack is
heavy — give the job a generous health-check wait and a 30-min timeout;
`fullyParallel:false` stays. Local verification is limited to: workflow YAML
validates (actionlint if available, else careful review), and the job's
script block reproduced locally end-to-end (which is exactly T2). The first
real CI run happens when the branch is pushed — that push is review-required,
so final proof lands with the PR (note this honestly in the commit body).

### T4 — Runtime axe sweep spec + CI wiring

The PR #1 follow-up "runtime axe/Pa11y in CI (needs a built-app harness)" is
now unblocked by T3's composed stack. Add `@axe-core/playwright` to `e2e/` and
`e2e/smoke/s16-axe.spec.ts`: run axe on the signed-out home + sign-in + sign-up,
client `/assessments` + one self-assessment questionnaire, admin dashboard + one
workspace. Fail on WCAG A/AA violations; triage what it finds — fix the cheap
ones in this task (expected: the known heatmap `scope=row` gap lands in T6, so
exclude that rule with a comment pointing at T6, or do T6 first if sequencing
allows). Document any deliberately-excluded rules inline. The spec runs in the
same suite, so T3's CI job picks it up automatically.

### T5 — Import IG Core/Supporting cross-reference metadata (CSF Rules 2/5)

`apps/api/app/routes/csf.py:980` — "IG core/supporting metadata isn't in the
catalog yet; defaults keep": `is_core_primary=False`,
`is_supporting_or_supplemental=False`, `is_core=False` are passed to
`blended_priority()` / `gap_priority()` (`apps/api/app/csf/playbook.py:114-190`),
so Rule 2 (Core+Primary strict floor) and Rule 5 (Supporting/Supplemental
override) NEVER fire, and gap priorities skew low. Source the CSF 2.0
Implementation-Guidance cross-reference data (grep
`reference-docs/SHIELDv2_Master_Spec.txt` for the IG Core/Supporting mapping;
check how the zt catalog packages data under `packages/zt-data` for the
established pattern). Land it as catalog data (additive — the C0 pattern: older
assessments must parse unchanged), thread the real flags through the csf route,
and add unit tests proving Rule 2 and Rule 5 each fire on a known subcategory
and that the safe-default path still works for subcategories absent from the
mapping. Migrations, if any, must stay SQLite-safe (`batch_alter_table`).
"AI suggests, code computes" — this is catalog data feeding the deterministic
engine; the LLM is not involved.

### T6 — a11y fixes: roving tabindex + heatmap scope=row

(a) TierPicker and ZtStagePicker render `role=radio` buttons that are
Tab-reachable and Space/Enter-operable but lack arrow-key navigation. Implement
the WAI-ARIA radiogroup roving-tabindex pattern in both (ArrowRight/Down next,
ArrowLeft/Up previous, wrap; selected — or first, if none — is the sole
tabIndex=0 stop). Do not break the auto-save PATCH-on-select behavior (s3/s6
cover it). (b) Risk heatmap tbody `<th>` likelihood labels need `scope="row"`
so Chromium's a11y tree resolves them as rowheaders. Extend s12-a11y-nav with
arrow-key assertions on a TierPicker and update s8's heatmap header assertion
to use the now-correct rowheader role. If T4 landed first, delete its
scope-row rule exclusion.

### T7 — CSF draft-exists guard

`POST /csf/services/<id>/assessments` mints a new draft version on every call —
unbounded in practice. Add a guard: if an unsubmitted draft already exists,
return it (200 with the existing draft, or 409 with a typed
`{reason: "draft_exists", ...}` — pick whichever the existing API idiom
supports; the T4/D-016 typed-error pattern is the precedent). CAUTION: s7
deliberately relies on always-fresh drafts ("fresh draft ALWAYS minted"), and
s5/s6/s11 mint drafts via `page.request.post` in setup — update every affected
spec to handle the existing-draft response (reuse it; determinism holds because
fixture Run-AI is idempotent per assessment). Unit test the guard; full e2e
green is the real gate here.

### T8 — Close the coverage gaps: /admin/management UI spec + C8 verbatim prompts

(a) `e2e/smoke/s2-management.spec.ts`: exercise the Management UI itself (not
the admin API): create a client, approve a domain, see both reflected in the
list, remove the domain, see removal reflected. Use unique timestamped names;
reject-reserved-TLD copy from T9 asserted here if T9 landed first.
(b) In s3 (or a small s3 extension): assert the rendered CSF questionnaire
prompt text for 2-3 known subcategories matches the master spec verbatim
(source: grep `reference-docs/SHIELDv2_Master_Spec.txt` for the interview
prompts; import or inline the expected strings with a comment naming the spec
section). Check off SMOKE_TEST §2 and the §3 verbatim-prompts clause with spec
filenames once green.

### T9 — Reserved-TLD guard at domain approval

`beacon.test` sits approved-but-unregistrable: the email validator 422s
special-use TLDs (`.test`, `.invalid`, `.localhost`, `.example` is fine) BEFORE
the domain-approval check, so an admin can approve a domain no user can ever
register on. Fix at approval time: the admin add-domain route rejects
special-use/reserved TLDs with a typed 422 (same reserved-name check the email
validator applies — reuse `email-validator`'s logic rather than a hand-rolled
list if feasible), friendly copy in the Management UI. Migrate the seed's
Beacon domain to `beacon.example` if the seed still creates `beacon.test`
(check `seed_demo.py` — s13 already provisions `beacon.example` itself). Unit
test the route; assert the UI copy in s2-management (T8) if it exists by then.

### T10 — Docs refresh + wrap-up

BUILD_REPORT.md and CHANGELOG.md are stuck at Phase 2 — rewrite both to v3.0.0
reality (v2 work order merged, sprint-1 smoke suite, this sprint's changes;
CHANGELOG gets proper entries per sprint, BUILD_REPORT reflects the current
build/gate set including the new CI e2e+axe jobs). Sync SMOKE_TEST.md
checkboxes for anything this sprint newly covered (§2, §3 verbatim clause,
§12 arrow-key note). Run the FULL gate set one last time (full e2e, pytest,
tsc). Overwrite CONTEXT.md with the end-of-sprint snapshot.

## Definition of done

- `pnpm audit`: 0 critical / 0 high (or each remaining advisory explicitly
  documented as no-non-breaking-fix).
- Full e2e suite green TWICE on a from-scratch stack (`down -v` -> seed -> run).
- No hardcoded seeded UUIDs anywhere in `e2e/`.
- CI workflow contains e2e + axe jobs whose script block is proven locally.
- Rules 2/5 fire with real IG metadata under unit test; safe-default fallback
  still covered.
- `pytest -m unit` and web tsc green; every commit conventional and task-scoped.
- CONTEXT.md snapshot written; BUILD_REPORT/CHANGELOG current.

## Explicitly out of scope (needs-David or Sprint 3)

- Pushing the branch / opening the PR (review-required; also proves T3 in CI).
- SMOKE_TEST §10 document eyeball, §14 live-AI run (Sprint 1 leftovers).
- Next.js 15 / React 19 major upgrade (only if a critical advisory forces it).
- `infra/terraform`, MFA/email-verify flags, FedRAMP LLM connector (Sprint 3;
  blocked on David's account/region/network decisions).
