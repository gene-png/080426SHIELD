# SHIELD Delivery Plan — post-v2 (A–F) to production

_Created 2026-07-02. Owner: David Catarious. Execution: autonomous sprint loop
(`/loop-sprint-cron` + `.claude/sprint-queue.json`), human-gated items called out
explicitly. Sprint docs: `SPRINT_<n>.md`._

## Where we are

**Current as of 2026-08-19.** The MVP path is tracked in the section below, which
is maintained rather than archival. Sprint sections further down are historical
and are left as written.

Five services are built and running (Tech Debt, ATT&CK, Zero Trust, NIST CSF,
Risk Register), all with exporters, deliverables and client dashboards. 43
Playwright specs plus ~900 backend and ~220 web unit tests run in CI. Since
2026-08-08 the work has been the **cross-service integrity stretch**
(`docs/plans/2026-08-08-cross-service-integrity.md`, W0–W8) rather than new
features: making AI-suggested values impossible to lose silently, and making
approval and release mean what they say.

The 2026-07-02 framing below — "nothing has been verified at runtime" — no longer
holds and is kept only as history. What is still true, and is the single largest
gap, is that **no part of the AI layer has ever run against a real model**; see
item 0 in the MVP path.

_Original 2026-07-02 entry: the v2 Developer Work Order (Parts A–F) is merged to
`main` (PR #1, v3.0.0); all local CI gates were green at merge but nothing was
runtime-verified; `SMOKE_TEST.md` was entirely unchecked._

## Guiding rules

- Every automatable SMOKE_TEST.md item becomes a **committed Playwright spec**
  under `e2e/` — the smoke test should never again require a human for the parts
  a browser can assert.
- Defects found get fixed in the same sprint, each on the sprint branch as its
  own conventional commit; small PRs to `gene-png/SHIELD062626` once collaborator
  access lands.
- Human-only items (document eyeballing, live-AI run, infra account decisions)
  are tracked here as **needs-David**, never silently dropped.
- "AI suggests, code computes" is inviolable: no fix may move scoring into
  prompts or fixtures into human-reachable paths.

## MVP completion path (LIVING — update as items land)

_Added 2026-08-19, current as of 2026-08-25. **This section is maintained, not archival.** When an item
lands, change its status here in the same PR that lands it — the same rule
`CONTEXT.md` follows. A status line that is wrong is worse than none, because
this is the document someone reads to decide what to work on._

**MVP means:** all five services usable for real client engagements, producing
correct documents, with the AI layer working end to end. Not the seeded demo —
fixture mode already demos all five.

**`mvp-blocking` means the MVP cannot ship while this is open.** Written down
2026-08-30 because the label had drifted to "this is important" and four issues <!-- counted: historical -->
were carrying it without meeting the bar or belonging to any item. Two failed
the test and were re-labelled or closed; two were real and became item 11. The
definition is here, where the plan defines its scope, so the next triage answers
itself instead of arriving as a question.

<!-- counted: "exactly one item" states a cardinality rule, not a tally -->
**Every `mvp-blocking` issue belongs to exactly one item below, or is recorded
as deliberately unowned with a reason.** An unowned blocker is invisible: the
plan's total silently stops covering the plan's own definition of done, which is
what happened between 2026-08-26 and 2026-08-30.

### Order, status, and what blocks what

| # | Item | Status | Blocked by | Estimate | Actual |
| --- | --- | --- | --- | --- | --- |
| 0 | **Live-AI verification (#51)** | **DONE** (2026-08-19) | — | — | — |
| 1 | **Export-target trio — #73 + #75 + #79** | **DONE** (PR #86, D-049, merged 2026-08-20) | — | — | — |
| 2 | **CSF client dashboard** | **DONE** (PR #80, merged 2026-08-19) | — | — | — |
| 2a | **W8a — the #72 sweep (tests that cannot fail)** | **DONE** (PR #93, D-051, merged 2026-08-20) | — | — | — |
| 3a | **Export/persistence audit — Tech Debt (+ #77)** | **DONE** (PR #94, D-052, merged 2026-08-20) | — | — | — |
| 3b | **Export/persistence audit — ATT&CK** | **DONE** (PR #116, merged 2026-08-22). <!-- counted: historical --> §14 audit run against the post-#102 shape: D-052's shape-guard invariant **confirmed** for all five jobs and now mechanically pinned; three defects fixed (per-technique surfaces contradicted the rollup in the same document; the top-50 gap truncation disclosure was pinned by no test; D/P/R posture counted unconfirmed tools); two filed — #114 (dashboard recomputes from latest APPROVED while labelled with the released version, suspected CSF/ZT twins) and #115 (a partially-failed run is indistinguishable from a complete one) | — | — | — |
| 4 | **W3 — Tech Debt approval snapshot** | **DONE** (PR #95, D-053, migration 0043, merged 2026-08-20). Regression fixed by **#96** | — | — | — |
| 5 | **W2 — ATT&CK resolver rewrite + tri-state** | **DONE** (PR #103, merged 2026-08-20). Scoped to the resolver; the two gaps it left honest rather than implied are #101 + #102, item 5a | — | — | — |
| 5a | **#101 + #102 — persist the flags, and stop unconfirmed support scoring** | **DONE** (PR #110, merged 2026-08-21). <!-- counted: historical --> Migrations 0044 + 0045, `attack/pending.py`, run-AI + patch + `confirm-citations` + heatmap + finalize + all 3 exporters + admin and CLIENT surfaces, `seed_demo` (D-055, D-056). §14 audit: 6 findings, 5 fixed, 1 filed (#109). CI green — six checks incl. full E2E. The local `s2` / `s33:84` failures were **measured, not assumed**: `/admin/management` costs 1+2N requests and took 95.6s to settle at 88 clients vs 5.4s at 3; both specs pass on a re-seeded DB. Product finding tracked as #111 | — | — | — |
| 6 | **W1 Risk step (+ #84)** | Not started — **re-sized 2026-08-22** after an adversarial review of the item-9 sweep. Now also owns **#121** (the `risk_synthesize` prompt instructs tokens the parser rejects, so a live run stores entries with no likelihood/impact/tier and the client dashboard reports N open risks whose matrix sums to fewer than N — this is **F6**, which the 2026-08-08 plan says belongs in W1) and **#122** (the audit row counts findings received, never entries persisted) and **#132** (`risk.py` re-derives the ATT&CK citation drop as a two-line list comprehension with no counter, no reason and nothing in the audit row -- found by grepping the SHAPE, not the call sites, and absent from this plan entirely until the review of PR #157 noticed an `mvp-blocking` issue with no owning item). **#84 is two call sites, not one** — `risk.py:177` and `:193` | Nothing | **4–6 sessions** (re-sized 2026-08-25 — see "Why the range is wide") | — |
| 7 | **W1 ATT&CK step** | **PART 2 IN PROGRESS, RED ON PURPOSE** — branch `feat/attack-ai-inputs-provenance` carries a committed failing test (`db43a86`) and no endpoint; that 404 is where work resumes. **Decision superseded 2026-08-26.** It read "port the `/ai-inputs` panel from #29's branch (6 new files, zero drift)". `feat/attack-ai-inputs-visibility` is now 104 commits behind `main` <!-- counted: git rev-list --count origin/feat/attack-ai-inputs-visibility..origin/main, 2026-08-27 --> and its `routes/attack.py` differs by 385 insertions / 626 deletions -- it predates the resolver rewrite (5a), the D-053 snapshot, #102's withholding and #133's enrichment, and the endpoint its four files call does not exist on `main` under that name -- **but the payload half of this item already SHIPS**, see the scope correction below. So: WRITE fresh against the current resolver using #29 as a shape reference, rewrite the enrichment, and re-derive #33's finding 5. **The 1-1.5 estimate rested on the porting assumption, which expired; the current 4-6 was derived bottom-up on 2026-08-27 (see "Re-sizing item 7") and needs no further work.** Also owns **#131** — an unapproved draft's vendor and spelling override the approved snapshot and the winning spelling reaches the client deliverable; same file and the same `pairs` tuple #133 widened | Nothing (5a is DONE) | **4–6 sessions** (re-derived 2026-08-27 — see "Re-sizing item 7") | — |
| 8 | **W6 — Risk export/publish split** | Not started. **SPLIT 2026-08-30:** #123 is the `routes/clients.py` half and queues behind #114 (same file — see "File-contention dependencies"); the export/publish half is independent. Also owns **#123** — clicking Generate 404s the client's Risk dashboard with "No finalized Risk Register for your organization yet" while the finalized v1 sits right there, because the query takes the highest version with no finalized filter | **#123 half: #114.** Export/publish half: nothing | **1–1.5 sessions** | — |
| 9 | **Correctness defects only a code review catches** | **IN PROGRESS — sweep done, fixes not started.** MVP-blocking, reclassified 2026-08-22. Carries #114 (all four client dashboards label released-deliverable numbers with a recomputed assessment — 8 call sites, one root cause), #115 (a partially-failed AI run is indistinguishable from a complete one), #46 (a wrong top-level key collapses to zero silently — the root of half of #115), #109 (an `unusable` citation leaves no per-row record). **#59 stays deferred**; #114 ships a loud typed error on NULL `parent_version` instead — see the note below. **The targeted twin-sweep is DONE** and its ~0.5–1 session is spent, not remaining: it found the ZT Gap-Plan caption defect (fixed, PR #127) and, once its own verdicts were adversarially reviewed, three more — **#124** (ZT client dashboard ignores the engagement target: "+0 points to target" beside a PDF saying 37 gaps at S4), **#125** (a DoD target of Stage 4 is silently clamped to 3 and then labelled `source: client`), **#126** (Tech Debt "Annual spend" is a floor with no flag, beside a `savings` figure that has one). The open-ended audits of CSF/ZT/Risk are #118, deferred with a firing trigger rather than to a backlog | Nothing | **4–6 sessions** (fixes only; re-sized 2026-08-25 — see "Why the range is wide") | — |
| 9a | **Docs-truth pass — `docs/security.md`** | **DONE** (PR for `docs/security-honesty-pass`, 2026-08-25). The doc stated TLS, KMS at rest, signed CI artifacts, a server-side MIME sniff, an HIBP top-100k check, a payload hash on the audit row, and a 15-minute access token. None existed. Split into implemented-with-evidence vs planned-not-implemented on `docs/operations.md`'s model; `operations.md`'s own false "(idempotent)" claim about `seed_demo.py` fixed too | Nothing | **0.5–1 session** | **~1.5–2 sessions** (3 review rounds, ~30 findings; 2 code defects filed as #142/#144, 1 tooling as #143, plus #145 and a new CI gate) |
| 10 | **The redaction boundary — eight filed defects (#135–#140, #142, #144)** | **DONE** (PR #155, merged 2026-08-26). <!-- counted: historical --> Sixteen blockers surfaced over four review rounds; thirteen closed here, two filed as #152/#153, one as #151. Five were introduced by the fix for a different defect — two of those inside this branch (B3→B12, B11→B16) — and one, the name dictionary destroying the word `client` for any tenant with a generic mailbox, was **pre-existing on `main`** and found only because the reviewer was pointed at the hint construction rather than the rules. Two derived corpora ship with it and are permanent: `test_redact_real_identifiers.py` (848 shipped ATT&CK/CSF/ZT identifiers in three contexts) and `scripts/leave_row_oracle.py` (disables one narrowing guard at a time and reports which exemption rows still pass). Both found defects no truth-table cell could. CI green on all seven checks including E2E and Demo, which had never run on the branch | Nothing | **2–3** | **~5–6** |
| 11 | **The two redaction leaks item 10 filed rather than fixed — #152 + #153** | Not started. Filed by item 10 and **orphaned when it closed**: both are labelled `client-data-egress` on a FedRAMP Moderate/High target, so client identifiers reach a third-party provider. #152 — a signature block whose signatory line ends in punctuation or exceeds four words is not cut. #153 — bare UK national, E.164 without the plus, and the US international prefix all leak. One PR, batched by file per the item-10 rule: both live in `app/ai/redact.py` and are decided by the same corpus | Nothing | **On start** — see below | — |
| 12 | **The pre-commit hook set diverges from every pinned tool version — #168** | Not started. Found by the adversarial reviewer during the #165 sweep, **pre-existing on `main`**. `.pre-commit-config.yaml` runs prettier `v3.1.0` (46 files disagree, measured 2026-08-30), ruff `v0.6.9` against `ruff==0.16.3`, and black `24.8.0` against `black==26.5.1` — all three REWRITE, while `SECURITY.md:44` makes the hook mandatory and `docs/development.md:65` forbids `--no-verify`. A mandatory step producing the failure it exists to prevent. The prettier half needs a local hook (`mirrors-prettier` is archived and `v3.1.0` is its newest tag); the ruff/black half is a `rev` bump whose **effect is unmeasured** — black crosses two stable-style years | **Nothing logically; land it BETWEEN items** — its fix reformats 46 files, so it collides with every other item's working tree | **On start** — see below | — |


### Total remaining: 13–19.5 sessions across the FOUR SIZED items, and the parts sum to it

**Updated 2026-08-27**, when item 7 was re-derived. Previously 10–15. Expect the upper half; see the
next section for why, and note that all three measured items have now landed
in it or past it.

**Size items 6 and 9 with the review rounds INSIDE the number, not added
afterwards.** Both fix code that already exists, so their truth tables land in
the after-the-rule regime — measured at 42% of in-risk exemption rows pinning
nothing, against 3.8% for tables written before their pattern. The LEAVE-row
oracle run is already budgeted into both; what the estimate must also carry is
the rounds that oracle output will generate.

**A HISTORICAL note, kept because the incident is the lesson.** During PR #146
this heading read 12–18.5 for one draft and the parts did not sum to it. The
totals it discusses — 12–18.5 and 12–18 — are both superseded: item 10 landed on
2026-08-26 and the figure is now 13–19.5 across the items in the table below,
after item 7 was re-sized on 2026-08-27.

That restatement is itself the rule firing. The paragraph said "today's 12–18"
and went stale the moment the item it was written beside was marked DONE, in the
same commit, by the same author. A total in prose is a derived value with a
second place to be wrong, which is why `check_plan_totals.py` reads the table
rather than the sentence. The residual
was exactly 0.5–1: item **9a**, which is DONE in this PR and was still being
counted as remaining. (The total then returned to 12–18 by a separate route:
item 10 grew from six issues to eight and was re-sized 1.5–2.5 → 2–3. Two <!-- counted: historical -->
unrelated changes landing near the same figure is a coincidence worth naming,
because a reader comparing drafts would otherwise conclude nothing had moved.) The number was carried forward rather than re-added
— in the section whose own next paragraph says a total that does not sum is the
same defect as a wrong status line. Caught by the adversarial review of this PR,
not by writing the rule.

| Item | Estimate |
| --- | --- |
| 7 — W1 ATT&CK step (+ #131) | 4–6 |
| 9 — correctness defects only a code review catches | 4–6 |
| 6 — W1 Risk step | 4–6 |
| 8 — W6 Risk export/publish split | 1–1.5 |
| **Total** | **13–19.5** |

**Items 11 and 12 are NOT in that table and NOT in that total, on purpose.**
Both are sized **on start**, so the total above covers four of the six remaining
items and says so rather than implying otherwise. They are excluded from the
summing table rather than given a placeholder because `check_plan_totals.py`
fails loud on an estimate it cannot parse — that is the fix for the bug where an
annotated cell was dropped from the sum in silence, and putting "on start" in
the table would either trip the gate or force the placeholder that caused it.

**Why unsized rather than guessed.** Item 10 was sized 2–3 and landed at ~5–6;
issue 165 was sized "two characters" and landed at 15 files, four review rounds
and new issues of its own. Both are redaction/tooling work, which is exactly what items
11 and 12 are, and neither sized from the outside. Item 7 got the same treatment
on 2026-08-27 for the same reason. A forecast written the week the last one was
found wrong is how a third gets written.

At 4–8 hours a session the four sized items are roughly **52–156 hours**, or
**2–6 working weeks** at 5–6 productive hours a day — plus items 11 and 12.
The width of that is the point, not a
hedge; see below. **Nothing is blocked by anything at the ITEM level** — but
several units inside items 8 and 9 are blocked at the FILE level, all in
`routes/clients.py` — the block below is the list; see "File-contention dependencies". At the item level: 5a was the last link in the W3 → W2 → W1-ATT&CK chain. Order is
10 → 7 → 9 → 6 → 8, with 11 and 12 unsequenced against them — but **item 12
is the LEAST independent item here, not an independent one.** Fixing #168
reformats 46 files, so it touches every other item's working tree and
changes what `check_recalled_counts` can see (`CLAUDE.md`, "limits of the
mechanism"). Land it between items, never alongside one. Item 11 is
genuinely independent: `app/ai/redact.py` and its own tests.

**The arithmetic is written out because the previous total was asserted rather
than added.** A schedule whose parts do not sum to its total is the same defect
as a status line that is wrong, and this document has now produced both. If an
item re-sizes, the table above moves with it in the same PR.

### The LEAVE-row oracle run is budgeted into items 6 and 9, not discovered there

**Added 2026-08-25, from a measurement rather than a worry.**

`apps/api/scripts/leave_row_oracle.py` disables one narrowing guard at a time and
reports which exemption rows in a truth table still pass. A row that passes with
its guard removed was never testing that guard. Measured over the redaction
corpus:

| Tables | Rows in the risk class | Pinning nothing |
| --- | --- | --- |
| Written before their pattern (#130, PR #141) | 53 | **2 (3.8%)** |
| Written alongside/after their rule (item 10) | 38 | **16 (42.1%)** |

The variable is order, not subject matter: a table written first is an
independent specification, a table written afterwards is a transcript of what
the rule already does.

**Items 6 and 9 both fix code that already exists.** Their tables therefore land
in the 42% regime by construction. That is a derived prediction, not a guess,
and it is why the run is scheduled here rather than left to be rediscovered:

- **Item 6 (W1 Risk step)** — the run costs minutes; the tables it checks decide
  whether a live Risk run's likelihood/impact/tier parsing is pinned or merely
  green (#121, #122).
- **Item 9 (correctness defects)** — same, across four client dashboards.

No re-size for either: the run is minutes against a 4-6 session item, and it is
cheaper than one round of the review it prevents. Recorded so the step is not <!-- counted: "one round" is a unit of comparison, not a tally. -->
read as scope creep when it appears in those PRs.

### Item 10 was the egress half of what items 9 and 6 are the output half of

Worth stating once, because the three read as unrelated on this list. Item 10
fixed what leaves the platform: `redact_for_ai` is the single path every AI
payload takes to a non-FedRAMP provider, and a defect there corrupts the model's
INPUT for all five services at once. Items 9 and 6 fix what comes back — whether
a partially-failed run is distinguishable from a complete one (#115, #46),
whether a live Risk run's entries carry the likelihood and impact the parser
demands (#121, #122), whether a dashboard's numbers describe the assessment it
names (#114).

Same problem, two directions: **can we tell what the AI layer actually did.**
Item 10's answer to that on the egress side is `llm_calls.redaction_mode` — a row
that can now say which mode a call ran under, rather than being byte-identical
whether the redactor ran or was switched off. Items 9 and 6 owe the same
property on the response side, and #122 is literally the same defect facing the
other way: an audit row counting what was received rather than what was kept.

### Why the range is wide, and why the low end is not the plan

The range is wide, and that is honest rather than lazy: what would narrow it is
knowing how many adversarial rounds an item needs, and that is only learned by
doing the item.

(This paragraph used to open by restating the range and its width as a
percentage. Both were correct when written and both went stale the moment item 9a
left the total — a derived value given a second place to be wrong, twenty lines
below the table it was derived from. The cheapest fix for a derived value going
stale is not deriving it in prose.)

The evidence says expect the upper half:

- **The first measurement.** The #130 redaction fix (PR #141) was planned at
  **0.25 sessions** and came in at **0.5–1** — 2–4x. Two review rounds found real
  defects rather than nits, including one *in the fix* that was worse than the
  bug: a narrowed separator class that leaked sixteen Unicode whitespace
  characters, so an address separated by a narrow-no-break space egressed
  verbatim with an empty `removed_counts`.
- **Items 6 and 9 both touch scoring**, and this document already records that
  items touching scoring here have needed **four to five** adversarial rounds
  rather than one.

So items 6 and 9 move from 3–4 to **4–6**. That is a second, separate correction
from the 2026-08-22 re-size — that one redistributed newly-found issues between
items, this one is about round count per item. They add rather than overlap.

### Review overhead is per-PR, not per-unit-of-work — so batch by file, not by issue

**The measurements live in ONE table — "Estimate vs actual, recorded as items
land", below.** This section argues from them; it no longer restates them.

**Consolidated 2026-08-30, because the duplicate had already gone wrong.** A
second copy of this data sat here with its columns in a different order, and it
disagreed with the other one: 9a's actual read `~1` here and `~1.5–2` there,
and `~1.5–2` is what item 9a's own status row says. Nothing flagged it — the
gate reads the totals table, not these. The note under the other table has said
"Maintain ONE table; a second copy is a second place to be wrong" since the
third adversarial pass over PR #146 put it there; the copy it warns about
outlived the warning by two weeks and was found by adding a row to both.

**Every measured item has overrun, and the next sizing should absorb that
rather than rediscover it.** In each, the overrun was review
yield rather than mis-scoping: the work found was real, and most of it was
invisible to the estimate because it did not exist until a fix created it.
Item 10's four rounds produced 9, then 1, then 5, then 1 blockers — the count <!-- counted: historical -->
did not converge monotonically, which is the part a three-round budget would <!-- counted: A hypothetical budget size, not a count of anything that exists. -->
have got wrong.

Two things make item 10's overrun worth the price rather than a warning:
**one** of the sixteen was a pre-existing defect on `main` that nothing else in
the process would have found — the name dictionary destroying the word
"client" for any tenant with a generic mailbox. Five were **introduced by the
fix for a different defect**, which is a cost of the round rather than a
recovery from it.

(An earlier draft of this sentence said "five … pre-existing on `main`",
swapping the two categories and inflating the recovery 5x — in the paragraph
offered as the reason the overrun was worth paying. Row 72 of this file had it
right the whole time.)

The second thing: the two derived corpora it produced are permanent, and both
are now budgeted into items 6 and 9.

None of the three was mis-scoped. In each, the reviewer found real defects at a steady
rate right through the last round — the second round of #130 found a leak worse
than the bug being fixed, and the third round of 9a found a live wrong total in
the PR that existed to end wrong totals. The rounds were not padding.

What that means for sizing: **a fixed 2–9 hours of review sits on every PR
regardless of its size.** Small items pay it proportionally hardest, and the
cost scales with the number of PRs, not with the amount of work.

**So: batch by file and harness, not by issue number.**

- **Item 10 is ONE PR, not six.** #135–#140 are six defects in `app/ai/redact.py`, <!-- counted: historical -->
  all decided by the same truth table, all reviewed in the same context. Six
  branches would pay the review overhead six times for no additional review
  value — the reviewer would re-read the same file six times — and would leave
  five stale cross-references in the docs between merges. This is why item 10 was
  first sized at 1.5–2.5 rather than the 3–4 a cold item carries. It was re-sized
  to 2–3 and landed at ~5–6; the table row is the record.
- **Item 9's issues** (#114, #115, #46, #109, #124, #125, #126) split more
  naturally, because they span four surfaces. Split them by **surface**, not by
  issue — **four groups, and every issue is in exactly one**:

  | Group | Issues | Surface |
  | --- | --- | --- |
  | Parse guards | #46, #115 | `app/ai/engine.py` |
  | Version label | #114 | the four client dashboards + `routes/clients.py` |
  | Target and flag defects | #124, #125, #126 | ZT and Tech Debt |
  | Per-row citation record | #109 | `app/attack/pending.py`, `attack/citations.py` |

  **#109 gets its own group rather than riding with another.** It is a fourth
  surface — the ATT&CK pending/citation store — and folds into none of the other
  three. An earlier draft of this split listed three groups covering six of the
  seven, which reads as covering all of them: the item's stated scope stops
  matching its branches and nothing fails to say so. Same shape as #131 being
  unowned for a week. Cheaper to fix on paper than after three branches are open.

Written down because the instinct at the moment of starting is to open one
branch per issue — it feels tidier, and it produces a cleaner issue tracker. It
also multiplies the one cost this table shows is fixed.

### When the two batching rules conflict, cost wins — and the `Scope:` line says so

**They do conflict, and item 10 is the case.** Two rules are in play and they are
not the same rule:

- **Batch by surface** is about *review coherence*. A reviewer holding the
  address truth table in mind is not in the right frame to audit an
  `is_production()` predicate.
- **Batch to amortise overhead** is about *cost*. A fixed 2–9 hours of review
  sits on every PR regardless of size.

Item 10 spans **three** surfaces: `app/ai/redact.py` (#135–#140),
`app/config.py` + `app/main.py` (#142), and a model plus an Alembic migration
(#144). Surface coherence says split it; cost says do not, because #142 is one
predicate and three call sites and its own PR would pay the full fixed review
cost for a ten-line change.

**For a change that small, cost wins — keep the grouping.** But the reviewer's
recorded failure mode is *"ran, but not against this change — a stale tree, the
wrong branch, a subset of the diff"*, and a three-surface PR is the ideal shape
for a clean report about two thirds of it. So:

> **When cost overrides surface coherence, the PR's `Scope:` line enumerates
> every surface rather than describing the PR by its dominant one.**

That field exists for exactly this and it costs a sentence. Without it the next
reader sees a rule applied inconsistently with no record of the trade — and the
audit block reads as complete over a diff the reviewer only partly saw.

### A PR that files an issue names its owning item in the same body

**Filing an issue and assigning it to an item are separate steps, and only the
first has a gate.** `check_issue_references.py` stops a PR closing an issue by
accident; nothing notices a PR that *creates* one and leaves it unowned. So every
PR that files issues reliably produces unowned ones, and they surface weeks later
as "the plan cannot deliver the outcome it states".

Four this session alone, and they are not four one-offs — they are one missing
step, four times:

| Issue | Went unowned until |
| --- | --- |
| #131 | a week; caught while re-reading the plan |
| #109 | caught on paper, in a split that covered six of seven |
| #142 | this section |
| #143 | this section |

**The practice:** a PR that files an issue names the owning item in its body, or
marks it **deliberately unowned** and says why. It costs nothing at filing time
and is checkable by eye in review.

**Not gated, deliberately.** A check would have to recognise "this PR filed issue
N" and "N is assigned to an item", and the only signal in the body is an issue
reference — which appears in prose constantly for reasons that have nothing to do
with filing. That is the same signal-to-noise problem measured for the prose-total
gate (1 real in 13) and for TI001 (5 in 41), and it fails it worse. Written down
instead, beside the batching rule, because both are decisions made at the moment
of starting when the instinct runs the other way.

**Assignments for the issues this section names:**

- **#142** — the `is_production()` predicate covering one of three environments,
  so `SHIELD_REDACTION_MODE=off` and a placeholder signing secret are permitted
  on `staging`. Owned by **item 10**: single egress path, security boundary, and
  the same file family as #135-#140.
- **#144** — `llm_calls` records no redaction mode, so a disabled-redactor row is
  byte-identical to a clean one. Also **item 10**, though it carries a migration
  the other six do not; if it splits out, it splits as a second PR within the
  item rather than a seventh branch.
- **#143** — the pre-push hook printing "skipped (api container not running)"
  over a genuinely failing suite. **Deliberately not on the MVP path and not
  labelled `mvp-blocking`**: it is developer tooling, CI still runs the suite as
  a required check, and no client document or audit row depends on it. Stated
  rather than left unlabelled, because in a list "unlabelled" and "deliberately
  out of scope" look identical.
- **#175** - `./packages:/app/packages` is bind-mounted with no `node_modules`
  overlay, so a host `pnpm install` breaks the container for the five workspace
  packages behind it. **Deliberately not on the MVP path and not labelled
  `mvp-blocking`**, on the same reasoning as #143 directly above: it is
  developer environment setup, and no client document or audit row depends on
  it. The bar is the one written at the top of this file - MVP means all five
  services producing correct documents - and a broken container produces no
  document at all rather than a wrong one, which is the failure mode CI and a
  rebuild already cover. Stated rather than left unlabelled, for the reason
  #143 gives.

  Recorded 2026-09-02 after the issue was cited in review as carrying
  `mvp-blocking`. It does not, and never did - `gh issue view 175` returns an
  empty label set, and it is absent from `gh issue list --label mvp-blocking
  --state open`. The claim came from a summary table, not from the API. Noted
  because an unlabelled issue and a deliberately-exempt one are the same bytes,
  which is exactly what #143's last sentence is about, and because the blocking
  set is what the delivery order is derived from: a phantom member distorts
  every sequencing decision taken after it.
- **#184** - CSF silently clamps an out-of-range `target_tier` and reports the
  clamped value back as the one requested. **Deliberately not on the MVP path
  and not labelled `mvp-blocking`**, same treatment as #143 and #175 above.

  It is the CSF twin of #125 and it was labelled `mvp-blocking` on filing, on
  the reasoning that `target_tier` renders verbatim into the client deliverable
  - `csf/exporters.py:310`/`:402` headings, `:315`/`:407` empty state,
  `:326`/`:421` every gap row - and that `routes/csf.py:2261` passes a
  client-supplied value into `analyze_gaps`. Both facts are true. **The label
  was still wrong**, because a render site only matters if a bad value can
  reach it, and none can: `schemas/intake.py:75`/`:174` bound `csf_target_tier`
  at `ge=2, le=4`, `schemas/csf.py:166` bounds the self-assessment write at
  `ge=1, le=4`, and CSF's ceiling is 4. Every write path sits inside the ladder,
  so the clamp is unreachable from stored data. The live defect is confined to
  the `/gap-analysis` query parameter, which finalize never receives.

  **The condition that flips it, written down because it is not hypothetical:**
  a CSF variant whose ceiling falls BELOW its schema bound. That is precisely
  what DoD ZTRA did to Zero Trust - a 3-stage ladder behind a schema still
  permitting 4 - and #125 is what it cost. One new framework, or one widened
  bound, converts #184 from latent to shipped with no other code change and
  nothing on the path to catch it. Re-label it the day either happens.

  Stated rather than left unlabelled, for the reason #143 gives.

### Scope correction, 2026-08-27 — half of item 7 part 2 already ships

**Read this before writing any code for item 7 part 2.** Verified against `main`
at `fdfde7d` by reading the code, not the plan.

`POST /ai/preview` exists (`apps/api/app/routes/ai_preview.py`): admin-only,
tenant-scoped, and it builds its payload by calling `build_attack_ai_request` --
the exact function run-ai uses -- so a preview cannot diverge from what
egresses. It returns the REDACTED outbound payload plus `removed_counts`,
constructs no provider and writes no `llm_calls` row. The web half ships too:
`app/api/proxy/ai/preview/route.ts`, `lib/ai/preview.ts`, and `AiPreviewButton`,
which is **already rendered in `AttackWorkspace.tsx`** alongside CSF and ZT, with
`tests/unit/test_ai_preview.py` behind it.

So "the endpoint does not exist" is true of the NAME
(`/attack/services/{id}/ai-inputs` appears nowhere in `apps/api/app` or
`apps/web/src`) and misleading about the CAPABILITY. Acting on the old sentence
means building a second payload view. That is the wrong work this correction
exists to prevent.

**The remaining gap is a different question, and it is the more valuable one.**

| Endpoint | Answers |
| --- | --- |
| `/ai/preview` (ships) | *What will be sent?* |
| `/ai-inputs` (open) | *What was NOT sent, and where did what was sent come from?* |

The original spec is provenance and exclusions: `capabilities[]` with
`awaiting_signoff` / `source_list_version` / `source_document`; `sources[]`;
`excluded[]` from `CapabilityList.excluded_rows`; `not_sent[]` filtered out by
security scope; `totals`.

**Why that gap matters, in the code's own words.** `_client_capability_inputs`
applies three load-bearing filters -- security scope, list status, and
approved-snapshot membership -- and returns only the survivors. It surfaces
nothing it drops. Its docstring already states the consequence:

> a tool missing from it cannot be named, and the technique it covers reads as
> uncovered

The filter is correct on all three counts. That is the point: this is not a bug,
it is a correct filter whose drops are invisible. A `gap` on a client
deliverable can mean "no control here" or "the tool was filtered and nobody
could see it", and the client cannot tell which.

**So the work is:** provenance and exclusions only, TDD-first against the three
filters, and a panel section BESIDE `AiPreviewButton` rather than a second
surface -- which is what `docs/plans/2026-08-08-attack-citation-resolver.md`
already says: "the step-1 edit modal should extend that panel rather than invent
a second surface".

**The 4-6 estimate THIS SECTION was written against is SUPERSEDED and was deliberately not replaced at the time.**
**[Superseded in turn — read "Re-sizing item 7" below.]** That section
re-derived 4-6 from scratch, bottom-up, and recorded it; the two numbers are
the same and their derivations are not, which is why this paragraph reads as
a contradiction without this line. What follows describes the FIRST 4-6. It
priced a payload half that had already shipped. A forecast is not a recalled
count -- there is no command to cite -- so writing a second derived number on
the same day the first was found wrong is how a third gets written. The measured
actual replaces it when the item lands, which is the discipline the
estimate-vs-actual table exists for.

**Generalised, because item 7's premise was wrong by half and items 9, 6 and 8
were sized against assumptions about what exists too: verifying an item's
premise against `main` is the FIRST action when starting any item.** Not a
re-plan of the remaining items now -- that is the move that costs days. One
cheap check, distributed, at the moment it is worth doing. It paid for itself
here before a line of code.

### Re-sizing item 7, 2026-08-27

The recorded **1–1.5** rested on one assumption — "port the `/ai-inputs` panel
from #29's branch, zero drift" — and that assumption expired. It is not adjusted
here; it is void, and the replacement is derived from two independent directions
that are then checked against each other.

**What actually has to be built.** `feat/attack-ai-inputs-visibility` is 104
commits behind `main`. Its ai-inputs-specific surface is **825 insertions**
across six files (a 243-line panel, a 214-line panel test, a 280-line backend
test, types, client, proxy route) — genuinely useful as a shape reference. But
it sits on **630 insertions** of backend that `main` has since rewritten:
`routes/attack.py` is 1835 lines today and `citations.py` 478, and neither
resembles what #29 called. The endpoint does not exist on `main` at all; the
only trace is a stale `.pyc`. So the panel is a reference and the backend is a
fresh write, against four subsystems that all postdate #29: the resolver rewrite
(5a), the D-053 approval snapshot, #102's withholding, and #133's enrichment.
The payload has to express all four or the panel shows something the model was
never given.

**Bottom-up:** backend endpoint and schema against the current resolver,
including reading those four subsystems (0.75–1); backend tests covering tenant
isolation, admin-only, and redaction parity by CALLING the redactor rather than
restating it (0.5–0.75); the web half — proxy route, client, types, panel,
workspace wiring, vitest (0.75–1); e2e plus the `--force-recreate web` cycle and
the serialised seeded DB (0.25–0.5); review rounds, which are inside the number
and not a contingency (0.75–1.25); and **#131** — a resolver defect whose fix
changes client deliverable content, so it needs its own enumeration and its own
verification that the losing spelling stops reaching the deliverable (0.75–1.25).
That sums to **3.75–5.75**.

**Cross-check from the measured ratios.** Stated precisely, because an earlier
draft of this paragraph said "2–4x on every item that has landed" and that is
row one's own label promoted to a property of the whole table. What the table
actually records is **1.5–4x** (9a, 0.5–1 against ~1.5–2), **1.67–3x** (item 10,
2–3 against ~5–6) and **2–4x** (#130, 0.25 against 0.5–1) — a band of roughly
1.5–4x, with the largest item at the low end. A fresh-write base of 1.5–2 against
that gives 1.5–8. The bottom-up figure sits inside it. The conclusion survives
the correction, which is why the correction is worth making: the answer did not
depend on the overstatement, so nothing is lost by removing it.

**Recorded as 4–6.**

**Recommendation: split it, and the reason is measured rather than aesthetic.**
Item 7 part 2 and #131 should be separate PRs. Splitting no longer costs an
unattended merge — both come back to a human under condition 5 regardless, since
an endpoint plus a panel ships with tests and #131 changes deliverable content.
What it buys is review convergence: the four adversarial passes over PR #157
returned 17, 12, 11 and 15 findings and did not converge, because each pass
audited a surface the previous step had grown. A smaller surface is the only
lever that has ever moved that number. Suggested split, decomposed from the bottom-up above rather than estimated
afresh, so the parts still sum to the whole: **7b, endpoint and panel,
3–4.5** (the bottom-up total less #131's share); **#131, 0.75–1.25**. An
earlier draft said 2.5–4 and 1–2, which summed to 3.5–6 and matched neither the
parts nor the recorded 4–6 — and acting on it would have moved the plan total to
12.5–19.5 with `check_plan_totals` reporting green, because that gate checks
only that the table sums to itself.

### Estimate vs actual, recorded as items land

The **Actual** column in the table above is filled in the PR that lands each
item, not afterwards. Real measurements will size the remaining work
better than any judgement call — the same move this document already made for
"what a session is, in hours", which is measured from git history rather than
guessed. When a total is next wrong, the arithmetic will be sitting beside it.

| Work | Estimated | Actual | Ratio | Review rounds | Findings |
| --- | --- | --- | --- | --- | --- |
| #130 redaction fix (PR #141) | 0.25 | 0.5–1 | 2–4x | 2 | 16 |
| 9a docs-truth pass, `docs/security.md` | 0.5–1 | ~1.5–2 | **1.5–4x** | 3 | ~30 |
| 10 the redaction boundary (PR #155) | 2–3 | ~5–6 | 1.67–3x | 4 | 16 blockers |
| issue 165, the prettier pin (PR #169) | "two characters" | 15 files, 4 versions | **not computable** | 4 | 4 BLOCKING + 2 ADVISORY |

**Superseded — the table directly above is now the only one.** This paragraph was written when 9a and #130 were the only measured
items and said 9a was "the larger overrun of the two". Item 10 has since
landed at 2-3 estimated against ~5-6 actual and is the larger of THREE.

Kept rather than deleted because the near-miss is the lesson: a row was added
to one estimate-vs-actual table and this sibling section, 130 lines down in
the same file, was not touched — found by the third adversarial pass over the
PR that added the row. Maintain ONE table; a second copy is a second place to
be wrong.
It was sized "under a session" as a documentation edit. It took three review
rounds and produced two new `mvp-blocking` issues (#142, #144), one unlabelled
tooling issue (#143), a new CI gate with 19 tests, and #145 — because the audit
of a document's claims is an audit of the code behind them, and the code
disagreed in ten places. A table that recorded the small overrun and omitted the
big one would be status ahead of truth one level up, inside the pass whose
subject is exactly that.

### Why item 9 exists (added 2026-08-22)

**MVP means all five services usable for real client engagements, producing
correct documents.** A defect that makes a document say something untrue is
therefore MVP-blocking whether or not it is on a feature list — and this class
has a specific property that keeps it out of one:

> "These are things only a detailed code review catches, and my own pre-launch
> pass is going to be focused on UI and on the AI producing consistent, accurate
> outputs, not code-level review."

None of the three is visible from the UI, and none produces a wrong-looking
number. #114 shows a *plausible* coverage figure under a *plausible* version
label — the two simply come from different records. #115 reports a citation total
that is internally consistent and silently covers a fraction of the catalogue.
#109 loses a disclosure while the score stays correct. A pre-launch pass looking
for things that look wrong will pass all three.

So they do not go in a backlog to be caught later, because the mechanism that
would catch them is the one not being run. They are scheduled.

**Not exhaustive.** Item 9 names the three found so far; the audits that produced
them (items 3a and 3b) covered Tech Debt and ATT&CK only. CSF, ZT and Risk have
had no equivalent pass, and #114 is already evidence that these defects come in
sets of four — it was filed against ATT&CK and confirmed in all four dashboards,
including one nobody suspected.

#### Two scope decisions, stated rather than left to be discovered

**#59 stays deferred. #114's fix ships a loud fallback instead.** #114 depends on
`Deliverable.parent_version`, and #59 documents that the repair path for it is a
permanent no-op on multi-version parents — so on the face of it item 9 could not
complete. Measured before deciding:

- All four finalize paths (`attack.py`, `csf.py`, `zt.py`, `tech_debt.py`) set
  `parent_version=<assessment>.version` **at creation**. Every deliverable made
  since migration 0041 has it.
- NULL is therefore only possible on rows finalized **before 0041**.
- The dev database holds **0** such rows and **0** services with more than one
  deliverable version, and there is no production deployment.

So the un-repairable case cannot be created any more and does not currently
exist. #114's fix raises a **typed error** when `parent_version` is NULL rather
than falling back to "latest finalized" — a silent fallback would reintroduce
this exact defect for precisely the rows most likely to have several versions.
If that error ever fires it has named a genuinely un-repairable legacy row, which
is when #59 stops being deferrable.

**#46 is in item 9's scope, not separate.** It is the root of half of #115: a
wrong top-level key passes the shape guard, collapses to zero, and for the
batched `mitre_map` job is counted as a batch SUCCESS — invisible even in the
ledger. Fixing #115 without it fixes the visible half only. Note the fix is a
real behaviour change (a provider omitting the key on an empty result goes from
silent zero to hard failure), which is the correct direction under FAIL LOUDLY
but is a deliberate call, not a tidy-up.

#### Why the total moved from 5–6.5 to 8–10.5 (2026-08-22)

The twin-sweep inside item 9 reported six of seven defect shapes clean across <!-- counted: historical -->
CSF, ZT and Risk. An adversarial review of **those verdicts** — not of the
services — overturned four of them.

The failure was in the generalisation step, and it is worth keeping: the sweep
carried ATT&CK's **vocabulary** (`pending_review`, "withheld") into services that
do not use those words, instead of ATT&CK's **shape** — *an aggregate applies an
exclusion that the per-row rendering does not*. Grepping the word returned
nothing and the verdict was recorded as "no twin". The shape was present in three
services, and in one of them it had been written up in
`docs/plans/2026-08-08-cross-service-integrity.md` as F6 since 2026-08-08.

**The split matters more than the total.** The new issues do not all
belong to the item that found them:

- **#121, #122** and the corrected scope of **#84** are Risk-service defects that
  W1's Risk step was always going to have to fix — **item 6**, which absorbs
  ~1.5 sessions that would otherwise have been double-counted in item 9 while
  item 6's real cost stayed hidden behind a settled-looking number.
- **#123** is the generate/export lifecycle — **item 8**.
- **#124, #125, #126** are item 9's own.

A sweep is bounded and cheap and it closed the shapes it was given. What it
cannot do is find a shape nobody has named yet, which is why #118 keeps its
trigger.

### What a "session" is, in hours

Measured from this repo's own git history rather than estimated:

| Unit of work | Rounds | Dense elapsed |
| --- | --- | --- |
| W1 ZT step (PR #66) — red tests through round 5 | 5 | ~8.5h continuous for red → round 3, plus ~2–3h for rounds 4–5 |
| CSF client dashboard (PR #80) — API + frontend + e2e | 1 | ~4h |
| Shape guards + CSF provenance (PR #78) | 1 | ~2–3h |

So **one "session" ≈ 4–8 hours of continuous work**, and the variance is almost
entirely adversarial rounds: each round costs roughly 1–3h including the fixes it
generates. W1-ZT's elapsed span looks like 23h in the log, but two of those gaps
are idle time, not work — do not read commit timestamps as effort.

**8–10.5 sessions ≈ 32–84 hours ≈ 7–15 working days** at 5–6 productive hours a
day. **[SUPERSEDED — the 8–10.5 above is an old total.]** The current figure
is 13–19.5 across the four sized items, plus items 11 and 12 unsized, which the
"Total remaining" section states as **2–6 working weeks**. This paragraph is kept
for its hours-per-session derivation, which is measured and still holds; its
"two to three weeks" conclusion is not current and is superseded by that section.

Two caveats that matter for planning:

- These are throughput numbers for an agent working with parallel subagents, not
  a human developer's rate. Do not use them to size someone else's week.
- **W2 is the estimate most likely to be wrong**, and wrong upward. It is the
  largest item, it touches scoring, and items that touch scoring in this repo
  have needed four to five adversarial rounds rather than one.

### Dependencies, stated rather than implied

```
W3 ──> W2 ──> W1 ATT&CK          (WAS the long pole; W3 and W2 are DONE; item 7 is sized in the table above)
                └─> ATT&CK export audit

#73 ─┬─> (independent)
#75 ─┤
#79 ─┘

W1 Risk ──> (independent)
W6      ──> export/publish half independent; its #123 half queues
            behind #114 (same file) — see "File-contention dependencies"
#51     ──> (independent, but gates "MVP" itself)
```

- **W3 before W2** — narrow-confirmed is unsound against a mutable approved list,
  and the snapshot is what discharges that. Do not assume the dependency is
  satisfied by the ADD-path carve-out; it is not.
- **W2 before W1-ATT&CK** — building counters against a resolver that is about to
  be replaced means building them twice. Also settled: **#44's fork resolves to
  `applied` + a separate tri-state count**, not a reason code inside `dropped`.
- **W2 before the ATT&CK export audit** — same files, and the audit wants the
  post-rewrite shape.
- **#29 must not merge** until a clean adversarial audit. (W2 landed as PR #103 on 2026-08-20; the resolver half of #29 is superseded, the `/ai-inputs` panel half is item 7.)
- Items 1 and 6 depend on nothing and can run in parallel with the chain.
  **Item 8 is HALF independent**: its export/publish half depends on nothing,
  its #123 half queues behind #114 on `routes/clients.py`. This line said
  "1, 6 and 8" for one draft of the very commit that added the dependency
  two lines below it — see the note there.

#### File-contention dependencies, added 2026-08-30

**This block falsified the rule it was written to demonstrate.** `CLAUDE.md`
rule 3 gained a threshold from this branch — "a correction reaches roughly one
screen unaided" — and the two lines immediately above this heading contradicted
it through a first draft and a reviewer pass. **Two lines is not one screen; it
is adjacency, and it still failed.** The rule has been corrected to say what the
evidence supports: proximity catches nothing reliably, and the grep is the only
mechanism at any distance.

These are not logical dependencies — nothing blocks anything conceptually. They
are **the same-file kind**, which is why they were invisible until someone
looked at line numbers instead of item names. Recorded here rather than in a
session summary, because a dependency that lives only in a chat log is the shape
this document already has a bullet about.

**`routes/clients.py` holds four separate work units**, spread across three
items:

```
#124 ZT target ignored          clients.py:749  target = zt_compute(fw, targets)
                                using per-row targets only; the client target
                                (_zt_client_target_stage, :253) is never called
                                in zt_dashboard, though _zt_gap_total uses it :322
#126 Tech Debt spend floor      an unknown annual_cost_usd coerces to 0.0 (:878)
                                and enters annual_spend for EVERY item (:879).
                                savings_cost_known is set False (:882) only when
                                a CUT item has unknown cost -- the CUT guard at
                                :880 makes it a NARROWER predicate, not the same
                                one. The response carries no spend equivalent of
                                that flag, and the flag it needs must be computed
                                over ALL items. Copying the savings predicate
                                ships spend_cost_known: true over a floored
                                spend figure -- a false assurance about money.
                                TWIN, and it is the worse half: tech_debt/
                                exporters.py:96-106 repeats the asymmetry
                                exactly -- total_cost skips an unknown cost
                                (:100-101) while savings_known is CUT-guarded
                                (:102-104) -- so the RELEASED PDF/DOCX/XLSX
                                prints an unqualified "Total annual cost" that
                                is a floor, beside a savings figure that does
                                carry its qualifier. #126 is not a dashboard
                                defect; it reaches the client document
#114 version label vs numbers   the label and the numbers come from two
                                INDEPENDENT lookups: _latest_released_deliverable
                                orders by released_at, _latest_finalized (:182)
                                orders by version. Nothing ties them. Eight
                                call sites: :272 :299 :338 :380 :576 :722 :851
                                :1086 -- and Deliverable.parent_version already
                                records the right answer, used correctly next
                                door in deliverable_release.py
#123 Risk dashboard 404         the register query takes the highest VERSION with
                                no finalized filter (:974), then 404s with a
                                message asserting nothing is finalized (:982)
```

**Every entry above names the MECHANISM, not only the line.** A line number goes
stale the next time anyone reflows the function, silently; the mechanism is
greppable back to a line whenever one is needed. Three of the numbers in the
first draft of this block were wrong for exactly that reason -- see the
spot-check rule in `CLAUDE.md`.

So, as a strict order:

- **#114 requires #124/#125/#126 landed.** Same file. Not folded into one PR
  either: #124/#125/#126 are independent per-service defects — **#125 is not a
  "point fix", see below** — and #114 is a
  cross-cutting refactor, and stacking a refactor on point fixes in one diff is
  item 10's shape.
- **#123 requires #114 landed.** Same file again. #123 is **item 8's
  `clients.py` half** — item 8 spans two territories, and its export/publish
  half is independent of this chain.
- **#125 is the exception to "it is all in `clients.py`"** — its clamp is
  `app/zt/scoring.py:243-244` and its label `routes/zt.py:1747`. That puts the
  #124/#125/#126 PR on **condition 5** (deterministic scoring engines) as well
  as condition 6.
- **#125 is LIVE TODAY on the ZT finalize path — not latent.** An earlier draft
  of this bullet said it was "latent today only because the ZT dashboard
  publishes no target-source field". That second clause is true — `grep
  target_stage_source` returns `routes/zt.py:1747` and nothing in `clients.py` —
  and being true is exactly why it ended the check. The site it cites is
  **finalize**, not the dashboard. Traced end to end:

  ```
  schemas/intake.py:77    zt_target_stage ge=2 le=4, NO framework discrimination
  routes/intake.py:52     _ZT_SERVICE_TYPES treats CISA and DoD identically
  routes/intake.py:85-101 _validate_targets checks PRESENCE only, never range
  zt/maturity.py:96       CISA has 4 stages, DoD has 3
  routes/zt.py:1618/1624  engagement_target passed through as target_stage=
  zt/scoring.py:32        DEFAULT_TARGET_STAGE = STAGE_3 = 3
  zt/scoring.py:243-244   clamps to min(DEFAULT_TARGET_STAGE, max_stage) = 3
  zt/scoring.py:276       returns target_stage= -- the CLAMPED value
  routes/zt.py:1746       "target_stage": gap.target_stage,      <- clamped 3
  routes/zt.py:1747       "target_stage_source": "client"        <- ADJACENT LINE
  ```

  **The two fields are adjacent lines in the same audit row.** It reads
  `target_stage: 3, target_stage_source: "client"` for a client who chose 4 --
  the false value and the false attribution of it, side by side, in the record
  that exists to establish provenance. Nothing between intake and the deliverable
  discriminates by framework: intake accepts 2-4 for both, validates presence
  only, and DoD's ceiling is 3.

  **The UI OFFERS the invalid choice, which is where the fix has to start.**
  `apps/web/src/lib/intake/types.ts:217-221` gives `zero_trust_dod` a
  `{ value: 4, label: "Stage 4 · Optimal" }` option — and "Optimal" is CISA's
  label for its fourth stage, which DoD does not have. So a consultant is shown
  a stage that cannot exist for the framework they selected, under a name
  borrowed from a different one. Every fix-site list for #125 must include it;
  an earlier draft of this block omitted it and would have shipped a backend
  fix under a UI that still offers the value.

  A DoD ZTRA engagement whose client picks Stage 4 at intake is silently clamped
  to 3, and the finalize audit row on the deliverable says the target is 3 and
  the client chose it. That ships today, with no dashboard involved.

  **This is a PRODUCT defect, not a documentation one, and the distinction
  changes how its PR is reviewed.** The other defects in this section are
  documents describing code inaccurately. This is the product writing a FALSE
  STATEMENT ABOUT THE CLIENT'S OWN STATED CHOICE into the audit trail of a
  deliverable, on a FedRAMP Moderate/High-target platform. `target_stage_source`
  exists precisely to distinguish a client's decision from a default, and it
  reports "client" for a value the client did not choose — a guard keyed on
  whether a value was OFFERED rather than whether it SURVIVED.

  Sequencing is unchanged: #125 ships in Track C's first PR because fixing #124
  activates its second surface. What changes is the review — that PR carries a
  falsified audit row and a scoring-engine clamp, and must not be read as three
  small per-service fixes.

  The instruction is unchanged — **#124 and #125 must land together** — but the
  reason is that #124 adds a second surface to an already-live mislabel, not
  that it wakes a sleeping one.

**Item 6 is the one to watch, not to split.** #121 is fixed in `risk.py` and the
AI prompt, but its symptom renders at `clients.py:959-1010`, so a test for it
may reach into the contended file.

### W8 is split, and half of it moved into the path (decided 2026-08-20)

**This was deferred and is no longer.** The #72 pattern — a test that passes
whether or not the fix it guards is present — has now produced **nine**
instances, two of them inside the audit that was specifically hunting for them,
written by the session that had logged the seventh minutes earlier. Nine
failures of a documented discipline is a mechanism problem, and the rule living
in `CLAUDE.md` demonstrably does not prevent new instances.

So W8 splits along the line where the two halves actually differ:

- **W8a — the #72 sweep. Item 2a above, in the path.** Deterministic, no LLM.
- **W8b — the adversarial reviewer as a CI job. Deferral reason CORRECTED
  2026-08-20:** it is non-deterministic and expensive per PR, which still holds.
  What does NOT hold is the rest of the original sentence — "invoking it manually
  is demonstrably working". Within a day, three consecutive code PRs (#93, #94,
  #95) merged with the audit silently skipped, each green, each putting a defect
  on `main` that the audit found afterwards, including a client-facing fabricated
  gap. A deterministic merge check now requires RECORDED audit evidence on any
  code PR (`scripts/check_audit_evidence.py`), which closes the silent-skip
  failure mode without W8b's cost. Whether W8b itself moves up is open — but it
  must not be re-deferred on the manual-process-works argument, which is the
  argument that failed. See D-051.

**W8a is two tiers, and the catch rates are stated because overstating them
would itself be the #72 pattern one level up:**

| Tier | Mechanism | Measured against today's suite | Catches |
| --- | --- | --- | --- |
| 1 | Static: private CONSTANT imports from the module under test; containment assertions whose needle carries no literal text | **5 + 2 real hits** — but the first implementation flagged 41 + 38, and narrowing to the measured shape is what made it usable | ~3–4 of the 9 |
| 2 | Mutation sweep — the automation of red-on-revert. Purpose-built, because `DropKeyword` is what catches instance 9 and mutmut has no such operator | Every mutant costs a full test run, so nightly over changed files, never a PR gate | the class |

Tier 1 cannot see instance 2 (setup performs the step under test) or instance 9
(a deletable keyword argument) — neither has a static signature. **Tier 2 runs
nightly or on a label, not as a blocking gate:** a non-blocking mechanism that
runs beats a blocking one that gets disabled.

**Why it moves up rather than sitting at the end.** Every remaining item — W3,
W2, W1 Risk, W1 ATT&CK, W6 — ships new tests. Landing this first means five
workstreams get the guarantee as they are written; landing it last means
retroactively auditing five workstreams' worth of tests. The argument is about
sequencing, not severity. It does not make a service usable for a client
engagement, so it is item **2a** rather than item 1 — real, ordered, and not
pretending to be user-facing.

### #84 is taken as part of W1 Risk, not sequenced after it

`_gather_findings` (`routes/risk.py:171-202`) builds the finding set **fed into
`risk_synthesize`** — the job W1's Risk step exists to instrument. This is not an
adjacent defect in a shared file; it sets the **input population** of the job
whose output W1 Risk accounts for, so building the accounting first means every
fixture encodes the wrong population and then has to be rebuilt.

It is also worse than #84 originally stated, and the severity belongs here
rather than only in the issue. ZT falls back to a literal (`else 3`) but at
least honours a stored per-capability target; **CSF has no per-row target at
all**, so `maturity_tier < 3` ignores the client's tier unconditionally.

**For a tier-4 client this is total silent omission, not a miscount.** Every
subcategory sitting at tier 3 is a real gap that generates **zero** risk
findings — the Risk Register does not under-count them, it does not mention them.
Nothing on any surface indicates the omission. Whoever scopes W1 Risk should
treat #84 as "the Risk Register is silent about a class of real risk for most
clients", not as an off-by-one in a target comparison; the two justify very
different amounts of care, and the second reading is the one that gets deferred.

### Why the chain is worth a second session in parallel

Items 4 and 5 are ~3–4.5 sessions; item 7 is sized separately in the table
above and no longer fits this grouping. Everything else combined is ~2–3. The
chain touches `attack.py`, `tech_debt.py` and `citations.py`; the parallel track
touches `risk.py`, `csf.py` and the web dashboards. File contention is low, and
the two decisions the chain was waiting on are now made.

### Live-AI verification — DONE 2026-08-19, and what it does NOT claim

The AI layer has now run against a real model.
`apps/api/tests/live/test_live_accounting.py` (opt-in, `pytest -m live`,
self-skips without a key) exercises the accounting loop through the real route
in three labelled tiers, because "verified live" would otherwise blur three
different claims:

- **Tier A — natural.** A real Anthropic call through `POST /zt/.../run-ai`:
  `received=74 applied=74 dropped={}`, invariant held. Every prior live test
  called `run_job` **directly**, so the accounting loop had never seen a real
  response — that was the actual gap. Worth recording separately: the real model
  produced **no drift at all**, so no drop reason occurs naturally on this
  prompt.
- **Tier B — corrupt-after-live.** The real provider is called (real cost,
  latency, egress, redaction) and the returned body is mutated before parsing.
  Covers `entry_shape`, `unknown_key`, `unknown_field`, `unparseable`,
  `out_of_range`, `superseded`, `locked`, and the
  `parse_json_object_with_list` 502.
- **Tier C — impossible live.** `protected` can NEVER be observed against a real
  provider: `protected_keys()` returns an empty set when `is_fixture` is false,
  by construction. Permanently fixture-only in ZT and CSF alike, and asserted as
  such rather than carried as an open item forever.

**What this does NOT claim.** Tier B proves OUR HANDLING against a real response
body. It does not prove a real model emits these faults at any rate. Tier A is
the only evidence here about real model behaviour, and it says: none observed on
this prompt, in this run.

Separately, `scripts.smoke_live_ai` confirmed the redaction seam against live
output — `{'email': 2, 'name': 2, 'client_org': 2}` stripped before egress, with
a completed `llm_calls` row carrying real token counts.

**Mode discipline, decided rather than inherited:** fixture is the resting state;
live is opt-in per run. `s6` and `s7` perform Run-AI and assert
fixture-deterministic outcomes, so an ambient-live e2e run would cost real tokens
and probably fail. `.env` is back on `fixture`; the key stays for opt-in runs.

**The lens outlives the milestone.** Fixtures echo the parser's own keys back by
construction, which is why a green fixture suite proves nothing about a drop, a
shape error, or a drift — the #72 pattern. The #73/#75/#79 audit found two more
instances of it (2026-08-20) in tests written the same day by someone who had
just written the rule down, which is the case for mechanising the sweep (W8)
rather than trusting anyone to remember it.


### Branch protection: configured 2026-08-20, verified 2026-08-21

**Resolved.** This section previously read "`main` has NO branch protection —
zero rules, not even force-push blocking", and stayed that way after the setting
was actually made. Re-checked against the GitHub API
(`gh api repos/.../branches/main/protection`) rather than from memory:

- **Seven required status checks** as of a re-read on 2026-08-25: Python (ruff +
  black + pytest + bandit), Web (prettier + eslint + typecheck + build), E2E
  (Playwright smoke suite), Demo (hosted-demo reset + journey spec), Secret scan
  (gitleaks), **"Adversarial audit recorded"** — the condition D-054 said it was
  waiting on — and **"No accidental issue closes"**, added with PR #113 after
  this list was first written. The list said six until 2026-08-25; a
  point-in-time API read goes stale the next time protection changes, so it
  carries the date it was taken.
- Force-pushes **blocked**. Branch deletion **blocked**.

**What that actually binds — stated precisely, because the short version is
wrong.** An earlier draft of this section said "the §14 gate now blocks" and "a
red suite can no longer merge". Both are overstatements, and an adversarial
audit caught them contradicting the bullets directly below them:

- Required checks bind **a non-admin merging via a pull request**. This repo has
  no such person today.
- `enforce_admins` is **false** — both developers are admins and bypass every
  check above.
- **A pull request is not required** to push to `main`, and
  `.github/workflows/audit-gate.yml` triggers on `pull_request` only. A commit
  pushed straight to `main` therefore produces no "Adversarial audit recorded"
  check run **at all** — there is nothing to require. This is the largest
  remaining gap, and it is what makes the two sentences above false rather than
  merely optimistic.

So: the gate is a guardrail on the PR path, not a wall around `main`.

**Also open, and listed rather than left implied:**

- `required_conversation_resolution` is **not set** — the most relevant omission
  here, given §14 is about audit findings not being silently dropped: an
  unresolved review thread does not block a merge.
- `strict` is **false**, so a branch need not be up to date with `main` before
  merging — two PRs that are individually green can still break `main` together.
- Even once a PR is required, `required_approving_review_count`,
  `require_last_push_approval` and `dismiss_stale_reviews` are all unset, so a
  solo author still self-merges and a post-approval push is unreviewed.
  "Require a PR" is roughly half the fix, not the whole of it.
- `required_signatures` is **not set**. Defensible for now; not invisible for a
  product targeting FedRAMP Moderate/High.
- **Tags are not protected at all**, and protection covers `main` only — a
  release tag can be moved.
- `restrictions` (who may push) is org-repo-only, so on a personal repo it is
  **unavailable** rather than unset. "We cannot" and "we chose not to" are
  different facts and this is the first.

**Caveat on the verification itself.** `gh api .../branches/main/protection`
reads **classic** branch protection only. It neither shows nor reconciles
repository **rulesets**, which can add or — via bypass actors — subtract
enforcement independently. The read-back below is necessary evidence, not
sufficient; a full answer needs `gh api repos/.../rulesets` as well.

A GitHub settings change no file in this repo can make or verify, which is why
the state is recorded here with the command that reads it back:

```
gh api repos/gene-png/080426SHIELD/branches/main/protection
```

One nuance the check names hide: `pip-audit` and `pnpm audit` both run with
`continue-on-error: true`, so a vulnerable dependency never reddens the Python
or Web check.

### Recently landed (context for the above)

- **W1 CSF** (PR #54, D-045) and **W1 ZT** (PR #66, D-047) — every AI suggestion
  applied or itemized. ZT took five adversarial rounds.
- **W4** (PR #58, D-046) — release assigns RELEASED to the parent. Unblocked W5.
- **Shape guards + CSF provenance** (PR #78, D-048) — all four suggestion jobs
  refuse a wrong-shaped list; offline runs no longer overwrite hand-typed CSF
  scores.
- **CSF client dashboard** (PR #80) — the last assessment service without one.
  Ships reading the client's intake target, which is why #79 exists and is first
  in the queue.
- **The §14 audit gate** (PR #98, **D-054**) — a deterministic merge check
  requiring recorded audit evidence on any code PR. Built after the gate was
  silently skipped three times running; its own audit found eight defects in it. <!-- counted: historical -->
  **Registered as a required status check** on `main` (2026-08-20, verified
  2026-08-21), which binds a non-admin merging via a PR and nothing else — see
  the branch-protection section above for what that does and does not cover.
  D-054 carries a dated correction pointing here, following the same in-entry
  convention D-045 and D-051 already use.

  **Owed, and tracked rather than done here:** the gate's own source
  (`check_audit_evidence.py`, `audit-gate.yml`) still tells its reader it "only
  REPORTS", and points at D-051 instead of D-054. Both are now false and both
  are more authoritative than this file for anyone opening the gate — #108.
  Its `docs/` exemption is also a whole-subtree carve-out that exempts §14's own
  definition — #106. And a body wrapped in an HTML comment satisfies it while
  rendering blank — #107.
- **Two retro-audit fixes** — **#96**, the W3 snapshot silently NARROWING the
  ATT&CK allow-list (client-facing fabricated gaps, live on main for ~1h), and
  **#97**, the mutation sweep mutating the wrong node on chained calls and
  scoring every mutant "killed" when the suite never ran.
- **Live-AI verification** (PR #82) — a working key was installed 2026-08-19 and
  all five purposes ran against a real provider with redaction confirmed. The
  drop paths, which fixture mode structurally cannot reach, are now exercised by
  a corrupting-provider live test. Resting mode is back to `fixture`; live is
  opt-in per run.

### Deferred, and NOT part of MVP — listed so they are not silently dropped

| Item | Status | Note |
| --- | --- | --- |
| **W0 freeze** | Open decision | Unblocked by W4, but needs Part 3 reopen scoped for CSF (that is W5). D-046 is explicit the W4 lock is PARTIAL |
| **W5 — reopen ×4 + release-staleness guard** | Not started | Unblocked by W4. **#59 is in scope for it** |
| **W7 — watermarking** | Not started | Gated on W5 |
| **W8b — adversarial reviewer as a CI job** | Deferred; **reason corrected 2026-08-20** | Agent file landed (PR #36); the CI job was never built. Still non-deterministic and expensive per PR. But "invoking it manually is demonstrably working" was FALSE within a day — #93/#94/#95 all merged with the audit silently skipped. A deterministic merge check now requires recorded audit evidence (`scripts/check_audit_evidence.py`); do not re-defer W8b on the manual-process argument. See D-051. **W8a (#72) split out and moved into the path above** |
| **#67 recurrence risk** | Fixed for CSF (PR #78) | — |
| Production runway | Unscheduled | See the section below; still gated on cloud/account decisions |

### Open issues by theme (as of 2026-08-19)

- **Export correctness:** #73, #75, #79 — item 1, **in review**. Two more filed
  out of its audit: **#84** (`risk.py` compares against a hardcoded target, so
  client-facing risk findings use a gap set no other surface agrees with) and
  **#85** (self-assessment submit accepts a target of 1 where intake enforces
  `>= 2` — inert until the trio made stored targets load-bearing)
- **AI ledger:** #47, #52, #53 — `llm_calls` says COMPLETED for rejected calls,
  is flushed-not-committed, and marks unbillable calls charged
- **Silent discard:** #46, #60 — wrong top-level key, CSF's unread
  `executive_summary`. **#77 closed (D-052)**: every registered job now carries a
  top-level shape guard, which is a sentence that could not be written before
- **Accessibility:** #69 — live regions mounted with their text, so failures
  announce and successes never do
- **Dev loop:** #65 — `seed_demo.py` is all-or-nothing, so a drifted dev DB
  cannot be repaired by re-seeding
- **Policy, needs a human:** #57 (client read of a released ATT&CK assessment),
  #62 (`ServiceStatus.RELEASED`), **#87 — DECIDED 2026-08-20 (D-050): the
  contracted target. Required follow-up #89 (UI: the selector is
  exploration-only, Finalize must surface the divergence, **and the test pinning
  D-050 lands in the same PR** — an unpinned decision reverses the first time
  someone "fixes" the mismatch by wiring the selector into finalize, and no
  current test would catch it). #90 is the amendment path: a re-scope IS
  reachable today by cutting a new assessment cycle, but that discards all
  87/106 answers and needs the client to act, so **build a consultant-side amend
  route AND an approval-time target snapshot together** — the snapshot composes
  with W3 (item 4), and without it an amend route would retroactively change what
  a released deliverable claims. #85 sits on the client write path that stays
  reachable every cycle, so it is load-bearing rather than narrow)**

## Sprint 1 — Smoke-test automation sweep + defect burn-down (COMPLETE 2026-07-03)

Goal: every automatable section of SMOKE_TEST.md (§0–§9, §11–§13, §15) has a
passing Playwright spec; defects found so far are fixed. Branch:
`qa/smoke-sweep-sprint-1`. Detail: `SPRINT_1.md`. Queue: `.claude/sprint-queue.json`.

Known defects going in (from the 2026-07-02 interactive session):
1. Home-page marketing copy advertises "reviewer audit walk" (reviewer role was
   removed in A3) and names the fourth service "Attack Surface Mapping" instead
   of MITRE ATT&CK Coverage Mapping.
2. ~~Sign-up helper copy describes v1 behavior ("first registrant becomes the
   Primary POC") instead of B1 (first user bootstraps admin; others need an
   approved domain).~~ **RESOLVED (D-034):** `/sign-up` copy now describes open
   self-serve registration with automatic org assignment.
3. ~~Seed data creates the Atlas client but approves no email domain, so
   self-registration on a fresh stack is impossible until an admin adds one.~~
   **RESOLVED (D-034):** self-registration is now open and auto-provisions the
   tenant, so a fresh stack needs no admin domain approval to sign up.
4. Duplicate-email registration surfaces a raw "Request validation failed."
5. No custom `not-found.tsx`: bad URLs render the bare Next.js 404 (dead end,
   violates the §12 no-dead-ends rule).
6. Doc drift: README describes a worker service (removed in F) and an e2e
   harness (directory is empty); BUILD_REPORT.md / CHANGELOG.md stuck at Phase 2.
   (Fixed already: seed_demo.py crash on dropped A1 column — parked on
   `fix/seed-demo-a1-drift` awaiting PR access.)

## Sprint 2 — Findings burn-down + CI hardening (PLANNED 2026-07-03, not launched)

Goal: fix everything Sprint 1's specs surfaced; wire the e2e suite and runtime
axe into GitHub CI; import IG Core/Supporting cross-reference metadata so CSF
roll-up Rules 2/5 and `is_core` stop using safe defaults; refresh stale docs
(BUILD_REPORT, CHANGELOG; README was fixed in Sprint 1 T10). Detail:
`SPRINT_2.md` (11 tasks T0-T10). Queue staged at
`.claude/sprint-queue.sprint-2.json` — see the SPRINT_2.md launch checklist
(branch creation, queue swap, demo-DB wipe warning) before invoking
`/loop-sprint-cron`.

## Sprint 3 — Audit correctness & honesty (COMPLETE 2026-07-09, PR #26)

(The "production runway" sprint originally sketched here was re-scoped; infra
remains gated on David — see the needs-David track.) Actual Sprint 3 burned
down the 2026-07-08 deep repo audit: CSF live-mode Run-AI schema align, real
forced-reauth + refresh rotation, Redis rate limiting, §15.5 export
filenames, `llm_calls` tenant attribution, docs truth pass. Detail:
`SPRINT_3.md`.

## Sprint 4 — Framework majors + multi-provider LLM (COMPLETE 2026-07-10, PR #28)

The D-018 majors bundle (Next 15 / React 19 / Tailwind 4 / ESLint 9 flat /
Node 22; ESLint 10 deferred upstream) executed one major per commit to
audit-zero, plus OpenAI + Gemini adapters behind the redacting egress seam
(D-024). Detail: `SPRINT_4.md`.

## Sprint 5 — Client value loop (PLANNED 2026-07-10, not launched)

Goal: the client-facing value surfaces — deliverable release-to-client flow
(D-025), `/documents` (§6.7), `/home` dashboard (§6.4) + value-loop card
(§2.5), CSF POA&M step (spec step 10), redaction preview gate, `/admin/audit`
viewer, vitest harness + react-hooks v6 adoption. Detail: `SPRINT_5.md`.
Queue staged at `.claude/sprint-queue.sprint-5.json` — see the SPRINT_5.md
launch checklist before invoking `/loop-sprint-cron`.

## Production runway (unscheduled — gated on David)

`infra/terraform` skeleton for AWS GovCloud / Azure Government (**blocked on
David: account/region/network decisions**); MFA + email-verify feature-flag
enablement (D-020); production deploy runbook; DR drills.

## Needs-David track (not in any sprint queue)

- SMOKE_TEST §10: eyeball the generated CSF/Risk Register PDF/Word/XLSX files
  (Sprint 1 generates and collects them; David judges "looks right").
- SMOKE_TEST §14: one live-AI run (requires `ANTHROPIC_API_KEY` +
  `SHIELD_LLM_MODE=live` in `.env`).
- Push `fix/seed-demo-a1-drift` + open PR once Gene grants collaborator access;
  same for the Sprint 1 branch.
- Sprint 3 infra decisions (cloud, account, region, network).
