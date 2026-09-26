# 2026-09-25: every ATT&CK surface reports the two new statuses (#554 c3a)

Branch `track2/attack-status-surfaces`, from `main` at `9c08bfb`.

## Why

The owner's reporting decision on #554: coverage is computed over ASSESSED
techniques only, and the not-verified count sits BESIDE the percentage on
every surface, never dropped. D-092 made `outside_control_surface` and
`unable_to_determine` storable but not writable (Decision 5), because no
surface could yet show them. This slice teaches the surfaces first.
`coverage.WRITABLE` is unchanged, so nothing new becomes writable (both statuses were already storable under D-092).

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

- Widening `coverage.WRITABLE`, the release-readiness gate (c3b, #622,
  blocked on #603 and #620), and the narrative editor (#615).

## Round 1 (review of 43edf12)

- **Three surfaces the first list missed now carry the counts:** the client
  dashboard's KPI row and Detect / Prevent / Respond triad, the home value
  card ("N techniques uncovered, M not verified", from a new API field
  `attack_not_verified_count`), and the admin matrix's per-tactic header.
- **The triad's denominator** leaves out the two new statuses. N/A stays in it,
  as before #554, because moving it would change a number on released
  dashboards. That is for the owner.
- **The web list is derived** (`attack-percentages-state-the-outside-counts.test.ts`):
  any component reading ATT&CK data that renders a coverage figure must state
  the counts. The API renderers stay a named registry.
- **Smaller fixes:** the heatmap card's formula matches the exports; the PDF
  calls the shared sentence; the admin badge renders an unknown status instead
  of throwing; `coverage.py` lists what remains before `WRITABLE` widens;
  D-092 is date-qualified.
- **Risk export wording** (the owner's recommendation, 2026-09-25; the final
  call is pending): the disclosure names "techniques marked Not verified"
  beside unscored rows, as the ATT&CK deliverable does. Citability is
  unchanged.

## Round 2 (review of d50a930)

- **"Scored" means the same rows in both client documents.** `coverage.UNJUDGED`
  is shared by the deliverable's `scored_count` and the Risk Register's citable
  scope. This reverses D-092 Decision 3's rule. The "X/Y" total is now
  `catalogue_count`, so it does not shrink.
- **`coverage.ASSESSED` is read, not restated**, and an AST guard fails on a
  hand-written covered + partial + gap under `app/`.
- **The web guard walks all of `src`**, pages included.
- **Gene's decision (2026-09-25):** N/A leaves the Detect / Prevent / Respond
  denominator, so it matches the KPI row. Condition 6.
- Filed: #634 (empty-state twins) and #635 (PDF header overflow).
