# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-17 (W1 CSF step — PR opened; issues #51, #52, #53 filed)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`feat/w1-csf-dropped-suggestions`** — W1's CSF step, PR open. Four adversarial
rounds, all six queue gates green, `s7` green in fixture mode.

`main` is at PR #48.

## What this stretch was

W1 (issue #44) closes one defect family found in ten places across the four
services:

> An AI-suggested value that fails validation is dropped silently, and the run's
> output is indistinguishable from a run where the model had nothing to say.

`docs/plans/2026-08-08-cross-service-integrity.md` is the plan of record (W0–W8).
**D-045** carries the decision, the reason vocabulary, and all four audit rounds.

Shipped for CSF: `suggestions_received` / `suggestions_applied` / itemized
`dropped[{reason, key, field, values, value}]`, with

```
received == applied + sum(d.values for d in dropped)
```

counted in **values** (one field on one row), not entries.

## Pick up here — ZT, then Risk, then ATT&CK

Order is unchanged: **CSF → ZT → Risk → ATT&CK**, ATT&CK still gated on W2.

**Budget each remaining service for the same number of audit rounds CSF took —
four.** That is not pessimism about the work converging. The defect rate did not
fall across CSF's rounds, and the reason is worth stating exactly: round 4's
find was a regression introduced by *round 3's own fix*. The audit catching the
audit's repair is the process working correctly on itself, not evidence that the
feature was in bad shape. Plan the rounds in; do not treat a clean round 2 as a
reason to stop.

**Watch for one specific shape, twice now the same.** A guard added to prevent
OVERCOUNTING has twice created a path where nothing is recorded at all:

- Round 1 → 2: `if not fields and not unknown_fields` meant one unrecognized key
  suppressed the full-row-width charge, so four of five scores fell out of both
  sides of the invariant.
- Round 3 → 4: `if recognized_values:` suppressed the row-level record entirely
  when every field was also misnamed, so an entry naming an unseeded tier
  reported a field-name curiosity and never said the tier does not exist.

Both are the same shape: **a conditional written to stop double-counting whose
false branch silently drops the record instead of emitting it under a different
reason.** When the next service's version needs one, make the false branch emit
something — a zero-value record naming the fault is honest and keeps the reader
informed; silence is not.

Two owner-set constraints on #44 still stand:

1. **`dropped[].value` is AI output.** API response may carry it; audit rows and
   logs get reason codes and counts ONLY (Master Spec §12.1). CSF pins this with
   two tests, both now carrying a model-invented field name. **ZT still owes the
   revisit of `value=repr(raw)[:120]` in `zt.py`** — pre-existing, mine.
2. **ATT&CK is gated on W2** and is not a copy of the pattern — W2's confirmed /
   needs-review / rejected must reconcile with applied-vs-dropped explicitly.
   Both readings are on #44; neither is obviously right.

## Open decisions — NOT to be reconstructed from memory

**The W0 freeze.** `context/gene.md` previously pointed at "#37" for this and
**that cross-reference is wrong** — #37 is CLOSED and is the SEV-1
writable-RELEASED issue. The freeze decision needs re-locating before it can
move. The substance is unchanged: PR #42 shipped only the audit row, the three
freeze guards were pulled because 25 of 25 approved CSF assessments have zero
dimension scores (approval precedes seeding universally), and freezing
`seed_profiles` would leave the Playbook permanently unexportable. Still due
**after Part 3 reopen is scoped for CSF**.

**W3 gates W2.** W3 = snapshot the exact tool-name set when a Tech Debt
capability list is approved, and have ATT&CK's "matched exactly, so confirmed"
read that snapshot. An APPROVED list is still editable, so narrow-confirmed is
unsound without it.

## Open issues

| # | What |
|---|---|
| #51 | W1 CSF accounting **never observed against a real provider** — fixture mode structurally cannot produce a drop |
| #52 | `charged_likely` true for auth-rejected calls that cannot have been billed (N-019 inverted, all four services) |
| #53 | `llm_calls` flushed not committed — any exception in `csf.py:1816-1902` discards a paid-for egress row; the D-031 409 reaches it **by design** |
| #46 | wrong-top-level-KEY still silent; explicitly outside W1's invariant |
| #47 | `llm_calls` records COMPLETED for a rejected response |
| #43 | `CsfDimensionScore` locked-row semantics + empty/null PATCH bodies |
| #40 | ZT workspace has no lock control |

Plus pre-existing #30–#33, and **PR #29, green and still must not merge** until
the resolver rewrite (W2) lands plus a clean adversarial audit.

## Environment note

The root `.env` was found in **live mode with a rejected Anthropic key** (401 on
every call), which was 502-ing `s7` and failing two `test_risk_dashboard` cases
that assume the fixture default. Flipped to fixture for the gate run and
**restored to `SHIELD_LLM_MODE=live` afterwards, as found.** The key still needs
replacing before any live work — and #51 is the live run W1 actually owes.

## What actually worked

Four adversarial rounds on CSF; every round found real defects in the previous
round's repairs, and **every queue gate was green each time**. The single most
useful catch was the `s7` regex: a copy change made *for precision* broke the one
end-to-end check of the feature, and it would have failed as "element(s) not
found" — the symptom `CLAUDE.md` already records being misdiagnosed as a slow
page and "fixed" with a longer timeout. Three independent reviewers found it; no
gate did.

Second most useful: the round-3 fixes were written alongside their tests rather
than test-first, so each new test was verified by **reverting the fix and
watching it fail**. Four reverts, four confirmed failures. When the order is
wrong, that is the substitute, and it is not optional.
