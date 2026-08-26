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
- **Withholding a value from a RATIO can raise it. Check which side of the
  fraction you took it out of.** #102 withholds a technique whose evidence is
  unconfirmed, and the obvious reading — "it is uncertain, so leave it out of
  both numerator and denominator, exactly as `unscored` already works" — shipped
  `gap` as withholdable. But `coverage_pct` is
  `(covered + 0.5·partial) / (covered + partial + gap)`, so a gap contributes to
  the DENOMINATOR only: ten covered beside ten gaps reported 50%, and flagging
  every gap reported **100%** with ten findings deleted. A run in which more
  evidence was doubted claimed twice the coverage. Only values that carry
  numerator weight can be withheld conservatively; withholding a pure-denominator
  value is a strictly optimistic move wearing a cautious one's clothes. And even
  for the rest it is not unconditional — withholding one `partial` from nine
  confirmed `covered` takes 95% to 100%, because narrowing a denominator changes
  what the ratio is a ratio OF. **A percentage over a withheld population is not
  self-describing: render the withheld count beside it, everywhere, and test that
  you did.** CSF, ZT and Risk all compute the same shape of fraction.
- **A rule that withholds a claim must separate "the evidence failed" from "no
  evidence was offered" — and if the store cannot tell them apart, fix the
  store.** #102's first predicate was "pending unless a confirmed citation backs
  the status", which is right for every AI-authored row and withheld every
  hand-curated one: a consultant typing `covered` into the matrix has made no
  inference, and the rule was about inferences. The heatmap reported zero covered
  over ten curated techniques with nothing in the product able to clear it, and
  the test that caught it (`test_heatmap_reflects_coverage_after_patches`)
  predated the feature by months. The fix was not a special case but a missing
  state: outcomes that resolve to NOTHING — a rejected citation, and a status the
  model cited nothing for at all — now get persisted rows of their own, because otherwise
  "we dropped the model's evidence" and "nobody ever cited anything" are the same
  stored bytes. **Before writing a withholding rule, ask what the absence of a
  record means, and make sure the writer records absence on purpose rather than
  by not writing.**
- **Missing data defaults to UNCONFIRMED, never to confirmed.** Standing rule,
  recorded after the third occurrence: D-054's nullable-vendor default, migration
  0044's NULL citations, and the fail-open draft of #102 that would have let an
  assessment whose citations were never checked read as fully confirmed because
  nothing on record contradicted it. Absence of evidence is not evidence of
  confirmation. The cost of fail-closed is rework a human can clear; the cost of
  fail-open is a false assurance already delivered to a client, and only one of
  those is recoverable. When fail-closed looks unaffordable, check the blast
  radius rather than assuming — for 0044 it was zero RELEASED assessments.
