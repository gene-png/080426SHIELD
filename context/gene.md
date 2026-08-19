# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-19 (CSF dashboard audited, green; tier-inconsistency finding decided — ship correct, fix exporter/home fast-follow)_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

**`main` is at `91861b6`** (this file's last refresh). PR #78 (shape guards
+ #67) and PR #76 (CONTEXT.md correction) are both open, status unchecked as
of the last relay. The CSF dashboard is fully built and audited (see below),
its own PR not yet opened pending the tier decision.

**#77 rescoped, agreed:** folds into item 4's Tech Debt export/persistence
pass rather than a fifth PR.

## CSF client dashboard — audited, green, one decision made before merge

Full feature (API + frontend + e2e) held for one combined audit, as
recommended — and the combined view is exactly what caught the finding
below; a narrower per-layer review would likely have missed it, since it
required comparing the new dashboard against two *existing* surfaces outside
the diff, not just reviewing the new code in isolation.

**Finding: three client-facing CSF surfaces disagree on gap count.** The
dashboard correctly reads the client's intake tier. The CSF exporter
(released PDF) and the `/home` value-loop card both still use a hardcoded
default tier of 3. For a client whose real target is 4: released PDF says
"no gaps at target tier 3," `/home` says "0 gaps," the dashboard says "106
gaps." Neither the seed nor `s43` can catch it — both default to tier 3, so
all three surfaces agree in test. This is the CSF twin of #73/#75, filed
against ZT only until now — not yet filed as its own issue for CSF as of
this writing.

**Decision: ship the dashboard as built, correct. Do not regress it to the
shared wrong default.** Reasoning: the exporter and `/home` card were
already wrong before this PR existed — that's a pre-existing, independent
defect, not something the dashboard introduces. Deliberately reintroducing
that same wrong number into a third, brand-new surface to make all three
match doesn't fix anything; it takes correct, tested code and breaks it to
agree with two things that are already broken, raising the wrong-number
count from two surfaces to three. On a security/compliance product, a
client walking away believing "0 gaps, met my target" when the true count is
106 is a worse outcome than a client noticing a discrepancy between two
screens and asking which one is right — the second case at least surfaces
the right question.

**Follow-up, elevated, not left in the general item-4 queue:** file the CSF
twin of #73/#75 now, and do it paired with ZT's already-queued #73/#75 fix —
same underlying bug shape (hardcoded default instead of the real intake
target), so whoever does ZT's fix will already have full context loaded.
Pull this pair to the FRONT of item 4, ahead of Tech Debt's and ATT&CK's
audit passes, since this one is confirmed and fully diagnosed, not
speculative — there's no discovery work left, only the fix.

**Open question for Gene, changes urgency, not the decision above:** are
there real client engagements live on this platform right now, where a real
client could see the "0 gaps" PDF or `/home` card before the fast-follow
lands? If yes, the exporter/home fix should happen immediately, not just
"next in queue." If this is still pre-launch, next-in-queue is fine.

**Everything else from the audit — approved, no notes:** admin preview link
added (parity with the other three services' pattern); the unscored
function no longer renders as the largest gap via a 0-gap comparison, now
carries `current_label: "Unscored"`; a success log added, logging
`target_tier` and `target_tier_source` specifically — the two values this
exact finding turns on, good foresight; `radarData` dead code and its two
fake-covering tests removed; the vacuous `total_gap_count >=` assertion
fixed to actually exercise the 0→106 tier change — **this is at least a
sixth instance of the #72 test-shape pattern** (a test that cannot fail by
construction), worth remembering as more evidence for whenever #72's
systematic sweep happens; missing cross-tenant and admin-preview tests
added; `routes.ts` made exhaustive over `Record<ServiceType,...>`, turning a
silent null into a compile error.

Gates: 7 CSF dashboard pytest, 25 across all dashboard suites, 220 web,
`s43` and `s7` both green, ruff/black/prettier/tsc/lint clean.

## Environment gotcha, new: migrations can be green in tests and absent in dev Postgres

`s7` failed twice and was nearly misread as a spec regression. Cause:
migration 0042 had never been applied to the dev Postgres container. Every
pytest fixture migrates its own throwaway SQLite from scratch, so the new
column existed in all 220+ unit tests regardless of the real dev database's
state — invisible until e2e hit a live 500 against the actual container.
Fixed by applying it; `s7` went green in 2 minutes once applied. **Lesson:
a green unit suite proves the SQLite fixtures are migrated, not that the dev
Postgres container is** — check migration state in the actual dev container
after adding one, don't infer it from test results. Same family as the
existing `.env`-mode gotcha below: verify the real running state, don't
assume it from something adjacent that looks like it should imply it.

## MVP prioritization — decided, do not re-litigate from memory

Gene defined MVP explicitly: **all five services, real client engagements,
correct documents, working AI end to end — not the seeded demo.**

Revised priority order (supersedes any earlier ordering in CONTEXT.md or
older handoffs):

1. **Provider live key — Gene's own action, not the agent's.** Root `.env` key
still 401s. Nothing on live-AI validation (#51) moves until this is fixed.
2. **Shape-guard + #67 — PR #78 open.** #77 folded into item 4.
3. **CSF client dashboard — built and audited, green.** Tier-inconsistency
finding decided above; PR pending that context landing with the team.
4. **One focused persistence/export audit pass per service — CSF/ZT's
tier-default twin pair goes FIRST** (see above, confirmed not speculative),
then Tech Debt (fold in #77), ATT&CK, Risk. ZT's own #73/#75 audit is
otherwise already done, five rounds.
5. **W3 → W2 → W1-ATT&CK on a second session, run in parallel with 1-4 —
UNBLOCKED**, both #44 and W3 resolved (see below). ~4-6 sessions total, the
long pole — everything else combined is ~2-3.
6. **W6 (Risk publish gate) — add to the parallel track.**

**Real cost flagged, not free:** running a second session means Gene
personally relays two independent threads instead of one.

## #44 — resolved: applied + separate tri-state count, not inside dropped

The decisive point: W1's `applied` doesn't mean "contributed to the score"
— it means "the model's suggested value was written to the record." For a
needs-review citation, section 5.1 says apply it and mark it. Putting it in
`dropped` would assert it wasn't applied, which is false, and the panel
renders drops as losses. ATT&CK is structurally different from CSF/ZT:
section 5.1 says "needs review" changes NOTHING about the score on its own,
so `applied` never meant "contributed to the number" there the way it does
for the other two.

**Answer: count it as applied, and report the tri-state as its own count**
distinct from `citations_normalized` and `citations_rejected`. The invariant
`received == applied + dropped` holds unchanged.

**One implementation requirement, non-negotiable:** the panel must show the
tri-state breakdown visibly alongside `applied`, not bury it, or this
recreates the F9 ambiguous-single-number failure one layer downstream.

## W3 — resolved: Option A, approval-time membership snapshot

When a CapabilityList is approved, store the exact security-scope tool-name
set as data; ATT&CK's "confirmed" reads that snapshot instead of live rows.
Chosen over Option B because A closes all five doors at once and pays for
itself — W2 needs the same snapshot for `clients.py`'s live-read problem on
the Tech Debt dashboard, same defect, same fix.

**Before implementation, state explicitly: what happens to the snapshot on
re-approval.**

**Independent of A vs B:** the `include_excluded_row` green "Human-curated"
pill is a live bug — needs its own fix regardless of which W3 option ships.

## Risk / W6 — decided

`DECISIONS.md:940`: client-level Risk dashboard was deliberate. Never
deliberated: `POST /risk/register/export` has no approval gate and sets
`finalized_at`, which `clients.py` reports as `released_at` — no review
window, unlike the other four services. Also live: `clients.py` selects the
highest-version register unconditionally then requires `finalized_at`
(per-version) — Generate for v2 can 404 the client's dashboard mid-read.

**Decision: yes, Risk needs the same release guarantees for MVP.** The
v2-unpublish bug is arguably MVP-blocking on its own.

## Open decisions — NOT to be reconstructed from memory

1. **#57** — client read of a released ATT&CK assessment, and through what
view.
2. **`ServiceStatus.RELEASED`** — never-assigned fifth status, seed-only. In
scope or deferred? (#62)
3. **W0's freeze shape** — freeze outright vs. gate on export staleness.
4. **Are there real client engagements live right now?** (see CSF dashboard
section above) — changes the urgency of the exporter/home fast-follow.

## Environment — needs a human

- **The root `.env` is in live mode with a key that returns 401.** Gene's
own action item — nothing else unblocks it.
- Verify actual container mode from inside, never assume from the file:
`docker compose exec -T api sh -lc 'env | grep SHIELD_LLM_MODE'`.
`docker compose up -d --force-recreate <service>` silently recreates
dependent services too via `depends_on`.
- After adding a migration, verify it landed in the dev Postgres container
directly — a green unit suite only proves the SQLite fixtures migrated, not
that Postgres did (see above).
- The harness has silently killed long background execs at least twice with
no established threshold — run full suites via CI or foreground slices.

## Do not merge

**PR #29** — green in CI, gated on the W2 resolver rewrite plus a clean
adversarial audit.
