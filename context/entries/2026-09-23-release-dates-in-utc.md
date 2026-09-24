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
  `ResultsList` format the same instants, two of them the same `released_at`.
  Each is pinned.
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
use the viewer's zone. That includes the admin deliverable cards' release
time. A syntax rule cannot tell a date from a price there. Filed as #507.
`lib/dates.ts::formatDateOnly` is correct as it is: it builds calendar dates at
local midnight and formats them locally.
