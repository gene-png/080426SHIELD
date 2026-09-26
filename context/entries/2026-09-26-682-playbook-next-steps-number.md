# 2026-09-26: the CSF playbook's next steps agree in number with their counts (#682)

Branch `track2/csf-playbook-number`, from `main` at `50395ab`.

- **What was wrong.** `csf/playbook_export.py::_next_steps` wrote "Remediate
  the 1 Priority 1 gap(s) first — these are Core-metric, high-impact,
  multi-system weaknesses." Priorities 2 and 3 carried the same "gap(s)"
  hedge. The PDF and the Word renderers both call this function, so both
  deliverables said it.
- **The fix.** Each sentence switches on its count: "gap"/"gaps", and for
  Priority 1 "this is a … weakness" or "these are … weaknesses".
- **The test.** A new file (no existing test read these sentences) pins the
  singular, the plural and the untouched no-gaps sentence, written out rather
  than derived. It was red first, and red again with `main`'s function
  restored.
- **Not in scope.** The "N gap(s) at target T4" summary lines in
  `routes/csf.py` and `routes/zt.py` hedge a count but carry no fixed plural
  pronoun. Several existing tests pin that exact text, so it is left alone.
- **Condition 6:** client-visible copy in a deliverable.
