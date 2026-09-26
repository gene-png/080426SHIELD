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
- **Round 1 of #692 found the same shape in the same file:**
  `_overview_sentences`, which all four renderers call, said "1 subcategories
  fall short of their target maturity" and "covers 1 in-scope NIST CSF 2.0
  subcategories". Both now agree with their counts ("subcategory falls short
  of its target"). The priority breakdown ("1 Priority 1 (critical), 0
  Priority 2, …") reads as labels at any count, so it stays. Filed: #696.
- **Round 2 found one more, in both full deliverables:** the per-function line
  "1 subcategories · … · 1 gap(s)." It is now built once, by
  `_function_detail`, which both `render_full_pdf` and `render_full_docx` call.
  A surface test through both renderers catches a renderer that goes back to
  an inline copy. An overview fixture with three subcategories and one gap
  now tells the two counts apart.
