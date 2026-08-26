# Gene's Context: 080426SHIELD

## PICK UP HERE - item 10 is DONE; Track 3 is next (2026-08-26)

**Written by the agent at Gene's explicit request.** This file is owner-write-only;
an agent writing it stays the exception.

### The one-line state

`main` is at `fbca899`. **PR #155 merged on 2026-08-26** with all seven CI checks
green, including E2E and Demo, which had never run on the branch. Item 10 is
**DONE**. Working tree clean.

### What the previous version of this section said, and why it is worth recording

It said "item 10 is NOT ready", "**Do not open a PR until the blockers below are
closed**", listed nine blockers as live, and gave a 12-18 session total. Every
one of those was true on 2026-08-25 and false after PR #155 merged -- and the
section survived that merge unchanged, because the merge commit corrected the
issue COUNT further down the file and nobody re-read the top.

That is the same shape as the count itself, one section up: the prose an agent
reads FIRST outlived the state it described. An agent picking this file up would
have refused to open a PR on already-merged work, or re-done nine fixed
blockers. Found by the adversarial reviewer on the PR that was correcting the
count below it.

### Item 10, as it actually landed

Sized 2-3 sessions; actual ~5-6. Sixteen blockers over four review rounds
producing **9, 1, 5, 1** -- a count that did not converge monotonically, which
is what a three-round budget would have got wrong. Thirteen closed in PR #155,
three filed: #151, #152, #153.

Five of the sixteen were introduced by the fix for a DIFFERENT defect, two of
those inside the branch itself (B3 -> B12, B11 -> B16). One -- the name
dictionary destroying the word "client" for any tenant with a generic mailbox --
was **pre-existing on `main`** and found only because the reviewer was pointed at
the hint construction rather than at the rules.

Two derived corpora shipped with it and are permanent:

- `tests/unit/test_redact_real_identifiers.py` -- every shipped ATT&CK, CSF and
  ZT identifier through three contexts. Found B10 and B11.
- `scripts/leave_row_oracle.py` -- disables one narrowing guard at a time and
  reports which exemption rows still pass. Its `--check-registry` half is a CI
  gate; the rest is a required step, not a gate.

Both are budgeted into items 6 and 9, which must now be sized with the review
rounds INSIDE the number: both fix existing code, so their tables land in the
after-the-rule regime (42% of in-risk exemption rows pinning nothing, against
3.8% for tables written before their pattern).

### Next: Track 3

Item 7 part 2 (`/ai-inputs` endpoint + panel), then **#131 back to Gene before it
lands** -- fixing it changes deliverable content by definition, which the
standing merge rule in CLAUDE.md reserves for a human.

**One correction to the plan's item 7 note.** It says "port the `/ai-inputs`
panel from #29's branch (6 new files, zero drift)". `feat/attack-ai-inputs-visibility`
is now **103 commits behind main** and its `routes/attack.py` differs by
385 insertions / 626 deletions -- it predates the resolver rewrite, the D-053
snapshot, #102's withholding and #133's enrichment. The four files it adds are a
useful shape reference; the backend endpoint they call does not exist on `main`.
This is "write against the current resolver using #29 as reference", not "port",
and the 1-1.5 estimate rests on the porting assumption.

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
   Open/Fixed table, `redact.py:82-88`, `smoke_live_ai.py`. The cell count was
   REMOVED rather than corrected: it was 327, then 376, then 410, and a count in
   prose is a derived value with a second place to be wrong.
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
- Gates before every commit: host `prettier@3.9.5 --check`, in-container
  `ruff check --no-cache . && black --check .`, `check_test_integrity`,
  `check_no_control_chars`, `check_plan_totals`, `check_separator_classes`,
  `leave_row_oracle.py --check-registry`. That last one is a CI check and was
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

## Open mvp-blocking issues (14)

**Read live from GitHub on 2026-08-26, immediately after PR #155 merged.**

`#153 #152` (the two redaction leaks item 10 filed rather than fixed) · `#132
#131` · `#126 #125 #124 #123` (dashboards) · `#122 #121` (Risk, **item 6**) ·
`#115 #114 #109` (**item 9**) · `#46`

Closed since: `#130` by PR #141; `#135`-`#140`, `#142`, `#144` by PR #155.

**This heading read 20 with a paragraph underneath certifying it as freshly
read.** Both were true on 2026-08-25 and false the moment PR #155 merged --
it closed EIGHT (#135-#140, #142, #144; the ninth, #130, was PR #141's and is
listed separately above) — and the certifying paragraph went stale WITH the number it certified,
while still reading as a guarantee. That is worse than a bare stale count: a
reader checking whether the figure could be trusted found a sentence saying yes.

Fourth instance this week, and three of the four were in the files that document
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
