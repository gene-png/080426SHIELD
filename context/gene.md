# Gene's Context: 080426SHIELD

## PICK UP HERE - item 10 is NOT ready (2026-08-25)

**Written by the agent at Gene's explicit request before a machine restart.**
This file is owner-write-only; an agent writing it stays the exception.

### The one-line state, corrected

`main` is at `02f43d6`. Branch **`fix/redaction-boundary-item-10`** is committed
and pushed at `af069e1`. An earlier version of this file said "item 10 complete
in code". **That was wrong.** The adversarial review finished after it was
written and found **14 findings, 9 of them confirmed by running the code**,
including two cases where a fix REINTRODUCED the defect it was fixing.

**Do not open a PR until the blockers below are closed.**

### THE BLOCKERS - all nine verified in-container, not taken on reading

Repro for every one: `docker compose exec -T api python -c "from app.ai.redact import redact_for_ai as R; print(R(<string>, mode='strict'))"`

| # | Defect | Verified output |
| --- | --- | --- |
| B1 | **#135 reintroduced.** The 5-line contact lookahead fires on any IP, date or 7+ digit run, so an ordinary ZT note is truncated and the ledger records a successful redaction. | `Flat segmentation.
Best
practice per CISA ZTMM.
Host 10.20.30.40 bridges both.` -> everything after line 1 deleted, `{'signature_block': 1}` |
| B2 | **#140 reintroduced.** 3-5 short numbers on one line, 7-15 digits total, become a phone. | `Ports 22 80 443 3389 8080 are open.` -> `Ports [PHONE] are open.`; also `08-25-2026` and `2024 2025 2026` |
| B3 | `_CITY_STATE_ZIP` eats `<Word> ID <5 digits>` - `ID` is Idaho and the rule is IGNORECASE. | `Nessus Plugin ID 19506 remains open.` -> `[ADDRESS] remains open.` |
| B4 | `_STREET_PAT` eats `<number-or-numword> <word> drive/way`. | `There is one possible way to remediate.` -> `There is [ADDRESS] to remediate.`; `Replaced the 16 TB drive.` -> `Replaced the [ADDRESS].` |
| B5 | **Real phone formats leak.** The required separator excludes both machine formats; the OLD rule caught both. | `+15551234567` and `5551234567` -> unchanged, `{}` |
| B6 | A sign-off with opener and name on ONE line is never cut. | `Thanks, Dana Whitfield` -> name and title leak |
| B7 | `_RE_CAGE` eats ATT&CK IDs - `and` is a connector and the value test is "5 alnum with a digit". | `CAGE and T1078` -> `[CAGE]`; also across a newline |
| B8 | `MS` is a 25th facility keyword, NOT on Pub 28, with no table row. The completeness test only walks table -> pattern, never pattern -> table. | `We use MS 365.` -> `We use [ADDRESS].` |
| B9 | `Business Unit 4 reported an outage.` -> `Business [ADDRESS] reported...`. #139 invented a terminal guard and applied it to the facility branch only, not to its twin. | confirmed |

**The common cause is one thing: every LEAVE table was enumerated against the
FIRST version of its rule and never re-derived after the rule changed.** The
phone LEAVE rows pass for reasons unrelated to the class they name (`Ports 30000
40000` only passes because 5-digit groups exceed `\d{1,4}`; the bullet list only
because the separators are newlines). That is CLAUDE.md's "caught by the round
AFTER the round that added them", and it is the thing to fix structurally rather
than case by case.

### Also outstanding, lower severity

- **`check_separator_classes.py` collapses exit 2 into exit 1.** `check()` returns
  2 on a tokenize failure and `main()` never reads it - the gate that cites D-051
  does not meet it. One-line fix. Its `_HSPACE` exemption is also line-scoped, so
  `_PHONE_SEP = r"(?:" + _HSPACE + r"|[ .-])"` would pass silently.
- **`docs/security.md` claims the signature cut length is recorded.** It is not -
  `removed_chars` is computed and `del`eted. Either restore it somewhere or
  correct the doc. It also still lists #138/#139/#144 as Open.
- **`redact.py:82-88` says `_RE_PHONE`/`_RE_CAGE` no longer contain `\s`.**
  `_CAGE_SEP`, `Mail\s+Stop` and `_RE_CONTACT_HINT` all still do, and D-058 still
  says so correctly - the new note contradicts the decision record.
- **Cell count:** the file says 327; the collector says **376**. Same
  parametrisation-invalidates-the-count trigger already in CLAUDE.md.
- **`smoke_live_ai.py:44`** references the removed `signature_block_chars` key.
- **Nothing renders `redaction_mode`** - `AuditViewer.tsx` has no such column, so
  #144 ships API-only. Say so in 0046 or add the column.

### What DID survive the audit

- **Migration 0046 holds.** The reviewer attacked the read paths (no aggregate,
  no filter, no coercion), hunted a second `LLMCall` insert site (only three
  exist, two are tests), and checked `String(16)` against the Literal. Upgrade and
  downgrade verified on Postgres and a full SQLite round trip, 22 columns either
  side.
- **#142 holds.** All four `is_production()` call sites converted, one test cell
  per environment per guard.
- **The `removed_counts` unit invariant test is genuinely discriminating** - it
  derives the expected total from placeholder occurrences in the output.

### Where the plan lives

`DELIVERY_PLAN.md`, section "MVP completion path". Order and remaining sizes:

| # | Item | Est | State |
| --- | --- | --- | --- |
| 9a | docs-truth pass, `docs/security.md` | 0.5-1 | **DONE**, PR #146 merged |
| 10 | the redaction boundary (#135-#140, #142, #144) | 2-3 | **code complete, unmerged** |
| 7 | W1 ATT&CK step + #131 | 1-1.5 | not started |
| 9 | correctness defects only a code review catches | 4-6 | not started |
| 6 | W1 Risk step | 4-6 | not started |
| 8 | W6 Risk export/publish split | 1-1.5 | not started |

**Total remaining 12-18 sessions, roughly 3-5 working weeks.** `check_plan_totals.py`
gates that the parts sum. Item 9 splits by SURFACE into four groups (see the plan);
item 10 is deliberately ONE PR across three surfaces because review overhead is
per-PR, not per-unit-of-work.

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

**Three new gates shipped this week**, all wired into `ci.yml`:
`check_no_control_chars.py`, `check_plan_totals.py`, `check_separator_classes.py`
— the last found a third instance of its own defect on first run.

## What is LEFT on item 10, in order

1. **Close the nine blockers above.** They are all in `app/ai/redact.py`. Do the
   structural fix, not nine patches: **re-derive every LEAVE table against the
   rule as it stands now**, because each one was written against an earlier
   version and several rows pass for reasons unrelated to the class they name.
2. **Add the missing REDACT rows.** `+15551234567` and `5551234567` leaked
   because `PHONE_REDACT` had no machine-format row. The old rule caught both --
   use it as an oracle (CLAUDE.md has the entry) before it is gone.
3. **Fix the two gate defects** (`check_separator_classes` exit 2; the line-scoped
   `_HSPACE` exemption).
4. **Correct the docs** that now misdescribe the code: `docs/security.md`'s
   "cut length is now recorded" and its Open/Fixed table, `redact.py:82-88`, the
   327-vs-376 cell count, `smoke_live_ai.py:44`.
5. **Re-run the adversarial reviewer** on the corrected tree. It has now
   overturned this branch twice; do not treat a third clean-looking state as
   final without it.
6. **Confirm a clean full `pytest -m unit`**, then open the PR. `Scope:` must
   enumerate all three surfaces.

## Standing environment facts

- Detached tests survive a killed wrapper:
  `docker compose exec -d api sh -lc '... > /tmp/x.log 2>&1; echo $? > /tmp/x.exit'`
  then poll for the exit file. **Kill stale pytest runs by PID** — `pkill` is not
  in that image and prints nothing while doing nothing.
- After ANY `apps/web` edit: `docker compose up -d --force-recreate api web`,
  then re-check `SHIELD_LLM_MODE`.
- Gates before every commit: host `prettier@3.9.5 --check`, in-container
  `ruff check --no-cache . && black --check .`, `check_test_integrity`,
  `check_no_control_chars`, `check_plan_totals`, `check_separator_classes`.
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

## Open mvp-blocking issues (20)

**Read from GitHub on 2026-08-25, not carried forward** — the previous count of
13 went stale the moment #135-#140 were filed, and a count is exactly the kind of
derived value this round has been correcting elsewhere.

`#144 #142` (this round: the ledger cannot prove the redactor ran; the redactor
can be disabled on staging) · `#140 #139 #138 #137 #136 #135` (the redaction
boundary, **item 10**) · `#132 #131` · `#126 #125 #124 #123` (dashboards) ·
`#122 #121` (Risk, **item 6**) · `#115 #114 #109` (**item 9**) · `#46`

Closed: `#130`, by PR #141.

Not `mvp-blocking` and deliberately so: **#143** (the pre-push hook's fail-open)
is tooling, off the MVP path entirely — recorded here because "unlabelled" and
"deliberately out of scope" look identical in a list.

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether #130 gets pulled ahead of item 7 part 2 (agent's recommendation: yes — it corrupts every AI input platform-wide and fails quietly, which is exactly what a UI-focused pre-launch pass will not catch). Whether #131's fix needs provenance carried through `pairs` (approved vs live) rather than reconstructed from the tuple. Whether the "searched for: `<shape>`" line gets enforced or stays transparency-only (see above).

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
