# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-19 (W1 ZT merged as PR #66, five audit rounds; MVP prioritization pass done)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**Nothing merged since ZT.** `main` is at `68ca6c9` (PR #66, W1's ZT step, five
adversarial rounds), CI green on all five checks.

**PR #76 is ready to merge** — docs-only, corrects CONTEXT.md's stale "#66 in
flight" claim, 5/5 checks green, no conflicts. Mechanical, just needs the click.

State of `main` is in **`CONTEXT.md`**, though CONTEXT.md itself is one PR
(#76) behind on the ZT merge as of this writing.

## MVP prioritization — decided this pass, do not re-litigate from memory

Gene defined MVP explicitly: **all five services, real client engagements,
correct documents, working AI end to end — not the seeded demo.** That
resolves an open question the agent asked; treat it as settled.

Revised priority order (supersedes any earlier ordering in CONTEXT.md or
older handoffs):

1. **Provider live key — Gene's own action, not the agent's.** Root `.env` key
still 401s. Nothing on live-AI validation (#51) moves until this is fixed.
2. **One small correctness PR: shape-guard `mitre_map` + `risk_synthesize`
(the #46 family), and fix #67** (CSF's offline Run-AI silently overwrites
hand-typed dimension scores — already a real incident, Identity pillar
3.00 → 1, unrecoverable). Cheap, independent, do this first.
3. **CSF client dashboard — start now, in parallel with #4, not after it.**
`dashboardPathFor` returns null for `nist_csf`; the largest service and the
one with the most AI investment has no client-facing results page at all.
That's a harder MVP gate than a wrong number.
4. **One focused persistence/export audit pass per service** (Tech Debt,
ATT&CK, CSF, Risk — ZT's already done, five rounds). Use the export lens
specifically, the one that found #73/#75 on ZT. Escalate to more rounds only
if a pass finds something serious — do NOT default to the full four/five-round
multi-lens treatment on all four remaining services, there isn't time before
MVP.
5. **W3 → W2 → W1-ATT&CK on a second session, run in parallel with 1-4, once
two decisions below are made.** Sized against comparable merged work: W3
~1-1.5 sessions, W2 ~2-3 sessions (the big one — `citations.py::resolve()`
rewrite, tri-state, `pending_review` as a fourth technique state, #29 folds in),
W1-ATT&CK ~1 session. ~4-6 sessions total, the long pole — everything else
combined is ~2-3. File contention is low (chain lives in
`attack.py`/`tech_debt.py`/`citations.py`; the other track in
`jobs.py`/`csf.py`/`risk.py`/web dashboards); the one overlap is ATT&CK's
exporter — sequence that pass after W2, not against it.
6. **W6 (Risk publish gate) — add to the parallel track.** Not originally on
the MVP list; see below for why it's now on it.

**Real cost flagged, not free:** running a second session means Gene
personally relays two independent threads instead of one. Worth it given the
sizing math, but it's on him, not a free lever.

## Risk / W6 — decided

`DECISIONS.md:940` confirms the client-level Risk dashboard (no per-service
`Deliverable`) was a deliberate choice. What was never deliberated:
`POST /risk/register/export` has no approval gate and sets `finalized_at`,
which `clients.py` reports to the client as `released_at`. An admin clicking
Export to look publishes to the client — no review window, unlike the other
four services (`s40` tests that for them). Risk is generated from batched AI
synthesis with findings dropping silently — the least-reviewed of the five
outputs is the only one with no review window.

Also a live bug, independent of the above: `clients.py` selects the
highest-version register unconditionally then requires `finalized_at`
(per-version) — clicking Generate for v2 can 404 the client's dashboard
mid-read.

**Decision: yes, Risk needs the same release guarantees as the other four for
MVP.** The v2-unpublish bug is arguably MVP-blocking on its own. W6 sized as
moderate — publish marker, gate change, `s30`, a DECISIONS.md amendment
(CLAUDE.md requires it in the same PR), and the seed. Comparable to W4,
smaller than W2.

## Open decisions — NOT to be reconstructed from memory

1. **#44's fork — leaning, not settled.** `needs_review`: inside `dropped`
with its own reason code, or a sub-count of `applied`? Leaning toward inside
`dropped`: the bucket already holds `locked`/`protected`, which are visible,
by-design, non-alarming, and render separately rather than disappearing —
`needs_review` (visible and retained, per the W2 plan section 5.1) fits that
precedent rather than breaking it. **Not formally decided in issue #44** —
check against the actual W2 implementation before treating this as settled.
2. **W3's snapshot-vs-confirm-queue choice — genuinely open, not enough
detail yet to decide.** Needs the two options spelled out from
`docs/plans/2026-08-08-attack-citation-resolver.md` before anyone commits.
Both #44's fork and this one block the second-session start.
3. **#57** — client read of a released ATT&CK assessment, and through what
view.
4. **`ServiceStatus.RELEASED`** — the never-assigned fifth status, seed-only.
In scope or deferred? (#62)
5. **W0's freeze shape** — freeze outright vs. gate on export staleness. Due
after Part 3 reopen is scoped for CSF.

## Environment — needs a human

- **The root `.env` is in live mode with a key that returns 401.** Every AI
call fails. This is Gene's own action item — nothing else unblocks it.
- Verify actual container mode from inside, never assume from the file:
`docker compose exec -T api sh -lc 'env | grep SHIELD_LLM_MODE'`.
`docker compose up -d --force-recreate <service>` silently recreates
dependent services too via `depends_on`, which can re-diverge the two from
`.env` unpredictably.
- The harness has silently killed long background execs at least twice with
no established threshold — run full suites via CI or foreground slices, not
background.

## Do not merge

**PR #29** — green in CI, gated on the W2 resolver rewrite plus a clean
adversarial audit. Most likely to look mergeable after a break.
