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
  tools columns. **A tool whose citation was inferred and not yet cleared is
  printed with ` (unconfirmed)`** (from `pending.uncleared_tools`). A row with
  one confirmed tool is not pending review, so without the mark an inferred
  tool beside a confirmed one would have reached the client looking confirmed.
  The summary sheet says what the mark means. Notes stays, because it has its
  own writer (the technique panel's PATCH).
- **Gaps sheet:** a Rationale column.
- **New Unscored sheet:** every technique the rollup counts as unscored, by
  code. It uses the rollup's own predicate and iterates the catalogue as the
  rollup does, so its length equals `rollup.unscored_count`.
- **Coverage %:** reads **"not measured"** wherever Covered + Partial + Gap is
  zero, in XLSX, DOCX and PDF, overall and per tactic, and in the stored
  `Deliverable.summary` the results list shows. It is not "n/a", which is the
  N/A status two columns away: "never assessed" would have read as "not
  applicable to us". Each renderer states the formula.
- **Text cells are safe:** model rationale and client-supplied tool names can
  no longer become an XLSX formula (a leading `=` is kept as text), and a
  control character is dropped instead of failing the finalize.

`attack/analytics.py` is unchanged: its 0.0 also feeds the dashboards (#489).

## Proof

The first-round tests fail against the unfixed exporter (9 of 27). Every fix
was then reverted on its own and turned a named test red: the XLSX, DOCX and PDF
percentage sites, the PDF definition, the Unscored predicate, the Gaps
rationale, the unconfirmed mark, the formula guard, the illegal-character strip,
the stored summary line (checked through the real finalize endpoint), and the
label. Measured on the live-run assessment: none of the 632 rationales contain a
redaction placeholder or begin with a formula character, so the last two
defended cases are latent, not live.

## Left alone, on purpose

The dashboards' identical `0.0%` reads `analytics.compute`, which is outside
this file: #489. CSF and ZT divide by the catalogue total, which is never zero,
so they do not share the defect.
