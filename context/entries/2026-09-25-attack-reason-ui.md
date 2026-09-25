# 2026-09-25: the ATT&CK workspace edits a row's reason and narrative (#554 slice 4)

Branch `track2/attack-reason-ui`, from `main` at `2028f38`.

## What changed

- **The catalog serves `reason_codes`**: every code with the one status it may
  accompany, built from `coverage.REASON_CODES`. The web keeps no list of its
  own.
- **The technique panel shows a Reason select** for a row whose status takes
  codes (Partial, N/A). It offers only that status's codes, so N/A with
  `missing_control_category` cannot be picked; the API refuses it anyway, with
  a typed 422. "No reason given" stays selectable and sends null. Requiring a
  reason is the release gate's job (#557), and that gate is c3 of #554, not yet
  built; the label promises nothing about it (D-076). The chosen code's
  definition is shown under the select.
- **A narrative field** ("What could not be established") shows for an
  `unable_to_determine` row, or any row already carrying a narrative, and saves
  on blur. It shows a live "N / 8000" count. There is no browser cap: an
  over-long narrative is kept whole, the count says how far over, and it is not
  saved until it is shortened, so a paste is never cut. Clearing it sends
  null. The box is controlled, and resyncs from the stored value only when that
  value differs from what the box last saved. A successful save never resets
  it under the cursor; a refused save shows the stored value again.
- **The API stores a blank narrative as NULL**, since the web is not the only
  writer and the release gate will ask whether one exists. No writer can produce that status yet (D-092 Decision 5), so today
  it only ever shows a stored narrative.
- The new controls keep a visible focus ring. The existing Notes box uses
  `focus:outline-hidden`, which CLAUDE.md records as cancelling it; that is not
  copied, and not changed here.

## Not in this slice

- Widening the web's `CoverageStatus` to the two new statuses, and every status
  badge and label that must learn them: the release-readiness and reporting
  slice (c3).
- The release gate that makes a reason required (c3).
