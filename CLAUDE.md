# CLAUDE.md — SHIELD

Durable project knowledge for every Claude session, every developer. If it's a
fact that outlives the current sprint, it belongs here. Session status belongs
in `context/<your-name>.md`; state-of-main belongs in `CONTEXT.md`.

## What this is

SHIELD is Kentro's multi-tenant cybersecurity assessment platform for
consultant-led client engagements (FedRAMP Moderate/High targets). Four
assessment services — Technical Debt Review, Zero Trust (CISA ZTMM 2.0 + DoD
ZTRA), NIST CSF 2.0 (10-step Playbook), MITRE ATT&CK coverage — plus a Risk
Register (5x5 NIST 800-30) synthesized from them.

Stack: pnpm monorepo. Next.js 14 App Router (`apps/web`), FastAPI + SQLAlchemy
2 + Alembic (`apps/api`), Postgres 16 / Redis / MinIO / Keycloak / MailHog via
`docker-compose.yml`. No worker service — AI jobs run synchronously in `api`.
Playwright e2e lives in `e2e/` (host-run). Reference spec:
`reference-docs/SHIELDv2_Master_Spec.txt`. Architecture detail:
`docs/architecture.md`.

## Core principles (non-negotiable)

1. **"AI suggests, code computes."** Deterministic scoring lives in Python
   engines (`app/csf/playbook.py`, `app/risk/engine.py`, `app/zt/scoring.py`).
   The LLM only drafts values and narrative through the single redacting
   egress client (`app/ai/llm.py`). No fix may move scoring into prompts.
2. **FAIL LOUDLY.** No silent failures, ever. No `catch` that swallows, no
   `return null` / default-value fallbacks on error, no bare `except: pass`.
   Errors throw/raise with useful context. User-facing API errors are typed
   (`{reason, message}` dict-detail — the D-016 pattern) mapped to friendly
   copy, never raw validation dumps and never a lie that something succeeded.
3. **TDD.** Test first, watch it fail, implement the minimum, watch it pass.
   Never weaken or delete a test to get to green — fix the code. If a test
   itself is genuinely wrong, say so explicitly before touching it.
4. **Simple code.** Small single-purpose functions, no speculative
   abstraction, names that don't require reading the body.
5. **Debug logging.** Success paths log too, with a consistent module prefix —
   a future reader should never wonder "did this actually run?"
6. **Migrations stay SQLite-safe** (`batch_alter_table`) — tests run SQLite,
   prod runs Postgres. New persisted analysis fields are additive/optional so
   older rows parse unchanged (the C0 pattern).

## Real commands (use these, not generic equivalents)

- Docker CLI is NOT on Git Bash PATH:
  `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` first, every shell.
- Backend unit tests: `docker compose exec -T api pytest -m unit -q`
  (~3 min alone, 13–16 min under load; run detached and poll for the exit code).
- Web typecheck: `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`
- e2e (host, not docker): `cd e2e && npx playwright test [file]` — base URL
  `http://localhost:3000`, chromium, serialized (shared seeded DB). Full suite
  ~17 min.
- Format check (MANDATORY before every commit — CI enforces it, the Sprint 2
  loop shipped unformatted files it only caught at CI): run host prettier at the
  version the lockfile pins (`3.9.5`) so local and CI agree —
  `npx -y prettier@3.9.5 --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"` from
  the repo root. `--write` the same glob to fix, then re-check.
- Python lint/format (in-container, CI-parity — MANDATORY before every commit
  that touches `apps/api`): `docker compose exec -T api sh -lc "cd /app && ruff
  check --no-cache . && black --check ."`. Compose bind-mounts the root
  `./pyproject.toml` read-only at `/pyproject.toml` (the api build context is
  only `apps/api`, whose `pyproject.toml` carries no `[tool.ruff]`/`[tool.black]`
  tables, so both tools skip it and walk up to the root config — same rule set
  CI runs). Sprint 3 shipped 6 ruff errors CI caught because in-container runs
  used tool defaults; this closes that gap (`--no-cache`: `/.ruff_cache` is not
  writable in the container).
- Web unit tests (vitest, loop gate since Sprint 5):
  `docker compose exec -T web sh -lc "cd /app && pnpm -F web test"`
