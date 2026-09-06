# Reconciliation drafts — 2026-09-05

**This file is a DRAFT staging document, not a handoff.** `context/gene.md`
answers "where am I" and every fresh session reads it first; this answers "what
am I about to write" and is consumed by the reconciliation PR. Keeping them
separate is deliberate — merging them bloats the handoff and hands the next
reader a sorting job.

## THIS FILE IS NOT DELETED BY THE RECONCILIATION PR

**That is the instruction. The marking below is only the backup.**

The reconciliation PR consumes the plan arithmetic and nothing else. `CLAUDE.md`
edits are deferred to a fresh session by design, so **the durable half has
nowhere to land yet** — deleting this file in the reconciliation PR removes
content that has not arrived anywhere else.

**It dies in the CLAUDE.md PR: the one that actually consumes it.** Then the
delete and the lift are one change and cannot come apart.

Why ordering rather than machinery: the index and inline tags below are prose
inside a file that a PR deletes. A reviewer seeing a consumed draft removed sees
something that looks entirely correct — which is exactly the moment the marking
is least likely to be read. **The reflex survives the rule until the rule has a
gate, and there is no gate here.** So the fix is that the deletion happens in
the PR where forgetting is impossible, not a louder warning in the PR where it
is easy.

## Read this before deleting the file

Two kinds of content are here and **they have different fates.** The PR that
closes the reconciliation will correctly delete a consumed draft. If the durable
half has not been lifted out first, that deletion silently takes a week of
governance findings with it — and it will look entirely correct while doing so.

### CONSUMED — dies with the reconciliation PR, as it should

| section | why it dies |
| --- | --- |
| The fourteen dispositions for #183–#196 | they land in `DELIVERY_PLAN.md` and on the issues |
| The two re-size corrections, recorded as two | they land in the item table |
| The re-derived total, and the governance-overhead placement | same |
| Item 7 / item 9 status fixes, and the re-measure step | done once, then gone |
| Post-merge content for `context/gene.md` | it moves into `gene.md` |
| The #197-specific verdict reading and E2E retry read | they described one run, which has now happened |

### DURABLE — `CLAUDE.md` material, outlives all of this

**Lift these out BEFORE the reconciliation PR deletes this file.**

| section | what it is |
| --- | --- |
| `## HOLD for CLAUDE.md`, **Block 1** | instruments that report only on success — the four-instance rule and its table |
| `## HOLD for CLAUDE.md`, **Block 2** | the standard for any new gate: exercise the judgment, then the delivery |
| `## Why this reconciliation exists` | an internal-consistency check is not a correctness check — three verified instances |
| **#183's partition-by-meaning rule** — inside the OUTSIDE dispositions, not its own section | before a literal sweep, partition hits by MEANING not by file, and write down which partition must not move |
| **The pre-named rationalisations** — inside "RED in `test_deliverable_reconciliation.py`" | naming the specific excuses in advance, because a rule that does not name them loses to them |
| **`## Step 0 — is it a verdict at all?`** | both-or-neither validity, already generalised into Block 1's first row |
| **The instrument lesson worth generalising** — inside the post-merge block | the uploader's log line works when nothing uploads |

**Anything not listed as DURABLE is CONSUMED.**

---

# Reconciliation draft — dispositions for #183–#196

**STATUS: dispositions drafted; every number in this file is BLOCKED. Read the
blocked stamps before quoting anything numeric from here.**

## Two decisions that currently exist only in conversation

1. **Cut off `origin/main` AFTER VERIFYING it carries #197.** Not off a named
   merge commit: the squash merge creates a commit that is not an ancestor of
   this branch, so there is no SHA to write down in advance, and one written now
   expires the moment anything else lands. **The middle line is the
   instruction:**

       git fetch origin
       git log origin/main --oneline -1      # MUST show (#197)
       git checkout -b docs/plan-reconciliation origin/main

   If Gene has not merged, `origin/main` is still `ad22ead`, the branch is cut
   off the pre-#197 tree, and the totals get re-derived from the table #197
   replaces — **silently, because nothing about that branch would look wrong.**
   Track C rewrites `DELIVERY_PLAN.md` by 111 insertions / 13 deletions.

   *(An earlier draft of this line said "cut off Track C's merge commit". That
   was wrong for the reason above, and is itself the line-number rule one object
   over: a SHA is a property of a history that has not happened yet.)*
