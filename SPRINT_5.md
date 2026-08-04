# SPRINT 5 — Client value loop

_Branch: `feat/client-value-loop-sprint-5` (from `main` post-#28). Queue:
`.claude/sprint-queue.sprint-5.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron`. Created 2026-07-10 after Sprint 4
(PR #28) merged. NOT YET LAUNCHED._

## Sprint goal

Make the platform deliver visible value to the CLIENT role. Everything the
consultants produce today dead-ends at admin-only routes — the Master Spec's
"highest-value page in the entire platform" (§2.5) doesn't exist, clients
cannot see a single deliverable, and the append-only audit trail has zero
read surface. Five client-facing features, two Sprint-4 follow-ups, and one
hygiene task:

1. **Deliverable release-to-client flow** (spec §6.7, §12) — a NEW decision
   (D-025 expected), not a revival of the removed D-005/D-006 reviewer gate
   (D-023 records that supersession). Consultant explicitly releases; until
   then the client never sees AI output or drafts (§12 :1805).
2. **`/home` client dashboard** (§6.4) + **cross-service value-loop card**
   (§2.5) — the signed-in executive landing page.
3. **POA&M step for CSF gap analysis** (§6 :1345, §8 :1346) — per-gap
   Characterize / Prioritize / Action items (owner, deadline, resources,
   success criteria) / POA&M linkage, exported into the action-plan XLSX.
4. **Redaction preview gate** (audit §4c #3) — see exactly what a Run-AI will
   send BEFORE it egresses.
5. **`/admin/audit` viewer** (audit §4c #4) — the `audit_entries` +
   `llm_calls` read surface.
6. Follow-ups from Sprint 4: **web unit-test harness (vitest)** with tests
   for the two `reqSeq` guards, and **react-hooks v6 rule adoption** (the 14
   rules disabled for parity in T3/Sprint 4).
7. Hygiene T0: **prettier 3.9.5 pin sync** (dependabot PR #29 supersession).

Version at close: `3.2.0` (new client-facing features justify the minor).

## Prerequisites / launch checklist (human)

1. Merge this planning PR.
2. `git checkout -b feat/client-value-loop-sprint-5 main` BEFORE the first fire.
3. Archive the old runtime queue, COPY `.claude/sprint-queue.sprint-5.json` to
   `.claude/sprint-queue.json`; set `working_dir` + `expected_gh_user` for
   your box.
4. Invoke `/loop-sprint-cron`.
5. Close dependabot PR #29 as superseded once T0 lands (T0 makes the same
   bump on the sprint branch plus the pin-reference sync #29 can't do).
6. **SMOKE_TEST §14 (live AI)** remains David's pending item (provider key
   still not in `.env` as of 2026-07-10) — independent of this sprint; if the
   live run surfaces defects, append them to this queue as tasks.

## Environment facts the loop must know

All CLAUDE.md gotchas hold, plus the Sprint-4 additions: the api service
compose-mounts the root `pyproject.toml` so in-container ruff/black equal CI
(4th gate in the queue); web stack is Next 15 / React 19 / Tailwind 4 /
ESLint 9 flat / Node 22. This box: web on :3001; e2e via winget node.exe +
`e2e/node_modules/@playwright/test/cli.js`; Docker CLI needs the PATH export
per shell; `gh auth switch --user SpearheadAnalytica` before gh writes.
Sprint-4 lessons that bite here: poll long gates in the FOREGROUND to the end
of the iteration (never park on background monitors); never run `pnpm build`
in the web container while e2e runs (shared `.next`); force-recreate web
after ANY web/packages source edit before e2e; never restart api mid-pytest
(SIGKILL 137). New migrations this sprint MUST be additive/SQLite-safe
(`batch_alter_table`, C0): expected `0028` (deliverable release fields),
`0029` (POA&M action fields).

## Tasks

### T0 — Prettier 3.9.5 pin sync (supersedes dependabot #29)

Dependabot PR #29 bumps `prettier` 3.9.4→3.9.5 in root `package.json` but
cannot update the FOUR places the version is pinned as a gate: CLAUDE.md
real-commands, CONTEXT.md machine-local facts, the runtime queue `gates`
array, and this staged queue. Land the bump + lockfile on the sprint branch
and sync every pin in one commit so the gate never drifts from the lockfile
(the Sprint-2 lesson: format gate divergence ships red CI). Verify: repo-wide
`npx -y prettier@3.9.5 --check` green; grep finds zero remaining `3.9.4`
references outside CHANGELOG history; runtime queue gate string updated.

### T1 — Deliverable release flow, backend (D-025)

The spec's release rule (§12 :1805): *"Released to client = consultant
explicitly released. Until then, the client never sees the AI output or the
draft."* Today `Deliverable` (models/deliverable.py) deliberately has NO
release state — migration `0015` dropped `released_to_client_at` when the
reviewer flow was removed (D-023). Reintroduce release as a NEW single-role
decision:

- Migration `0028` (additive, C0): `deliverables.released_at` (nullable
  DateTime) + `released_by` (nullable FK users.id). Old rows = unreleased.
- `POST /{service}/deliverables/{id}/release` — admin-only, requires
  `finalized_at` set (typed 409 `not_finalized` otherwise, D-016 envelope),
  idempotent (releasing a released deliverable = 200 no-op with loud log),
  audit row `*.deliverable.released`.
- Client read route: `GET /clients/{cid}/deliverables` returning ONLY
  released deliverables (title, summary, version, released_at, per-format
  filenames + artifact ids, superseded flag), tenant-enforced via the
  existing `require_*_in_tenant` pattern (404 on mismatch, never 403).
- Artifact download: extend the artifact download path so a CLIENT user can
  fetch artifacts belonging to a RELEASED deliverable of their own tenant —
  and nothing else (unit test the deny paths: unreleased, wrong tenant,
  non-deliverable artifact).
- DECISIONS: append **D-025** recording the reintroduction as a new
  admin-only release action (explicitly not a revival of D-005/D-006's
  reviewer gate).
- TDD: contract tests for release + client list + artifact access
  (allow/deny matrix) before implementation.

### T2 — `/documents` client page (§6.7)

"WHAT YOU'VE RECEIVED": table of released deliverables for the signed-in
client — service, title, version, released date, status badge
(Final / Superseded), download links per format (PDF/XLSX/DOCX where
present). Empty state per the no-dead-ends rule (§12). Client nav gains the
entry; admin sees no change. e2e spec: release a deliverable as admin (API),
sign in as client, see it listed, download link 200s with the §15.5
filename; unreleased deliverable NOT listed. Depends on T1.

### T3 — `/home` client dashboard shell (§6.4)

The signed-in client landing page (route exists for CLIENT role; admins keep
`/admin`). Per §6.4 (:1000): greeting; HERO band ("Your {service} report is
ready" + View/Download) shown ONLY when a released deliverable exists (else
next-step guidance); per-service status grid (intake → in progress → report
ready, from existing assessment/service status — no new scoring); "what's
waiting on you" (open self-assessments, unread messages); recent activity.
Explicitly HIDES scoring math, audit internals, raw AI output (§6.4). Signed-in
clients landing on `/` redirect to `/home`. e2e spec covers hero-present and
hero-absent states. Depends on T1 (release state feeds the hero + grid).

### T4 — Cross-service value-loop card (§2.5)

The §2.5 (:314) synthesis on `/home`: one card aggregating Tech Debt savings
estimate + ZT gap count + ATT&CK uncovered-technique count + CSF gap count
into an executive summary. **"AI suggests, code computes" is inviolable:**
this is a DETERMINISTIC aggregation endpoint over already-computed engine
outputs (`GET /clients/{cid}/value-summary`, admin+client, tenant-enforced) —
no LLM call, no new scoring, nulls for services without approved/released
data (render "pending" — never fake numbers). Unit tests: aggregation with
full data, partial data, no data. e2e: card renders on `/home` with seeded
data. Depends on T3.

### T5 — POA&M step for CSF gap analysis (§6 :1345, §8 :1346)

Spec Step 10 requires per-gap: Characterize (accept/mitigate/transfer/avoid),
Prioritize (P1/P2/P3 — `gap_priority()` in `csf/playbook.py:177` already
computes the default), Action items (owner, deadline, resources, success
criteria), POA&M linkage (free-text reference id). Today NONE of these fields
exist (audit §4c #5).

- Migration `0029` (additive, C0): new `csf_gap_actions` table keyed to
  (assessment, subcategory): `characterization`, `priority_override`,
  `owner`, `deadline`, `resources`, `success_criteria`, `poam_ref`, all
  nullable.
- CRUD routes (admin-only, D-016 typed errors), autosave-friendly.
- Admin UI: extend the existing gap-analysis view with the action-item
  editor per gap (follow the CsfDimensionEditor auto-save pattern —
  remember the Playwright auto-save gotcha: `click()` + `waitForResponse`).
- Export: action-plan sheet added to the playbook XLSX
  (`csf/playbook_export.py:render_xlsx`) — priority defaults from
  `gap_priority()`, overridden where set. Deliberately NOT a new §15.5
  deliverable kind; it extends the existing playbook workbook.
- TDD: engine-side unit tests (default priority vs override), route
  contract tests, export content test; e2e: edit an action item, reload,
  survives; XLSX artifact regenerates.

### T6 — Redaction preview gate (audit §4c #3)

`POST /ai/preview` (admin-only, per-service like run-ai, rate-limited by the
existing AI limiter): builds the SAME payload run-ai would build, runs it
through `redact_payload` (`ai/redact.py:250`), and returns the redacted
payload + `removed_counts` WITHOUT creating an `llm_calls` row and WITHOUT
egress. Web: the Run-AI flow gains a "Preview what will be sent" affordance
showing the redacted payload + counts before confirming the real run
(non-blocking — Run-AI still works directly; the preview is an offered gate,
not a forced modal). Unit tests: preview response equals the redaction of
the run-ai payload builder's output for the same state; no `llm_calls` row
created; counts match. e2e: open preview, see counts, then run AI. NOTE:
adding a new python module under `app/` needs `docker compose restart api`.

### T7 — `/admin/audit` viewer (audit §4c #4)

Read surface for the two append-only stores (42 write sites, zero readers):

- `GET /admin/audit-entries` — paginated (cursor on `at`/`id` desc), filters:
  `action` prefix, `target_type`, `actor_user_id`, `correlation_id`, date
  range. Admin-only.
- `GET /admin/llm-calls` — paginated, filters: `client_id`, `purpose`,
  `provider`, `status`, date range. Returns the audit-safe fields (redacted
  counts, tokens, duration, status, error_message — error_message is already
  key-safe post-Sprint-4 Gemini fix). Admin-only.
- `/admin/audit` page: two-tab table UI (Activity / AI calls) with the
  filters, correlation-id click-through linking the two tabs. Read-only —
  no mutation affordances on an append-only store.
- Unit: filter/pagination contract tests + a client-role 403 test. e2e: an
  action performed in the test (e.g. a release from T1's flow) appears in
  the viewer; llm_calls tab shows fixture-mode rows.

### T8 — Web unit-test harness (vitest) + reqSeq guard tests

apps/web has NO unit-test framework (Sprint-4 deferral). Stand up vitest +
@testing-library/react + jsdom for `apps/web` (and `packages/design-system`
importable): `pnpm -F web test` script, deterministic (no network — mock
fetch). First tests: the two stale-fetch `reqSeq` guards
(`admin/csf/CsfPlaybookPanel.tsx:131`, `messages/MessageThread.tsx`) —
assert a stale response arriving after a newer request does NOT write state,
and errors surface to the error state (fail-loudly). Wire `pnpm -F web test`
into CI's web job AND append an in-container test gate to the runtime queue
`gates` array (same pattern as Sprint-4 T0). Keep the harness minimal — no
snapshot tests, no coverage thresholds this sprint.

### T9 — Adopt the 14 react-hooks v6 rules

Sprint-4 T3 disabled 14 new `eslint-plugin-react-hooks` v6 rules
(`set-state-in-effect`, `purity`, etc.) to hold strict rule parity. Adopt
them now as a deliberate lint tightening: enable all 14 in
`eslint.config.js`, fix every violation (~15 components at Sprint-4 count —
re-run to get the true current list). Violations in the mount-fetch family
may warrant the `reqSeq` guard pattern (T8's tests show the shape) — but do
NOT add speculative guards to components the rules don't flag; the broader
guard sweep stays a Sprint-6 candidate. Rule-by-rule notes in the commit
body for anything intentionally configured off (target: zero rules off).
Gates: eslint exit 0, tsc, full e2e (behavioral edits to shared components).
Depends on T8 (guard changes need the new tests green).

### T10 — Wrap-up

- SMOKE_TEST.md: new sections for the release flow, `/documents`, `/home`
  (+ value card), POA&M editing, redaction preview, audit viewer — each
  checked ONLY when a green committed spec proves it (annotate spec files).
- CHANGELOG `[3.2.0]` per-task entries with commits.
- DECISIONS: verify D-025 landed (T1); append others if any task made one.
- Full exit gate set: full e2e, pytest -m unit, tsc, prettier 3.9.5,
  in-container ruff/black, AND the new web vitest gate (T8).
- CONTEXT.md overwritten with the end-of-sprint snapshot (Sprint-4 format).

## Definition of done

- A client user can sign in and see `/home` (§6.4) with the value-loop card
  (§2.5), and download released deliverables from `/documents` (§6.7);
  unreleased/draft work remains invisible to clients (§12 release rule).
- CSF gaps carry actionable POA&M fields exported in the playbook XLSX.
- Admins can preview redacted egress before Run-AI and browse the audit
  trail at `/admin/audit`.
- `pnpm -F web test` exists, runs in CI and the queue gates, and covers both
  reqSeq guards; all 14 react-hooks v6 rules enabled with zero violations.
- Prettier pinned at 3.9.5 everywhere it is referenced; dependabot #29
  closed as superseded.
- Migrations 0028/0029 additive and SQLite-safe (C0); every commit
  conventional and task-scoped; CONTEXT.md snapshot written.

## Explicitly out of scope (Sprint 6+ / needs-David)

- The reqSeq guard sweep across the ~12 other mount-fetch components (only
  where T9's rules force it).
- `infra/terraform`, deploy runbook, DR drills — gated on David's
  cloud/account/region decisions.
- Real MFA + email-verification flows (D-020 posture unchanged);
  Auth.js v5 migration; ESLint 10 (still blocked upstream).
- `azure_openai`/`bedrock`/`local` LLM adapters; FedRAMP POA&M template
  export (§16 future scope — this sprint's POA&M is the working fields, not
  the FedRAMP artifact).
- Client notifications/email on release (release is visible on `/home` and
  `/documents`; outbound notification is a future decision).
