# Gene's Context: 080426SHIELD

## PICK UP HERE — 2026-09-05 (end of session)

**Supersedes the 2026-09-04 section below.** That section is still accurate on
what the branch contains and why; it is WRONG on one instruction — see the
correction immediately below, which is the first thing to read.

### Correction: `/tmp/w.exit` is stale. Do not read it.

The 2026-09-04 session closed by telling Gene to read the result with `cat
/tmp/w.exit` and treat `exit 0` as the outstanding gate cleared. (The file's
2026-09-04 section itself only gives the launch and dot-count commands, so this
correction is about that closing instruction, not about text below.) Doing that
today reports a **false green**. Measured this session:

    docker compose exec -T api sh -lc 'ls -la --time-style=full-iso /tmp/w.exit /tmp/w.log'
    -rw-r--r-- ... 2026-09-05 15:19:01 +0000 /tmp/w.exit     <- contains "0"
    -rw-r--r-- ... 2026-09-05 15:48:39 +0000 /tmp/w.log      <- written LATER

The exit file was written **29 minutes before the log stopped growing**, so it
cannot be that run's exit code. And the run it claims to summarise did not
finish: the log ends mid-line at `[ 98%]` with 7025 dots and **no pytest summary
line at all** —

    docker compose exec -T api sh -lc 'grep -nE "passed|failed|error" /tmp/w.log'   # no output

The containers read `Up 8 minutes` at 20:14 UTC while the log had been untouched
since 15:48, so the `exec -d` process was killed by a container stop (host sleep
or Docker Desktop restart) roughly 53 tests from the end. `/tmp` survives a
container stop; the process does not.

**So: the full unit suite is STILL the outstanding gate. It has still never
completed green on the final tree.** Nothing about the 2026-09-04 evidence
changed — it is still strong, still composite, still not a single green run.

**Delete the stale artifacts before restarting, so this cannot be misread
again:**

    docker compose exec -T api sh -lc 'rm -f /tmp/w.exit /tmp/w.log /tmp/w.start'

### Instructions that fail by looking like success — the running record

Three this session, all the same shape: the check runs, returns something that
reads as a clean pass, and the pass is an artifact of the check rather than a
property of the thing checked. Recorded together because the shape matters more
than any one instance, and because two of the three came from Gene — authorship
is not a defence against it.

1. **The exit-file rule.** "`cat /tmp/w.exit`; `exit 0` clears the gate." The
   file said `0` and the run had died at 98%. Detail above.
2. **A format-check with no stated location.** Prescribed without saying which
   directory to run it in; a pnpm-root check and an `e2e/` check are different
   checks with the same command.
3. **`git diff --stat $(git log --before="20:22" -1 --format=%H)..HEAD`.**
   `--before="20:22"` parses as *today* at 20:22, which resolved to `67142b3` —
   HEAD itself. The command compared HEAD to HEAD and printed an empty diff,
   which is exactly what "no non-doc files changed" looks like. Anchor to the
   run's actual start instead, and never to a bare wall-clock time:

       git diff --stat $(git log --before="2026-09-05T00:22:19Z" -1 --format=%H)..HEAD

   Anchored that way the base is `e0efdba` and the range is `context/gene.md`
   alone, 266 insertions / 154 deletions, **no non-doc files**. Docs-only is now
   measured. It does not rescue the run — a tree that never moved and a run that
   died at 98% are independent facts, and only the second decides anything.

The general rule this produces: **a verification command must be able to fail.**
Before trusting a clean result, ask what a dirty one would have looked like and
confirm the command could have produced it.

### The `main` bypass is documented, and it is worse than "unchecked"

Both docs-only pushes to `main` this session printed `Bypassed rule violations`
— "Changes must be made through a pull request" and "7 of 7 required status
checks are expected". That **confirms the documented posture rather than
revealing a gap**, so it is a decision for Gene, not a defect to fix:

- `docs/security.md` — "branch protection has `enforce_admins: false`, so both
  developers can merge past every check above".
- `DELIVERY_PLAN.md` — the precise statement, under the heading "Branch
  protection: configured 2026-08-20, verified 2026-08-21": "Required checks
  bind **a non-admin merging via a pull request**. This repo has no such person
  today." The same bullet list calls the direct-push hole "the largest /
  remaining gap" — that phrase WRAPS, so search it with `rg -U --multiline`.
- `DECISIONS.md` — the same correction, recorded as an overstatement an
  adversarial pass caught: "the gate is a guardrail on the PR path, not a wall
  around `main`".

(Quoted, not numbered, per the rule below. On `main` these sit near
`DELIVERY_PLAN.md:956-990`; on this branch, ~120 lines lower. Which is the
argument.)

**The line worth deciding from:** a direct push to `main` produces **no
"Adversarial audit recorded" check run at all** — the commit is *invisible* to
the audit gate, not merely unchecked by it. There is nothing red to notice and
nothing to require. Measured, not cited:

    grep -n -A8 '^on:' .github/workflows/audit-gate.yml
    on:
      pull_request:
        branches: [main]
        types: [opened, synchronize, reopened, edited]

No `push:` trigger. Fine for a handoff file. Not fine for anything else — **and
the keystrokes are identical**, which is the whole risk.

