# 2026-09-25: the ATT&CK workspace edits a row's reason code (#554 slice 4)

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
- **No narrative editor.** One was built here and removed after four review
  rounds: it only shows on rows no writer can produce yet (D-092 Decision 5),
  and each round found the next hole. It moves to #615, with the slice that
  makes `unable_to_determine` writable, and #615 carries the review rounds'
  findings as acceptance criteria. The coordinator's call, overturnable.
- **The API stores a blank narrative as NULL**, since the web is not the only
  writer and the release gate will ask whether one exists.
- The Reason select keeps a visible focus ring. The existing Notes box uses
  `focus:outline-hidden`, which CLAUDE.md records as cancelling it; that is not
  copied, and not changed here.

## Not in this slice

- Widening the web's `CoverageStatus` to the two new statuses, and every status
  badge and label that must learn them: the release-readiness and reporting
  slice (c3).
- The release gate that makes a reason required (c3).