2. **The baseline trap.** Sizing against *current* `main` undercounts the
   branch's governance cost by exactly the three `context/gene.md` pushes made
   to `main` on 2026-09-05: `17481f3..HEAD` is 34 files / 2618 / 265, while
   `ad22ead..HEAD` is 34 / 2252 / 93. The 366/172 difference is work pushed out
   of the branch into its own baseline. Size against `17481f3` or the merge
   base.

   Slices against `17481f3`, summing exactly: code 13 / 624 / 54 · tests
   11 / 1242 / 11 · docs+governance 5 / 631 / 200 · e2e harness + `.gitignore`
   5 / 121 / 0. (624 + 1242 + 631 + 121 = 2618; 54 + 11 + 200 + 0 = 265.)

## Why this reconciliation exists — an instance, not housekeeping

**[DURABLE — lift into CLAUDE.md before this file is deleted]**

**An internal-consistency check is not a correctness check, and consistency is
exactly what lets a wrong set of numbers survive.** Three instances, measured:

1. **`attack/catalog.py`'s docstring** (#183). It says 196 parents + 411 subs =
   607 total. The arithmetic is *right*; all three numbers are wrong. The module
   exports 193 / 440 / 633. Being internally consistent is why it reads as
   trustworthy and why it survived long enough to propagate into #115's body.
2. **`check_plan_totals.py`.** Its own docstring: *"Fail when
   `DELIVERY_PLAN.md`'s stated total does not equal the sum of its parts."* It
   sums every non-total row and compares. Run on 2026-09-05 it reported
   `plan totals: 13-19.5 across 4 items, heading and table agree` — **green,
   over item 7's 4–6 for work PR #180 shipped on 2026-09-02.** Sum-correct,
   fact-wrong, passing. The gate cannot see that a part describes finished work,
   because nothing outside the table is consulted.
3. **The removed "totals agrees with per-list state" test.** Both sides were
   built in the same loop from the same `cap_list`, so it could not fail.

The common shape: each verifies numbers against *each other* rather than against
the world. **Every one needs an external anchor.** Measure the catalog instead of
reading the docstring; derive the total from measured Actuals instead of carrying
estimates forward; assert against a fixture the code did not build.

**This reconciliation is the fix for instance 2.** Item 7's row and the 13–19.5
total are wrong today with a green gate over them, and re-deriving from measured
Actuals is what supplies the missing anchor. Read it as an instance of the shape,
not as tidying.

## Post-merge content — belongs on THIS branch, not on #197

**Do not edit any file on #197.** It is green on all seven required checks and
waiting on a human. A file edit invalidates them and buys a fresh ~15.7-minute
E2E plus the ~15-minute Python job to add a paragraph to a handoff doc. `#197`'s
`context/gene.md` is already accurate for the state it describes; everything
below is post-merge content. **Until the merge, the PR itself is the record** —
a fresh session finds #197 open, green, with the handoff comment and check
results attached, which is more authoritative than a doc summarising it. If the
window stretches, **add a comment** (comments trigger nothing; `audit-gate.yml`
fires on `edited`).

Carry into `context/gene.md` on the reconciliation branch, alongside everything
else in this file:

- Seven of seven required checks green on #197; `mergeable: MERGEABLE`;
  `closingIssuesReferences` returns `125` and `126` **by API**, not by the
  guard's "clean (N declared closes)" message.
- Full unit suite `7081 passed, 18 deselected, exit 0` in `0:42:18`, validated
  by mtime-ordering **and** a summary line, on a tree byte-identical to the
  rebased one (`git diff --stat 3c954ca..HEAD` empty).
- E2E: **no retry**, measured two independent ways. Recorded on #187, which it
  does **not** settle.

### The instrument lesson worth generalising

**[DURABLE — lift into CLAUDE.md before this file is deleted]**

`playwright-report/` can **never** separate "passed" from "passed on retry" —
`reporter: [["list"]]` means it is never written at all, so its absence is
constant across both outcomes. `test-results/` **can**, because `-retry1`
directories land there and `trace: "on-first-retry"` writes a trace iff
something retried.