*(The citation round that produced this section had **four** errors in it, and
the count is the point. `DELIVERY_PLAN.md:980` for `enforce_admins` was
**correct on `main`** and my correction of it was wrong — I read the feature
branch, where the same string sits at `:1078` because this branch inserts 111
lines above it. So `:1054` and `:1078-1085` are right here and land on
`#96`/`#84` on `main`. `:645` was wrong; its real line is `:984` on `main`.
And a line-wise grep for "the largest remaining gap" returns nothing, because
the phrase wraps a line break — an absence that reads as fabrication:

    grep -n "the largest remaining gap" DELIVERY_PLAN.md     # no match
    rg -U --multiline -n "largest\s+remaining gap" DELIVERY_PLAN.md   # 1083-1084

Neither of us was careless. **A line number is a property of a tree, not of a
document**, and we were reading two trees. That is why the rule below is
mechanical.)*

### Citing and checking: the mechanical rule

Prose did not hold this — both of us broke it the day after writing it down. So:

1. **When you cite, quote the string and name the file. Never the line.** A
   quoted string survives a rebase, a branch and an insertion above it; a line
   number survives none of them and fails by pointing at real prose about
   something else, which reads as verified.
2. **When you check a citation, search with a multiline-capable tool** — `rg -U
   --multiline`, never bare `grep -n`. Markdown wraps at 80 columns, so any
   quoted phrase longer than a few words is more likely than not to straddle a
   line break.
3. **If the search returns nothing, confirm the tool could have found it before
   reporting an absence.** Re-search a short fragment that cannot wrap. A
   no-match is a claim about the world and needs the same calibration as a
   finding — this is the "calibrate before reading a negative" rule, and its
   first casualty was its own author.
4. **Prefer a measurement to a citation wherever one exists.** Reading
   `audit-gate.yml`'s `on:` block settles the trigger question outright; citing
   a document *about* the trigger block inherits every drift problem above. **A
   measurement has no line number to drift.**


### The cwd question, settled: the three adversarial passes are clean

The 2026-09-05 session ran from the parent directory and therefore had no
`adversarial-reviewer`, no `CLAUDE.md` and no slash commands. The obvious
follow-up — whether the three passes that found the ZT regression were also run
without their definition, which would make five findings the output of a generic
fallback — was checked, not assumed. They were not. Evidence:

- `~/.claude/projects/` holds two dirs for this repo. `C--repos-SHIELD080326`
  (parent cwd) contains **exactly one** session — 2026-09-05, this one. Every
  other session, including the 2026-09-04 one, lives under
  `C--repos-SHIELD080326-SHIELD080306main`. The mistake is confined to one day.
- Every `cwd` recorded in the 2026-09-04 transcript is
  `C:\repos\SHIELD080326\SHIELD080306main` or a subdirectory of it.
- That session dispatched `subagent_type: adversarial-reviewer` exactly **three**
  times, matching the three passes; all three `.meta.json` files record
  `"agentType":"adversarial-reviewer"`, `"model":"opus"`, `spawnDepth 1`.
- Each pass was instructed to re-read its own definition from disk, and the
  subagent transcripts show it happening: **3 reads** of
  `.claude\agents\adversarial-reviewer.md` and 5 of `CLAUDE.md`, at the correct
  absolute paths.

So the PR body may cite those five findings as a real audit. This is the second
instance of "an agent that isn't there doesn't say so, it just answers" — the
first was `attack-dev` dispatched from a branch that lacked its definition. The
cheap standing guard is the one used above: have the agent read its own
definition from disk and report any disagreement, so absence leaves a trace.

### Do not create `wip/zt-2026-09-04`

That name predates the date roll and nothing exists at it. `origin/wip/
zt-2026-09-05` at `67142b3` already carries `e0efdba`, `d176115` and `67142b3`;
`fix/zt-targets-and-spend-floor` is untouched at `3f9164f`. The remote is at
**49 branches** with the 40-branch cleanup unstarted — a second ref at the same
commits is one more thing to reason about, not insurance.

### Verified state at end of this session

    git log --oneline -1                              d176115
    git status --porcelain                            (clean)
    git rev-list --left-right --count origin/main...HEAD   0  4
    git rev-parse --short origin/fix/zt-targets-and-spend-floor   3f9164f
    git branch --show-current                         fix/zt-targets-and-spend-floor
    docker compose ps                                 api/db/keycloak/minio/redis healthy, web up

Four commits above `origin/main`, clean tree, **still not pushed**; the remote
branch is still pre-rebase at `3f9164f`, so the push still needs
`--force-with-lease`.

### Start Playwright and the adversarial reviewer

**Run Claude Code from inside `SHIELD080306main/`, not from its parent.** This
session ran from `C:\repos\SHIELD080326`, and as a result **the
`adversarial-reviewer` subagent was not available at all** — project agents live
in `SHIELD080306main/.claude/agents/`, and Claude Code only loads them when that
directory is the working directory. The same applies to `CLAUDE.md` and every
`.claude/commands/` slash command. If the agent list does not contain
`adversarial-reviewer`, you are in the wrong directory; nothing else will fix it.
This affected the 2026-09-05 session only — the three adversarial passes ran
from the correct cwd, verified above.

**The adversarial reviewer** (`.claude/agents/adversarial-reviewer.md`, opus,
Read/Grep/Glob only) is a subagent, not a process — there is nothing to "start"
in advance. Invoke it with the Agent tool, `subagent_type:
adversarial-reviewer`, once per thing under audit. Run it on the PR before
opening it and again after any substantive change; never substitute a
self-audit. When the work under review is itself a set of verdicts (as it is
here — three passes and a test-suite claim), point it at the **verdicts and the
method**, not the code. Note `/audit` is a different thing: a security/dependency
sweep, not this.

**Playwright** exists here in two unrelated forms; be explicit about which one
you mean.

