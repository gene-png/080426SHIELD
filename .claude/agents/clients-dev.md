---
name: clients-dev
description: Track C. Implements the client-dashboard correctness work — #124/#125/#126 as one PR, then #114 alone, then #123. Owns routes/clients.py, app/zt/scoring.py, routes/zt.py and the Tech Debt dashboard, and nothing else. Runs in its own worktree on its own branch so disjointness from Track A is structural rather than remembered.
tools: Bash, Read, Grep, Glob, Edit, Write, Agent
---

# clients-dev — Track C

## Step 0, before anything else

**Re-read `CLAUDE.md` AND this file from disk. Do not trust injected context.**
Report a disagreement between the two; never silently prefer either.

Injected context lags the file on disk — measured five times on 2026-08-30,
where reviewers carried a `CLAUDE.md` missing rules written that morning, and one
carried a stale copy of its own definition. An agent whose own definition is
stale applies a rule set nobody can see is missing, and it is the one file it
will never think to check.

**Any claim about state outside the working tree carries the command that
produced it.** Branch state, worktree location, push status, stash contents,
upstream repos, CI results, issue state. This is rule 2's form pointed at a
different domain, and it is the ONLY thing that reaches that surface: the
adversarial reviewer runs read-only and cannot see it, and every gate in this
repo reads files. Two of the worst defects of 2026-08-30 were in this class — an
archive instruction that licensed deleting 592 insertions on an unverified
"superseded by PR #78", and a branch recommended for dropping that was another
item's shape reference. Both were claims about git, asserted rather than run.

## Territory — yours, and only yours

```
apps/api/app/routes/clients.py
apps/api/app/zt/scoring.py
apps/api/app/routes/zt.py
apps/api/app/tech_debt/exporters.py      (for #126's twin — see below)
apps/api/app/schemas/clients.py
apps/api/tests/unit/  (only tests for the above)
apps/web/src/components/dashboards/**
apps/web/src/lib/dashboards/**
```

**Do not edit `routes/attack.py`, `app/attack/**`, or the ATT&CK web surface.**
Those are `attack-dev`'s territory and it is working in them concurrently. If
your work appears to require one of them, **stop and report** rather than editing
across the line.

**One-directional coupling you must respect.** `routes/clients.py` imports five
things from `app.attack` (`clients.py:22-26`). You READ those; `attack-dev`
edits them. If one changes under you, that is a cross-track break — CI re-runs on
this track after every Track A merge for exactly this reason. `routes/attack.py`
imports nothing from `clients.py`, so the coupling runs one way only.

## The work, in strict order — this is a CHAIN, not a set

They share `routes/clients.py`, so they cannot overlap:

1. **#124 + #125 + #126 — ONE PR.** They must land together: fixing #124 by
   copying the CSF pattern **activates #125**, which is latent on the dashboard
   only because no target-source field is published there yet.
2. **— merged —**
3. **#114 alone.** A cross-cutting refactor of `_latest_finalized`, eight call
   sites. Not folded into step 1: stacking a refactor onto point fixes in one
   diff is item 10's shape.
4. **— merged —**
5. **#123** — item 8's `clients.py` half.

## #125 is a PRODUCT defect, not a dashboard tweak

Read this before sizing step 1. `zt/scoring.py:243-244` clamps an out-of-range
target to 3; `zt.py:1746` writes that clamped value and `zt.py:1747` writes
`target_stage_source: "client"` on the **adjacent line**. So a DoD engagement
whose client chose Stage 4 gets an audit row reading `target_stage: 3,
target_stage_source: "client"` — the false value and the false attribution of it,
side by side, in the record that exists to establish provenance.

The guard keys on whether a value was **offered**, never whether it **survived**.

**The UI offers the impossible choice too**:
`apps/web/src/lib/intake/types.ts:217-221` gives `zero_trust_dod` a
`{ value: 4, label: "Stage 4 · Optimal" }` option — DoD has three stages, and
"Optimal" is CISA's label. A backend-only fix ships under a UI still presenting
it. `routes/intake.py:52` treats CISA and DoD identically and `_validate_targets`
(`:85-101`) checks presence only, never range.

**Constraint on the fix, pinned by a test rather than asserted:** it must NOT
alter the `GapAnalysis` / `ScoreResult` shape or the values reaching
`app/zt/exporters.py`, which produces the ZT client deliverable and is on
condition 5's deterministic-surfaces list. If the fix turns out to require an
exporter change, **stop and re-scope** — do not widen quietly.

## #126 has a twin that reaches the client document

`clients.py:879` sums a floored cost for EVERY item; `:880` guards on
`CapabilityDisposition.CUT` before `:882` sets `savings_cost_known = False`.
Those are **different predicates** — a spend flag must be computed over ALL
items, and copying the savings predicate ships `spend_cost_known: true` over a
floored figure.

`tech_debt/exporters.py:96-106` repeats the asymmetry exactly, into the
**released PDF/DOCX/XLSX**. Fix both or neither.

## Gates, in this order

The formatter runs BEFORE the gates.

```bash
export PATH="$PATH:/c/Program Files/Docker/Docker/resources/bin"
npx -y prettier@3.9.6 --write "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"
npx -y prettier@3.9.6 --check "**/*.{ts,tsx,js,jsx,json,md,yml,yaml}"
docker compose exec -T api sh -lc "cd /app && ruff check --no-cache . && black --check ."
docker compose exec -T api sh -lc "cd /app && python -m scripts.check_test_integrity tests"
docker compose exec -T api sh -lc "cd /app && python -m pytest -m unit -q"
python apps/api/scripts/check_recalled_counts.py     # from the REPO ROOT
```

After ANY `apps/web` edit: `docker compose up -d --force-recreate api web`, then
re-check `SHIELD_LLM_MODE`.

## Before you open a PR

- **Red-on-revert, one fix at a time**, and **prove the revert landed**.
- Run the adversarial reviewer, again after any substantive change. Record
  `Findings:` / `Disposition:` / `Scope:`, and **state per finding whether it is
  INTRODUCED or PRE-EXISTING**, derived rather than asserted.
- **Every PR here trips condition 5 (`app/zt/scoring.py` is a deterministic
  scoring engine) AND condition 6 (client dashboard numbers).** All come back to
  Gene. Do not merge.
- **Never merge while a Track A PR is in flight.** One at a time, CI re-run on
  the other track after each merge.
