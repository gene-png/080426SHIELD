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
- Seed: `docker compose exec -T api python scripts/seed_demo.py` — **NOT
  idempotent, despite what it prints (#65).** The guard is "does ANY `Service`
  row exist, for any tenant" — one service minted by an e2e spec aborts the
  whole seed with "Services already present; skipping seeding." and exit 0. A
  drifted dev DB therefore can never be repaired by re-seeding; the only
  recovery is `docker compose down -v`. CI never hits this because its runners
  start with empty volumes, so CI stays green on specs that cannot run
  locally.

## Environment gotchas (learned the hard way)

- **next dev hot-reload does NOT fire through the Windows bind mount.** After
  ANY `apps/web` source edit: `docker compose up -d --force-recreate web`
  (~10–20s) before e2e. In-container touch/restart does not help.
- **`up -d --force-recreate web` silently recreates `api` too**, because `web`
  `depends_on` it and compose reconciles the dependency — so api picks up
  whatever the root `.env` says *at that moment*. This bit during W4: api had
  been deliberately recreated in `fixture` mode, `.env` was later restored to
  `live`, and a routine web recreate flipped api back to live with an invalid
  key, 502-ing every Run-AI. "The container keeps the mode I recreated it with"
  is only true until the next `up` touches it. After changing `.env`, or when
  you need a specific mode to hold, recreate `api web` together and re-check
  `docker compose exec -T api sh -lc 'env | grep SHIELD_LLM_MODE'` — don't infer
  it from what you set earlier.
- **A new migration does NOT reach the dev Postgres on its own, and no backend
  test will tell you.** Every pytest fixture points `DATABASE_URL` at its own
  SQLite file and runs `command.upgrade(cfg, "head")` itself, so a new column is
  present in every unit test while the running dev database is still on the
  previous revision. The model has the attribute, Postgres does not, and the
  first thing to notice is an e2e failing with `An internal error occurred` over
  a 500 — `psycopg.errors.UndefinedColumn` in `docker compose logs api`. Run
  `docker compose exec -T api sh -lc "cd /app && alembic upgrade head"` after
  adding one; `alembic current` tells you where the dev DB actually is. (0042
  cost an e2e run diagnosed as a spec regression before the logs were read.)
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
- Tailwind `outline-hidden` sets `outline-style: none` and CANCELS a focus
  ring even when `focus:outline-2` / `focus:outline-brand-500` also apply —
  the width and colour land, the style does not. Remove the class; don't
  layer over it. A11y assertions should pin the *rendered* outline width, not
  just that focus moved (a focus move with no visible change reads as dead).
- A spec that self-skips on a data precondition is UNTESTED, not passing. `s34`'s
  Run-AI-guard test skipped every standalone run (the seeded service was
  released, so the button was disabled) and hid a real fail-open defect until the
  first full-suite run. **Fixed 2026-08-07 (PR #19):** it now mints its own
  tenant + ATT&CK service + DRAFT assessment, so `readOnly` cannot be true and
  the skip became an assertion. The general rule stands — when a `test.skip(...)`
  guards a spec, seed the precondition instead of branching on it. The tell that
  it was worth doing: on the day of the fix the seeded assessment happened to be
  DRAFT, so the spec "passed" while proving nothing about the guard.
- **Author AI fixtures from what the PROMPT says, never from what the parser
  expects.** A fixture hand-written against the parser's own field names agrees
  with the parser *by construction*, so it can never express the one failure that
  matters — the model and the code disagreeing about a key. Whoever writes it
  already knows the answer the parser wants, and encodes that answer. Copy the
  keys out of the prompt text (and out of a real logged response where one
  exists); if the prompt says "Policy and Process" while the example JSON says
  `policy`, that discrepancy is the test case, not a detail to normalise away.
  This shape has now surfaced independently several times — the Sprint 3 T0
  drift, `mitre_map`'s fixture, the Risk Register enum mismatch, and W1's
  `unknown_field` (2026-08-09), where a green suite certified "3 of 3 applied,
  nothing dropped" over three lost scores per row. Corollary: **fixture mode
  cannot exercise drop/rejection counters at all** — the fixtures echo the
  payload keys back verbatim, so those paths need synthetic unit tests and a
  live run, and a green e2e proves nothing about them.
- **A guard against DOUBLE-counting will quietly become a guard against counting
  at all.** Twice in W1's CSF step, a conditional added so a value would not be
  charged on both sides of an invariant turned into a path that recorded
  nothing: `if not fields and not unknown_fields` let one unrecognized key
  suppress a full-row charge, and `if recognized_values:` suppressed the
  row-level record whenever every field was also misnamed — so an entry naming
  an unseeded tier reported a field-name curiosity and never said the tier does
  not exist. Both were caught by the round AFTER the round that added them.
  The shape to watch: a conditional whose false branch drops the record instead
  of emitting it under a different reason. Make the false branch emit something —
  a zero-value record that names the fault is honest, and silence never is.
- **A rule you have rewritten three times is a design problem, not a bug list.
  Enumerate the state space instead of patching the case in front of you.** W1's
  ZT run-AI severity rule was wrong in three consecutive adversarial rounds, and
  every time the fix was correct for the case that prompted it and wrong for a
  case nobody had listed: round 3 made a total loss alert and thereby shouted
  over an all-by-design-skip run; round 4 fixed that and thereby marked a
  wholly-lost response "done"; each round's tests covered the state it had just
  fixed. The tell is not the defect count, it is that the same predicate keeps
  changing shape — `applied === 0`, then `applied === 0 && failed.length === 0`,
  then `applied === 0 && lostValues > 0`. When you see that, stop adding
  conditionals and write the truth table: the inputs here were four booleans, so
  the whole space was thirteen renderable states and fits in one table-driven
  test. Do the matrix FIRST, then change the logic — a matrix written after the
  fix only pins the fix.
- **A test that supplies its own expected value — or its own precondition — from
  the thing under test cannot fail.** The AI-fixture rule above is one instance
  of this; this is the general shape, and it turned up twice on 2026-08-18 in
  code that had already passed review. `tests/unit/test_csf_ai_contract.py`
  builds its "prompt-compliant" response out of `_PARSER_ROW_KEYS` — the
  parser's own constants — so it agrees with the parser by construction and
  cannot see the prose/JSON drift the `csf_score` prompt actually carries, which
  is the one thing a contract test exists to catch. `test_deliverable_release.py`
  writes `parent_version = 1` by direct SQL and *then* re-releases, so it proves
  the flip works given a link while the production claim under test — that
  re-releasing establishes the link — is false for every multi-version service
  (#59). Both were green; neither could ever have been red. The tell: the test
  and the code read from the same constant, or the test's setup performs the very
  step the code is supposed to perform. Derive the expected value from the SPEC —
  the prompt text, a real logged response, the documented behaviour — and let the
  setup build only the world, never the outcome.
- **Changing user-facing copy for precision silently breaks whatever asserts it.**
  W1's panel line went from "suggested values" to "suggested **score** values"
  because the counts cover scoring rows only. The vitest was updated in the same
  pass; `s7`'s regex was not, so the one end-to-end check of the feature could
  never match — and it fails as `element(s) not found`, the symptom this file
  already records being misdiagnosed as a slow page and "fixed" with a longer
  timeout. When you reword any string a spec matches, `grep` the exact old
  phrase across `e2e/` and `apps/web` before moving on; three independent
  reviewers each found this one, and no gate did.
- **`int()` is not a validator, and neither is `float()`.** `int(True)` is 1,
  `int(1.9)` is 1, `int("2")` is 2. A coercion in a validation path writes a
  value the model never sent, reports it as applied, and records nothing —
  silent handling inside the code meant to end silent handling. Parse to a
  number, judge RANGE first (so `3.9` reports as out-of-range rather than as a
  fraction), then reject anything not whole. Accept `"2"` and `2.0`: refusing a
  value the model plainly meant is the same defect facing the other way.
- **A success record must be written where the success is, not before it.**
  Anything that says "this happened" — an audit row, a ledger row, a log line
  claiming `applied=N` — belongs after the commit or guard that makes it true,
  or it will eventually assert something the database does not contain. Three
  instances so far: N-019 (`llm_calls` records 0 tokens for failed calls that
  logged `charged_likely: true` — the money was spent and the ledger says zero),
  #47 (`llm_calls` records COMPLETED for a response that was rejected after
  parsing), and W1's accounting log, which claimed `applied=N` above the D-031
  re-read and so reported values applied for transactions that then rolled back.
  When adding any "it worked" record, find the line that makes it true and put
  the record below it.
- **A defect found in one service exists in its twins until you have checked.**
  CSF, ZT, ATT&CK, Tech Debt and Risk are five copies of the same shapes, so a
  fix filed against one is a fix owed by all of them. #75 was filed against ZT
  and fixed there; CSF truncated identically, through the same
  `DEFAULT_TOP_N = 20`, in the same three renderers, and the first
  implementation left it — inside the PR that was also fixing #79, which exists
  *because* an earlier change fixed one surface and not its twin. The same round
  found `_zt_gap_total` untouched twelve lines below the `_csf_gap_total` that
  was fixed. Half-fixes are worse than none here: raising CSF's target to the
  client's tier increases its gap count, so leaving the disclosure out hid MORE
  than before the "fix". Before opening a PR, grep the sibling services for the
  function you just changed, and when you deliberately leave a twin alone, say
  so in the code — an unstated exemption reads as an oversight to everyone who
  finds it later, including you.
- **Verify each assertion red-on-revert, one fix at a time.** A suite that goes
  green after a change proves the change did not break anything; it says nothing
  about whether the new tests can fail. Revert each fix individually and confirm
  its own test fails with the message you wrote for it. In the export trio this
  turned four green tests into four discriminating ones and caught two more
  instances of the #72 pattern (the eighth and ninth) — one where `str(count) in summary` was satisfied
  by an unrelated coverage fraction (`106/106 subcategories scored` contains
  `106`), and one where an entire keyword argument was deletable with the whole
  suite passing. Both were written by someone who had logged that pattern the
  same day, which is the point: knowing the shape does not prevent producing it,
  only checking does.
- **Assert what must APPEAR before what must not.** `toHaveCount(0)` on a page
  still mid-fetch passes vacuously — the element it forbids simply has not
  rendered yet. Wait on the positive state first (`toBeVisible`), then assert the
  absence; by then the page has settled and the check means something. s40's
  no-client assertion passed this way while the page underneath was still
  printing the exact error it forbade.
- **If a page's heading renders in every state except the failure one, "heading
  visible" silently becomes a proxy for "the page works".** `/admin/deliverables`
  early-returned a bare error card, so a failed fetch dropped the `Deliverables`
  heading; s40 waits on that heading, so a real 400 surfaced as "element(s) not
  found", was read as a slow page, and the timeout got raised instead (CI red on
  main from 2026-08-07). Restoring the header alone would then have turned s40
  green over a page showing nothing but `Failed to load deliverables (400).` Fix
  both ends: render the page identity in EVERY branch, and make the spec assert a
  state only a working page can reach. Download the CI artifact
  (`gh run download <id> -n playwright-report`) — `error-context.md` carries the
  failing page snapshot and ends this class of argument in one read.
- **Before naming a new e2e spec, `ls e2e/smoke`.** Phase D added
  `s37-admin-deliverables` and `s38-help` alongside the existing
  `s37-security-signoff` and `s38-progress-stages` — Playwright does not care, so
  nothing failed, and the collision was only caught while writing docs. Renamed to
  `s40`/`s41`. `s12` still carries a genuine pre-existing duplicate.
- **Playwright's `innerText` returns CSS-TRANSFORMED text.** A heading styled
  `uppercase` reads back as `"ACTION REQUIRED (7)"`. Use `textContent` when
  asserting wording — that is also what the accessible name is computed from, so
  it is what a screen reader announces. Asserting `innerText` pins the styling,
  not the copy.
- **A count rendered inside a heading changes its accessible name.** `<h3>Action
  required <span>(2)</span></h3>` has the name `"Action required (2)"`, so an
  exact `getByRole("heading", { name: "Action required" })` misses. Keep the count
  in the heading (a screen-reader user should hear it) and match with an anchored
  regex.
- **`.next/types` survives a branch switch and breaks `tsc`.** After checking out
  a branch without a route another branch added, `tsc --noEmit` fails with
  `Cannot find module '../../src/app/.../page.js'` from the stale generated
  validator. `rm -rf apps/web/.next/types` then recreate web. It is a cache
  artifact, not a type error — do not "fix" the code.
- A React hook that returns `null` for BOTH "still loading" and "request failed"
  makes its callers conflate the two. Anything gating on that null fails open the
  moment the box is slow — expose an explicit phase instead.
- A `fetch` Response body can be read ONCE. An error path that tries
  `res.json()` and then falls back to `res.text()` throws "body stream
  already read" and masks the real status — this hid a 404 behind a confusing
  error in all six `lib/*/client.ts` wrappers until the 2026-08-04 fix pass.
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
| `DELIVERY_PLAN.md` | Path to MVP: order, status, blockers, sizes. The **MVP completion path** section is LIVING — update an item's status in the PR that lands it, never afterwards. Sprint sections below it are historical | Both |
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