1. *The Playwright MCP browser tools* (`mcp__playwright__*`) are registered and
   available as deferred tools — load them with ToolSearch before calling. They
   drive an ad-hoc browser; they are not the test suite.
2. *The e2e suite* (`e2e/`, `@playwright/test`, chromium only, `workers: 1`,
   serialized against one seeded DB) runs **on the host, not in a container**,
   against the composed stack. `e2e/README.md` is canonical. First run on a
   fresh box needs `cd e2e && npm ci && npx playwright install --with-deps
   chromium`. With the stack already healthy (it is), just:

       export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"
       cd e2e && npx playwright test

   Docker's CLI is not on Git Bash's PATH by default; that export is required in
   every shell (#191 is that this failure is unhelpful). A full run is ~43 min.
   If the DB has been mutated, do the full `down -v` bring-up in `e2e/README.md`
   instead — it destroys local demo data on purpose.

   The last e2e verdict still stands and does not need re-running for this
   branch: `exit 1`, 77 passed / 3 failed / 12 skipped, all three failures
   attributed (load flake, #196, #187).

### Do these in order, next session

1. `cd` into `SHIELD080306main` and start Claude Code there. Confirm
   `adversarial-reviewer` is in the agent list before relying on it.
2. Delete the stale `/tmp/w.*` (command above), then restart the full unit suite
   detached — step 1 of the 2026-09-04 section, unchanged. ~1 hour.
3. While it runs: judge it ONLY by whether the dot count is growing. The
   container has no `ps` or `pgrep`, so any process count reads 0 and means
   nothing. `docker compose restart api` is the reliable way to stop a run.
4. **Push before anything else long-running.** `d176115` still exists in exactly
   one place and carries three adversarial passes, the regression fix, the third
   writer and the fixture corrections. A safe non-moving backup that overwrites
   nothing and does not touch the gated branch tip:

       git push origin HEAD:wip/zt-2026-09-04

5. When the suite lands: confirm the log's **summary line** exists and the exit
   file's mtime is **after** the log's last write, then read the code. Only then
   is the gate cleared.
6. Then `git push --force-with-lease` and open the PR with the Adversarial audit
   block and `Auto-close-approved: 125, 126` — 2026-09-04 section, step 2.

### Still open, unchanged

#124 (the immediate next branch) is unstarted. #188–#196 are filed and none
blocks this branch; #189 and #192 are worth doing soon, #196 is the one that
costs somebody an afternoon of misattribution if left.

Two known limits recorded here rather than in `CLAUDE.md`: the sign-in canary
does not detect every kind of box degradation (it read 0.56s while the suite ran
40% slow), and `CLAUDE.md`'s unit-suite timing is stale by more than an order of
magnitude.

---

## Superseded — 2026-09-04 (end of session)

**Maintained by the agent since D-063; Gene owns it by review.** Every number
below carries the command that produced it, or says it was not derived.

### The one-line state

Track C's first slice is **committed at `e0efdba`, three commits above
`origin/main`, and NOT PUSHED** — the remote branch is still at the pre-rebase
`3f9164f`, so the next push needs `--force-with-lease`. It closes **#125 and
#126** and deliberately **not #124**; that deviation is recorded in
`DELIVERY_PLAN.md` beside the instruction it departs from, in #143's form.

**No PR is open.** One gate is unfinished: see "The one thing not verified".

### Verify the state before trusting this file

    git log --oneline -3
    git status --porcelain
    git rev-list --left-right --count origin/main...HEAD
    git rev-parse --short origin/fix/zt-targets-and-spend-floor
    gh issue list --label mvp-blocking --state open --json number --jq length

`jq` is NOT on this box's PATH — use gh's built-in `--jq`, never a pipe.

### Do these in order

**1. Re-run the full unit suite and capture its exit code.** The only
outstanding gate. Run it detached: a detached `exec -d` survives, a host-side
child does not.

    docker compose exec -d api sh -lc 'cd /app && date +%s > /tmp/w.start && python -m pytest -m unit tests/unit > /tmp/w.log 2>&1; echo $? > /tmp/w.exit'

Judge progress by whether the LOG IS GROWING. The container has no `ps`, no
`pgrep`, and `pkill` does not match these patterns, so a process count always
reads 0 and means nothing — that mistake cost this session two concurrent
suites competing for twenty minutes. `docker compose restart api` is the
reliable way to stop a run.

    docker compose exec -T api sh -lc 'tr -cd "." < /tmp/w.log | wc -c'

Expect roughly an hour. Do not judge the rate from a short sample: stretches of
this suite are DB-heavy and a 60-second window inside one implies a nine-hour
ETA that is not real. Compare a single file against a known baseline instead —
`tests/unit/test_intake_routes.py` was 42.7s this morning and 60.5s this
evening, so the box is about 40% slower, not broken.

**2. Push and open the PR.**

    git push --force-with-lease

The PR body MUST carry both of these or the required checks fail:

    ## Adversarial audit
    Findings: ...
    Disposition: ...
    Scope: ...

    Auto-close-approved: 125, 126

Then confirm the closes actually took, before merging:

    gh pr view <n> --json closingIssuesReferences

**3. It comes back to Gene at merge.** It trips merge-rule condition 5 on the
scoring engine, `models/**`, `apps/api/tests/**`, `e2e/**` and the web test
globs, and condition 6 on two client-visible strings. Not an unattended merge.

### The one thing not verified

**The full unit suite has never completed green on the final tree.** What is
known:

- The last COMPLETE run finished `exit 1` — 7078 passed, 2 failed, both in
  `test_deliverable_reconciliation.py`, both caused by that file's fixture
  defaulting `annual_cost_usd` to None.
- That fixture was fixed and the file verified alone: 4 passed, exit 0.
- Everything changed since is a test rewrite, comments, docstrings and docs.
  `test_self_assessment.py` passes alone (5 passed, exit 0).

The evidence is strong and composite, and it is NOT a single green full run. Do
not describe it as one until step 1 produces `exit 0`.

### What e2e actually said

`exit 1` — 77 passed, 3 failed, 12 skipped, 42.9 min. Every failure attributed:

| spec | verdict |
| --- | --- |
| `s37-security-signoff:42` | load flake; passes in isolation (46.8s) |
| `s34-llm-key:95` | PRE-EXISTING, environmental — fails identically on `origin/main` (22.0s vs 22.2s), same box. This box has `ANTHROPIC_API_KEY` set; the spec asserts none is loaded. Filed as #196 |
| `s42-layout-overflow:91` | known pre-existing, #187 |

The container-identity gate printed both its lines, and its load-bearing claim
is now MEASURED: deleting the stamp mid-run gave `3 passed` and `EXIT=1`, so a
`globalTeardown` throw really does fail the run rather than only printing.

### Gates green as of `e0efdba`

prettier, ruff, black, tsc, eslint (0 errors), vitest 289 passed, and all five
static gates run AFTER the formatter.

### What this branch turned out to be

It began as #125 + #126 and grew, because three adversarial passes found real
defects — **the second pass found that two of the first pass's fixes had
themselves introduced defects, and the third found another round.** The
sequence is the point: the first audited the code, the second audited the
repairs, the third audited those.

The regression worth remembering: making `analyze_gaps` REFUSE an out-of-range
target instead of clamping was correct, and it blanked both cards on the ZT
workspace for a DoD engagement at Stage 4 — #125's own population — because
`normalizeTarget` was framework-blind and `refreshScoreAndGap` swallows the
rejection under one `Promise.all`. 7072 passing backend tests could not see it.

Two fixtures were found describing worlds that cannot exist, each hiding a real
state: a one-row CSV against five extracted items, and an item default of no
cost. Both corrected rather than their assertions weakened.

The third pass caught that the commit said "closes #125 and #126" while GitHub
needs a keyword per reference — `#126` would have stayed open on the
mvp-blocking list asserting a defect that no longer exists. Verified by running
`find_closing_references`, not by reading the regex.

### Issues filed this session

#188 per-capability target exemption (latent) · #189 PATCH accepts `true` as
Stage 1 (Pydantic lax bool-to-int, measured) · #190 stage-0 comment describing
behaviour no route implements · #191 docker-not-on-PATH kills e2e unhelpfully ·
#192 no gate catches double-encoded UTF-8 · #193 the "Tracked" that tracked
nothing · #194 `MIN_TARGET_STAGE` duplicated in three components · #195
`patch_self_assessment_answer` accepts and drops `target_stage` · #196 s34
cannot pass on a box with a provider key.

None blocks this branch. #189 and #192 are worth doing soon; #196 is the one
that costs somebody an afternoon of misattribution if left.

### Two durable facts for CLAUDE.md, deliberately not added yet

Deferred to a fresh session because that file is over its size budget and the
trim is meant to happen incrementally:

- **The sign-in canary does not detect every kind of box degradation.** It
  measures the HTTP path. This evening it read 0.56s (healthy) while the unit
  suite ran about 40% slow. The per-file baseline comparison is the honest check.
- **CLAUDE.md's "~3 min alone" for the unit suite is stale.** It is 7078 tests;
  CI's Python job takes about 14 minutes and this box takes 40-60.

### Not done, unchanged

Branch deletion is still unstarted. All archive tags are pushed to `origin`, so
nothing is at risk. Key it per-branch on content equivalence — squash-merging
means the naive equivalence check is not enough.


## Previous pick-up — 2026-09-03 and earlier (superseded, kept for history)

**Maintained by the agent since D-063; Gene owns it by review.** Every number
below carries the command that produced it.

### The one-line state

`main` is at `295a1d9`. **Item 7 part 2 is started and RED on purpose** — one
failing test, no endpoint. Two PRs are in flight and the MVP path was corrected
underneath them: it now has six remaining items, not four.

### Start here, in this order

1. **`git checkout feat/attack-ai-inputs-provenance`** and run
   `docker compose exec -T api sh -lc "cd /app && python -m pytest tests/unit/test_attack_ai_inputs.py -q"`.
   It fails with **404**. That is correct and is where work resumes.
2. Read `DELIVERY_PLAN.md` → "Scope correction, 2026-08-27", then the
   **file-contention dependencies** under "Dependencies". The first stops you
   building the wrong surface; the second stops two tracks colliding in
   `routes/clients.py`.
3. Read `CLAUDE.md`'s task map and **only the rows that apply**.

### Before writing the ai-inputs query, read this

**The single most likely way item 7 part 2 gets built wrong** is deriving
`not_sent` from live `CapabilityItem` rows for every list. The existing test's
fixture is `status=APPROVED` with `approved_membership` NULL, so it takes the
LIVE branch at `attack.py:624` — a live-only implementation **passes it green**
and is wrong in both directions on a real approved list, where the snapshot IS
the membership. A row re-classified into scope after approval is genuinely not
sent but reports as sent; that is the fabricated-gap failure the endpoint exists
to prevent, carrying its own disclosure as proof.

Write the **path-3 test first**, seeded through `build_approved_membership`
(`tech_debt.py:803-827`), before the query exists to be tested.

Call, do not restate: `approved_membership_stale` (`tech_debt.py:157-213`)
already computes path 3's diff · `awaiting_security_signoff`
(`security_scope.py:54-61`) IS the `awaiting_signoff` field · copy the endpoint
shape from `heatmap` (`attack.py:1500`) · `_client_capability_inputs` takes
**client_id, not service_id** · do NOT add `enforce_ai_rate_limit`.

**One trap:** `Reconciliation.attribution_complete` is not persisted, so
`excluded_rows` is written empty when the count is untrustworthy. Path 4 must
distinguish "nothing was excluded" from "we cannot know what was excluded".

### The plan changed on 2026-08-30

- **`mvp-blocking` now has a written definition** — "the MVP cannot ship while
  this is open" — because it had drifted to "this is important".
- **Items 11 and 12 exist.** 11 = #152 + #153, the redaction egress leaks item
  10 filed and orphaned when it closed. 12 = #168, the pre-commit hook set.
  Both sized **on start**, and both deliberately OUTSIDE the 13–19.5 total.
- **Item 8 is split.** #123 joins the `clients.py` chain; the export/publish
  half stays with item 6 in the held risk track.
- **Two tracks, a held third.** Track A (attack) = item 7 → #131 → #109.
  Track C (`clients.py` + `zt/scoring.py`) = #124/#125/#126 → #114 → #123.
  Held: item 6 → item 8's export half. Merge track PRs ONE AT A TIME and re-run
  CI on the other track after each — `clients.py:22-26` imports five things from
  `app.attack`.

### In flight

- **PR #169** — the prettier pin. Closes 165. Gene merges (condition 5).
- **#168** (pre-commit runs prettier 3.1.0 / ruff 0.6.9 / black 24.8.0 against
  pins nothing uses) and **#170** (merge-rule condition 2 assumes the reviewer
  saw the branch; a stale Read can serve it otherwise) — both filed, neither
  fixed.

