# Gene's Context: 080426SHIELD

## PICK UP HERE — 2026-09-04

**Maintained by the agent since D-063; Gene owns it by review.** Every number
below carries the command that produced it, or says it was not derived.

### The one-line state

Track C's first slice is **rebased onto `origin/main` and committed at
`9941a2e`**. It closes **#125 and #126**, and deliberately **not #124** — that
deviation from the plan's "must land together" is recorded in
`DELIVERY_PLAN.md` beside the instruction it departs from, in #143's form.

**Gate status is stated per gate rather than certified in one word**, because
an earlier draft of this line said "green on every local gate" while the only
citable suite result predated two rounds of fixes — and on this branch the full
unit suite is the gate that has already caught a defect the targeted runs could
not see. Run them; do not trust this sentence:

    docker compose exec -d api sh -lc 'cd /app &&       python -m pytest -m unit tests/unit > /tmp/u.log 2>&1; echo $? > /tmp/u.exit'
    docker compose exec -T web sh -lc 'cd /app && pnpm -F web test'
    npx -y prettier@3.9.6 --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"

Note the container has no `ps`, `pgrep` or usefully-matching `pkill`: judge a
detached run by whether its log is GROWING, never by a process count, and
`docker compose restart api` is the reliable way to stop one.

### Verify the state before trusting this file

    git log --oneline -3
    git status --porcelain
    git rev-list --left-right --count origin/main...HEAD
    gh issue list --label mvp-blocking --state open --json number --jq length

Note `jq` is NOT on this box's PATH — use gh's built-in `--jq`, never a pipe.

### What happened this session

**The box was the blocker, and it is fixed.** Sign-in latency was 7.9–8.7s all
of the previous session, above what `signIn` tolerates with `retries: 0`, so
every e2e verdict was noise. A Docker Desktop restart took warm latency to
**0.52s**. The first request after a recreate is a next-dev cold compile (~15s)
and is expected — measure the second onward.

**Ordering was changed on purpose.** The hand-off put the rebase after the
suites; running them first produces a verdict on a tree the rebase then
invalidates, at 41 minutes a time. Rebased first, ran once.

**The full unit suite finally produced a citable exit code**, which is what the
previous session could not get: 7072 passed, 17 deselected, exit 0, in 41m10s,
on the rebased tree, using CI's exact invocation. CI's own Python job takes
about 14m for the same work, so this box runs it roughly 3x slower —
**CLAUDE.md's "~3 min alone" for this suite is stale and should be corrected the
next time someone edits that line.**

### The review found a regression the green suite could not

An adversarial run returned findings across code and prose. Six were BLOCKING,
and **all six were re-verified by hand before anything was acted on** — the
reviewer's calibration was good, but the rule is to check.

The one that mattered: making `analyze_gaps` refuse an out-of-range target
instead of clamping it **introduced a silent client-visible regression**. A DoD
engagement at Stage 4 — #125's own population — made the ZT workspace request a
stage the API now refuses; `refreshScoreAndGap` runs both fetches under one
`Promise.all` and swallows the rejection, so the gap card **and the score card**
rendered blank. The score card does not depend on the target at all. Nothing in
`apps/api` could have caught it, and 7072 green tests did not.

Fixed by deriving `normalizeTarget`'s selectable set from the framework's own
catalog, removing the intake option that offered the impossible stage, and
adding the server-side range check `_validate_targets` never had.

### A test fixture that made every completeness assertion meaningless

Worth reading even if nothing else here is. `test_tech_debt_dashboard.py`
uploaded a one-row CSV while the mocked extractor returned five items, so the
seeded list reported `source_rows_total=1` against `included_count=5`. Measured,
not inferred. `excluded_count` is `max(received - included, 0)`, which floors
that to 0 — so the impossible list read as "nothing was excluded" and **every
completeness assertion in the file was made about a world that cannot exist.**
That is what hid the fourth state. The fixture was corrected; the assertions
were not weakened.

### Everything fixed here, beyond the original two issues

- The ZT workspace regression above, with `normalizeTarget` exported and pinned,
  including a positive control that a real CISA 4 survives.
- The exporter still printed "Total annual cost" over a floor when an included
  item had no cost, while the new dashboard called the same list "partial" — two
  surfaces contradicting each other about one list, and the client only keeps
  the document.
