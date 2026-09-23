# 2026-09-23 — The ATT&CK workbook says what the assessment knows

Branch `fix/attack-workbook-says-what-it-knows`, base `df7d5b7`. Everything is in
`apps/api/app/attack/exporters.py`, which #482 owned until it merged.

## What was wrong, measured on the dev stack's one live-run assessment

| | stored | exported |
| --- | --- | --- |
| rationale | 632 of 633 rows | nowhere |
| detection / prevention / response tools | 515 rows with detection tools | nowhere |
| Notes (the sheet's only free-text column) | 0 of 633 rows | an empty column |
| the one unscored technique (`T1137.006`) | — | one "Unscored" cell among 633 rows |
| a tactic with nothing addressable | — | `0.0%`, the same figure as an all-gap tactic |

The last row is not hypothetical: another dev assessment has every
Reconnaissance technique unscored, so its Recon tactic exported 0.0%.

## What changed

- **Coverage sheet:** Rationale, Detection tools, Prevention tools and Response
  tools columns. Notes stays, because it has its own writer (the technique
  panel's PATCH) and a consultant's note is not the model's rationale.
- **Gaps sheet:** a Rationale column.
- **New Unscored sheet:** every technique the rollup counts as unscored, by
  code. It uses the rollup's own predicate (no row, no status, or an unrecognised
  status) and iterates the catalogue as the rollup does, so its length equals
  `rollup.unscored_count`.
- **Coverage %:** reads `n/a` wherever Covered + Partial + Gap is zero, in all
  three renderers (XLSX, DOCX, PDF), overall and per tactic. Each renderer states
  the formula beside the number. `attack/analytics.py` is unchanged: its 0.0 also
  feeds the dashboard and the risk register, so only what the deliverable prints
  changes here.

## Proof

The new tests fail against the unfixed exporter (9 of 27). Each fix was then
reverted on its own and turned exactly one named test red: the XLSX, DOCX and
PDF percentage sites separately, the PDF definition, the Unscored predicate,
and the Gaps rationale.

## Left alone, on purpose

The dashboard shows the same `0.0%` for nothing-addressable tactics. It reads
`analytics.compute`, is outside this file, and is filed separately.