### What Gene owes a decision on

Nothing outstanding. **Two branches and three stashes** were approved for
archiving on 2026-08-30 — named explicitly, because "the parked branches" was
ambiguous and the ambiguity was dangerous:

- `feat/w2-attack-citation-resolver` and `scratch/w2-and-docs-parked` — local
  only, on no remote. Every artifact they carry already exists on `main`
  (`citations.py`, `check_audit_evidence.py`, `AttackCitationAccounting.tsx`).
  Tag `archive/<name>`, then drop them.
- **The three stashes: INSPECT EACH BEFORE DROPPING. Not approved for blind
  deletion.** An earlier draft of this section licensed dropping them on a
  justification that covered only the branches — and the branches are tagged
  first, so that half is recoverable while the stashes are not. What they hold,
  read 2026-08-30 with `git stash show --stat`:
  - `stash@{0}` — 112 insertions / 4 files, the same `attack.py` + `tech_debt.py`
    + `AttackWorkspace.tsx` content as `scratch/w2-and-docs-parked`.
  - `stash@{1}` — **592 insertions / 11 files**, CSF provenance and AI shape
    guards, incl. `DECISIONS.md`, `ai/jobs.py`, `csf_profile.py`, four test
    files. The largest of the three by an order of magnitude. It is *believed*
    superseded by PR #78; that belief has NOT been checked against its contents.
  - `stash@{2}` — a 237-line `context/gene.md` rewrite, superseded by D-063.
  `git stash drop` is unrecoverable, and afterwards "it was worthless" and "it
  held the only copy" are byte-identical states. This repo already has one
  recorded instance of a whole governance change sitting stashed through an
  entire review. Diff `stash@{1}` against `main` before deciding.
