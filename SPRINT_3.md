# SPRINT 3 — Correctness & honesty (audit burn-down)

_Branch: `fix/audit-correctness-sprint-3` (from `main` post-#21). Queue:
`.claude/sprint-queue.sprint-3.json` (rename to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron`. Created 2026-07-08 from the deep repo
audit (`docs/audits/2026-07-08-repo-audit.md`). NOT YET LAUNCHED._

## Sprint goal

Everything the platform CLAIMS is true becomes true, and the silent-failure
paths the audit found get fixed. Concretely: CSF live-mode Run-AI actually
works (schema + grounding), the attack/ZT mint routes get the T7 draft guard,
the auth compensating controls documented in README/BUILD_REPORT are either
implemented or honestly retracted, auth + run-AI routes get rate limiting
(Redis finally earns its keep), the CSF Playbook and Risk Register exports
follow the spec §15.5 filename convention, `llm_calls` rows become
tenant-attributable, and the documentation set stops lying
(architecture.md's single-tenant/Celery fiction, README's phantom runbooks,
duplicate D-015, "(admin/reviewer)" OpenAPI summaries).

Explicitly rescheduled by David 2026-07-08: the framework-majors bundle
(Next 15/16, React 19, Tailwind 4, Node 22 — D-018) moves to Sprint 4;
client-facing features (deliverable release, /home value loop, POA&M step)
to Sprint 5 candidates.

## Prerequisites / launch checklist (human)

0. New machine or new developer? Do ONBOARDING.md first (Docker, Node, gh,
   e2e deps, seeded stack — zero-to-loop).
1. Merge the sprint-3 planning PR (this doc + queue + audit report).
2. `git checkout -b fix/audit-correctness-sprint-3 main` BEFORE the first fire.
3. `mv .claude/sprint-queue.json .claude/sprint-queue.sprint-2.done.json`
   (if a prior runtime queue exists) then COPY
   `.claude/sprint-queue.sprint-3.json` to `.claude/sprint-queue.json`.
4. In your runtime copy (`.claude/sprint-queue.json` — gitignored,
   machine-local), set `working_dir` to YOUR absolute repo path and
   `expected_gh_user` to YOUR GitHub login. The loop preflight halts on
   either being wrong.
5. Invoke `/loop-sprint-cron`.
5. AFTER T0 lands: SMOKE_TEST §14 (live-AI run) is finally meaningful — do it
   then, not before (T0 fixes the bug that would have failed it).
6. Needs-David inputs, non-blocking: the v2 Developer Work Order document for
   `reference-docs/` (T7 commits it if provided, else records its absence);
   cloud/account/region decisions stay Sprint-4+ (terraform intentionally NOT
   in this sprint).

## Environment facts the loop must know

All CLAUDE.md gotchas hold. This box: web on :3001 (root `.env` WEB_PORT;
e2e resolves via `e2e/helpers/baseUrl.ts`); node.exe + gh.exe under
`%LOCALAPPDATA%\Microsoft\WinGet\Packages` (not on PATH) — run Playwright via
that node.exe + `e2e/node_modules/@playwright/test/cli.js`; gh active account
can silently flip to the read-only EMU — run
`gh auth switch --user SpearheadAnalytica` before any gh write. NEW GATE this
sprint: host prettier `format:check` (lockfile-pinned version via
`npx -y prettier@<lockfile version> --check ...`) — CI enforces it and the
sprint-2 loop missed it.

## Tasks

### T0 — Fix CSF live-mode Run-AI (schema + grounding + contract test)

The audit's critical find (`docs/audits/2026-07-08-repo-audit.md` §3b):
(a) `_CSF_SCORE_PROMPT` (apps/api/app/ai/jobs.py:41-54) instructs the model to
return `{"subcategories": [...]}` while the route parses
`data.get("scores", [])` keyed on `tier`+`subcategory_code`
(apps/api/app/routes/csf.py:1099-1128) — the FIXTURE shape — so live mode
silently discards a schema-compliant response (fail-loudly violation);
(b) the job payload sends only tier/subcategory codes, no interview answers or
evidence, though the prompt claims they are supplied (ZT does this right:
routes/zt.py:398-400). Fix BOTH: align the prompt schema with the parser
(pick one shape; the fixture shape is fine — update the prompt), and build the
payload from the assessment's interview answers/evidence summaries the way ZT
does (mind redaction: the payload goes through the redactor, that's the
point). Add a contract test that fails if prompt schema and parser diverge
again (e.g. parse a response constructed to the prompt's documented schema and
assert changes > 0), plus a test that the payload contains answers. Fixture
mode must stay deterministic — update `app/ai/fixtures.py` only if the shape
decision requires it, keeping D-017 semantics. Full e2e green (s3/s5/s7 exercise
fixture Run-AI).

### T1 — Port the T7 draft-exists guard to attack + ZT mint routes

`POST /attack/services/{id}/assessments` (routes/attack.py:~243) pre-seeds
~600 coverage rows per mint; `POST /zt/.../assessments` (routes/zt.py:~471)
~87 rows; both mint unbounded new versions per call. Apply T7's
idempotent-200 pattern (return the open draft; new version only after the
prior draft closes — see routes/csf.py:364-381 and
tests/unit/test_csf_draft_guard.py). Check whether tech_debt has the same
pattern and cover it if so. CAUTION: s5/s6/s11 mint attack/zt drafts via
page.request.post in setup — update them to handle the existing-draft
response exactly as T7 updated s7 (close-then-mint where a genuinely fresh
draft is required). Unit tests both routes (exists/not-exists/closed-then-mint).
Full e2e green is the real gate.

### T2 — Auth compensating controls: enforce or retract

README.md:137 and BUILD_REPORT.md (A07) claim "daily forced re-auth" and a
"30-minute idle timeout" as MFA offsets; neither is enforced
(config flags `shield_idle_timeout_seconds`/`shield_forced_reauth_seconds`
referenced nowhere; `/auth/refresh` routes/auth.py:315-333 re-issues token
pairs indefinitely, no rotation/revocation). Implement the honest version:
(a) carry an original-auth-time claim in the refresh token and reject refresh
beyond `shield_forced_reauth_seconds` with a typed 401
(`reason=reauth_required`) — web sign-in flow must handle it (friendly copy,
redirect to sign-in); (b) refresh-token rotation (new refresh token per
refresh; old one invalidated — jti denylist in Redis or a rotating-pair
check); (c) dead flags fail loudly: if `shield_auth_require_mfa` or
`shield_auth_require_email_verify` is set true at startup, raise a clear
configuration error instead of silently doing nothing (the flows don't exist
yet — pretending is worse); (d) update README.md:137 + BUILD_REPORT A07 to
describe exactly what is now real. Unit tests for (a)-(c). Mind e2e: specs
sign in fresh each run, so generous defaults (e.g. 24h reauth) keep the suite
green.

### T3 — Rate limiting on auth + run-AI routes

Redis is composed and idle (D-015 Part F noted it as placeholder).
Add fixed-window (or sliding-window) rate limits: per-IP + per-account on
`/auth/login` and `/auth/register`; per-client on the five run-AI endpoints
(the expensive path). Typed 429 `{reason: "rate_limited", message}` per D-016;
`Retry-After` header; limits configurable via `app/config.py` with generous
defaults that never trip the e2e suite (document the numbers in the commit).
Fail-open ONLY on Redis unavailability with a loud structlog warning (an
outage must not brick auth), and unit-test that path too. No silent behavior.

### T4 — §15.5 filename convention for CSF Playbook + Risk Register exports

Spec §15.5: every download carries
`{Company_Name}_{Service_Name}{MMDDYY}` naming via the existing
`deliverable_filename()` helper (apps/api/app/tech_debt/filename.py — already
used by the four service deliverable routes). The CSF Playbook 5-file export
(routes/csf.py:~1202-1259, `CSF_Playbook_v{n}*`) and Risk Register exports
(routes/risk.py:~332-356, `Risk_Register_v{n}.*`) don't comply. Route both
through the helper (keep version suffixes). Update s7/s8 artifact-name
assertions (they delta-assert on names). e2e s7+s8 green.

### T5 — llm_calls tenant attribution

Add nullable `client_id` to `llm_calls` (additive migration, SQLite-safe
`batch_alter_table`, C0 pattern — old rows parse unchanged). Set it at all
five call sites (tech_debt/extract, attack, csf, zt, risk — risk currently
passes no service_id either; give it the client at minimum). Unit test that a
run-AI call writes an attributed row. Supports the FedRAMP narrative that
redaction+audit is the primary egress control.

### T6 — Docs truth pass

Fix every §2 audit finding:
- REWRITE `docs/architecture.md`: multi-tenant D-015 reality (client_id
  columns, X-Client-Id, tenant.py 404s), NO worker/Celery (sync AI in api,
  Redis now = rate limiting per T3), `audit_entries` (not audit_events), real
  AI flow (no `unredact` — it doesn't exist), current service list.
- README.md: multi-tenant statement; runbooks section says what EXISTS
  (docs/runbooks/ is empty — either say "planned" or remove); terraform
  marked planned-not-present; real test matrix (unit + tsc + e2e; drop
  phantom `pytest -m integration` and web `pnpm test`); e2e counts current
  (16 files; count tests at task time — 34 as of the audit).
- CHANGELOG.md: fix the duplicate `[3.0.0]` (Sprint 1 gets its own version);
  add this sprint's entry at close.
- DECISIONS.md: dedupe D-015 (append-only log — add an erratum entry
  renumbering the second D-015 (Part F) to a fresh number and noting the
  collision); add an entry recording the D-005/D-006 supersession (reviewer
  role + release flow removed by Work Order A1/A3, per code reality).
- Purge stale reviewer references: OpenAPI summaries "(admin/reviewer)"
  (routes/admin.py:144,197 — externally visible at :8000/docs),
  docstrings/comments in dependencies.py, security/jwt.py, schemas/auth.py,
  routes/intake.py.
- docs/operations.md + docs/development.md: remove worker/Celery/Prometheus
  fiction; document what's real.
- reference-docs: if David supplied the v2 Developer Work Order, commit it;
  else add a note in a reference-docs README that Parts A-F decisions live in
  DECISIONS.md + code comments. Also record the Master Spec's "108
  subcategories" vs implemented 106 (NIST CSF 2.0 Final) discrepancy there.
- BUILD_REPORT.md: A06/A07 rows reflect T2's real posture; test counts.
Depends on T2 (must document what T2 actually shipped).

### T7 — Loop hygiene + wrap-up

- Add the host prettier `format:check` gate to this queue's `gates` array
  documentation and CLAUDE.md commands (the sprint-2 loop shipped unformatted
  files that CI caught; agents must run the check before commit).
- Sync SMOKE_TEST.md for anything this sprint changed (§14 becomes runnable
  post-T0 — note it; do NOT check it, it needs David's live run).
- Run the FULL gate set: full e2e suite, pytest -m unit, tsc, prettier check.
- CHANGELOG entry for the sprint; overwrite CONTEXT.md with the
  end-of-sprint snapshot.

## Definition of done

- CSF Run-AI live-shape contract test green; payload carries interview
  answers; prompt and parser agree.
- attack/zt (and tech_debt if applicable) mint routes idempotent under test;
  no spec relies on unbounded minting.
- `/auth/refresh` enforces forced re-auth + rotation under test; dead flags
  fail loudly; README/BUILD_REPORT match reality.
- 429s with typed reasons on auth/run-AI under test; e2e suite unaffected.
- CSF/risk exports named per §15.5; s7/s8 green.
- `llm_calls.client_id` populated on all five paths.
- Zero "reviewer" in OpenAPI/docstrings; architecture.md/README accurate to
  a fresh reader; D-015 dedupe + supersession entries in DECISIONS.md.
- Full gate set green twice (mid-sprint checkpoint + close); every commit
  conventional and task-scoped; CONTEXT.md snapshot written.

## Explicitly out of scope (Sprint 4/5 candidates)

- Framework-majors bundle (Next 15/16, React 19, Tailwind 4, Node 22) — Sprint 4.
- Client deliverable release + /home value-loop card + POA&M step +
  redaction preview gate + /admin/audit viewer — Sprint 5 candidates
  (audit §4c).
- infra/terraform + deploy runbook + backup/restore drill — needs David's
  cloud decisions; backup runbook may pull forward if Sprint 4 has room.
- DoD 152-activity catalog completion; i18n implement-or-rescind decision.
