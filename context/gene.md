# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-19 (CSF dashboard API complete, 4 tests green; frontend next; PR #78 CI unchecked since push)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`main` is at `efa4a15`** (this file's last refresh). PR #78 (shape guards
+ #67) and PR #76 (CONTEXT.md correction) are both open; #78's CI hadn't been
checked since the last push as of this writing — check it, then keep going
on the dashboard regardless of the result. No file overlap between #78
(consultant Run-AI panel) and the CSF client dashboard (a separate
client-facing read surface), so there's no reason to block one on the other.

**#77 rescoped, agreed:** folds into item 4's Tech Debt export/persistence
pass rather than a fifth PR. `extract.py` will be loaded anyway during that
pass — same value-survives-to-artifact defect shape, same visit.

**CSF client dashboard — API layer complete, frontend not started.**
`GET /clients/{client_id}/csf/{service_id}/dashboard`, release-gated to
match the other four services (unreleased is a typed 404). Payload is
entirely engine-derived from `csf/scoring.py` and `csf/gap.py` — zero AI
output, stricter than #44's admin-transient carve-out, appropriate for a
client-facing surface.

Two things built in deliberately, applying what ZT's round 5 found rather
than waiting to rediscover them here:
- **Reads the client's intake target, not the engine default** — the #73
shape (ZT's exporter has computed gaps against a hardcoded 3 for the whole
life of the repo, so a stored target of 2 printed as 3). Carries
`target_tier_source` (`"client"` / `"default"`) so a fallback is a visible,
disclosed decision, not a silent one. Pinned by a test that sets target=4
and asserts the gap set moves with it.
- **Carries `total_gap_count` alongside the truncated `top_gaps`** — the #75
shape (ZT's 20-item slice with the true total nowhere on the page). A test
actually exercises truncation, not just asserts the field exists, and checks
the per-function gap counts sum to the true total.

4 tests green: released returns six functions with correct percentages,
unreleased is a typed 404, truncation disclosure holds, intake target is
honoured.

**What's left:** the frontend half — `lib/dashboards/csf.ts` +
`transform/csf/`, the `app/dashboards/csf/[serviceId]/page.tsx` route,
wiring `dashboardPathFor` to stop returning null for `nist_csf`, and an e2e
spec (`s43` is the next free number).

**Recommendation: hold the whole feature — API + frontend + e2e — for one
combined audit once complete**, not a partial API-only pass now. That
matches how CSF's and ZT's W1 steps actually got reviewed: as finished
vertical slices, not layer by layer.

## MVP prioritization — decided, do not re-litigate from memory

Gene defined MVP explicitly: **all five services, real client engagements,
correct documents, working AI end to end — not the seeded demo.**

Revised priority order (supersedes any earlier ordering in CONTEXT.md or
older handoffs):

1. **Provider live key — Gene's own action, not the agent's.** Root `.env` key
still 401s. Nothing on live-AI validation (#51) moves until this is fixed.
2. **Shape-guard + #67 — PR #78 open.** #77 folded into item 4 (see above).
3. **CSF client dashboard — API done, frontend in progress.** See above.
4. **One focused persistence/export audit pass per service** (Tech Debt —
fold in #77 here, ATT&CK, CSF combined-with-dashboard-audit above, Risk —
ZT's already done, five rounds). Escalate only if a pass finds something
serious.
5. **W3 → W2 → W1-ATT&CK on a second session, run in parallel with 1-4 —
UNBLOCKED**, both #44 and W3 resolved (see below). Sized against comparable
merged work: W3 ~1-1.5 sessions, W2 ~2-3 sessions (the big one), W1-ATT&CK
~1 session. ~4-6 sessions total, the long pole — everything else combined is
~2-3.
6. **W6 (Risk publish gate) — add to the parallel track.**

**Real cost flagged, not free:** running a second session means Gene
personally relays two independent threads instead of one.

## #44 — resolved: applied + separate tri-state count, not inside dropped

The decisive point: W1's `applied` doesn't mean "contributed to the score"
— it means "the model's suggested value was written to the record." For a
needs-review citation, section 5.1 says apply it and mark it — the citation
genuinely is written to detection_tools/prevention_tools/response_tools.
Putting it in `dropped` would assert it wasn't applied, which is false, and
the panel renders drops as losses.

ATT&CK is structurally different from CSF/ZT here: section 5.1 is explicit
that marking a citation "needs review" changes NOTHING about the score on
its own — coverage is computed from technique status, not from citations.
So for ATT&CK, `applied` never meant "contributed to the number" the way it
does for the other two services.

**Answer: count it as applied, and report the tri-state as its own count**
distinct from `citations_normalized` and `citations_rejected` — which
section 5.1 already requires regardless. The invariant
`received == applied + dropped` holds unchanged, no restatement needed.

**One implementation requirement, non-negotiable:** the panel must show the
tri-state breakdown visibly alongside `applied`, not bury it. If `applied`
is shown alone, a consultant will read it as "contributed to the score,"
which is false for the needs-review subset — that's the exact ambiguous-
single-number failure that killed the F9 counter layer.

## W3 — resolved: Option A, approval-time membership snapshot

When a CapabilityList is approved, store the exact security-scope tool-name
set as data; ATT&CK's "confirmed" reads that snapshot instead of live rows.
Chosen over Option B (confront the confirm queue) because A closes all five
doors at once, B leaves two open and breaks a deliberate workflow. A also
pays for itself: W2 needs the same snapshot for `clients.py`, which
currently reads `CapabilityItem` rows live for the client Tech Debt
dashboard — same defect, same fix.

**Before implementation, state explicitly, don't leave implicit: what
happens to the snapshot on re-approval.**

**Independent of A vs B:** the `include_excluded_row` green "Human-curated"
pill is a live bug — `confidence_pct=None` matches the human-curation path,
so a row nobody reviewed renders an affirmative false claim. Needs its own
fix regardless of which W3 option ships.

## Risk / W6 — decided

`DECISIONS.md:940` confirms the client-level Risk dashboard (no per-service
`Deliverable`) was a deliberate choice. What was never deliberated:
`POST /risk/register/export` has no approval gate and sets `finalized_at`,
which `clients.py` reports to the client as `released_at` — no review
window, unlike the other four services.

Also a live bug: `clients.py` selects the highest-version register
unconditionally then requires `finalized_at` (per-version) — clicking
Generate for v2 can 404 the client's dashboard mid-read.

**Decision: yes, Risk needs the same release guarantees as the other four
for MVP.** The v2-unpublish bug is arguably MVP-blocking on its own. W6
sized as moderate, comparable to W4, smaller than W2.

## Open decisions — NOT to be reconstructed from memory

1. **#57** — client read of a released ATT&CK assessment, and through what
view.
2. **`ServiceStatus.RELEASED`** — the never-assigned fifth status, seed-only.
In scope or deferred? (#62)
3. **W0's freeze shape** — freeze outright vs. gate on export staleness. Due
after Part 3 reopen is scoped for CSF.

## Environment — needs a human

- **The root `.env` is in live mode with a key that returns 401.** Every AI
call fails. This is Gene's own action item — nothing else unblocks it.
- Verify actual container mode from inside, never assume from the file:
`docker compose exec -T api sh -lc 'env | grep SHIELD_LLM_MODE'`.
`docker compose up -d --force-recreate <service>` silently recreates
dependent services too via `depends_on`.
- The harness has silently killed long background execs at least twice with
no established threshold — run full suites via CI or foreground slices, not
background.

## Do not merge

**PR #29** — green in CI, gated on the W2 resolver rewrite plus a clean
adversarial audit. Most likely to look mergeable after a break.
