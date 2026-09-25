# CLAUDE.md — SHIELD

## Before anything else: is your copy of this file COMPLETE?

**This file must end with the line `<!-- CLAUDE-MD-CANARY: v1 -->`. If you
cannot see that marker at the end of what you received, YOUR COPY IS
TRUNCATED. Stop.** Say so, name the last heading you did receive, and do not
apply the merge rule or any condition test until someone confirms which clauses
you are missing. A truncated governance file is a control that does not exist.

**This notice is at the TOP because that is the only part a truncated reader
gets.** The marker and the fuller explanation are at the very end, which is
exactly the region a cut removes — so stating the rule only there would tell
the whole population it exists to protect precisely nothing. (Found by the
adversarial reviewer on #347, against the first version of this canary, which
did exactly that.)

## Where to start, by task

**Read the rows that apply and stop.** The parts that matter to you are a small
fraction of this file.

| If you are… | Read |
| --- | --- |
| Picking up after a break | `context/<your-name>.md`, then `DELIVERY_PLAN.md`'s MVP completion path |
| Deciding whether an agent may merge | **The merge rule**, immediately below the core principles. Do not grow it. |
| Writing or changing code | Core principles, then Real commands, then the gotcha bullets for the subsystem you are touching |
| Writing a test | Core principle 3, and the bullets on tests that cannot fail (#72, D-051) |
| Touching the redactor or any AI path | Core principle 1, the redaction bullets, and D-058 |
| Adding or changing a gate | The silent-success bullet, and the fail-closed bullet |
| Opening a PR | Rules of the road: the reviewer, the audit block, the closing-keyword check, and the merge rule above |
| Writing a number into any document | The rules for numbers in prose |
| Debugging something that "should work" | Environment gotchas. Start there, not in the code. |
| Editing this file, `DECISIONS.md`, or any `context/*.md` | The size ratchet, the file-ownership table, and the branch-vs-direct rule |
| Anything not listed above | Read on. "Stop" applies to a row that matches, never to the absence of one. |

**This file has a SIZE GATE** (`check_claude_md_size.py`), because at 210,958
bytes a reader silently cut the last 29% and took the merge rule's path list
with it. Anything you add here is paid for by trimming something, and the most
consequential rules stay at the TOP where a partial read still reaches them.

**One rule outranks the rest: VERIFY BY RUNNING.** Nearly every expensive
failure recorded in this file traces to a premise someone reasoned about instead
of executing.

**Its unstated precondition: verify that what you are measuring is the thing you
think you are measuring.** An exit status is set by whichever step ran LAST, not
by the step you cared about, and every form of that failure looks like success.
Three shapes, one property, all three hit on 2026-09-09 alone:

| what was written | whose status you got |
| --- | --- |
| `python gate.py \| head -1; echo $?` | `head`'s — a fail-closed **2** read as a clean **0** |
| `hits=$(grep -c X file)` under `bash -e` | `grep`'s — a legitimate zero-count **exits the script** |
| `python fix.py; echo done` | `echo`'s — python crashed on line 26 and the chain reported **0** |

**One remedy covers all three: `set -euo pipefail` at the top.** Reach for
`${PIPESTATUS[0]}` only where a pipeline's non-final status is genuinely wanted.
Where the OUTPUT is what you rely on, do not pipe at all.

**The detection is worth as much as the remedy, because the status tells you
nothing by construction.** The third row was caught by `git diff --stat` showing
ONE changed file where five were expected — an independent signal about the
work, not about the exit code. **When a command's status cannot be trusted,
check the artifact it was supposed to produce.**

**That remedy is BASH-ONLY, and its failure in PowerShell is silent.** There is
no `PIPESTATUS` in PowerShell 5.1: `${PIPESTATUS[0]}` parses as a variable named
`PIPESTATUS[0]` and evaluates to `$null` with no error. Use `$LASTEXITCODE` —
but it holds the last **native** command's code, so `python x.py | findstr .`
reports findstr's 0 and loses python's 2, exactly as bash does. **The hazard is
not bash's. Only the remedy is.** Measured 2026-09-08 (D-071).

**And it is not only pipes.** Lines fed to PowerShell 5.1 statement-at-a-time,
one containing a `&&`, run every line above the bad one, print a parser error,
and exit **0**. Measured on stdin (`-Command -`); an interactive console paste
is a different, unmeasured case. Nothing is substituted and nothing is
swallowed — the status simply does not describe what happened, which is the
harder version of the same lesson: **a green exit is evidence about the last
thing the shell finished, not about the work you asked for.**

## What this file is

Durable project knowledge for every Claude session, every developer. If it's a
fact that outlives the current sprint, it belongs here. Session status belongs
in `context/<your-name>.md`; state-of-main belongs in `CONTEXT.md`.

## What SHIELD is

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

## The merge rule: when an agent may merge without checking back

**This sits at the top of the file because everything past a reader's size
limit is cut away silently.** For at least three days it sat at byte 192,494 of
a 210,958-byte file, so agents read that a PR "tripping condition 5" comes back
and could not read WHICH PATHS trip it. Keep it here; D-079 records how that
happened.

**An agent merges on green WITHOUT checking back, when all six hold.**

1. **All seven CI checks green.** Five jobs in `ci.yml` — python, web,
   secret-scan, e2e, demo — plus two in `audit-gate.yml`. `mutation-sweep.yml`
   is schedule-only and excluded. **Re-derive this count if a job is added**;
   it is a hardcoded number in prose, which this file has a rule about.
2. **The adversarial reviewer ran against the FINAL state of the branch**, and
   whatever it found is fixed or filed, recorded with `Findings:` /
   `Disposition:` / `Scope:`. "Clean" means clean on the LAST run, not the
   first. The gate checks only that `Findings:` and `Disposition:` exist; it
   does not read `Scope:` and cannot tell whether the reviewer ran at all.
3. **`DELIVERY_PLAN.md`, `CONTEXT.md` and `context/<name>.md` updated in the
   landing commit**, with any counts read live rather than carried forward.
4. **No migration.**
5. **None of the paths listed below**, which are the ones where a green suite
   proves least. **A diff changing no executable line in them does not trip it**
   (#530); `check_condition5.py` decides, and its exit 2 reads as tripped. A PR
   changing a workflow or that gate is tripped whatever its report says (#572).
6. **Nothing that changes deliverable content, exporter output, or client
   dashboard numbers.**

**Any red, or any PR tripping 4, 5 or 6, comes back to the human.**

**Conditions 1 and 4 are mechanical; 5 is computed by `check_condition5.py`
over the list and what it derives, but a live prompt outside them, or any gate
input it does not derive (#572), needs a human read. Conditions 2, 3 and 6 are self-attested
by the agent that wants to merge** — three checkable conditions and three
honest ones, not "a file-path check plus two facts". Condition 6 is a
judgement call an agent can talk itself out of; when it is arguable, it has
been tripped.

### Condition 5: the paths

The gate reads this list; the bullets explain it, and a test pins the two agree.

    apps/api/app/ai/**
    apps/api/app/csf/playbook.py
    apps/api/app/risk/engine.py
    apps/api/app/zt/scoring.py
    apps/api/app/attack/coverage.py
    apps/api/app/csf/scoring.py
    apps/api/app/zt/maturity.py
    apps/api/app/tech_debt/security_scope.py
    apps/api/app/risk/exporters.py
    apps/api/app/tech_debt/extract.py
    apps/api/app/config.py
    apps/api/app/models/**
    apps/api/alembic/env.py
    apps/api/tests/**
    e2e/**
    apps/web/**/*.test.ts
    apps/web/**/*.test.tsx
    apps/web/**/*.spec.ts
    apps/web/**/*.spec.tsx
    apps/api/scripts/seed_demo.py
    scripts/demo-reset.sh
    docker-compose.yml
    docker-compose.demo.yml
    apps/api/scripts/check_*.py
    apps/api/scripts/leave_row_oracle.py
    tests/gates/**
    .github/workflows/**
    .github/pull_request_template.md

- `apps/api/app/ai/` — the single egress path for all five services.
- `apps/api/app/csf/playbook.py`, `app/risk/engine.py`, `app/zt/scoring.py` —
  the deterministic scoring engines. Core principle 1 is "AI suggests, code
  computes", and naming only the suggesting half would let a refactor of the
  5x5 risk mapping merge unattended. #84 is on record as `risk.py` hiding
  exactly that.
- the deterministic surfaces the first draft of this list missed:
  `app/attack/coverage.py`, `app/csf/scoring.py`, `app/zt/maturity.py`,
  `app/tech_debt/security_scope.py`, `app/risk/exporters.py`. Naming one file
  for three of five services and none for ATT&CK or Tech Debt was a half-sweep.
- any live LLM **prompt**, which is not confined to `app/ai/` —
  `app/tech_debt/extract.py` holds one, and fixture mode echoes payload keys
  back verbatim, so a prompt drift cannot turn CI red.
- `apps/api/app/config.py` — the switch deciding whether the redactor may be
  disabled, and its default. **#142 lived here, not in `app/ai/`.** A PR
  widening `is_development()` reintroduces it while tripping nothing else here.
- `apps/api/app/models/**` and `apps/api/alembic/env.py` — "no migration"
  (condition 4) is not "nothing under `alembic/`". A cascade rule or a column
  default changes stored behaviour without one.
- `apps/api/tests/**`, `e2e/**`, and `apps/web/**/*.test.ts`,
  `apps/web/**/*.test.tsx`, `apps/web/**/*.spec.ts`, `apps/web/**/*.spec.tsx` —
  weakening a test satisfies condition 1 more directly than editing a workflow
  does, and this repo keeps finding tests that could not fail (#72, D-051). Web
  **test globs only**, deliberately: the `apps/web` product code that matters is
  already caught by condition 6's dashboard clause, and widening to
  `apps/web/**` would expand scope on an argument nobody has made.
- `apps/api/scripts/seed_demo.py` and `scripts/demo-reset.sh` — both drive CI
  jobs, and seed data being clean is why #130 survived months of green.
- `docker-compose.yml` and `docker-compose.demo.yml` — CI's E2E and Demo jobs
  ARE this file: it defines the api bind mounts every containerised gate reads,
  the web install guard, the api boot chain, and every healthcheck. Listing
  only `scripts/demo-reset.sh`, a WRAPPER around `docker compose`, left a
  compose-only PR clearing all six conditions.
- `apps/api/scripts/check_*.py`, `apps/api/scripts/leave_row_oracle.py` (a CI
  gate whose name does not match `check_*`), `tests/gates/**`,
  `.github/workflows/**`, and `.github/pull_request_template.md` — the gates and
  the harness that enforce this rule. A change here satisfies condition 1 by
  construction. `fetch-depth: 0` and one colon in the PR template are each the
  single character deciding whether a gate means anything.

**Derive the set; do not extend the list.** The membership test is "does any
WORKFLOW execute it as a gate" — all of them, not `ci.yml`:

    grep -rnE "(bash|python( -m)?) +[A-Za-z0-9_./-]*(check_|leave_row_oracle|tests[/.]gates|scripts[/.])" .github/workflows/

**Doubt the command first.** The version published here before it read `ci.yml`
alone and required a literal `scripts/` or `tests/gates/` path, so it missed
`audit-gate.yml`'s `bash tests/gates/close_guard_linked_file.sh` entirely and
missed `python -m scripts.check_test_integrity` — a dotted module with no slash
— inside the very file it did read. It had been RUN before publishing and
returned ten real invocations, which is exactly what made it credible:
**running a command proves what it returns, never what it cannot see.** If a
gate is wired in a spelling neither the command nor this list knows, both are
wrong, and the command is the one that will go on reporting clean.

### Re-derive the measurement whenever condition 5 changes

What the rule actually clears is documentation PRs. Code comes back, and so does
anything adding or changing a test — and this repo does not ship code without
tests. Condition 5's path list applied to the fifteen most recent PR merges on
`main`:

| measured | cleared | came back | with the exception |
| --- | --- | --- | --- |
| 2026-08-26 | 4 | 11 | 4 / 11 |
| 2026-09-21 | 2 | 13 | 3 / 12 |

<!-- counted: condition 5's path list applied to `git log --first-parent -40 --format='%H|%s' <ref> | grep -E '\(#[0-9]+\)$' | head -15`, ref fdfde7d^1 and 897eeae; last column check_condition5.py at f41f5ae plus list-change trips read from the diffs, 2026-09-25 (D-095) -->

Each is a claim about a fixed window, so it does not rot the way a live count
does — and each is true only of condition 5 as it stood that day. **Re-derive
whenever condition 5 changes**, which is not a remote contingency: it changed
twice in the three days before the first measurement, and again in September.
On 2026-09-21 one of the thirteen came back ONLY through the new
`tests/gates/**` glob, tripping nothing else, so that glob is load-bearing on
real traffic rather than theoretically.

Dropping the rule was weighed against the same evidence and loses: the PRs that
clear are the ones that recur every round (D-059). A re-derivation selects PR
merges with the selector above, never commits: counting commits once reported
"fifteen cleared, zero came back".

### Worked examples

A STALE worked example is worse than none, because it ends the check with the
wrong answer in the place a reader looks first. These are phrased from the
conditions rather than from an issue number for that reason.

- **Anything shipping an endpoint or a panel comes back.** It ships with tests,
  or condition 1 proves nothing about it, so it trips `apps/api/tests/**`.
  Whether the surface is admin-only is not a question condition 5 asks.
- **A PR that repairs the gates comes back**, tripping condition 5 on both
  `check_*.py` and `apps/api/tests/**` at once. That such a commit is
  *repairing* the harness this rule depends on argues for a human reading it,
  not against.
- **Anything whose fix changes what a client's dashboard or deliverable shows
  comes back** under condition 6 — that is what condition 6 says, and it is
  the clause most often talked past.

## Real commands (use these, not generic equivalents)

**SCOPE: these are GIT BASH forms, and several do not run in PowerShell.** This
repo is developed on Windows, so the default shell in a fresh terminal is the
one that cannot parse them. The commands carrying `&&` are a grep rather than a
number, because a number goes stale the next time a command is added:

    sed -n '/^## Real commands/,/^## Environment gotchas/p' CLAUDE.md | grep -n '&&'

Two corrections when reading its output. **It over-reports on purpose** — this
block discusses `&&` in prose and matches itself; the commands are the ones
inside backticks under a `- ` bullet. And **hit LINES are not commands**: the
ruff/black bullet wraps across two source lines and carries a `&&` on each.
Count bullets, not lines.

**Empty output means the anchors moved, NOT that the section is PowerShell-safe.**
Both headings match by prefix and it must be run from the repo root. Reword the
FIRST heading and `sed` prints nothing, `grep` exits 1, and silence reads as the
reassuring answer. Reword only the SECOND and the range never closes, running to
EOF and dragging in JavaScript `&&` from the prose below — wrong, but visibly
wrong. The two failures do not look alike, and only one announces itself.

**What breaks where.** A floor rather than a census. Every row run in **Git Bash
and PowerShell 5.1 on 2026-09-08**. The cells are exit codes and the annotation
covers those — it does not cover the row labels, and a marker like this one has
already certified a table whose row label was wrong (D-071).

| Form | Git Bash | PowerShell 5.1 |
| --- | --- | --- |
| OUTER `&&` joining two host commands | 0 | **parse error** |
| `\"` escaping inside `sh -lc "..."` | **0** | **2** — `Unterminated quoted string` |
| `-w /app` | **128** — `Cwd must be an absolute path` | 0 |
| `sh -c "cd /app && ..."` — INNER `&&` | 0 | 0 |
| single quotes inside double | 0 | 0 |

**No shell shows you every breaking row** — two fail only in PowerShell, one only
in Git Bash — so verifying in the shell you happen to use is structurally
insufficient, and it clears the rows it cannot see by staying silent.

**A PowerShell `&&` parse error can exit 0.** Submitted statement-at-a-time it
runs every line above the offending one and reports success; submitted as a
script it runs none and exits 1. Nothing tells you which lines RAN, and the exit
status does not either.

So where a command's OUTPUT is what you rely on, the prescription is only these:
**no OUTER `&&` between two host commands (use separate lines); no
backslash-escaped quotes inside a quoted argument (use single quotes inside
double); and no `-w <dir>`.** `sh -lc "cd <dir> && ..."` is FINE and is the
replacement for `-w` — its `&&` is inside a single quoted argument handed to the
container's shell, which both host shells pass through untouched.

**Known to need rewriting for PowerShell:** `cd e2e && npx playwright test
[file]` (run it as two lines). The format check was run in Git Bash only.
Lines not in the `sh -lc` shape (e.g. `export PATH`, the pytest and seed
lines) are unmeasured there; the default below applies.

**The rule, and it binds every command block in this file: a block that claims it
runs anywhere carries the SHELLS it was actually run in and the DATE it was run.**
What counts is a SHAPE, not a word list — any sentence asserting a block **runs,
or does not run,** in more than one shell, however phrased. **The negative
direction is the more dangerous**, because nobody runs the thing they have been
told is broken, so a false negative is never disproved by anyone who obeys it.

**Absent an annotation, assume the block was written for Git Bash and verify
before running it elsewhere.** That is a default for the READER, file-wide: the
file asserts nothing, most blocks have not been run anywhere else, and absence
of a marker is absence of evidence. No example is cited for it on purpose — a
bash-only unmarked block stops being an example the moment anyone marks it,
which is what acting on this rule does.

Never put the marker on a block you did not run in the shells it names: a
decorative one is worse than silence, because it is what the reader checks
instead of running it. **State what it covers, not only where it ran** — a
block-level marker over a table certifies every cell at once and offers no way
to write "measured, except this row" (D-071).

**And where the command involves early termination, concurrency or ordering, run
it more than once and record the OBSERVED SET rather than a single value.** The
trigger is a property of the command, visible before you run it —
`Select-Object -First 1` stops a pipeline early and says so in its own name.
Record `-1 x14, 2 x1`, never "15 runs": a count can be filled in ritually, while
a distribution is self-announcing. A measurement of that kind was taken once,
recorded with a real exit code and a real date, and was the minority outcome
(D-071).
- Docker CLI is NOT on Git Bash PATH:
  `export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"` first, every shell.
- Backend unit tests: `docker compose exec -T api pytest -m unit -q`
  (~3 min alone, 13–16 min under load; run detached and poll for the exit code).
- Web typecheck: `docker compose exec -T web sh -lc "cd /app && pnpm -F web exec tsc --noEmit"`
- e2e (host, not docker): `cd e2e && npx playwright test [file]` — base URL
  `http://localhost:3000`, chromium, serialized (shared seeded DB). Full suite
  ~17 min.
- Format check (MANDATORY before every commit; CI enforces it). CI installs
  `--frozen-lockfile`, so the LOCKFILE decides prettier's version. Read it with
  the pre-commit hook's own reader, which takes the ROOT IMPORTER's entry
  (never the alphabetical `packages:` list, whose first entry is the LOWEST,
  #311) and refuses when it cannot read. From the repo root, **Git Bash only**:

      v=$(scripts/prettier-hook.sh --print-version)
      npx -y "prettier@${v:?}" --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"

  **Run 2026-09-24, both directions:** it read 3.9.8 and `--check` exited 0.
  With no lockfile the hook refused, `${v:?}` exited 1, and `npx` never ran.
  `--write` the same glob to fix, then re-check.
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
  the loop gates as they then stood, and only surfaced in CI's `next build`):
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

- **Git Bash rewrites an argument beginning with `/` into a Windows path when
  it crosses into a NATIVE WINDOWS EXECUTABLE, and does it silently.** Not a
  Docker quirk and not a `gh` quirk: it is MSYS argument marshalling at the
  Win32 boundary, so it reaches `gh.exe`, `python.exe`, `docker.exe` and every
  other `.exe` you pass a leading-slash string to. Prefix with
  `MSYS_NO_PATHCONV=1`.

  **It is NOT "any command", and getting that wrong would discredit working
  ones.** Measured 2026-09-09, Git Bash, `MSYS_NO_PATHCONV` unset:

      echo /admin/management                        -> /admin/management
      sed -n '/^## Environment gotchas/p' CLAUDE.md -> ## Environment gotchas ...
      python -c "print(sys.argv[1])" /admin/management
                                                    -> C:/Program Files/Git/admin/management

  Bash builtins are unaffected and MSYS-native binaries handle it themselves.
  The load-bearing consequence: **the portability grep this file publishes under
  "Real commands" still works.** A draft of this entry said "any command", which
  predicts that grep broken; running it is what showed the mechanism was the exe
  boundary rather than the shell. **The widely-recommended `//` escape is NOT a
  remedy** — it arrives as `//admin/management`, leading slash doubled.

  **Recorded as the MECHANISM because the enumeration already failed.** The
  `-w /app` row in the table above is this same rewrite written down as one
  tool's literal symptom, and it was no help at all the second time: nothing in
  it says "any argument", so a `gh issue create --title /admin/...` finds no
  prior art.

  **The observability difference is the more useful half.** `-w /app` fails
  LOUDLY — Docker rejects it, exit 128, `Cwd must be an absolute path`. The `gh`
  case failed SILENTLY: the title was mangled, `gh` accepted it, exit 0, and
  printed a cheerful confirmation containing the corrupted string that nobody
  read. Same mechanism, opposite observability, and only the loud one made it
  into the file. **Assume every quiet instance of a known-loud failure exists
  and has not been noticed.**

  Do not add a row per tool. A row per tool is an enumeration of what its author
  happened to hit.

- **ON WINDOWS, `sh` IS BASH, so a shell script "tested under `sh`" was never
  tested under `sh` at all.** Every bashism passes locally and the first
  environment that refuses it is the runner. Measured 2026-09-21:

      Git Bash   sh --version            -> GNU bash, version 5.2.37(1)-release
                 sh -c 'set -o pipefail' -> accepted
      Debian     /bin/sh                 -> dash
                 sh -c 'set -o pipefail' -> sh: 1: set: Illegal option -o pipefail

  What it cost: a gate running the repo's shell scripts under `sh` passed all
  seven subjects on Windows and failed three on the runner, each dying at
  `set -o pipefail` before reaching any argument handling. Exit 2, no message,
  which is also what a crash looks like.

  **The remedy is NOT "make everything bash" and NOT "make everything POSIX".**
  Both were proposed and both are wrong: the shebang is the contract and it
  legitimately VARIES — `docker-compose.yml` runs `sh /app/web-install-if-stale.sh`,
  so POSIX compatibility is a real requirement for that one, and forcing bash
  would stop checking the single case where it matters. A harness reads each
  file's shebang and honours it; a subject with no recognisable shebang is a
  could-not-look, not a guess.

  **The transferable part is not about shells.** A local run can exercise a
  different interpreter, library or resolver than CI under the same command
  name, and nothing in the output says so. When a check passes locally and fails
  on the runner, suspect the interpreter before the code.

  **A WRAPPER WRITTEN TO VERIFY SOMETHING IS WHERE THIS KEEPS LANDING.** From
  one evening, by three authors: `sh` that was bash; `pytest ... | tail` inside
  `sh -lc`, which has no `pipefail`, so the harness read `tail`'s status and
  reported STAYED GREEN over two failures; the same pipe again in a second
  author's helper; `git worktree add` failing so the following `cd` failed and
  `sed` ran in the wrong directory, empty output read as "no conflict";
  `mktemp -d` giving an MSYS path Docker could not mount, reporting PASS for
  both variants of a comparison having scanned ZERO files; `gh pr edit ... |
  tail` from a directory that was not a repo, where `gh` failed and `tail`
  returned 0. **Most of them produced the answer the author was hoping for.**
  The failure mode is not noise, it is agreement.

- **RUFF'S FIRST-PARTY RESOLUTION DEPENDS ON THE LAYOUT IT IS RUN IN, so the
  in-container lint gate is STRUCTURALLY BLIND to one class of import error
  that CI catches.** Not "scoped narrower" — blind. No invocation fixes it.

  ruff decides first-party by asking whether the dotted module path exists under
  `src`, which defaults to the config's directory. This repo has a top-level
  `scripts/` unrelated to `apps/api/scripts/`, and the api container mounts
  `apps/api` at `/app` with the root `pyproject.toml` at `/` — so NEITHER
  `scripts/` path exists in the container. A bare `from scripts import x` is
  therefore third-party in the container and first-party in a full checkout.
  Measured 2026-09-21:

      | import form                  | CI layout | container |
      | bare + blank line            | PASS      | I001      |
      | dotted (`from scripts.y ...`)| PASS      | PASS      |

  **Two consequences, and the second bites.** `ruff check --no-cache .` inside
  the container — CI's exact command — exits 0 on a file CI rejects. And
  **`ruff --fix` MOVES the red rather than removing it**: the blank line it
  inserts satisfies the full-checkout layout and breaks the container one. The
  stable answer is the DOTTED form, because it **fails to resolve in both**
  — so it is classified the same way in both — which is what the rest of
  `tests/unit/` already uses.

  To reproduce a CI lint red locally, mount the FULL worktree and run ruff from
  `apps/api` so `src` resolves to the repo root. A different layout, not a
  different flag.

- **next dev hot-reload does NOT fire through the Windows bind mount.** After an
  `apps/web` SOURCE edit: `docker compose up -d --force-recreate web`
  (~10–20s) before e2e. In-container touch/restart does not help.
- **A LOCKFILE change is picked up by a plain `docker compose restart web`.**
  `node_modules` lives in named volumes, and `docker-compose.yml` once guarded
  the install on the binary EXISTING rather than on its version:

      [ -f apps/web/node_modules/next/dist/bin/next ] || pnpm install;

  **That guard is GONE** (#226 / PR #309). `scripts/web-install-if-stale.sh`
  compares a hash of `pnpm-lock.yaml` against a stamp in the volume. The quoted
  line is kept as the SYMPTOM a reader arrives with.

  **The procedure is two lines, not three:**

      docker compose restart web
      docker compose exec -T web node -p "require('/app/apps/web/node_modules/next/package.json').version"

  **The `pnpm install` line that used to come first is now actively harmful and
  is removed rather than reordered.** It has no `--frozen-lockfile`, so it
  resolves `package.json` RANGES — the drift the mount exists to end — and it
  writes no stamp, so the `restart` on the next line re-runs the guard and
  reinstalls over the top. The documented step 1 was undone by the documented
  step 2, and the version you then read back came from the guard rather than
  from the command you were told was the fix.

  **It is the LOCKFILE that is watched, not `package.json`.** A `package.json`
  edit with no `pnpm install` changes no hash and triggers no reinstall —
  correctly, because the lockfile is what CI installs from.

  **The confirmation read is not optional.** On a security bump, "the container
  started" and "the patch is applied" read identically without it. Measured on
  the `next` 15.5.24 RCE patch before #226: `package.json` said 15.5.24 and the
  running container said 15.5.23.

  **Three separate lines, no OUTER `&&`, no backslash escaping, and no `-w`** —
  each fixed by a different thing, and mixing them up is how the SECOND version
  of this block also shipped broken (D-071). **Run in Git Bash and PowerShell
  5.1 on 2026-09-08**, in both before the claim was written, and re-run since.
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
  with the parser *by construction*, so it can never express the one failure
  that matters — the model and the code disagreeing about a key. Whoever writes
  it already knows the answer the parser wants, and encodes that answer. Copy
  the keys out of the prompt text (and out of a real logged response where one
  exists); if the prompt says "Policy and Process" while the example JSON says
  `policy`, that discrepancy is the test case, not a detail to normalise away.
  This shape has surfaced independently several times — the Sprint 3 T0 drift,
  `mitre_map`'s fixture, the Risk Register enum mismatch, and W1's
  `unknown_field` (2026-08-09), where a green suite certified "3 of 3 applied,
  nothing dropped" over three lost scores per row.

  **Corollary: fixture mode cannot exercise drop/rejection counters at all** —
  the fixtures echo the payload keys back verbatim, so those paths need
  synthetic unit tests and a live run, and a green e2e proves nothing about
  them.
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
  fixed.

  **The tell is not the defect count, it is that the same predicate keeps
  changing shape** — `applied === 0`, then `applied === 0 && failed.length === 0`,
  then `applied === 0 && lostValues > 0`. When you see that, stop adding
  conditionals and write the truth table: the inputs here were four booleans, so
  the whole space was thirteen renderable states and fits in one table-driven
  test. **Do the matrix FIRST, then change the logic** — a matrix written after
  the fix only pins the fix.
- **A test that supplies its own expected value — or its own precondition — from
  the thing under test cannot fail.** The AI-fixture rule above is an instance
  <!-- counted: "an instance" counts nothing that can grow. -->
  of this; this is the general shape, and it turned up twice on 2026-08-18 in
  code that had already passed review. `test_csf_ai_contract.py` builds its
  "prompt-compliant" response out of `_PARSER_ROW_KEYS` — the parser's own
  constants — so it agrees with the parser by construction and cannot see the
  prose/JSON drift the `csf_score` prompt actually carries, which is the one
  thing a contract test exists to catch. `test_deliverable_release.py` writes
  `parent_version = 1` by direct SQL and *then* re-releases, so it proves the
  flip works given a link while the production claim under test — that
  re-releasing establishes the link — is false for every multi-version service
  (#59). Both were green; neither could ever have been red.

  **The tell: the test and the code read from the same constant, or the test's
  setup performs the very step the code is supposed to perform.** Derive the
  expected value from the SPEC — the prompt text, a real logged response, the
  documented behaviour — and let the setup build only the world, never the
  outcome.
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
  unconfirmed, and the obvious reading — leave it out of both numerator and
  denominator, as `unscored` already works — shipped `gap` as withholdable. But
  `coverage_pct` is `(covered + 0.5·partial) / (covered + partial + gap)`, so a
  gap contributes to the DENOMINATOR only: ten covered beside ten gaps reported
  50%, and flagging every gap reported **100%** with ten findings deleted.
  <!-- counted: a hypothetical worked example, fixed by construction, not recalled from a population -->
  A run in which more evidence was doubted claimed twice the coverage.

  Only values carrying numerator weight can be withheld conservatively;
  withholding a pure-denominator value is a strictly optimistic move wearing a
  cautious one's clothes. And it is not unconditional even for the rest —
  withholding one `partial` from nine confirmed `covered` takes 95% to 100%,
  because narrowing a denominator changes what the ratio is a ratio OF. **A
  percentage over a withheld population is not self-describing: render the
  withheld count beside it, everywhere, and test that you did.** CSF, ZT and
  Risk all compute the same shape of fraction.
- **A rule that withholds a claim must separate "the evidence failed" from "no
  evidence was offered" — and if the store cannot tell them apart, fix the
  store.** #102's first predicate was "pending unless a confirmed citation backs
  the status", which is right for every AI-authored row and withheld every
  hand-curated one: a consultant typing `covered` into the matrix has made no
  inference, and the rule was about inferences. The heatmap reported zero
  covered over ten curated techniques with nothing in the product able to clear
  it, and the test that caught it predated the feature by months.

  The fix was not a special case but a missing state: outcomes that resolve to
  NOTHING — a rejected citation, and a status the model cited nothing for at all
  — now get persisted rows of their own, because otherwise "we dropped the
  model's evidence" and "nobody ever cited anything" are the same stored bytes.
  **Before writing a withholding rule, ask what the absence of a record means,
  and make sure the writer records absence on purpose rather than by not
  writing.**
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
  positive-sounding message on an empty read.** `check_audit_evidence.py`
  shipped with `is_code_change([])` returning False, so an empty changed-file
  list printed "documentation-only change, exempt" and exited **0** — a green
  gate, with an encouraging sentence, from input that supported neither reading.
  Not reachable through its own workflow, which is exactly why it survived
  review: the hole opens the day someone changes the checkout depth.

  **A checker's "nothing to complain about" branch and its "I could not look"
  branch must not be the same branch.** Every gate in this repo returns a
  distinct non-zero (2) for unreadable input, separate from the 1 it returns for
  a real violation.

  **Recorded because this is the one case where writing it down demonstrably
  worked.** `check_issue_references.py` was written months later by someone who
  had read this entry, and its fail-closed path and the test pinning it were in
  the first committed version — the defect never existed in it. Set that against
  the closing-keyword rule, rewritten three times and violated a fourth. The
  difference is not diligence: the fail-closed lesson is a rule about code you
  are *writing on purpose*, and the closing-keyword one is about prose you are
  *not thinking about*. Only the second kind needs a machine.
- **A defect found in one service exists in its twins until you have checked.**
  CSF, ZT, ATT&CK, Tech Debt and Risk are five copies of the same shapes, so a
  fix filed against one is a fix owed by all of them. #75 was fixed in ZT while
  CSF truncated identically through the same `DEFAULT_TOP_N = 20` in the same
  three renderers — inside the PR that was also fixing #79, which exists
  *because* an earlier change fixed one surface and not its twin. Half-fixes are
  worse than none: raising CSF's target to the client's tier increases its gap
  count, so leaving the disclosure out hid MORE than before the "fix".

  Grep the sibling services for the function you just changed, and **when you
  deliberately leave a twin alone, say so in the code.**

  **FIX FROM THE SHAPE, NOT FROM THE LIST YOU WERE HANDED — a reviewer's site
  list is evidence that twins exist, never the set of them.** One branch
  produced three consecutive half-fixes, each round correcting every twin it was
  shown and none it was not, because each worked from the previous review's
  list, which is a sample. **Expect the last twin to be the one a USER reads** —
  a hover title gets corrected while the paragraph beside it does not, because
  the reviewer quoted the hover (D-074, D-072).
- **These gates check whether a test can fail at all (#72, D-051).**
  `docker compose exec -T api sh -lc "cd /app && python -m scripts.check_test_integrity tests"`
  is a two-second static pass and **runs in CI before pytest** — it flags a test
  importing a private CONSTANT from the module it tests, and a containment
  assertion whose needle carries no literal text (`str(n) in blob` rather than
  `f"of {n} gaps" in blob`). Neither is forbidden; both demand a written
  `# test-integrity: <reason>` on the line or in the comment block above it, and
  an empty reason is not a reason.

  `scripts/mutation_sweep.py` is the other half — `--paths <files> --tests
  <target>` applies one change at a time and reports what no test noticed. Its
  `DropKeyword` operator exists because instance 9 was a deletable `targets=`
  argument, which off-the-shelf mutation tools do not model.

  **Neither gate is enough to call #72 done**: tier 1 cannot see a test whose
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
- **A CERTIFICATE OVER THE WRONG PROPOSITION IS WORSE THAN NO CERTIFICATE,
  BECAUSE IT ENDS THE CHECK THAT WOULD HAVE CAUGHT IT.** Every verification step
  proves some proposition. The failure is proving one ADJACENT to the claim you
  are making, and then citing it — a bare unsupported claim invites a check; a
  claim under a command and a date does not.

  **The check is one question, asked before you cite anything: what proposition
  does this command actually prove, and is it the one in my sentence?** Where
  they differ, change the command or change the sentence; do not publish the
  pair. It generalises past grep: a **test** proves its assertions hold, not
  that they can fail (#72); an **exit code** proves the last command's status,
  not the one you meant; a **CI certificate** proves a head passed, not that a
  branch is ready; a **`--collect-only`** proves collection, not that anything
  ran; a **reviewer's clean report** proves nothing was found in what it read,
  which is why the `Scope:` line exists.

  **AND THE SENTENCE THAT NAMES ITS OWN VERIFICATION IS THE ONE TO RE-RUN**,
  because the phrase is doing the work the measurement should. "Checked and left
  alone", "measured, not assumed", "verified" — each reads as evidence and is
  only ever a claim ABOUT evidence. **When you write a word asserting you
  verified something, that is the sentence to go back and run.** Not because you
  are careless — in the recorded instances the author had run the commands and
  read the output — but because the phrase closes the question for every later
  reader, and it closed it around a property nobody had tested (D-079).

- **Before reporting a sweep complete, name the SHAPE you searched for and one
  place it could hide that shares no vocabulary with the original.** Keyword
  sweeps keep coming back clean over live defects because the second instance
  was written by someone using different words.

  **This binds PROSE sweeps identically, and prose is where it is skipped.** A
  commit correcting the three documents a finding named left two present-tense
  claims standing elsewhere, because the author never asked what ELSE asserted
  the same thing. Write the shape for prose the way you would for code — "any
  sentence stating what happens when X fails, in the present tense" — and grep
  the bare nouns rather than the phrasing you were shown.

  `risk.py` re-derived a gap comparison instead of calling `analyze_gaps` (#84),
  and reimplements the ATT&CK citation drop with no counter (#132), found only
  because the sweep asked "where else does a model's string get compared to a
  stored value and the misses discarded?" rather than "where else is
  `_validate_tools` called?". **If you cannot describe the defect without naming
  the function it was found in, you have not generalised it yet.**

  **A good shape statement**, from the `docs/security.md` honesty pass (#146):

  > A control stated in the present tense whose implementation is a deferral
  > comment, a client-supplied value, a header with no transport to enforce it,
  > or a function with no callers.

  It names four distinct failure modes rather than one; it names no file,
  function or symbol; each mode is checkable by reading the implementation
  rather than by knowing the history; and it found defects outside the table it
  would have been natural to check. **The test of a shape statement is whether
  it could have been written BEFORE seeing the defect that prompted it.**
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
- **A FIELD IS ADDITIVE ONLY IF NO CONSUMER BRANCHES ON ITS PRESENCE.** Adding
  a key to a shared envelope reads as the safest change there is, and the PR
  that does it says so: #307 added a typed `reason` to every schema 422 and
  promised "additive, deliberately". That was false at merge time.
  `SignUpForm.tsx` chose between typed copy and a friendly fallback by testing
  `reason`'s PRESENCE, so the new key made the fallback unreachable and put the
  internal string "Request validation failed." under the Email field of the
  **public** sign-up page (#317, tier-1, live on `main` until PR #320).

  A consumer never has to opt in to be broken by a new key. It only has to have
  branched on the key's ABSENCE — what a careful consumer does when the key is
  optional — **so the more defensively it was written the more likely it is to
  break.**

  **The check is mechanical: before adding a field to a shared envelope, grep
  the consumers for a PRESENCE test rather than a value test.** For the D-016
  envelope that is `error.reason` and `error.message` across `apps/web/src`;
  `reason === "..."` is safe, a bare `reason &&` is the defect **unless
  something else already excludes the new key** — `lib/auth/options.ts` is safe
  only because it sits inside `err.status === 403`. A status gate is not a value
  test, so say so at the site. Nothing about the new field's own correctness
  reveals this: the evidence is entirely in files the PR does not touch.

  Two corollaries, both paid for here. **The comment stating the precondition is
  what hides the breakage** — the fallback carried "raw schema validation
  carries no typed reason", true when written, deleted as a fact by #307, and
  surviving as a sentence telling the next reader the branch was sound: a
  precondition that has EXPIRED, not a scope that is too narrow. And **test both
  halves of the branch you changed** — a fix keyed on the value can be
  "repaired" into discarding every friendly message the API does send, with the
  fallback tests green throughout.

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

- **A CORRECT CHANGE WHOSE STATED MOTIVATION DOES NOT SURVIVE CONTACT WITH THE
  CODE. The change stays; the justification gets rewritten.** The tell: a fix is
  right on its own terms — it closes a real hole, its tests discriminate,
  red-on-revert holds — and the sentence explaining WHY it matters turns out to
  describe a path nothing can reach. The instinct is to withdraw the change.
  That is usually wrong.

  - **#240's export guard**, written to catch a DRAFT-ATT&CK-sourced register
    reaching export. Every input the snapshot can record is already approved or
    released, so the guard cannot fire. Kept as a RATCHET against a future
    loosening of the resolver, and the code now says so.
  - **#188's per-capability target disclosure**, justified by "the same stored
    integer is usable or not depending on which framework asks". Capability
    codes are framework-namespaced and both read paths take the framework from
    the assessment, so no row can be read under a different framework. The test
    written to prove it used two DIFFERENT codes, which was the tell and was not
    read as one.

  **Both resolved to "a disclosure that should normally never fire", and that is
  a legitimate thing to build.** What is not legitimate is leaving the original
  motivation standing, because a reader then takes the defect as triggerable
  today and sizes everything downstream against a hazard that does not exist.

  The procedure is three lines: state the population the change actually
  protects; say plainly that no current writer can produce one, where that is
  true; and say what would make it reachable again. Migration 0047's
  `## Blast radius, measured before choosing` and the ratchet note in
  `routes/risk.py` are the worked examples.

  **Where the justification came from matters more than that it was wrong.**
  Both were written from a plausible mechanism nobody executed: the claim "these
  two things can meet" is a measurement, not a deduction.

- **An over-match can be the ONLY thing covering a legitimate case. Before fixing
  one, check what it was accidentally catching.** The tell: the "wrong"
  behaviour and the only correct behaviour for some input come from the same
  line. It is the twin-sweep rule's cousin: that one asks where else the defect
  is, this one asks what else it is doing. Say which one a fix is: "adds
  coverage that never existed" is not "preserves coverage". Instance: D-087.
- **A redaction/validation corpus drawn from your own assumptions cannot falsify
  them — and seed data is somebody's assumptions too.** A suite built on seed
  data, or on a corpus the rule's author wrote, passes forever over the class
  the author never writes; the #130 instances are in D-087.

  #72's shape pointed at test DATA rather than test code, with the same fix:
  **enumerate the CLASSES and require a row per class.** The classes a
  hand-written corpus structurally cannot contain: malformed strings,
  `name + version number`, non-US locale variants, and strings that have already
  been through the pipeline once.
- **A table written FIRST is an independent specification. A table written
  AFTERWARDS is a transcript of what the rule does.** Enumerating cases against
  a rule you have already written cannot falsify that rule, because the rule is
  where the cases came from. Measured on 104 LEAVE rows: tables written before
  their pattern pinned nothing **3.8%** of the time; tables written alongside or
  after their rule, **42.1%** — same corpus, same author, same week, the only
  variable being whether the table existed before the code did (D-058).

  **The step**: any LEAVE table written or extended after its rule exists gets
  `leave_row_oracle.py` run before the PR, and rows that pin nothing are
  rewritten or reclassified. Scoring a row needs judgement, so the tool reports
  and a human decides. What IS gated, behind `--check-registry`: a LEAVE table
  with no registered guards, and a table DECLARED not-LEAVE whose rows the
  redactor leaves untouched (#221). **Budget it** — any item fixing existing
  code lands its tables in the 42% regime by construction.

  **It is a floor, not a census**, and can only under-report: the guard list is
  hand-built, so `unrelated` is an UPPER BOUND. **Still ungated is whether the
  tool can RUN** (#299) — two mutation anchors had drifted out of `redact.py`
  and the oracle had been exiting 2 for an unknown length of time, because
  `--check-registry` returns before `build_mutations` is called.
- **Sweeping for a defect's twins, grep the SYMPTOM as well as the call sites.**
  Grepping for callers of the function you just fixed finds every copy that went
  through that function and misses every REIMPLEMENTATION of it. #84 escaped the
  #73/#75/#79 sweep exactly that way: `risk.py` never calls `analyze_gaps`, it
  re-derives the comparison inline, so a complete call-site sweep reported clean
  over a file that computed client-facing risk findings against a hardcoded
  target. **Grep for what the defect LOOKS like** — the literal default values,
  the truncation constant, the magic number, the shape of the comparison.
  Concretely, **as `risk.py` read before #84 was fixed**:
  `grep -rnE "(maturity_tier|maturity_stage) *< *[0-9]"` returned `risk.py:177`
  on the first try, and `grep -rnE "is not None else [0-9]"` returned
  `risk.py:193`. Neither appeared in any list of `analyze_gaps` callers. A
  reimplementation shares the symptom, never the symbol.

  **The example is DATE-QUALIFIED rather than refreshed, and that is the repair
  this file prescribes for itself.** #84's fix replaced both lines, so both
  greps now return nothing — and a reader who tries the technique on a fixed
  tree gets silence and concludes the technique does not work. Swapping in a
  fresh live instance would re-arm exactly that: the cited instance is the first
  thing anyone fixes. Pin the example to when it was true; the TECHNIQUE is what
  survives.

  **AND THE OBVIOUS FIX — "so call `analyze_gaps`" — IS REFUSED, deliberately.**
  #84 was closed by sharing the TARGET RESOLUTION (`resolve_target_tier` /
  `resolve_target_stage`, imported rather than copied) and leaving the
  comparison local. Calling `analyze_gaps` here would cap the risk-synthesis
  feed at `DEFAULT_TOP_N = 20`, because it returns `gaps=tuple(rows[:top_n])` —
  the truncation #75/#79 record in three renderers, arriving in the client's
  register. Trading a wrong baseline for silent data loss is not a trade. The
  full migration needs an explicit `top_n` and its own red-on-revert; until then
  this file is a deliberate non-caller, and PR #348 carries the reason at the
  site.
- **A CHANGE THAT REMOVES OR REPLACES A GUARD NEEDS AT LEAST ONE ASSERTION
  THAT GOES RED WHEN THE GUARD IS DELETED, EXERCISED THROUGH THE SURFACE THE
  CLIENT ACTUALLY REACHES.** A resolver and a pure function are not that
  surface. Neither is a schema. From one branch family on 2026-09-10, each found
  by red-on-revert and none by review:

  - The #195 schema tests stayed GREEN with the route pointed back at the wide
    admin schema. They pinned the shape of two Pydantic models; the defect was
    which model the handler names.
  - The 422-handler test stayed GREEN with the handler's call site reverted,
    because it called the coercion helper directly.
  - #184's tests covered `resolve_target_tier` and `analyze`. The reachable
    defect was a query parameter, and deleting its guard would have left the
    whole suite green while turning a 200 into an untyped 500.

  **The tell is that the test imports the thing it is defending rather than
  calling the endpoint that reaches it.** That reads as more focused and is
  strictly weaker: the wiring is where the guard is selected, and the wiring is
  what a refactor changes. **The check is mechanical** — delete the guard, run
  the suite, require a specific named test to go red. If the only red is in a
  file that imports the guard directly, the surface is not covered.

- **Verify each assertion red-on-revert, one fix at a time.** A suite that goes
  green after a change proves the change did not break anything; it says nothing
  about whether the new tests can fail. Revert each fix individually and confirm
  its own test fails with the message you wrote for it. In one export trio this
  turned four green tests into four discriminating ones and caught two more #72
  instances — one where `str(count) in summary` was satisfied by an unrelated
  fraction, one where an entire keyword argument was deletable with the suite
  passing. Both were written by someone who had logged that pattern the same
  day: knowing the shape does not prevent producing it.

  **A revert that silently fails to apply reports the same green as a test that
  cannot fail — so prove the revert LANDED before you read its result.** A
  scripted `str.replace` matched zero occurrences because the search string
  carried a real tab where the file has a literal backslash-`t`; `replace` does
  not raise on a miss, so the suite ran against the UNMODIFIED file and came
  back green. Written up, that would have read "verified red-on-revert" over a
  fix pinned by nothing. Cheap guards, in preference order: `assert
  s.count(old) == 1` before replacing; `grep` the mutated line and read it back;
  or revert with `git` rather than a string edit. **Treat "the revert produced
  no failures" as a claim about your tooling until proven otherwise.**

  **THE STRONGEST RECORDED CASE IS ONE WHERE EVERY OTHER SIGNAL AGREED,
  INCLUDING THE AUTHOR'S OWN EYES.** A `\b` written for a boundary reached the
  file as a literal BACKSPACE byte (U+0008) inside a raw string, so the
  alternation matched nothing. `grep` printed a correct-looking line, because a
  backspace renders as nothing. The tests passed. The same regex typed inline in
  a shell found the codes. **Only the mutation disagreed** — every other
  behavioural signal was reading the SOURCE while the defect was in the COMPILED
  value.

  **It is not the cheapest signal, and a draft of this said it was the only one
  — directly above its own counterexample.** `check_no_control_chars.py` reads
  `path.read_bytes()` and finds that byte in two seconds. **Run the gate first;
  reach for red-on-revert to prove the fix holds.** And that gate DID fire,
  correctly, on the first run, and was not read. **When a gate reports something
  you did not expect, read it before deciding what it is about.**
- **Replacing a character class with an enumerated one is a subtraction you must
  COMPUTE, not guess** — the enumerated version once dropped sixteen characters
  `\s` matches and leaked addresses (D-058). **Write it as the subtraction and
  let the language define the set** (`[^\S\n\v\f\r\x1c\x1d\x1e\x85\u2028\u2029]`), then pin BOTH halves as
  parametrised sweeps whose parameters come from somewhere other than the thing
  under test. Note `[^\S\r\n]`, the idiom everyone reaches for, is also wrong —
  it still crosses `\v`, `\f`, `\x1c`-`\x1e`, `\x85`, U+2028 and U+2029.
- **An escape sequence written into prose becomes an invisible control byte, and
  CI now checks for it** (`apps/api/scripts/check_no_control_chars.py`, the
  "control-character sweep" step). `\b` in a non-raw string is a BACKSPACE; `\v`,
  `\f` and `\u2028` are equally invisible. This repo writes prose ABOUT regexes
  constantly -- decision records quote the patterns they decide -- so
  `DECISIONS.md` acquires an empty code span and a control byte inside a sentence
  explaining word boundaries, and nothing notices: the file parses, prettier
  passes, the diff looks fine. **Four instances on one branch**: two pre-existing, <!-- counted: historical -->
  one in the commit fixing those two, and one in the CI comment introducing the
  gate, in the sentence describing the defect. The last was caught by the gate on
  its first run. That is the argument for mechanising it rather than writing a
  fifth paragraph -- the same argument the closing-keyword check settled.
- **Changing a parametrisation invalidates every count derived from it, and the
  count is usually in another file.** Narrower and more checkable than "re-check
  your numbers": the trigger is mechanical. PR #141 stated the address truth
  table had 153 cells. The fix for a review finding was to parametrise two
  sweeps per separator as well as per character, which multiplied the collected
  count several-fold. (The number that stood here was 327; it was 376 within the
  week and 410 after item 10, which is why it is no longer written down. Run the
  collector.) The stale 153 shipped to `main` in `CONTEXT.md` and `DECISIONS.md`
  and was found a PR later.

  What caught it was **re-counting**, not re-reading: the sentence still parsed,
  still looked deliberate, and was wrong by a factor of two. The number goes
  stale at the exact moment the change is most obviously substantive, which is
  when attention is on the code and not on the prose two files away. **After
  touching any `@pytest.mark.parametrize` argument, grep the repo for the old
  count before committing.**
- **A CORRECTION PARAGRAPH OUTLIVES THE NUMBER IT CORRECTED, and then certifies
  a wrong one.** The prose written to explain WHY a number is trustworthy goes
  stale with the number, while still reading as a guarantee. A bare stale count
  invites a check; a stale count under "read live from GitHub, not carried
  forward" ends it. It has happened repeatedly in one week, and most instances
  are in the files documenting the rule — **D-079** carries the list, kept THERE
  because a list here acquires a tally that goes stale in turn.

  The countermeasure is not more care, because in most instances the author was
  actively applying the rule. It is: **when you write a sentence certifying a
  derived value, put the value where a gate can read it, and let the sentence
  point at the gate rather than restate the number.** `check_plan_totals.py`
  reads the table, not the prose, which is why the plan's total is the one
  figure in this repo that has never shipped wrong.

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
  that exits 0 without having looked — the way you enumerate a truth table
  before a regex.** The fail-closed rule above is about the branch you write on
  purpose. This is about the branches you do not notice you wrote:

  - `check_audit_evidence.py` — `is_code_change([])` returned False, so an empty
    changed-file list printed "documentation-only change, exempt" and exited 0.
  - `mutation_sweep.py` — `_run_tests` reports "killed" for any non-zero exit,
    and pytest exits non-zero for collection errors, so a suite that never ran
    an assertion scored every mutant killed and printed "no surviving mutants".
    A tool for certifying that tests can fail, unable to notice it could not
    itself fail.
  - `check_plan_totals.py` — an unparseable estimate hit the same `continue` as
    the column-header row, so an annotated cell was dropped from the sum in
    silence, and the cheapest route to green was to change the total.
  - `check_test_integrity.py` — `rglob` on a nonexistent path yields nothing, so
    `check_test_integrity /nope` printed "clean" and exited **0**. Latent, not
    live: `ci.yml` carries `working-directory: apps/api`, so the gate's
    correctness lived in a line in a DIFFERENT file that nothing checks.

  One shape: **"I could not look" sharing a branch with "nothing to complain
  about".** The rule against it was already written down when the second and
  third were produced, which is D-051's own finding — so the countermeasure is a
  step in the procedure, not more resolve. Before the first line of a new
  checker, list every `return 0` / `continue` / `pass` it will have and write
  beside each one what the input looked like. Any entry whose answer is "I don't
  know" or "there was nothing there" is the bug.
- **A PATTERN THAT WAS CORRECT IN ITS ORIGINAL CONTEXT CARRIES NO MARKER
  SAYING WHAT MADE IT CORRECT. When you reach for a known-good shape, state what
  PROPERTY of the original made it right, and check that the property holds
  here.** Copying a shape that works is the cheapest way to be wrong while
  looking careful: the reviewer sees a form this repo already endorses and the
  author has an honest reason for choosing it. The failure is not the copy — it
  is that the ORIGINAL had a precondition nobody wrote down.

  - **A pointer at a duplicated cross-language literal.** `SCHEMA_REASON_PREFIX`
    says why it is on THAT side: the window is closed by whoever edits THIS
    constant, who would otherwise have no way to know the copy exists. The
    property is **the pointer sits where the change originates** — one on the
    consuming side closes nothing, because the person renaming the API literal
    never opens the web file.
  - **Two helpers that choose between a server's sentence and local copy.** One
    withholds it, one prefers it, and both are right. The deciding property is
    whether the LOCAL copy carries information the server's does not — not which
    module the caller lives in, which is the thing that looks like the
    difference. Only the withholding side records that reasoning; **write it
    into the side that lacks it.**

  **The test is one sentence, and it goes in the code rather than the PR:** name
  the property, then say why it holds here. If you cannot name it, you have
  copied a form rather than a decision. This is the twin-sweep rule reflected —
  that one says a defect found in one place exists in its twins until checked,
  this one says a SOLUTION does not transfer until checked.

- **A SELECTOR THAT SELECTS NOTHING PASSES. ASSERT THE COUNT IT SELECTED
  BEFORE READING ITS RESULT.** Same family as the silent-success branch, one
  layer out: there the checker looked and had nothing to say; here it never
  looked, and the green is indistinguishable.

  | The selector | What it selected | What it reported |
  | --- | --- | --- |
  | `pytest -k <filter>` | zero of the four tests reading a renamed key | green |
  | `pytest --collect-only` | everything, and ran none of it | a count |
  | `if "--check-registry" in argv` | nothing; fell through to the report path | exit 0 |
  | a flag the script does not implement | nothing; ignored | the success banner |

  **The remedy is the same in all four: make the count part of the result.**
  `-k` prints how many it deselected — read it. A grep for the SUBJECT beats a
  filter you believe in: on the renamed key, `-k` came back green and `grep`
  found all four consumers.

  **AND A FIXTURE THAT BUILDS AN UNREACHABLE STATE IS THE SAME DEFECT AT THE
  INPUT END.** A dashboard fixture set `tier = None` while leaving likelihood
  and impact intact, but the writer computes `tier_for(lk, im) ... else None`,
  so a null tier ALWAYS travels with null operands. The fixture built the one
  state the application cannot reach, and it was the one state where the banner
  under test made a false claim about its own data. Ask of the SETUP: **can the
  system under test produce this state?** If you cannot name the writer that
  does it, the test is about a different system.
- **"THE DISCLOSURE REACHES A SCREEN" IS PART OF THE DEFINITION OF DONE FOR ANY
  PR THAT ADDS A PROVENANCE FIELD.** A field recording what was withheld,
  dropped, rejected, unconfirmed or not-looked-at is finished only when a person
  can see it without querying the API: **on a screen OR in a delivered
  artifact.** The artifact half is not padding — the canonical instance lives in
  an EXPORT (`source_rows_total` and `withheld` in `tech_debt/exporters.py` and
  `attack/exporters.py`, including the exclusion disclosure that understated
  spend by $240,000), so read as screens-only, a PR adding a withheld count
  consumed solely by the XLSX exporter records no exemption.

  **Ownership, decided on #244: the pages under `apps/web/src/app/**` AND THE
  COMPONENTS THEY RENDER belong to whichever track owns the API surface the page
  reads. Dashboards go to the service track that produces their numbers.**
  Where a page reads SEVERAL API surfaces or NONE, it belongs to the track that
  owns the numbers the page exists to show — without that clause the rule yields
  NO owner for the nine pages reading no service API, and two tracks each
  conclude the other owns the work, reproducing #244 under the rule written to
  end it. "And the components they render" is load-bearing: the lead instance,
  `components/admin/AuditViewer.tsx`, is not under `app/**` at all.

  The reason is the load-bearing part: **the person who writes the honesty
  string is the one who knows what it means.** #244's instance 3 is a panel
  printing "Every source row is accounted for" over a discarded list.

  **Ownership alone only relocates the follow-up.** Every discard counter #122,
  #132 and the enum work added goes into the audit `details` payload, and
  nothing under `apps/web` reads it (#322) — the field is declared on
  `AuditEntryRow`, so the data reaches the browser and is discarded THERE.
  `entries_written`, `entries_received` and `discarded_entries` match nothing
  under `apps/web`. #316's `excluded_inputs` reached one HTTP response and died
  on reload. Each shipped with its record written where the success is, and
  stopped one layer short of anyone seeing it.

  **THE MECHANISM EXISTS**: `check_disclosure_consumers.py`, wired into
  `ci.yml`. Two things were wrong in its first version: **it matches per
  SERVICE, not across one pooled blob** (field names are not unique across
  models, so a pooled search let Risk's fields pass on ATT&CK's renderer and the
  gate ran green over a live instance of the defect it catches, #372); and
  **both surfaces are checked, the exporter half being load-bearing** —
  `unusable_target_codes` reaches no screen at all, so a web-only gate would
  report a defect over a field that reaches the client's deliverable. Residuals
  are in its docstring; the largest is that the predicate is prefix-anchored, so
  `unconfirmed_citations` and a bare `dropped` are invisible (#373).

  The gate is a floor, not a census. **The endpoint is not the surface** — open
  the component the reader uses and confirm it renders.

- **A USER-FACING string naming an action must name a control that exists and
  works TODAY — verified by opening the handler, not by knowing the domain.**
  Knowing the domain is what lets you write a plausible remedy without checking
  it: the recorded instances were written by people who understood the system.
  A message with no remedy is fine; an imperative is a promise the thing exists.
  Worse than a false docstring, because a developer who acts on one learns the
  truth in an hour and a client who acts on false copy learns nothing. **D-076**
  carries the recorded instances and the three-step check.

- **A comment or message stating a rule NARROWER than the reader will assume,
  positioned exactly where they would go to check, is worse than no comment.**
  It is true, so nothing flags it; it is where you look, so it ends the search;
  and it reads as a guarantee rather than as a scope. The instances, most in the
  redaction subsystem within two days:

  - `# noqa: S105 - dev placeholder, refused in prod via assert_safe_for_runtime`
    beside the JWT signing secret. True. The guard covered one of three
    environments, and this sentence is why nobody checked the other two (#142).
  - `"SHIELD_REDACTION_MODE=off is forbidden when ENVIRONMENT=production"` — the
    runtime error the guard raises, naming a narrower rule than the one that
    should exist, in the string a developer reads while debugging it.
  - `_redacted_form`'s docstring claiming it used "the SAME redactor the egress
    path uses" while calling one rule out of ten. The docstring even argued
    correctly that a second copy would drift, directly above the second copy.
  - `redact.py`'s separator note, wrong on arrival rather than stale (#158).

  Every one was found by reading the CODE and comparing, never by reading the
  prose — which is the only method that works, because the prose is accurate.
  The countermeasure is mechanical: when a comment states a condition, read the
  condition it describes and check the two agree in SCOPE, not just in truth.
  And when you fix such a guard, fix its message in the same commit — an error
  string is documentation a developer reads under pressure.
- **Replacing a validator gives you a free ORACLE for exactly one round: the
  thing you are replacing.**
  <!-- counted: "one round" is a duration in the claim itself, not a recalled figure -->
  Enumeration depends on imagining cases, and the cases you fail to imagine are
  precisely the ones that leak. Item 10 replaced a phone regex; its REDACT half
  was one grouping, so four formats the OLD rule caught — including
  `1-800-555-0199` and any number separated by a non-ASCII space — leaked
  silently. Nobody imagined them; the adversarial reviewer found them by reading.
  <!-- counted: historical -->

  The mechanical version costs nothing: **run the old rule and the new rule over
  the same corpus and diff their match sets.** Every input the old one caught
  and the new one does not is either an intended false-positive fix or a new
  leak, and you must classify each. It works for any validator, filter, guard or
  parser being replaced — and only for that one round, because after the old one
  <!-- counted: "one round" is a duration in the claim itself, not a recalled figure -->
  is deleted the oracle is gone. **Capture the diff while you still have both.**

  **A published standard is to a keyword list what the old rule is to a
  replacement pattern.** #139 asked which facility designators to add, and the
  honest answer to "which ones did I think of" is always "the ones I thought
  of". USPS Publication 28 Appendix C2 is the approved list, so the question
  became a lookup, and the table asserts every covered row redacts and every
  exclusion still does not — complete against a standard rather than against
  recall. It also gave the residual a better reason: `Level` is excluded because
  **it is not on Pub 28 C2 at all**, not because "patch level 3 is inseparable
  from a floor" — a phrasing that invites the next person to attempt the
  separation and fail identically.

  Enumeration finds what you thought of; the oracle finds what the previous
  author — or the standards body — thought of.
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
  `res.json()` and then falls back to `res.text()` throws "body stream already
  read", and THAT TypeError propagates in place of the typed error the block
  exists to build — destroying the status and the correlation id at the moment
  they are needed. Read the body once with `res.text()`, then `JSON.parse` it.

  **This entry used to say the 2026-08-04 pass fixed it "in all six
  `lib/*/client.ts` wrappers". That was true of the glob and false of the
  defect, and it is why nobody looked again for four weeks.** Swept by SHAPE on
  2026-09-09, five more sites had it: `lib/api.ts` — the shared wrapper the six
  call — plus `lib/admin/audit.ts` and `lib/ai/preview.ts`, whose
  `AuditProxyError` and `AiPreviewError` were equally never constructed, and
  both `lib/intake/` helpers. Filed as #174, which itself named only
  `lib/api.ts`. **The transferable part is the failure, not the count: the sweep
  predicate was a PATH instead of a defect.** A completed sweep over
  `lib/*/client.ts` reads as a completed sweep, and the sentence recording it is
  what stops the next reader checking.
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
  `SHIELD_EMAIL_DELIVERY_ENABLED` turns on real SMTP sending (MailHog in dev, UI
  :8025); enabling it without an SMTP host refuses to boot. Flipping
  REQUIRE_EMAIL_VERIFY breaks every e2e sign-in (seeded/spec users are
  unverified) — enforcement is a deploy-time choice, not a dev default.

## How we collaborate (two developers + agents)

Dave (SpearheadAnalytica) and Gene (gene-png, repo owner). Git is the sync
mechanism; docs carry only what git can't show.

| File | Role | Who writes |
|---|---|---|
| `CLAUDE.md` | Durable facts, principles, gotchas | Both — append/refine in PRs |
| `.claude/agents/*.md` | Agent definitions: territory, gates, merge rules | Both — PR; each agent re-reads its own from disk |
| `.claude/settings.json` | Committed Claude Code config. `env` only | Both — PR. Never `permissions`/`hooks` |
| `CONTEXT.md` | Project status as of `main` | Updated as part of a PR, never outside one |
| `context/dave.md` | Dave's in-flight status | **Dave ONLY.** Read for awareness; never write it |
| `context/gene.md` | Gene's in-flight status | **The agent maintains it; Gene owns it by REVIEW, in the PR.** He keeps every decision in the file and gives up typing it |
| `DECISIONS.md` | Append-only decision log (D-numbers) | Both — append in the PR that makes the decision |
| `docs/architecture.md` | Structure | Updated in the PR that changes architecture |
| `SPRINT_<n>.md` | Per-sprint plan (immutable once the sprint closes) | Sprint author |
| `DELIVERY_PLAN.md` | Path to MVP: order, status, blockers, sizes. The **MVP completion path** section is LIVING — update an item's status in the PR that lands it, never afterwards. Sprint sections below it are historical | Both |
| `SMOKE_TEST.md` | QA checklist — a box is checked ONLY if a green committed spec proves it, annotated with the spec filename | Both, honesty convention enforced |

### The size ratchet: this file is INSTRUCTIONS, `DECISIONS.md` is the RECORD

**THIS IS NOW A GATE, not an aspiration.** `apps/api/scripts/check_claude_md_size.py`
refuses this file above 150,000 bytes, which is the size at which a reader
silently truncates it. It reached 210,958 bytes on 2026-09-22 and the merge
rule's condition-5 path list was in the 29% that got cut — the most
consequential rule in the repo, unreadable, with every gate green (**D-079**,
#347). The file's own 600-line budget is reported by the gate and NOT enforced;
enforcing it today would hold the repo permanently red, which teaches everyone
to route around the gate.

**The split is the whole rule.** If a paragraph says what to DO, it belongs
here. If it says what HAPPENED, it belongs in `DECISIONS.md` under a D-number,
cited here in one line. Most of the length this file keeps acquiring is
incident narrative — *how* a defect was found, *who* found it, *how many*
rounds it took. That is worth keeping. It is not worth keeping HERE, because
every reader pays for it on every read and the instruction it supports is
usually one sentence.

**How the trim happens: incrementally, in whatever PR next touches this file.**
Never as its own project — except when the gate is red, an exemption added by
the PR that did exactly that (#347). Read it as a decision that was taken, not
as a principle that was followed.

**What the budget does NOT license.** It is not a reason to delete a rule
because it is long. Load-bearing rules stay at any length:

- **Verify by running.** The highest-value rule in this file.
- **"AI suggests, code computes"** and **FAIL LOUDLY** — core principles 1 and 2.
- **The gate suite** and the reasons each gate exists.
- **The merge rule.** Keeping it ACCURATE is mandatory and is not "growth":
  condition 1 says to re-derive its check count when a job is added, and D-059
  says to re-derive its measurement whenever condition 5 changes. Never leave a
  known gap in it because a budget said not to grow. What to resist is growth
  in KIND — another condition, another worked example. If it becomes
  unholdable, restructure the presentation rather than freeze a rule whose own
  conditions mandate re-derivation.

**And ORDER is now part of the rule, because truncation cuts from the end.**
What a partial reader loses is decided by position, so the merge rule sits at
the top of this file and stays there.

Rules of the road:

- **A closing keyword beside an issue number closes it — and CI now enforces
  this, so it is a check rather than a rule you have to remember.** GitHub's
  parser matches `fix(e[sd])?|close[sd]?|resolve[sd]?` followed by `#N` and does
  not read the words around it. Write `filed as #NNN`, `see #NNN`, or `tracked
  in #NNN` instead.

  **It reads three places: the PR title, the PR description, and every commit
  message.** The description is parsed independently of the commits. **Quotes,
  code fences and HTML comments are not exempt**, and in examples use `#NNN` — a
  placeholder with **no digits**, never a made-up number, because issue numbers
  only go up and a keyword beside an invented number is inert today and live the
  day the repo reaches it.

  **THE NEGATION IS INVISIBLE TO THE MATCHER, so an HONEST SCOPE STATEMENT is
  the sentence most likely to close an issue by accident.** `does not fix #N`,
  `partially fixes #N` and `not fixed by this PR: #N` all match. That is worse
  than it sounds, because it is a sentence a careful author writes ON PURPOSE:
  a PR that fixes a symptom and says the underlying defect is untouched is one
  merge away from closing the issue it just disclaimed. **The more honest the
  write-up, the likelier the trip.** Phrase it without a closing verb beside the
  number. **Do NOT reach for `Auto-close-approved:`** to get past this red; that
  line approves exactly the outcome the sentence exists to prevent.

  The mechanism is `check_issue_references.py`, wired as the required check **"No
  accidental issue closes"**. If a close is intended, say so in the PR
  description — bare numbers, no `#`, because a marker containing the word
  "close" beside `#N` would itself be an instance of the bug:

      Auto-close-approved: <issue numbers, bare>

  **`Auto-close-approved:` authorises the guard; it does NOT close the issue.**
  A PR with the approval line and no keyword merges without closing anything,
  leaving a fixed bug on the mvp-blocking list asserting a defect that no longer
  exists. Write both, then confirm with `gh pr view <n> --json
  closingIssuesReferences` before you merge.

  **Why this is mechanised rather than documented.** The same issue was closed
  by accident three times: each fix was a better-worded rule, the second
  incident was the PR documenting the first, and the third was a sentence
  warning about the second.
- **Run the adversarial reviewer, and record the audit in the PR body.**
  `.claude/agents/adversarial-reviewer.md` via the Agent tool. Run it before you
  open the PR, and **again after any substantive change** — a rule that fires
  once at open misses the patch that looked done and was not. **Never a
  self-audit instead**: D-054's gate proves an audit was *recorded*, not that it
  happened.

  **It always runs, on every surface including prose. What changes is what
  BLOCKS.** Advisory findings are FILED with an issue number rather than fixed
  before merge. **The labels and the test between them live in the agent file
  and are deliberately NOT restated here** — an abridged copy is how the
  direct-to-`main` exception once shipped licensing a push for an item it
  omitted.

  **The gate ("Adversarial audit recorded", `check_audit_evidence.py`) wants a
  literal section.** Prose describing an audit is explicitly not enough:

      ## Adversarial audit
      Findings: none
      Disposition: nothing to act on
      Scope: reviewed at <sha>, from `../review-<sha>` (detached worktree)

  **DISPATCH AGAINST A DETACHED WORKTREE** — `git worktree add --detach
  ../review-<sha> <sha>` — and give the reviewer that absolute path. It starts
  no containers, binds no ports, needs no `.env`, and `--detach` takes no
  branch, so a checkout in the shared tree cannot move underneath it. That makes
  "ran, but not against this change" impossible rather than merely detectable.
  The reviewer's own `Scope:` line states what it could not reach; yours states
  what it was POINTED at.

  **State per finding whether it is INTRODUCED or PRE-EXISTING.** The reviewer
  cannot run `git diff`, so every finding arrives attributed to the author by
  default. The claim is checkable by `git blame` and costs one word.

  **Docs-only PRs are exempt from the GATE and not from this RULE.** Use
  judgement on a typo; not on a document stating a number or a rule.

  Three things that make the run worth its cost: **point it at the VERDICTS and
  the METHOD** when the work is itself a review or sweep (a sweep that finds
  nothing is indistinguishable from one that looked in the wrong places);
  **re-verify every finding** before acting, since it executes nothing and is
  confidently wrong often enough to matter; and **a finding it upholds is a
  result worth recording**, not a null.

  **A reviewer that has not delivered is not a reviewer that failed. ASK IT,
  IMMEDIATELY AND EVERY TIME.** `idle` is not a delivery signal. Asking costs
  nothing. **Declaring the channel broken is a different act and needs
  evidence** — a tool error, a refusal, a named absence; "it has been a while"
  is not. An open list of how it can be unavailable:

  | Kind | What to do |
  | --- | --- |
  | **Absent** — agent type not in the environment | nothing to retry |
  | **Erroring** — dispatches and returns nothing usable | retry once, then treat as absent |
  | **Timed out / killed mid-run** | retry once, narrower; record partial findings AS partial |
  | **Not dispatched** — you did not run it | say which instruction conflicted; "absent" here is false |
  | **Ran, reported to nobody** — plain-text output is not transmitted to the dispatcher at all | ask for the report; silence looks identical to absent and crashed |
  | **Ran, not against this change** — stale tree, wrong branch, exhausted context | the detached worktree above prevents it |

  **The audit section must not lie about which happened.** Write `Findings: not
  run — reviewer absent` (or `erroring`, `timed out`, `not dispatched: <what
  conflicted>`). Never `Findings: none`: "none" is a claim about the code and
  "not run" is a claim about the process, and the gate accepts both because it
  only checks the lines exist.

  **A STATUS WORD FOR AN ACTION NEVER TAKEN IS NOT STALENESS.** `Findings:
  dispatched, UNDELIVERED at open`, written with nothing dispatched, was never
  true. Enumerating states does not prevent it; the status-word rule does — **a
  status word carries its output**, and `dispatched` carries the tool result.
  **Correct it IN PLACE, visibly**: an audit block quietly repaired reads
  exactly like one that was always right.

  **Who may decide a PR ships without it: the human dev at the keyboard, by
  name, in the PR body.** Never an agent, never by inference from silence, never
  the author when the author is an agent. That authorisation is prose and
  nothing checks it — `enforce_admins` is false and both devs are admins, so
  either can already merge past a red gate. **The checkable version is a GitHub
  review approval** (`gh pr review --approve`) from the named human. A blocked
  PR waits, and its issue gets a comment saying it is blocked on tooling.

  **This rule is unenforceable and unobservable, and is written down anyway.**
  W8b — the reviewer as a CI job — would bind it and is deferred. Do not read it
  as a mechanism. D-057 reverses part of D-054; **D-079** carries what the drift
  cost. If running it conflicts with another instruction, **say so out loud
  rather than resolving it quietly** — that silent resolution is the exact
  failure D-054 was written about.
- **When you cite a rule as the REASON for a constraint, the citation is a claim
  and gets checked like one.** Instances from 2026-08-30, all in agent
  definitions, all where the constraint was RIGHT and the reason was false:
  `enforce_ai_rate_limit` attributed to `/ai/preview` when it guards five
  endpoints including the one in the agent's own file; `zt/exporters.py` cited to
  merge-rule condition 5 when condition 5 does not list it (condition 6 does);
  `DECISIONS.md` cited to condition 3 when condition 3 names three files and not
  that one.

  **A correct constraint with a false citation is worse than an unexplained
  one.** This repo tells every agent to verify what it reads — so the agent
  checks the reason, finds it false, and may discard an instruction that was
  right. An unexplained constraint merely lacks support; a miscited one actively
  argues against itself.

- **GIT WORKTREES ISOLATE FILES. THEY DO NOT ISOLATE A DOCKER-COMPOSE STACK.**
  `docker-compose.yml` hardcodes `name: shield-v2` and binds `./apps/api:/app`,
  so `docker compose exec` from ANY tree attaches to the same container, mounted
  from whichever tree last ran `up`. Two worktrees created to give two agents
  structural isolation would have run every containerised gate against a third
  tree.

  **A second stack was weighed and WITHDRAWN** — it needs its own
  `COMPOSE_PROJECT_NAME`, ports, `.env` (gitignored, so `git worktree add` never
  creates one) and duplicated services, with host-run e2e binding `:3000` from
  both. **Agents take turns in one tree.**

  **For the WEB toolchain they no longer have to:** `scripts/verify-in-worktree.sh`
  runs tsc, vitest or eslint against the worktree you are standing in, in a
  `--rm` container touching no running service. It needs no `pnpm install` —
  `node_modules` are named volumes. The one thing NOT in a volume is
  `packages/*/node_modules`, gitignored and missing from every fresh worktree;
  the script mounts it read-only from the primary tree, and that single line is
  what makes it work.

  **`--self-test` is the part that matters.** It appends a deliberate type
  error, proves the write landed with `grep`, requires the run to go RED, and
  removes it. A green from the wrong mount is indistinguishable from a green
  from your own work — a typecheck once returned 0 while the container was
  mounted from a tree containing none of that branch.

  **The shared stack is still required for e2e**, the only residual. **The rule
  is bounded by its REASON, not by the word "worktree"**: a worktree that starts
  no containers, runs no gates and writes nothing is outside it — which is what
  makes the read-only reviewer dispatch above safe. Where one tree is kept
  anyway, detect a switch with `git reflog show HEAD | wc -l` sampled before and
  after; **`git rev-parse HEAD` cannot do this**, because a switch away and back
  leaves it byte-identical. Tracked in #203.

- **While any agent holds the shared tree, the ORCHESTRATING SESSION changes
  nothing that agent's work or its gates depend on.** That sentence is the rule;
  what follows is examples and NOT the set. "Agents take turns in one tree" and
  the agent definitions' "only one runs at a time" bind the AGENTS — not the
  session driving them, which has no definition of its own to carry a rule.

  The dependency set is wider than the checkout: tracked files and the index;
  **untracked and ignored** files (the root `.env` decides `SHIELD_LLM_MODE`;
  `.claude/sprint-queue.json` is loop state); shared refs and the object store —
  `git stash drop`, `git branch -D`, `git tag -d` and `git gc --prune=now` write
  no tracked file and are the destructive ones, and `refs/stash` is shared by
  every linked worktree; and **the single Docker stack** every containerised
  gate attaches to. Creating a ref nothing else reads is fine; deleting or
  renumbering one is not.

  **A worktree at another path is not an exemption, and "host-side" is not the
  test.** Host-run Playwright e2e issues no `docker compose exec` and still
  drives the shared containers on `:3000`. The test is whether the work needs
  anything from the shared stack or the shared refs. A worktree cut from an old
  branch also carries a stale `CLAUDE.md`. Tracked in #203.

- **Two rules for reading a result, and they are one instinct against two
  failure modes.**

  **PREFER THE MOST PRIMITIVE AVAILABLE SIGNAL.** Every layer of presentation
  between you and the raw fact is somewhere a plausible wrong answer can live,
  and it arrives in the right format, in the place the real one goes. Measured
  2026-09-01:

  | Read | Should have read |
  | --- | --- |
  | `head`'s exit status through a pipe | `${PIPESTATUS[0]}` |
  | pytest's printed summary line | the exit code |
  | `od -c` output grepped for `\r` | `d.count(b'\r')` |
  | a detached run's marker EXISTS | the marker's AGE |
  | a suite's exit code | which TREE, at which REVISION, it ran against |

  The marker row was a success record from a run a week earlier, read as the
  current one: `test -f /tmp/x.exit` tests existence, not freshness. **`rm -f`
  the marker before launching, or use a per-run filename.** The tree row: a
  backgrounded suite returned exit 0 while the fix it covered had been reverted
  seconds earlier by a careless `git checkout -- <file>`, which restores from
  the INDEX, so unstaged work goes with the mutation being undone. **Have the
  run print the revision and cleanliness of the tree it is testing.**

  **PREFER A CHECK WHOSE TWO SIDES CAN ONLY AGREE IF THE THING IS TRUE.** After
  converting a file to LF, `git diff --numstat` raw versus `--ignore-cr-at-eol`
  beats both `file(1)` and a byte count, because its two numbers **converge only
  if the CRs are gone** — it has an internal contradiction available to it and
  would have to fail loudly to be wrong. Same property as red-on-revert.

  **And two readings agreeing does not validate a third that disagrees.** There,
  `file` and the byte count agreed against `od | grep`, and preferring the
  majority got the right answer for the wrong reason: `od -c` renders `\r`
  inside multi-byte sequences as literal text, so grepping its output counts
  RENDERED LINES. It answered a different question in the same units, the
  hardest kind to catch. **Diagnose the disagreement; do not vote on it.**

- **"IS THIS ALREADY LANDED?" HAS EXACTLY ONE SOUND TEST HERE, AND IT IS NOT
  ANCESTRY AND NOT A DIFF.** Merge it and count what it stages:

      git worktree add --detach ../landed-check origin/main
      cd ../landed-check
      git merge --no-commit --no-ff origin/<branch>
      git diff --cached --name-only | wc -l     # 0 = the content is already on main
      git merge --abort

  **Run it against a branch you KNOW is unlanded in the same pass.** A test that
  returns 0 for everything answers the question you wanted and means nothing.

  **Why `git merge-base --is-ancestor` is the wrong tool: THIS REPO
  SQUASH-MERGES.**
  <!-- counted: the cardinality of a squash merge by definition, not a tally of a population -->
  A squash creates one new commit whose parent is `main`'s, so a branch's own
  commits never become ancestors of `main` however completely its content
  landed. `--is-ancestor` answers NO for every PR this repo has ever merged. It
  is not a weak signal, it is a constant.

  **Why a file count is the wrong tool, and this one is subtler.**
  `git diff main <branch>` answers "how do these two trees differ";
  `git diff main...<branch>` answers "what did this branch ADD". Read the first
  as the second and a branch whose base is behind looks like it contributes
  every file `main` has moved on since. Measured 2026-09-21: a branch reported
  as "21 files differ" was 131 insertions against 3169 deletions, the deletions
  being `main`'s own work, which merging can never remove.

  Both mistakes were made on the same question within an hour, by two people,
  with two different instruments, and both answers were shaped like the right
  one. A third reading — pointing the CORRECT test at a different branch than
  the one being asked about — produced a confident "already landed" for a branch
  contributing nineteen files. **Name the branch the test ran against in the
  same breath as the result.**

- **"READY" IS TWO CLAIMS. GREEN AND MERGEABLE ARE DIFFERENT, AND A CI
  CERTIFICATE IS ABOUT A HEAD, NOT A BRANCH.** Before reporting a PR ready, run
  the merge and report both:

      git worktree add --detach ../mergecheck origin/<branch>
      git -C ../mergecheck merge --no-commit --no-ff origin/main    # 0 = mergeable

  `gh pr view <n> --json mergeable,mergeStateStatus,headRefOid` gives the same
  verdict in one call and also gives the head the checks ran against. **Compare
  that head to the branch tip and to `main`** — a green certificate is evidence
  about the commit that was tested, and it survives, unchanged and reassuring,
  after `main` has moved underneath it. Measured 2026-09-10: three PRs reported
  "green on all 7 — ready" on certificates older than `main`; the third was
  `CONFLICTING`, and the conflict was in the one file carrying a warning that a
  live bool guard is load-bearing. GitHub knew the whole time.

  **AND `MERGEABLE` SAYS NOTHING ABOUT THAT BRANCH AND ITS SIBLING.** Two PRs
  that each merge cleanly and conflict WITH EACH OTHER are both reported
  `MERGEABLE`, both green, and invisible; whichever merges first turns the other
  red, after the decision rather than before it. **Whenever two or more open PRs
  touch the same file, run the pairwise merge and say WHICH PAIRS you checked** —
  "they merge cleanly" over an unstated set is the
  certificate-over-the-wrong-proposition shape.

  **AND A THIRD CLAIM RIDES WITH THEM: WHAT THE PR WILL CLOSE, VERIFIED AGAINST
  `closingIssuesReferences` AND NEVER AGAINST THE APPROVAL MARKER.** Measured on
  #348: the body carried `Auto-close-approved: 84` and
  `closingIssuesReferences` returned **`[]`**. Merging it would have left #84
  FIXED AND OPEN on the mvp-blocking board — **a REPORTING failure, not a
  bookkeeping one**, because every status given afterwards would have been wrong
  by one issue and the next person planning from the board would have sized work
  <!-- counted: the MAGNITUDE of an off-by-one error, not a tally of a population -->
  against a lie.

- **A STATUS WORD CARRIES ITS OUTPUT, OR IT DOES NOT GO IN THE REPORT.**
  "Merged" carries the `git log --oneline -1 origin/main` line. "Pushed" carries
  the ref. "Dispatched" carries the tool result. "Green" carries the exit code.

  Measured 2026-09-01 — **false status claims, all in reports, none caught by
  the report:** "Merge this, then I rebase", about a PR that had never been
  opened; "Merged", with `main` unchanged, twice; "Running the adversarial
  reviewer now", with nothing dispatched. Every one was caught by a human
  checking the artifact in one command.

  **The asymmetry is the diagnosis.** Test output gets pasted without being
  asked; merges, pushes and dispatches do not — and that is exactly where all
  three failures landed. The words describing an ACTION TAKEN ELSEWHERE are the
  ones with no evidence attached, because the evidence lives in a system you
  have to go and ask. A resolution not to do it again is worthless here.
  **Putting the burden on the SENTENCE is what makes it hold**: a status word
  without its output is visibly incomplete to any reader in about a second.

- **THE REFLEX SURVIVES THE RULE UNTIL THE RULE HAS A GATE. A rule that lives
  only in prose gets followed on the item you are thinking about and skipped on
  the item next to it.** Measured 2026-09-01, in one batch of issue filings:
  **#175** was filed with the derived form and its body argues the case —
  naming five workspace packages goes stale on the sixth, so gate it off
  `pnpm-workspace.yaml`. **#173** was filed in the same batch as a list of two
  sites; there are six. **#174**, same batch, a list of one site; there are
  three. The author wrote the argument for derived sets and then, minutes later
  and twice, enumerated.

  **So the test of a rule is not whether it is written down, it is whether
  something fires.** When you find yourself writing a list of sites into an
  issue, a plan or a comment, write the PREDICATE and a one-line grep beside it,
  and say the enumeration was found incomplete. This is why
  `check_recalled_counts`, `check_plan_totals`, `check_separator_classes` and
  `check_claude_md_size` exist as scripts rather than as paragraphs.

- **PREFER A DERIVATION OVER A SYNCHRONIZATION. When you cannot, say which
  update closes the window and how wide it is.** A derived value cannot be out
  of sync; a synchronized one merely is not, right now, for reasons that have to
  keep holding.

  - `_HSPACE` as a **computed subtraction** from `\s` rather than a hand-listed
    character class. The list was wrong by sixteen characters and nothing could
    see it.
  - `_client_capability_inputs` as a **projection of**
    `_client_capability_membership` rather than a second query answering the
    same question: one query, one set of membership rules, so the allow-list and
    the payload cannot disagree.
  - A React panel's phase as a **derivation of the current id** —
    `loaded.serviceId === serviceId ? loaded.phase : {kind: "loading"}` — rather
    than a reset fired on change. The derivation evaluates in the render the
    prop change triggers, so there is **no window**. A `cancelled` flag alone
    fixes only the late-response half and leaves the stale-data half live.

  Each replaced something that had to be **kept** in sync with something that
  **cannot** be out of sync. Where a derivation is genuinely unavailable, name
  the closing update and the width of the gap in a comment — an unstated window
  is the one nobody tests.

- **`Query(ge=..., le=...)` OPTS A ROUTE OUT OF THE TYPED-ERROR CONVENTION
  WHILE LOOKING LIKE MORE VALIDATION.** FastAPI's own rejection of a bound
  parameter goes through `_handle_validation_error`, which emits `"Request
  validation failed."` with a `details` array and, since #307, a synthesised
  `schema_*` **`reason`**. A `schema_*` code is a machine token with no client
  copy behind it, so the web layer's D-016 mapping has nothing usable to key on
  — and #317 is what happened to the one consumer that read the key's PRESENCE
  as copy. Core principle 2 names a raw validation dump as what a user-facing
  error must not be. **So adding the bound makes the route stricter and its
  error less usable, in one edit, invisibly.**

  `routes/zt.py` decided this first and wrote down why; `routes/csf.py` reached
  for the bound and had to be corrected to match. **Where a route already
  refuses something with a typed `{reason, message}` detail, refuse the new
  thing the same way.** A declarative bound is right where nothing typed exists
  to be consistent with — a new endpoint, a parameter no client maps to copy —
  and its OpenAPI visibility is a real benefit there.

  The general form: a framework's built-in validation and this repo's error
  envelope are two different contracts, and moving a check from the second to
  the first is a silent downgrade for every consumer that reads `reason`.

  (This paragraph's stated MECHANISM has expired once already — it said "no
  `reason` key", true when written and false the day #307 merged. The
  conclusion was unchanged by that, which is why the mechanism is spelled out
  rather than asserted.)

- **A guard's message must name the CAUSE, not the CHECK.** One line covering
  three branches tells a reader that a check failed. Three lines tell them what
  is wrong. The difference only shows up while someone is debugging under
  pressure, which is the only time the message is read.

  The instance: a worktree precondition ran three greps and printed a single
  `HALT: worktree predates the agent layer` for all of them. Correct, and useless
  — the most plausible misreading was "the rebase did not work", when the actual
  cause was that there had been nothing to rebase onto. **A guard that fires
  correctly for a reason nobody would guess gets debugged in the wrong
  direction.** Each branch now names its own cause and what it implies.

- **PUT THE DISCRIMINATOR WHERE THE CONFUSED READER IS STANDING, not where the
  explanation lives.** A correct explanation sited one paragraph away from the
  symptom does not reach the person looking at the symptom — and it is worse
  than silence when a *different*, reassuring explanation is sited closer.

  The instance: the stash-archive block explains name collisions as normal
  ("these archives already carry suffixed names because the bare name was
  taken"), four lines below a command that, run in the wrong shell, makes *every*
  archive collide on one name. A reader hitting the collision meets the
  reassuring reason first, and it is true — of a different cause. The tell is
  disarmed before they reach anything that would distinguish the two. The fix
  was one clause at the reassuring sentence, saying which observation means
  which cause, rather than a better paragraph elsewhere.

  **When you document a failure, find the sentence a confused reader reaches
  FIRST and ask whether it sends them the wrong way.**

- **AN EXAMPLE OF A RULE BEING VIOLATED IS FALSIFIED BY THE RULE BEING FOLLOWED.
  Cite the rule's SCOPE, never an instance of the breach.** Citing a specific
  violation couples the citation's truth *inversely* to the rule working: the
  cited instance is the first thing anyone fixes, and fixing it makes your
  sentence false. It happened inside a single commit here — a file-wide rule was
  supported by naming one block that broke it, and the same commit marked that
  block. Picking a different instance re-arms it rather than repairing it. The
  durable form is structural: "command blocks appear under `## Environment
  gotchas` and `Rules of the road` too, and the SCOPE line does not reach them"
  (D-071).

- **A control that protects an agent from STALE STATE must be verifiable from
  INSIDE that state.** A rule written in a file the stale worktree does not have
  is a warning about stale state that is unreachable from the stale state —
  worse than no control, because it creates the belief the hazard is handled.
  Measured 2026-08-30: both agent definitions opened with "re-read `CLAUDE.md`
  and this file from disk", and neither file existed in either worktree, whose
  branches predate them. An agent doing step 0 there finds a disagreement it is
  told to report — and resolving it by preferring disk would run the wrong
  formatter under a rule set it cannot see is missing.

  The fix is not a better-worded rule. It is **three greps the agent executes
  first**, which halt it when its own worktree predates the layer. **And a guard
  must be observed in BOTH states before it is trusted**: watching it fire
  proves it fires, not that it passes, and a typo that halts unconditionally
  leaves every agent dead on arrival — indistinguishable from the hazard the
  guard exists to catch.

- **EVERY agent definition carries this line, written before the agent runs
  rather than after:** *"Re-read `CLAUDE.md` **and your own agent definition**
  from disk at the start of a task rather than trusting injected context. Report
  a disagreement between the two; never silently prefer either."*

  **"And your own agent definition" is load-bearing, and the first draft of this
  bullet omitted it.** The reviewer that caught the omission demonstrated it in
  the same run: its injected prompt carried a three-label disposition list while
  the file on disk had four, and it evaluated the fourth **only because it had
  been told to read from disk** — an instruction that named the wrong file and
  worked by accident. An agent whose own definition is stale applies a rule set
  nobody can see is missing, and it is the one file it will never think to check.

  **Injected context lags the file, and TRUNCATION is a second mechanism with
  the same signature.** A rule on disk and absent from context is produced by
  both, and the prescribed remedy for one — re-read from disk — is useless
  against the other. Distinguish them by measuring the file's SIZE before
  reaching for the familiar explanation (D-079). Lag instances accumulate on
  **#170** rather than in a count here.

  The risk scales with the number of agents: two agents operating on a rule set
  that predates the rules written FOR them produce work that passes every gate
  and violates a rule neither ever saw.

- **CITE A QUOTED STRING AND A FILE, NEVER A LINE NUMBER — and check a citation
  with `rg -U --multiline`, never bare `grep -n`. A line number is a property of
  a tree, not of a document.** Measured 2026-09-05: `DELIVERY_PLAN.md:980` and
  `:1078` are both correct for the same sentence, on `main` and on a branch
  inserting 111 lines above it.
  <!-- counted: git diff --stat origin/main..HEAD -- DELIVERY_PLAN.md -> 111 insertions, 2026-09-05 -->
  Two people each "verified" the other wrong, and both were right.

  The wrapping half is the dangerous one. Prose here wraps at 80 columns, so a
  quoted phrase longer than a few words usually straddles a line break and a
  line-wise `grep` returns NOTHING for text that is present:

      grep -n "the largest remaining gap" DELIVERY_PLAN.md            # no match
      rg -U --multiline -n "largest\s+remaining gap" DELIVERY_PLAN.md  # 1083-1084

  A multiline tool is necessary and NOT sufficient: a literal space still will
  not cross the wrap, because what is there is a newline and an indent. **Write
  every space in a quoted phrase as `\s+`.**

  **A no-match is a claim about the world. Before reporting an absence, confirm
  the tool could have found it** — re-search a fragment that cannot wrap. This
  nearly produced an accusation of fabrication against correctly-quoted text,
  and a case-sensitive search against an UPPERCASE heading nearly produced a
  second false absence in the same minute.

  **AND WHEN N INDEPENDENT SOURCES REPORT THE SAME ABSENCE, RUN THE SEARCH
  BEFORE NAMING A MECHANISM.** Four reviewers, in four separate runs against
  four different trees, each reported the same rule missing from this file. Each
  was dismissed as detached-worktree staleness — a real mechanism, documented
  here, and the first explanation that fits. The rule was simply not in the
  file. **Four independent observations of one fact are data, and a mechanism
  that explains them away costs one command to test.** "Your context is stale"
  explains any disagreement whatsoever, which is what should make it suspect
  rather than comfortable. D-079 is the second instance: truncation wearing
  #170's clothes.

- **A CITATION'S WORTH IS WHETHER IT FAILS LOUDLY. Pin to an immutable object
  where you can; where you must cite something mutable, the citation has to be
  MACHINE-CHECKED so the change trips something.** Three weaker forms were each
  proposed as the durable one and each broken: *"a claim about a completed
  action cannot be falsified by later action"* (false — one that AGGREGATES OVER
  AN OPEN POPULATION goes stale on the next member; `a3137d5..851348b`
  reproduces forever, `a3137d5..HEAD` does not); *"cite something that cannot
  change without someone having to edit it"* (false — a quoted phrase survived a
  correct edit that moved it into a `title` attribute); and *a quoted string is
  safe because it survives a reflow* (true of reflows and beside the point).

  **Rank the forms by how they fail.** A phrase quoted in prose just stops being
  there — **silent**. A phrase quoted in an ASSERTION is worse: it keeps
  reporting success, which is #72 reached from the citation rule.

  **A SHA is the loud form, and NOT because it stops resolving.** A rebase
  ORPHANS a commit without deleting it, so the object answers `git cat-file -t`
  with `commit` until garbage collection. A citation check asking "does this
  resolve?" PASSES on a SHA no longer on the branch. **What fails loudly is
  ANCESTRY, and only if someone asks:**

      git merge-base --is-ancestor <sha> HEAD

  Measured 2026-09-09 after a rebase: four cited SHAs all answered `cat-file -t`
  with `commit`, and none was an ancestor of the rebased tip. Two CI
  certificates and a review-coverage claim were pinned to one of them.

  **The gate this wants covers PR BODIES, not changed files** — both stale
  citations that prompted this rule were in bodies, and a body is not a file, so
  a tree-walking gate reaches neither. Not built.

  **A number carrying its command must also name its REF.** A unit-test total of
  7128 was written with its command and no tree; `main` later moved to 7128
  itself, so re-running on `main` REPRODUCED the number while the branch was
  really 7137 — a false confirmation manufactured by the one sentence whose
  purpose is to license not checking. Write `7137 (<command>, at d1d927d)`.

- **SPOT-CHECK a subagent's `file:line` citations before they enter a document,
  and record the check. A sample, not all of them — what you need is the
  report's CALIBRATION.** This replaces "be skeptical of subagent output", which
  is a disposition, and dispositions lose to convenience under time pressure.

  Measured 2026-08-30, a clean partition: of fourteen `file:line` citations that
  entered `DELIVERY_PLAN.md` from an Explore agent's report, **the eleven that
  were independently run were all correct and the three that were only read were
  all wrong.**

  **Sample a third, and round up** — at that hit rate, drawing 3 of 14 catches a
  bad citation only **55%** of the time.
  <!-- counted: python -c "from math import comb; print(1-comb(11,3)/comb(14,3))", 2026-08-30 -->
  An earlier draft asserted three checks "would have caught it", stating a 55%
  chance as a certainty, in the rule about not writing numbers you have not
  derived.

  **The sample CALIBRATES the report; it does not CLEAR the citations**, and the
  figures are conditional on this incident's error rate rather than a detection
  guarantee. Read the table as "how likely am I to learn this report is
  unreliable", never as "what fraction of bad citations do I catch".

  **And it assumes the bad citations are EXCHANGEABLE with the good ones, which
  here they demonstrably were not** — the three wrong were exactly the three
  nobody had executed, and drawing 11 with 0 bad has probability 1/364 under a
  random-draw model. **Sample the citations you have NOT executed**; three from
  that stratum would have been certain rather than 55%. **The wrong ones do not
  look wrong** — one was a bare closing paren, another a real line of code that
  reads plausibly in context. D-079 carries the arithmetic.

- **A plan entry that carries only a LOCATION is a derived value with a second
  place to be wrong. Name the MECHANISM instead, or as well.** "`clients.py:741`"
  goes stale the next time anyone reflows that function, silently.
  "`zt_dashboard` never calls `_zt_client_target_stage`, though `_zt_gap_total`
  does" survives the reflow and is greppable back to a line whenever one is
  needed. Line numbers are for finding the code today; the mechanism is what the
  entry is for.

  **Corollary: cite the FILE and the QUOTED STRING, never the line.** Write
  `DELIVERY_PLAN.md, the paragraph quoting "Total annual cost"` rather than
  `DELIVERY_PLAN.md:737` — the quoted string survives every reflow, is greppable
  in one command, and cannot silently point at the wrong paragraph.

  <!-- counted: historical -->
  Three instances on 2026-09-02, from three different causes: a reviewer's clone
  pinned to an older commit, so every citation was shifted; two plan notes added
  that morning moving a citation from :737 to :780 between one message and the
  next; and a gate's fail-closed branch moving :152 to :162 between two people
  reading the same file. None was a mistake anyone made. Every one was a correct
  number that had stopped being correct, and the wrong line usually still
  contains plausible code — which is what makes a stale citation worse than a
  missing one.

- **The rules for numbers in prose, and a gate that enforces the first two on
  the shared documents.** Every miss behind them is one pattern: a value written
  from memory instead of derived. **D-079** carries the instances, several of
  which are inside the paragraphs correcting earlier instances.

  1. **Don't write the count.** If a number describes a list in the same
     document, delete it and let the list be the count. "The blockers:" cannot
     go stale. **When the list lives OUTSIDE the document, write the COMMAND,
     not the number — and not a marker either**: rule 2's marker is a freshness
     CLAIM, and one certified 17 open blockers through an afternoon in which the
     figure changed twice. **Delete the COUNT, never the MAPPING** — "seventeen
     open blockers" is volatile, "#123 belongs to item 8" is durable.
  2. **Cite, don't recall.** A number from OUTSIDE the document carries the
     command that produced it and the date it was run:

         <!-- counted: gh issue list --label mvp-blocking --state open
              --json number | jq length, 2026-08-26 -->

     If you cannot paste the command, you do not know the number and must not
     write it. A measurement over a fixed window is a claim about history and
     does not rot, but carries its window and date for the same reason, **and it
     is re-derived when its inputs change**.
  3. **Correct at the instruction, not at the discussion.** Every miss landed
     where the topic was DISCUSSED while the line telling someone what to DO was
     left standing. A correction is UNVERIFIED until you have grepped the doc
     set for the claim's SUBJECT, and the correcting commit records the grep.
     **PROXIMITY CATCHES NOTHING RELIABLY — the grep is the only mechanism, at
     any distance.** A draft that drew a one-screen threshold left a
     contradiction two lines above its own correction, through a full reviewer
     pass. The question is never "was I careful" but "did I run the grep".
  4. **A subject sweep enumerates how the subject can be WRITTEN before it
     greps.** One literal is one spelling. Grep the bare noun, read every hit,
     and classify each — a sweep for a stale `prettier@3.9.5` found seven sites
     and was reported complete twice, while the subject was written four ways
     and one missed spelling was the largest defect on the branch.
  5. **A de-duplication that points at the NON-AUTHORITATIVE source is worse
     than the duplication it removes.** Three docs saying "the version the
     lockfile pins" were repointed at `package.json` to give it one home — but
     that holds a RANGE and CI installs `--frozen-lockfile`, so two had been
     correct before the edit. **Establish which source the machine reads.**

  **The gate is `apps/api/scripts/check_recalled_counts.py`**, blocking on
  `ENFORCED_TARGETS` and report-only on `context/*.md`. **NOT "the shared
  documents" — `DECISIONS.md` is in neither list**, and the gate prints the set
  it read on every clean result. It matches SPELLED cardinals and deliberately
  not digits, because "14 open" beside its command is the fixed form.

  **Two markers, not the same claim.** `<!-- counted: <command>, <date> -->` is
  rule 2 satisfied. `<!-- counted: historical -->` is for a count QUOTED as the
  record of a past event, which cannot grow. Neither may be used to silence a
  number you have not checked.

  **Limits, all found by using it.** The provenance window is the finding's line
  and two either side, so write markers on ONE line. Matching is PER LINE. The
  cardinal must sit NEXT TO the noun, so `thirteen recorded instances` is
  invisible where `nine instances` is caught — a floor, not a census, and **that
  <!-- counted: quoted illustrations of the pattern, not counts of anything -->
  is why rule 3 still matters after the gate exists**. The finding set is **NOT
  STABLE UNDER REFORMATTING, so run the gate AFTER the formatter**: `prettier
  --write` reflows prose and can move a count across or off a line break with no
  change to the sentence. **The gate cannot see itself** — its help text is a
  Python string, so the paragraph teaching this rule carried an uncited count of
  its own until a human read it.

  **The gate finds; it does not fix.** Every site gets its own disposition;
  where a finding is a false positive, say why at the site rather than widening
  the pattern. **It catches FORM; it cannot catch what a correct number
  IMPLIES** — it caught "Three checks drawn at random would have caught it", and
  <!-- counted: historical -- a verbatim quote of the phrase the gate caught, not a count -->
  the repair derived the true figure, 54.7%, then stated it so as to imply a
  detection guarantee it does not support. Form is mechanisable, implication is
  not; do not grow the gate into the second role.

- **Check `git stash list` DURING work, not only when stopping.** A stash is
  invisible to `git status`, survives a branch switch, and is one command from
  loss. An end-of-session check catches it far too late: this repo has one
  recorded instance of an entire governance change sitting stashed through a
  whole adversarial review, produced within an hour of running the checklist
  that names `git stash list`. The checklist was not wrong; it fires at the
  wrong time.
- **Archive a stash before dropping it -- salvage is a race, not a plan.**
  `git stash drop` frees the reflog slot and prints the commit's SHA; the commit
  stays in the object store until pruned. `git fsck --unreachable | grep commit`
  is git's documented recovery, but it races an unknown `gc`, returns unlabelled
  commits, and `git stash clear` prints no SHA at all. So archive first, and
  select **by SHA, never by index** -- an index names a different entry the
  moment anything else drops:

      sha=$(git rev-parse "stash@{<n>}")
      git tag "archive/stash-${sha:0:8}-<what-it-holds>" "$sha"
      git push origin "archive/stash-${sha:0:8}-<what-it-holds>"

  **Git Bash only. Run in PowerShell 5.1 on 2026-09-08, where it does something
  worse than fail:** `${sha:0:8}` is read as a variable named `sha:0:8`, which
  does not exist, so it expands to **nothing** -- `archive/stash--x`, no error,
  no SHA, and every stash archived that way collides on one name. No PowerShell
  equivalent is offered, deliberately: a marker covering the FAILURE does not
  cover a REMEDY (D-071).

  This repo's archives carry a branch AND a `-tag`-suffixed tag per stash
  because the bare name was taken. **But if EVERY archive collides on one name,
  that is the PowerShell expansion above, not a name clash** -- the
  discriminator matters because the sentence before it explains a collision
  away, and it is the one a confused reader reaches first.

  **Discharge any decision-hold on dropping by ENUMERATING the archived ref's
  parents, never by diffing it** -- a stash taken with `-u` keeps its untracked
  files on a THIRD parent, which `git stash show` cannot display at all:

      git rev-list --parents -n1 <ref>     # three parents means an untracked half
      git ls-tree -r --name-only <ref>^3   # and this lists what it holds

  A ref existing proves only that a ref was written, and a diffstat proves only
  the tracked half. **Drop highest-numbered first**; dropping `stash@{0}`
  renumbers every higher entry. **Assert the SHA immediately before each drop**
  — that is what catches an index that moved between archiving and dropping.
  Do none of this **while an agent holds the shared tree**.
- **Branch + PR for anything that changes behaviour or states a rule. Two
  exceptions go direct to `main`, and they are exceptions because practice
  already worked this way.**

  1. **`context/*.md`** — the personal status files. Owner-write-only by
     convention, read by the other dev for awareness, stale within hours.
  2. **Typo-class prose fixes** — a misspelling, a mangled character, a
     formatting slip. Nothing that changes what a reader would DO.

     **A broken link is NOT typo-class**, though it looks like one. Repointing a
     cross-reference is a judgement about where a reader should go, and "a
     pointer to something that no longer exists" is on the reviewer's BLOCKING
     (prose) list. Fixing one direct to `main` pushes an unreviewed judgement
     call, and `audit-gate.yml` triggers on `pull_request` only, so nothing
     would see it.

  **The boundary is the only test:** a prose fix that changes what someone would
  do is not typo-class. Those are PRs. **Read the BLOCKING (prose) list in the
  agent file rather than here** — an abridged copy of it is how this exception
  first shipped licensing direct pushes for one of the items it omitted.

  **Why this is a correction rather than a loosening.** Measured on
  <!-- counted: git log -25 --format=%s main | grep -cvE '[(]#[0-9]+[)]$', 2026-08-27 -->
  2026-08-27 over the last twenty-five commits on `main`: **nine were direct**,
  every one `docs(context):`, every one touching only `.md` files under
  `context/`. The rule said never; practice said always, for one specific and
  harmless class. A rule that is routinely and correctly ignored teaches that
  the rules here are advisory, which is expensive for the ones that are not.

  Everything else — code, tests, CI, gates, migrations, and any document stating
  a rule or a number someone acts on — is branch + PR.
- **The merge rule — when an agent may merge unattended — is at the TOP of
  this file**, under `## The merge rule`. It was here, at byte 192,494 of a
  210,958-byte file, and every reader with a size limit got the conditions
  without the path list that decides them (D-079). It is the one rule whose
  POSITION is load-bearing.
- **AN ISSUE IS FILED WITH ITS LABELS OR IT IS NOT FILED. Search first, and the
  search only works because everything else was labelled.** The board is
  `is:issue is:open label:mvp-blocking` ordered by tier. An issue without
  `mvp-blocking` is not on it; one with `mvp-blocking` and no tier has no place
  in the ordering. Either way it is invisible to the only view used to decide
  what to work on — not a slow record, an unreachable one.

  Every new issue carries, at creation: `mvp-blocking` + one of `tier-1` /
  `tier-2` / `tier-3`, OR `unowned-with-reason` with the reason in the body, OR
  `post-mvp` — deliberately deferred past the MVP, a decision rather than a
  backlog, and not a trigger: one that must come back gets the
  `scheduled-trigger` label and its `Trigger-date:` / `Trigger-reason:` lines.
  "Untriaged" is not a fourth option, because nothing ever comes back
  to triage it. `gh label list` is the authority for what exists, and
  `check_issue_labels.py` enforces the labels, not the reason (D-086).

  The tiers are a judgement about client-facing consequence, not effort:
  **tier-1** is live, unmitigated wrongness a client can reach — a number they
  never asked for, presented as one they did; **tier-2** is client-facing with a
  mitigation shipped, or no wrong number delivered; **tier-3** is wrongness that
  changes nothing about what the client ends up with. Label to the SHIPPED state rather than the threat model, and say
  on the issue which you did, so the call can be overturned instead of inherited.

  **The test is CONSEQUENCE, not audience:** an internal screen is not tier-3 by
  that fact. A consultant acting on a false screen is the last step of the
  DELIVERY path, so its consequence reaches the client. #70 and #74 are tier-2 even though every CSF
  and ATT&CK deliverable states its own coverage. A false "done" can still make
  a consultant release work they would not have released, so do not re-derive
  tier-3 from that measurement. The path is the delivery path, not any human. A
  reviewer or developer misled by a false gate is not on it, and what the gate
  lets through is tiered on its own merits (D-087). **A label's name is not its
  test:** `mvp-blocking` means "on the board", not "blocks the MVP". The scale
  has no term yet for compliance-record consequence (#528, D-087).

  Search before filing, knowing the search finds only what earlier filers
  labelled: #184 and #286 are the same defect, filed twice (D-086).

- **Write rich PR descriptions** (see PR #16 for the format: summary, task
  table, test plan, known follow-ups). The other person's agents orient from
  `gh pr view` — a good body saves them reading your whole diff.
- Conventional commits; end commit bodies with the model's co-author line.
- To see what your collaborator is doing: `gh pr list` + their `context/*.md`
  — not their unmerged branches.
- `.claude/sprint-queue.json` is machine-local loop runtime state (gitignored).
  **`.claude/settings.json` is COMMITTED and `.claude/settings.local.json` is
  NOT** (`.gitignore:66`). The committed one carries
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, so both devs get the flag — it lived
  in the gitignored file until 2026-08-30, which meant Dave never had it. Keep
  it `env`-only: **no `permissions`, no `hooks`**. `Bash(python -c ' *)` stays
  out of the allow-list permanently, because under Agent Teams a pre-approved
  permission is granted to every agent the team spawns rather than to the
  session that approved it, and a step needing Python belongs in
  `apps/api/scripts/` where the reviewer can read it. An empty allow-list means
  more prompts, which is the intended trade. Staged sprint queues
  (`.claude/sprint-queue.sprint-<n>.json`) ARE committed — the plan of record.
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

## If you cannot read this section, stop

**Why this section exists, and it is the finding the size gate alone does not
fix.** The reader limit is a property of the READER, not of this repository. On
2026-09-22 one session's injected copy carried all 210,958 bytes while another
reader's was cut at 150,000 — same commit, same file, different rule sets.
<!-- counted: "one session" names a single observed reader, not a tally of a population -->
Two agents can examine the same PR, apply the merge rule sincerely, and reach
opposite verdicts on condition 5, and **neither can tell which one it is**:
nothing in either agent's output distinguishes "this PR is clear" from "I could
not see the clause that would have caught it."

That is the exit-2 distinction this repo built its gate philosophy on — "I
checked and it passes" versus "I could not look" — missing from the governance
layer itself, in the one artifact that defines what checking means.
`check_claude_md_size.py` fixes today's instance; it cannot fix the mechanism,
because the file goes over budget again eventually, or some reader arrives with
a limit below 150,000, and it recurs silently. The canary converts an invisible
variance into a declared one — the same move as making a gate exit 2 instead
of 0 — **but only because the instruction to check for it is stated at the TOP
of this file and in every `.claude/agents/*.md`.** Stated only here, at the end,
it would address nobody: a truncated reader never receives this paragraph. The
first version of the canary did exactly that, and the adversarial reviewer
called it a necessary precondition that was not yet load-bearing.

**`check_claude_md_size.py --require-canary` asserts the marker is the LAST
non-empty line**, so a later edit cannot append past it and quietly push it out
of reach — which would restore the exact failure it exists to announce.

### Where the next 15,000 bytes come from

Written down BEFORE the alarm, because a gate that fires with no prepared remedy
reads as the gate being broken, and a gate that fires and names the next cut is
a ratchet. **The soft line is 135,000 bytes**; when it trips, take these in
order. Each is a RECORD whose instruction is already stated in one line above
it, so moving it loses no rule:

1. **The `## Environment gotchas` redaction-subsystem narratives** — the
   LEAVE-table oracle percentages. The rules are
   one sentence each; the stories belong under D-058. (The over-match and
   address-corpus stories already moved, to D-087, on 2026-09-24.)
2. **The worked examples under `Rules of the road`** — the sweep shape
   statement, the subagent-citation arithmetic, the stash-archive PowerShell
   measurements. All have a live D-number or issue already holding them.
3. **The per-instance lists** inside the numbers-in-prose, correction-paragraph
   and twin-sweep rules. Each is a list that grows, which is the defect those
   rules describe; they belong in D-079 and D-074, where a tally is expected to
   move.

Do NOT take the merge rule, the core principles, "verify by running", or the
gate suite. Those stay at any length, and the size ratchet above says so.

---

**If you cannot read the line below, your copy of `CLAUDE.md` is TRUNCATED.
Stop.** Say so, name the last heading you did receive, and do not apply the
merge rule or any condition test until someone confirms which clauses you are
missing. A truncated governance file is a control that does not exist.

<!-- CLAUDE-MD-CANARY: v1 -->
