# SPRINT 4 — Framework majors + multi-provider LLM

_Branch: `feat/majors-providers-sprint-4` (from `main` post-#26). Queue:
`.claude/sprint-queue.sprint-4.json` (copy to `.claude/sprint-queue.json` to
launch). Driver: `/loop-sprint-cron`. Created 2026-07-09 after Sprint 3
(PR #26) merged. NOT YET LAUNCHED._

## Sprint goal

Two themes David set explicitly:

1. **The D-018 framework-majors bundle** deferred from Sprint 2/3: Next 15,
   React 19, Tailwind 4, ESLint 10, Node 22 — each landed separately with the
   full e2e suite as the regression net, ending at **zero high/critical
   audit findings** at root and in `e2e/`.
2. **Multi-provider LLM egress** (David 2026-07-09: "do we have to use
   anthropic?"): implement OpenAI and Gemini adapters behind the existing
   single redacting egress client. The seam already exists — Master Spec §4.4
   mandates an env-configurable provider, `config.py` already types
   `shield_llm_provider` as
   `anthropic|openai|azure_openai|bedrock|gemini|local`, and
   `llm.py:_build_provider` fails loudly for anything unimplemented. This
   sprint makes `openai` and `gemini` real; the rest stay loud errors.

Plus the loop-hygiene fix Sprint 3's red CI proved necessary: in-container
ruff/black don't see the ROOT `pyproject.toml` config, so the loop shipped
lint the PR run caught (fixed manually as `753d765`). T0 closes that gap
before anything else lands.

## Prerequisites / launch checklist (human)

1. Merge the sprint-4 planning PR (this doc + queue + SMOKE_TEST §10
   check-off).
2. `git checkout -b feat/majors-providers-sprint-4 main` BEFORE the first fire.
3. Archive the old runtime queue
   (`mv .claude/sprint-queue.json .claude/sprint-queue.sprint-3.done.json`),
   then COPY `.claude/sprint-queue.sprint-4.json` to
   `.claude/sprint-queue.json`; set `working_dir` + `expected_gh_user` for
   your box.
4. Invoke `/loop-sprint-cron`.
5. **SMOKE_TEST §14 (live AI)** is David's pending item and is independent of
   this sprint's launch. If the live run surfaces defects (redaction, response
   quality, `client_id` attribution), triage them INTO this sprint by
   appending queue tasks — don't wait for Sprint 5.
6. Needs-David, still open, NOT blocking: cloud/account/region decisions
   (gates the terraform/deploy/DR work, Sprint 5+); API keys if he wants a
   live smoke of the new OpenAI/Gemini adapters (unit tests don't need them).

## Environment facts the loop must know

All CLAUDE.md gotchas hold. This box: web on :3001 (root `.env` WEB_PORT);
e2e via the winget node.exe + `e2e/node_modules/@playwright/test/cli.js`;
Docker CLI needs the PATH export per shell; gh can silently flip to the
read-only EMU account — `gh auth switch --user SpearheadAnalytica` before gh
writes. Gates: pytest -m unit, web tsc, host prettier 3.9.4 — and after T0,
in-container ruff+black with the ROOT config. Sprint-3 lessons that bite here:
don't restart the api container while an in-container pytest is running
(SIGKILL 137); don't park on background monitors mid-gate — poll synchronously
to the end of the iteration. Framework bumps change `apps/web/package.json`:
reinstall INSIDE the web container, then `docker compose up -d
--force-recreate web` before any e2e.

## Tasks

### T0 — Lint-gate CI parity (do first; protects every later commit)

Sprint 3's only red CI was 6 ruff errors the loop never saw: CI runs
ruff/black from a full checkout where config discovery walks up to the ROOT
`pyproject.toml` `[tool.ruff]`; the api container mounts only `apps/api`, so
in-container runs silently used defaults. Fix so the loop's gate equals CI:
preferred — add a read-only compose mount of the root config into the api
service at `/pyproject.toml` (parent of `/app`, so ruff/black discovery finds
it naturally); fallback — gates `docker cp` the file in first. Then (a) append
`ruff check --no-cache .` + `black --check .` (in-container, from `/app`) to
the `gates` array of the RUNTIME queue and to this staged queue's
documentation, (b) record the command in CLAUDE.md, (c) prove parity by
showing the gate now reproduces the exact rule set CI ran (e.g. temporarily
revert `753d765` in a scratch copy and watch the gate catch it). Verify:
gate red on a seeded violation, green on main.

### T1 — Next 15 + React 19

The core bump; they go together (Next 15 pairs with React 19). Bump `next`,
`react`, `react-dom`, `@types/react`, `@types/react-dom`,
`eslint-config-next`; run the official codemods (`npx @next/codemod@latest`);
review breaking changes that touch us: async request APIs
(`cookies()/headers()` — the proxy routes use them), caching-default changes
on fetch/route handlers (the app relies on dynamic rendering — verify each
`app/api/proxy/*` route), `next.config.js` option renames. **KNOWN RISK:**
`next-auth` 4.24.x peer-depends on next 12–14; verify actual runtime behavior
on 15 early. If it genuinely requires the Auth.js v5 migration (new API
surface, session callback changes), HALT with a written diagnosis — that
migration is a Dave-decision, not a loop-decision. Reinstall in-container +
force-recreate web. Gate: web `pnpm build` in-container AND the FULL e2e
suite green — it exists for exactly this task.

### T2 — Tailwind 4

CSS-first configuration (`@theme` in CSS replaces most of
`tailwind.config`), new `@tailwindcss/postcss` plugin, breaking utility
renames. `packages/design-system/src/tokens.css` custom properties must
survive (the s16 axe sweep asserts the `--ink-tertiary` contrast fix from
Sprint 2 T4). Verify: visual sanity via the full e2e suite + s16 axe green;
grep for removed utilities (`shadow-sm` renames etc.) across
`apps/web/src` and `packages/`.

### T3 — ESLint 10 (flat config)

eslintrc is gone in 10: migrate `apps/web` to `eslint.config.js` flat config
with `eslint-config-next`'s flat export (bumped in T1). Keep rule parity —
diff `eslint --print-config` before/after on a representative file. CI web
job runs eslint; it must stay green with no rule losses silently accepted
(document any intentional rule change in the commit body).

### T4 — Node 22

Bump `node:20-bookworm-slim` → `node:22-bookworm-slim` in the three
`apps/web/Dockerfile` stages and `node:20-bookworm` in `docker-compose.yml`;
add/refresh `engines` in the web package.json; bump CI `setup-node` versions
and the ONBOARDING.md instruction (host Node LTS). Rebuild web image,
reinstall, full e2e. Low drama, but do it AFTER T1–T3 so a Node-related
failure isn't confounded with framework breakage.

### T5 — Dependency audit to zero

After T1–T4: `pnpm audit` at root and `npm audit` in `e2e/` must show **0
critical and 0 high**. The 17 root findings as of Sprint 3 close were all
`next <15.5.16` (resolved by T1) except dev-transitives (js-yaml, postcss,
uuid) — bump or override those (root `pnpm.overrides`), and document any
deliberately-open moderate/low findings in the commit body. Also review
`.github/dependabot.yml`: majors stay suppressed (D-018 posture unchanged —
majors are sprint-planned; this sprint IS that plan executing).

### T6 — Multi-provider LLM: OpenAI + Gemini adapters

Implement `OpenAIProvider` and `GeminiProvider` in `app/ai/llm.py` beside
`AnthropicProvider`, selected by `_build_provider` on
`settings.shield_llm_provider`. Ground rules:

- **The egress contract is untouched.** Redaction, the `llm_calls` audit row
  (provider + model columns already exist), `client_id` attribution (T5
  sprint 3), and "AI suggests, code computes" all live ABOVE the provider
  seam — adapters only translate prompt+payload → provider API → text back.
- **Prefer thin `httpx` adapters** (httpx is already a dependency; both
  chat/completions and generateContent are simple REST for our use) over
  adding SDK dependencies; if an SDK is genuinely cleaner, lazy-import it the
  way `AnthropicProvider` does so fixture/test paths never load it.
- Config: `openai_api_key`, `gemini_api_key` settings (empty default);
  constructor raises the same loud RuntimeError as Anthropic when the
  selected provider's key is missing. `shield_llm_model` stays the single
  model knob — document per-provider examples (`gpt-*`, `gemini-*`).
  `azure_openai`/`bedrock`/`local` remain loud not-implemented errors.
- Unit tests per adapter with monkeypatched httpx (request shape: model, max
  tokens, the redacted payload embedded; response parsing; token-count
  extraction where the API reports it; HTTP error → typed failure, llm_calls
  row status=failed — mirror the existing Anthropic tests). NO live calls in
  tests or CI.
- Fixture mode stays the default and stays deterministic (D-017 untouched).
- Docs: README AI section + `docs/architecture.md` AI flow get a provider
  matrix (implemented vs planned); SMOKE_TEST §14 rewritten provider-agnostic
  (set `SHIELD_LLM_PROVIDER` + that provider's key). Append a DECISIONS entry
  (next free number — verify against the log, D-024 expected) recording the
  posture: provider env-configurable per spec §4.4, fixture default, FedRAMP
  deployments pick the provider inside their authorization boundary.

### T7 — Wrap-up

- SMOKE_TEST sync for anything this sprint changed (§14 provider-agnostic
  wording lands in T6; verify).
- CHANGELOG `[3.1.0]` (majors justify the minor bump) with per-task entries.
- Full exit gate set: full e2e, pytest -m unit, tsc, prettier, and the new
  T0 ruff/black gate. Overwrite CONTEXT.md with the end-of-sprint snapshot.

## Definition of done

- Web stack on Next 15 / React 19 / Tailwind 4 / ESLint 10 / Node 22; full
  e2e suite green on the new stack; `pnpm build` green in CI.
- `pnpm audit` (root) and `npm audit` (e2e/) each report 0 critical / 0 high.
- `SHIELD_LLM_PROVIDER=openai` and `=gemini` construct working adapters under
  unit test; unimplemented providers and missing keys fail loudly; fixture
  default unchanged; DECISIONS entry appended; docs show the provider matrix.
- Loop lint gate proven equal to CI's ruff/black run (T0), present in the
  runtime queue gates, and green at sprint close.
- Every commit conventional and task-scoped; CONTEXT.md snapshot written.

## Explicitly out of scope (Sprint 5+ / needs-David)

- Client-facing features: deliverable release flow, /home value loop, POA&M
  step, redaction preview gate, /admin/audit viewer (audit §4c — Sprint 5).
- infra/terraform, deploy runbook, backup/restore drill — gated on David's
  cloud/account/region decisions.
- Real MFA + email-verification flows (flags currently fail loudly at boot,
  D-020); Auth.js v5 migration unless T1 forces the question.
- `azure_openai` / `bedrock` / `local` LLM adapters — stay loud
  not-implemented until a deployment needs one.
- DoD 152-activity catalog completion; i18n implement-or-rescind decision.