The general property: **the uploader's own log line —
`No files were found with the provided path: …` — is an instrument that still
works when nothing uploads.** The read comes from the uploader having *looked*,
not from an artifact to download. An instrument that reports only on success
goes silent in exactly the case you needed it, and its silence is
indistinguishable from a clean result. Prefer the one that reports either way.

## HOLD for CLAUDE.md — apply on the reconciliation branch, verbatim

**[DURABLE — lift into CLAUDE.md before this file is deleted]**

Both blocks below are **staged, not written**. `CLAUDE.md` is a tracked file on
#197's branch; editing it now invalidates seven green checks to add a paragraph.
Apply them after the merge, on `docs/plan-reconciliation`.

### Block 1 — instruments that report only on success

- **AN INSTRUMENT THAT REPORTS ONLY ON SUCCESS GOES SILENT IN EXACTLY THE CASE
  YOU NEEDED IT, AND ITS SILENCE IS INDISTINGUISHABLE FROM A CLEAN RESULT.**
  Prefer the instrument that reports either way. Four instances in two days, <!-- counted: historical -->
  every one an absence produced by the method and read as a fact about the
  world:

  | the silent instrument | what it looked like | the instrument that reports either way |
  | --- | --- | --- |
  | `/tmp/w.exit` | `0` over a run that died at `[ 98%]` — an exit file can report a code, never "I was killed before writing one" | exit-file mtime **after** the log's last write, **and** a summary line in the log. Both or neither |
  | `grep -n "the largest remaining gap"` | no match, for text that is present — the phrase wraps at 80 columns | `rg -U --multiline` with every space written `\s+`, then re-search a fragment that cannot wrap before reporting an absence |
  | `statusCheckRollup: []` | read as "the gates are broken"; the PR was `CONFLICTING`, so GitHub built no merge commit and `pull_request` workflows had nothing to run on | `mergeStateStatus` + `mergeable` alongside the rollup — they name the cause the empty rollup cannot |
  | the Playwright artifact that was never uploaded | no `playwright-report` artifact, read as "nothing retried" — but `reporter: [["list"]]` means it is never written on **any** outcome | the uploader's own log line, `No files were found with the provided path: …`. It works **when nothing uploads**, because the read is that the uploader *looked* |

  The fourth is the sharpest: `test-results/` **can** separate a pass from a
  pass-on-retry, because `trace: "on-first-retry"` writes there iff something
  retried — but only the uploader's report, not the artifact, survives the case
  where there is nothing to upload.

### Block 2 — the standard for any new gate

**Exercise the judgment, then exercise the delivery. They are two tests and the
first is the one people do and then stop.** A gate that decides correctly but
cannot deliver its decision is indistinguishable from a gate that never fires,
and silence reads as success.

Done twice, both halves each time:

- **The container-identity gate.** Deleting the stamp mid-run proved not only
  that it detects the missing stamp but that the detection reaches `$?` —
  `3 passed` with `EXIT=1`.
- **The unit-suite watch.** The probe proved the *judgment*: `5|137` fires,
  `7025|` — the exact dead-run signature — does not, so it reads a verdict
  rather than reacting to activity. The 30-minute heartbeat then proved the
  *delivery*: the event actually reached the session.

**Exercise the judgment, then exercise the delivery. They are two tests and the
first is the one people do and then stop.** A gate that decides correctly but
cannot deliver its decision is indistinguishable from a gate that never fires,
and silence reads as success.

Done twice now, both halves each time:

- **The container-identity gate.** Deleting the stamp mid-run proved not only
  that it detects the missing stamp but that the detection reaches `$?` —
  `3 passed` with `EXIT=1`, so a `globalTeardown` throw really fails the run
  rather than only printing.
- **The unit-suite watch.** The probe proved the *judgment*: `5|137` fires,
  `7025|` — yesterday's exact dead-run signature — does not, so it reads a
  verdict rather than reacting to activity. The 30-minute heartbeat then proved
  the *delivery*: the event actually reached the session.

## The rule these dispositions apply

**The document bar decides the LABEL. What completes an item's work decides
OWNERSHIP.** They are different questions. The plan already works this way —
item 7 "also owns #131", item 6 "also owns #121, #122, #132" — none assigned by
surface. A defect that makes a document say something untrue is `mvp-blocking`;
reaching a client deliverable or client dashboard puts it inside an item and
inside the total. Harness, CI or developer tooling goes outside, **with the
reason stated in #143's form** — because in a list "unlabelled" and
"deliberately out of scope" look identical.

