# Gene's Context: 080426SHIELD

## Pick up here

**PR #133 is merged.** Item 7's backend half is on `main` — all 7 checks green. Nothing is mid-edit; the working tree is clean and everything is pushed.

The three things to do, in order:

1. **Start #130** — the highest-value open bug, unblocked, and the one most likely to be invisible to a UI-focused pre-launch pass.
2. **Item 7 part 2** — the `/ai-inputs` endpoint + `AttackAiInputsPanel`.
3. Then items 6, 8, 9.

**Last updated:** 2026-08-23 (item 7 backend merged as PR #133; adversarial reviewer run on real feature work for the first time and it overturned the branch's central claim; three new mvp-blocking issues filed — #130, #131, #132)

This file is owner-write-only. **This round it was written by the agent at Gene's explicit request** ("give me instructions so we can pick back up"), which is an exception rather than a new default. It also merges a relay session's update (`88983b2`) that landed on `main` mid-round; that content is preserved below rather than overwritten. **This file lives in the repo, not on any one machine; a local computer restart does not affect it.**

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

## Open mvp-blocking issues (13)

`#132 #131 #130` (new this round) · `#126 #125 #124 #123` (dashboards) · `#122 #121` (Risk, item 6) · `#115 #114 #109` · `#46`

## Open decisions: NOT to be reconstructed from memory

**New this round:** whether #130 gets pulled ahead of item 7 part 2 (agent's recommendation: yes — it corrupts every AI input platform-wide and fails quietly, which is exactly what a UI-focused pre-launch pass will not catch). Whether #131's fix needs provenance carried through `pairs` (approved vs live) rather than reconstructed from the tuple. Whether the "searched for: `<shape>`" line gets enforced or stays transparency-only (see above).

**Still open, unchanged:** whether #111 (admin-console N+1) gets pulled ahead. Whether the stale-cross-reference CI trigger gets a tracking issue now or waits until filed. Path-scoped branch-protection exemption for `context/gene.md`, not yet requested. What "addressable" coverage means for #102's exclusion of `pending_review`. Local-device mirror of this file. #90's build, #89's pin test, #92's contract-test fix. #57, `ServiceStatus.RELEASED` (#62), W0's freeze shape. Whether to parallelize item 6. Whether #84 gets the `mvp-blocking` label. First real unattended cron run (the Monday after 2026-08-22), worth confirming it actually fired. #106/#107 root fixes still parked behind "worked around, issue stays open".

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
