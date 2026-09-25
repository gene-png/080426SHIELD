# 2026-09-25: every ATT&CK surface reports the two new statuses (#554 c3a)

Branch `track2/attack-status-surfaces`, from `main` at `9c08bfb`.

## Why

The owner's reporting decision on #554: coverage is computed over ASSESSED
techniques only, and the not-verified count sits BESIDE the percentage on
every surface, never dropped. D-092 made `outside_control_surface` and
`unable_to_determine` storable but not writable (Decision 5), because no
surface could yet show them. This slice teaches the surfaces first.
`coverage.WRITABLE` is unchanged, so nothing new becomes storable.

## What changed

- **Deliverable (XLSX, DOCX, PDF) and the stored summary.** "Not verified N,
  Outside control surface M" beside the percentage, from one function
  (`outside_assessed_text`), shown even at zero. Both counts are also per
  tactic. The percentage's definition names both as outside it.
- **Client dashboard (API and page).** Both counts overall and per tactic, as
  required fields. The status chip names each new status, and shows a status it
  does not know as "Unknown status": it used to fall back to N/A, which would
  tell a client an unverified technique does not apply to them. The
  percentage's sentence carries both counts.
- **Admin workspace.** The status badge names both, and the heatmap card
  states both beside its percentage, always, with a tile each.
- **Risk link scope (my call, overturnable, recorded on #554).**
  `unable_to_determine` is not a judgement, so a risk entry cannot cite it.
  `outside_control_surface` is a judgement, like N/A, and stays citable.
- **A test that no surface can drop the count**
  (`test_attack_outside_assessed_on_every_surface.py`). It checks each
  renderer, the summary, the admin heatmap and the client dashboard, from rows
  written to the database, with literal counts.

## Not in this slice

- Widening `coverage.WRITABLE`, the release-readiness gate (c3b, blocked on
  #603 and #620), and the narrative editor (#615).