- **NOT `feat/attack-ai-inputs-visibility`.** It is pushed to `origin`, and it is
  **item 7's shape reference** — the 825-insertion `/ai-inputs` surface
  `DELIVERY_PLAN.md` sends you to. Its endpoint does NOT exist on `main`, so the
  "everything is already on main" justification is false for it specifically.
  Leave it alone until item 7 lands.

### Open work, derived not recalled

**Do not write these numbers down. Run them:**

    gh issue list --label mvp-blocking --state open --json number | jq length
    gh pr list --state open

Every open blocker is owned by an item — `CONTEXT.md` has the by-item mapping,
which is durable in a way the count is not. #165 closes with PR #169; #159 lost
the label on 2026-08-30.

A `<!-- counted: … -->` marker is not enough here. On 2026-08-30 one certified
`17`, a re-label in the same session made it `16`, and the PR that closes #165
was already green. The count changed twice in an afternoon; the command did not.

### The lesson this session produced

**A subject sweep enumerates how the subject can be WRITTEN before it greps.**
Issue 165 was sized "two characters" and landed at 15 files, because
`grep "3\.9\.5"` reached one of four spellings of "the prettier version". Two
of the three misses were found by other people. Now rules 4 and 5 in
`CLAUDE.md`'s numbers block.

## What item 10 did (all eight issues, code complete)

