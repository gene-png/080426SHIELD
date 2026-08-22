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

_Added 2026-08-19, current as of 2026-08-20. **This section is maintained, not archival.** When an item
lands, change its status here in the same PR that lands it — the same rule
`CONTEXT.md` follows. A status line that is wrong is worse than none, because
this is the document someone reads to decide what to work on._

**MVP means:** all five services usable for real client engagements, producing
correct documents, with the AI layer working end to end. Not the seeded demo —
fixture mode already demos all five.

### Order, status, and what blocks what

| # | Item | Status | Blocked by | Rough size |
| --- | --- | --- | --- | --- |
| 0 | **Live-AI verification (#51)** | **DONE** (2026-08-19) | — | — |
| 1 | **Export-target trio — #73 + #75 + #79** | **DONE** (PR #86, D-049, merged 2026-08-20) | — | — |
| 2 | **CSF client dashboard** | **DONE** (PR #80, merged 2026-08-19) | — | — |
| 2a | **W8a — the #72 sweep (tests that cannot fail)** | **DONE** (PR #93, D-051, merged 2026-08-20) | — | — |
| 3a | **Export/persistence audit — Tech Debt (+ #77)** | **DONE** (PR #94, D-052, merged 2026-08-20) | — | — |
| 3b | **Export/persistence audit — ATT&CK** | Not started | **item 5a** — same files, and the audit wants the post-#102 shape (the three renderers and `finalize` all changed) | 0.5 session + unknown fixes |
| 4 | **W3 — Tech Debt approval snapshot** | **DONE** (PR #95, D-053, migration 0043, merged 2026-08-20). Regression fixed by **#96** | — | — |
| 5 | **W2 — ATT&CK resolver rewrite + tri-state** | **DONE** (PR #103, merged 2026-08-20). Scoped to the resolver; the two gaps it left honest rather than implied are #101 + #102, item 5a | — | — |
| 5a | **#101 + #102 — persist the flags, and stop unconfirmed support scoring** | **DONE** (PR #110, merged 2026-08-21). Migrations 0044 + 0045, `attack/pending.py`, run-AI + patch + `confirm-citations` + heatmap + finalize + all 3 exporters + admin and CLIENT surfaces, `seed_demo` (D-055, D-056). §14 audit: 6 findings, 5 fixed, 1 filed (#109). CI green — six checks incl. full E2E. The local `s2` / `s33:84` failures were **measured, not assumed**: `/admin/management` costs 1+2N requests and took 95.6s to settle at 88 clients vs 5.4s at 3; both specs pass on a re-seeded DB. Product finding tracked as #111 | — | — |
| 6 | **W1 Risk step (+ #84)** | Not started | Nothing | 1.5–2 sessions |
| 7 | **W1 ATT&CK step** | Not started — decision taken: port the `/ai-inputs` panel from #29's branch (6 new files, zero drift), rewrite the enrichment fresh against the new resolver, and re-derive #33's finding 5 rather than porting it | **item 5a** | 1 session |
| 8 | **W6 — Risk export/publish split** | Not started | Nothing | 0.5–1 session |

**Total remaining: roughly 5–9 focused sessions** (items 0 and 2 landed), plus whatever items 0 and 3
surface. Call it **two to three weeks** of concentrated work, not days — and the
W3 → W2 → W1-ATT&CK chain is over half of it.

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

**6–10 sessions ≈ 35–65 hours ≈ 7–12 working days** at 5–6 productive hours a
day. That is where "two to three weeks" comes from.

Two caveats that matter for planning:

- These are throughput numbers for an agent working with parallel subagents, not
  a human developer's rate. Do not use them to size someone else's week.
- **W2 is the estimate most likely to be wrong**, and wrong upward. It is the
  largest item, it touches scoring, and items that touch scoring in this repo
  have needed four to five adversarial rounds rather than one.

### Dependencies, stated rather than implied

```
W3 ──> W2 ──> W1 ATT&CK          (the long pole; ~4-5.5 sessions end to end)
                └─> ATT&CK export audit

#73 ─┬─> (independent)
#75 ─┤
#79 ─┘

W1 Risk ──> (independent)
W6      ──> (independent)
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
- **#29 must not merge** until W2 lands plus a clean adversarial audit.
- Items 1, 6 and 8 depend on nothing and can run in parallel with the chain.

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

Items 4, 5 and 7 are ~4–5.5 sessions; everything else combined is ~2–3. The
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

- **Six required status checks**, including **"Adversarial audit recorded"** —
  the condition D-054 said it was waiting on. The other five are Python (ruff +
  black + pytest + bandit), Web (prettier + eslint + typecheck + build), E2E
  (Playwright smoke suite), Demo (hosted-demo reset + journey spec), and Secret
  scan (gitleaks).
- Force-pushes **blocked**. Branch deletion **blocked**.

**What that actually binds — stated precisely, because the short version is
wrong.** An earlier draft of this section said "the §14 gate now blocks" and "a
red suite can no longer merge". Both are overstatements, and an adversarial
audit caught them contradicting the three bullets directly below them:

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
  silently skipped three times running; its own audit found eight defects in it.
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