All fourteen get a disposition. Outside-the-total is a disposition; unmentioned
is not.

---

## INSIDE item 9 — labelled `mvp-blocking` (3)

**[CONSUMED — dies with the reconciliation PR]**

All three reach scoring, and therefore the deliverable.

**#188 — ZT per-capability `target_stage` falls back silently when out of range.**
#125's shape one level down: the per-capability writer repeats the defect the
engagement-level fix just closed. Reaches scoring, so it reaches the deliverable.
Owned by item 9 because it is the same population #125 is about.

**#189 — `PATCH /zt/answers` accepts `true` as Stage 1.** The one writer of the
stage columns that does not refuse a bool; Pydantic's lax bool-to-int coercion,
measured. A stage written as `1` because someone sent `true` scores identically
to a deliberate Stage 1 and is indistinguishable afterwards.

**#195 — `patch_self_assessment_answer` accepts `target_stage` and silently
drops it.** Accepting a field and discarding it is the silent-failure shape: the
caller's request and the stored state disagree, with no error.

## INSIDE item 9 — owned, NOT labelled (2)

Ownership without the label. Both fail the document bar and both are required
for item 9's work to be complete.

**#185 — `ZtWorkspace` swallows score/gap fetch failures into a permanent
loading state.** Admin-surface, so it fails the document bar. But it is **the
completion of #125, not an independent defect**: #125's fix makes the API return
a typed error, and that error is invisible to a consultant until this lands.
Shipping #125 without it ships a fix nobody can see.

**#194 — `MIN_TARGET_STAGE` duplicated as a literal in three ZT components.**
The structural cause behind both #185 and #188. Three literals is three places
to be wrong and **two already were**. Leaving it means the next framework-blind
copy gets written by default.

## OUTSIDE the total — fixed in passing (2)

Both are false comments that no document depends on, so neither is labelled.
Both sit in files #188/#189 will already open, so **batch-by-file applies** —
they are fixed in passing, not scheduled.

**#190 — `schemas/zt.py` documents a stage-0 behaviour no route implements.**

**#193 — `build_context`'s "Tracked, not silently accepted" tracks nothing**, and
names no issue number. A comment asserting a guarantee the code does not provide.

## OUTSIDE the total — with stated reasons (7)

**#183 — `attack/catalog.py`'s docstring states the catalog size three ways and
all three are wrong.** Documentation; nothing computes from it. Measured this
session: the docstring says 196 parents / 411 subs / 607 total, the module
exports **193 / 440 / 633** (14 tactics, the one figure that is right).

- It is **internally consistent** (196 + 411 = 607), which is why it has survived
  and why it reads as trustworthy.
- **It has already propagated once**: #115's own body says "607 techniques → 25
  batches", and that number came from this docstring.
- **The general rule this issue should carry, not just the fact about 607:**
  **before a literal sweep, partition the hits by MEANING rather than by file,
  and write down which partition must not move.** A literal with two meanings is
  the third instance this week:

  | literal | must change | must NOT change |
  | --- | --- | --- |
  | "Total annual cost" | live code in the exporter | historical quotation in `DECISIONS.md` and `CONTEXT.md` |
  | `607` | the wrong catalog size in this docstring | `routes/attack.py`'s N-033 incident count — 607 `gap` + 26 `not_applicable` across all 633 techniques, which is *correct* |

  Partitioning by file would move both halves of each row. The partition is
  semantic, so it has to be written down before the sweep, not discovered during
  it.

**#184 — CSF silently clamps an out-of-range target tier and reports the clamped
value back as the one requested.** Settled: **screen, not document.** Flip
condition already recorded on the issue — it is not currently reachable out of
range because `schemas/intake.py` bounds `csf_target_tier` at `ge=2, le=4` and
CSF's ceiling is 4, so it is **one schema edit, or one new CSF framework with a
shorter ladder, from being live**. ZT is exposed where CSF is not only because
DoD ZTRA's ceiling is 3 while its intake schema permits 4.

