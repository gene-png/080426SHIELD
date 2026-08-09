# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-09 (cross-service integrity work — PRs #34, #35, #36, #39, #42 merged; #45 in review)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`fix/ai-response-shape-not-silently-discarded`** — PR #45, closes #41. The
last thing in flight. Four CI jobs green, E2E was still running at the break;
merge it when green if it hasn't already landed.

Nothing else is on a branch. `main` is at PR #42.

## What this stretch was

The ATT&CK citation-resolver plan (#34) read as an ATT&CK problem. It isn't.
Auditing the other four services found **one defect family in ten places**:

> An AI-suggested value that fails validation is dropped silently, and the run's
> output is indistinguishable from a run where the model had nothing to say.

`docs/plans/2026-08-08-cross-service-integrity.md` (PR #35) is the plan of
record. Read it before picking anything up — the workstreams below are W0–W8
there.

**Merged:** #34 (ATT&CK plan), #35 (cross-service plan), #36
(`adversarial-reviewer.md` onto main — it is a registered `subagent_type` now,
stop inlining it), #39 (F9, ZT provenance), #42 (W0, CSF audit row).

## Pick up here

**W1 — `dropped[]` rollout. Issue #44 has the settled design; read it first.**
Order: **CSF → ZT → Risk → ATT&CK**, and #41 (PR #45) had to land first.

The design is deliberately NOT counters:

```
suggestions_received / suggestions_applied / dropped: [{reason, key, value}]
received == applied + len(dropped)
```

Itemized, because a single integer cannot state its own scope — that is what
sank the F9 counter layer. The invariant turns "did we count everything" into a
test failure instead of an audit finding.

Two owner-set constraints on #44, do not lose them:

1. **`dropped[].value` is AI output.** `models/llm_call.py` — "Counts only -
   never payload content (Master Spec §12.1)". API response may carry it; audit
   rows get reason codes and counts ONLY; logs get a bounded non-content
   identifier. NOTE: F9 already logs `value=repr(raw)[:120]` in `zt.py` — that
   was mine, it predates the rule being stated, and W1's ZT step must revisit it.
2. **ATT&CK is gated on W2 landing** and is not a copy of the pattern — W2's
   confirmed / needs-review / rejected has to reconcile with applied-vs-dropped
   explicitly, and the invariant restated either way. Both readings are written
   out on #44; neither is obviously right.

Starting point for CSF: `csf.py:1504` `data.get("scores", [])`. Note it
conflates two reasons in one `continue` (`if row is None or row.locked`) and
that `f"{tier}|{code}"` yields the literal `"None|None"` when the keys are
absent — which is why dropped entries need the verbatim key.

## Open decisions — NOT to be reconstructed from memory

**W0's freeze (#37).** PR #42 shipped only the audit row. The three freeze
guards were pulled: 25 of 25 approved CSF assessments have zero dimension
scores, so approval precedes seeding universally, and freezing `seed_profiles`
would leave the Playbook permanently unexportable. Two questions on #37 need
answering before it can move — what CSF approval governs, and whether the
Playbook track gets its own approval (same shape as Risk Register in §W6).
The recommendation is due back **after Part 3 reopen is scoped for CSF**, and it
is a choice between freezing outright and gating on export staleness. A freeze
with no recovery path is what made it a trap.

**W3 gates W2.** W3 = record the exact tool-name set at the moment a Tech Debt
capability list is approved, and have ATT&CK's "matched exactly, so confirmed"
read that snapshot. Without it, narrow-confirmed is unsound: an APPROVED list is
still editable (the guard refuses only RELEASED, which no route assigns), and
the security-classification confirm queue changes allow-list membership by
design. Do not ship W2's narrow definition against a mutable list.

## Open issues filed this stretch

| # | What |
|---|---|
| #37 | W0 freeze — open decision, see above |
| #40 | ZT workspace has no lock control; API supports it, ATT&CK/CSF ship it |
| #41 | top-level non-dict response discarded → PR #45 |
| #43 | `CsfDimensionScore` locked-row semantics + empty/null PATCH bodies |
| #44 | W1 design + the two constraints |
| #46 | wrong-top-level-KEY still silent — the Sprint 3 T0 drift, other half. Explicitly outside W1's invariant |
| #47 | `llm_calls` records COMPLETED for a rejected response |

Plus pre-existing #30–#33 (ATT&CK audit record and deferrals) and **PR #29,
green and still must not merge** until the resolver rewrite lands.

## What actually worked, and what didn't

Eleven adversarial passes across F9 and W0; **nine found real defects, six of
them in my own fixes**, including two recommendations that would have made
things worse (un-locking seeded demo data; stranding 25 assessments). Green CI
never caught any of it.

The F9 counter layer failed three consecutive passes while the provenance fix
beside it passed four — it got deleted rather than shipped. **A surfaced number
that is wrong is worse than no number, because once a banner exists its absence
reads as "nothing was dropped."** That lesson is why W1 is itemized.

Practical: three concurrent `pytest -m unit` runs starve the api container to a
crawl. Run one, detached INSIDE the container (`nohup` + a `/tmp/*.exit` file),
and poll it — a host-side wrapper gets orphaned and its exit code is the
pipeline's, not pytest's. When in doubt, let CI be the authority and say so.