| Issue | Fix |
| --- | --- |
| #135 | Signature blocks: opener counts only when the next line looks like a signatory OR one of the next 5 lines is contact-shaped. Replaced a comma rule that leaked name/title/org/ZIP. |
| #136 | `_RE_CONTRACT` gained `IGNORECASE`. |
| #137 | `_RE_CAGE`: value must contain a digit (that is what separates a code from a word); connector loop handles `code(s)`/`number(s)`/`No.`; glued `CAGE1ABC2` works again. |
| #138 | House numbers alphanumeric + spelled-out, trailing directional, and `City ST NNNNN(-NNNN)?` as ONE grouping. |
| #139 | Facility branch from **USPS Pub 28 C2**, all 24 designators tabled: 7 covered, 8 added, 9 excluded with reasons. `LEVEL` excluded because it is not on the standard. |
| #140 | `_RE_PHONE` rewritten from a digit-density heuristic to explicit groupings + a 7-15 digit bound. |
| #142 | `is_production()` DELETED; `is_development()` + `expose_api_docs()`. All four call sites converted — redaction-off, JWT placeholder, `/docs`, `/openapi.json` were all permitted on `staging`. |
| #144 | Migration **0046**: nullable `llm_calls.redaction_mode`, no server default, written at INSERT, write-once. Pre-migration rows stay NULL and NULL means NOT RECORDED. |

**New gates shipped this week**, all wired into `ci.yml`:
`check_no_control_chars.py`, `check_plan_totals.py`, `check_separator_classes.py`,
and **[CORRECTED 2026-08-27]** `check_recalled_counts.py` — the count that used to
open this sentence said three and went stale within the week, which is the defect
this very list is about. The list is the count.

## What was LEFT on item 10 — all of it done (kept as the record of a near-miss)

**Every step below was completed in PR #155.** It is kept because the previous
version of this file left this section presented as CURRENT, seventeen lines
under a heading announcing item 10 was DONE — and its first instruction was
"Close the nine blockers above", pointing at a list that no longer existed. The
adversarial reviewer caught it on the PR that was correcting the count further
down this same file.

That is the second time in two days the same shape has bitten this file: the
opening section was rewritten, the count was corrected, and the section that
actually TELLS an agent what to do was walked past both times. Correcting the
paragraph someone points at is not the same as correcting the file.

1. ~~Close the nine blockers.~~ Done, plus four more found afterwards —
   thirteen in PR #155.
2. ~~Add the missing REDACT rows using the old rule as an oracle.~~ Done; the
   diff of old-rule vs new-rule match sets found both machine phone formats.
3. ~~Fix the two gate defects.~~ Done — `check_separator_classes` exit 2 no
   longer collapses to 1, and the line-scoped `_HSPACE` exemption now demands a
   written reason.
4. ~~Correct the docs.~~ Done — `docs/security.md`'s cut-length claim and
   Open/Fixed table, and `smoke_live_ai.py`. The cell count was REMOVED rather
   than corrected: it was 327, then 376, then 410, and a count in prose is a
   derived value with a second place to be wrong.

   **NOT `redact.py:82-88`, which this line used to claim.** That note still
   says "every separator in the module is now built from `_HSPACE`" while
   `_RE_CONTACT_HINT` uses bare `\s`, and no gate can see it —
   `check_separator_classes` flags hand-ENUMERATED classes, not `\s`. This file
   said done; CLAUDE.md's narrower-rule bullet says not done; CLAUDE.md is
   right. Filed as **#158** rather than left living only in a lessons file.
5. ~~Re-run the adversarial reviewer.~~ Done, twice more.
6. ~~Confirm a clean full `pytest -m unit`, then open the PR.~~ Done; PR #155
   merged with all seven CI checks green.

## Standing environment facts

- Detached tests survive a killed wrapper:
  `docker compose exec -d api sh -lc '... > /tmp/x.log 2>&1; echo $? > /tmp/x.exit'`
  then poll for the exit file. **Kill stale pytest runs by PID** — `pkill` is not
  in that image and prints nothing while doing nothing.
- After ANY `apps/web` edit: `docker compose up -d --force-recreate api web`,
  then re-check `SHIELD_LLM_MODE`.
- Gates before every commit: host `prettier@3.9.6 --check`, in-container
  `ruff check --no-cache . && black --check .`, `check_test_integrity`,
  `check_no_control_chars`, `check_plan_totals`, `check_separator_classes`,
  `leave_row_oracle.py --check-registry`, and **[CORRECTED 2026-08-27]**
  `check_recalled_counts.py` (run from the REPO ROOT, not the container — it
  resolves the repo root from its own path and refuses rather than guessing). That last one is a CI check and was
  missing from this list, so a commit passing every gate here could still go
  red -- on a new LEAVE table with no registered guards, which is the silent
  success the oracle exists to catch.
- **Writing Python via heredoc mangles backslashes.** Build escapes with
  `chr(92)` and assert the result is ASCII before writing. This cost ~8 repairs.

## The lesson this week actually produced

Three participants — reviewer, implementing agent, reviewing human — each
asserted numbers or rules from READING rather than running, at roughly even
odds of being wrong, in a week whose subject was that error. Every claim made
after executing something held. Recorded in D-058. **Nothing reportable until
it has been run.**

---

# Previous rounds (history)

## What we did this round

### Item 7 backend — PR #133, merged, 7/7 green

Branch `feat/attack-client-named-tools`, two commits (`09a57e3` then `5a88431`), squashed as `ed96486`.