**#186 — `OverlapDashboard` calls a partial cost figure a Total, three cards from
the "Missing cost" count that proves it is not.** A **real product defect**, not
a cosmetic one — and it still sits outside, because it is **admin-facing** and so
fails the document bar. *Same disposition as #187, opposite reasoning; both are
written down so nobody reopens the question in a month.* It **consumes #126's
`spend_completeness`** tri-state — confirmed: the issue's own fix section says
"consume `spend_completeness`, do not invent a fourth spelling", and the field
lands in `schemas/clients.py` and `TechDebtDashboard.tsx` on Track C — so it is
**ordered after item 9, not owned by it**.

**#187 — CI cannot distinguish "passed" from "passed on retry".** Tooling, and
outside. **But it has already caused a live incident**: a real s39 failure was
absorbed by a retry and merged a week ago. The note must carry that, or the next
reader files it as theoretical.

**#191 — `containerIdentity` fails the whole e2e suite with a message that names
the check, not the cause.** Harness. **Crash versus verdict**: a run that dies
for an environmental reason must not be readable as a test verdict, which is the
distinction this issue is about.

**#192 — no gate catches double-encoded UTF-8, and one instance remains in
`routes/attack.py`.** Determined this session: **outside whole, no split
needed** — both halves are outside, so the issue does not need splitting.

- The missing gate is tooling.
- The live instance is a corrupted em dash in the docstring of
  `_validate_tools` — a function **nested inside** `run_ai`, **not a `#`
  comment** as the issue body says.
- Measured, not inferred: served `/openapi.json` is 231,019 bytes and contains
  no double-encoding signature, with a positive control confirming the search
  works on that file; nothing in `apps/api/app/` reads `__doc__`.