- Web lint (loop gate since mid-Sprint-6 — a latent react-hooks error slipped
  the five-gate set and only surfaced in CI's `next build`):
  `docker compose exec -T web sh -lc "cd /app && pnpm -F web lint"`
- Dependency audits: `pnpm audit` at root, `npm audit` inside `e2e/`.
- **Bandit is CI-only** (`bandit -q -c pyproject.toml -r apps/api/app`), not a
  loop gate — and ruff's `# noqa: S1xx` does NOT suppress it. A string bandit
  flags needs its own `# nosec BXXX` marker too (Sprint 6 shipped a red CI on
  exactly this: a `"password_reset"` purpose label flagged as B105).
- Seed: `docker compose exec -T api python scripts/seed_demo.py` (idempotent).

## Environment gotchas (learned the hard way)

- **next dev hot-reload does NOT fire through the Windows bind mount.** After
  ANY `apps/web` source edit: `docker compose up -d --force-recreate web`
  (~10–20s) before e2e. In-container touch/restart does not help.
- Adding a NEW python module under `app/` needs `docker compose restart api`
  (uvicorn --reload catches edits to existing modules, may miss new files).
- After editing `apps/web/package.json`, reinstall inside the web container.
- A dir named `coverage/` anywhere gets gitignored by the repo-wide pattern —
  check `git status` after creating one (needed a negation for
  `apps/web/src/app/api/proxy/attack/coverage/`).
- Known e2e flake: next-dev cold-compile timeouts under back-to-back load —
  a re-run passes clean; don't "fix" specs for it.
- Playwright traps: `getByRole` name matching is SUBSTRING (`exact: true` near
  sibling widgets); `check()`/`uncheck()` fail on auto-save checkboxes (use
  `click()` + `waitForResponse`); assert post-Run-AI state after
  `page.reload()` (StrictMode double-load race); no body click before the
  first Tab in skip-link tests.
- Demo stack: web :3000, API docs :8000/docs, Keycloak :8080, MinIO :9001,
  MailHog :8025. Logins: `admin@kentro.example` / `DemoPass!2026` (Kentro
  consultant), `client@atlas.example` / `DemoPass!2026` (Atlas tenant).
  Spec-created users need unique timestamped emails.
- LLM defaults to `fixture` mode: deterministic offline suggestions for all
  five AI purposes (D-017). Live mode (D-024/D-026): `SHIELD_LLM_MODE=live` +
  `SHIELD_LLM_PROVIDER=<anthropic|openai|gemini>` + that provider's key + a
  valid `SHIELD_LLM_MODEL` — a misconfigured live boot fails LOUDLY at startup
  (`live_llm_readiness()`), not on first Run-AI. Sprint 7 added `vertex`
  (ADC-based, no API key — D-029; GCP-validated 2026-07-15). Live tests are
  opt-in (`pytest -m live`, self-skip keyless).
- Real auth flows exist since Sprint 6 but enforcement is flag-gated, default
  OFF: `SHIELD_AUTH_REQUIRE_MFA` (TOTP challenge, D-027) and
  `SHIELD_AUTH_REQUIRE_EMAIL_VERIFY` (typed 403 on unverified login, D-028).
  `SHIELD_EMAIL_DELIVERY_ENABLED` turns on real SMTP sending (MailHog in dev,
  UI :8025); enabling it without an SMTP host refuses to boot. Flipping
  REQUIRE_EMAIL_VERIFY breaks every e2e sign-in (seeded/spec users are
  unverified) — enforcement is a deploy-time choice, not a dev default.

## How we collaborate (two developers + agents)

Dave (SpearheadAnalytica) and Gene (gene-png, repo owner). Git is the sync
mechanism; docs carry only what git can't show.

| File | Role | Who writes |
|---|---|---|
| `CLAUDE.md` | Durable facts, principles, gotchas | Both — append/refine in PRs |
| `CONTEXT.md` | Project status as of `main` | Updated as part of a PR, never outside one |
| `context/dave.md`, `context/gene.md` | Personal in-flight status: branch, what's mid-stream, next steps | Owner ONLY. Read the other's for awareness; never write it |
| `DECISIONS.md` | Append-only decision log (D-numbers) | Both — append in the PR that makes the decision |
| `docs/architecture.md` | Structure | Updated in the PR that changes architecture |
| `SPRINT_<n>.md` | Per-sprint plan (immutable once the sprint closes) | Sprint author |
| `SMOKE_TEST.md` | QA checklist — a box is checked ONLY if a green committed spec proves it, annotated with the spec filename | Both, honesty convention enforced |

Rules of the road:

- **Never commit directly to `main`.** Branch + PR, even for small fixes.
- **Write rich PR descriptions** (see PR #16 for the format: summary, task
  table, test plan, known follow-ups). The other person's agents orient from
  `gh pr view` — a good body saves them reading your whole diff.
- Conventional commits; end commit bodies with the model's co-author line.
- To see what your collaborator is doing: `gh pr list` + their `context/*.md`
  — not their unmerged branches.
- `.claude/sprint-queue.json` is machine-local loop runtime state (gitignored).
  Staged sprint queues (`.claude/sprint-queue.sprint-<n>.json`) ARE committed —
  they're the plan of record.
- **Sprint loops are launched by the human dev at the keyboard, never by an
  agent.** Agents plan the sprint, stage the queue, and merge the planning PR;
  the dev walks the launch checklist and starts `/loop-sprint-cron` themselves
  (the cron is session-scoped and needs babysitting only a human can commit to).
- **Sprint plans get a read-only Codex review before the planning PR merges**
  (since Sprint 8): `npm i -g @openai/codex`, `codex login`, then
  `codex exec --sandbox read-only` with the draft plan + pointed questions.
  Adopted/rejected findings are tabled in the planning PR body. Codex is a
  reviewer only — it authors nothing.
- Never commit: credentials, tokens, `.env`, `e2e/artifacts/` binaries.
