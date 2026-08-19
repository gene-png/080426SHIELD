# Gene's Context — 080426SHIELD

**Last updated:** 2026-08-19 (Pre-launch confirmed with evidence; twin issue filed paired; dashboard PR being opened)

This file is owner-write-only. It exists so any session (mine or a relay) can pick up the real state of the project without reconstructing it from scattered chat history. Update it after every substantive decision.

## Branch / in flight

`main` is at `8533f10`. PR #76 (docs sync) is ready to merge (5/5 checks, no conflicts) but not merged — merging is Gene's call, not mine.

**The CSF dashboard PR is being opened now** — the tier decision below is settled, the twin issue is filed, this is the last step before the PR goes up. Once it's open, expect a PR number and CI status back.

## MVP prioritization order (decided)

1. W1 item 4 audit queue — CSF twin-of-#73/#75 fix, paired with ZT's fix (elevated to front of queue, see below)
2. W3 (approval-time capability-list snapshot) — gates W2
3. W2 (ATT&CK citation resolver rewrite)
4. W1 remaining: Risk, then ATT&CK (gated on W2)
5. W6 (Risk publish/release gate) — same release guarantees as the other four services; the v2-unpublish bug is arguably MVP-blocking on its own
6. CSF client dashboard — see below, now unblocked

Reasoning throughout: a surfaced number that's wrong is worse than no number (core project lesson, CONTEXT.md). Every prioritization call here optimizes against silent-wrong-output risk first, feature completeness second.

## #44 — needs_review placement (resolved, reversed from my original call)

I originally recommended `needs_review` live inside `dropped` with its own reason code. The other agent pushed back with a rigorous argument grounded in the actual W2 plan §5.1 text: `applied` in W1's accounting means "written to the record," not "contributed to the score," and for ATT&CK specifically §5.1 states "needs review" changes nothing about the score on its own. I conceded — that's correct.

**Final: needs_review counts as applied. The tri-state (applied / needs_review / dropped) is reported as a separate count, not folded into the dropped reason vocabulary.**

## W3 (resolved)

Option A — approval-time capability-list membership snapshot. Requirement before implementation: re-approval behavior must be explicitly stated (what happens if the capability list changes between snapshot and re-approval). Not yet specified by the other agent as of last update — flag this if implementation starts before it's answered.

## Risk / W6 (resolved)

Yes — Risk needs the same release guarantees as the other four services for MVP. This isn't optional polish. The v2-unpublish bug on its own is arguably MVP-blocking, independent of anything else in the queue.

## CSF client dashboard — audited, green, tier decision settled, PR next

Full audit came back clean except one finding: a three-surface tier inconsistency (the dashboard, and two other already-existing surfaces, disagree on target tier under certain conditions). Three options were on the table:

1. Fix all three surfaces in this PR
2. Regress the dashboard to match the two already-wrong surfaces
3. Ship the dashboard as built (correct), fix the other two as a fast-follow

**Decision: option 3.** Rejected option 2 outright — deliberately shipping a wrong number to match two other wrong numbers violates the core lesson above. Option 1 was rejected as scope creep on this PR; the fix belongs with the other tier-inconsistency work, not bolted onto the dashboard ship. The twin issue (CSF's version of #73/#75) is filed, paired with ZT's existing fix, at the front of the item-4 audit queue — not a generic backlog entry.

All other audit findings were fixed. 4 passing tests. Postgres-migration environment gotcha logged (see Environment notes below). Frontend was the remaining piece after the API layer landed; PR is being opened now that the tier decision and twin issue are both settled.

### Pre-launch confirmed with evidence — the urgency question is closed

I'd asked whether there are real client engagements live today, since a wrong number on a dashboard matters a lot more if someone could actually see it right now. Gene verified directly rather than asserting it:

- `docs/operations.md` draws an explicit honest split: "Running today" is only the Docker Compose dev/demo stack; "nothing in [Planned production posture] exists in this repo yet."
- `infra/terraform/` is an empty placeholder. `docs/runbooks/` is empty. Cloud account/region decisions are pending. There is no deploy job in CI.
- README states it plainly: "this is a local production-parity compose, not a cloud deploy."
- Even if someone has stood up the hosted-demo overlay, it runs seeded data where `source_request_id` is null — all three surfaces default to tier 3 and agree, so there's no live disagreement to see.

**Conclusion: first-in-queue is correct, not today-urgent.** No client can see a wrong PDF today because there's nowhere for one to log in. The twin issue stays paired with ZT's #73/#75 as planned, at the front of item 4 — sequencing doesn't change, just confirms it isn't fire-drill territory.

## Open decisions — NOT to be reconstructed from memory

- #57 — client read behavior for a released ATT&CK assessment
- `ServiceStatus.RELEASED` (#62)
- W0's freeze shape

## Environment notes (standing)

- Postgres migrations: [carried forward from prior entry — see commit `8533f10` history for exact gotcha text if needed]
- Provider live key / root `.env` key issue from earlier in the project: resolved, no longer standing.

## Do not merge

PR #29 — explicitly marked do-not-merge by Gene. Do not touch without direct instruction.

## Recurring defect shapes to watch for (CLAUDE.md)

- A test that supplies its own expected value or precondition from the thing under test cannot fail. At least 6 confirmed instances of this pattern so far (the "#72 pattern").
- A conditional written to stop double-counting whose false branch silently drops the record.
- An AI-suggested value that fails validation is dropped silently, making the run indistinguishable from a run where the model had nothing to say — this is the root defect family behind #73/#75/CSF-twin.