- **#33 finding 5 fixed.** A tool named after the client was uncitable on every run, forever. The resolver is built from UNREDACTED capability names while the payload is redacted in `run_job`, and the prompt says cite the name verbatim — so an obedient model cited a string the resolver had never heard of. Reproduced on `main` first: `[CLIENT] SOC Platform` rejected, the same tool under its stored name resolving fine.
- **Enrichment.** The payload now carries `name` / `vendor` / `category` / `security_functions` instead of a bare string. The extractor already computed "Falcon does detect + respond" and the pipeline threw it away. (The relay's flagged landmine — `_fixture_mitre_map` keeping only `isinstance(v, str)` — fired exactly as predicted and was fixed.)
- **The D-053 split.** `name`/`vendor` from the approved snapshot (they define membership), `category`/`security_functions` read live via the snapshot's `item_id` (they only describe).

### The adversarial reviewer's first run on real feature work

The part worth remembering. **10 findings; 6 fixed, 3 filed, 1 accepted.** Three were defects the agent had just introduced, in a slice already reported to Gene as done and gate-green.

- The redacted-form **alias was indexed into `_by_norm` alongside real names.** A client's list can hold both spellings of one tool (the extractor redacts its own inventory input, so `[CLIENT] SOC Platform` is the normal product of any extraction after intake), so the alias collided with a real name — the only citable string became `ambiguous`, and under #102 that pulls the technique out of the coverage denominator. **Worse than the bug it fixed.** Aliases now sit in their own tier below real names.
- **`_redacted_form` claimed parity with the egress path and implemented 1 rule of 8.** Its docstring argued correctly that a second copy would drift, directly above the second copy.
- **Four tests that could not fail.** The worst named the invariant in its title, described a collision in its docstring, used candidates that do not collide, and asserted a *successful* resolve.

Every fix verified **red-on-revert individually** (7 of them). The most valuable: renaming `item_id` in the writer now breaks the enrichment tests — it did not before, because the fixture hand-wrote the snapshot under a comment promising it matched the writer. Tests now seed through `build_approved_membership`, extracted from `approve_capability_list` for exactly that reason.

**The relay called this one in advance.** Last round's entry named a candidate defect shape: *"a redaction/aliasing scheme correct only as long as two code paths are kept in sync by hand"*, noting it was good self-awareness but "not yet a guarded property." That is precisely finding 2. The prediction was right, and the gap between noticing a fragility and guarding it was one PR wide.

### Three new mvp-blocking issues, split by owning item

Deliberately NOT absorbed into item 7, so no item hides another's cost:

- **#130 — redaction over-matches. The big one.** `redact.py:158`'s suite pattern has no trailing boundary and `[\s.#]*` matches empty, so `Fl`/`Ste`/`Apt`/`Unit`/`Floor` swallow the rest of any word. Verified in-container on `main`: `Flat network segmentation` → `[ADDRESS] network segmentation`; `Flag any unencrypted volumes` → `[ADDRESS] any…`; `Flowmon`, `Fleet`, `Flashpoint`, `Unitrends`, `Steadfast`, `Fluency` all → a bare `[ADDRESS]`. Single egress path, so **all five services and every AI purpose**. Security prose is unusually rich in "fl" (flat, flag, flaw, flow). Suggested fix and the residual `Unit 42` collision are on the issue.
- **#131 — D-053 leak.** An unapproved draft's vendor and spelling override the approved snapshot, and the winning spelling reaches the client deliverable. Pre-existing.
- **#132 — `risk.py` drops technique/control links silently.** No counter, no reason, nothing in the audit row. Belongs to **item 6's** family alongside #121/#122/#84. Found by grepping the *shape*, not the call sites — `risk.py` never calls `_validate_tools`, it reimplements it inline.

Also corrected **#33 finding 12**: non-ASCII tool names are NOT uncitable. Exact citations resolve (`_norm` doesn't strip non-ASCII); only the near-miss rescue fails. Real gap, wrong severity — that changes its priority.

### CLAUDE.md

Three lessons added, each from a confirmed finding: derived lookup keys belong in their own tier below the authoritative one; a parity claim is enforced by CALLING the other function, not restating it; and the sweep rule below.

## The four-theme critique: where each theme stands

Recorded by the relay last round, updated with what actually landed.

| Theme | Response | Status now |
|---|---|---|
| 1. Process crowding out features | Item 7 named as the correction | **Done** — #133 is the first feature PR since #116 |
| 2. Status ahead of truth | Pushed-vs-drafted framing adopted | **In use** every update since |
| 3. Vocabulary sweeps over shape sweeps | Required "searched for: `<shape>`" line in sweep output, folded into item 7's PR | **Landed** in CLAUDE.md and used in #133's body; it found #132 |
| 4. Stale cross-references | Table splitting structural (checkable) from semantic (not) classes, to be filed as a CI trigger | **Still not filed.** Scheduled after item 7; item 7 part 2 is still open, so this has not slipped yet — but it is the one to watch |

### Open question the relay raised, now answerable

*"The 'searched for: `<shape>`' line is self-attested free text, not something the reviewer or CI checks. Same shape as the authority-admission gap. Is the reviewer going to be told to check it, or is it transparency-only?"*

**Answer as of this round: transparency-only, enforcement not built.** Nothing reads the line. But it is not worthless — this round the line forced the sweep to be phrased as *"a model's string compared against a stored value, misses discarded"* rather than *"callers of `_validate_tools`"*, and that rephrasing is what surfaced #132 in a file that shares no vocabulary with ATT&CK. So: the mechanism worked as a thinking aid on its first use, and remains unenforced. Worth deciding whether the reviewer gets told to check it, rather than letting it drift into the same "prose nobody reads" category.

## Branch / in flight

`main` has #110, #113, #116, #117, #119, #127, #128, #129, #133 merged. **Working tree clean, nothing local, nothing mid-edit.**

## Open mvp-blocking issues AS OF 2026-08-26 — historical, do not act on

<!-- counted: historical -->

**14, read live from GitHub on 2026-08-26, immediately after PR #155 merged.**
**It is 2026-08-26's number and nothing else.** For the current figure run the
command in "Open work" at the top of this file; for the by-item mapping see
`CONTEXT.md`.

**This heading has now held three different values** — 20, then 14, and it was
still saying 14 on 2026-08-30 when the mapping gave 15 and the list below
omitted #168. `CLAUDE.md` cites it as instance 1 of the
correction-paragraph-outlives-its-number shape, and it went stale a third time
while that citation stood. Date-qualified rather than updated: a heading in a
history section that reads as current is the defect, and a fresh number would
only reset the clock on it.

`#153 #152` (the two redaction leaks item 10 filed rather than fixed) · `#132
#131` · `#126 #125 #124 #123` (dashboards) · `#122 #121` (Risk, **item 6**) ·
`#115 #114 #109` (**item 9**) · `#46`

Closed since: `#130` by PR #141; `#135`-`#140`, `#142`, `#144` by PR #155.

**This heading read 20 with a paragraph underneath certifying it as freshly
read.** Both were true on 2026-08-25 and false the moment PR #155 merged --
it closed EIGHT (#135-#140, #142, #144; the ninth, #130, was PR #141's and is
listed separately above).

The arithmetic, written out because 20 - 8 = 12 and the answer is 14: item 10
also **filed** two, #152 and #153, before it merged. 20 - 8 + 2 = 14. A
correction paragraph that shows only the subtraction invites the check and
then fails it.

The certifying paragraph went stale WITH the number it certified,
while still reading as a guarantee. That is worse than a bare stale count: a
reader checking whether the figure could be trusted found a sentence saying yes.

Fifth instance this week, and three of the five were in the files that document
the rule against it. See CLAUDE.md, "a correction paragraph outlives the number
it corrected".

Not `mvp-blocking` and deliberately so -- recorded because "unlabelled" and
"deliberately out of scope" look identical in a list: **#151** (Tailwind
classes naming undefined design tokens render as nothing, 18 occurrences),
**#154** (the computed glue-alphabet sweep, filed with its reasoning and
measured as searching an empty space), **#156** (ruff isort classifying
`apps/api/scripts` by whether an unrelated top-level `scripts/` exists), and
**#143** (the pre-push hook's fail-open). Matches CONTEXT.md's list, which
it did not until PR #157 -- this file named only #143, so three issues that
CONTEXT.md called deliberate were indistinguishable from oversights here,
which is the exact failure the sentence claims to prevent.

