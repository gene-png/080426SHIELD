# 2026-09-23: Release dates read the same day for every reader (UTC)

Branch `fix/timezone-utc`, base `f231b0e`.

## What was wrong

The client dashboards' "Released …" badge formatted an instant in the
VIEWER's zone. A release at 02:00 UTC read as the day before for anyone west
of UTC, so one release read as different days to different readers, and as a
different day from the UTC the API stores. No `Intl.DateTimeFormat` in
`apps/web/src` named a zone.

It was two copies of the same defect. The other dashboards use `DashShell`'s badge.
`AttackDashboard.tsx` carried a private badge and formatter. Pinning the shared
one alone fixes those, leaves ATT&CK wrong, and re-tests clean on the
dashboard the report came from.

No exporter prints the release date. The one date an export stamps, the CSF
playbook's, is already UTC.

## What changed

- **`dashboards/shared.tsx`**: the badge's formatter is pinned to
  `timeZone: "UTC"`. `DashShell` takes an optional `footer`, so ATT&CK keeps
  its own wording.
- **`AttackDashboard.tsx`**: its private formatter and badge are gone, and it
  renders inside `DashShell` like the others.
- **The twins**: `DeliverablesTable`, `IntakeOrgIndex`, `HomeDashboard` and
  `ResultsList` format the same instants. Three of them show `released_at`;
  `IntakeOrgIndex` shows `intake_completed_at`. Each is pinned.
- **Their twins in turn.** Pinning the admin table alone made one release
  read as two days to one consultant. The admin deliverable cards and the
  intake screens show the same `released_at`, `finalized_at` and
  `intake_completed_at` through `toLocaleString`, in the viewer's zone. Round
  1 of review caught this. Those sites now go through
  `lib/dates.ts::formatInstantUtc`, which is UTC and names the zone, so every
  surface showing one of those instants agrees:
  - the four cards (`DeliverableCard` and its CSF, ZT and ATT&CK siblings);
  - `IntakeQueue`, `IntakeSubmitted` and `Step6Review`.
- **The gate**: `apps/web/eslint/intl-timezone.js`, installed by
  `eslint.config.js` for product code, refuses any `Intl.DateTimeFormat`, with
  or without `new`, whose arguments carry no `timeZone` in an object literal.
  It fails closed on options it cannot see into. Tests are exempt, because they
  read the ambient zone on purpose. On its first run it found exactly the four
  twins above.

## Proof

The tests set `TZ` before importing the module, because the formatter is built
at import, and they assert that the zone took. The runner's own zone is UTC,
where a pinned and an unpinned formatter print the same day.

| mutation | goes red |
| --- | --- |
| the shared formatter unpinned | both `formatDate` tests (west and east of UTC) and ATT&CK's badge test |
| ATT&CK back on its own badge | ATT&CK's badge test |
| the rule unwired from `eslint.config.js` | the wiring test, which lints through the real config |

## Residual

`toLocaleString` / `toLocaleDateString` / `toLocaleTimeString` on a `Date` also
use the viewer's zone, and a syntax rule cannot tell a date from a price
there. Filed as #507. What remains after this branch: request times, message
and inbox times, the audit log, and a capability table's date column. These
are times where the viewer's own clock is arguably the right answer, which is
a product decision.

The lint rule matches the literal spellings every product site uses, and its
header lists the spellings it cannot see.
`lib/dates.ts::formatDateOnly` is correct as it is: it builds calendar dates at
local midnight and formats them locally.
