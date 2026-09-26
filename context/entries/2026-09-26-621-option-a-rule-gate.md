# 2026-09-26: #621's counts appear only under #620's rules (option (a))

Branch `track2/attack-status-surfaces`, re-merged onto `main` at `22c47a4`, which
has #620 in it.

Gene's advisor chose option (a) on 2026-09-26. #621's additions render only for
an assessment that `attack/rules.py::parents_computed` puts under D-094's rules:
one approved after #620 (`parent_rules = 2`), or a draft (NULL). An assessment
approved before #620 (`parent_rules = 1`) renders what was delivered.

The additions are the "Not verified N, Outside control surface M" counts, and
the rows, columns, cards, chips, filter options and definition wording that
carry them.

## Gated

- **XLSX, DOCX and PDF** (`exporters.states_outside_counts`, which reads
  `ctx.parents_computed`). Rule 1 is compared with the text recorded from
  `main` before #621 (`tests/golden/outside_counts_rule1/`).
- **The stored finalize summary.**
- **The client dashboard API.** The counts are omitted from the JSON, so #620's
  golden dashboard test passes unchanged.
- **The admin heatmap API.** The counts are null.
- **The home value card's count.** It is summed over new-rule assessments only,
  and is null when there are none.
- **The web client dashboard**: the counts, the two filter options, and the
  triad's ASSESSED-only population.
- **The admin heatmap card and matrix header**: the counts, the cards, and the
  definition.
- **The value card's hint.**

## Left ungated, and why

- **"X/Y scored"** takes Y from `catalogue_count`. That differs from scored +
  unscored only by Not verified rows, which a rule-1 assessment cannot hold.
  Nothing may write one.
- **Status labels and chips for the two statuses, and "Unknown status" in
  place of the N/A fallback.** These are reachable only through a status that
  a rule-1 assessment cannot store.
- **The Risk Register's link scope and its disclosure sentence.** The register
  is a separate deliverable built at generation time, not a re-render of an
  ATT&CK report. Its scope excludes Not verified rows, which a rule-1
  assessment has none of, and its findings under rule 1 are pinned by #620's
  golden test.