## Open decisions: NOT to be reconstructed from memory

**Historical — #130 was pulled ahead, fixed in PR #141, and closed.** It was listed here as a live "new this round" decision, with an action recommendation, twenty-six lines below the line recording it closed. The heading says these are NOT to be reconstructed from memory, which reads as an instruction to treat the contents as current. Found by the third adversarial pass. Still genuinely open: whether #131's fix needs provenance carried through `pairs` (approved vs live) rather than reconstructed from the tuple. Whether the "searched for: `<shape>`" line gets enforced or stays transparency-only (see above).

**Closed since the last round** (2026-08-25, recorded here at Gene's explicit
instruction — this file is owner-write-only and an agent writing it stays the
exception, not a new default):

- **First real unattended cron run — CONFIRMED.** `Scheduled triggers` fired on
  its own cron at `2026-08-24T07:54:48Z`, `event=schedule`, green on `main`. The
  two Aug 22 runs were `workflow_dispatch`, i.e. manual, which is why this was
  still open. Cited on #145, which depends on the mechanism.
- **Stale-cross-reference tracking issue — FILED as #145.** Structural half now
  gated by `check_plan_totals.py`; prose half measured at 1 true finding in 13
  (7.7% signal) and deliberately not gated, under the same reasoning that
  narrowed TI001. Three sub-questions left explicitly open on the issue rather
  than implied closed.

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. Whether #84 gets the `mvp-blocking` label. #106/#107 root fixes still parked behind "worked around, issue stays open".

## Adversarial-reviewer

**Third use, and the first on real feature work rather than on its own rules.** It overturned the branch's central claim. The headline: a slice that passed ruff, black, prettier, `check_test_integrity` and a full green suite was carrying a regression worse than the bug it fixed, plus four tests that could not fail. No mechanical gate saw any of it.

Re-verify every finding before acting — it runs read-only and executes nothing, so every claim is static reading. This round two claims needed in-container verification before being acted on; both held, and one (#130) turned out worse than reported.

## Recurring defect shapes to watch for (CLAUDE.md)

**#72 (tests that cannot fail): four more instances this round, all produced by the agent in the same change where it was fixing that pattern's cousins.** Instances 10–13. CLAUDE.md's line — *knowing the shape does not prevent producing it, only checking does* — is now the most heavily evidenced sentence in the file, and it is the argument for the reviewer being a standing rule rather than a habit.

**The relay's candidate shape from last round is now confirmed and recorded in CLAUDE.md**: a scheme correct only while two code paths are kept in sync by hand. The guarded form is "call the other function, do not restate it."

## Environment notes (standing)

Background/foreground test runs kept getting killed by the harness wrapper this round. Reliable pattern: `docker compose exec -d api sh -lc '… > /tmp/x.log 2>&1; echo $? > /tmp/x.exit'` then poll for the exit file. The detached pytest survives even when the wrapper is killed.

## MVP-complete vs. client-ready: standing distinction

Unchanged.