- **A guard that cannot read its input must FAIL CLOSED, and the tell is a
  positive-sounding message on an empty read.** `check_audit_evidence.py` shipped
  with `is_code_change([])` returning False, so an empty changed-file list printed
  "documentation-only change, exempt" and exited **0** — a green gate, with an
  encouraging sentence, from input that supported neither reading. Not reachable
  through its own workflow (`fetch-depth: 0` plus `bash -e` turn a failed diff
  into a red step), which is exactly why it survived review: the hole opens the
  day someone changes the checkout depth or adds a `|| true`.

  The general shape: a checker's "nothing to complain about" branch and its
  "I could not look" branch must not be the same branch. Every gate in this repo
  now returns a distinct non-zero (2) for unreadable input, separate from the 1 it
  returns for a real violation.

  **Recorded because this is the one case where writing it down demonstrably
  worked.** `check_issue_references.py` was written months later by someone who
  had read this entry, and its fail-closed path and the test pinning it were in
  the first committed version — the defect never existed in it. Set that against
  the closing-keyword rule three entries down, which was rewritten three times
  and violated a fourth. The difference worth noticing is not diligence: the
  fail-closed lesson is a rule about code you are *writing on purpose*, and the
  closing-keyword one is a rule about prose you are *not thinking about*. Only the
  second kind needs a machine.
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
- **Two gates now check whether a test can fail at all (#72, D-051).**
  `docker compose exec -T api sh -lc "cd /app && python -m scripts.check_test_integrity tests"`
  is a two-second static pass and **runs in CI before pytest** — it flags a test
  importing a private CONSTANT from the module it tests, and a containment
  assertion whose needle carries no literal text (`str(n) in blob` rather than
  `f"of {n} gaps" in blob`). Neither is forbidden; both demand a written
  `# test-integrity: <reason>` on the line or in the comment block above it, and
  an empty reason is not a reason. `scripts/mutation_sweep.py` is the other
  half — `--paths <files> --tests <target>` applies one change at a time and
  reports what no test noticed. Its `DropKeyword` operator exists because
  instance 9 was a deletable `targets=` argument, which off-the-shelf mutation
  tools do not model. Neither gate is enough to call #72 done: tier 1 cannot see a test whose
  SETUP performs the step under test, and a surviving mutant is a question
  rather than a verdict.
- **A snapshot beats a lock when the workflow legitimately mutates.** Tech Debt's
  APPROVED capability list stays editable until release, and that is on purpose —
  the security-classification confirm queue and excluded-row recovery are both
  first-class features. #32 sat deferred for months because the obvious fix,
  making APPROVED immutable, would have broken them. What was actually wrong was
  that the edit silently rewrote history: the ATT&CK allow-list read live rows,
  so a citation "confirmed against the approved list" was checked against
  whatever the list had since become. D-053 records the membership at approval
  instead (migration 0043) and lets re-approval refresh it, audited with both the
  new and replaced counts. When a guarantee and a workflow collide, ask whether
  the guarantee needs the state frozen or only needs to know what the state WAS.
- **Before reporting a sweep complete, name the SHAPE you searched for and one
  place it could hide that shares no vocabulary with the original.** Keyword
  sweeps keep coming back clean over live defects because the second instance
  was written by someone using different words. `risk.py` re-derived a
  gap comparison instead of calling `analyze_gaps` (#84); it also reimplements
  the ATT&CK citation drop as a two-line list comprehension with no counter
  (#132), found only because the sweep asked "where else does a model's string
  get compared to a stored value and the misses discarded?" rather than "where
  else is `_validate_tools` called?". Write the shape down in the PR body next to
  the grep you ran. If you cannot describe the defect without naming the function
  it was found in, you have not generalised it yet and the sweep will miss.

  **A worked example, because every entry above says to write a shape statement
  and none of them shows a good one.** From the `docs/security.md` honesty pass
  (PR #146):

  > A control stated in the present tense whose implementation is a deferral
  > comment, a client-supplied value, a header with no transport to enforce it,
  > or a function with no callers.

  What makes it work, itemised so the next one can be built the same way:

  - **It names four distinct failure modes, not one.** A shape with a single
    mode is usually just the found defect restated.
  - **It names no file, function or symbol.** Nothing in it points back at
    `security.md` or at the OWASP table that prompted the audit.
  - **Each mode is checkable by reading the implementation**, not by knowing the
    history — "a function with no callers" is a grep, "a deferral comment" is a
    comment saying the real thing is deferred.
  - **It found three defects outside the table it would have been natural to
    check**: the MIME sniff that trusts the client's `Content-Type`, the
    "HIBP top-100k" that is a three-entry deny list, and the `signed_url`
    credited as the artifact control with zero call sites. None of the three is
    in the OWASP table; a sweep phrased as "check the OWASP rows" finds none of
    them.

  The test of a shape statement is whether it could have been written **before**
  seeing the defect that prompted it. This one could.
- **A derived lookup key belongs in its OWN tier, below the authoritative one.**
  #33 finding 5 needed the resolver to recognise a tool under the placeholder the
  model was shown, so the redacted form was indexed as an alias — into the same
  `_by_norm` dict as real capability names. But a client's list can hold both
  spellings of one tool (the extractor redacts its own input, so
  `[CLIENT] SOC Platform` is the normal product of a later extraction), and the
  alias then collided with a real name: the only string the model can cite became
  `ambiguous`, and under the #102 withholding rule that pulled the technique out
  of the coverage denominator. Strictly worse than the defect being fixed. Real
  names are exact matches on what is stored; aliases are reversals of a
  transformation. Keep them in separate indexes and consult the authoritative one
  first, so an alias can only decide what the real key could not.
- **"Uses the same X as the Y path" is a claim to enforce by CALLING X, never by
  reimplementing it.** `_redacted_form` said in its docstring that it used "the
  SAME redactor the egress path uses" and then called `redact_org_name` — one
  rule out of the ten `redact_for_ai` runs in strict mode. The docstring even argued the point
  correctly ("a second copy would drift") while the code below it was the second
  copy. It was wrong immediately, not eventually: the address rule rewrote
  ordinary product names, so `Flowmon` egressed as a bare `[ADDRESS]` and had the
  exact disease the fix was for. (That over-match is fixed — #130 — so `Flowmon`
  now survives; the example is past tense and the lesson is not. A keyword
  followed by a number is still rewritten, so the case is still live.) When a
  function must agree with another function, import it and pass it the same
  inputs — including the MODE and any optional arguments, because a parity claim
  covers those too.

- **An over-match can be the ONLY thing covering a legitimate case. Before fixing
  one, check what it was accidentally catching.** `suite_pat`'s `\bFl` ate the
  `oor` in "Floor", and that bug was the sole reason `2nd Floor` got any
  redaction at all — the pattern has no branch for a value that PRECEDES its
  keyword, so tightening `Fl` silently removed coverage nobody knew existed.
  Nothing fails when this happens: no test knew the coverage was there, because
  it was never intended. The tell is that the "wrong" behaviour and the only
  correct behaviour for some input are produced by the same line. Cousin of the
  twin-sweep rule below — that one asks where else the defect is, this one asks
  what else the defect is doing. Concretely, on #130: `2nd Floor` → `2nd
  [ADDRESS]` (number left behind) and `3rd Fl` → no match at all, so the honest
  framing of the new branch was "adds coverage that never existed and closes a
  live leak", not "preserves coverage through a fix". Say which one it is; this
  repo has already been bitten by comments that were true only for the case they
  were written for.
- **A redaction/validation corpus drawn from your own assumptions cannot falsify
  them — and seed data is somebody's assumptions too.** #130 lived for months
  under a green suite because all 73 name-shaped strings in `seed_demo.py` and
  `fixtures.py` pass the address rule clean, so an address assertion built on
  seed data passes forever. Then, fixing it, a hand-written corpus of "real
  product names" certified a pattern carrying **six leak regressions**, because
  the author writes addresses correctly spaced and the failing class was
  malformed input (`PO Box99`, `Suite400`) that arrives from OCR and exported
  spreadsheets. This is #72's shape pointed at test DATA rather than test code,
  and the fix is the same as everywhere else here: enumerate the CLASSES and
  require a row per class, rather than adding whichever example you thought of
  last. The classes a hand-written corpus structurally cannot contain: malformed
  strings, `name + version number`, non-US locale variants, and strings that have
  already been through the pipeline once.
- **A table written FIRST is an independent specification. A table written
  AFTERWARDS is a transcript of what the rule does.** That single sentence
  explains D-058's own caveat, why 376 green cells certified a rule carrying
  nine live defects, and an 11x measured split. It is the enumeration rule above
  pointed at ORDER rather than at content: enumerating cases against a rule you
  have already written cannot falsify that rule, because the rule is where the
  cases came from.

  **Measured, not asserted** (2026-08-25, `apps/api/scripts/leave_row_oracle.py`,
  104 LEAVE rows, 22 guards). A LEAVE row asserts ordinary prose survives the
  redactor untouched. Disable the guard it was written to pin: if the row still
  passes, it was never testing that guard -- "the boundary held" and "no rule was
  ever interested in this string" are the same green.

  | Tables | In risk class | Pinning nothing |
  | --- | --- | --- |
  | Written before their pattern (#130, PR #141) | 53 | **2 (3.8%)** |
  | Written alongside/after their rule (item 10) | 38 | **16 (42.1%)** |

  Same corpus, same author, same file, same week. The only variable is whether
  the table existed before the code did.

  **The step, and it is a step rather than a gate**: any LEAVE table written or
  extended after its rule exists gets an oracle run before the PR, and rows that
  pin nothing are rewritten or reclassified. Scoring a row needs judgement about
  what it was written for, so the tool reports and a human decides. Exactly one
  property of it can fail on input nobody configured -- a table with no
  registered guards -- and THAT is gated
  (`leave_row_oracle.py --check-registry`, CI step "LEAVE-row oracle
  registry"), because otherwise a new table reports clean and the tool acquires
  the silent-success shape it was built to find.

  Three classes, and the third is derived rather than listed: a row that
  survives even with EVERY guard removed at once was never in the risk class
  (`Splunk Enterprise` contains no designator substring), so it is a
  **negative control by design** -- load-bearing against future change, and
  simply the wrong question for this oracle. Deriving that class rather than
  hand-listing it moved the headline from 29.8% to 19.8%; a hand-written
  exclusion list would have been one more enumeration, and would have read as
  special pleading around an inconvenient number.

  **Budget it.** Items 6 and 9 both fix existing code, so their tables land in
  the 42% regime by construction, not by bad luck. Forty seconds against that
  prior is the cheapest thing on the remaining path -- schedule the run rather
  than rediscover the need for it.

  **Residual, stated so it is examined rather than assumed**: the guard list is
  hand-built, so the tool is itself an enumeration of what its author thought of
  -- this entire lesson one level up. `unrelated` is therefore an UPPER BOUND
  with a known error direction: modelling more guards can only move rows out of
  it. The way out is deriving mutations from the pattern's own structure
  (alternations, named sub-patterns) instead of listing them by hand. Not built;
  the hand list found an 11x signal on its first run.
- **Sweeping for a defect's twins, grep the SYMPTOM as well as the call sites.**
  Grepping for callers of the function you just fixed finds every copy that went
  through that function and misses every REIMPLEMENTATION of it. #84 escaped the
  #73/#75/#79 sweep exactly that way: `risk.py` never calls `analyze_gaps`, it
  re-derives the comparison inline, so a complete call-site sweep reported clean
  over a file that computes client-facing risk findings against a hardcoded
  target. Grep for what the defect LOOKS like — the literal default values, the
  truncation constant, the magic number, the shape of the comparison. Concretely,
  on the trio: `grep -rnE "(maturity_tier|maturity_stage) *< *[0-9]"` returns
  `risk.py:177` on the first try, and `grep -rnE "is not None else [0-9]"`
  returns `risk.py:193`. Neither appears in any list of `analyze_gaps` callers.
  A reimplementation shares the symptom, never the symbol.
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

  **A revert that silently fails to apply reports the same green as a test that
  cannot fail — so prove the revert LANDED before you read its result.** The
  check produces the reassuring answer in both cases, and it is the answer you
  are hoping for, which is the worst possible combination. Concretely, on #130:
  a scripted `str.replace` of `_STREET_SEP` matched zero occurrences because the
  search string carried a real tab where the file has a literal backslash-`t`;
  `replace` does not raise on a miss, so the suite ran against the UNMODIFIED
  file and came back 111 passed. Written up, that would have read "verified
  red-on-revert" over a fix pinned by nothing.

  Cheap guards, in order of preference: `assert s.count(old) == 1` before
  replacing (a miss and an unintended double-hit both raise); `grep` the mutated
  line and read it back; or revert with `git` rather than a string edit. And
  treat "the revert produced no failures" as a claim about your tooling until
  proven otherwise — the first hypothesis is that the mutation did not land, not
  that the assertion is weak.
- **Replacing a character class with an enumerated one is a subtraction you must
  COMPUTE, not guess.** `\s` matches 19 horizontal characters. Narrowing it to
  "space, tab, non-breaking space" to stop a rule crossing newlines therefore
  dropped SIXTEEN more (U+2000-U+200A, U+202F, U+205F, U+3000, U+1680, U+001F) --
  and in the redactor that is a LEAK, not a residual: a street address separated
  by a narrow no-break space, which is exactly what PDF and Word extraction emit,
  egressed verbatim with no `address` key in `removed_counts`. Strictly worse
  than the over-match being fixed. The decision was framed as being about
  NEWLINES, so the replacement was written to solve newlines and nobody
  re-derived what else was in the class. Write it as the subtraction and let the
  language define the set (`[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]`), then pin BOTH halves as
  parametrised sweeps whose parameters come from somewhere other than the thing
  under test. Note `[^\S\r\n]`, the idiom everyone reaches for, is also wrong -- it
  still crosses `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, U+2028 and U+2029.
- **An escape sequence written into prose becomes an invisible control byte, and
  CI now checks for it** (`apps/api/scripts/check_no_control_chars.py`, the
  "control-character sweep" step). `\b` in a non-raw string is a BACKSPACE; `\v`,
  `\f` and `\u2028` are equally invisible. This repo writes prose ABOUT regexes
  constantly -- decision records quote the patterns they decide -- so
  `DECISIONS.md` acquires an empty code span and a control byte inside a sentence
  explaining word boundaries, and nothing notices: the file parses, prettier
  passes, the diff looks fine. **Four instances on one branch**: two pre-existing,
  one in the commit fixing those two, and one in the CI comment introducing the
  gate, in the sentence describing the defect. The last was caught by the gate on
  its first run. That is the argument for mechanising it rather than writing a
  fifth paragraph -- the same argument the closing-keyword check settled.
- **Changing a parametrisation invalidates every count derived from it, and the
  count is usually in another file.** Narrower and more checkable than "re-check
  your numbers": the trigger is mechanical. PR #141 stated the address truth
  table had 153 cells. The fix for a review finding was to parametrise two
  sweeps per separator as well as per character — 7 sites x 19 horizontal and
  7 x 10 vertical — which multiplied the collected count several-fold. (The
  number that stood here was 327; it was 376 within the week and 410 after
  item 10, which is why it is no longer written down. Run the collector.)
  The stale
  153 shipped to `main` in `CONTEXT.md` and `DECISIONS.md` and was found a PR
  later. What caught it was **re-counting**, not re-reading: the sentence still
  parsed, still looked deliberate, and was wrong by a factor of two.
  The number goes stale at the exact moment the change is most obviously
  substantive, which is when attention is on the code and not on the prose two
  files away. So: after touching any `@pytest.mark.parametrize` argument, grep
  the repo for the old count before committing.
- **A CORRECTION PARAGRAPH OUTLIVES THE NUMBER IT CORRECTED, and then certifies
  a wrong one.** The re-count trigger above says a changed parametrisation
  invalidates counts in other files. This is its nastier sibling: the prose
  written to explain WHY a number is trustworthy goes stale with the number,
  while still reading as a guarantee. A bare stale count invites a check. A stale
  count under "read live from GitHub, not carried forward" ends the check.

  Instances in one week — **five**, of which three are in the files that
  document the rule. An earlier draft said "four" and was left saying four
  when two more were added, which is this bullet's own defect for the SECOND
  time (it also shipped a wrong closure count). The number is written out
  here only because the list is immediately below it; if it grows again,
  delete the count rather than update it:

  - `context/gene.md` — "Open mvp-blocking issues (20)" under a paragraph
    certifying it freshly read. EIGHT issues closed in the merge that carried
    the file; the heading did not move and the certificate stayed.

    An earlier draft of this very bullet said NINE -- the count of everything
    closed since the heading was written, which silently included one closed
    by a different PR. The lesson's own defect, in the paragraph introducing
    the lesson, caught by review rather than by the author. Derive a closure
    count from `gh pr view <n> --json closingIssuesReferences`, not from
    memory of what happened.
  - `DELIVERY_PLAN.md` — a paragraph explaining a corrected total said "today's
    12-18" and went stale in the same commit that changed the total to 10-15,
    written by the author applying the rule.
  - `leave_row_oracle.py` — a docstring recording that its own counts must be
    re-counted on every guard-list change, quoting counts that were two guard-list
    changes old.
  - **`CLAUDE.md` itself, three bullets above this one** — the re-count-trigger
    bullet said the collected count was **327**. It was 376 by the time that
    sentence shipped and is 410 now. A bullet about counts going stale in
    another file, carrying a stale count.
  - `tests/unit/test_redact_address_matrix.py` — "(The count is 327 now…)",
    present tense, in the file that PRODUCES the number.

  One further citation was drafted and withdrawn: `redact.py:82`, a note about an
  earlier note about `\s`. It is a real defect and it is a DIFFERENT one — a
  scope over-claim that was wrong on arrival rather than a number that went
  stale — and it belongs under the narrower-rule bullet below. Filing it here to
  pad the list would have mislabelled it, which is what makes the next sweep
  miss.

  The countermeasure is not more care, because in three of four the author was
  actively applying the rule. It is: **when you write a sentence certifying a
  derived value, put the value where a gate can read it, and let the sentence
  point at the gate rather than restate the number.** `check_plan_totals.py`
  reads the table, not the prose, which is why the plan's total is the one figure
  in this repo that has never shipped wrong.

- **When a guard keys on a predicate, sweep every call site of the predicate,
  not every caller of the guard.** `is_production()` has four call sites and all
  four mean "is this anything other than a developer's machine" while asking "is
  this production". Two are startup guards (redaction-off, placeholder signing
  secret); two publish Swagger UI and the full OpenAPI schema. `Environment` is a
  three-member literal, so `staging` gets all four. Fixing three of four leaves
  the shape alive, and the tell that nobody swept is a reassuring comment: the
  `# noqa` beside the signing secret reads "refused in prod via
  assert_safe_for_runtime" — true, and the reason the next reader stops looking.
  Filed as #142.
- **Before writing a gate, enumerate its SILENT-SUCCESS branches — every path
  that exits 0 without having looked — the way you enumerate a truth table before
  a regex.** The fail-closed rule further up is about the branch you write on
  purpose. This is about the branches you do not notice you wrote, and the
  distinction matters because the second kind has now happened three times in
  this repo's own tooling, every one of them found in review rather than by the
  author:

  - `check_audit_evidence.py` — `is_code_change([])` returned False, so an empty
    changed-file list printed "documentation-only change, exempt" and exited 0.
  - `mutation_sweep.py` — `_run_tests` reports "killed" for any non-zero exit,
    and pytest exits non-zero for collection errors too, so a suite that never
    ran an assertion scored every mutant killed and printed "no surviving
    mutants". A tool for certifying that tests can fail, unable to notice that it
    could not itself fail. Fixed with a `BaselineNotGreen` check.
  - `check_plan_totals.py` — a table row whose estimate did not parse hit the
    same `continue` as the column-header row, so an annotated cell
    (`2-3 (needs-David)` — the house style one table up) was dropped from the sum
    in silence, and the cheapest route to green was to change the total to the
    short sum. The gate steering the author into the defect it exists to catch.

  Three instances, one shape: **"I could not look" sharing a branch with
  "nothing to complain about".** The rule against it was already written down
  when the second and third were produced, which is D-051's own finding — so the
  countermeasure is not more resolve, it is a step in the procedure. Before the
  first line of a new checker, list every `return 0` / `continue` / `pass` it will
  have and write beside each one what the input looked like. Any entry whose
  answer is "I don't know" or "there was nothing there" is the bug, and it is
  cheaper to find on that list than in review.
- **A comment or message stating a rule NARROWER than the reader will assume,
  positioned exactly where they would go to check, is worse than no comment.**
  It is true, so nothing flags it; it is where you look, so it ends the search;
  and it reads as a guarantee rather than as a scope. Four instances, three of
  them in the redaction subsystem within two days and the fourth added later:

  - `# noqa: S105 - dev placeholder, refused in prod via assert_safe_for_runtime`
    beside the JWT signing secret. True. The guard covered one of three
    environments, and this sentence is why nobody checked the other two (#142).
  - `"SHIELD_REDACTION_MODE=off is forbidden when ENVIRONMENT=production"` — the
    runtime error the guard itself raises, naming a narrower rule than the one
    that should exist, in the string a developer reads while debugging it.
  - `_redacted_form`'s docstring claiming it used "the SAME redactor the egress
    path uses" while calling one rule out of ten. The docstring even argued
    correctly that a second copy would drift, directly above the second copy.
  - `redact.py:82` -- "Every separator in the module is now built from
    [`_HSPACE`]", itself written as a correction to an earlier note that HAD
    gone stale. `_RE_CONTACT_HINT` uses bare `\s` twice, and
    `check_separator_classes.py` cannot see it: that gate flags hand-ENUMERATED
    classes, not `\s`. Wrong on arrival rather than stale, which is why it is
    filed here -- it was withdrawn from the staleness bullet above and, for one
    draft, recorded in neither list. Tracked as **#158**.

  All four were found by reading the CODE and comparing, never by reading the
  prose — which is the only method that works, because the prose is accurate.
  The countermeasure is mechanical, not attentional: when a comment states a
  condition, read the condition it describes and check the two agree in SCOPE,
  not just in truth. And when you fix such a guard, fix its message in the same
  commit — an error string is documentation that a developer reads under
  pressure, and a stale one costs more there than in a doc.
- **Replacing a validator gives you a free ORACLE for exactly one round: the
  thing you are replacing.** Enumeration depends on imagining cases, and the
  cases you fail to imagine are precisely the ones that leak. Item 10 replaced a
  phone regex; the truth table's LEAVE half was carefully enumerated and its
  REDACT half was seven rows of one grouping, so four formats the OLD rule caught
  — `1-800-555-0199`, `1.555.867.5309`, `020 7946 0958`, and any number separated
  by a non-ASCII space — leaked silently, and `CAGE1ABC2` regressed the same way.
  Nobody imagined them; the adversarial reviewer found them by reading.

  The mechanical version costs nothing: **run the old rule and the new rule over
  the same corpus and diff their match sets.** Every input the old one caught and
  the new one does not is either an intended false-positive fix or a new leak,
  and you must classify each. It works for any validator, filter, guard or parser
  being replaced — and only for one round, because after the old one is deleted
  the oracle is gone. Capture the diff while you still have both.

  **Second example, same shape: a published standard is to a keyword list what
  the old rule is to a replacement pattern.** #139 asked which facility
  designators to add, and the honest answer to "which ones did I think of" is
  always "the ones I thought of". USPS Publication 28 Appendix C2 is the approved
  list of US secondary unit designators — 24 entries — so the question became a
  lookup. Of those, 7 were already covered, 8 were added, and 9 were excluded as
  ordinary English that takes a digit (`KEY`, `LOT`, `SIDE`, `REAR`, `FRNT`,
  `SPC`, `PH`, `LOWR`, `UPPR`). The table asserts every "covered" row actually
  redacts and every exclusion still does not, so the list is complete against a
  standard rather than against recall.

  It also gave the residual a better reason. `Level` is excluded not because
  "patch level 3 is inseparable from a floor" — a phrasing that invites the next
  person to attempt the separation and fail identically — but because **LEVEL is
  not on Pub 28 C2 at all**. That is the same scope call as the non-US postcode
  residual, with the same firing condition, so three residuals now share one
  reason and one trigger instead of three separate stories.

  This covers the half enumeration structurally cannot: enumeration finds what
  you thought of, the oracle finds what the previous author — or the standards
  body — thought of.
- **When testing ONE branch of a disjunction, assert the other branches are
  absent.** Not the #72 shape — removing every detector would fail the test — but
  the same practical result: the test passes and proves nothing about the thing
  it is named for. `_RE_CONTACT_HINT` matches an email OR a `--` delimiter OR a
  phone-shaped run OR a ZIP line. The fixture written to prove the phone branch
  handled non-ASCII separators contained `Arlington VA 22209`, so it passed on
  the ZIP branch while the phone branch was ASCII-only and broken. The gate found
  the defect; the test named for it never could have.

  One line fixes it: the phone fixture asserts the ZIP hint does NOT fire on it.
  Every multi-signal guard has this shape, and the more signals it has the more
  reliably a test of any one of them passes for free.
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

- **A closing keyword beside an issue number closes it — and CI now enforces
  this, so it is a check rather than a rule you have to remember.** GitHub's
  parser matches `fix(e[sd])?|close[sd]?|resolve[sd]?` followed by `#N` and does
  not read the words around it. `does not fix #NNN`, `partially fixes #NNN`,
  `Filed, not fixed: #NNN` and `not resolved: #NNN` all close the issue. Write
  `filed as #NNN`, `see #NNN`, or `tracked in #NNN` instead.

  **It reads three places, not one: the PR title, the PR description, and every
  commit message.** The description is parsed independently of the commits — the
  third accidental close in this repo came from a PR body while every rule up to
  then targeted commit bodies, and the squash commit contained no match at all.

  **Quotes, code fences and HTML comments are not exempt**, and in examples use
  `#NNN` — a placeholder with **no digits**. Not a made-up number: issue numbers
  only go up, so a keyword beside an invented number is inert today and live the
  day the repo reaches it. (This paragraph originally illustrated that with a
  literal number and thereby became a fifth instance, caught by the check rather
  than by a merge.)

  The mechanism is `apps/api/scripts/check_issue_references.py`, wired as the
  required check **"No accidental issue closes"**. If a close is intended, say so
  in the PR description — bare numbers, no `#`, because a marker containing the
  word "close" beside `#N` would itself be an instance of the bug:

      Auto-close-approved: <issue numbers, bare>

  **`Auto-close-approved:` authorises the guard; it does NOT close the issue.**
  Two different mechanisms, and it is easy to assume the line does both. GitHub
  closes an issue only on a real closing keyword beside the reference
  (`Fixes #NNN`); the `Auto-close-approved:` line exists solely so this repo's
  own check permits that keyword instead of rejecting it. A PR that has the
  approval line and no keyword merges without closing anything — which is the
  failure that leaves a fixed bug sitting open on the mvp-blocking list,
  asserting a defect that no longer exists. When you intend a close, write both
  and then confirm it took: `gh pr view <n> --json closingIssuesReferences`
  should name the issue before you merge.

  **Why this is mechanised rather than documented.** The same issue was closed by
  accident three times. Each fix was a better-worded rule; the second incident
  was the PR that documented the first, and the third was a sentence warning
  about the second. Three rounds of documentation produced a fourth incident.
  That is #72's finding applied to prose: discipline against a known shape has
  failed nine recorded times here, including instances written minutes after the
  rule was logged.
- **Run the adversarial reviewer, and record the audit in the PR body.**
  `.claude/agents/adversarial-reviewer.md` via the Agent tool. Run it before you
  open the PR where you can, and **again after any substantive change to the
  branch** — PR #29's plan records two consecutive patches that each looked done
  and each were wrong, both caught only by re-auditing while CI stayed green. A
  rule that fires once at open would have missed both.

  **Never a self-audit instead.** D-054's gate cannot tell the difference: it
  proves an audit was *recorded*, not that it happened. Three PRs and a
  cross-service sweep passed a required check that way before anyone noticed.

  **What the gate needs, so following this rule does not produce a red X.** The
  required check is **"Adversarial audit recorded"**
  (`apps/api/scripts/check_audit_evidence.py`), and it wants a literal section —
  prose describing an audit is explicitly not enough
  (`test_merely_mentioning_the_words_is_not_evidence`):

      ## Adversarial audit
      Findings: none
      Disposition: nothing to act on

  **Docs-only PRs are exempt from the gate and NOT exempt from this rule**, and
  the two are different things. The gate skips a pure-docs change deliberately —
  its own comment calls that "the one defensible skip". This rule still asks for
  the reviewer, because `CLAUDE.md`, `DELIVERY_PLAN.md` and `DECISIONS.md` are
  where wrong claims do their damage, and the review that produced this very
  bullet found eleven defects in two markdown files. Use judgement on a typo;
  do not use judgement on a document that states a number or a rule.

  **This rule is unenforceable, and unobservable, and it is written down anyway.**
  Nothing records whether the reviewer ran, or when. The gate reads a body and
  cannot see who wrote the findings. W8b — the reviewer as a CI job — is the
  mechanism that would bind it and is still deferred. So this is exactly the
  "discipline against a known shape" that D-051 says has failed nine times here,
  and it is weaker than the gate it supplements, because the gate at least
  produces a red X. It is here because the alternative is nothing, and because
  the cost of the last drift was measured rather than imagined. Do not read it as
  a mechanism.

  **What the drift cost.** Pointed at that sweep, the reviewer overturned **four
  of its six** "clean" verdicts, including one reported as "no twin" over a defect
  written up in `docs/plans/2026-08-08-cross-service-integrity.md` (F6) two weeks
  earlier and still live. The diagnosis is the reusable part: the sweep had
  generalised ATT&CK's *vocabulary* (`pending_review`, "withheld") instead of
  ATT&CK's *shape* — an aggregate applying an exclusion the per-row rendering does
  not. Grepping the word found nothing; the shape was in three services. A
  self-audit cannot catch that, because the blind spot and the reviewer are the
  same mind.

  Three things that make the run worth its cost:

  - **When the work is itself a review, a sweep or an audit, point the reviewer
    at the VERDICTS and the METHOD, not at the code.** A sweep that finds nothing
    is indistinguishable from a sweep that looked in the wrong places.
  - **Re-verify every finding before acting on it.** It runs read-only and
    executes nothing, so every claim is static reading, and it is confidently
    wrong often enough to matter — the review of this bullet marked one finding
    CONFIRMED that was simply wrong, because it could not read a GitHub issue.
  - **A finding it upholds is a result worth recording**, not a null. "The shape
    guard holds for all five jobs" is what told us to pin an invariant rather
    than fix it.

  **When the reviewer cannot run.** "Use judgement" is the gap this rule exists to
  close, so the cases are named and so is the person who may decide.

  Kinds of unavailable — **an open list, not an enumeration**, because the fourth
  one below is the case this repo has actually hit and the first draft omitted it:

  - **Absent** — the `adversarial-reviewer` agent type is not in the environment
    at all. Nothing to retry.
  - **Erroring** — it dispatches and fails, or returns nothing usable. Retry once.
    If it fails again, treat as absent.
  - **Timed out or killed mid-run** — retry once with a narrower scope (fewer
    files, one question). If it produces partial findings, record them **as
    partial**; a truncated run is evidence about the part it reached and says
    nothing about the rest.
  - **Not dispatched** — present and working, but you did not run it, because
    running it conflicted with something else. This is D-054's own recorded root
    cause: *"the agent resolved a conflict between 'do not invoke subagents
    unprompted' and §14 silently, in favour of not running it."* Say which
    instruction conflicted. Writing "absent" here is false and sends the next
    reader hunting an environment problem that never existed.
  - **Ran, but not against this change** — a stale tree, the wrong branch, a
    subset of the diff, or a run that exhausted its own context and returned a
    complete-looking report on the first few files. None of these times out,
    errors, or is absent; all of them produce a clean report that is true about
    what the reviewer saw and false about this PR. This is why the audit block
    carries a **`Scope:`** line — the reviewer is instructed to state what it
    examined and what it could not reach, and without a field to put it in that
    evidence is produced and then thrown away at the recording step.

  Anything else: describe it. The list is illustrative.

  **The audit section must not lie about which happened.** If the reviewer did not
  run, write `Findings: not run — reviewer absent` (or `erroring`, `timed out`,
  `not dispatched: <what conflicted>`). Never `Findings: none`. Those are different claims: "none" is a claim about the code,
  "not run" is a claim about the process, and the gate accepts both because it
  only checks that the lines exist. That asymmetry is precisely why the honesty
  has to be a rule rather than a check.

  **Who may decide a PR ships without it: the human dev at the keyboard, by name,
  recorded in the PR body.** Never an agent, never by inference from silence, and
  never the author of the code when the author is an agent — the same principle
  as sprint loops being launched by a human and never by an agent.

  **That authorisation is prose, and nothing checks it.** No script reads the
  line; nothing distinguishes a body where Gene approved from one where an agent
  typed his name. It is weaker still than it looks, because `enforce_admins` is
  false and both devs are admins — either of them can already merge past a red
  gate without writing anything at all. It is written down so it can be pointed
  at afterwards, not because it stops anything. **The checkable version, if this
  ever needs to be real, is a GitHub review approval** (`gh pr review --approve`)
  from the named human rather than a line of body text — that is attributable and
  visible to the API.

  A blocked PR waits, and the issue it belongs to gets a comment saying it is
  blocked on tooling rather than deprioritised, so it does not read as stalled.
  **The exception is a change the gate itself exempts and that states no number
  or rule** — a typo fix in prose. That is the "use judgement" case above, and it
  does not become a hard block just because the reviewer is away.

  This clause exists because the reviewer went absent for one turn immediately
  after PR #128 merged the rule above, and the rule had nothing to say about
  it. Dated by the PR rather than the clock on purpose: D-057 is dated the day
  it was written and the rule merged the next, so a reader comparing two dates
  sees a contradiction that neither file resolves.

  If running it ever conflicts with another instruction, **say so out loud rather
  than resolving it quietly** — that silent resolution is the exact failure D-054
  was written about, and it has now happened twice.

  (Decision recorded as **D-057**, which reverses part of D-054. Closes the
  `CLAUDE.md` half of #108; the other half — the gate's own source still saying
  it "only REPORTS" and citing D-051 — is untouched and still open.)
- **Never commit directly to `main`.** Branch + PR, even for small fixes.
- **An agent merges on green WITHOUT checking back, when all six hold.** Standing
  as of 2026-08-26, after three consecutive PRs came to the human for a decision
  the evidence had already made. Three of the six conditions are checkable and
  three are self-attested — see the note below the list, which an earlier draft
  contradicted from here:

  1. All seven CI checks green. (Five jobs in `ci.yml` — python, web,
     secret-scan, e2e, demo — plus two in `audit-gate.yml`. `mutation-sweep.yml`
     is schedule-only and excluded. **Re-derive this count if a job is added**;
     it is a hardcoded number in prose, which this file has a bullet about.)
  2. The adversarial reviewer ran **against the final state of the branch**, and
     whatever it found is fixed or filed, recorded with `Findings:` /
     `Disposition:` / `Scope:`. "Clean" means clean on the LAST run, not the
     first — item 10 would never have qualified under the first-run reading, and
     §14 already requires a re-run after any substantive change. Note the gate
     checks only that `Findings:` and `Disposition:` exist; it does not read
     `Scope:` and cannot tell whether the reviewer ran at all.
  3. `DELIVERY_PLAN.md`, `CONTEXT.md` and `context/<name>.md` updated **in the
     landing commit**, with any counts read live rather than carried forward.
  4. No migration.
  5. **None of the following paths**, which are the ones where a green suite
     proves least:
       * `apps/api/app/ai/` — the single egress path for all five services.
       * `apps/api/app/csf/playbook.py`, `app/risk/engine.py`,
         `app/zt/scoring.py` — the deterministic scoring engines. Core Principle
         1 says "AI suggests, code computes"; condition 5 named only the
         suggesting half for one draft, so a refactor of the 5x5 risk mapping
         would have merged unattended. #84 is on record as `risk.py` hiding
         exactly that.
       * any live LLM **prompt**, which is not confined to `app/ai/` —
         `app/tech_debt/extract.py:44` holds one, and fixture mode echoes payload
         keys back verbatim, so a prompt drift cannot turn CI red.
       * `apps/api/app/config.py` — the switch deciding whether the redactor
         may be disabled, and its default. **#142 lived here, not in
         `app/ai/`.** A PR widening `is_development()` reintroduces it while
         tripping nothing else on this list.
       * `apps/api/app/models/**` and `apps/api/alembic/env.py` — "no
         migration" (condition 4) is not "nothing under `alembic/`". A
         cascade rule or a column default changes stored behaviour without
         one.
       * `apps/api/tests/**` and `e2e/**` — weakening a test satisfies
         condition 1 more directly than editing a workflow does, and this
         repo has thirteen recorded instances of tests that could not fail.
       * `apps/api/scripts/seed_demo.py` and `scripts/demo-reset.sh` — both
         drive CI jobs, and seed data being clean is why #130 survived months
         of green.
       * the deterministic surfaces the first draft of this list missed:
         `app/attack/coverage.py`, `app/csf/scoring.py`, `app/zt/maturity.py`,
         `app/tech_debt/security_scope.py`, `app/risk/exporters.py`. Naming
         one file for three of five services and none for ATT&CK or Tech Debt
         was a half-sweep — the defect this file has a bullet about.
       * `apps/api/scripts/check_*.py`, `apps/api/scripts/leave_row_oracle.py`
         (a CI gate whose name does not match `check_*`),
         `.github/workflows/**`, and
         `.github/pull_request_template.md` — the gates and the harness that
         enforce this rule. A change here satisfies condition 1 by construction.
         This file already records that `fetch-depth: 0` and one colon in the PR
         template are each the single character deciding whether a gate means
         anything.
  6. Nothing that changes deliverable content, exporter output, or client
     dashboard numbers.

  **Any red, or any PR tripping 4, 5 or 6, comes back to the human.**

  **Conditions 1 and 4 are mechanical; 5 is mostly a path match but its
  live-prompt clause needs a diff read. Conditions 2, 3 and 6 are
  self-attested by the agent that wants to merge**, and 6 is a judgement call an
  agent can talk itself out of. An earlier draft of this rule called the whole
  thing "a file-path check plus two facts, not a judgement call", which is this
  file's own narrower-than-the-reader-assumes shape. It is not that; it is three
  checkable conditions and three honest ones. When 6 is arguable, it has been
  tripped.

  Worked examples, so the boundary is not re-litigated per PR: item 7 part 2's
  `/ai-inputs` endpoint and panel is admin-only and trips none of the paths —
  land it. **#131 comes back**, because the winning spelling reaching the client
  deliverable means fixing it changes deliverable content by definition. Items 9
  and 6 come back for the same reason. **Item 8 comes back too** — an earlier
  draft said it "qualifies outright unless the export split touches exporter
  output", which is wrong twice over: the item is *named* export/publish split,
  and it owns #123, a **client dashboard** defect. Fixing #123 changes what the
  client's Risk dashboard shows, which is condition 6's third clause. The
  example contradicted the #131 reasoning directly above it.
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
