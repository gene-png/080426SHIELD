# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-19 (PR #78 open for #2/#67, CI running; #77 filed; CSF dashboard greenlit)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`main` is at `ef73f65`** (this file's last refresh). CI is running on
PR #78, nothing else has merged.

**PR #78 open** — shape guards (`mitre_map`, `risk_synthesize`) + #67 (CSF
provenance protection, migration 0042). Correctly based on `ef73f65` after a
branching mishap (briefly forked off the docs PR instead of main; rebased,
fixed). CI running as of this writing.

**#77 filed, not yet fixed:** `tech_debt_extract` turns out to be the last AI
job without a shape guard — needs per-item coercion, not a blanket
substitution, since its parsing shape differs from the other four. Caught
because the agent went back and corrected its own claim that "every
registered job now carries a shape guard" before that line landed in a doc —
the self-correction working as intended, worth noting. **Recommend folding
#77 into item 4's Tech Debt export/persistence audit pass** rather than a
standalone PR — same code, same visit, no reason to context-switch twice.

**Green light given: start the CSF client dashboard now**, in parallel with
#78's CI and the audit queue. Don't wait for #78 to merge first — that was
the whole point of calling it a parallel track.

**PR #76** is still open, still unrelated to gene.md's own commits, won't
conflict with any of this. Still needs your click, not the agent's.

## MVP prioritization — decided, do not re-litigate from memory

Gene defined MVP explicitly: **all five services, real client engagements,
correct documents, working AI end to end — not the seeded demo.**

Revised priority order (supersedes any earlier ordering in CONTEXT.md or
older handoffs):

1. **Provider live key — Gene's own action, not the agent's.** Root `.env` key
still 401s. Nothing on live-AI validation (#51) moves until this is fixed.
2. **Shape-guard + #67 — PR #78 open, CI running.** #77 (tech_debt_extract's
guard) recommended folded into item 4 rather than shipped separately.
3. **CSF client dashboard — IN PROGRESS**, started in parallel per the
green light above. `dashboardPathFor` returns null for `nist_csf`; the
largest service and the one with the most AI investment has no client-facing
results page at all.
4. **One focused persistence/export audit pass per service** (Tech Debt —
fold in #77 here, ATT&CK, CSF, Risk — ZT's already done, five rounds). Use
the export lens specifically, the one that found #73/#75 on ZT. Escalate
only if a pass finds something serious.
5. **W3 → W2 → W1-ATT&CK on a second session, run in parallel with 1-4 —
UNBLOCKED**, both #44 and W3 resolved (see below). Sized against comparable
merged work: W3 ~1-1.5 sessions, W2 ~2-3 sessions (the big one), W1-ATT&CK
~1 session. ~4-6 sessions total, the long pole — everything else combined is
~2-3. File contention is low; the one overlap is ATT&CK's exporter —
sequence that pass after W2, not against it.
6. **W6 (Risk publish gate) — add to the parallel track.**

**Real cost flagged, not free:** running a second session means Gene
personally relays two independent threads instead of one.

## #44 — resolved: applied + separate tri-state count, not inside dropped

Reversed my earlier lean after the agent's pushback, and the pushback is
right. The decisive point: W1's `applied` doesn't mean "contributed to the
score" — it means "the model's suggested value was written to the record."
For a needs-review citation, section 5.1 says apply it and mark it — the
citation genuinely is written to detection_tools/prevention_tools/
response_tools. Putting it in `dropped` would assert it wasn't applied, which
is false, and the panel renders drops as losses.

ATT&CK is also structurally different from CSF/ZT here: section 5.1 is
explicit that marking a citation "needs review" changes NOTHING about the
score on its own — coverage is computed from technique status, not from
citations. So for ATT&CK, `applied` never meant "contributed to the number"
the way it does for the other two services.

**Answer: count it as applied, and report the tri-state as its own count**
distinct from `citations_normalized` and `citations_rejected` — which
section 5.1 already requires regardless. The invariant
`received == applied + dropped` holds unchanged, no restatement needed.

**One implementation requirement, non-negotiable:** the panel must show the
tri-state breakdown visibly alongside `applied`, not bury it. If `applied`
is shown alone, a consultant will read it as "contributed to the score,"
which is false for the needs-review subset — that's the exact ambiguous-
single-number failure that killed the F9 counter layer. Do not ship this
without the tri-state count on screen next to it.

## W3 — resolved: Option A, approval-time membership snapshot

When a CapabilityList is approved, store the exact security-scope tool-name
set as data; ATT&CK's "confirmed" reads that snapshot instead of live rows.
Chosen over Option B (confront the confirm queue) because A closes all five
doors at once, B leaves two open (patch_capability_item can still rename
tools) and breaks a deliberate workflow (security_scope.py's docstring: "the
only way out of the subset is a human agreeing with the model"). A also pays
for itself: W2 needs the same snapshot for clients.py, which currently reads
CapabilityItem rows live for the client Tech Debt dashboard, so a post-
release edit changes the client's dashboard total while the released PDF
says otherwise. Same defect, same fix.

**Before implementation, state explicitly, don't leave implicit: what
happens to the snapshot on re-approval.** Retaken fresh, diffed against the
prior snapshot, something else — pick one and write it down, the same
discipline this arc has required everywhere else.

**Independent of A vs B:** the `include_excluded_row` green "Human-curated"
pill is a live bug — it writes `confidence_pct=None`, the same value the
human-curation path writes, so a row nobody reviewed renders an affirmative
false claim. Needs its own fix regardless of which W3 option ships.

## Risk / W6 — decided

`DECISIONS.md:940` confirms the client-level Risk dashboard (no per-service
`Deliverable`) was a deliberate choice. What was never deliberated:
`POST /risk/register/export` has no approval gate and sets `finalized_at`,
which `clients.py` reports to the client as `released_at`. An admin clicking
Export to look publishes to the client — no review window, unlike the other
four services (`s40` tests that for them).

Also a live bug, independent of the above: `clients.py` selects the
highest-version register unconditionally then requires `finalized_at`
(per-version) — clicking Generate for v2 can 404 the client's dashboard
mid-read.

**Decision: yes, Risk needs the same release guarantees as the other four for
MVP.** The v2-unpublish bug is arguably MVP-blocking on its own. W6 sized as
moderate — publish marker, gate change, `s30`, a DECISIONS.md amendment, and
the seed. Comparable to W4, smaller than W2.

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
dependent services too via `depends_on`, which can re-diverge the two from
`.env` unpredictably.
- The harness has silently killed long background execs at least twice with
no established threshold — run full suites via CI or foreground slices, not
background.

## Do not merge

**PR #29** — green in CI, gated on the W2 resolver rewrite plus a clean
adversarial audit. Most likely to look mergeable after a break.
