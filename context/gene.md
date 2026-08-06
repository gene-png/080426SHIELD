# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-06_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

- `feat/home-task-buckets` — **PR #15**, C3, against `main`. One commit,
  `apps/web` + one e2e spec only, nothing under `apps/api`.
  - `/home`'s "Your services" was one flat grid in arrival order, so a client
    read every phase pill to find the one that needed them — and an open
    self-assessment rendered TWICE, once as a card and again in the
    "Waiting on you" list beside it.
  - Now three buckets by **who owns the next move**: Action required /
    In progress / Results available, each service in exactly one. Empty
    buckets don't render. "Waiting on you" is gone; unread messages move into
    Action required, since they need the client but have no service card.
  - **No six-stage bar on this surface** — Master Spec §6.4 is "phase and next
    steps only" for a client. The six-stage derivation stays admin-only.
  - Phase pills deliberately UNCHANGED. The bucket says who has the next move,
    the pill says what phase the engagement is in. Also the safe call: `s31`
    routes its assertions off pill text, so rewording would have meant editing
    a test to reach green.

## Phase C is complete

C1 `#12` (admin queue stages + bulk create) → C2 `#14` (`/results` replaces
`/documents`) → C3 `#15` (this branch).

## CI debt — read this before trusting a green tick

**GitHub Actions had a major outage on 2026-08-06 from 15:22 UTC** (critical,
"workflow runs failing or delayed, queued jobs may time out"). Consequences
that outlive the outage:

1. **`main`'s HEAD `cf9cccd` (the PR #14 merge) has NO CI run.** All five jobs
   on the post-merge run sat unstarted and were killed at GitHub's 15/20-minute
   queue timeouts. `main`'s last green run is `60f59f7` (PR #13).
   - Mitigating, and worth knowing rather than re-deriving: `cf9cccd`'s tree is
     **byte-identical** to `396c776`, the branch tip that got the full local
     gate set (ruff, black, `pytest -m unit` 801/801) AND four green CI jobs
     (web, e2e, gitleaks, demo) at 15:36, before the outage bit. The gap is a
     missing checkmark, not unverified code.
2. **PR #15 has no CI run at all.** Retargeting its base from
   `feat/results-consolidation` to `main` fires `pull_request: edited`, which is
   NOT in the workflow's default trigger set — and a close/reopen didn't create
   a run either, because run creation itself was failing.

## Next steps

1. Once Actions recovers: re-run CI on `main` for `cf9cccd`, and force PR #15's
   first run with an empty commit (`synchronize` is the reliable trigger — base
   changes and reopens are not).
2. Merge PR #15, then `CONTEXT.md` + `SMOKE_TEST.md` + `DECISIONS.md` need a
   Phase C wrap-up pass. `CONTEXT.md`'s "Current state" still stops at PRs
   #11/#12 in flight.
3. Carry-overs still open from `fix/seven-issue-pass`, none urgent:
   - `s34-llm-key`'s Run-AI-guard test self-skips when the seeded ATT&CK service
     is already released. A spec that seeds its own unreleased service would make
     it unconditional. That skip is what hid the fail-open race until the first
     full-suite run — treat a conditionally-skipping spec as untested.
   - Key validation has a real provider probe for `anthropic` only; openai /
     gemini / vertex refuse with an explicit not-implemented rather than
     pretending to validate.
   - `release_deliverable()` still never flips the per-service assessment to
     `RELEASED` (D-035). Consistency cleanup.
   - SMOKE §36's live-key line still needs a human with a real key.

## Notes for Dave

- `needsClient()` in `HomeDashboard.tsx` is now the single predicate for "the
  client still owes their self-assessment" — it feeds both the Action-required
  bucket and the hero's Continue button. Those were written out separately
  before, which is exactly how the same assessment got rendered twice. Add
  readers to that function, not another inline filter.
- `dashboardPathFor()` (`apps/web/src/lib/dashboards/routes.ts`) remains the
  single source of truth for "where does this service kind go". `/home` and
  `/results` both read it.
- `/documents` permanently redirects to `/results` and **stays** — release
  emails carrying the old path are already in people's inboxes. `s17` asserts
  that promise rather than leaving it to trust.
- Two testing traps this branch hit, both worth knowing before you write
  assertions against a heading:
  - The bucket count renders INSIDE the `<h3>`, so the accessible name is
    `"Action required (2)"`, not `"Action required"`.
  - Playwright's `innerText` returns CSS-transformed text — the heading is
    styled `uppercase`, so it reads back `"ACTION REQUIRED (2)"`. Use
    `textContent`, which is what the accessible name (and a screen reader) sees.
- My box runs web on `:3000` (canonical), not the `:3001` the CONTEXT machine
  notes describe.
