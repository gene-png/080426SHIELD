# Gene — current status

_Owner: Gene (gene-png). Only Gene's sessions write this file._
_Last updated: 2026-08-07_

Keep this short and current: your sessions overwrite it freely (it's yours
alone, so it never merge-conflicts). Dave's agents read it at `/pickup` to
know what you have in flight without digging through branches.

## Branch / in flight

Nothing but the docs PR carrying this file. `main` is at `a9ec90f` with PRs
**#15–#19** merged: Phase C's C3, all four Phase D items, and the `s34` fix. All
five went in with a full green CI board (Python, Web, gitleaks, E2E, Demo).

## What just landed

**The UX findings burn-down is complete.** Both review documents are closed out:
`UX findings.docx` (22 findings + the "Recommended page structure" appendix) and
the 2026-08-04 guided live run (`REPORT.md`, F-1..F-12, at
`../e2e-review-20260804-211926/`). The full finding → PR mapping is in
`CONTEXT.md` under "UX findings burn-down" — don't re-derive it, establishing it
took a pass through PR #6's change→finding table plus the migration history.

New decisions: **D-042** (`/results` canonical, `/documents` redirects forever),
**D-043** (client Home by ownership; six-stage bar stays admin-only),
**D-044** (admin Deliverables: derived status, superseded wins, read-only).

No migrations in Phase C or D.

## Next steps

1. **The one real gap is verification, not code.** ZT, CSF and MITRE have never
   completed against **live Anthropic** since PR #6 added streaming to answer
   F-3. Sprint 7's live validation was Vertex/Gemini — a different adapter with a
   different failure mode. On the default provider exactly one purpose
   (`extract.capabilities`) has ever completed live, and that predates the
   streaming change. Needs a human with a real key; SMOKE §14/§36 both want it.
2. Follow-ups recorded in the PR bodies, none urgent:
   - Cross-tenant deliverables roll-up (D-044 scopes to the active tenant).
   - A spec pinning that bulk "select all" is scoped to VISIBLE queue rows. The
     predicates are unit-tested; the scoping itself is not.
   - A spec asserting back-link **wording**. Six labels read "Back to documents"
     while landing on `/results` for a whole release, because every spec checked
     the href and none checked the words.
   - Key validation has a real provider probe for `anthropic` only; openai /
     gemini / vertex refuse with an explicit not-implemented.
   - `release_deliverable()` still never flips the per-service assessment to
     `RELEASED` (D-035).

## Notes for Dave

- **`ls e2e/smoke` before naming a spec.** I added `s37-admin-deliverables` and
  `s38-help` on top of the existing `s37-security-signoff` and
  `s38-progress-stages`. Playwright does not care, so nothing failed — the
  collision surfaced only while writing docs. Renamed to `s40`/`s41`. `s12` has a
  genuine pre-existing duplicate.
- `needsClient()` in `HomeDashboard.tsx` is the single predicate for "the client
  still owes their self-assessment" — it feeds both the Action-required bucket
  and the hero's Continue button. Those were written out separately before, which
  is exactly how the same assessment got rendered twice. Add readers to that
  function, not another inline filter.
- `lib/admin/filters.ts` holds the queue filter predicates as pure functions so
  the filtering and the empty-state message read ONE definition of "what is
  active". Add a filter there and add its label too, or the empty state will
  under-report why the list is empty.
- `SERVICE_DESCRIPTIONS` moved out of `Step1Services.tsx` into
  `lib/intake/types.ts`; `/help` and the intake picker share it now. Intake-only
  mechanics (the "clears the other picks" hint) stay in the component.
- `dashboardPathFor()` (`apps/web/src/lib/dashboards/routes.ts`) remains the
  single source of truth for "where does this service kind go". `/home` and
  `/results` both read it.
- `/documents` permanently redirects to `/results` and **stays** — release emails
  carrying the old path are already in people's inboxes. `s17` asserts that
  promise rather than leaving it to trust.
- Two heading-assertion traps, now also in `CLAUDE.md`: a count rendered inside a
  heading changes its accessible name (`"Action required (2)"`), and Playwright's
  `innerText` returns CSS-transformed text — an `uppercase` heading reads back
  SHOUTING, so use `textContent`.
- My box runs web on `:3000` (canonical), not the `:3001` the CONTEXT machine
  notes describe.
