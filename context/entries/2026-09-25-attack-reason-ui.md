# 2026-09-25: the ATT&CK workspace edits a row's reason and narrative (#554 slice 4)

Branch `track2/attack-reason-ui`, from `main` at `2028f38`.

## What changed

- **The catalog serves `reason_codes`**: every code with the one status it may
  accompany, built from `coverage.REASON_CODES`. The web keeps no list of its
  own.
- **The technique panel shows a Reason select** for a row whose status takes
  codes (Partial, N/A). It offers only that status's codes, so N/A with
  `missing_control_category` cannot be picked. The API refuses it anyway, with
  a typed 422. "No reason given (required before release)" stays selectable
  and sends null: a missing reason is a release question, not a click-time one
  (#557). The chosen code's definition is shown under the select.
- **A narrative field** ("What could not be established") shows for an
  `unable_to_determine` row, or any row already carrying a narrative, and saves
  on blur. No writer can produce that status yet (D-092 Decision 5), so today
  it only ever shows a stored narrative.
- The new controls keep a visible focus ring. The existing Notes box uses
  `focus:outline-hidden`, which CLAUDE.md records as cancelling it; that is not
  copied, and not changed here.

## Not in this slice

- Widening the web's `CoverageStatus` to the two new statuses, and every status
  badge and label that must learn them: the release-readiness and reporting
  slice (c3).
- The release gate that makes a reason required (c3).