- The unbalanced reconciliation no longer reads "complete" on the client card.
- `resolve_target_stage` raised `OverflowError` on an int wider than a double,
  contradicting its own never-raises docstring while claiming parity with
  `_as_number`, which carries exactly that guard. Its cases are now derived from
  the `except` arms rather than hand-listed.
- `spendSub` — the sentence the client actually reads — was exported and pinned;
  it had no test at all, and deleting its branches left everything green.
- Every `file:line` citation the branch introduced is now a quoted string. This
  took THREE passes and the failure mode was the same each time: the first
  enumerated one spelling (`file.py:NNN`) and missed nine bare `:NNN` ranges; the
  second was clean over the code but I then introduced two NEW ones while writing
  the deviation record, and one of those did not resolve to what it named. A
  sweep certified complete is worth less than the same sweep re-run after the
  next edit.
- Double-encoded UTF-8 repaired in the Tech Debt subsystem, including a
  client-visible one in `Deliverable.summary`. The first repair enumerated the
  byte signatures I could think of and missed two, in the very session that
  fixed an instance of enumerate-instead-of-derive. The repair now DERIVES: it
  round-trips each run of high characters through cp1252 and keeps the result
  only if it decodes as valid UTF-8, which is self-checking. Verified repo-wide;
  one instance remains in `routes/attack.py`, left deliberately because that
  file belongs to the ATT&CK track. A gate for the class is #192.

Each fix was verified **red-on-revert individually, with the revert proven to
have landed** before its result was read.

### The second review is the one worth reading

The reviewer ran twice. The first pass found the regression above. **The second
pass, pointed at the FIXES, found four more BLOCKING issues and two of them were
defects the fixes themselves introduced** — which is why §14 says to re-run after
any substantive change rather than once at the start.

- The fourth-state fix set `spend_completeness: "partial"`, and the renderer
  turns `partial` with no excluded rows into **"Floor - some tools lacked a
  cost"**. In that state every tool IS costed. A vague label had been converted
  into a precise, checkable falsehood on the client's card.
- The same fix withheld the completeness claim on the dashboard and NOT in the
  exporter, so the released document said "Total annual cost" for a list the
  card called partial — **the exact contradiction #126 exists to end,
  reinstated in a state nobody had enumerated.** The deferral reason on the test
  pinning it ("needs the `attribution_complete` migration") was disproved by the
  dashboard fix in the same commit: withholding a claim needs the two counts,
  which the context already carries. The migration buys naming the CAUSE.
- **#125 was not closed.** `submit_self_assessment` is a third writer of the
  stored target and was still framework-blind, while the intake comment called
  itself "the only place that can refuse it". The existing test looked like
  coverage and could not fail: it posts `target_stage: 4` at a **CISA** service,
  where 4 is real.

All four are fixed and each is pinned red-on-revert. The lesson to carry: the
first review audited the code and the second audited the repairs, and the second
found more.

### Issues filed this session

    gh issue list --state open --limit 20 --json number,title --jq '.[] | "\(.number) \(.title)"'

#188 (per-capability target exemption, latent), #189 (PATCH accepts `true` as
Stage 1 — Pydantic lax bool-to-int, measured), #190 (stage-0 comment describing
behaviour no route implements), #191 (docker-not-on-PATH kills e2e with a
message naming the check not the cause), #192 (no gate catches double-encoded
UTF-8), #193 (the "Tracked, not silently accepted" that tracked nothing), #194
(`MIN_TARGET_STAGE` duplicated as a literal in three ZT components), #195
(`patch_self_assessment_answer` accepts `target_stage` and drops it), #196 (s34's
key-panel spec cannot pass on a dev box that has a provider key).

None blocks this branch. #189 and #192 are the two worth doing soon; #196 is
the one that costs somebody an afternoon of misattribution if it is left.

### What is NOT done

- **e2e has not been run on the final tree.** Expect one pre-existing failure
  that is not this branch's: `s42-layout-overflow` at 1024px, which fails on
  `main` too (#187). Export the docker PATH first or `globalSetup` dies with a
  bare `ENOENT` (#191).
- **The adversarial reviewer has not re-run against the final state.** It ran
  against the pre-fix tree; §14 requires a re-run after substantive change, and
  this branch changed a great deal since.
- **Branch deletion is still unstarted.** All archive tags are pushed to
  `origin`, so nothing is at risk. Key it per-branch on content equivalence —
  squash-merging means the naive equivalence check is not enough.


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