- **Flip condition (#184's form):** it is outside *because* `_validate_tools` is
  nested rather than being the handler. FastAPI publishes a **route** function's
  docstring as its OpenAPI description, and `run_ai` is a route handler
  (`@router.post`). **Any refactor that hoists `_validate_tools` to module
  level, or moves those bytes into `run_ai`'s own docstring, starts serving
  them.** One indent level from being served. "It's only a docstring" is true
  today, for a stated reason, not in general.

**#196 — s34's key-panel spec cannot pass on a dev box that has a provider key,
and says nothing about why.** Harness. The spec asserts no provider key is
loaded; a box with `ANTHROPIC_API_KEY` set fails it identically on `origin/main`
(22.0s vs 22.2s, same box), so it is environmental, not a regression.

---

## FIRST JOB on the reconciliation branch: re-measure the three stale claims

**[CONSUMED — dies with the reconciliation PR]**

**Do not act on the morning's findings. Re-measure them on the post-#197 tree.**
Item 7's `PART 2 IN PROGRESS, RED ON PURPOSE`, item 9's `fixes not started`, and
item 7's 4–6 inside `13–19.5` were all measured against `ad22ead`, and #197
changes `DELIVERY_PLAN.md` by 111 insertions. **Some may already be fixed by
#197** — which shrinks the work — and others will not be, and those are the
reconciliation's first job. Carrying the morning's findings forward as still-true
is the moving-tree failure aimed at my own output.

    git show origin/main:DELIVERY_PLAN.md > /tmp/dp.md
    rg -U --multiline -n "PART\s+2\s+IN\s+PROGRESS|RED\s+ON\s+PURPOSE" /tmp/dp.md
    rg -U --multiline -n "fixes\s+not\s+started" /tmp/dp.md
    rg -U --multiline -n "13\s*[-–]\s*19\.5" /tmp/dp.md

Quote what is there; do not cite line numbers.

## BLOCKED — every number below waits on a named input

**[CONSUMED — dies with the reconciliation PR]**

Nothing in this section is derived yet. **A draft that reads as finished is how a
provisional number becomes a committed one.**

- **Item 9 Actual — BLOCKED on Track C merge.** Derive from code 624 + tests
  1242 for **two of seven** (#125, #126). A red suite means more work and a
  different Actual, so this cannot be written before the run that measures it
  has finished.
- **Item 9 re-size, correction 1 of 2 — BLOCKED on Track C merge.** The
  mis-sizing of #125 and #126 against what they actually took: #125 needed a
  third unvalidated writer, #126 a second closing keyword. **Two of the original
  seven were mis-sized before any fold.** Record first, alone.
- **Item 9 re-size, correction 2 of 2 — BLOCKED on correction 1.** The fold of
  #188, #189, #195, #185 and #194 on top. Recorded **as a separate correction**
  so nobody later reads one number and thinks it covered both. Precedent: item 6
  re-sized 2026-08-22 on taking #121/#122/#132, and again 2026-08-25.
- **Item 7 status and re-size — BLOCKED on the reconcile itself.** The row still
  reads `PART 2 IN PROGRESS, RED ON PURPOSE`; PR #180 ("feat(attack): ai-inputs
  — what was NOT sent, and where what was sent came from") **merged 2026-09-02**,
  closing #108.
- **New total — BLOCKED on both item 9 corrections and item 7.** Currently
  `13–19.5` across four sized items, unmoved since 2026-08-27.
- **Governance overhead — BLOCKED on a decision about where it goes, not on a
  measurement.** 631 insertions (CLAUDE.md, the reviewer brief, gene.md,
  CONTEXT.md) is **not item 9 work**. Charging it to item 9 distorts the
  estimate; dropping it hides an overhead that recurred on every branch this
  week. It goes somewhere visible, outside item 9's number.
- **Ratio worth carrying:** tests ran at roughly **twice** the code on Track C
  (1242 vs 624). That ratio predicts item 9's remaining five better than any
  code count — but it is one observation, not a rate.
- **The suite's denominator is itself tree-dependent — BLOCKED on the run.** The
  familiar ~7078 comes from the 7072-passed run, which predates `e0efdba`. This
  branch adds one test file (`test_zt_target_stage_provenance.py`), modifies
  eight, and adds **at least 31 net new test functions** (`+31 / -0` on
  `def test_`; parametrised cases mean 31 is a floor, not the figure). So a
  percentage against 7078 measures this run against a different tree — the
  line-number problem one metric over. **Fix when the run lands: take the
  completed run's own dot count as the new denominator and record the commit it
  was measured on (`3c954ca`).**

---

# How to read the unit-suite verdict — WRITTEN BEFORE THE RESULT WAS SEEN

## OUTCOME (appended after the fact — the rule below is unedited)

**GREEN.** `7081 passed, 18 deselected, 14 warnings in 2538.42s (0:42:18)`,
exit 0, measured on `3c954ca`. Step 0 held both ways: exit-file mtime
21:39:04.220 is 13.7s *after* the log's last write at 21:38:50.520, and the
summary line is present. `HEAD` was still `3c954ca` with a clean worktree, so
the tree did not move under the verdict.

The composite is now a single green run — the first on the final tree.

**Correction to this file's own denominator instruction:** "take the completed
run's own dot count" is wrong as written. The whole-log dot count is **7118**;
the count over progress lines only is **7081**, matching the passed figure
exactly. The 37-dot excess is periods inside the summary and warning prose
(`2538.42s`, `docs.pytest.org`). Use the passed count, or count dots only on
lines matching `^[.sxfE]+ +\[`. An internal-consistency habit — counting dots
because dots were what we watched — overcounting by reading prose as data.

**Unreconciled, and stated rather than smoothed:** passed rose 7072 → 7081, only
+9, against a measured `+31 / -0` on `def test_` in `apps/api/tests/**`. The 18
deselected may absorb some. The gap does not affect the verdict, and it is not
explained. Worth a look before the +31 floor is cited again.

---


Committed 2026-09-05 while the run was ~30 min in at 5680 dots, outcome unknown.
The point of writing it now is that the end of a long day supplies rationalisations
that are unavailable at the start. If the reading below feels too strict when the
result actually lands, that feeling is the thing this file exists to overrule.

Run: detached, started 20:56:31 UTC, covers **`3c954ca`** on
`fix/zt-targets-and-spend-floor`.

## The E2E retry read — WRITTEN BEFORE THE RESULT WAS SEEN (PR #197)

**[CONSUMED — dies with the reconciliation PR]**

**Green reads as finished, which is exactly when this gets skipped.** CI runs
`retries: 1`, so a green E2E cannot distinguish "passed" from "passed on the
second attempt" — that is #187, still open. `trace: "on-first-retry"` means a
trace exists **if and only if** something retried, so the artifact is the read:

    gh run download <run-id> -n <e2e-artifact>
    find . -name '*-retry1*' -o -path '*-retry1/*'   # under test-results/

Decided in advance, before seeing it:

- **A `-retry1` directory for `s42`** → CI's retry is absorbing the
  layout-overflow failure that reproduces locally on `main`. That **settles
  #187's open reading** and is a finding to record on the issue, not a
  curiosity. Same read that surfaced the s39 incident on #180's run a week
  after it merged.
- **A `-retry1` for anything else** → same treatment: a masked failure, named
  and recorded.
- **No traces at all** → a clean first-pass green. **Say so plainly**, without
  hedging it into ambiguity.

Do not skip this because the check is green. The check being green is the
condition under which it matters.

## Step 0 — is it a verdict at all? Both, or neither.

**[DURABLE — lift into CLAUDE.md before this file is deleted]**

    docker compose exec -T api sh -lc 'ls -la --time-style=full-iso /tmp/w.exit /tmp/w.log; grep -nE "passed|failed|error" /tmp/w.log | tail -3'

1. **`/tmp/w.exit`'s mtime is AFTER `/tmp/w.log`'s last write.**
2. **A pytest summary line exists in the log.**

**Both or neither.** Either alone can be satisfied by a corpse — yesterday's had
exactly one of the two (an exit file reading `0`, written 29 minutes before the
log stopped at `[ 98%]` with no summary), and that near-miss is the whole reason
this run exists. If only one holds, there is no verdict: the run died, and the
correct action is to restart it, not to interpret it.

Also record the run's own dot count as the new denominator, against `3c954ca` —
the familiar ~7078 is from the 7072-passed run, which predates `e0efdba` and at
least 31 net new test functions.

## Step 1 — read the outcome. Three cases, decided in advance.

### RED in `test_deliverable_reconciliation.py`

**This is a FINDING, not a re-run.** It means the per-file verification was
insufficient and **the two-day composite claim collapses.** The composite was:
that file failed twice in the last complete run, its fixture was fixed, the file
was then verified alone at 4 passed / exit 0, and everything since was test
rewrites, comments and docs. If it is red here, "verified alone" did not
generalise, and the reasoning that has stood in for a green run all week was
wrong.

Write it up as a finding against the composite method. Do not re-run it first;
do not fix it and report the fix without reporting that the method failed.
**This is the outcome most likely to be rationalised at the end of a long day**,
and the rationalisations that will be available are: "it's a flake", "it passed
alone this morning", "the fixture change is obviously correct", "just re-run it".
All four are pre-rejected here.

### RED anywhere else

**New information. The branch is not ready.** Not a flake until proven one, and
proving one means the isolation run plus an attribution, in the form the e2e
failures got (`s37` load flake, `s34` identical on `origin/main`, `s42` = #187).
No merge, no PR.

### GREEN (exit 0, summary line, both step-0 conditions)

The composite becomes **a single green run — the first on the final tree.** Say
that plainly and stop hedging it, which is the opposite error and also worth
naming. Then the sequence unblocks, in order:

1. `git push --force-with-lease` (remote is pre-rebase at `3f9164f`).
2. Open the PR. The body MUST carry both or the required checks fail:

       ## Adversarial audit
       Findings: ...
       Disposition: ...
       Scope: ...

       Auto-close-approved: 125, 126

   The three adversarial passes are citable as a real audit — verified from the
   transcripts, correct cwd, definition read from disk three times.
3. **Confirm the closes took BEFORE merging:**
   `gh pr view <n> --json closingIssuesReferences`. GitHub needs a keyword per
   reference; #126 would otherwise stay open on the mvp-blocking list asserting
   a defect that no longer exists.
4. Merge is **not unattended** — trips merge-rule condition 5 on the scoring
   engine, `models/**`, `apps/api/tests/**`, `e2e/**` and the web test globs,
   and condition 6 on two client-visible strings. It comes back to Gene.
5. **Then** cut the reconciliation branch **off the merge commit, not `main`**,
   and apply `scratchpad/dispositions.md`.

## What does not change in any of the three cases

- `CLAUDE.md` gets the gate standard (exercise the judgment, then exercise the
  delivery) only after the run returns — the tree does not move under a verdict.
- The reconciliation's numbers stay blocked until Track C merges. A red suite
  means more work and a different Actual.
